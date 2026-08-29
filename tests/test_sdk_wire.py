"""Push a real ``anthropic`` SDK client through the adapter against a local HTTP stub.

This is the only test that imports the SDK, and it is skipped when the ``live``
extra is not installed. It never contacts Anthropic: ``base_url`` points at a
throwaway server on localhost that returns canned Messages API JSON. It proves
the request bodies the adapter builds (system, tools, output_config, echoed
thinking + tool_use blocks, merged tool_result blocks) are accepted by the SDK
and serialised on the wire exactly as intended.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

anthropic = pytest.importorskip("anthropic")

from prooftrail.agent import AnthropicModelClient, BudgetGuard, CostLedger, RefundAgent
from prooftrail.agent.tool_defs import REFUND_TOOL_SPECS
from prooftrail.scenarios import generate_scenario
from prooftrail.agent.tool_defs import build_refund_tool_actions


def _message(content: list[dict], stop_reason: str, *, input_tokens: int, output_tokens: int) -> dict:
    return {
        "id": "msg_stub",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


class _Stub(BaseHTTPRequestHandler):
    responses: list[dict] = []
    bodies: list[dict] = []
    headers_seen: list[dict] = []

    def do_POST(self):  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length", "0"))
        _Stub.bodies.append(json.loads(self.rfile.read(length)))
        _Stub.headers_seen.append({k.lower(): v for k, v in self.headers.items()})
        payload = json.dumps(_Stub.responses.pop(0)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):  # silence
        return


@pytest.fixture
def stub_server():
    server = HTTPServer(("127.0.0.1", 0), _Stub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _Stub.responses, _Stub.bodies, _Stub.headers_seen = [], [], []
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


def test_real_sdk_serialises_the_adapter_requests_against_a_local_stub(stub_server, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    scenario = generate_scenario("F02", 0)
    try:
        order = scenario.seeded.orders[0]
        request = scenario.user_requests[0]
        args = {"order_id": order["order_id"], "amount_cents": order["amount_cents"]}
        _Stub.responses = [
            _message(
                [
                    {"type": "thinking", "thinking": "", "signature": "sig-1"},
                    {"type": "tool_use", "id": "toolu_real_1", "name": "issue_refund", "input": args},
                ],
                "tool_use", input_tokens=900, output_tokens=40,
            ),
            _message(
                [{"type": "text", "text": "I retried the refund."},
                 {"type": "tool_use", "id": "toolu_real_2", "name": "issue_refund", "input": args}],
                "tool_use", input_tokens=1000, output_tokens=30,
            ),
            _message(
                [{"type": "text", "text": f"I refunded ${order['amount_cents'] / 100:.2f} for order {order['order_id']}."}],
                "end_turn", input_tokens=1100, output_tokens=20,
            ),
        ]
        sdk = anthropic.Anthropic(api_key="stub-not-a-real-key", base_url=stub_server, max_retries=0)
        client = AnthropicModelClient(
            model="claude-opus-5",
            client=sdk,
            budget=BudgetGuard(1.0, CostLedger(tmp_path / "ledger.jsonl")),
            label="F02-s00",
        )
        tools = build_refund_tool_actions(scenario.tools, lambda: scenario.ledger.last().seq if scenario.ledger.last() else None)
        scenario.record_user_intent(0)
        trace = RefundAgent(client, tools).run(case_id=scenario.case_id, user_requests=(request.to_dict(),))
        chain_ok, _ = scenario.ledger.verify_chain()
    finally:
        scenario.close()

    assert chain_ok
    assert trace.model == "claude-opus-5"
    assert trace.usage.llm_calls == 3 and trace.usage.input_tokens == 3000 and trace.usage.output_tokens == 90
    assert len(trace.tool_calls) == 2
    assert trace.tool_calls[0].error.startswith("ToolTimeout"), "F02 first call times out after commit"
    assert "txn_" not in trace.tool_calls[0].error, "timeout must not reveal commit status"
    assert trace.tool_calls[1].result["ok"] is True

    # What actually went over the wire.
    assert [h["x-api-key"] for h in _Stub.headers_seen] == ["stub-not-a-real-key"] * 3
    first, second, third = _Stub.bodies
    assert first["model"] == "claude-opus-5"
    assert first["max_tokens"] == 4096
    assert first["output_config"] == {"effort": "medium"}
    assert "thinking" not in first, "adaptive thinking is the model default; nothing is forced"
    assert first["system"].startswith("You are a customer-support refund agent.")
    assert [t["name"] for t in first["tools"]] == [spec.name for spec in REFUND_TOOL_SPECS]
    assert first["tools"][3]["input_schema"]["required"] == ["order_id", "amount_cents"]
    assert first["messages"] == [{"role": "user", "content": [{"type": "text", "text": request.text}]}]

    assert [m["role"] for m in second["messages"]] == ["user", "assistant", "user"]
    assistant = second["messages"][1]["content"]
    assert assistant[0] == {"type": "thinking", "thinking": "", "signature": "sig-1"}
    assert assistant[1] == {"type": "tool_use", "id": "toolu_real_1", "name": "issue_refund", "input": args}
    result_block = second["messages"][2]["content"][0]
    assert result_block["type"] == "tool_result" and result_block["tool_use_id"] == "toolu_real_1"
    assert result_block["is_error"] is True
    assert "commit status is unknown" in result_block["content"]

    assert [m["role"] for m in third["messages"]] == ["user", "assistant", "user", "assistant", "user"]
    assert third["messages"][3]["content"][0] == {"type": "text", "text": "I retried the refund."}
    ok_block = third["messages"][4]["content"][0]
    assert ok_block["tool_use_id"] == "toolu_real_2" and "is_error" not in ok_block
    assert json.loads(ok_block["content"])["ok"] is True

    # Provider metadata was captured from the SDK's typed response objects.
    provider = trace.messages[2]["provider"]
    assert provider["response_id"] == "msg_stub"
    assert provider["usage"]["input_tokens"] == 900
    assert provider["tool_call_ids"] == ["toolu_real_1"]
    assert trace.messages[2]["provider_content"][0]["type"] == "thinking"
