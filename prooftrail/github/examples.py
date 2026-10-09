"""Synthetic scenario packs for offline audits, tests and the local UI.

Every synthetic pack is labelled as such. Owner, repository, SHAs and timestamps
are placeholders, not GitHub objects. Expected verdicts are written by hand so
the tests check the rules independently of the engine's output.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contract import GithubRequest
from .evidence import EvidenceSnapshot

PACK_SCHEMA_VERSION = 1
OWNER = "example-owner"
REPO = "example-repo"
EXPECTED = "a" * 40
OTHER = "b" * 40
OLD = "c" * 40
COLLECTED = "2026-10-09T10:00:00Z"
MERGED_AT = "2026-10-08T12:00:00Z"
REQUIRED_CHECKS = ["replay", "mcp-adapter"]
NOTE = "Synthetic fixture for tests and demonstrations. Not production evidence."

_ENDPOINTS = {
    "repository": f"/repos/{OWNER}/{REPO}",
    "pull_request": f"/repos/{OWNER}/{REPO}/pulls/4",
    "check_runs": f"/repos/{OWNER}/{REPO}/commits/{EXPECTED}/check-runs",
    "commit_statuses": f"/repos/{OWNER}/{REPO}/commits/{EXPECTED}/status",
    "pull_request_recheck": f"/repos/{OWNER}/{REPO}/pulls/4",
}
_OBSERVATION_ORDER = ("repository", "pull_request", "check_runs", "commit_statuses", "pull_request_recheck")
RATE_LIMITED = ("rate_limited", 403, 0, False)
FORBIDDEN = ("forbidden", 403, 0, False)
TIMED_OUT = ("timeout", None, 0, False)
NOT_FOUND = ("not_found", 404, 0, False)
INCOMPLETE = ("pagination_limit", 200, 5, False)


def _request(claim_types: list[str], checks: list[str] | None = None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "domain": "github",
        "repository": {"owner": OWNER, "name": REPO},
        "pull_request": 4,
        "expected_head_sha": EXPECTED,
        "expected_base_branch": "main",
        "required_checks": list(checks or REQUIRED_CHECKS),
        "claims": [{"id": f"c{index}", "type": kind} for index, kind in enumerate(claim_types, start=1)],
    }


def _pull(*, head: str = EXPECTED, base: str = "main", base_repo: str = f"{OWNER}/{REPO}",
          merged: bool = False, state: str = "open") -> dict[str, Any]:
    return {
        "number": 4, "state": state, "merged": merged, "merged_at": MERGED_AT if merged else None,
        "title": "Synthetic pull request", "html_url": f"https://github.com/{OWNER}/{REPO}/pull/4",
        "base": {"ref": base, "repo": base_repo},
        "head": {"ref": "synthetic/feature", "sha": head, "repo": f"{OWNER}/{REPO}"},
    }


def _run(run_id: int, name: str, *, conclusion: str | None = "success", status: str = "completed",
         sha: str = EXPECTED, producer: str = "github-actions") -> dict[str, Any]:
    return {"id": run_id, "name": name, "head_sha": sha, "status": status, "conclusion": conclusion,
            "producer": producer, "started_at": COLLECTED,
            "completed_at": COLLECTED if status == "completed" else None, "html_url": None}


def _status(context: str, state: str, *, sha: str = EXPECTED) -> dict[str, Any]:
    return {"context": context, "state": state, "sha": sha, "updated_at": COLLECTED, "target_url": None}


def _observations(changes: dict[str, tuple[str, int | None, int, bool]]) -> list[dict[str, Any]]:
    items = []
    for name in _OBSERVATION_ORDER:
        status, http_status, pages, complete = changes.get(name, ("ok", 200, 1, True))
        items.append({"name": name, "endpoint": _ENDPOINTS[name], "status": status, "http_status": http_status,
                      "collected_at": COLLECTED, "pages": pages, "complete": complete, "message": ""})
    return items


def _bundle(label: str, *, pull: dict[str, Any] | None, recheck: str | None = EXPECTED,
            runs: list[dict[str, Any]] | None = None, statuses: list[dict[str, Any]] | None = None,
            changes: dict[str, tuple[str, int | None, int, bool]] | None = None) -> dict[str, Any]:
    return {
        "bundle_schema_version": 1,
        "provenance": {"kind": "synthetic_fixture", "label": label, "synthetic": True,
                       "collected_at": COLLECTED, "api_host": None, "fixture_note": NOTE},
        "repository": {"full_name": f"{OWNER}/{REPO}", "private": False, "default_branch": "main"},
        "pull_request": pull,
        "pull_request_recheck_head_sha": recheck,
        "check_runs": list(runs or []),
        "commit_statuses": list(statuses or []),
        "observations": _observations(changes or {}),
    }


def _pack(identifier: str, title: str, description: str, claims: list[str], bundle: dict[str, Any],
          verdict: str, claim_verdicts: list[str], checks: list[str] | None = None) -> dict[str, Any]:
    return {
        "pack_schema_version": PACK_SCHEMA_VERSION,
        "id": identifier,
        "title": title,
        "description": description,
        "synthetic": True,
        "note": NOTE,
        "request": _request(claims, checks),
        "bundle": bundle,
        "expected": {"verdict": verdict,
                     "claims": {f"c{index}": status for index, status in enumerate(claim_verdicts, start=1)}},
    }


def _healthy_runs() -> list[dict[str, Any]]:
    return [_run(101, "replay"), _run(102, "replay"), _run(103, "mcp-adapter")]


def scenario_packs() -> list[dict[str, Any]]:
    """Return the synthetic scenario packs in a fixed order."""
    correct = ["pr_exists", "base_branch", "head_sha", "required_checks_passed"]
    return [
        _pack("synthetic-correct-open-pr", "Correct open pull request",
              "PR exists, targets main, head matches, and both required checks succeeded on the expected SHA. "
              "Two replay attempts come from separate events; the latest attempt counts.",
              correct, _bundle("Correct open PR", pull=_pull(), runs=_healthy_runs()),
              "SUPPORTED", ["SUPPORTED"] * 4),
        _pack("synthetic-other-repository", "PR attached to another repository",
              "GitHub reports the pull request against a different base repository.",
              correct, _bundle("PR in other repository", pull=_pull(base_repo="other-owner/other-repo"),
                               runs=_healthy_runs()),
              "CONTRADICTED", ["CONTRADICTED", "UNVERIFIABLE", "UNVERIFIABLE", "SUPPORTED"]),
        _pack("synthetic-wrong-base", "Wrong target branch",
              "The pull request targets develop, but the request expects main.",
              correct, _bundle("Wrong base branch", pull=_pull(base="develop"), runs=_healthy_runs()),
              "CONTRADICTED", ["SUPPORTED", "CONTRADICTED", "SUPPORTED", "SUPPORTED"]),
        _pack("synthetic-head-mismatch", "Head SHA mismatch",
              "The pull request head is stable at a different SHA from the expected revision.",
              ["pr_exists", "head_sha"], _bundle("Head mismatch", pull=_pull(head=OTHER), recheck=OTHER),
              "CONTRADICTED", ["SUPPORTED", "CONTRADICTED"]),
        _pack("synthetic-merge-claim-unmerged", "Merge claimed for an open pull request",
              "The request claims a merge, but GitHub reports the pull request as open and unmerged.",
              ["pr_merged"], _bundle("Unmerged PR", pull=_pull(state="open", merged=False)),
              "CONTRADICTED", ["CONTRADICTED"]),
        _pack("synthetic-merged-pr", "Merged pull request",
              "GitHub reports merged=true with a merge timestamp. That flag is the only fact the merge claim establishes.",
              ["pr_merged"], _bundle("Merged PR", pull=_pull(state="closed", merged=True)),
              "SUPPORTED", ["SUPPORTED"]),
        _pack("synthetic-older-sha-success", "Successful checks on an older SHA only",
              "Required checks passed on an earlier commit. Nothing ran on the expected SHA.",
              ["required_checks_passed"],
              _bundle("Checks on older SHA", pull=_pull(),
                      runs=[_run(201, "replay", sha=OLD), _run(202, "mcp-adapter", sha=OLD)]),
              "CONTRADICTED", ["CONTRADICTED"]),
        _pack("synthetic-failed-check", "Failed required check",
              "The replay check concluded failure on the expected SHA.",
              ["required_checks_passed"],
              _bundle("Failed check", pull=_pull(),
                      runs=[_run(301, "replay", conclusion="failure"), _run(302, "mcp-adapter")]),
              "CONTRADICTED", ["CONTRADICTED"]),
        _pack("synthetic-pending-check", "Pending required check",
              "The mcp-adapter check is still in progress, so it cannot count as success yet.",
              ["required_checks_passed"],
              _bundle("Pending check", pull=_pull(),
                      runs=[_run(401, "replay"), _run(402, "mcp-adapter", status="in_progress", conclusion=None)]),
              "UNVERIFIABLE", ["UNVERIFIABLE"]),
        _pack("synthetic-skipped-check", "Skipped required check",
              "The replay check was skipped. Skipped is not success, so the claim fails.",
              ["required_checks_passed"],
              _bundle("Skipped check", pull=_pull(),
                      runs=[_run(501, "replay", conclusion="skipped"), _run(502, "mcp-adapter")]),
              "CONTRADICTED", ["CONTRADICTED"]),
        _pack("synthetic-incomplete-checks", "Required check missing from incomplete evidence",
              "Check-run pagination stopped early and mcp-adapter was not collected.",
              ["required_checks_passed"],
              _bundle("Incomplete checks", pull=_pull(), runs=[_run(601, "replay")],
                      changes={"check_runs": INCOMPLETE}),
              "UNVERIFIABLE", ["UNVERIFIABLE"]),
        _pack("synthetic-rerun-latest-success", "Rerun after a failure",
              "The first replay attempt failed and a rerun succeeded. The latest attempt counts.",
              ["required_checks_passed"],
              _bundle("Rerun", pull=_pull(),
                      runs=[_run(701, "replay", conclusion="failure"), _run(702, "replay"), _run(703, "mcp-adapter")]),
              "SUPPORTED", ["SUPPORTED"]),
        _pack("synthetic-ambiguous-producers", "Two producers report the same check name",
              "A check run and a commit status both claim the name replay on the expected SHA.",
              ["required_checks_passed"],
              _bundle("Ambiguous producers", pull=_pull(), runs=[_run(801, "replay"), _run(802, "mcp-adapter")],
                      statuses=[_status("replay", "success")]),
              "UNVERIFIABLE", ["UNVERIFIABLE"]),
        _pack("synthetic-head-changed", "Head changed during collection",
              "The head at the second read differs from the first, so the current revision is not established.",
              ["pr_exists", "head_sha"], _bundle("Head changed", pull=_pull(), recheck=OTHER),
              "UNVERIFIABLE", ["SUPPORTED", "UNVERIFIABLE"]),
        _pack("synthetic-rate-limited", "GitHub rate limit",
              "The pull request could not be read because the rate limit was reached.",
              ["pr_exists", "base_branch"],
              _bundle("Rate limited", pull=None, recheck=None,
                      changes={"pull_request": RATE_LIMITED, "pull_request_recheck": RATE_LIMITED}),
              "UNVERIFIABLE", ["UNVERIFIABLE", "UNVERIFIABLE"]),
        _pack("synthetic-forbidden-checks", "Insufficient permission for check runs",
              "The token cannot read check runs, so the required checks cannot be decided.",
              ["required_checks_passed"],
              _bundle("Forbidden checks", pull=_pull(), runs=[], changes={"check_runs": FORBIDDEN}),
              "UNVERIFIABLE", ["UNVERIFIABLE"]),
        _pack("synthetic-timeout-pull-request", "Pull request read timed out",
              "The pull request endpoint timed out, so the merge status is unknown.",
              ["pr_merged"],
              _bundle("Timed out", pull=None, recheck=None,
                      changes={"pull_request": TIMED_OUT, "pull_request_recheck": TIMED_OUT}),
              "UNVERIFIABLE", ["UNVERIFIABLE"]),
        _pack("synthetic-unsupported-claims", "Claims outside this milestone",
              "Production deployment and an all-tests claim are not verifiable here.",
              ["production_deployment", "all_tests_passed"],
              _bundle("Unsupported claims", pull=_pull(), runs=_healthy_runs()),
              "UNVERIFIABLE", ["UNVERIFIABLE", "UNVERIFIABLE"]),
        _pack("synthetic-pr-not-found", "Pull request does not exist",
              "The repository is readable, but the requested pull request number does not exist.",
              ["pr_exists"], _bundle("PR not found", pull=None, recheck=None,
                                     changes={"pull_request": NOT_FOUND, "pull_request_recheck": NOT_FOUND}),
              "CONTRADICTED", ["CONTRADICTED"]),
    ]


def write_synthetic_packs(directory: Path) -> list[Path]:
    """Write every synthetic pack as deterministic JSON. Existing files are replaced."""
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for pack in scenario_packs():
        path = directory / f"{pack['id']}.json"
        path.write_text(json.dumps(pack, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                        encoding="utf-8", newline="\n")
        written.append(path)
    return written


def live_capture_pack(request: GithubRequest, snapshot: EvidenceSnapshot, identifier: str) -> dict[str, Any]:
    """Package one live snapshot as a saved capture. It is not labelled synthetic."""
    bundle = snapshot.to_bundle()
    bundle["provenance"]["kind"] = "saved_live_capture"
    bundle["provenance"]["label"] = f"Saved live capture collected at {snapshot.provenance.collected_at}"
    return {
        "pack_schema_version": PACK_SCHEMA_VERSION,
        "id": identifier,
        "title": f"Saved live capture: {request.repository.full_name} PR #{request.pull_request}",
        "description": "Read-only GitHub REST API snapshot of a public repository. Not synthetic.",
        "synthetic": False,
        "note": f"Saved live capture collected at {snapshot.provenance.collected_at}.",
        "request": request.to_dict(),
        "bundle": bundle,
    }


def _pack_files(directory: Path) -> dict[str, Path]:
    """Map each pack ID to its file. The listing is the allow-list; caller input never builds a path."""
    files: dict[str, Path] = {}
    if directory.is_dir():
        for path in sorted(directory.glob("*.json")):
            files[json.loads(path.read_text(encoding="utf-8"))["id"]] = path
    return files


def list_packs(directory: Path) -> list[dict[str, Any]]:
    items = []
    for identifier, path in _pack_files(directory).items():
        pack = json.loads(path.read_text(encoding="utf-8"))
        items.append({"id": identifier, "title": pack["title"], "description": pack["description"],
                      "synthetic": pack["synthetic"], "note": pack["note"]})
    return items


def load_pack(directory: Path, identifier: str) -> dict[str, Any]:
    files = _pack_files(directory)
    if identifier not in files:
        raise KeyError("Unknown example.")
    return json.loads(files[identifier].read_text(encoding="utf-8"))
