import json

import pytest

from prooftrail.agent import (
    AnthropicModelClient,
    BudgetExceededError,
    BudgetGuard,
    CostLedger,
    MissingApiKeyError,
    ModelClient,
    ProviderTransientError,
    RefundAgent,
    ToolCall,
    ToolSpec,
    prompt_sha256,
)
from prooftrail.agent.anthropic_client import (
    compute_cost_usd,
    from_anthropic_message,
    is_transient_error,
    to_anthropic_messages,
)
from prooftrail.config import cost_usd
from prooftrail.ids import intent_id

from fakes import FakeAnthropic, FakeBlock, FakeMessage, FakeUsage, text_turn, tool_turn
from test_agent import CommitThenTimeoutRefundTool


def _client(responses, **kwargs) -> AnthropicModelClient:
    return AnthropicModelClient(
        model="claude-opus-5",
        client=FakeAnthropic(responses),
        sleep=lambda _seconds: None,
        **kwargs,
    )


def test_anthropic_client_satisfies_the_model_client_protocol():
    client = _client([text_turn("hi")])
    assert isinstance(client, ModelClient)
    assert client.is_live_model is True
    assert client.model_name == "claude-opus-5"


def test_live_run_records_model_usage_cost_prompt_hash_and_tool_calls():
    case_id = "F02-s00"
    request_intent = intent_id(case_id, 0)
    args = {"order_id": "ord_47", "amount_cents": 4700}
    client = _client(
        [
            tool_turn("issue_refund", args, call_id="toolu_a", input_tokens=100, output_tokens=20),
            tool_turn("issue_refund", args, call_id="toolu_b", input_tokens=150, output_tokens=10),
            text_turn("I refunded $47.00 for order ord_47.", input_tokens=200, output_tokens=8),
        ]
    )
    tool = CommitThenTimeoutRefundTool()
    trace = RefundAgent(client, [tool]).run_request(
        case_id=case_id, intent_id=request_intent, text="Please refund $47.00 for order ord_47."
    )

    assert trace.model == "claude-opus-5"
    assert trace.stop_reason == "end_turn"
    assert trace.usage.llm_calls == 3
    assert trace.usage.input_tokens == 450
    assert trace.usage.output_tokens == 38
    assert trace.usage.cost_usd == pytest.approx(cost_usd("claude-opus-5", 450, 38), abs=1e-6)
    assert len(trace.tool_calls) == 2
    assert tool.refunded_cents == 9400

    # The assistant transcript keeps provider ids, prompt hash, usage and stop reason.
    first_assistant = trace.messages[2]
    assert first_assistant["tool_calls"][0]["provider_call_id"] == "toolu_a"
    provider = first_assistant["provider"]
    assert provider["provider"] == "anthropic"
    assert provider["stop_reason"] == "tool_use"
    assert provider["usage"] == {
        "input_tokens": 100,
        "output_tokens": 20,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cost_usd": cost_usd("claude-opus-5", 100, 20),
    }
    assert len(provider["prompt_sha256"]) == 64
    assert provider["tool_call_ids"] == ["toolu_a"]
    assert provider["attempts"] == 1
    # Thinking blocks are frozen verbatim so they can be echoed back.
    assert first_assistant["provider_content"][0] == {
        "type": "thinking",
        "thinking": "(thinking)",
        "signature": "sig_toolu_a",
    }

    # The second request echoes the provider content and links the tool result
    # to the provider's tool_use id, not to ProofTrail's tool_call id.
    second_request = client._client.messages.requests[1]
    assert second_request["model"] == "claude-opus-5"
    assert second_request["max_tokens"] == 4096
    assert second_request["output_config"] == {"effort": "medium"}
    assert second_request["system"].startswith("You are a customer-support refund agent.")
    assistant_content = second_request["messages"][1]["content"]
    assert assistant_content[0]["type"] == "thinking"
    assert assistant_content[-1] == {"type": "tool_use", "id": "toolu_a", "name": "issue_refund", "input": args}
    tool_result = second_request["messages"][2]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "toolu_a"
    assert tool_result["is_error"] is True
    assert "ToolTimeout" in tool_result["content"]
    assert [call["attempts"] for call in client.calls] == [1, 1, 1]


def test_transient_failures_are_retried_but_tools_never_re_execute():
    args = {"order_id": "ord_1", "amount_cents": 100}
    sleeps: list[float] = []
    client = AnthropicModelClient(
        model="claude-opus-5",
        client=FakeAnthropic(
            [
                ProviderTransientError("connection reset"),
                tool_turn("issue_refund", args, call_id="toolu_x"),
                ProviderTransientError("overloaded"),
                ProviderTransientError("rate limited"),
                text_turn("Done: refunded $1.00 for order ord_1."),
            ]
        ),
        max_retries=3,
        retry_base_delay=0.5,
        sleep=sleeps.append,
    )
    tool = CommitThenTimeoutRefundTool()
    trace = RefundAgent(client, [tool]).run_request(case_id="F03-s00", text="Refund ord_1")

    assert len(tool.invocations) == 1, "a retried model call must not re-run the tool"
    assert [call["attempts"] for call in client.calls] == [2, 3]
    assert sleeps == [0.5, 0.5, 1.0]
    assert trace.messages[2]["provider"]["attempts"] == 2
    assert trace.final_report.startswith("Done")


def test_retries_are_bounded_and_non_transient_errors_are_not_retried():
    sleeps: list[float] = []
    client = AnthropicModelClient(
        model="claude-opus-5",
        client=FakeAnthropic([ProviderTransientError("a"), ProviderTransientError("b")]),
        max_retries=1,
        sleep=sleeps.append,
    )
    with pytest.raises(ProviderTransientError, match="b"):
        client.complete(messages=[{"role": "user", "content": "x"}], tools=(), max_output_tokens=10, effort="low")
    assert sleeps == [1.0]

    class Forbidden(Exception):
        status_code = 403

    client = AnthropicModelClient(
        model="claude-opus-5", client=FakeAnthropic([Forbidden("nope")]), sleep=sleeps.append
    )
    with pytest.raises(Forbidden):
        client.complete(messages=[{"role": "user", "content": "x"}], tools=(), max_output_tokens=10, effort="low")
    assert sleeps == [1.0], "no additional sleep for a non-transient error"


def test_transient_classification_covers_sdk_shapes_without_importing_it():
    class RateLimitError(Exception):
        status_code = 429

    class APIConnectionError(Exception):
        pass

    class Subclassed(APIConnectionError):
        pass

    class BadRequest(Exception):
        status_code = 400

    assert is_transient_error(RateLimitError())
    assert is_transient_error(APIConnectionError())
    assert is_transient_error(Subclassed())
    assert is_transient_error(ProviderTransientError())
    assert not is_transient_error(BadRequest())
    assert not is_transient_error(ValueError())


def test_budget_guard_blocks_before_the_call_and_records_real_spend(tmp_path):
    ledger = CostLedger(tmp_path / "cost_ledger.jsonl")
    tiny = BudgetGuard(0.0001, ledger)
    fake = FakeAnthropic([text_turn("hi")])
    client = AnthropicModelClient(model="claude-opus-5", client=fake, budget=tiny, sleep=lambda _s: None)
    with pytest.raises(BudgetExceededError, match="PROOFTRAIL_BUDGET_USD"):
        client.complete(messages=[{"role": "user", "content": "hello"}], tools=(), max_output_tokens=64, effort="low")
    assert fake.messages.requests == [], "the guard must refuse before any network call"
    assert ledger.entries() == []

    roomy = BudgetGuard(1.0, ledger)
    client = AnthropicModelClient(model="claude-opus-5", client=fake, budget=roomy, label="F01-s00", sleep=lambda _s: None)
    response = client.complete(messages=[{"role": "user", "content": "hello"}], tools=(), max_output_tokens=64, effort="low")
    assert response.text == "hi"
    rows = ledger.entries()
    assert len(rows) == 1
    assert rows[0]["label"] == "F01-s00"
    assert rows[0]["model"] == "claude-opus-5"
    assert rows[0]["input_tokens"] == 100 and rows[0]["output_tokens"] == 20
    assert rows[0]["cost_usd"] == cost_usd("claude-opus-5", 100, 20)
    assert rows[0]["cumulative_usd"] == rows[0]["cost_usd"]
    assert rows[0]["prompt_sha256"] == response.metadata["prompt_sha256"]
    # A fresh guard over the same ledger sees the spend, so the cap persists across processes.
    assert BudgetGuard(1.0, CostLedger(ledger.path)).spent_usd == rows[0]["cost_usd"]


def test_budget_guard_reads_env_and_rejects_non_positive_limits(monkeypatch, tmp_path):
    monkeypatch.setenv("PROOFTRAIL_BUDGET_USD", "2.5")
    guard = BudgetGuard.from_env(ledger_path=tmp_path / "ledger.jsonl")
    assert guard.limit_usd == 2.5
    assert guard.remaining_usd == 2.5
    assert BudgetGuard.from_env(limit_usd=7, ledger_path=tmp_path / "ledger.jsonl").limit_usd == 7
    monkeypatch.delenv("PROOFTRAIL_BUDGET_USD")
    assert BudgetGuard.from_env(ledger_path=tmp_path / "ledger.jsonl").limit_usd == 30.0
    with pytest.raises(ValueError):
        BudgetGuard(0)


def test_missing_api_key_is_a_clear_error_and_never_read_from_code(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(MissingApiKeyError, match="ANTHROPIC_API_KEY"):
        AnthropicModelClient(model="claude-opus-5")


def test_message_conversion_merges_parallel_tool_results_and_extracts_system():
    messages = [
        {"role": "system", "content": "SYSTEM"},
        {"role": "user", "intent_id": "int_1", "content": "Refund both."},
        {
            "role": "assistant",
            "content": "Looking up both orders.",
            "tool_calls": [
                {"id": "tc_1", "provider_call_id": "toolu_1", "name": "lookup_order", "arguments": {"order_id": "a"}},
                {"id": "tc_2", "provider_call_id": None, "name": "lookup_order", "arguments": {"order_id": "b"}},
            ],
        },
        {"role": "tool", "tool_call_id": "tc_1", "name": "lookup_order", "content": {"ok": True}, "is_error": False},
        {"role": "tool", "tool_call_id": "tc_2", "name": "lookup_order", "content": {"error": "boom"}, "is_error": True},
    ]
    system, converted = to_anthropic_messages(messages)
    assert system == "SYSTEM"
    assert [m["role"] for m in converted] == ["user", "assistant", "user"]
    assert converted[1]["content"] == [
        {"type": "text", "text": "Looking up both orders."},
        {"type": "tool_use", "id": "toolu_1", "name": "lookup_order", "input": {"order_id": "a"}},
        {"type": "tool_use", "id": "tc_2", "name": "lookup_order", "input": {"order_id": "b"}},
    ]
    results = converted[2]["content"]
    assert [r["tool_use_id"] for r in results] == ["toolu_1", "tc_2"]
    assert json.loads(results[0]["content"]) == {"ok": True}
    assert results[1]["is_error"] is True
    with pytest.raises(ValueError):
        to_anthropic_messages([{"role": "narrator", "content": "?"}])


def test_response_conversion_handles_refusals_and_cache_pricing():
    message = FakeMessage(
        [FakeBlock("text", text="")],
        "refusal",
        FakeUsage(input_tokens=1000, output_tokens=0, cache_read_input_tokens=500, cache_creation_input_tokens=200),
        stop_details={"type": "refusal", "category": "other"},
    )
    response = from_anthropic_message(message, model="claude-opus-5", prompt_hash="p" * 64)
    assert response.text == ""
    assert response.tool_calls == ()
    assert response.stop_reason == "refusal"
    assert response.metadata["stop_details"] == {"type": "refusal", "category": "other"}
    assert response.usage.input_tokens == 1700
    expected = compute_cost_usd(
        "claude-opus-5",
        input_tokens=1000,
        output_tokens=0,
        cache_read_input_tokens=500,
        cache_creation_input_tokens=200,
    )
    assert response.usage.cost_usd == expected
    assert expected == pytest.approx((1000 * 5 + 500 * 0.5 + 200 * 6.25) / 1_000_000, abs=1e-9)


def test_prompt_hash_is_stable_and_sensitive_to_every_input():
    tools = (ToolSpec("t", "d", {"type": "object"}),)
    base = dict(model="m", messages=[{"role": "user", "content": "x"}], tools=tools, max_output_tokens=5, effort="low")
    assert prompt_sha256(**base) == prompt_sha256(**base)
    assert prompt_sha256(**{**base, "effort": "high"}) != prompt_sha256(**base)
    assert prompt_sha256(**{**base, "model": "n"}) != prompt_sha256(**base)
    assert prompt_sha256(**{**base, "tools": ()}) != prompt_sha256(**base)


def test_tool_call_arguments_are_taken_from_the_provider_verbatim():
    message = tool_turn("lookup_order", {"order_id": "ord_9"}, call_id="toolu_9", thinking=None)
    response = from_anthropic_message(message, model="claude-opus-5", prompt_hash="h" * 64)
    assert response.tool_calls == (ToolCall("lookup_order", {"order_id": "ord_9"}, "toolu_9"),)
    assert response.raw_content == ({"type": "tool_use", "id": "toolu_9", "name": "lookup_order", "input": {"order_id": "ord_9"}},)
