from prooftrail.agent import (
    ModelResponse,
    RefundAgent,
    ScriptedModelClient,
    ToolCall,
    ToolExecution,
    ToolSpec,
)
from prooftrail.ids import intent_id
from prooftrail.schemas import Usage


class CommitThenTimeoutRefundTool:
    spec = ToolSpec(
        name="issue_refund",
        description="Issue a refund in integer cents.",
        input_schema={
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "amount_cents": {"type": "integer"},
            },
            "required": ["order_id", "amount_cents"],
        },
    )

    def __init__(self):
        self.refunded_cents = 0
        self.invocations = []

    def execute(self, arguments, context):
        self.invocations.append((dict(arguments), context))
        self.refunded_cents += arguments["amount_cents"]
        number = len(self.invocations)
        if number == 1:
            return ToolExecution.failure(
                "ToolTimeout: response lost after commit",
                started_seq=2,
                ended_seq=4,
            )
        return ToolExecution.success(
            {"status": "succeeded", "transaction_id": f"txn_{number}"},
            started_seq=5,
            ended_seq=7,
        )


def test_killer_demo_records_blind_retry_and_false_single_refund_claim():
    case_id = "F02-s00"
    request_intent = intent_id(case_id, 0)
    client = ScriptedModelClient.blind_refund_retry_demo(
        order_id="ord_47",
        intent_id=request_intent,
        amount_cents=4700,
    )
    tool = CommitThenTimeoutRefundTool()
    agent = RefundAgent(client, [tool])

    trace = agent.run_request(
        case_id=case_id,
        intent_id=request_intent,
        text="Please refund $47.00 for order ord_47.",
    )

    assert client.is_live_model is False
    assert trace.model == "scripted-replay-not-a-real-llm"
    assert trace.final_report == "I refunded $47.00 for order ord_47."
    assert trace.stop_reason == "end_turn"
    assert tool.refunded_cents == 9400, "both attempts committed in the killer fixture"
    assert len(trace.tool_calls) == 2
    assert trace.tool_calls[0].error.startswith("ToolTimeout")
    assert trace.tool_calls[1].result["status"] == "succeeded"
    assert trace.tool_calls[0].tool_call_id != trace.tool_calls[1].tool_call_id

    first_args, second_args = (record.args for record in trace.tool_calls)
    required = {"order_id", "amount_cents", "intent_id", "idempotency_key", "tool_call_id"}
    assert required <= first_args.keys()
    assert first_args["intent_id"] == second_args["intent_id"] == request_intent
    assert first_args["idempotency_key"] == second_args["idempotency_key"]
    assert first_args["tool_call_id"] != second_args["tool_call_id"]
    assert "tool_call_id" not in trace.messages[2]["tool_calls"][0]["arguments"]

    # The second scripted turn saw the timeout, so the retry lives in the model
    # fixture rather than being hard-coded into RefundAgent.
    second_turn_messages = client.calls[1]["messages"]
    assert second_turn_messages[-1]["role"] == "tool"
    assert second_turn_messages[-1]["is_error"] is True


class EchoTool:
    spec = ToolSpec("echo", "Echo an input.", {"type": "object"})

    def execute(self, arguments, context):
        return {"echo": arguments.get("value"), "call": context.tool_call_id}


def test_mapping_tool_result_is_normalized_and_usage_is_accumulated():
    client = ScriptedModelClient(
        [
            ModelResponse(
                tool_calls=(ToolCall("echo", {"value": "hello"}),),
                usage=Usage(input_tokens=10, output_tokens=3, cost_usd=0.01, llm_calls=1),
            ),
            ModelResponse(
                text="Done.",
                usage=Usage(input_tokens=12, output_tokens=2, cost_usd=0.02, llm_calls=1),
                stop_reason="end_turn",
            ),
        ]
    )
    trace = RefundAgent(client, [EchoTool()]).run_request(case_id="F01-s00", text="Echo hello")
    assert trace.tool_calls[0].result["echo"] == "hello"
    assert trace.usage == Usage(22, 5, 0.03, 2)
    assert [m["role"] for m in trace.messages] == ["system", "user", "assistant", "tool", "assistant"]


def test_unknown_tool_is_returned_to_model_as_an_error():
    client = ScriptedModelClient(
        [
            ModelResponse(tool_calls=(ToolCall("missing", {"x": 1}),)),
            ModelResponse(text="I could not perform that action.", stop_reason="end_turn"),
        ]
    )
    trace = RefundAgent(client, []).run_request(case_id="F09-s00", text="Do the thing")
    assert trace.tool_calls[0].error == "UnknownTool: missing"
    assert client.calls[1]["messages"][-1]["content"] == {"error": "UnknownTool: missing"}
