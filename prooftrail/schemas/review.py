"""Tamper-evident records for independent human label review.

Review decisions live outside ``data/frozen`` so the frozen benchmark inputs
and their machine-generated provisional labels remain byte-identical forever.
These records are attestations, not cryptographic identity signatures; Git
history (and, preferably, a signed commit or reviewed pull request) supplies
the reviewer-authenticity layer.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


class ReviewAction:
    APPROVE = "APPROVE"
    AMEND = "AMEND"
    ABSTAIN = "ABSTAIN"

    ALL = (APPROVE, AMEND, ABSTAIN)


@dataclass(frozen=True)
class ReviewSource:
    dataset_manifest_sha256: str
    case_sha256: str
    provisional_labels_sha256: str
    review_material_sha256: str
    ledger_tip_hash: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ReviewSource":
        return cls(**value)


@dataclass(frozen=True)
class Reviewer:
    reviewer_id: str
    display_name: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Reviewer":
        return cls(**value)


@dataclass(frozen=True)
class LabelAmendment:
    verdict: str
    first_bad_event_seq: int | None
    expected_claims: list[dict[str, Any]]
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "LabelAmendment":
        return cls(**value)


@dataclass(frozen=True)
class ReviewDecision:
    schema_version: int
    case_id: str
    source: ReviewSource
    reviewer: Reviewer
    reviewed_at: str
    action: str
    attestation_version: str
    attested: bool
    rationale: str
    amendment: LabelAmendment | None = None
    supersedes_decision_sha256: str | None = None
    decision_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ReviewDecision":
        value = dict(value)
        value["source"] = ReviewSource.from_dict(value["source"])
        value["reviewer"] = Reviewer.from_dict(value["reviewer"])
        if value.get("amendment") is not None:
            value["amendment"] = LabelAmendment.from_dict(value["amendment"])
        return cls(**value)


__all__ = [
    "LabelAmendment",
    "ReviewAction",
    "ReviewDecision",
    "Reviewer",
    "ReviewSource",
]
