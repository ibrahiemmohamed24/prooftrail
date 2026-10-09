import json

from prooftrail.github.audit import audit as run_audit
from prooftrail.github.certificate import LIMITATIONS, render_markdown
from prooftrail.github.contract import parse_request
from prooftrail.github.evidence import bundle_sha256, load_bundle
from prooftrail.github.examples import scenario_packs

PACKS = {pack["id"]: pack for pack in scenario_packs()}


def _run(pack_id):
    pack = PACKS[pack_id]
    return run_audit(parse_request(pack["request"]), load_bundle(pack["bundle"])), pack


def test_json_certificate_states_source_hash_and_limits():
    result, pack = _run("synthetic-correct-open-pr")
    certificate = result["certificate"]
    assert certificate["certificate_type"] == "github_execution_verification"
    assert certificate["domain"] == "github"
    assert certificate["source"]["bundle_sha256"] == bundle_sha256(pack["bundle"])
    assert certificate["source"]["synthetic"] is True
    assert "does not authenticate" in certificate["source"]["integrity_note"]
    assert certificate["persisted"] is False
    assert certificate["model_calls"] == 0
    assert certificate["network_used"] is False
    assert certificate["limitations"] == list(LIMITATIONS)


def test_limitations_say_what_a_merge_and_a_green_check_do_not_prove():
    text = " ".join(LIMITATIONS)
    assert "does not prove that the merge commit" in text
    assert "does not prove deployment" in text
    assert "does not prove that all tests passed" in text
    assert "No numerical confidence" in text


def test_certificates_are_deterministic_for_the_same_bundle():
    first, _ = _run("synthetic-rerun-latest-success")
    second, _ = _run("synthetic-rerun-latest-success")
    assert json.dumps(first["certificate"], sort_keys=True) == json.dumps(second["certificate"], sort_keys=True)
    assert first["certificate_markdown"] == second["certificate_markdown"]


def test_markdown_lists_claims_checks_and_the_synthetic_warning():
    result, _ = _run("synthetic-failed-check")
    markdown = result["certificate_markdown"]
    assert "# GitHub execution verification: example-owner/example-repo #4" in markdown
    assert "- **Verdict:** `CONTRADICTED`" in markdown
    assert "SYNTHETIC FIXTURE" in markdown
    assert "| c1 | `required_checks_passed` | `CONTRADICTED` | `required_check_contradicted` |" in markdown
    assert "| replay | `CONTRADICTED` | `check_failed` |" in markdown


def test_pipes_and_newlines_in_text_cannot_break_the_markdown_table():
    result, _ = _run("synthetic-failed-check")
    certificate = json.loads(json.dumps(result["certificate"]))
    certificate["claims"][0]["reason"] = "first | second\nthird"
    markdown = render_markdown(certificate)
    assert "first \\| second third" in markdown
