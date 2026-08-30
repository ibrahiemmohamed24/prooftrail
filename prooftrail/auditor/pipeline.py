"""End-to-end ProofTrail auditor pipeline."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..schemas import AgentTrace, AuditOutput, ClaimVerdict, FrozenCase, LedgerEvent, Status, aggregate_verdict
from ..schemas.events import verify_chain
from .claim_extractor import ClaimExtractor, extract_claims
from .evidence_linker import link_claim
from .reconciler import reconcile_claim
from .temporal_verifier import verify_temporal


_ZERO_USAGE: dict[str, Any] = {
    "input_tokens": 0,
    "output_tokens": 0,
    "cost_usd": 0.0,
    "llm_calls": 0,
}


class ProofTrailPipeline:
    """Offline-first pipeline; inject an extractor to replace the fallback."""

    name = "prooftrail"

    def __init__(
        self,
        extractor: ClaimExtractor | None = None,
        *,
        use_temporal_verifier: bool = True,
    ):
        self.extractor = extractor
        self.use_temporal_verifier = use_temporal_verifier
        self.name = "prooftrail" if use_temporal_verifier else "prooftrail-no-temporal"

    def run(
        self,
        trace: AgentTrace,
        ledger: list[LedgerEvent],
        *,
        usage: Mapping[str, Any] | None = None,
    ) -> AuditOutput:
        ordered = sorted(ledger, key=lambda event: event.seq)
        claims = extract_claims(trace.final_report, self.extractor)

        # Frozen production ledgers are sealed.  Synthetic unit-test ledgers may
        # intentionally omit hashes; when any hash is present, fail closed unless
        # the complete chain verifies.
        if any(event.hash for event in ordered):
            ok, bad_seq = verify_chain(ordered)
            if not ok:
                verdicts = [
                    ClaimVerdict(
                        claim.claim_id,
                        claim.claim_text,
                        claim.claim_type,
                        Status.UNVERIFIABLE,
                        [bad_seq] if bad_seq is not None else [],
                        "Ledger integrity verification failed; its state cannot be trusted as independent evidence.",
                    )
                    for claim in claims
                ]
                return AuditOutput(
                    case_id=trace.case_id,
                    auditor=self.name,
                    verdict=Status.UNVERIFIABLE,
                    claims=verdicts,
                    first_bad_event_seq=bad_seq,
                    explanation=f"Ledger hash-chain verification failed at event #{bad_seq}.",
                    usage=dict(usage or _ZERO_USAGE),
                )

        temporal_issues = verify_temporal(ordered) if self.use_temporal_verifier else []
        verdicts: list[ClaimVerdict] = []
        first_bad_candidates: list[int] = []
        for claim in claims:
            linked = link_claim(claim, trace, ordered)
            result = reconcile_claim(linked, temporal_issues)
            verdicts.append(
                ClaimVerdict(
                    claim_id=claim.claim_id,
                    claim_text=claim.claim_text,
                    claim_type=claim.claim_type,
                    status=result.status,
                    evidence_seqs=list(result.evidence_seqs),
                    reason=result.reason,
                )
            )
            if result.status == Status.CONTRADICTED and result.first_bad_event_seq is not None:
                first_bad_candidates.append(result.first_bad_event_seq)

        verdict = aggregate_verdict(claim.status for claim in verdicts)
        first_bad = min(first_bad_candidates) if first_bad_candidates else None
        counts = {status: sum(item.status == status for item in verdicts) for status in (Status.SUPPORTED, Status.CONTRADICTED, Status.UNVERIFIABLE)}
        explanation = (
            f"Audited {len(verdicts)} claim(s) against {len(ordered)} ledger event(s): "
            f"{counts[Status.SUPPORTED]} supported, {counts[Status.CONTRADICTED]} contradicted, "
            f"{counts[Status.UNVERIFIABLE]} unverifiable."
        )
        return AuditOutput(
            case_id=trace.case_id,
            auditor=self.name,
            verdict=verdict,
            claims=verdicts,
            first_bad_event_seq=first_bad,
            explanation=explanation,
            usage=dict(usage or _ZERO_USAGE),
        )

    def audit(self, case: FrozenCase) -> AuditOutput:
        """Adapter for ``eval.runner.Auditor``; labels never enter this method."""

        return self.run(case.trace, case.ledger)


def audit_trace(
    trace: AgentTrace,
    ledger: list[LedgerEvent],
    *,
    extractor: ClaimExtractor | None = None,
    usage: Mapping[str, Any] | None = None,
) -> AuditOutput:
    """Functional entry point for ``AgentTrace + LedgerEvent[] -> AuditOutput``."""

    return ProofTrailPipeline(extractor).run(trace, ledger, usage=usage)
