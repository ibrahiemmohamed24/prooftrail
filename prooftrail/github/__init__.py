"""GitHub execution verification: observable facts about one pull request and revision.

Layers: contract (input schema) -> evidence (snapshots and bundles) -> client (read-only
live collection) -> verify (deterministic rules) -> certificate (JSON and Markdown).
The refund reconciler is not used here.
"""
from .audit import audit as run_audit
from .client import collect_live
from .contract import ContractError, GithubRequest, parse_request
from .evidence import EvidenceSnapshot, bundle_sha256, load_bundle

__all__ = ["ContractError", "EvidenceSnapshot", "GithubRequest", "bundle_sha256", "collect_live",
           "load_bundle", "parse_request", "run_audit"]
