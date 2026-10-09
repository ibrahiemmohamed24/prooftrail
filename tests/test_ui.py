import json
import re
from pathlib import Path

from prooftrail.cli import main
from prooftrail.ui import build_ui
from prooftrail.ui import render
from prooftrail.ui.build import ASSET_DIR
from prooftrail.ui.model import COMPARISON_PATH, CaseView, load_site
from prooftrail.ui.model import load_case
from prooftrail.config import FROZEN_DIR

HEX_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b")
ROOT_BLOCK = re.compile(r":root\s*\{.*?\}", re.S)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_build_writes_every_page_and_asset(tmp_path):
    written = build_ui(tmp_path)
    case_ids = [case.case_id for case in load_site().cases]
    assert len(case_ids) == 40
    assert (tmp_path / "index.html").is_file()
    assert (tmp_path / "cases.html").is_file()
    for case_id in case_ids:
        assert (tmp_path / "cases" / f"{case_id}.html").is_file()
        assert (tmp_path / "certificates" / f"{case_id}.html").is_file()
    for name in ("prooftrail.css", "fonts.css", "app.js", "fonts/SpaceGrotesk-latin.woff2"):
        assert (tmp_path / "assets" / name).is_file()
    asset_count = sum(1 for path in ASSET_DIR.rglob("*") if path.is_file() and "__pycache__" not in path.parts)
    assert len(written) == 6 + 4 * len(case_ids) + asset_count
    assert (tmp_path / "benchmark.json").read_bytes() == COMPARISON_PATH.read_bytes()
    for case_id in case_ids:
        for suffix in ("json", "md"):
            exported = tmp_path / "certificates" / f"{case_id}.{suffix}"
            source = FROZEN_DIR / case_id / f"certificate.{suffix}"
            assert exported.read_bytes() == source.read_bytes()


def test_build_is_byte_for_byte_repeatable(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    build_ui(first)
    build_ui(second)
    files = sorted(path.relative_to(first) for path in first.rglob("*") if path.is_file())
    assert files
    for relative in files:
        assert (first / relative).read_bytes() == (second / relative).read_bytes(), relative


def test_chain_status_checks_raw_ledger_not_saved_summary(tmp_path):
    import shutil

    case_id = "F02-s00"
    directory = tmp_path / case_id
    shutil.copytree(FROZEN_DIR / case_id, directory)
    payload = json.loads(_read(directory / "case.json"))
    payload["ledger"][0]["hash"] = "0" * 64
    (directory / "case.json").write_text(json.dumps(payload), encoding="utf-8")
    assert json.loads(_read(directory / "summary.json"))["ledger_chain_valid"] is True
    assert load_case(case_id, frozen_dir=tmp_path).chain_valid is False


def test_overview_states_the_verified_numbers(tmp_path):
    build_ui(tmp_path)
    page = _read(tmp_path / "index.html")
    comparison = json.loads(_read(COMPARISON_PATH))
    proof_trail = comparison["prooftrail"]["metric_values"]["family_mean_accuracy"]
    b1_mean = comparison["b1"]["metric_distribution"]["family_mean_accuracy"]["mean"]
    assert f"{proof_trail * 100:.1f}%" in page
    assert f"B1 {b1_mean * 100:.1f}%" in page
    assert "Same evidence. Independent truth. Frozen traces." in page
    assert "Human-verified labels 40/40" in page


def test_case_list_has_one_row_per_case(tmp_path):
    build_ui(tmp_path)
    assert _read(tmp_path / "cases.html").count("data-verdict=") == 40


def test_case_page_separates_agent_claims_from_ledger_proof(tmp_path):
    case = next(case for case in load_site().cases if case.first_bad_event_seq is not None)
    build_ui(tmp_path)
    page = _read(tmp_path / "cases" / f"{case.case_id}.html")
    for label in ("AGENT SAID", "LEDGER PROVED", "EVIDENCE INSPECTOR", "First harmful event"):
        assert label in page
    assert f'id="event-{case.first_bad_event_seq}"' in page


def test_untrusted_text_is_escaped(tmp_path):
    base = load_site().cases[0]
    hostile = "<script>alert(1)</script>"
    case = CaseView(
        case_id=base.case_id,
        family_id=base.family_id,
        family_name=base.family_name,
        family_summary=base.family_summary,
        verdict="CONTRADICTED",
        first_bad_event_seq=None,
        explanation=hostile,
        final_report=f"I refunded it. {hostile}",
        claims=(
            {
                "claim_id": "claim_001",
                "claim_text": hostile,
                "claim_type": "other",
                "status": "CONTRADICTED",
                "evidence_seqs": [],
                "reason": hostile,
                "tool_calls": [],
            },
        ),
        events=(),
        chain_valid=True,
        coverage=(0, 1),
        auditor_llm_calls=0,
        agent_tool_calls=0,
        review_action=None,
    )
    for page in (render.render_case(case), render.render_certificate(case)):
        assert "<script>" not in page
        assert "&lt;script&gt;" in page


def test_colors_live_only_in_css_tokens():
    css = _read(ASSET_DIR / "prooftrail.css")
    outside_tokens = ROOT_BLOCK.sub("", css, count=1)
    assert not HEX_COLOR.search(outside_tokens)
    assert not re.search(r"rgba?\(", outside_tokens)
    assert not HEX_COLOR.search(_read(Path(render.__file__)))


def test_certificate_keeps_navigation_out_of_print(tmp_path):
    build_ui(tmp_path)
    case_id = load_site().cases[0].case_id
    page = _read(tmp_path / "certificates" / f"{case_id}.html")
    assert 'class="sidebar no-print"' in page
    assert 'class="toolbar no-print"' in page
    assert "@media print" in _read(tmp_path / "assets" / "prooftrail.css")


def test_cli_ui_build_writes_the_index(tmp_path, capsys):
    assert main(["ui", "build", "--output", str(tmp_path)]) == 0
    assert (tmp_path / "index.html").is_file()
    assert "UI written" in capsys.readouterr().out
