"""Read-only application boundary shared by local HTTP and future adapters."""
from __future__ import annotations

import json
import math
import types
from dataclasses import fields
from typing import Any, get_args, get_origin, get_type_hints

from .auditor import audit_trace, build_certificate, render_certificate_markdown
from .config import FROZEN_DIR, PROJECT_ROOT
from .freeze import all_case_ids
from .github import ContractError, collect_live, load_bundle, parse_request, run_audit
from .github.client import token_from_environment
from .github.examples import list_packs, load_pack
from .schemas.events import LedgerEvent, verify_chain
from .schemas.trace import AgentTrace
from .ui.model import COMPARISON_PATH

GITHUB_EXAMPLES_DIR = PROJECT_ROOT / "examples" / "github"

MAX_BYTES = 2 * 1024 * 1024
MAX_EVENTS = 2000


class InvalidEvidence(ValueError):
    """Safe, non-sensitive validation message for external callers."""


def decode_json(raw: bytes) -> Any:
    if len(raw) > MAX_BYTES:
        raise InvalidEvidence("Evidence exceeds the 2 MiB limit.")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise InvalidEvidence("Duplicate JSON keys are not allowed.")
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(InvalidEvidence("Non-finite numbers are not allowed.")))
        _depth(value)
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise InvalidEvidence("Expected a valid UTF-8 JSON document.") from exc


def _depth(value, level=0):
    if level > 40:
        raise InvalidEvidence("JSON nesting exceeds 40 levels.")
    if isinstance(value, dict):
        for item in value.values():
            _depth(item, level + 1)
    elif isinstance(value, list):
        for item in value:
            _depth(item, level + 1)
    elif isinstance(value, float) and not math.isfinite(value):
        raise InvalidEvidence("Non-finite numbers are not allowed.")


def _matches(value, annotation):
    origin = get_origin(annotation)
    if annotation is Any:
        return True
    if origin is types.UnionType:
        return any(_matches(value, arg) for arg in get_args(annotation))
    if origin is list:
        return isinstance(value, list) and all(_matches(item, get_args(annotation)[0]) for item in value)
    if origin is dict:
        return isinstance(value, dict) and all(isinstance(key, str) for key in value)
    if annotation is float:
        return type(value) in (int, float)
    if hasattr(annotation, "__dataclass_fields__"):
        try:
            _validate(value, annotation)
            return True
        except InvalidEvidence:
            return False
    return type(value) is annotation


def _validate(value, schema):
    if not isinstance(value, dict):
        raise InvalidEvidence(f"{schema.__name__} must be an object.")
    allowed = {field.name for field in fields(schema)}
    if set(value) - allowed:
        raise InvalidEvidence(f"Unknown fields in {schema.__name__}.")
    hints = get_type_hints(schema)
    for key, item in value.items():
        if not _matches(item, hints[key]):
            raise InvalidEvidence(f"Invalid type for {schema.__name__}.{key}.")


def parse_ledger(value):
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_EVENTS:
        raise InvalidEvidence("Ledger must contain 1–2000 events.")
    events = []
    for row in value:
        _validate(row, LedgerEvent)
        try:
            event = LedgerEvent.from_dict(row)
        except (TypeError, ValueError) as exc:
            raise InvalidEvidence("Ledger event is missing required fields or has an unknown event type.") from exc
        if event.seq < 1 or any(len(h) != 64 or any(c not in "0123456789abcdef" for c in h) for h in (event.hash, event.prev_hash)):
            raise InvalidEvidence("Every event needs a positive sequence and 64-character hash/prev_hash.")
        events.append(event)
    return events


def verify_ledger(payload):
    if not isinstance(payload, dict) or set(payload) != {"ledger"}:
        raise InvalidEvidence("Expected an object containing only ledger.")
    events = parse_ledger(payload["ledger"])
    valid, first = verify_chain(events)
    return {"valid": valid, "first_bad_seq": first, "event_count": len(events),
            "trust_note": "Hash integrity does not establish that the ledger source is authentic."}


def audit_evidence(payload):
    if not isinstance(payload, dict) or set(payload) - {"schema_version", "case_id", "family_id", "seed", "trace", "ledger"}:
        raise InvalidEvidence("Expected trace and ledger, optionally frozen-case metadata. Unknown fields are rejected.")
    if type(payload.get("schema_version", 1)) is not int or payload.get("schema_version", 1) != 1:
        raise InvalidEvidence("Only schema version 1 is supported.")
    raw_trace = payload.get("trace")
    for key, annotation in (("case_id", str), ("family_id", str), ("seed", int)):
        if key in payload and type(payload[key]) is not annotation:
            raise InvalidEvidence(f"Invalid metadata type for {key}.")
    _validate(raw_trace, AgentTrace)
    raw_trace = dict(raw_trace)
    raw_trace.setdefault("case_id", "uploaded-evidence")
    try:
        trace = AgentTrace.from_dict(raw_trace)
        events = parse_ledger(payload.get("ledger"))
        output = audit_trace(trace, events)
        return {"audit": output.to_dict(), "certificate": build_certificate(output, trace, events),
                "certificate_markdown": render_certificate_markdown(output, trace, events),
                "ledger": verify_ledger({"ledger": payload["ledger"]}),
                "limitations": "Refund-domain deterministic extractor; unsupported language can yield UNVERIFIABLE. Not a general-purpose agent judge. No calibrated confidence score.",
                "persisted": False, "model_calls": 0}
    except InvalidEvidence:
        raise
    except (TypeError, ValueError, KeyError, AttributeError, IndexError) as exc:
        raise InvalidEvidence("Evidence does not satisfy the refund trace/ledger contract.") from exc


def list_frozen_cases():
    return list(all_case_ids())


def get_case(case_id):
    if case_id not in all_case_ids():
        raise KeyError("Unknown case.")
    return json.loads((FROZEN_DIR / case_id / "case.json").read_text(encoding="utf-8"))


def get_evidence_certificate(case_id):
    if case_id not in all_case_ids():
        raise KeyError("Unknown case.")
    return json.loads((FROZEN_DIR / case_id / "certificate.json").read_text(encoding="utf-8"))


def get_benchmark_summary():
    return json.loads(COMPARISON_PATH.read_text(encoding="utf-8"))


def audit_github_request(payload):
    """GitHub execution audit. mode=offline needs a saved bundle; mode=live reads api.github.com (read-only)."""
    if not isinstance(payload, dict) or set(payload) - {"mode", "request", "bundle"}:
        raise InvalidEvidence("Expected mode, request and, for offline mode, bundle. Unknown fields are rejected.")
    mode = payload.get("mode", "offline")
    if mode not in ("offline", "live"):
        raise InvalidEvidence("mode must be offline or live.")
    try:
        request = parse_request(payload.get("request"))
        if mode == "offline":
            if "bundle" not in payload:
                raise InvalidEvidence("Offline mode needs a saved evidence bundle.")
            snapshot = load_bundle(payload["bundle"])
        else:
            if "bundle" in payload:
                raise InvalidEvidence("Live mode reads GitHub itself and does not accept a bundle.")
            snapshot = collect_live(request)
    except ContractError as exc:
        raise InvalidEvidence(str(exc)) from exc
    return run_audit(request, snapshot)


def list_github_examples():
    return {"examples": list_packs(GITHUB_EXAMPLES_DIR), "live_token_configured": token_from_environment() is not None}


def get_github_example(identifier):
    """Return one allow-listed scenario pack without its expected verdicts."""
    pack = load_pack(GITHUB_EXAMPLES_DIR, identifier)
    pack.pop("expected", None)
    return pack
