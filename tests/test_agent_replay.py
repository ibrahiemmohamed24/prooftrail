import json
import tempfile
from pathlib import Path

from prooftrail.agent import (
    ModelResponse,
    RefundAgent,
    ScriptedModelClient,
    ToolCall,
    load_agent_trace,
    load_scripted_responses,
    save_agent_trace,
    save_scripted_responses,
)


def test_trace_roundtrip_is_utf8_and_stable():
    client = ScriptedModelClient([ModelResponse(text="تم رد المبلغ.", stop_reason="end_turn")])
    trace = RefundAgent(client, []).run_request(case_id="F01-s03", text="رجّع المبلغ")
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "trace.json"
        save_agent_trace(trace, target)
        assert load_agent_trace(target) == trace
        assert "تم رد المبلغ" in target.read_text(encoding="utf-8")
        assert target.read_bytes().endswith(b"\n")


def test_scripted_response_roundtrip_can_drive_a_fresh_client():
    responses = (
        ModelResponse(tool_calls=(ToolCall("lookup_order", {"order_id": "ord_1"}),)),
        ModelResponse(text="Order found.", stop_reason="end_turn"),
    )
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "responses.json"
        save_scripted_responses(responses, target)
        loaded = load_scripted_responses(target)
        assert loaded == responses
        assert json.loads(target.read_text(encoding="utf-8"))[0]["tool_calls"][0]["name"] == "lookup_order"
        assert ScriptedModelClient(loaded).remaining == 2
