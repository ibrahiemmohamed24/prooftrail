"""One GitHub execution audit: rules, bundle hash and certificates.

HTTP, UI, MCP and CLI adapters all call this function. None of them repeats the rules.
"""
from __future__ import annotations

from typing import Any

from .certificate import build_certificate, render_markdown
from .contract import GithubRequest
from .evidence import EvidenceSnapshot, bundle_sha256
from .verify import verify


def audit(request: GithubRequest, snapshot: EvidenceSnapshot) -> dict[str, Any]:
    verification = verify(request, snapshot)
    digest = bundle_sha256(snapshot.to_bundle())
    certificate = build_certificate(request, snapshot, verification, digest)
    return {
        "verdict": verification.verdict,
        "claims": certificate["claims"],
        "required_checks": certificate["required_checks"],
        "source": certificate["source"],
        "warnings": certificate["warnings"],
        "certificate": certificate,
        "certificate_markdown": render_markdown(certificate),
        "persisted": False,
        "model_calls": 0,
        "network_used": certificate["network_used"],
    }
