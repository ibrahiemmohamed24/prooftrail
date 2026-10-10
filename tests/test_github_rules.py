import copy

import pytest

from prooftrail.github.audit import audit as run_audit
from prooftrail.github.contract import parse_request
from prooftrail.github.evidence import load_bundle
from prooftrail.github.examples import scenario_packs
from prooftrail.github.verify import verify

PACKS = {pack["id"]: pack for pack in scenario_packs()}


def test_wrong_pr_number_never_supports_requested_pr_or_dependent_claims():
    pack = copy.deepcopy(PACKS["synthetic-correct-open-pr"])
    pack["bundle"]["pull_request"]["number"] = 999
    result = verify(parse_request(pack["request"]), load_bundle(pack["bundle"]))
    assert result.verdict == "CONTRADICTED"
    for claim in result.claims:
        assert claim.reason_code == "pull_request_number_mismatch"
        assert claim.status == ("CONTRADICTED" if claim.claim_type == "pr_exists" else "UNVERIFIABLE")
        assert claim.evidence == ("pull_request:999",)
    assert result.checks == ()


@pytest.mark.parametrize("sha, expected", [("b" * 40, "CONTRADICTED"), (None, "UNVERIFIABLE")])
def test_commit_status_needs_the_expected_revision(sha, expected):
    pack = copy.deepcopy(PACKS["synthetic-correct-open-pr"])
    pack["bundle"]["check_runs"] = []
    pack["bundle"]["commit_statuses"] = [
        {"context": name, "state": "success", "sha": sha}
        for name in pack["request"]["required_checks"]]
    result = verify(parse_request(pack["request"]), load_bundle(pack["bundle"]))
    assert _claim(result, "c4").status == expected
    assert all(check.status == expected for check in result.checks)


def test_matching_commit_status_revision_can_support_checks():
    pack = copy.deepcopy(PACKS["synthetic-correct-open-pr"])
    pack["bundle"]["check_runs"] = []
    pack["bundle"]["commit_statuses"] = [
        {"context": name, "state": "success", "sha": pack["request"]["expected_head_sha"]}
        for name in pack["request"]["required_checks"]]
    result = verify(parse_request(pack["request"]), load_bundle(pack["bundle"]))
    assert result.verdict == "SUPPORTED"


def _verification(pack_id):
    pack = PACKS[pack_id]
    return verify(parse_request(pack["request"]), load_bundle(pack["bundle"]))


def _claim(verification, claim_id):
    return next(item for item in verification.claims if item.claim_id == claim_id)


def _check(verification, name):
    return next(item for item in verification.checks if item.name == name)


@pytest.mark.parametrize("pack_id", sorted(PACKS))
def test_scenario_verdicts_match_hand_written_expectations(pack_id):
    pack = PACKS[pack_id]
    result = run_audit(parse_request(pack["request"]), load_bundle(pack["bundle"]))
    assert result["verdict"] == pack["expected"]["verdict"]
    assert {claim["claim_id"]: claim["status"] for claim in result["claims"]} == pack["expected"]["claims"]
    assert result["persisted"] is False
    assert result["model_calls"] == 0
    assert result["network_used"] is False


def test_correct_pr_supports_every_claim_with_evidence_references():
    verification = _verification("synthetic-correct-open-pr")
    assert verification.verdict == "SUPPORTED"
    assert _claim(verification, "c1").evidence == ("pull_request:4",)
    assert _check(verification, "replay").latest_run_id == 102
    assert _check(verification, "replay").attempt_ids == (101, 102)


def test_other_repository_is_contradicted_and_dependent_claims_abstain():
    verification = _verification("synthetic-other-repository")
    assert _claim(verification, "c1").reason_code == "pr_belongs_to_other_repository"
    assert _claim(verification, "c2").reason_code == "pull_request_identity_not_established"
    assert _claim(verification, "c3").reason_code == "pull_request_identity_not_established"


def test_wrong_base_branch_is_contradicted_with_observed_value():
    claim = _claim(_verification("synthetic-wrong-base"), "c2")
    assert claim.reason_code == "base_branch_mismatch"
    assert claim.observed == {"base_branch": "develop"}
    assert claim.expected == {"base_branch": "main"}


def test_head_mismatch_on_a_stable_head_is_contradicted():
    assert _claim(_verification("synthetic-head-mismatch"), "c2").reason_code == "head_sha_mismatch"


def test_head_change_during_collection_abstains_instead_of_guessing():
    claim = _claim(_verification("synthetic-head-changed"), "c2")
    assert claim.status == "UNVERIFIABLE"
    assert claim.reason_code == "head_changed_during_collection"


def test_merge_claim_on_an_open_pr_is_contradicted_and_merged_flag_is_the_only_fact_supported():
    assert _claim(_verification("synthetic-merge-claim-unmerged"), "c1").reason_code == "not_merged"
    merged = _claim(_verification("synthetic-merged-pr"), "c1")
    assert merged.status == "SUPPORTED"
    assert merged.reason_code == "merged_flag_observed"
    assert "does not prove" in merged.reason


def test_successful_checks_on_an_older_sha_are_not_used_for_the_expected_revision():
    check = _check(_verification("synthetic-older-sha-success"), "replay")
    assert check.reason_code == "required_check_not_observed_on_expected_sha"
    assert check.other_sha_run_ids == (201,)
    assert check.attempt_ids == ()


def test_failed_check_is_contradicted():
    check = _check(_verification("synthetic-failed-check"), "replay")
    assert (check.status, check.reason_code, check.latest_conclusion) == ("CONTRADICTED", "check_failed", "failure")


def test_pending_check_is_not_success_and_stays_unverifiable():
    check = _check(_verification("synthetic-pending-check"), "mcp-adapter")
    assert check.status == "UNVERIFIABLE"
    assert check.reason_code == "check_pending"


def test_skipped_check_is_not_success():
    check = _check(_verification("synthetic-skipped-check"), "replay")
    assert check.status == "CONTRADICTED"
    assert check.reason_code == "check_not_successful"


def test_required_check_absent_from_incomplete_evidence_is_unverifiable():
    verification = _verification("synthetic-incomplete-checks")
    for check in verification.checks:
        assert check.status == "UNVERIFIABLE"
        assert check.reason_code == "incomplete_evidence"
    assert _claim(verification, "c1").reason_code == "incomplete_evidence"


def test_rerun_uses_the_latest_attempt_and_lists_the_superseded_one():
    check = _check(_verification("synthetic-rerun-latest-success"), "replay")
    assert check.status == "SUPPORTED"
    assert check.latest_run_id == 702
    assert check.superseded_ids == (701,)


def test_disagreeing_attempts_are_disclosed_in_the_reason_not_hidden():
    check = _check(_verification("synthetic-rerun-latest-success"), "replay")
    assert "superseded by the latest attempt with this name and producer" in check.reason
    assert "Attempts disagree on the outcome" in check.reason


def test_two_producers_for_one_name_produce_no_confident_verdict():
    check = _check(_verification("synthetic-ambiguous-producers"), "replay")
    assert check.status == "UNVERIFIABLE"
    assert check.reason_code == "ambiguous_producers"
    assert check.producers == ("check_run:github-actions", "commit_status")


def test_missing_check_with_complete_evidence_is_contradicted_but_not_called_nonexistent():
    check = _check(_verification("synthetic-older-sha-success"), "mcp-adapter")
    assert check.status == "CONTRADICTED"
    assert "does not prove it never ran elsewhere" in check.reason


@pytest.mark.parametrize(("pack_id", "claim_id", "reason"), [
    ("synthetic-rate-limited", "c1", "source_rate_limited"),
    ("synthetic-timeout-pull-request", "c1", "source_timeout"),
    ("synthetic-forbidden-checks", "c1", "source_forbidden"),
    ("synthetic-pr-not-found", "c1", "pr_not_found"),
])
def test_source_failures_map_to_specific_reasons(pack_id, claim_id, reason):
    assert _claim(_verification(pack_id), claim_id).reason_code == reason


def test_forbidden_checks_never_produce_a_contradiction():
    verification = _verification("synthetic-forbidden-checks")
    assert verification.verdict == "UNVERIFIABLE"
    assert _claim(verification, "c1").status == "UNVERIFIABLE"


def test_unsupported_claims_are_classified_explicitly():
    verification = _verification("synthetic-unsupported-claims")
    assert [claim.reason_code for claim in verification.claims] == [
        "unsupported_in_this_milestone", "no_test_report_evidence"]
    assert verification.verdict == "UNVERIFIABLE"


def test_warnings_name_the_source_and_its_limits():
    verification = _verification("synthetic-rate-limited")
    assert any("SYNTHETIC FIXTURE" in item for item in verification.warnings)
    assert any("rate_limited" in item for item in verification.warnings)
    assert any("head changed" in item for item in _verification("synthetic-head-changed").warnings)
