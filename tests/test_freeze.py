import hashlib
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
    sha256_file,
    smoke_checks,
    write_manifest,
)
from prooftrail.schemas.events import verify_chain

from fakes import blind_retry_script, fake_live_factory


def test_sha256_file_is_line_ending_independent(tmp_path: Path):
    """Git checks the dataset out as LF; a Windows working tree may hold CRLF.
    The manifest hashes must not depend on which one the reader has."""

    payload = '{\n  "a": 1,\n  "b": "x"\n}\n'
    lf = tmp_path / "lf.json"
    crlf = tmp_path / "crlf.json"
    lf.write_bytes(payload.encode("utf-8"))
    crlf.write_bytes(payload.replace("\n", "\r\n").encode("utf-8"))
    assert lf.read_bytes() != crlf.read_bytes()
    assert sha256_file(lf) == sha256_file(crlf)
    assert sha256_file(lf) == hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_write_case_artifacts_emits_lf_only(tmp_path: Path):
    """Artifacts are hashed and committed, so writers must never emit CRLF."""

    frozen, _cache, _budget = _freeze_two(tmp_path)
    written = list((frozen / "F02-s00").iterdir())
    assert written, "freeze wrote nothing"
    for path in written:
        assert b"\r\n" not in path.read_bytes(), path.name


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
        "single_model": True,
        "single_provider": True,
    }
    assert manifest["providers"] == ["anthropic"]
    assert manifest["totals"]["list_price_equivalent_usd"] == manifest["totals"]["cost_usd"]
    assert all(c["provider"] == "anthropic" for c in manifest["cases"])
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
    assert result.checks["usage_recorded"] is False
    assert result.checks["cost_recorded"] is True, "a $0 figure is still a recorded figure"
    assert result.checks["ledger_chain_valid"] is True
    assert smoke_checks(result.run) == result.checks


def test_gemini_free_tier_freeze_replay_and_manifest_bill_zero(tmp_path, monkeypatch, capsys):
    from test_gemini_provider import _blind_retry_script as gemini_blind_retry
    from test_gemini_provider import _fake_gemini_factory

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(cli, "build_gemini_client", _fake_gemini_factory(gemini_blind_retry))
    monkeypatch.setattr(cli, "build_live_client", lambda **_: pytest.fail("gemini freeze must not build the paid client"))
    frozen = str(tmp_path / "frozen")
    cache = str(tmp_path / "replay")

    code = cli.main(["freeze", "--live", "--provider", "gemini", "--case", "F02-s00,F03-s01",
                     "--cache-dir", cache, "--frozen-dir", frozen])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "[ok ] F02-s00" in out and "billed $0.00 (free tier)" in out
    assert "Budget" not in out
    assert not (Path(cache) / "cost_ledger.jsonl").exists()

    manifest = json.loads((Path(frozen) / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["frozen_cases"] == 2
    assert manifest["providers"] == ["google-gemini"]
    assert len(manifest["models"]) == 1
    assert manifest["invariants"]["single_model"] is True
    assert manifest["invariants"]["all_usage_recorded"] is True
    assert manifest["totals"]["cost_usd"] == 0.0
    assert manifest["totals"]["list_price_equivalent_usd"] > 0
    assert manifest["problems"] == []
    labels = json.loads((Path(frozen) / "F02-s00" / "labels.provisional.json").read_text(encoding="utf-8"))
    assert labels["verified_by_human"] is False

    # Resume semantics: a second run skips frozen cases and spends nothing.
    monkeypatch.setattr(cli, "build_gemini_client", lambda **_: pytest.fail("skipped cases must not build a client"))
    code = cli.main(["freeze", "--live", "--provider", "gemini", "--case", "F02-s00", "--skip-frozen",
                     "--cache-dir", cache, "--frozen-dir", frozen])
    assert code == 0 and "already frozen, skipped" in capsys.readouterr().out

    code = cli.main(["replay", "--provider", "gemini", "--case", "F02-s00,F03-s01", "--cache-dir", cache, "--frozen-dir", frozen, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and payload["failures"] == []
    assert all(row["matches_frozen"] for row in payload["replayed"])

    code = cli.main(["freeze", "--live", "--provider", "gemini", "--case", "F04-s00", "--budget-usd", "1",
                     "--cache-dir", cache, "--frozen-dir", frozen])
    assert code == 7


def test_fully_cached_case_is_frozen_without_building_a_live_client(tmp_path):
    frozen, cache, budget = _freeze_two(tmp_path)
    before = (frozen / "F02-s00" / "case.json").read_text(encoding="utf-8")

    def no_client(**_kwargs):
        pytest.fail("a fully cached case must never construct the live client")

    result = freeze_case("F02-s00", live_factory=no_client, budget=None, cache_dir=cache, frozen_dir=frozen)
    assert result.ok and result.cache_hits == 3 and result.cache_misses == 0
    assert (frozen / "F02-s00" / "case.json").read_text(encoding="utf-8") == before

    from prooftrail.agent import ReplayCacheModelMismatch

    with pytest.raises(ReplayCacheModelMismatch):
        freeze_case("F02-s00", live_factory=no_client, budget=None, model="claude-sonnet-5", cache_dir=cache, frozen_dir=frozen)


def test_manifest_flags_a_dataset_that_mixes_models(tmp_path):
    frozen, cache, _budget = _freeze_two(tmp_path)
    case_path = frozen / "F03-s01" / "case.json"
    raw = json.loads(case_path.read_text(encoding="utf-8"))
    raw["trace"]["model"] = "claude-sonnet-5"
    case_path.write_text(json.dumps(raw), encoding="utf-8")
    manifest = build_manifest(frozen_dir=frozen, cache_dir=cache, expected=["F02-s00", "F03-s01"])
    assert manifest["invariants"]["single_model"] is False
    assert any("mixes models" in p for p in manifest["problems"])
    assert manifest["complete"] is False


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
    assert case.trace.usage.llm_calls > 0 and case.trace.usage.input_tokens > 0
    assistant_turns = [m for m in case.trace.messages if m["role"] == "assistant"]
    assert all(m.get("provider", {}).get("prompt_sha256") for m in assistant_turns)
    assert all("cost_usd" in m["provider"]["usage"] for m in assistant_turns)
    view = case.auditor_view()
    assert "family_id" not in view["trace"] and "seed" not in view["trace"]
    text = json.dumps(view)
    assert case.family_id not in text and case_id not in text
    assert replay_cache_path(_committed_cache_dir(), case_id).exists()


def _committed_cache_dir() -> Path:
    """Replay caches are namespaced per provider; the manifest says which one."""

    if _MANIFEST.exists():
        providers = json.loads(_MANIFEST.read_text(encoding="utf-8")).get("providers", [])
        if providers == ["google-gemini"]:
            return REPLAY_DIR / "gemini"
    return REPLAY_DIR


@pytest.mark.skipif(not _MANIFEST.exists(), reason="no frozen manifest committed yet")
def test_committed_manifest_matches_the_files_on_disk():
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    rebuilt = build_manifest(cache_dir=_committed_cache_dir())
    assert rebuilt["frozen_cases"] == manifest["frozen_cases"]
    assert rebuilt["totals"] == manifest["totals"]
    assert rebuilt["problems"] == manifest["problems"] == []
    assert [c["case_sha256"] for c in rebuilt["cases"]] == [c["case_sha256"] for c in manifest["cases"]]
    assert manifest["invariants"]["single_model"] is True
    assert manifest["invariants"]["single_provider"] is True
    assert manifest["invariants"]["all_labels_provisional"] is True
    assert manifest["totals"]["cost_usd"] == 0.0, "the free plan allows no billed spend"


@pytest.mark.skipif(not _MANIFEST.exists(), reason="no frozen manifest committed yet")
def test_committed_dataset_is_complete():
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    if manifest["frozen_cases"] < manifest["expected_cases"]:
        pytest.skip(f"dataset still in progress: {manifest['status']} (see PROJECT_STATUS.md)")
    assert manifest["complete"] is True, manifest_problems(manifest)
    assert manifest["frozen_cases"] == 40
    assert len(_committed_cases) == 40
