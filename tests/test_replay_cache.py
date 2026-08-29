import json

import pytest

from prooftrail.agent import (
    CachingModelClient,
    ModelResponse,
    RefundAgent,
    ReplayCache,
    ReplayCacheMiss,
    ScriptedModelClient,
    ToolCall,
)
from prooftrail.agent.runner import MODE_LIVE, MODE_REPLAY, run_case
from prooftrail.schemas import Usage

from test_agent import EchoTool


def _script() -> ScriptedModelClient:
    return ScriptedModelClient(
        [
            ModelResponse(
                tool_calls=(ToolCall("echo", {"value": "hello"}, "toolu_1"),),
                usage=Usage(10, 3, 0.01, 1),
                stop_reason="tool_use",
                raw_content=({"type": "thinking", "thinking": "", "signature": "s"},),
                metadata={"prompt_sha256": "x" * 64},
            ),
            ModelResponse(text="Done.", usage=Usage(12, 2, 0.02, 1), stop_reason="end_turn"),
        ],
        model_name="claude-opus-5",
    )


def test_recording_then_replaying_reproduces_the_identical_trace(tmp_path):
    path = tmp_path / "F01-s00.json"
    recorder = CachingModelClient(ReplayCache(path), _script())
    live_trace = RefundAgent(recorder, [EchoTool()]).run_request(case_id="F01-s00", text="Echo hello")
    assert recorder.misses == 2 and recorder.hits == 0
    assert live_trace.usage == Usage(22, 5, 0.03, 2)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["model"] == "claude-opus-5"
    assert len(payload["order"]) == 2

    replayer = CachingModelClient(ReplayCache(path), None)
    assert replayer.is_live_model is False
    assert replayer.model_name == "claude-opus-5"
    replay_trace = RefundAgent(replayer, [EchoTool()]).run_request(case_id="F01-s00", text="Echo hello")
    assert replayer.hits == 2 and replayer.misses == 0
    assert replay_trace == live_trace
    assert replay_trace.messages[2]["provider_content"][0]["signature"] == "s"


def test_replay_refuses_to_answer_prompts_it_never_saw(tmp_path):
    cache = ReplayCache(tmp_path / "missing.json")
    replayer = CachingModelClient(cache, None, model_name="claude-opus-5")
    with pytest.raises(ReplayCacheMiss, match="never recorded|diverged"):
        RefundAgent(replayer, [EchoTool()]).run_request(case_id="F01-s00", text="Echo hello")
    assert len(cache) == 0


def test_cache_totals_and_model_consistency(tmp_path):
    cache = ReplayCache(tmp_path / "c.json")
    cache.put("k1", ModelResponse(text="a", usage=Usage(5, 1, 0.001, 1)), model="m")
    cache.put("k2", ModelResponse(text="b", usage=Usage(7, 2, 0.002, 1)), model="m")
    cache.put("k1", ModelResponse(text="a2", usage=Usage(5, 1, 0.001, 1)), model="m")
    assert cache.order == ("k1", "k2")
    assert cache.total_usage() == {"input_tokens": 12, "output_tokens": 3, "cost_usd": 0.003, "llm_calls": 2}
    with pytest.raises(ValueError):
        cache.put("k3", ModelResponse(text="c"), model="other")
    cache.clear()
    assert not cache.path.exists() and len(cache) == 0


def test_run_case_records_every_user_intent_in_order_and_is_family_agnostic():
    client = ScriptedModelClient(
        [
            ModelResponse(text="I did not perform any refund yet.", stop_reason="end_turn"),
            ModelResponse(text="I did not perform the second refund either.", stop_reason="end_turn"),
        ]
    )
    run = run_case("F07", 1, model_client=client, mode=MODE_REPLAY)
    intents = [event for event in run.case.ledger if event.event_type == "user_intent"]
    assert [event.intent_id for event in intents] == [r["intent_id"] for r in run.case.trace.user_requests]
    assert run.case.family_id == "F07" and run.case.seed == 1
    assert run.mode == MODE_REPLAY
    assert run.ledger_chain_valid is True
    assert run.ground_truth.verified_by_human is False
    assert len(run.order_states) == 2
    summary = run.summary()
    assert summary["tool_call_count"] == 0
    assert summary["usage"]["llm_calls"] == 0


def test_run_case_reports_external_claims_only_when_the_agent_used_the_unledgered_tool():
    client = ScriptedModelClient(
        [
            ModelResponse(tool_calls=(ToolCall("send_email", {"to": "x@example.com", "subject": "s", "body": "b"}),)),
            ModelResponse(text="I emailed you a confirmation.", stop_reason="end_turn"),
        ]
    )
    run = run_case("F01", 0, model_client=client, mode=MODE_LIVE)
    claim_types = [claim["claim_type"] for claim in run.ground_truth.expected_claims]
    assert "external_side_effect" in claim_types
