"""Evidence snapshots: live reads, saved live captures, offline bundles and synthetic fixtures.

A bundle is plain JSON. Its SHA-256 (over canonical JSON) proves that the bundle
is unchanged since it was hashed. It does not prove who produced it.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from .contract import ContractError

BUNDLE_SCHEMA_VERSION = 1
PROVENANCE_KINDS = ("live", "saved_live_capture", "offline_bundle", "synthetic_fixture")
OBSERVATION_NAMES = ("repository", "pull_request", "pull_request_recheck", "check_runs", "commit_statuses")
OBSERVATION_STATUSES = ("ok", "not_found", "unauthorized", "forbidden", "rate_limited", "timeout", "unavailable",
                        "redirect_refused", "too_large", "invalid_response", "pagination_limit", "not_collected")
MAX_CHECK_RUNS = 500
MAX_COMMIT_STATUSES = 500
MAX_OBSERVATIONS = 20

_SHA = re.compile(r"^[0-9a-f]{40}$")
_FULL_NAME = re.compile(r"^[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}$")

_TOP_KEYS = {"bundle_schema_version", "provenance", "repository", "pull_request",
             "pull_request_recheck_head_sha", "check_runs", "commit_statuses", "observations"}


@dataclass(frozen=True)
class Provenance:
    kind: str
    label: str
    synthetic: bool
    collected_at: str | None
    api_host: str | None
    fixture_note: str | None = None


@dataclass(frozen=True)
class Observation:
    name: str
    endpoint: str
    status: str
    http_status: int | None
    collected_at: str | None
    pages: int
    complete: bool
    message: str = ""


@dataclass(frozen=True)
class RepositoryRecord:
    full_name: str
    private: bool
    default_branch: str


@dataclass(frozen=True)
class PullRequestRecord:
    number: int
    state: str
    merged: bool
    merged_at: str | None
    title: str
    html_url: str | None
    base_ref: str
    base_repo: str | None
    head_ref: str
    head_sha: str
    head_repo: str | None


@dataclass(frozen=True)
class CheckRunRecord:
    run_id: int
    name: str
    head_sha: str
    status: str
    conclusion: str | None
    producer: str
    started_at: str | None
    completed_at: str | None
    html_url: str | None


@dataclass(frozen=True)
class CommitStatusRecord:
    context: str
    state: str
    sha: str | None
    updated_at: str | None
    target_url: str | None


@dataclass(frozen=True)
class EvidenceSnapshot:
    provenance: Provenance
    repository: RepositoryRecord | None
    pull_request: PullRequestRecord | None
    recheck_head_sha: str | None
    check_runs: tuple[CheckRunRecord, ...]
    commit_statuses: tuple[CommitStatusRecord, ...]
    observations: tuple[Observation, ...]

    def observation(self, name: str) -> Observation | None:
        for item in self.observations:
            if item.name == name:
                return item
        return None

    def to_bundle(self) -> dict[str, Any]:
        provenance: dict[str, Any] = {
            "kind": self.provenance.kind,
            "label": self.provenance.label,
            "synthetic": self.provenance.synthetic,
            "collected_at": self.provenance.collected_at,
            "api_host": self.provenance.api_host,
        }
        if self.provenance.fixture_note is not None:
            provenance["fixture_note"] = self.provenance.fixture_note
        pull = None
        if self.pull_request is not None:
            record = self.pull_request
            pull = {
                "number": record.number, "state": record.state, "merged": record.merged,
                "merged_at": record.merged_at, "title": record.title, "html_url": record.html_url,
                "base": {"ref": record.base_ref, "repo": record.base_repo},
                "head": {"ref": record.head_ref, "sha": record.head_sha, "repo": record.head_repo},
            }
        repository = None
        if self.repository is not None:
            repository = {"full_name": self.repository.full_name, "private": self.repository.private,
                          "default_branch": self.repository.default_branch}
        return {
            "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
            "provenance": provenance,
            "repository": repository,
            "pull_request": pull,
            "pull_request_recheck_head_sha": self.recheck_head_sha,
            "check_runs": [
                {"id": run.run_id, "name": run.name, "head_sha": run.head_sha, "status": run.status,
                 "conclusion": run.conclusion, "producer": run.producer, "started_at": run.started_at,
                 "completed_at": run.completed_at, "html_url": run.html_url}
                for run in sorted(self.check_runs, key=lambda item: item.run_id)
            ],
            "commit_statuses": [
                {"context": item.context, "state": item.state, "sha": item.sha,
                 "updated_at": item.updated_at, "target_url": item.target_url}
                for item in sorted(self.commit_statuses, key=lambda item: item.context)
            ],
            "observations": [
                {"name": item.name, "endpoint": item.endpoint, "status": item.status,
                 "http_status": item.http_status, "collected_at": item.collected_at, "pages": item.pages,
                 "complete": item.complete, "message": item.message}
                for item in self.observations
            ],
        }


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def bundle_sha256(bundle: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(bundle)).hexdigest()


def _object(value: Any, allowed: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be an object.")
    if set(value) - allowed:
        raise ContractError(f"Unknown fields in {label}.")
    missing = allowed - set(value) - _OPTIONAL.get(label, set())
    if missing:
        raise ContractError(f"Missing fields in {label}.")
    return value


_OPTIONAL = {"check run": {"started_at", "completed_at", "html_url"},
             "commit status": {"sha", "updated_at", "target_url"},
             "pull request": set(), "provenance": {"fixture_note", "collected_at", "api_host"},
             "observation": {"http_status", "collected_at", "message"}}


def _text(value: Any, label: str, limit: int, *, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or len(value) > limit:
        raise ContractError(f"{label} is not valid.")
    return value


def _sha(value: Any, label: str, *, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ContractError(f"{label} must be a full 40-character lowercase SHA.")
    return value


def _integer(value: Any, label: str, *, low: int, high: int, allow_none: bool = False) -> int | None:
    if value is None and allow_none:
        return None
    if type(value) is not int or not low <= value <= high:
        raise ContractError(f"{label} is not valid.")
    return value


def _flag(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise ContractError(f"{label} must be true or false.")
    return value


def _provenance(value: Any) -> Provenance:
    body = _object(value, {"kind", "label", "synthetic", "collected_at", "api_host", "fixture_note"}, "provenance")
    kind = body.get("kind")
    if kind not in PROVENANCE_KINDS:
        raise ContractError("Unknown provenance kind.")
    synthetic = _flag(body.get("synthetic"), "provenance.synthetic")
    if synthetic != (kind == "synthetic_fixture"):
        raise ContractError("Only synthetic_fixture bundles may be marked synthetic, and they must be.")
    note = _text(body.get("fixture_note"), "fixture_note", 300, allow_none=True)
    if synthetic and not note:
        raise ContractError("Synthetic fixtures need a fixture_note saying they are not production evidence.")
    return Provenance(
        kind=kind,
        label=_text(body.get("label"), "provenance label", 200),
        synthetic=synthetic,
        collected_at=_text(body.get("collected_at"), "collected_at", 40, allow_none=True),
        api_host=_text(body.get("api_host"), "api_host", 100, allow_none=True),
        fixture_note=note,
    )


def _repository(value: Any) -> RepositoryRecord | None:
    if value is None:
        return None
    body = _object(value, {"full_name", "private", "default_branch"}, "repository")
    full_name = _text(body.get("full_name"), "repository full_name", 140)
    if not _FULL_NAME.fullmatch(full_name):
        raise ContractError("repository full_name is not valid.")
    return RepositoryRecord(full_name=full_name, private=_flag(body.get("private"), "repository.private"),
                            default_branch=_text(body.get("default_branch"), "default_branch", 250))


def _pull_request(value: Any) -> PullRequestRecord | None:
    if value is None:
        return None
    body = _object(value, {"number", "state", "merged", "merged_at", "title", "html_url", "base", "head"},
                   "pull request")
    base = _object(body.get("base"), {"ref", "repo"}, "pull request base")
    head = _object(body.get("head"), {"ref", "sha", "repo"}, "pull request head")
    return PullRequestRecord(
        number=_integer(body.get("number"), "pull request number", low=1, high=2_147_483_647),
        state=_text(body.get("state"), "pull request state", 20),
        merged=_flag(body.get("merged"), "pull request merged"),
        merged_at=_text(body.get("merged_at"), "merged_at", 40, allow_none=True),
        title=_text(body.get("title"), "pull request title", 300),
        html_url=_text(body.get("html_url"), "html_url", 300, allow_none=True),
        base_ref=_text(base.get("ref"), "base ref", 250),
        base_repo=_text(base.get("repo"), "base repo", 140, allow_none=True),
        head_ref=_text(head.get("ref"), "head ref", 250),
        head_sha=_sha(head.get("sha"), "head sha"),
        head_repo=_text(head.get("repo"), "head repo", 140, allow_none=True),
    )


def _check_runs(value: Any) -> tuple[CheckRunRecord, ...]:
    if not isinstance(value, list) or len(value) > MAX_CHECK_RUNS:
        raise ContractError("check_runs must be a list within the size limit.")
    runs = []
    for item in value:
        body = _object(item, {"id", "name", "head_sha", "status", "conclusion", "producer",
                              "started_at", "completed_at", "html_url"}, "check run")
        runs.append(CheckRunRecord(
            run_id=_integer(body.get("id"), "check run id", low=1, high=2**53),
            name=_text(body.get("name"), "check run name", 200),
            head_sha=_sha(body.get("head_sha"), "check run head_sha"),
            status=_text(body.get("status"), "check run status", 40),
            conclusion=_text(body.get("conclusion"), "check run conclusion", 40, allow_none=True),
            producer=_text(body.get("producer"), "check run producer", 100),
            started_at=_text(body.get("started_at"), "started_at", 40, allow_none=True),
            completed_at=_text(body.get("completed_at"), "completed_at", 40, allow_none=True),
            html_url=_text(body.get("html_url"), "check run url", 500, allow_none=True),
        ))
    return tuple(runs)


def _commit_statuses(value: Any) -> tuple[CommitStatusRecord, ...]:
    if not isinstance(value, list) or len(value) > MAX_COMMIT_STATUSES:
        raise ContractError("commit_statuses must be a list within the size limit.")
    statuses = []
    for item in value:
        body = _object(item, {"context", "state", "sha", "updated_at", "target_url"}, "commit status")
        statuses.append(CommitStatusRecord(
            context=_text(body.get("context"), "status context", 200),
            state=_text(body.get("state"), "status state", 20),
            sha=_sha(body.get("sha"), "status sha", allow_none=True),
            updated_at=_text(body.get("updated_at"), "updated_at", 40, allow_none=True),
            target_url=_text(body.get("target_url"), "target_url", 500, allow_none=True),
        ))
    return tuple(statuses)


def _observations(value: Any) -> tuple[Observation, ...]:
    if not isinstance(value, list) or len(value) > MAX_OBSERVATIONS:
        raise ContractError("observations must be a list within the size limit.")
    items = []
    for entry in value:
        body = _object(entry, {"name", "endpoint", "status", "http_status", "collected_at", "pages",
                               "complete", "message"}, "observation")
        if body.get("name") not in OBSERVATION_NAMES or body.get("status") not in OBSERVATION_STATUSES:
            raise ContractError("Unknown observation name or status.")
        items.append(Observation(
            name=body["name"],
            endpoint=_text(body.get("endpoint"), "endpoint", 200),
            status=body["status"],
            http_status=_integer(body.get("http_status"), "http_status", low=100, high=599, allow_none=True),
            collected_at=_text(body.get("collected_at"), "collected_at", 40, allow_none=True),
            pages=_integer(body.get("pages"), "pages", low=0, high=1000),
            complete=_flag(body.get("complete"), "observation complete"),
            message=_text(body.get("message", ""), "message", 300) or "",
        ))
    return tuple(items)


def load_bundle(payload: Any) -> EvidenceSnapshot:
    """Validate a saved bundle strictly; unknown or malformed fields are rejected."""
    body = _object(payload, _TOP_KEYS, "bundle")
    if type(body.get("bundle_schema_version")) is not int or body["bundle_schema_version"] != BUNDLE_SCHEMA_VERSION:
        raise ContractError("Only bundle_schema_version 1 is supported.")
    return EvidenceSnapshot(
        provenance=_provenance(body.get("provenance")),
        repository=_repository(body.get("repository")),
        pull_request=_pull_request(body.get("pull_request")),
        recheck_head_sha=_sha(body.get("pull_request_recheck_head_sha"), "recheck head sha", allow_none=True),
        check_runs=_check_runs(body.get("check_runs")),
        commit_statuses=_commit_statuses(body.get("commit_statuses")),
        observations=_observations(body.get("observations")),
    )
