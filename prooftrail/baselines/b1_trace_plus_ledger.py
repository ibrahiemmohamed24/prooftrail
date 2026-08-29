"""Official fair baseline: one model call over trace plus raw ledger."""
from __future__ import annotations

from typing import Any, Protocol

from ..config import AUDITOR_LIMITS, MODEL
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

    def __init__(self, client: AuditCompletionClient):
        self.client = client

    def audit(self, case: FrozenCase) -> AuditOutput:
        raw, usage = self.client.complete_json(
            system_prompt=B1_SYSTEM_PROMPT,
            user_prompt=build_b1_user_prompt(case),
            model=MODEL,
            max_output_tokens=AUDITOR_LIMITS.max_output_tokens,
            effort=AUDITOR_LIMITS.effort,
        )
        problems = validate_audit_output(raw)
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
