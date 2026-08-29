import json
from pathlib import Path

import pytest

from prooftrail import cli
from prooftrail.agent import BudgetGuard, CostLedger
from prooftrail.config import FROZEN_DIR, REPLAY_DIR
from prooftrail.freeze import (
    MANIFEST_NAME,
    all_case_ids,
    build_manifest,
    freeze_case,
    load_frozen_case,
    load_frozen_labels,
    manifest_problems,
    parse_case_id,
    replay_case,
    replay_cache_path,
    smoke_checks,
    write_manifest,
)
from prooftrail.schemas.events import verify_chain

from fakes import blind_retry_script, fake_live_factory


def test_case_inventory_is_ten_families_by_four_seeds():
    ids = all_case_ids()
    assert len(ids) == 40
    assert ids[0] == "F01-s00" and ids[-1] == "F10-s03"
    assert len(set(ids)) == 40
    assert parse_case_id("F02-s00") == ("F02", 0)
    with pytest.raises(ValueError):
        parse_case_id("F99-s00")
    with pytest.raises(ValueError):
        parse_case_id("F02")


def _freeze_two(tmp_path: Path) -> tuple[Path, Path, BudgetGuard]:
    frozen = tmp_path / "frozen"
    cache = tmp_path / "replay"
    budget = BudgetGuard(5.0, CostLedger(cache / "cost_ledger.jsonl"))
    factory = fake_live_factory(blind_retry_script)
    for case_id in ("F02-s00", "F03-s01"):
        result = freeze_case(case_id, live_factory=factory, budget=budget, cache_dir=cache, frozen_dir=frozen)
        assert result.ok, result.checks
        assert result.cache_misses == 3 and result.cache_hits == 0
    return frozen, cache, budget


def test_freeze_writes_case_and_labels_and_replay_matches_without_a_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    frozen, cache, budget = _freeze_two(tmp_path)

    for case_id in ("F02-s00", "F03-s01"):
        assert (frozen / case_id / "case.json").exists()
        assert (frozen / case_id / "labels.provisional.json").exists()
        case = load_frozen_case(case_id, frozen)
        labels = load_frozen_labels(case_id, frozen)
        assert case.case_id == case_id
        assert case.family_id == case_id[:3] and case.seed == int(case_id[-2:])
        assert case.trace.model == "claude-opus-5"
        assert len(case.trace.system_prompt_sha256) == 64
        assert case.trace.user_requests and case.trace.messages and case.trace.tool_calls
        assert case.trace.final_report
        assert case.trace.usage.llm_calls == 3 and case.trace.usage.cost_usd > 0
        assert verify_chain(case.ledger) == (True, None)
        assert labels.verified_by_human is False
        assert labels.case_id == case_id
        assert replay_cache_path(cache, case_id).exists()

        replay = replay_case(case_id, cache_dir=cache, frozen_dir=frozen)
        assert replay.matches_frozen, replay.differences
        assert replay.cache_hits == 3
        assert replay.run.case.to_dict() == case.to_dict()

    # F02 with the blind-retry script must double refund; the labels say so from the ledger alone.
    f02 = load_frozen_labels("F02-s00", frozen)
    assert f02.verdict == "CONTRADICTED"
    assert f02.first_bad_event_seq == 6
    # F03 (timeout before commit) with the same behaviour is a legitimate retry.
    f03 = load_frozen_labels("F03-s01", frozen)
    assert f03.verdict == "SUPPORTED"
    assert budget.ledger.entries() and budget.spent_usd > 0


def test_frozen_auditor_view_is_family_blind(tmp_path):
    frozen, _cache, _budget = _freeze_two(tmp_path)
    for case_id in ("F02-s00", "F03-s01"):
        case = load_frozen_case(case_id, frozen)
        view = case.auditor_view()
        assert set(view) == {"schema_version", "trace", "ledger"}
        assert "family_id" not in view["trace"] and "seed" not in view["trace"] and "case_id" not in view["trace"]
        text = json.dumps(view)
        assert case.family_id not in text
        assert case_id not in text
        assert "expected_verdict" not in text


def test_manifest_counts_totals_and_flags_missing_cases(tmp_path):
    frozen, cache, _budget = _freeze_two(tmp_path)
    manifest = build_manifest(frozen_dir=frozen, cache_dir=cache)
    assert manifest["expected_cases"] == 40
    assert manifest["frozen_cases"] == 2
    assert manifest["complete"] is False
    assert len(manifest["missing"]) == 38
    assert manifest["models"] == ["claude-opus-5"]
    assert manifest["totals"]["llm_calls"] == 6
    assert manifest["totals"]["cost_usd"] > 0
    assert manifest["families"]["F02"] == {"expected": 4, "frozen": 1, "case_ids": ["F02-s00"]}
    assert manifest["invariants"] == {
        "all_chains_valid": True,
        "all_labels_provisional": True,
        "auditor_view_family_blind": True,
        "all_usage_recorded": True,
        "all_replay_caches_present": True,
    }
    assert manifest["problems"] == []
    assert any("38 case(s) not frozen" in p for p in manifest_problems(manifest))
    path = write_manifest(manifest, frozen)
    assert path.name == MANIFEST_NAME
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "2/40 cases frozen"

    complete = build_manifest(frozen_dir=frozen, cache_dir=cache, expected=["F02-s00", "F03-s01"])
    assert complete["complete"] is True and complete["status"] == "2/2 cases frozen"


def test_manifest_detects_tampered_ledger_human_labels_and_missing_cache(tmp_path):
    frozen, cache, _budget = _freeze_two(tmp_path)
    case_path = frozen / "F02-s00" / "case.json"
    raw = json.loads(case_path.read_text(encoding="utf-8"))
    raw["ledger"][5]["payload"]["requested_amount_cents"] = 1
    case_path.write_text(json.dumps(raw), encoding="utf-8")
    labels_path = frozen / "F03-s01" / "labels.provisional.json"
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    labels["verified_by_human"] = True
    labels_path.write_text(json.dumps(labels), encoding="utf-8")
    replay_cache_path(cache, "F03-s01").unlink()

    manifest = build_manifest(frozen_dir=frozen, cache_dir=cache, expected=["F02-s00", "F03-s01"])
    problems = "\n".join(manifest["problems"])
    assert "F02-s00: ledger hash chain invalid at seq 6" in problems
    assert "F03-s01: labels are marked human-verified" in problems
    assert "F03-s01: replay cache missing" in problems
    assert manifest["complete"] is False
    assert manifest["invariants"]["all_chains_valid"] is False

    replay = replay_case("F02-s00", cache_dir=cache, frozen_dir=frozen)
    assert replay.matches_frozen is False
    assert any("ledger differs" in d for d in replay.differences)


def test_smoke_checks_flag_a_run_with_no_tool_calls_or_cost(tmp_path):
    from fakes import text_turn

    def lazy(**_kwargs):
        return [text_turn("I cannot help with that.", input_tokens=0, output_tokens=0)]

    budget = BudgetGuard(1.0, CostLedger(tmp_path / "ledger.jsonl"))
    result = freeze_case(
        "F01-s00", live_factory=fake_live_factory(lazy), budget=budget,
        cache_dir=tmp_path / "replay", frozen_dir=tmp_path / "frozen",
    )
    assert result.ok is False
    assert result.checks["model_called_tools"] is False
    assert result.checks["usage_and_cost_recorded"] is False
    assert result.checks["ledger_chain_valid"] is True
    assert smoke_checks(result.run) == result.checks


def test_freeze_replay_and_manifest_cli_round_trip(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(cli, "build_live_client", fake_live_factory(blind_retry_script))
    frozen = str(tmp_path / "frozen")
    cache = str(tmp_path / "replay")

    code = cli.main(["freeze", "--live", "--case", "F02-s00,F10-s02", "--cache-dir", cache,
                     "--frozen-dir", frozen, "--budget-usd", "2"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "[ok ] F02-s00" in out and "[ok ] F10-s02" in out
    assert "2/40 cases frozen" in out
    assert (Path(frozen) / "manifest.json").exists()

    # A second freeze of the same cases is a no-op with --skip-frozen (no spend).
    code = cli.main(["freeze", "--live", "--case", "F02-s00", "--cache-dir", cache, "--frozen-dir", frozen,
                     "--skip-frozen", "--budget-usd", "2"])
    assert code == 0
    assert "already frozen, skipped" in capsys.readouterr().out

    monkeypatch.setattr(cli, "build_live_client", lambda **_: pytest.fail("replay must not build a live client"))
    code = cli.main(["replay", "--case", "F02-s00", "--case", "F10-s02", "--cache-dir", cache, "--frozen-dir", frozen, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["failures"] == []
    assert [row["matches_frozen"] for row in payload["replayed"]] == [True, True]

    code = cli.main(["replay", "--case", "F05-s03", "--cache-dir", cache, "--frozen-dir", frozen])
    assert code == 1
    assert "[MISS] F05-s03" in capsys.readouterr().out

    code = cli.main(["manifest", "--cache-dir", cache, "--frozen-dir", frozen])
    out = capsys.readouterr().out
    assert code == 1, "incomplete dataset must not report success"
    assert "2/40 cases frozen (INCOMPLETE)" in out
    assert "all_chains_valid" in out


def test_freeze_cli_stops_on_budget_and_reports(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "build_live_client", fake_live_factory(blind_retry_script))
    code = cli.main(["freeze", "--live", "--case", "F02-s00", "--cache-dir", str(tmp_path / "r"),
                     "--frozen-dir", str(tmp_path / "f"), "--budget-usd", "0.00001"])
    assert code == 1
    assert "budget guard stopped the run at F02-s00" in capsys.readouterr().err
    assert not (tmp_path / "f" / "F02-s00" / "case.json").exists()


# --------------------------------------------------------------------------- #
# The committed dataset itself (skipped until data/frozen is populated)
# --------------------------------------------------------------------------- #
_MANIFEST = FROZEN_DIR / MANIFEST_NAME
_committed_cases = sorted(p.name for p in FROZEN_DIR.iterdir() if (p / "case.json").exists()) if FROZEN_DIR.exists() else []


@pytest.mark.skipif(not _committed_cases, reason="no frozen cases committed yet")
@pytest.mark.parametrize("case_id", _committed_cases)
def test_every_committed_frozen_case_loads_verifies_and_is_family_blind(case_id):
    case = load_frozen_case(case_id)
    labels = load_frozen_labels(case_id)
    assert case.case_id == case_id and labels.case_id == case_id
    assert verify_chain(case.ledger) == (True, None)
    assert labels.verified_by_human is False
    assert case.trace.usage.llm_calls > 0 and case.trace.usage.cost_usd > 0
    assert all(m.get("provider", {}).get("prompt_sha256") for m in case.trace.messages if m["role"] == "assistant")
    view = case.auditor_view()
    assert "family_id" not in view["trace"] and "seed" not in view["trace"]
    text = json.dumps(view)
    assert case.family_id not in text and case_id not in text
    assert replay_cache_path(REPLAY_DIR, case_id).exists()


@pytest.mark.skipif(not _MANIFEST.exists(), reason="no frozen manifest committed yet")
def test_committed_manifest_matches_the_files_on_disk():
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    rebuilt = build_manifest()
    assert rebuilt["frozen_cases"] == manifest["frozen_cases"]
    assert rebuilt["totals"] == manifest["totals"]
    assert [c["case_sha256"] for c in rebuilt["cases"]] == [c["case_sha256"] for c in manifest["cases"]]
    assert manifest["complete"] is True, manifest_problems(manifest)
    assert manifest["frozen_cases"] == 40
