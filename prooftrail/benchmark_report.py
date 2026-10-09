"""Deterministic comparison of repeated B1 runs and ProofTrail ablations.

The report is deliberately separate from the label-blind benchmark runner.
Auditors produce and freeze outputs first; only this offline step may load
ground truth.  Provisional labels require an explicit opt-in and can never
produce a headline-eligible report.
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any, Mapping, Sequence

from .auditor import ProofTrailPipeline
from .benchmark import B1BenchmarkRun, MODE_REPLAY, default_b1_output_dir
from .config import BENCHMARK_DIR, FROZEN_DIR, REVIEW_DIR
from .eval.metrics import evaluate_outputs
from .eval.spec import BenchmarkSpec, build_b1_spec
from .freeze import (
    MANIFEST_NAME,
    all_case_ids,
    load_frozen_case,
    load_frozen_labels,
    sha256_file,
)
from .review import build_review_manifest, load_reviewed_truths
from .schemas import AuditOutput, GroundTruth


REPORT_SCHEMA_VERSION = 1
DEFAULT_COMPARISON_DIR = BENCHMARK_DIR / "comparison"
METRIC_KEYS = (
    "family_mean_accuracy",
    "overall_accuracy",
    "macro_f1",
    "first_bad_event_hit_rate",
    "evidence_coverage",
)


class BenchmarkReportError(ValueError):
    """A comparison artifact is missing, stale, malformed or not eligible."""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BenchmarkReportError(f"required benchmark artifact is missing: {path}") from None
    except json.JSONDecodeError as exc:
        raise BenchmarkReportError(f"benchmark artifact is not valid JSON: {path}: {exc}") from None


def _load_outputs(path: Path, *, expected_auditor: str) -> dict[str, AuditOutput]:
    raw = _load_json(path)
    if not isinstance(raw, dict):
        raise BenchmarkReportError(f"outputs artifact must be an object: {path}")
    outputs: dict[str, AuditOutput] = {}
    for case_id, value in raw.items():
        if not isinstance(case_id, str) or not isinstance(value, dict):
            raise BenchmarkReportError(f"malformed output entry in {path}")
        try:
            output = AuditOutput.from_dict(value)
        except (TypeError, ValueError) as exc:
            raise BenchmarkReportError(f"invalid AuditOutput for {case_id}: {exc}") from None
        if output.case_id != case_id:
            raise BenchmarkReportError(
                f"output key {case_id!r} does not match payload case_id {output.case_id!r}"
            )
        if output.auditor != expected_auditor:
            raise BenchmarkReportError(
                f"{case_id} was produced by {output.auditor!r}, expected {expected_auditor!r}"
            )
        outputs[case_id] = output
    return outputs


def _validate_b1_artifacts(
    spec: BenchmarkSpec,
    *,
    case_ids: Sequence[str],
    benchmark_dir: str | Path,
) -> tuple[dict[str, AuditOutput], dict[str, Any]]:
    directory = default_b1_output_dir(spec, benchmark_dir)
    paths = {
        "spec": directory / "spec.json",
        "outputs": directory / "outputs.json",
        "failures": directory / "failures.json",
        "summary": directory / "summary.json",
    }
    stored_spec = _load_json(paths["spec"])
    if stored_spec != spec.to_dict():
        raise BenchmarkReportError(
            f"B1 run {spec.run_index} spec is stale or does not match its path"
        )
    failures = _load_json(paths["failures"])
    if failures != []:
        raise BenchmarkReportError(
            f"B1 run {spec.run_index} still contains {len(failures) if isinstance(failures, list) else 'unknown'} failure(s)"
        )
    outputs = _load_outputs(paths["outputs"], expected_auditor="B1")
    expected = set(case_ids)
    actual = set(outputs)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise BenchmarkReportError(
            f"B1 run {spec.run_index} case inventory mismatch; missing={missing}, extra={extra}"
        )
    summary = _load_json(paths["summary"])
    if not isinstance(summary, dict):
        raise BenchmarkReportError(f"B1 run {spec.run_index} summary must be an object")
    recomputed = B1BenchmarkRun(
        spec=spec,
        mode=MODE_REPLAY,
        requested_case_ids=tuple(case_ids),
        outputs=outputs,
        failures=[],
        cache_hits=0,
        cache_misses=0,
    ).summary()
    for key in (
        "auditor",
        "provider",
        "model",
        "run_index",
        "spec_sha256",
        "requested_cases",
        "completed_cases",
        "failure_count",
        "complete",
        "verdicts",
        "usage",
    ):
        if summary.get(key) != recomputed[key]:
            raise BenchmarkReportError(
                f"B1 run {spec.run_index} summary field {key!r} does not match outputs"
            )
    benchmark_root = Path(benchmark_dir).resolve()
    try:
        portable_directory = directory.resolve().relative_to(benchmark_root)
    except ValueError:
        raise BenchmarkReportError(
            f"B1 run {spec.run_index} artifacts escape benchmark_dir"
        ) from None
    metadata = {
        "run_index": spec.run_index,
        "spec_sha256": spec.sha256,
        "artifact_dir": portable_directory.as_posix(),
        "artifact_sha256": {name: sha256_file(path) for name, path in paths.items()},
        "summary": summary,
    }
    return outputs, metadata


def _metric_values(metrics: Mapping[str, Any]) -> dict[str, float]:
    return {
        "family_mean_accuracy": float(metrics["family_mean_accuracy"]),
        "overall_accuracy": float(metrics["overall_accuracy"]),
        "macro_f1": float(metrics["macro_f1"]),
        "first_bad_event_hit_rate": float(metrics["first_bad_event"]["hit_rate"]),
        "evidence_coverage": float(metrics["evidence_coverage"]["rate"]),
    }


def _stats(values: Sequence[float]) -> dict[str, float]:
    if not values:
        raise BenchmarkReportError("cannot aggregate an empty metric series")
    return {
        "mean": round(fmean(values), 9),
        "stddev": round(pstdev(values), 9) if len(values) > 1 else 0.0,
        "min": round(min(values), 9),
        "max": round(max(values), 9),
    }


def _verdict_counts(outputs: Mapping[str, AuditOutput]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for output in outputs.values():
        counts[output.verdict] = counts.get(output.verdict, 0) + 1
    return dict(sorted(counts.items()))


def _usage_totals(outputs: Mapping[str, AuditOutput]) -> dict[str, float | int]:
    result: dict[str, float | int] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "llm_calls": 0,
    }
    for output in outputs.values():
        result["input_tokens"] = int(result["input_tokens"]) + int(
            output.usage.get("input_tokens", 0)
        )
        result["output_tokens"] = int(result["output_tokens"]) + int(
            output.usage.get("output_tokens", 0)
        )
        result["llm_calls"] = int(result["llm_calls"]) + int(
            output.usage.get("llm_calls", 0)
        )
        result["cost_usd"] = round(
            float(result["cost_usd"]) + float(output.usage.get("cost_usd", 0.0)),
            9,
        )
    return result


def build_comparison_report(
    *,
    b1_runs: Mapping[int, Mapping[str, AuditOutput]],
    b1_metadata: Mapping[int, Mapping[str, Any]],
    prooftrail_outputs: Mapping[str, AuditOutput],
    no_temporal_outputs: Mapping[str, AuditOutput],
    truths: Mapping[str, GroundTruth],
    label_mode: str,
    dataset_manifest_sha256: str,
    review_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one deterministic report from already-frozen auditor outputs."""

    if label_mode not in {"provisional", "verified"}:
        raise BenchmarkReportError("label_mode must be 'provisional' or 'verified'")
    case_ids = tuple(sorted(truths))
    if not case_ids:
        raise BenchmarkReportError("comparison requires at least one ground-truth case")
    expected = set(case_ids)
    if len(b1_runs) != 3:
        raise BenchmarkReportError("the published comparison requires exactly three B1 runs")
    if set(b1_runs) != set(b1_metadata):
        raise BenchmarkReportError("B1 outputs and metadata have different run indices")
    for run_index, outputs in b1_runs.items():
        if set(outputs) != expected:
            raise BenchmarkReportError(f"B1 run {run_index} does not cover the truth inventory")
    if set(prooftrail_outputs) != expected or set(no_temporal_outputs) != expected:
        raise BenchmarkReportError("ProofTrail or its ablation does not cover the truth inventory")

    all_verified = all(truth.verified_by_human for truth in truths.values())
    if label_mode == "verified" and not all_verified:
        raise BenchmarkReportError("verified mode received one or more provisional labels")
    include_unverified = label_mode == "provisional"
    headline_eligible = label_mode == "verified" and all_verified

    b1_metric_rows: dict[int, dict[str, Any]] = {}
    b1_run_rows: list[dict[str, Any]] = []
    for run_index in sorted(b1_runs):
        outputs = b1_runs[run_index]
        metrics = evaluate_outputs(
            outputs,
            truths,
            include_unverified=include_unverified,
        )
        b1_metric_rows[run_index] = metrics
        metadata = dict(b1_metadata[run_index])
        metadata["metrics"] = metrics
        metadata["verdicts"] = _verdict_counts(outputs)
        b1_run_rows.append(metadata)

    full_metrics = evaluate_outputs(
        prooftrail_outputs,
        truths,
        include_unverified=include_unverified,
    )
    no_temporal_metrics = evaluate_outputs(
        no_temporal_outputs,
        truths,
        include_unverified=include_unverified,
    )
    b1_metric_stats = {
        key: _stats([_metric_values(row)[key] for row in b1_metric_rows.values()])
        for key in METRIC_KEYS
    }
    full_values = _metric_values(full_metrics)
    no_temporal_values = _metric_values(no_temporal_metrics)
    deltas = {
        key: round(full_values[key] - b1_metric_stats[key]["mean"], 9)
        for key in METRIC_KEYS
    }

    run_indices = sorted(b1_runs)
    variable_cases: list[dict[str, Any]] = []
    unanimous = 0
    for case_id in case_ids:
        verdicts = {
            str(run_index): b1_runs[run_index][case_id].verdict
            for run_index in run_indices
        }
        unique = sorted(set(verdicts.values()))
        if len(unique) == 1:
            unanimous += 1
        else:
            variable_cases.append(
                {
                    "case_id": case_id,
                    "verdicts": verdicts,
                    "unique_verdicts": unique,
                }
            )

    always_wrong: list[str] = []
    sometimes_wrong: list[str] = []
    for case_id in case_ids:
        wrong = sum(
            b1_runs[run_index][case_id].verdict != truths[case_id].verdict
            for run_index in run_indices
        )
        if wrong == len(run_indices):
            always_wrong.append(case_id)
        elif wrong:
            sometimes_wrong.append(case_id)

    full_wrong = [
        case_id
        for case_id in case_ids
        if prooftrail_outputs[case_id].verdict != truths[case_id].verdict
    ]
    ablation_changes = [
        {
            "case_id": case_id,
            "full_verdict": prooftrail_outputs[case_id].verdict,
            "without_temporal_verdict": no_temporal_outputs[case_id].verdict,
            "full_first_bad_event_seq": prooftrail_outputs[case_id].first_bad_event_seq,
            "without_temporal_first_bad_event_seq": no_temporal_outputs[
                case_id
            ].first_bad_event_seq,
        }
        for case_id in case_ids
        if (
            prooftrail_outputs[case_id].verdict
            != no_temporal_outputs[case_id].verdict
            or prooftrail_outputs[case_id].first_bad_event_seq
            != no_temporal_outputs[case_id].first_bad_event_seq
        )
    ]

    total_b1_usage = {
        "accepted_llm_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "billed_cost_usd": 0.0,
        "list_price_equivalent_usd": 0.0,
    }
    for row in b1_run_rows:
        usage = row["summary"]["usage"]
        total_b1_usage["accepted_llm_calls"] += int(usage["llm_calls"])
        total_b1_usage["input_tokens"] += int(usage["input_tokens"])
        total_b1_usage["output_tokens"] += int(usage["output_tokens"])
        total_b1_usage["billed_cost_usd"] += float(usage["cost_usd"])
        total_b1_usage["list_price_equivalent_usd"] += float(
            usage["list_price_equivalent_usd"]
        )
    total_b1_usage["billed_cost_usd"] = round(
        total_b1_usage["billed_cost_usd"], 9
    )
    total_b1_usage["list_price_equivalent_usd"] = round(
        total_b1_usage["list_price_equivalent_usd"], 9
    )
    total_predictions = len(case_ids) * len(run_indices)
    total_b1_usage["billed_cost_usd_per_prediction"] = round(
        total_b1_usage["billed_cost_usd"] / total_predictions, 9
    )
    total_b1_usage["list_price_equivalent_usd_per_prediction"] = round(
        total_b1_usage["list_price_equivalent_usd"] / total_predictions, 9
    )

    warning = (
        "PROVISIONAL DIAGNOSTIC ONLY: labels are ledger-derived and have not "
        "been approved by a human reviewer; no metric in this file is headline eligible."
        if not headline_eligible
        else "HUMAN-VERIFIED: all included labels passed the source-bound review workflow."
    )
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "label_mode": label_mode,
        "headline_eligible": headline_eligible,
        "warning": warning,
        "dataset": {
            "case_count": len(case_ids),
            "family_count": len({truth.family_id for truth in truths.values()}),
            "manifest_sha256": dataset_manifest_sha256,
        },
        "review_manifest": dict(review_manifest) if review_manifest is not None else None,
        "b1": {
            "run_count": len(run_indices),
            "runs": b1_run_rows,
            "metric_distribution": b1_metric_stats,
            "stability": {
                "unanimous_cases": unanimous,
                "case_count": len(case_ids),
                "unanimous_rate": round(unanimous / len(case_ids), 9),
                "variable_cases": variable_cases,
            },
            "usage": total_b1_usage,
        },
        "prooftrail": {
            "metrics": full_metrics,
            "metric_values": full_values,
            "verdicts": _verdict_counts(prooftrail_outputs),
            "usage": _usage_totals(prooftrail_outputs),
        },
        "ablations": {
            "all_llm_same_evidence": {
                "description": "B1 one-shot LLM over the same frozen trace and raw ledger.",
                "metric_distribution": b1_metric_stats,
            },
            "prooftrail_without_temporal_verifier": {
                "description": "Deterministic extraction, linking and state reconciliation with temporal/intent issues disabled.",
                "metrics": no_temporal_metrics,
                "metric_values": no_temporal_values,
                "verdicts": _verdict_counts(no_temporal_outputs),
                "usage": _usage_totals(no_temporal_outputs),
            },
            "prooftrail_full": {
                "description": "Deterministic extraction, evidence linking, state reconciliation and temporal/intent verification.",
                "metrics": full_metrics,
                "metric_values": full_values,
                "verdicts": _verdict_counts(prooftrail_outputs),
                "usage": _usage_totals(prooftrail_outputs),
            },
            "changed_cases_without_temporal": ablation_changes,
        },
        "comparison": {
            "prooftrail_minus_b1_mean": deltas,
        },
        "failure_analysis": {
            "b1_always_wrong_case_ids": always_wrong,
            "b1_sometimes_wrong_case_ids": sometimes_wrong,
            "prooftrail_wrong_case_ids": full_wrong,
        },
    }


def build_comparison_report_from_disk(
    *,
    provider: str,
    model: str,
    run_indices: Sequence[int] = (0, 1, 2),
    allow_provisional: bool = False,
    frozen_dir: str | Path = FROZEN_DIR,
    review_dir: str | Path = REVIEW_DIR,
    benchmark_dir: str | Path = BENCHMARK_DIR,
) -> dict[str, Any]:
    """Validate committed artifacts, then score them without network access."""

    run_indices = tuple(run_indices)
    if len(run_indices) != 3 or len(set(run_indices)) != 3:
        raise BenchmarkReportError("exactly three distinct run indices are required")
    case_ids = all_case_ids()
    manifest_path = Path(frozen_dir) / MANIFEST_NAME
    if not manifest_path.exists():
        raise BenchmarkReportError(f"frozen dataset manifest is missing: {manifest_path}")
    manifest_sha256 = sha256_file(manifest_path)

    review_manifest = build_review_manifest(
        expected=case_ids,
        review_dir=review_dir,
        frozen_dir=frozen_dir,
    )
    if allow_provisional:
        label_mode = "provisional"
        truths = {
            case_id: load_frozen_labels(case_id, frozen_dir)
            for case_id in case_ids
        }
        if any(truth.verified_by_human for truth in truths.values()):
            raise BenchmarkReportError(
                "immutable frozen labels must remain provisional; reviewed truth belongs in data/reviews"
            )
    else:
        label_mode = "verified"
        if not review_manifest["headline_eligible"]:
            counts = review_manifest["counts"]
            raise BenchmarkReportError(
                "human-reviewed truth is not headline eligible: "
                f"{counts['accepted']}/{counts['expected']} accepted, "
                f"{counts['pending']} pending, {counts['abstained']} abstained, "
                f"{counts['invalid']} invalid; pass --allow-provisional only for a diagnostic report"
            )
        truths = load_reviewed_truths(
            case_ids=case_ids,
            review_dir=review_dir,
            frozen_dir=frozen_dir,
        )

    b1_runs: dict[int, dict[str, AuditOutput]] = {}
    b1_metadata: dict[int, dict[str, Any]] = {}
    for run_index in sorted(run_indices):
        spec = build_b1_spec(
            provider=provider,
            model=model,
            run_index=run_index,
            frozen_dir=frozen_dir,
        )
        outputs, metadata = _validate_b1_artifacts(
            spec,
            case_ids=case_ids,
            benchmark_dir=benchmark_dir,
        )
        b1_runs[run_index] = outputs
        b1_metadata[run_index] = metadata

    cases = [load_frozen_case(case_id, frozen_dir) for case_id in case_ids]
    full = ProofTrailPipeline()
    no_temporal = ProofTrailPipeline(use_temporal_verifier=False)
    prooftrail_outputs = {case.case_id: full.audit(case) for case in cases}
    no_temporal_outputs = {
        case.case_id: no_temporal.audit(case) for case in cases
    }
    return build_comparison_report(
        b1_runs=b1_runs,
        b1_metadata=b1_metadata,
        prooftrail_outputs=prooftrail_outputs,
        no_temporal_outputs=no_temporal_outputs,
        truths=truths,
        label_mode=label_mode,
        dataset_manifest_sha256=manifest_sha256,
        review_manifest=review_manifest,
    )


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _metric_cell(values: Mapping[str, float]) -> str:
    return f"{_pct(values['mean'])} ± {_pct(values['stddev'])}"


def render_comparison_markdown(report: Mapping[str, Any]) -> str:
    """Render a compact, judge-readable comparison with an honesty banner."""

    headline = bool(report["headline_eligible"])
    title = (
        "ProofTrail verified benchmark"
        if headline
        else "ProofTrail provisional benchmark diagnostic"
    )
    b1 = report["b1"]
    pt = report["prooftrail"]
    no_temporal = report["ablations"]["prooftrail_without_temporal_verifier"]
    distributions = b1["metric_distribution"]
    lines = [
        f"# {title}",
        "",
        f"> **{report['warning']}**",
        "",
        f"- Dataset: **{report['dataset']['case_count']} cases / {report['dataset']['family_count']} families**",
        f"- B1 repeats: **{b1['run_count']}**",
        f"- Headline eligible: **{'yes' if headline else 'no'}**",
        "",
        "## Outcome",
        "",
        "| Auditor / ablation | Family-mean accuracy | Overall accuracy | Macro-F1 | First-bad hit rate | Evidence coverage |",
        "|---|---:|---:|---:|---:|---:|",
        "| B1 all-LLM (3-run mean ± population SD) | "
        + " | ".join(
            _metric_cell(distributions[key])
            for key in METRIC_KEYS
        )
        + " |",
        "| ProofTrail without temporal verifier | "
        + " | ".join(
            _pct(float(no_temporal["metric_values"][key]))
            for key in METRIC_KEYS
        )
        + " |",
        "| ProofTrail full | "
        + " | ".join(
            _pct(float(pt["metric_values"][key]))
            for key in METRIC_KEYS
        )
        + " |",
        "",
        "## Cost and repeat stability",
        "",
        f"- Accepted B1 completions: **{b1['usage']['accepted_llm_calls']}** "
        f"({b1['usage']['input_tokens']:,} input / {b1['usage']['output_tokens']:,} output tokens).",
        f"- Billed Free Tier cost: **${b1['usage']['billed_cost_usd']:.2f}**; "
        f"list-price equivalent: **${b1['usage']['list_price_equivalent_usd']:.4f}** "
        f"(**${b1['usage']['list_price_equivalent_usd_per_prediction']:.6f} per prediction**).",
        f"- B1 verdict unanimity: **{_pct(float(b1['stability']['unanimous_rate']))}** "
        f"({b1['stability']['unanimous_cases']}/{b1['stability']['case_count']} cases).",
        f"- ProofTrail model calls and billed cost: **{pt['usage']['llm_calls']} / ${pt['usage']['cost_usd']:.2f}**.",
        "",
        "## Failure analysis",
        "",
        f"- B1 wrong in all three runs: **{len(report['failure_analysis']['b1_always_wrong_case_ids'])}** case(s): "
        + (", ".join(report["failure_analysis"]["b1_always_wrong_case_ids"]) or "none")
        + ".",
        f"- B1 changed verdict across repeats: **{len(b1['stability']['variable_cases'])}** case(s): "
        + (
            ", ".join(row["case_id"] for row in b1["stability"]["variable_cases"])
            or "none"
        )
        + ".",
        f"- ProofTrail verdict differs from the selected truth source: **{len(report['failure_analysis']['prooftrail_wrong_case_ids'])}** case(s): "
        + (", ".join(report["failure_analysis"]["prooftrail_wrong_case_ids"]) or "none")
        + ".",
        f"- Removing temporal verification changed verdict or first-bad localization in "
        f"**{len(report['ablations']['changed_cases_without_temporal'])}** case(s).",
        "",
        "## Reproducibility boundary",
        "",
        "Every B1 run row in the JSON report carries its spec hash plus hashes of "
        "the exact spec, outputs, failures and summary artifacts. The report command "
        "performs no network calls. Re-running it without `--allow-provisional` "
        "fails closed until all 40 source-bound human decisions are accepted.",
        "",
    ]
    return "\n".join(lines)


def write_comparison_report(
    report: Mapping[str, Any],
    output_dir: str | Path = DEFAULT_COMPARISON_DIR,
) -> dict[str, Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    suffix = "verified" if report["headline_eligible"] else "provisional"
    paths = {
        "json": directory / f"comparison.{suffix}.json",
        "markdown": directory / f"comparison.{suffix}.md",
    }
    paths["json"].write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    paths["markdown"].write_text(
        render_comparison_markdown(report),
        encoding="utf-8",
        newline="\n",
    )
    return paths


__all__ = [
    "BenchmarkReportError",
    "DEFAULT_COMPARISON_DIR",
    "REPORT_SCHEMA_VERSION",
    "build_comparison_report",
    "build_comparison_report_from_disk",
    "render_comparison_markdown",
    "write_comparison_report",
]
