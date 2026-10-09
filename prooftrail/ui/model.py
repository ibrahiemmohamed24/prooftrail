"""Load frozen ProofTrail artifacts into plain view models for the static UI.

Only committed files are read: no model calls, no network and no clock, so the
same inputs always render the same pages.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..benchmark_report import DEFAULT_COMPARISON_DIR
from ..config import FROZEN_DIR, REVIEW_DIR
from ..freeze import all_case_ids
from ..review import DECISIONS_DIR_NAME
from ..scenarios import FAMILIES
from ..schemas.events import LedgerEvent, verify_chain

COMPARISON_PATH = Path(DEFAULT_COMPARISON_DIR) / "comparison.verified.json"

METRICS = (
    ("family_mean_accuracy", "Family-mean accuracy"),
    ("macro_f1", "Macro-F1"),
    ("first_bad_event_hit_rate", "First-bad hit rate"),
    ("evidence_coverage", "Evidence coverage"),
)

_FAMILIES = {family.family_id: family for family in FAMILIES}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class CaseView:
    case_id: str
    family_id: str
    family_name: str
    family_summary: str
    verdict: str
    first_bad_event_seq: int | None
    explanation: str
    final_report: str
    claims: tuple[dict[str, Any], ...]
    events: tuple[dict[str, Any], ...]
    chain_valid: bool
    coverage: tuple[int, int]
    auditor_llm_calls: int
    agent_tool_calls: int
    review_action: str | None

    def events_by_seq(self) -> dict[int, dict[str, Any]]:
        return {event["seq"]: event for event in self.events}

    def cited_by(self) -> dict[int, list[str]]:
        """Claim ids that cite each ledger seq, in claim order."""
        mapping: dict[int, list[str]] = {}
        for claim in self.claims:
            for seq in claim["evidence_seqs"]:
                mapping.setdefault(seq, []).append(claim["claim_id"])
        return mapping


@dataclass(frozen=True)
class MetricRow:
    key: str
    label: str
    proof_trail: float
    b1_mean: float
    b1_stddev: float


@dataclass(frozen=True)
class Overview:
    headline_eligible: bool
    case_count: int
    family_count: int
    manifest_sha256: str
    metrics: tuple[MetricRow, ...]
    proof_trail_llm_calls: int
    review_accepted: int
    review_amended: int
    review_expected: int
    b1_run_count: int
    temporal_changed_cases: int


@dataclass(frozen=True)
class Site:
    overview: Overview
    cases: tuple[CaseView, ...]


def load_case(case_id: str, *, frozen_dir: Path = FROZEN_DIR, review_dir: Path = REVIEW_DIR) -> CaseView:
    case_dir = Path(frozen_dir) / case_id
    case = _read_json(case_dir / "case.json")
    certificate = _read_json(case_dir / "certificate.json")
    summary = _read_json(case_dir / "summary.json")
    family = _FAMILIES[case["family_id"]]
    decision_path = Path(review_dir) / DECISIONS_DIR_NAME / f"{case_id}.review.json"
    review_action = _read_json(decision_path)["action"] if decision_path.exists() else None
    coverage = certificate["evidence_coverage"]
    return CaseView(
        case_id=case_id,
        family_id=case["family_id"],
        family_name=family.name.replace("_", " "),
        family_summary=family.one_line,
        verdict=certificate["verdict"],
        first_bad_event_seq=certificate["first_bad_event_seq"],
        explanation=certificate["explanation"],
        final_report=case["trace"]["final_report"],
        claims=tuple(certificate["claims"]),
        events=tuple(sorted(case["ledger"], key=lambda event: event["seq"])),
        chain_valid=verify_chain([LedgerEvent.from_dict(event) for event in case["ledger"]])[0],
        coverage=(int(coverage["cited"]), int(coverage["total"])),
        auditor_llm_calls=int(certificate["usage"].get("llm_calls", 0)),
        agent_tool_calls=int(summary["tool_call_count"]),
        review_action=review_action,
    )


def load_overview(comparison_path: Path = COMPARISON_PATH) -> Overview:
    comparison = _read_json(Path(comparison_path))
    b1 = comparison["b1"]["metric_distribution"]
    proof_trail = comparison["prooftrail"]["metric_values"]
    review = comparison["review_manifest"]["counts"]
    dataset = comparison["dataset"]
    return Overview(
        headline_eligible=bool(comparison["headline_eligible"]),
        case_count=int(dataset["case_count"]),
        family_count=int(dataset["family_count"]),
        manifest_sha256=str(dataset["manifest_sha256"]),
        metrics=tuple(
            MetricRow(key, label, float(proof_trail[key]), float(b1[key]["mean"]), float(b1[key]["stddev"]))
            for key, label in METRICS
        ),
        proof_trail_llm_calls=int(comparison["prooftrail"]["usage"]["llm_calls"]),
        review_accepted=int(review["accepted"]),
        review_amended=int(review["amended"]),
        review_expected=int(review["expected"]),
        b1_run_count=int(comparison["b1"]["run_count"]),
        temporal_changed_cases=len(comparison["ablations"]["changed_cases_without_temporal"]),
    )


def load_site(
    *,
    frozen_dir: Path = FROZEN_DIR,
    review_dir: Path = REVIEW_DIR,
    comparison_path: Path = COMPARISON_PATH,
) -> Site:
    cases = tuple(load_case(case_id, frozen_dir=frozen_dir, review_dir=review_dir) for case_id in all_case_ids())
    return Site(overview=load_overview(comparison_path), cases=cases)
