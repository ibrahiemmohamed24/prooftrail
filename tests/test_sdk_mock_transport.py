"""Drive the real ``anthropic`` SDK through the adapter over ``httpx2.MockTransport``.

Skipped when the ``live`` extra is not installed. No socket is opened: the
SDK's own HTTP client is given a mock transport, so this proves the request
bodies the adapter builds are serialised by the SDK exactly as intended, that
typed SDK responses are parsed into ``ModelResponse``, and that the SDK's real
exception classes are classified correctly by the bounded retry policy.
"""
from __future__ import annotations

import json

import pytest

anthropic = pytest.importorskip("anthropic")
httpx2 = pytest.importorskip("httpx2")

from prooftrail.agent import AnthropicModelClient, BudgetGuard, CostLedger, RefundAgent
from prooftrail.agent.anthropic_client import is_transient_error
from prooftrail.agent.tool_defs import REFUND_TOOL_SPECS, build_refund_tool_actions
from prooftrail.scenarios import generate_scenario


def _message(content: list[dict], stop_reason: str, *, input_tokens: int, output_tokens: int) -> dict:
    return {
        "id": "msg_mock",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


def _error(status: int, kind: str, message: str) -> dict:
    return {"type": "error", "error": {"type": kind, "message": message}}


class MockAPI:
    """Queue of (status, json) replies; records every request body and header."""

    def __init__(self, replies: list[tuple[int, dict]]):
        self.replies = list(replies)
        self.bodies: list[dict] = []
        self.headers: list[dict] = []

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/messages"
        self.bodies.append(json.loads(request.content))
        self.headers.append({k.lower(): v for k, v in request.headers.items()})
        status, payload = self.replies.pop(0)
        return httpx2.Response(status, json=payload)

    def client(self) -> "anthropic.Anthropic":
        return anthropic.Anthropic(
            api_key="mock-not-a-real-key",
            max_retries=0,
            http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(self.handler)),
        )


def test_sdk_serialises_adapter_requests_and_parses_typed_responses(tmp_path):
    scenario = generate_scenario("F02", 0)
    try:
        order = scenario.seeded.orders[0]
        request = scenario.user_requests[0]
        args = {"order_id": order["order_id"], "amount_cents": order["amount_cents"]}
        api = MockAPI(
            [
                (200, _message(
                    [
                        {"type": "thinking", "thinking": "", "signature": "sig-1"},
                        {"type": "tool_use", "id": "toolu_real_1", "name": "issue_refund", "input": args},
                    ],
                    "tool_use", input_tokens=900, output_tokens=40,
                )),
                (200, _message(
                    [
                        {"type": "text", "text": "I retried the refund."},
                        {"type": "tool_use", "id": "toolu_real_2", "name": "issue_refund", "input": args},
                    ],
                    "tool_use", input_tokens=1000, output_tokens=30,
                )),
                (200, _message(
                    [{"type": "text", "text": f"I refunded ${order['amount_cents'] / 100:.2f} for order {order['order_id']}."}],
                    "end_turn", input_tokens=1100, output_tokens=20,
                )),
            ]
        )
        client = AnthropicModelClient(
            model="claude-opus-5",
            client=api.client(),
            budget=BudgetGuard(5.0, CostLedger(tmp_path / "ledger.jsonl")),
            label="F02-s00",
        )
        tools = build_refund_tool_actions(
            scenario.tools, lambda: scenario.ledger.last().seq if scenario.ledger.last() else None
        )
        scenario.record_user_intent(0)
        trace = RefundAgent(client, tools).run(case_id=scenario.case_id, user_requests=(request.to_dict(),))
        chain_ok, _ = scenario.ledger.verify_chain()
    finally:
        scenario.close()

    assert chain_ok
    assert trace.model == "claude-opus-5"
    assert trace.usage.llm_calls == 3 and trace.usage.input_tokens == 3000 and trace.usage.output_tokens == 90
    assert len(trace.tool_calls) == 2
    assert trace.tool_calls[0].error.startswith("ToolTimeout") and "txn_" not in trace.tool_calls[0].error
    assert trace.tool_calls[1].result["ok"] is True

    assert [h["x-api-key"] for h in api.headers] == ["mock-not-a-real-key"] * 3
    assert all("anthropic-version" in h for h in api.headers)
    first, second, third = api.bodies
    assert first["model"] == "claude-opus-5" and first["max_tokens"] == 4096
    assert first["output_config"] == {"effort": "medium"}
    assert "thinking" not in first, "adaptive thinking is the model default; nothing is forced"
    assert first["system"].startswith("You are a customer-support refund agent.")
    assert [t["name"] for t in first["tools"]] == [spec.name for spec in REFUND_TOOL_SPECS]
    assert first["messages"] == [{"role": "user", "content": [{"type": "text", "text": request.text}]}]

    assert [m["role"] for m in second["messages"]] == ["user", "assistant", "user"]
    assistant = second["messages"][1]["content"]
    assert assistant[0] == {"type": "thinking", "thinking": "", "signature": "sig-1"}
    assert assistant[1] == {"type": "tool_use", "id": "toolu_real_1", "name": "issue_refund", "input": args}
    result_block = second["messages"][2]["content"][0]
    assert result_block["type"] == "tool_result" and result_block["tool_use_id"] == "toolu_real_1"
    assert result_block["is_error"] is True and "commit status is unknown" in result_block["content"]

    assert [m["role"] for m in third["messages"]] == ["user", "assistant", "user", "assistant", "user"]
    ok_block = third["messages"][4]["content"][0]
    assert ok_block["tool_use_id"] == "toolu_real_2" and "is_error" not in ok_block
    assert json.loads(ok_block["content"])["ok"] is True

    provider = trace.messages[2]["provider"]
    assert provider["response_id"] == "msg_mock"
    assert provider["usage"]["input_tokens"] == 900
    assert provider["tool_call_ids"] == ["toolu_real_1"]
    assert trace.messages[2]["provider_content"][0]["type"] == "thinking"


def test_real_sdk_errors_are_retried_only_when_transient(tmp_path):
    ok = _message([{"type": "text", "text": "fine"}], "end_turn", input_tokens=10, output_tokens=2)
    api = MockAPI(
        [
            (529, _error(529, "overloaded_error", "Overloaded")),
            (429, _error(429, "rate_limit_error", "Slow down")),
            (500, _error(500, "api_error", "Internal")),
            (200, ok),
        ]
    )
    sleeps: list[float] = []
    client = AnthropicModelClient(model="claude-opus-5", client=api.client(), max_retries=3, sleep=sleeps.append)
    response = client.complete(
        messages=[{"role": "user", "content": "hi"}], tools=(), max_output_tokens=32, effort="low"
    )
    assert response.text == "fine"
    assert response.metadata["attempts"] == 4
    assert sleeps == [1.0, 2.0, 4.0]
    assert len(api.bodies) == 4

    api = MockAPI([(400, _error(400, "invalid_request_error", "bad request"))])
    client = AnthropicModelClient(model="claude-opus-5", client=api.client(), max_retries=3, sleep=sleeps.append)
    with pytest.raises(anthropic.BadRequestError):
        client.complete(messages=[{"role": "user", "content": "hi"}], tools=(), max_output_tokens=32, effort="low")
    assert len(api.bodies) == 1, "4xx must not be retried"

    assert is_transient_error(anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x")))
    assert is_transient_error(anthropic.APITimeoutError(request=httpx2.Request("POST", "https://x")))


def test_budget_guard_refuses_before_the_sdk_sends_anything(tmp_path):
    api = MockAPI([(200, _message([{"type": "text", "text": "never"}], "end_turn", input_tokens=1, output_tokens=1))])
    client = AnthropicModelClient(
        model="claude-opus-5",
        client=api.client(),
        budget=BudgetGuard(0.0001, CostLedger(tmp_path / "ledger.jsonl")),
    )
    from prooftrail.agent import BudgetExceededError

    with pytest.raises(BudgetExceededError):
        client.complete(messages=[{"role": "user", "content": "hi"}], tools=(), max_output_tokens=4096, effort="low")
    assert api.bodies == []
