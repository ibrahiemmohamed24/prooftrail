"""Independent, source-bound human review of provisional benchmark labels.

The frozen cases and provisional labels are never modified. A reviewer reads a
pack derived only from ``case.json`` and ``labels.provisional.json``, then makes
one explicit per-case decision. Accepted decisions are resolved to
``GroundTruth(verified_by_human=True)`` only in memory after every source hash
and the decision hash have been checked.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .config import FROZEN_DIR, REVIEW_DIR, REVIEW_PACK_DIR
from .freeze import (
    CASE_FILE,
    LABELS_FILE,
    MANIFEST_NAME,
    all_case_ids,
    case_dir,
    load_frozen_case,
    load_frozen_labels,
    sha256_file,
)
from .schemas import (
    ClaimType,
    GroundTruth,
    LabelAmendment,
    ReviewAction,
    ReviewDecision,
    Reviewer,
    ReviewSource,
    STATUSES,
    aggregate_verdict,
)
from .schemas.events import GENESIS_HASH, verify_chain


REVIEW_SCHEMA_VERSION = 1
REVIEW_MATERIAL_SCHEMA_VERSION = 1
REVIEW_MANIFEST_SCHEMA_VERSION = 1
ATTESTATION_VERSION = "prooftrail-human-review-v1"
DECISIONS_DIR_NAME = "decisions"
REVIEW_MANIFEST_NAME = "manifest.json"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ReviewValidationError(ValueError):
    """A review cannot be trusted or resolved to a verified label."""


def canonical_json_bytes(value: Any) -> bytes:
    """Stable UTF-8 representation used for every review hash."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def build_review_material(case: Any, provisional: GroundTruth) -> dict[str, Any]:
    """Return exactly what a human may use to judge a label.

    Deliberately excluded: ProofTrail's ``audit.json``/certificate, any
    scenario expected verdict, provider reasoning blocks, and family metadata.
    The provisional proposal is visibly separated from the raw evidence.
    """

    proposal = provisional.to_dict()
    proposal.pop("family_id", None)
    return {
        "schema_version": REVIEW_MATERIAL_SCHEMA_VERSION,
        "case_id": case.case_id,
        "evidence": {
            "user_requests": case.trace.user_requests,
            "final_report": case.trace.final_report,
            "agent_visible_tool_calls": [
                {
                    "tool_call_id": call.tool_call_id,
                    "intent_id": call.intent_id,
                    "tool_name": call.tool_name,
                    "args": call.args,
                    "result": call.result,
                    "error": call.error,
                    "started_seq": call.started_seq,
                    "ended_seq": call.ended_seq,
                }
                for call in case.trace.tool_calls
            ],
            "ledger": [event.to_dict() for event in case.ledger],
        },
        "machine_preannotation_not_evidence": proposal,
    }


def _review_source(
    case_id: str,
    *,
    frozen_dir: str | Path = FROZEN_DIR,
) -> ReviewSource:
    directory = case_dir(frozen_dir, case_id)
    manifest_path = Path(frozen_dir) / MANIFEST_NAME
    if not manifest_path.exists():
        raise FileNotFoundError(f"frozen dataset manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    case = load_frozen_case(case_id, frozen_dir)
    provisional = load_frozen_labels(case_id, frozen_dir)
    case_hash = sha256_file(directory / CASE_FILE)
    labels_hash = sha256_file(directory / LABELS_FILE)
    manifest_row = next(
        (row for row in manifest.get("cases", []) if row.get("case_id") == case_id),
        None,
    )
    if manifest_row is None:
        raise ReviewValidationError(f"{case_id} is absent from the frozen dataset manifest")
    if manifest_row.get("case_sha256") != case_hash:
        raise ReviewValidationError(f"{case_id} case hash does not match the frozen dataset manifest")
    if manifest_row.get("labels_sha256") != labels_hash:
        raise ReviewValidationError(f"{case_id} label hash does not match the frozen dataset manifest")
    chain_valid, bad_seq = verify_chain(case.ledger)
    if not chain_valid:
        raise ReviewValidationError(f"{case_id} ledger hash chain is invalid at event #{bad_seq}")
    material = build_review_material(case, provisional)
    tip_hash = case.ledger[-1].hash if case.ledger else GENESIS_HASH
    return ReviewSource(
        dataset_manifest_sha256=sha256_file(manifest_path),
        case_sha256=case_hash,
        provisional_labels_sha256=labels_hash,
        review_material_sha256=canonical_json_sha256(material),
        ledger_tip_hash=tip_hash,
    )


def review_material_for_case(
    case_id: str,
    *,
    frozen_dir: str | Path = FROZEN_DIR,
) -> tuple[dict[str, Any], ReviewSource]:
    case = load_frozen_case(case_id, frozen_dir)
    provisional = load_frozen_labels(case_id, frozen_dir)
    return build_review_material(case, provisional), _review_source(case_id, frozen_dir=frozen_dir)


def render_review_markdown(material: Mapping[str, Any], source: ReviewSource) -> str:
    evidence = material["evidence"]
    proposal = material["machine_preannotation_not_evidence"]
    lines = [
        f"# Human label review — {material['case_id']}",
        "",
        "> Review the raw evidence first. The machine pre-annotation at the end is a suggestion, not evidence.",
        "> Do not consult this case's ProofTrail certificate or audit output while assigning ground truth.",
        "",
        "## Bound source hashes",
        "",
        f"- Dataset manifest: `{source.dataset_manifest_sha256}`",
        f"- Frozen case: `{source.case_sha256}`",
        f"- Provisional label: `{source.provisional_labels_sha256}`",
        f"- Review material: `{source.review_material_sha256}`",
        f"- Ledger tip: `{source.ledger_tip_hash}`",
        "",
        "## User request(s)",
        "",
        "```json",
        json.dumps(evidence["user_requests"], indent=2, ensure_ascii=False, sort_keys=True),
        "```",
        "",
        "## Agent final report (claims under review)",
        "",
        "```text",
        str(evidence["final_report"]),
        "```",
        "",
        "## Agent-visible tool calls",
        "",
        "```json",
        json.dumps(evidence["agent_visible_tool_calls"], indent=2, ensure_ascii=False, sort_keys=True),
        "```",
        "",
        "## Independent append-only ledger",
        "",
        "```json",
        json.dumps(evidence["ledger"], indent=2, ensure_ascii=False, sort_keys=True),
        "```",
        "",
        "## Machine pre-annotation — not evidence",
        "",
        "```json",
        json.dumps(proposal, indent=2, ensure_ascii=False, sort_keys=True),
        "```",
        "",
        "## Human checklist",
        "",
        "- Read the final report and identify every material action claim.",
        "- Match claims only to independent ledger events and state transitions.",
        "- Use `UNVERIFIABLE` when this ledger cannot observe the claimed side effect.",
        "- Approve, amend, or abstain with a case-specific rationale and explicit attestation.",
        "",
    ]
    return "\n".join(lines)


def write_review_pack(
    case_ids: Sequence[str],
    *,
    frozen_dir: str | Path = FROZEN_DIR,
    output_dir: str | Path = REVIEW_PACK_DIR,
) -> dict[str, dict[str, Path]]:
    """Write derived review aids only; never create a decision."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    written: dict[str, dict[str, Path]] = {}
    index = [
        "# ProofTrail human review queue",
        "",
        "These files are derived review aids. A pack does not verify any label.",
        "",
        "| Case | Markdown | Canonical material |",
        "|---|---|---|",
    ]
    for case_id in case_ids:
        material, source = review_material_for_case(case_id, frozen_dir=frozen_dir)
        json_path = destination / f"{case_id}.review.json"
        markdown_path = destination / f"{case_id}.review.md"
        json_path.write_text(
            json.dumps(material, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        markdown_path.write_text(
            render_review_markdown(material, source),
            encoding="utf-8",
            newline="\n",
        )
        written[case_id] = {"json": json_path, "markdown": markdown_path}
        index.append(f"| `{case_id}` | [{markdown_path.name}]({markdown_path.name}) | [{json_path.name}]({json_path.name}) |")
    (destination / "INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8", newline="\n")
    return written


def write_amendment_draft(
    case_id: str,
    output: str | Path,
    *,
    frozen_dir: str | Path = FROZEN_DIR,
) -> Path:
    provisional = load_frozen_labels(case_id, frozen_dir)
    draft = {
        "verdict": provisional.verdict,
        "first_bad_event_seq": provisional.first_bad_event_seq,
        "expected_claims": provisional.expected_claims,
        "notes": "Explain every human amendment to the provisional proposal.",
    }
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(draft, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def load_amendment(path: str | Path) -> LabelAmendment:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReviewValidationError("amendment must be a JSON object")
    try:
        return LabelAmendment.from_dict(value)
    except (KeyError, TypeError) as exc:
        raise ReviewValidationError(f"invalid amendment schema: {exc}") from exc


def _decision_hash_payload(decision: ReviewDecision) -> dict[str, Any]:
    payload = decision.to_dict()
    payload.pop("decision_sha256", None)
    return payload


def decision_sha256(decision: ReviewDecision) -> str:
    return canonical_json_sha256(_decision_hash_payload(decision))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def create_decision(
    case_id: str,
    *,
    action: str,
    reviewer_id: str,
    reviewer_name: str,
    rationale: str,
    attested: bool,
    amendment: LabelAmendment | None = None,
    supersedes_decision_sha256: str | None = None,
    reviewed_at: str | None = None,
    frozen_dir: str | Path = FROZEN_DIR,
) -> ReviewDecision:
    decision = ReviewDecision(
        schema_version=REVIEW_SCHEMA_VERSION,
        case_id=case_id,
        source=_review_source(case_id, frozen_dir=frozen_dir),
        reviewer=Reviewer(reviewer_id.strip(), reviewer_name.strip()),
        reviewed_at=reviewed_at or _utc_now(),
        action=action,
        attestation_version=ATTESTATION_VERSION,
        attested=attested,
        rationale=rationale.strip(),
        amendment=amendment,
        supersedes_decision_sha256=supersedes_decision_sha256,
    )
    decision = replace(decision, decision_sha256=decision_sha256(decision))
    problems = validate_decision(decision, frozen_dir=frozen_dir)
    if problems:
        raise ReviewValidationError("; ".join(problems))
    return decision


def _valid_utc_timestamp(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(parsed)


def _validate_amendment(amendment: LabelAmendment, ledger_seqs: set[int]) -> list[str]:
    problems: list[str] = []
    if amendment.verdict not in STATUSES:
        problems.append(f"amendment verdict is invalid: {amendment.verdict!r}")
    if not amendment.notes.strip():
        problems.append("an amendment needs non-empty notes")
    if not amendment.expected_claims:
        problems.append("an amendment needs at least one expected claim")
    statuses: list[str] = []
    contradicted_seqs: list[int] = []
    allowed_keys = {"claim_type", "status", "evidence_seqs", "note"}
    for index, claim in enumerate(amendment.expected_claims):
        if not isinstance(claim, dict):
            problems.append(f"expected_claims[{index}] must be an object")
            continue
        unknown = set(claim) - allowed_keys
        if unknown:
            problems.append(f"expected_claims[{index}] has unsupported fields: {sorted(unknown)}")
        claim_type = claim.get("claim_type")
        status = claim.get("status")
        evidence = claim.get("evidence_seqs")
        if claim_type not in ClaimType.ALL:
            problems.append(f"expected_claims[{index}].claim_type is invalid")
        if status not in STATUSES:
            problems.append(f"expected_claims[{index}].status is invalid")
        else:
            statuses.append(status)
        if not isinstance(evidence, list) or not all(
            isinstance(seq, int) and not isinstance(seq, bool) for seq in evidence
        ):
            problems.append(f"expected_claims[{index}].evidence_seqs must be a list of ints")
        else:
            missing = sorted(set(evidence) - ledger_seqs)
            if missing:
                problems.append(f"expected_claims[{index}] cites missing ledger events: {missing}")
            if status == "CONTRADICTED":
                contradicted_seqs.extend(evidence)
        if not isinstance(claim.get("note"), str) or not claim.get("note", "").strip():
            problems.append(f"expected_claims[{index}].note is required")
    if statuses and aggregate_verdict(statuses) != amendment.verdict:
        problems.append("amendment verdict does not equal the aggregate of expected claim statuses")
    if amendment.verdict == "CONTRADICTED":
        if amendment.first_bad_event_seq is None:
            problems.append("a contradicted amendment needs first_bad_event_seq")
        elif amendment.first_bad_event_seq not in ledger_seqs:
            problems.append("first_bad_event_seq does not exist in the ledger")
        elif contradicted_seqs and amendment.first_bad_event_seq != min(contradicted_seqs):
            problems.append("first_bad_event_seq must be the earliest contradicted evidence event")
    elif amendment.first_bad_event_seq is not None:
        problems.append("first_bad_event_seq must be null unless the verdict is CONTRADICTED")
    return problems


def validate_decision(
    decision: ReviewDecision,
    *,
    frozen_dir: str | Path = FROZEN_DIR,
) -> list[str]:
    """Return every trust/schema problem without mutating any file."""

    problems: list[str] = []
    if decision.schema_version != REVIEW_SCHEMA_VERSION:
        problems.append(f"unsupported review schema version {decision.schema_version}")
    if decision.action not in ReviewAction.ALL:
        problems.append(f"invalid review action {decision.action!r}")
    if not decision.reviewer.reviewer_id.strip() or not decision.reviewer.display_name.strip():
        problems.append("reviewer id and display name are required")
    if not _valid_utc_timestamp(decision.reviewed_at):
        problems.append("reviewed_at must be an ISO-8601 UTC timestamp")
    if decision.attestation_version != ATTESTATION_VERSION or decision.attested is not True:
        problems.append("the reviewer must explicitly accept the current attestation")
    if not decision.rationale.strip():
        problems.append("a case-specific review rationale is required")
    if decision.action == ReviewAction.AMEND and decision.amendment is None:
        problems.append("AMEND requires an amendment object")
    if decision.action != ReviewAction.AMEND and decision.amendment is not None:
        problems.append(f"{decision.action} must not include an amendment")
    if not _SHA256_RE.fullmatch(decision.decision_sha256):
        problems.append("decision_sha256 is missing or malformed")
    elif decision.decision_sha256 != decision_sha256(decision):
        problems.append("decision_sha256 does not match the decision contents")
    if decision.supersedes_decision_sha256 is not None and not _SHA256_RE.fullmatch(
        decision.supersedes_decision_sha256
    ):
        problems.append("supersedes_decision_sha256 is malformed")

    try:
        case = load_frozen_case(decision.case_id, frozen_dir)
        provisional = load_frozen_labels(decision.case_id, frozen_dir)
        expected_source = _review_source(decision.case_id, frozen_dir=frozen_dir)
    except (FileNotFoundError, KeyError, TypeError, ValueError, ReviewValidationError) as exc:
        problems.append(f"cannot load current frozen source: {type(exc).__name__}: {exc}")
        return problems
    if case.case_id != decision.case_id or provisional.case_id != decision.case_id:
        problems.append("decision case id does not match its frozen source")
    if provisional.verified_by_human:
        problems.append("the frozen source label must remain provisional")
    chain_valid, bad_seq = verify_chain(case.ledger)
    if not chain_valid:
        problems.append(f"frozen ledger hash chain is invalid at event #{bad_seq}")
    for field, expected in expected_source.to_dict().items():
        if getattr(decision.source, field) != expected:
            problems.append(f"source hash mismatch: {field}")
    if decision.amendment is not None:
        problems.extend(_validate_amendment(decision.amendment, {event.seq for event in case.ledger}))
    return problems


def decision_path(review_dir: str | Path, case_id: str) -> Path:
    return Path(review_dir) / DECISIONS_DIR_NAME / f"{case_id}.review.json"


def load_decision(path: str | Path) -> ReviewDecision:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise TypeError("top-level value is not an object")
        return ReviewDecision.from_dict(value)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ReviewValidationError(f"invalid review decision at {path}: {exc}") from exc


def write_decision(
    decision: ReviewDecision,
    *,
    review_dir: str | Path = REVIEW_DIR,
    frozen_dir: str | Path = FROZEN_DIR,
    replace_existing: bool = False,
) -> Path:
    problems = validate_decision(decision, frozen_dir=frozen_dir)
    if problems:
        raise ReviewValidationError("; ".join(problems))
    path = decision_path(review_dir, decision.case_id)
    if path.exists():
        previous = load_decision(path)
        if not replace_existing:
            raise FileExistsError(f"review already exists for {decision.case_id}; replacement must be explicit")
        if decision.supersedes_decision_sha256 != previous.decision_sha256:
            raise ReviewValidationError(
                "replacement must name the exact decision_sha256 it supersedes"
            )
    elif replace_existing:
        raise FileNotFoundError(f"cannot replace missing review for {decision.case_id}")
    elif decision.supersedes_decision_sha256 is not None:
        raise ReviewValidationError("a first decision cannot supersede another decision")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(decision.to_dict(), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def resolve_reviewed_truth(
    decision: ReviewDecision,
    *,
    frozen_dir: str | Path = FROZEN_DIR,
) -> GroundTruth | None:
    problems = validate_decision(decision, frozen_dir=frozen_dir)
    if problems:
        raise ReviewValidationError("; ".join(problems))
    if decision.action == ReviewAction.ABSTAIN:
        return None
    provisional = load_frozen_labels(decision.case_id, frozen_dir)
    if decision.action == ReviewAction.APPROVE:
        return GroundTruth(
            case_id=provisional.case_id,
            family_id=provisional.family_id,
            verdict=provisional.verdict,
            first_bad_event_seq=provisional.first_bad_event_seq,
            expected_claims=provisional.expected_claims,
            ledger_facts=provisional.ledger_facts,
            verified_by_human=True,
            notes=f"Human-approved provisional proposal. Review: {decision.decision_sha256}.",
        )
    amendment = decision.amendment
    assert amendment is not None
    return GroundTruth(
        case_id=provisional.case_id,
        family_id=provisional.family_id,
        verdict=amendment.verdict,
        first_bad_event_seq=amendment.first_bad_event_seq,
        expected_claims=amendment.expected_claims,
        ledger_facts=provisional.ledger_facts,
        verified_by_human=True,
        notes=f"Human-amended label: {amendment.notes} Review: {decision.decision_sha256}.",
    )


def load_reviewed_truths(
    *,
    case_ids: Iterable[str] | None = None,
    review_dir: str | Path = REVIEW_DIR,
    frozen_dir: str | Path = FROZEN_DIR,
) -> dict[str, GroundTruth]:
    truths: dict[str, GroundTruth] = {}
    for case_id in case_ids or all_case_ids():
        path = decision_path(review_dir, case_id)
        if not path.exists():
            continue
        truth = resolve_reviewed_truth(load_decision(path), frozen_dir=frozen_dir)
        if truth is not None:
            truths[case_id] = truth
    return truths


def build_review_manifest(
    *,
    expected: Sequence[str] | None = None,
    review_dir: str | Path = REVIEW_DIR,
    frozen_dir: str | Path = FROZEN_DIR,
) -> dict[str, Any]:
    expected_ids = tuple(expected) if expected is not None else all_case_ids()
    rows: list[dict[str, Any]] = []
    problems: list[str] = []
    counts = {
        "expected": len(expected_ids),
        "pending": 0,
        "reviewed": 0,
        "approved": 0,
        "amended": 0,
        "abstained": 0,
        "accepted": 0,
        "invalid": 0,
    }
    reviewers: dict[str, str] = {}
    for case_id in expected_ids:
        path = decision_path(review_dir, case_id)
        if not path.exists():
            counts["pending"] += 1
            rows.append({"case_id": case_id, "status": "PENDING"})
            continue
        try:
            decision = load_decision(path)
            decision_problems = validate_decision(decision, frozen_dir=frozen_dir)
        except ReviewValidationError as exc:
            decision = None
            decision_problems = [str(exc)]
        if decision_problems:
            counts["invalid"] += 1
            problems.extend(f"{case_id}: {problem}" for problem in decision_problems)
            rows.append({"case_id": case_id, "status": "INVALID", "problems": decision_problems})
            continue
        assert decision is not None
        counts["reviewed"] += 1
        reviewers[decision.reviewer.reviewer_id] = decision.reviewer.display_name
        if decision.action == ReviewAction.APPROVE:
            counts["approved"] += 1
            counts["accepted"] += 1
        elif decision.action == ReviewAction.AMEND:
            counts["amended"] += 1
            counts["accepted"] += 1
        else:
            counts["abstained"] += 1
        truth = resolve_reviewed_truth(decision, frozen_dir=frozen_dir)
        rows.append(
            {
                "case_id": case_id,
                "status": decision.action,
                "reviewer_id": decision.reviewer.reviewer_id,
                "reviewed_at": decision.reviewed_at,
                "decision_sha256": decision.decision_sha256,
                "resolved_label_sha256": canonical_json_sha256(truth.to_dict()) if truth else None,
            }
        )
    review_complete = counts["reviewed"] == counts["expected"] and not problems
    headline_eligible = counts["accepted"] == counts["expected"] and not problems
    manifest_path = Path(frozen_dir) / MANIFEST_NAME
    return {
        "schema_version": REVIEW_MANIFEST_SCHEMA_VERSION,
        "dataset_manifest_sha256": sha256_file(manifest_path) if manifest_path.exists() else None,
        "counts": counts,
        "reviewers": [
            {"reviewer_id": reviewer_id, "display_name": display_name}
            for reviewer_id, display_name in sorted(reviewers.items())
        ],
        "review_complete": review_complete,
        "headline_eligible": headline_eligible,
        "problems": problems,
        "cases": rows,
    }


def write_review_manifest(
    manifest: Mapping[str, Any],
    *,
    review_dir: str | Path = REVIEW_DIR,
) -> Path:
    path = Path(review_dir) / REVIEW_MANIFEST_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


__all__ = [
    "ATTESTATION_VERSION",
    "ReviewValidationError",
    "build_review_manifest",
    "build_review_material",
    "canonical_json_sha256",
    "create_decision",
    "decision_path",
    "decision_sha256",
    "load_amendment",
    "load_decision",
    "load_reviewed_truths",
    "render_review_markdown",
    "resolve_reviewed_truth",
    "review_material_for_case",
    "validate_decision",
    "write_amendment_draft",
    "write_decision",
    "write_review_manifest",
    "write_review_pack",
]
