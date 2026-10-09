"""Versioned input contract for GitHub execution verification (schema v1).

The contract only names observable facts about one pull request and one
revision. It never accepts URLs, file paths or credentials.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = 1
DOMAIN = "github"

SUPPORTED_CLAIM_TYPES = ("pr_exists", "base_branch", "head_sha", "pr_merged", "required_checks_passed")
UNSUPPORTED_CLAIM_TYPES = ("production_deployment", "all_tests_passed")
CLAIM_TYPES = SUPPORTED_CLAIM_TYPES + UNSUPPORTED_CLAIM_TYPES

MAX_CLAIMS = 20
MAX_REQUIRED_CHECKS = 20
MAX_CHECK_NAME_LENGTH = 200
MAX_PULL_REQUEST_NUMBER = 2_147_483_647

_OWNER = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_CLAIM_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_BRANCH = re.compile(r"^[A-Za-z0-9._/-]{1,250}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

_REQUEST_KEYS = {"schema_version", "domain", "repository", "pull_request", "expected_head_sha",
                 "expected_base_branch", "required_checks", "claims"}
_REPOSITORY_KEYS = {"owner", "name"}
_CLAIM_KEYS = {"id", "type"}


class ContractError(ValueError):
    """Safe validation message; it never echoes submitted secrets."""


@dataclass(frozen=True)
class Repository:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


@dataclass(frozen=True)
class ClaimSpec:
    claim_id: str
    claim_type: str


@dataclass(frozen=True)
class GithubRequest:
    repository: Repository
    pull_request: int
    expected_head_sha: str
    expected_base_branch: str
    required_checks: tuple[str, ...]
    claims: tuple[ClaimSpec, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "domain": DOMAIN,
            "repository": {"owner": self.repository.owner, "name": self.repository.name},
            "pull_request": self.pull_request,
            "expected_head_sha": self.expected_head_sha,
            "expected_base_branch": self.expected_base_branch,
            "required_checks": list(self.required_checks),
            "claims": [{"id": claim.claim_id, "type": claim.claim_type} for claim in self.claims],
        }


def _exact_keys(value: Any, allowed: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be an object.")
    unknown = set(value) - allowed
    if unknown:
        raise ContractError(f"Unknown fields in {label}.")
    return value


def _string(value: Any, label: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ContractError(f"{label} is not valid.")
    return value


def _validate_branch(value: Any) -> str:
    if not isinstance(value, str) or not _BRANCH.fullmatch(value):
        raise ContractError("expected_base_branch is not a valid branch name.")
    if value.startswith(("-", "/")) or value.endswith(("/", ".", ".lock")) or ".." in value or "//" in value:
        raise ContractError("expected_base_branch is not a valid branch name.")
    return value


def parse_request(payload: Any) -> GithubRequest:
    """Validate a schema-v1 GitHub verification request and return it frozen."""
    body = _exact_keys(payload, _REQUEST_KEYS, "request")
    if type(body.get("schema_version")) is not int or body.get("schema_version") != SCHEMA_VERSION:
        raise ContractError("Only schema_version 1 is supported.")
    if body.get("domain") != DOMAIN:
        raise ContractError("domain must be github.")

    repo = _exact_keys(body.get("repository"), _REPOSITORY_KEYS, "repository")
    owner = _string(repo.get("owner"), "repository owner", _OWNER)
    name = _string(repo.get("name"), "repository name", _REPOSITORY)
    if name in (".", ".."):
        raise ContractError("repository name is not valid.")

    number = body.get("pull_request")
    if type(number) is not int or not 1 <= number <= MAX_PULL_REQUEST_NUMBER:
        raise ContractError("pull_request must be a positive integer.")

    head = _string(body.get("expected_head_sha"), "expected_head_sha", _SHA)
    base = _validate_branch(body.get("expected_base_branch"))

    checks = body.get("required_checks")
    if not isinstance(checks, list) or not 1 <= len(checks) <= MAX_REQUIRED_CHECKS:
        raise ContractError(f"required_checks must contain 1 to {MAX_REQUIRED_CHECKS} names.")
    names: list[str] = []
    for item in checks:
        if not isinstance(item, str) or item != item.strip() or not item:
            raise ContractError("Each required check needs a non-empty name without surrounding spaces.")
        if len(item) > MAX_CHECK_NAME_LENGTH or _CONTROL.search(item):
            raise ContractError("A required check name is too long or contains control characters.")
        if item in names:
            raise ContractError("Duplicate required check names are not allowed.")
        names.append(item)

    raw_claims = body.get("claims")
    if not isinstance(raw_claims, list) or not 1 <= len(raw_claims) <= MAX_CLAIMS:
        raise ContractError(f"claims must contain 1 to {MAX_CLAIMS} entries.")
    claims: list[ClaimSpec] = []
    seen_ids: set[str] = set()
    for item in raw_claims:
        entry = _exact_keys(item, _CLAIM_KEYS, "claim")
        claim_id = _string(entry.get("id"), "claim id", _CLAIM_ID)
        if claim_id in seen_ids:
            raise ContractError("Claim ids must be unique.")
        seen_ids.add(claim_id)
        claim_type = entry.get("type")
        if claim_type not in CLAIM_TYPES:
            raise ContractError("Unknown claim type.")
        claims.append(ClaimSpec(claim_id=claim_id, claim_type=claim_type))

    return GithubRequest(
        repository=Repository(owner=owner, name=name),
        pull_request=number,
        expected_head_sha=head,
        expected_base_branch=base,
        required_checks=tuple(names),
        claims=tuple(claims),
    )
