"""ProofTrail's offline-first evidence auditor.

The public surface is intentionally small:

* :func:`audit_trace` turns an ``AgentTrace`` plus its raw ``LedgerEvent`` rows
  into the shared ``AuditOutput`` contract.
* :func:`render_certificate_json` and :func:`render_certificate_markdown`
  render the same result with the exact evidence rows and tool calls attached.
* :class:`DeterministicClaimExtractor` is the zero-cost fallback.  A future LLM
  extractor can implement the same ``extract(report)`` method without changing
  reconciliation or evaluation code.

Ground-truth labels are deliberately not accepted anywhere in this package.
"""

from .certificate import build_certificate, render_certificate_json, render_certificate_markdown
from .claim_extractor import DeterministicClaimExtractor, ExtractedClaim, extract_claims
from .pipeline import ProofTrailPipeline, audit_trace

__all__ = [
    "DeterministicClaimExtractor",
    "ExtractedClaim",
    "ProofTrailPipeline",
    "audit_trace",
    "build_certificate",
    "extract_claims",
    "render_certificate_json",
    "render_certificate_markdown",
]
