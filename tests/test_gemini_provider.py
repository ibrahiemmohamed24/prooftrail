import json
from email.message import Message
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from prooftrail import cli
import prooftrail.agent.gemini_client as gemini_module
from prooftrail.agent import (
    FreeTierConfirmationError,
    GeminiModelClient,
    GeminiResponseError,
    GeminiTransportError,
    MissingGeminiApiKeyError,
    ModelClient,
    RefundAgent,
    ToolSpec,
)
from prooftrail.agent.gemini_client import (
    from_gemini_response,
    list_price_equivalent_usd,
    to_gemini_contents,
    urllib_transport,
)
from prooftrail.agent.runner import MODE_LIVE, MODE_REPLAY
from prooftrail.ids import intent_id

from test_agent import CommitThenTimeoutRefundTool


def gemini_tool_turn(name, args, *, call_id, input_tokens=100, output_tokens=10):
    return {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {
                            "functionCall": {"id": call_id, "name": name, "args": args},
                            "thoughtSignature": f"signature_{call_id}",
                        }
                    ],
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": input_tokens,
            "candidatesTokenCount": output_tokens,
            "thoughtsTokenCount": 3,
            "totalTokenCount": input_tokens + output_tokens + 3,
            "serviceTier": "STANDARD",
        },
        "modelVersion": "gemini-3.7-flash-20260801",
        "responseId": f"resp_{call_id}",
    }


def gemini_text_turn(text, *, input_tokens=100, output_tokens=10):
    return {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [{"text": text, "thoughtSignature": "signature_final"}],
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": input_tokens,
            "candidatesTokenCount": output_tokens,
            "thoughtsTokenCount": 2,
            "totalTokenCount": input_tokens + output_tokens + 2,
            "serviceTier": "STANDARD",
        },
        "modelVersion": "gemini-3.7-flash-20260801",
        "responseId": "resp_final",
    }


class FakeGeminiTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, url, headers, payload, timeout_seconds):
        self.requests.append(
            {
                "url": url,
                "headers": dict(headers),
                "payload": json.loads(json.dumps(payload)),
                "timeout_seconds": timeout_seconds,
            }
        )
        if not self.responses:
            raise AssertionError("fake Gemini response script exhausted")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _client(responses, **kwargs):
    transport = FakeGeminiTransport(responses)
    client = GeminiModelClient(
        model="gemini-3.7-flash",
        api_key="fake-test-key",
        free_tier_confirmed=True,
        transport=transport,
        min_interval_seconds=0,
        sleep=lambda _seconds: None,
        **kwargs,
    )
    return client, transport


def test_gemini_client_is_a_real_model_client_and_records_free_tier_provenance():
    case_id = "F02-s00"
    args = {"order_id": "ord_47", "amount_cents": 4700}
    client, transport = _client(
        [
            gemini_tool_turn("issue_refund", args, call_id="call_a", input_tokens=100),
            gemini_tool_turn("issue_refund", args, call_id="call_b", input_tokens=150),
            gemini_text_turn("I refunded $47.00 for order ord_47.", input_tokens=200),
        ]
    )
    assert isinstance(client, ModelClient)
    tool = CommitThenTimeoutRefundTool()
    trace = RefundAgent(client, [tool]).run_request(
        case_id=case_id,
        intent_id=intent_id(case_id, 0),
        text="Please refund $47.00 for order ord_47.",
    )

    assert trace.model == "gemini-3.7-flash"
    assert trace.usage.llm_calls == 3
    assert trace.usage.input_tokens == 450
    assert trace.usage.output_tokens == 38
    assert trace.usage.cost_usd == 0.0
    assert tool.refunded_cents == 9400
    assert len(tool.invocations) == 2

    first_assistant = trace.messages[2]
    assert first_assistant["provider"]["provider"] == "google-gemini"
    assert first_assistant["provider"]["pricing_tier"] == "free"
    assert first_assistant["provider"]["billed_cost_usd"] == 0.0
    assert first_assistant["provider"]["usage"]["list_price_equivalent_usd"] > 0
    assert first_assistant["provider_content"][0]["thoughtSignature"] == "signature_call_a"

    second_payload = transport.requests[1]["payload"]
    model_parts = second_payload["contents"][1]["parts"]
    assert model_parts[0]["thoughtSignature"] == "signature_call_a"
    function_result = second_payload["contents"][2]["parts"][0]["functionResponse"]
    assert function_result["id"] == "call_a"
    assert function_result["name"] == "issue_refund"
    assert "ToolTimeout" in function_result["response"]["error"]
    assert transport.requests[0]["url"].endswith("/models/gemini-3.7-flash:generateContent")
    assert "fake-test-key" not in transport.requests[0]["url"]
    assert transport.requests[0]["headers"]["x-goog-api-key"] == "fake-test-key"
    assert "fake-test-key" not in json.dumps(trace.to_dict())
    assert "fake-test-key" not in json.dumps(client.calls)


def test_gemini_retries_provider_only_and_never_reexecutes_a_tool():
    args = {"order_id": "ord_1", "amount_cents": 100}
    sleeps = []
    transport = FakeGeminiTransport(
        [
            GeminiTransportError("rate limited", status_code=429, retry_after_seconds=7),
            gemini_tool_turn("issue_refund", args, call_id="call_1"),
            GeminiTransportError("overloaded", status_code=503),
            gemini_text_turn("Done: refunded $1.00 for order ord_1."),
        ]
    )
    client = GeminiModelClient(
        api_key="fake-test-key",
        free_tier_confirmed=True,
        transport=transport,
        min_interval_seconds=0,
        retry_base_delay=1,
        sleep=sleeps.append,
    )
    tool = CommitThenTimeoutRefundTool()
    trace = RefundAgent(client, [tool]).run_request(case_id="F03-s00", text="Refund ord_1")

    assert len(tool.invocations) == 1
    assert [row["attempts"] for row in client.calls] == [2, 2]
    assert sleeps == [7, 1]
    assert trace.final_report.startswith("Done")


def test_gemini_rejects_paid_or_unconfirmed_configuration_before_network(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("PROOFTRAIL_GEMINI_FREE_TIER", raising=False)
    with pytest.raises(FreeTierConfirmationError, match="Plan column says Free"):
        GeminiModelClient(api_key="fake-test-key")
    with pytest.raises(MissingGeminiApiKeyError, match="GEMINI_API_KEY"):
        GeminiModelClient(free_tier_confirmed=True)
    with pytest.raises(FreeTierConfirmationError, match="allowlist"):
        GeminiModelClient(
            model="gemini-paid-future-model",
            api_key="fake-test-key",
            free_tier_confirmed=True,
        )


def test_gemini_response_parser_excludes_thought_text_and_fails_closed_without_candidate():
    payload = gemini_text_turn("final answer", input_tokens=20, output_tokens=5)
    payload["candidates"][0]["content"]["parts"].insert(
        0, {"text": "internal summary", "thought": True, "thoughtSignature": "secret-state"}
    )
    response = from_gemini_response(
        payload, model="gemini-3.7-flash", prompt_hash="p" * 64
    )
    assert response.text == "final answer"
    assert response.raw_content[0]["thoughtSignature"] == "secret-state"
    assert response.usage.cost_usd == 0.0
    assert list_price_equivalent_usd("gemini-3.7-flash", 1_000_000, 1_000_000) == 4.5
    with pytest.raises(GeminiResponseError, match="block_reason=SAFETY"):
        from_gemini_response(
            {"promptFeedback": {"blockReason": "SAFETY"}},
            model="gemini-3.7-flash",
            prompt_hash="p" * 64,
        )


def test_gemini_content_conversion_preserves_parallel_parts_and_call_ids():
    messages = [
        {"role": "system", "content": "SYSTEM"},
        {"role": "user", "content": "Look up both"},
        {
            "role": "assistant",
            "content": "",
            "provider_content": [
                {
                    "functionCall": {"id": "fc_1", "name": "lookup", "args": {"x": 1}},
                    "thoughtSignature": "sig",
                },
                {"functionCall": {"id": "fc_2", "name": "lookup", "args": {"x": 2}}},
            ],
            "tool_calls": [
                {"id": "tc_1", "provider_call_id": "fc_1", "name": "lookup", "arguments": {"x": 1}},
                {"id": "tc_2", "provider_call_id": "fc_2", "name": "lookup", "arguments": {"x": 2}},
            ],
        },
        {"role": "tool", "tool_call_id": "tc_1", "name": "lookup", "content": {"ok": 1}},
        {"role": "tool", "tool_call_id": "tc_2", "name": "lookup", "content": {"ok": 2}},
    ]
    system, contents = to_gemini_contents(messages)
    assert system == "SYSTEM"
    assert [item["role"] for item in contents] == ["user", "model", "user"]
    assert contents[1]["parts"][0]["thoughtSignature"] == "sig"
    responses = contents[2]["parts"]
    assert [part["functionResponse"]["id"] for part in responses] == ["fc_1", "fc_2"]


def test_gemini_content_fallback_builds_function_parts_and_rejects_bad_history():
    messages = [
        {"role": "system", "content": "SYSTEM"},
        {"role": "user", "content": "Do it"},
        {
            "role": "assistant",
            "content": "Checking",
            "tool_calls": [
                {
                    "id": "tc_1",
                    "provider_call_id": "fc_1",
                    "name": "lookup",
                    "arguments": {"x": 1},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "tc_1", "name": "lookup", "content": "ok"},
    ]
    system, contents = to_gemini_contents(messages)
    assert system == "SYSTEM"
    assert contents[1]["parts"] == [
        {"text": "Checking"},
        {"functionCall": {"name": "lookup", "args": {"x": 1}, "id": "fc_1"}},
    ]
    assert contents[2]["parts"][0]["functionResponse"]["response"] == {"result": "ok"}
    with pytest.raises(ValueError, match="system messages must precede"):
        to_gemini_contents(
            [{"role": "user", "content": "x"}, {"role": "system", "content": "late"}]
        )
    with pytest.raises(ValueError, match="unsupported message role"):
        to_gemini_contents([{"role": "narrator", "content": "x"}])


def test_gemini_retry_bounds_nontransient_errors_and_paces_calls(monkeypatch):
    with pytest.raises(ValueError, match="max_retries"):
        GeminiModelClient(
            api_key="fake-test-key", free_tier_confirmed=True, max_retries=-1
        )

    client, transport = _client(
        [GeminiTransportError("bad request", status_code=400)], max_retries=5
    )
    with pytest.raises(GeminiTransportError, match="bad request"):
        client.complete(
            messages=[{"role": "user", "content": "x"}],
            tools=(),
            max_output_tokens=8,
            effort="low",
        )
    assert len(transport.requests) == 1

    client, _transport = _client(
        [GeminiTransportError("busy", status_code=503), GeminiTransportError("busy", status_code=503)],
        max_retries=1,
    )
    with pytest.raises(GeminiTransportError, match="busy"):
        client.complete(
            messages=[{"role": "user", "content": "x"}],
            tools=(),
            max_output_tokens=8,
            effort="low",
        )

    times = iter([10.0, 11.0, 15.0])
    sleeps = []
    transport = FakeGeminiTransport([gemini_text_turn("a"), gemini_text_turn("b")])
    paced = GeminiModelClient(
        api_key="fake-test-key",
        free_tier_confirmed=True,
        transport=transport,
        min_interval_seconds=4,
        sleep=sleeps.append,
        monotonic=lambda: next(times),
    )
    for text in ("one", "two"):
        paced.complete(
            messages=[{"role": "user", "content": text}],
            tools=(),
            max_output_tokens=8,
            effort="low",
        )
    assert sleeps == [3.0]

    monkeypatch.setenv("PROOFTRAIL_GEMINI_FREE_TIER", "true")
    env_confirmed = GeminiModelClient(
        api_key="fake-test-key",
        transport=FakeGeminiTransport([gemini_text_turn("ok")]),
        min_interval_seconds=0,
    )
    assert env_confirmed.model_name == "gemini-3.7-flash"
    assert list_price_equivalent_usd("unknown", 10, 10) == 0.0


def test_urllib_transport_success_and_redacted_failures(monkeypatch):
    class Response:
        def __init__(self, raw):
            self.raw = raw

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return self.raw

    monkeypatch.setattr(gemini_module, "urlopen", lambda *_args, **_kwargs: Response(b'{"ok": true}'))
    assert urllib_transport("https://example.invalid", {}, {"x": 1}, 1) == {"ok": True}

    monkeypatch.setattr(gemini_module, "urlopen", lambda *_args, **_kwargs: Response(b"not-json"))
    with pytest.raises(GeminiTransportError, match="invalid JSON"):
        urllib_transport("https://example.invalid", {}, {"x": 1}, 1)

    headers = Message()
    headers["Retry-After"] = "9"
    error_body = BytesIO(b'{"error":{"message":"quota exhausted"}}')

    def rate_limited(*_args, **_kwargs):
        raise HTTPError("https://example.invalid", 429, "rate", headers, error_body)

    monkeypatch.setattr(gemini_module, "urlopen", rate_limited)
    with pytest.raises(GeminiTransportError, match="quota exhausted") as caught:
        urllib_transport("https://example.invalid", {"x-goog-api-key": "secret"}, {}, 1)
    assert caught.value.status_code == 429
    assert caught.value.retry_after_seconds == 9
    assert "secret" not in str(caught.value)

    monkeypatch.setattr(
        gemini_module, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline"))
    )
    with pytest.raises(GeminiTransportError, match="network error"):
        urllib_transport("https://example.invalid", {}, {}, 1)


def _fake_gemini_factory(script_builder):
    from prooftrail.scenarios import generate_scenario

    def build(*, model, label):
        family, _, seed = label.partition("-s")
        scenario = generate_scenario(family, int(seed))
        try:
            request = scenario.user_requests[0]
            order = scenario.seeded.orders[0]
            script = script_builder(
                order_id=order["order_id"],
                intent_id=request.intent_id,
                amount_cents=order["amount_cents"],
            )
        finally:
            scenario.close()
        client, _transport = _client(script, label=label)
        return client

    return build


def _blind_retry_script(*, order_id, intent_id, amount_cents):
    del intent_id
    args = {"order_id": order_id, "amount_cents": amount_cents}
    return [
        gemini_tool_turn("issue_refund", args, call_id="call_a"),
        gemini_tool_turn("issue_refund", args, call_id="call_b"),
        gemini_text_turn(f"I refunded ${amount_cents / 100:.2f} for order {order_id}."),
    ]


def test_gemini_cli_live_then_replays_for_zero_billed_cost(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "build_gemini_client", _fake_gemini_factory(_blind_retry_script))
    cache_dir = tmp_path / "cache"
    live_out = tmp_path / "live"
    code = cli.main(
        [
            "agent", "run", "--live", "--provider", "gemini",
            "--family", "F02", "--seed", "0",
            "--cache-dir", str(cache_dir), "--output", str(live_out), "--json",
        ]
    )
    assert code == 0
    live = json.loads(capsys.readouterr().out)
    assert live["mode"] == MODE_LIVE
    assert live["provider"] == "gemini"
    assert live["pricing_tier"] == "free"
    assert live["billed_cost_usd"] == 0.0
    assert live["usage"]["llm_calls"] == 3
    assert live["usage"]["cost_usd"] == 0.0
    assert live["cache_misses"] == 3 and live["cache_hits"] == 0
    case = json.loads((live_out / "case.json").read_text(encoding="utf-8"))

    monkeypatch.setattr(
        cli,
        "build_gemini_client",
        lambda **_: pytest.fail("Gemini replay must never construct a live client"),
    )
    replay_out = tmp_path / "replayed"
    code = cli.main(
        [
            "agent", "run", "--replay", "--provider", "gemini",
            "--family", "F02", "--seed", "0",
            "--cache-dir", str(cache_dir), "--output", str(replay_out), "--json",
        ]
    )
    assert code == 0
    replay = json.loads(capsys.readouterr().out)
    assert replay["mode"] == MODE_REPLAY
    assert replay["cache_hits"] == 3 and replay["cache_misses"] == 0
    replayed = json.loads((replay_out / "case.json").read_text(encoding="utf-8"))
    assert replayed == case
