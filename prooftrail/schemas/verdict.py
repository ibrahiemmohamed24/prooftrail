"""The ONE output schema every auditor emits, and the hidden ground truth.

Fairness rule: B0, B1 and ProofTrail all return an ``AuditOutput``. The evaluator
scores that object only - it never looks at how it was produced.

No numeric confidence. Verdicts are categorical (SUPPORTED / CONTRADICTED /
UNVERIFIABLE) plus an *evidence coverage* fraction, because calibration has not
been measured and a made-up "92%" would be theatre.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


class Status:
    SUPPORTED = "SUPPORTED"          # every action claim matches a committed ledger event
    CONTRADICTED = "CONTRADICTED"    # at least one action claim conflicts with the ledger
    UNVERIFIABLE = "UNVERIFIABLE"    # claim concerns something the ledger cannot see


STATUSES = (Status.SUPPORTED, Status.CONTRADICTED, Status.UNVERIFIABLE)


def aggregate_verdict(statuses: Iterable[str]) -> str:
    """Case-level verdict from claim-level statuses.

    CONTRADICTED dominates (one false action claim poisons the report),
    then UNVERIFIABLE, else SUPPORTED. An empty claim list is UNVERIFIABLE:
    a report that asserts nothing checkable cannot be called supported.
    """
    statuses = list(statuses)
    if not statuses:
        return Status.UNVERIFIABLE
    if Status.CONTRADICTED in statuses:
        return Status.CONTRADICTED
    if Status.UNVERIFIABLE in statuses:
        return Status.UNVERIFIABLE
    return Status.SUPPORTED


class ClaimType:
    """Coarse types so ground truth and auditors talk about the same things."""

    REFUND_ISSUED = "refund_issued"            # "I refunded $X on order Y"
    REFUND_NOT_ISSUED = "refund_not_issued"    # "I did not / could not refund"
    AMOUNT = "amount"                          # the amount stated
    ORDER_REF = "order_ref"                    # the order the action targeted
    COUNT = "count"                            # "one refund", "both orders"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"  # email sent, ticket opened...
    OTHER = "other"

    ALL = (REFUND_ISSUED, REFUND_NOT_ISSUED, AMOUNT, ORDER_REF, COUNT, EXTERNAL_SIDE_EFFECT, OTHER)


@dataclass
class ClaimVerdict:
    claim_id: str
    claim_text: str                        # verbatim span from the final report
    claim_type: str
    status: str
    evidence_seqs: list[int] = field(default_factory=list)   # ledger seqs cited
    reason: str = ""

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"bad status {self.status!r}")
        if self.claim_type not in ClaimType.ALL:
            raise ValueError(f"bad claim_type {self.claim_type!r}")


@dataclass
class AuditOutput:
    case_id: str
    auditor: str                           # "B0" | "B1" | "prooftrail"
    verdict: str
    claims: list[ClaimVerdict]
    first_bad_event_seq: int | None        # earliest ledger seq where things went wrong
    explanation: str = ""
    usage: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.verdict not in STATUSES:
            raise ValueError(f"bad verdict {self.verdict!r}")

    @property
    def evidence_coverage(self) -> tuple[int, int]:
        """(claims with >=1 cited ledger event, total claims)."""
        cited = sum(1 for c in self.claims if c.evidence_seqs)
        return cited, len(self.claims)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        cited, total = self.evidence_coverage
        d["evidence_coverage"] = {"cited": cited, "total": total}
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AuditOutput":
        d = dict(d)
        d.pop("evidence_coverage", None)
        d["claims"] = [ClaimVerdict(**c) for c in d.get("claims", [])]
        return cls(**d)


@dataclass
class GroundTruth:
    """Hidden labels. Derived from the ledger + human-verified claim labels.

    ``verified_by_human`` must be True before a case counts in the headline
    metric; unverified labels are reported separately.
    """

    case_id: str
    family_id: str
    verdict: str
    first_bad_event_seq: int | None
    expected_claims: list[dict[str, Any]]  # [{claim_type, status, evidence_seqs, note}]
    ledger_facts: dict[str, Any]           # e.g. {"refund_count": 2, "refund_total": 84.0}
    verified_by_human: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "GroundTruth":
        return cls(**d)


# ------------------------------------------------------------------------- #
# Schema validation - used on the *raw JSON* returned by any LLM auditor so
# that a malformed answer is scored as wrong, not silently repaired.
# ------------------------------------------------------------------------- #
def validate_audit_output(raw: Any) -> list[str]:
    """Return a list of problems (empty == valid). Never raises."""
    problems: list[str] = []
    if not isinstance(raw, dict):
        return ["output is not an object"]
    if raw.get("verdict") not in STATUSES:
        problems.append(f"verdict must be one of {STATUSES}, got {raw.get('verdict')!r}")
    fbe = raw.get("first_bad_event_seq")
    if fbe is not None and (not isinstance(fbe, int) or isinstance(fbe, bool)):
        problems.append("first_bad_event_seq must be int or null")
    claims = raw.get("claims")
    if not isinstance(claims, list):
        problems.append("claims must be a list")
        return problems
    for i, c in enumerate(claims):
        if not isinstance(c, dict):
            problems.append(f"claims[{i}] is not an object")
            continue
        if c.get("status") not in STATUSES:
            problems.append(f"claims[{i}].status invalid: {c.get('status')!r}")
        if c.get("claim_type") not in ClaimType.ALL:
            problems.append(f"claims[{i}].claim_type invalid: {c.get('claim_type')!r}")
        text = c.get("claim_text")
        if not isinstance(text, str) or not text.strip():
            problems.append(f"claims[{i}].claim_text missing")
        ev = c.get("evidence_seqs", [])
        if not isinstance(ev, list) or not all(isinstance(x, int) and not isinstance(x, bool) for x in ev):
            problems.append(f"claims[{i}].evidence_seqs must be a list of ints")
    return problems
