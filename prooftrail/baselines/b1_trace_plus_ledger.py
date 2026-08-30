"""Official fair baseline: one model call over trace plus raw ledger."""
from __future__ import annotations

from typing import Any, Protocol

from ..config import AUDITOR_LIMITS, AuditorLimits
from ..schemas.trace import FrozenCase, Usage
from ..schemas.verdict import AuditOutput, ClaimVerdict, validate_audit_output
from .prompts import B1_SYSTEM_PROMPT, build_b1_user_prompt


class AuditCompletionClient(Protocol):
    """Provider-neutral boundary; live and replay clients implement this."""

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
        max_output_tokens: int,
        effort: str,
    ) -> tuple[dict[str, Any], Usage]: ...


class InvalidBaselineOutput(ValueError):
    pass


class B1Auditor:
    """A deliberately structure-free comparator for ProofTrail's hybrid path."""

    name = "B1"

    def __init__(
        self,
        client: AuditCompletionClient,
        *,
        model: str,
        limits: AuditorLimits = AUDITOR_LIMITS,
    ):
        self.client = client
        if not model.strip():
            raise ValueError("B1 model must be explicit")
        self.model = model
        self.limits = limits

    def audit(self, case: FrozenCase) -> AuditOutput:
        raw, usage = self.client.complete_json(
            system_prompt=B1_SYSTEM_PROMPT,
            user_prompt=build_b1_user_prompt(case),
            model=self.model,
            max_output_tokens=self.limits.max_output_tokens,
            effort=self.limits.effort,
        )
        problems = validate_audit_output(raw)
        ledger_seqs = {event.seq for event in case.ledger}
        raw_claims = raw.get("claims")
        if isinstance(raw_claims, list):
            for index, claim in enumerate(raw_claims):
                if not isinstance(claim, dict):
                    continue
                evidence = claim.get("evidence_seqs")
                if isinstance(evidence, list) and all(
                    isinstance(seq, int) and not isinstance(seq, bool) for seq in evidence
                ):
                    missing = sorted(set(evidence) - ledger_seqs)
                    if missing:
                        problems.append(f"claims[{index}] cites missing ledger events: {missing}")
        first_bad = raw.get("first_bad_event_seq")
        if first_bad is not None and first_bad not in ledger_seqs:
            problems.append("first_bad_event_seq does not exist in the ledger")
        if problems:
            raise InvalidBaselineOutput("; ".join(problems))
        return AuditOutput(
            case_id=case.case_id,
            auditor=self.name,
            verdict=raw["verdict"],
            claims=[ClaimVerdict(**claim) for claim in raw["claims"]],
            first_bad_event_seq=raw.get("first_bad_event_seq"),
            explanation=raw.get("explanation", ""),
            usage=usage.to_dict(),
        )
