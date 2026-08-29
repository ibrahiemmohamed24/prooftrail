import json

import pytest

from prooftrail import cli
from prooftrail.agent import AnthropicModelClient, ScriptedModelClient
from prooftrail.agent.runner import MODE_LIVE, MODE_REPLAY

from fakes import FakeAnthropic, blind_retry_script, text_turn


def _fake_live_factory(script_builder):
    from prooftrail.scenarios import generate_scenario

    def build(*, model, budget, label):
        family, _, seed = label.partition("-s")
        scenario = generate_scenario(family, int(seed))
        try:
            request = scenario.user_requests[0]
            order = scenario.seeded.orders[0]
            script = script_builder(order_id=order["order_id"], intent_id=request.intent_id, amount_cents=order["amount_cents"])
        finally:
            scenario.close()
        return AnthropicModelClient(model=model, client=FakeAnthropic(script), budget=budget, label=label, sleep=lambda _s: None)

    return build


def test_live_then_replay_round_trip_without_a_key(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(cli, "build_live_client", _fake_live_factory(blind_retry_script))
    cache_dir = tmp_path / "replay"
    out_live = tmp_path / "live"

    code = cli.main(
        ["agent", "run", "--live", "--family", "F02", "--seed", "0",
         "--cache-dir", str(cache_dir), "--output", str(out_live), "--budget-usd", "1", "--json"]
    )
    assert code == 0
    live = json.loads(capsys.readouterr().out)
    assert live["mode"] == MODE_LIVE
    assert live["model"] == "claude-opus-5"
    assert live["actual_refunded_cents"] == 9400
    assert live["verdict"] == "CONTRADICTED"
    assert live["first_bad_event_seq"] == 6
    assert live["ledger_chain_valid"] is True
    assert live["usage"]["llm_calls"] == 3
    assert live["usage"]["cost_usd"] > 0
    assert live["cache_misses"] == 3 and live["cache_hits"] == 0
    assert live["budget_spent_usd"] == pytest.approx(live["usage"]["cost_usd"], abs=1e-6)
    assert (cache_dir / "F02-s00.json").exists()
    assert (cache_dir / "cost_ledger.jsonl").exists()
    case = json.loads((out_live / "case.json").read_text(encoding="utf-8"))
    assert case["trace"]["model"] == "claude-opus-5"
    assert case["trace"]["messages"][2]["provider"]["prompt_sha256"]
    labels = json.loads((out_live / "labels.provisional.json").read_text(encoding="utf-8"))
    assert labels["verified_by_human"] is False

    # Replay: the factory would blow up if it were called, and no key exists.
    monkeypatch.setattr(cli, "build_live_client", lambda **_: pytest.fail("replay must not build a live client"))
    out_replay = tmp_path / "replay-out"
    code = cli.main(
        ["agent", "run", "--replay", "--family", "F02", "--seed", "0",
         "--cache-dir", str(cache_dir), "--output", str(out_replay), "--json"]
    )
    assert code == 0
    replay = json.loads(capsys.readouterr().out)
    assert replay["mode"] == MODE_REPLAY
    assert replay["cache_hits"] == 3 and replay["cache_misses"] == 0
    replayed_case = json.loads((out_replay / "case.json").read_text(encoding="utf-8"))
    assert replayed_case == case, "replay reproduces the frozen case byte-for-byte"


def test_replay_without_a_cache_fails_loudly(tmp_path, capsys):
    code = cli.main(
        ["agent", "run", "--replay", "--family", "F01", "--seed", "3",
         "--cache-dir", str(tmp_path), "--output", str(tmp_path / "out")]
    )
    assert code == 4
    assert "replay cache miss" in capsys.readouterr().err


def test_live_without_a_key_fails_before_running(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    code = cli.main(
        ["agent", "run", "--live", "--family", "F01", "--seed", "0",
         "--cache-dir", str(tmp_path), "--output", str(tmp_path / "out")]
    )
    assert code == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_budget_guard_stops_a_live_run(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "build_live_client", _fake_live_factory(blind_retry_script))
    code = cli.main(
        ["agent", "run", "--live", "--family", "F02", "--seed", "0",
         "--cache-dir", str(tmp_path), "--output", str(tmp_path / "out"), "--budget-usd", "0.00001"]
    )
    assert code == 3
    assert "budget guard" in capsys.readouterr().err
    assert not (tmp_path / "cost_ledger.jsonl").exists()


def test_human_readable_live_output_mentions_budget_and_cache(tmp_path, monkeypatch, capsys):
    def happy(**_kwargs):
        return [text_turn("I did not issue a refund; please confirm the order first.")]

    monkeypatch.setattr(cli, "build_live_client", _fake_live_factory(happy))
    code = cli.main(
        ["agent", "run", "--live", "--family", "F01", "--seed", "2",
         "--cache-dir", str(tmp_path), "--output", str(tmp_path / "out"), "--budget-usd", "1", "--fresh"]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "Budget        :" in out
    assert "Replay cache  :" in out
    assert "verified_by_human=False" in out


def test_scripted_client_still_round_trips_new_response_fields():
    from prooftrail.agent import ModelResponse

    client = ScriptedModelClient([ModelResponse(text="x")])
    assert client.responses[0].raw_content == ()
    assert client.responses[0].metadata == {}
    assert ModelResponse.from_dict(client.responses[0].to_dict()) == client.responses[0]
