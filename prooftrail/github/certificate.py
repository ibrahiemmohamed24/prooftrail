"""Certificates for GitHub execution verification (JSON and Markdown).

Certificates state the source label, collection times, bundle hash and the
limits of each verdict. They contain no credentials and no current-time stamp,
so the same bundle always produces the same certificate.
"""
from __future__ import annotations

from typing import Any

from .contract import GithubRequest
from .evidence import EvidenceSnapshot
from .verify import CheckAssessment, ClaimResult, Verification

CERTIFICATE_VERSION = 1

LIMITATIONS = (
    "SUPPORTED on a required check means a check run or commit status named that way completed successfully "
    "on the expected SHA. It does not prove that all tests passed, how many tests ran, or that the change fixes a bug.",
    "pr_merged SUPPORTED means GitHub reported merged=true at collection time. It does not prove that the merge "
    "commit equals the expected revision, and it does not prove deployment.",
    "production_deployment and all_tests_passed are not verified in this milestone and always return UNVERIFIABLE.",
    "CONTRADICTED for a required check means it was not observed as a successful completion on the expected SHA "
    "in complete evidence. It does not prove the check never ran elsewhere.",
    "Hash integrity is relative to the bundle hash. It does not authenticate who produced the evidence.",
    "No numerical confidence is reported. Verdicts come from deterministic rules over the recorded observations.",
)


def _claim(result: ClaimResult) -> dict[str, Any]:
    return {
        "claim_id": result.claim_id,
        "claim_type": result.claim_type,
        "status": result.status,
        "reason_code": result.reason_code,
        "reason": result.reason,
        "expected": result.expected,
        "observed": result.observed,
        "evidence": list(result.evidence),
    }


def _check(item: CheckAssessment) -> dict[str, Any]:
    return {
        "name": item.name,
        "status": item.status,
        "reason_code": item.reason_code,
        "reason": item.reason,
        "producers": list(item.producers),
        "attempt_ids": list(item.attempt_ids),
        "latest_run_id": item.latest_run_id,
        "latest_conclusion": item.latest_conclusion,
        "superseded_ids": list(item.superseded_ids),
        "other_sha_run_ids": list(item.other_sha_run_ids),
        "evidence": list(item.evidence),
    }


def build_certificate(request: GithubRequest, snapshot: EvidenceSnapshot, verification: Verification,
                      bundle_sha256: str) -> dict[str, Any]:
    provenance = snapshot.provenance
    pr = snapshot.pull_request
    repository = snapshot.repository
    claims = [_claim(item) for item in verification.claims]
    return {
        "certificate_type": "github_execution_verification",
        "certificate_version": CERTIFICATE_VERSION,
        "domain": "github",
        "verdict": verification.verdict,
        "source": {
            "kind": provenance.kind,
            "label": provenance.label,
            "synthetic": provenance.synthetic,
            "fixture_note": provenance.fixture_note,
            "collected_at": provenance.collected_at,
            "api_host": provenance.api_host,
            "bundle_sha256": bundle_sha256,
            "integrity_note": "The bundle hash shows the bundle is unchanged since hashing. It does not authenticate the source.",
        },
        "request": request.to_dict(),
        "repository": None if repository is None else {
            "full_name": repository.full_name, "private": repository.private,
            "default_branch": repository.default_branch},
        "pull_request": None if pr is None else {
            "number": pr.number, "state": pr.state, "merged": pr.merged, "merged_at": pr.merged_at,
            "title": pr.title, "html_url": pr.html_url, "base_ref": pr.base_ref, "base_repo": pr.base_repo,
            "head_ref": pr.head_ref, "head_sha": pr.head_sha, "head_repo": pr.head_repo},
        "observed_revision": {
            "expected_head_sha": request.expected_head_sha,
            "pull_request_head_sha": pr.head_sha if pr is not None else None,
            "recheck_head_sha": snapshot.recheck_head_sha,
            "head_changed_during_collection": bool(
                pr is not None and snapshot.recheck_head_sha is not None and snapshot.recheck_head_sha != pr.head_sha),
        },
        "claims": claims,
        "required_checks": [_check(item) for item in verification.checks],
        "observations": [
            {"name": item.name, "endpoint": item.endpoint, "status": item.status,
             "http_status": item.http_status, "collected_at": item.collected_at, "pages": item.pages,
             "complete": item.complete}
            for item in snapshot.observations
        ],
        "warnings": list(verification.warnings),
        "limitations": list(LIMITATIONS),
        "persisted": False,
        "model_calls": 0,
        "network_used": provenance.kind == "live",
    }


def _cell(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(item) for item in value) or "—"
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(certificate: dict[str, Any]) -> str:
    source = certificate["source"]
    revision = certificate["observed_revision"]
    repo = certificate["request"]["repository"]
    lines = [
        f"# GitHub execution verification: {repo['owner']}/{repo['name']} #{certificate['request']['pull_request']}",
        "",
        f"- **Verdict:** `{certificate['verdict']}`",
        f"- **Source:** {_cell(source['label'])}",
        f"- **Bundle SHA-256:** `{source['bundle_sha256']}` ({_cell(source['integrity_note'])})",
        f"- **Expected head:** `{revision['expected_head_sha']}`",
        f"- **Observed head:** `{_cell(revision['pull_request_head_sha'])}`",
        f"- **Recheck head:** `{_cell(revision['recheck_head_sha'])}`",
        f"- **Network used:** {'yes' if certificate['network_used'] else 'no'} · "
        f"**Model calls:** {certificate['model_calls']} · **Persisted:** no",
    ]
    if source["synthetic"]:
        lines.append(f"- **Synthetic fixture:** {_cell(source['fixture_note'])}")
    lines += ["", "## Claims", "", "| Claim | Type | Verdict | Reason code | Reason | Evidence |",
              "|---|---|---|---|---|---|"]
    for claim in certificate["claims"]:
        lines.append(f"| {_cell(claim['claim_id'])} | `{claim['claim_type']}` | `{claim['status']}` | "
                     f"`{claim['reason_code']}` | {_cell(claim['reason'])} | {_cell(claim['evidence'])} |")
    lines += ["", "## Required checks", "", "| Check | Verdict | Reason code | Latest run | Superseded | Producers |",
              "|---|---|---|---|---|---|"]
    for check in certificate["required_checks"]:
        lines.append(f"| {_cell(check['name'])} | `{check['status']}` | `{check['reason_code']}` | "
                     f"{_cell(check['latest_run_id'])} | {_cell(check['superseded_ids'])} | "
                     f"{_cell(check['producers'])} |")
    if not certificate["required_checks"]:
        lines.append("| — | — | — | — | — | — |")
    lines += ["", "## Observations", "", "| Source | Status | Complete | Pages | Collected at |",
              "|---|---|---|---|---|"]
    for item in certificate["observations"]:
        lines.append(f"| {_cell(item['name'])} | `{item['status']}` | {'yes' if item['complete'] else 'no'} | "
                     f"{item['pages']} | {_cell(item['collected_at'])} |")
    if certificate["warnings"]:
        lines += ["", "## Warnings", ""] + [f"- {_cell(item)}" for item in certificate["warnings"]]
    lines += ["", "## Limitations", ""] + [f"- {item}" for item in certificate["limitations"]]
    return "\n".join(lines) + "\n"
