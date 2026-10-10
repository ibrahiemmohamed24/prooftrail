"""Deterministic GitHub execution rules.

Verdicts use the existing categories: SUPPORTED, CONTRADICTED, UNVERIFIABLE.
There is no model, no free-text extraction and no numerical confidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..schemas.verdict import Status, aggregate_verdict
from .contract import GithubRequest
from .evidence import CheckRunRecord, CommitStatusRecord, EvidenceSnapshot, Observation

SUPPORTED = Status.SUPPORTED
CONTRADICTED = Status.CONTRADICTED
UNVERIFIABLE = Status.UNVERIFIABLE

SOURCE_REASONS = {
    "not_found": "source_not_found",
    "unauthorized": "source_unauthorized",
    "forbidden": "source_forbidden",
    "rate_limited": "source_rate_limited",
    "timeout": "source_timeout",
    "unavailable": "source_unavailable",
    "redirect_refused": "source_redirect_refused",
    "too_large": "source_too_large",
    "invalid_response": "source_invalid_response",
    "pagination_limit": "incomplete_evidence",
    "not_collected": "source_not_collected",
}
FAILED_CONCLUSIONS = ("failure", "timed_out", "cancelled", "action_required")
NOT_SUCCESSFUL_CONCLUSIONS = ("neutral", "skipped")
UNSUPPORTED_REASONS = {
    "production_deployment": "unsupported_in_this_milestone",
    "all_tests_passed": "no_test_report_evidence",
}


@dataclass(frozen=True)
class ClaimResult:
    claim_id: str
    claim_type: str
    status: str
    reason_code: str
    reason: str
    expected: dict[str, Any]
    observed: dict[str, Any]
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class CheckAssessment:
    name: str
    status: str
    reason_code: str
    reason: str
    producers: tuple[str, ...]
    attempt_ids: tuple[int, ...]
    latest_run_id: int | None
    latest_conclusion: str | None
    superseded_ids: tuple[int, ...]
    other_sha_run_ids: tuple[int, ...]
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class Verification:
    verdict: str
    claims: tuple[ClaimResult, ...]
    checks: tuple[CheckAssessment, ...]
    warnings: tuple[str, ...]


def _observation_reason(observation: Observation | None, fallback: str) -> tuple[str, str]:
    if observation is None:
        return fallback, f"No observation was recorded for the source ({fallback})."
    code = SOURCE_REASONS.get(observation.status, "source_invalid_response")
    detail = observation.message or observation.status
    return code, f"{observation.endpoint}: {detail}"


def _repository_problem(snapshot: EvidenceSnapshot) -> tuple[str, str] | None:
    """A 404 on the repository can mean 'absent' or 'not visible to this token', so it is not contradicted."""
    repository = snapshot.observation("repository")
    if repository is None:
        return "repository_not_collected", "The repository observation is missing."
    if repository.status == "ok":
        return None
    if repository.status == "not_found":
        return "repository_not_found_or_inaccessible", (
            f"{repository.endpoint}: the repository is not readable with the given access.")
    return _observation_reason(repository, "repository_not_collected")


def _repository_identity_problem(snapshot: EvidenceSnapshot, expected_repo: str) -> tuple[str, str]:
    problem = _repository_problem(snapshot)
    if problem is not None:
        return problem[0], f"Repository identity unconfirmed: {problem[1]}"
    if snapshot.repository is None:
        return "repository_identity_unconfirmed", "The repository observation is ok but carries no repository record."
    return "repository_identity_mismatch", (
        f"The repository endpoint reports {snapshot.repository.full_name}, not {expected_repo}.")


def _pull_request_problem(snapshot: EvidenceSnapshot) -> tuple[str, str]:
    problem = _repository_problem(snapshot)
    if problem is not None:
        return problem
    return _observation_reason(snapshot.observation("pull_request"), "pull_request_not_collected")


def _state(run: CheckRunRecord) -> tuple[str, str, str]:
    """Return (verdict, reason code, text) for one check run's latest attempt."""
    if run.status != "completed":
        return UNVERIFIABLE, "check_pending", f"Check run {run.run_id} is {run.status}; it is not successful yet."
    if run.conclusion == "success":
        return SUPPORTED, "check_completed_successfully", f"Check run {run.run_id} concluded success."
    if run.conclusion in FAILED_CONCLUSIONS:
        return CONTRADICTED, "check_failed", f"Check run {run.run_id} concluded {run.conclusion}."
    if run.conclusion in NOT_SUCCESSFUL_CONCLUSIONS:
        return CONTRADICTED, "check_not_successful", (
            f"Check run {run.run_id} concluded {run.conclusion}; neutral or skipped is not success.")
    return UNVERIFIABLE, "check_conclusion_inconclusive", f"Check run {run.run_id} has no usable conclusion."


def _status_state(status: CommitStatusRecord) -> tuple[str, str, str]:
    if status.state == "success":
        return SUPPORTED, "check_completed_successfully", f"Commit status {status.context} is success."
    if status.state == "pending":
        return UNVERIFIABLE, "check_pending", f"Commit status {status.context} is pending."
    if status.state in ("failure", "error"):
        return CONTRADICTED, "check_failed", f"Commit status {status.context} is {status.state}."
    return UNVERIFIABLE, "check_conclusion_inconclusive", f"Commit status {status.context} has an unknown state."


def _assess_check(name: str, snapshot: EvidenceSnapshot, expected_sha: str) -> CheckAssessment:
    runs = [run for run in snapshot.check_runs if run.name == name and run.head_sha == expected_sha]
    other = tuple(sorted(run.run_id for run in snapshot.check_runs if run.name == name and run.head_sha != expected_sha))
    statuses = [item for item in snapshot.commit_statuses
                if item.context == name and item.sha == expected_sha]
    if any(item.context == name and item.sha is None for item in snapshot.commit_statuses):
        return CheckAssessment(
            name=name, status=UNVERIFIABLE, reason_code="status_revision_unconfirmed",
            reason="A matching commit status has no SHA; its revision cannot be established.",
            producers=(), attempt_ids=(), latest_run_id=None, latest_conclusion=None,
            superseded_ids=(), other_sha_run_ids=other, evidence=())
    producers = sorted({f"check_run:{run.producer}" for run in runs} | {"commit_status" for _ in statuses})
    if not producers:
        note = " Successful runs on other SHAs were ignored." if other else ""
        return CheckAssessment(
            name=name, status=CONTRADICTED, reason_code="required_check_not_observed_on_expected_sha",
            reason=("No check run or commit status with this name exists on the expected SHA in complete "
                    "evidence. This does not prove it never ran elsewhere." + note),
            producers=(), attempt_ids=(), latest_run_id=None, latest_conclusion=None,
            superseded_ids=(), other_sha_run_ids=other, evidence=())
    if len(producers) > 1:
        return CheckAssessment(
            name=name, status=UNVERIFIABLE, reason_code="ambiguous_producers",
            reason="Several producers report this name on the expected SHA; no single result can be chosen.",
            producers=tuple(producers), attempt_ids=tuple(sorted(run.run_id for run in runs)),
            latest_run_id=None, latest_conclusion=None, superseded_ids=(), other_sha_run_ids=other, evidence=())
    if runs:
        attempts = sorted(runs, key=lambda run: run.run_id)
        latest = attempts[-1]
        status, code, text = _state(latest)
        superseded = tuple(run.run_id for run in attempts[:-1])
        if superseded:
            # Separate events (push and pull_request) and reruns both create attempts; the latest id is used.
            text += (f" Earlier attempts {', '.join(str(item) for item in superseded)} are superseded by the "
                     "latest attempt with this name and producer.")
            outcomes = {run.conclusion or run.status for run in attempts}
            if len(outcomes) > 1:
                text += " Attempts disagree on the outcome; the latest attempt by id is the one reported."
        return CheckAssessment(
            name=name, status=status, reason_code=code, reason=text, producers=tuple(producers),
            attempt_ids=tuple(run.run_id for run in attempts), latest_run_id=latest.run_id,
            latest_conclusion=latest.conclusion, superseded_ids=superseded, other_sha_run_ids=other,
            evidence=(f"check_run:{latest.run_id}",))
    if len(statuses) > 1:
        return CheckAssessment(
            name=name, status=UNVERIFIABLE, reason_code="duplicate_status_contexts",
            reason="The same commit status context appears more than once; the result is ambiguous.",
            producers=tuple(producers), attempt_ids=(), latest_run_id=None, latest_conclusion=None,
            superseded_ids=(), other_sha_run_ids=other, evidence=())
    status_item = statuses[0]
    status, code, text = _status_state(status_item)
    return CheckAssessment(
        name=name, status=status, reason_code=code, reason=text, producers=tuple(producers),
        attempt_ids=(), latest_run_id=None, latest_conclusion=status_item.state, superseded_ids=(),
        other_sha_run_ids=other, evidence=(f"commit_status:{name}",))


def _check_source_problem(snapshot: EvidenceSnapshot) -> tuple[str, str] | None:
    for name in ("check_runs", "commit_statuses"):
        observation = snapshot.observation(name)
        if observation is None:
            return "check_sources_not_collected", f"The {name} observation is missing."
        if observation.status != "ok":
            code, text = _observation_reason(observation, "check_source_unavailable")
            return code, text
        if not observation.complete:
            return "incomplete_evidence", f"{observation.endpoint}: pagination is incomplete."
    return None


def _required_checks(request: GithubRequest, snapshot: EvidenceSnapshot) -> tuple[ClaimResult, tuple[CheckAssessment, ...]]:
    expected = {"head_sha": request.expected_head_sha, "required_checks": list(request.required_checks)}
    problem = _check_source_problem(snapshot)
    if problem is not None:
        assessments = tuple(
            CheckAssessment(name=name, status=UNVERIFIABLE, reason_code=problem[0], reason=problem[1],
                            producers=(), attempt_ids=(), latest_run_id=None, latest_conclusion=None,
                            superseded_ids=(), other_sha_run_ids=(), evidence=())
            for name in request.required_checks)
    else:
        assessments = tuple(_assess_check(name, snapshot, request.expected_head_sha)
                            for name in request.required_checks)
    status = aggregate_verdict(item.status for item in assessments)
    causes = {item.reason_code for item in assessments}
    if status == CONTRADICTED:
        code = "required_check_contradicted"
    elif status == UNVERIFIABLE and len(causes) == 1:
        code = next(iter(causes))  # one shared cause (for example source_forbidden) is reported as-is
    elif status == UNVERIFIABLE:
        code = "required_check_unverifiable"
    else:
        code = "required_checks_succeeded"
    observed = {item.name: {"status": item.status, "reason_code": item.reason_code,
                            "latest_run_id": item.latest_run_id, "latest_conclusion": item.latest_conclusion}
                for item in assessments}
    evidence = tuple(ref for item in assessments for ref in item.evidence)
    return ClaimResult(
        claim_id="", claim_type="required_checks_passed", status=status, reason_code=code,
        reason=" ".join(item.reason for item in assessments), expected=expected, observed=observed,
        evidence=evidence), assessments


def verify(request: GithubRequest, snapshot: EvidenceSnapshot) -> Verification:
    """Apply the deterministic rules to one request and one evidence snapshot."""
    expected_repo = request.repository.full_name.lower()
    pr = snapshot.pull_request
    pr_obs = snapshot.observation("pull_request")
    repo = snapshot.repository
    repo_obs = snapshot.observation("repository")
    pr_ok = pr is not None and pr_obs is not None and pr_obs.status == "ok"
    number_mismatch = pr_ok and pr.number != request.pull_request
    repo_identity = (repo_obs is not None and repo_obs.status == "ok" and repo is not None
                     and repo.full_name.lower() == expected_repo)
    identity = pr_ok and repo_identity and pr.base_repo is not None and pr.base_repo.lower() == expected_repo
    recheck_obs = snapshot.observation("pull_request_recheck")
    recheck_sha = snapshot.recheck_head_sha if recheck_obs is not None and recheck_obs.status == "ok" else None
    pr_ref = f"pull_request:{request.pull_request}"
    claims: list[ClaimResult] = []
    checks: tuple[CheckAssessment, ...] = ()

    for claim in request.claims:
        expected: dict[str, Any] = {}
        observed: dict[str, Any] = {}
        evidence: tuple[str, ...] = ()
        if claim.claim_type in UNSUPPORTED_REASONS:
            status, code, text = UNVERIFIABLE, UNSUPPORTED_REASONS[claim.claim_type], (
                "This claim type is not verifiable in this milestone; see limitations.")
        elif number_mismatch:
            expected = {"pull_request": request.pull_request}
            observed = {"pull_request": pr.number}
            status = CONTRADICTED if claim.claim_type == "pr_exists" else UNVERIFIABLE
            code, text = "pull_request_number_mismatch", (
                "The evidence describes a different pull request; dependent claims cannot be verified.")
            evidence = (f"pull_request:{pr.number}",)
        elif claim.claim_type == "pr_exists":
            expected = {"repository": request.repository.full_name, "pull_request": request.pull_request}
            if pr_ok and identity:
                status, code, text = SUPPORTED, "pr_found_in_expected_repository", "The pull request exists in the expected repository."
                evidence = (pr_ref,)
            elif pr_ok and not repo_identity:
                # The pull request was returned, but the repository itself could not confirm the identity.
                status = UNVERIFIABLE
                code, text = _repository_identity_problem(snapshot, expected_repo)
            elif pr_ok:
                status, code, text = CONTRADICTED, "pr_belongs_to_other_repository", (
                    "GitHub reports the pull request against a different base repository.")
                observed = {"base_repository": pr.base_repo}
                evidence = (pr_ref,)
            elif pr_obs is not None and pr_obs.status == "not_found" and repo_identity:
                status, code, text = CONTRADICTED, "pr_not_found", "The repository is readable but this pull request does not exist."
            else:
                code, text = _pull_request_problem(snapshot)
                status = UNVERIFIABLE
        elif claim.claim_type == "base_branch":
            expected = {"base_branch": request.expected_base_branch}
            if not pr_ok:
                code, text = _pull_request_problem(snapshot)
                status = UNVERIFIABLE
            elif not identity:
                status, code, text = UNVERIFIABLE, "pull_request_identity_not_established", (
                    "The base repository does not match the expected repository.")
            else:
                observed = {"base_branch": pr.base_ref}
                evidence = (pr_ref,)
                if pr.base_ref == request.expected_base_branch:
                    status, code, text = SUPPORTED, "base_branch_matches", "The pull request targets the expected base branch."
                else:
                    status, code, text = CONTRADICTED, "base_branch_mismatch", "The pull request targets a different base branch."
        elif claim.claim_type == "head_sha":
            expected = {"head_sha": request.expected_head_sha}
            if not pr_ok:
                code, text = _pull_request_problem(snapshot)
                status = UNVERIFIABLE
            elif not identity:
                status, code, text = UNVERIFIABLE, "pull_request_identity_not_established", (
                    "The base repository does not match the expected repository.")
            else:
                observed = {"head_sha": pr.head_sha, "head_sha_recheck": recheck_sha}
                evidence = (pr_ref,)
                if recheck_sha is None:
                    status, code, text = UNVERIFIABLE, "head_recheck_unavailable", (
                        "The head could not be read a second time, so stability during collection is unknown.")
                elif recheck_sha != pr.head_sha:
                    status, code, text = UNVERIFIABLE, "head_changed_during_collection", (
                        "The pull request head changed while evidence was collected; the current revision cannot be established.")
                elif pr.head_sha == request.expected_head_sha:
                    status, code, text = SUPPORTED, "head_sha_matches", "The current head matches the expected revision."
                else:
                    status, code, text = CONTRADICTED, "head_sha_mismatch", "The current head differs from the expected revision."
        elif claim.claim_type == "pr_merged":
            expected = {"merged": True}
            if not pr_ok:
                code, text = _pull_request_problem(snapshot)
                status = UNVERIFIABLE
            elif not identity:
                status, code, text = UNVERIFIABLE, "pull_request_identity_not_established", (
                    "The base repository does not match the expected repository.")
            else:
                observed = {"merged": pr.merged, "merged_at": pr.merged_at, "state": pr.state}
                evidence = (pr_ref,)
                if pr.merged and pr.merged_at:
                    status, code, text = SUPPORTED, "merged_flag_observed", (
                        "GitHub reported merged=true at collection time. This does not prove the merge commit "
                        "equals the expected revision or that anything was deployed.")
                elif pr.merged:
                    status, code, text = UNVERIFIABLE, "merge_evidence_inconsistent", "merged=true without merged_at."
                elif pr.state == "closed":
                    status, code, text = CONTRADICTED, "closed_without_merge", "The pull request was closed without merging."
                else:
                    status, code, text = CONTRADICTED, "not_merged", "The pull request is open and not merged."
        else:  # required_checks_passed
            result, checks = _required_checks(request, snapshot)
            status, code, text = result.status, result.reason_code, result.reason
            expected, observed, evidence = result.expected, result.observed, result.evidence
        claims.append(ClaimResult(claim_id=claim.claim_id, claim_type=claim.claim_type, status=status,
                                  reason_code=code, reason=text, expected=expected, observed=observed,
                                  evidence=evidence))
    warnings: list[str] = []
    if snapshot.provenance.synthetic:
        warnings.append("SYNTHETIC FIXTURE: this is not production evidence.")
    if snapshot.provenance.kind == "offline_bundle":
        warnings.append("Saved offline bundle: integrity is relative to its hash; source authenticity is not established.")
    if snapshot.provenance.kind == "saved_live_capture":
        warnings.append("Saved live capture: observations describe the time they were collected, not this audit's time.")
    if not snapshot.network_used and not snapshot.provenance.synthetic:
        warnings.append("Uploaded or saved evidence: no network was used for this audit. "
                        "Declared provenance does not authenticate the source or establish current GitHub state.")
    if pr_ok and recheck_sha is not None and recheck_sha != pr.head_sha:
        warnings.append("The pull request head changed during collection; current-revision claims abstain.")
    for observation in snapshot.observations:
        if observation.status != "ok" or not observation.complete:
            warnings.append(f"{observation.name}: {observation.status}"
                            + ("" if observation.complete else " (incomplete)"))
    verdict = aggregate_verdict(item.status for item in claims)
    return Verification(verdict=verdict, claims=tuple(claims), checks=checks, warnings=tuple(warnings))
