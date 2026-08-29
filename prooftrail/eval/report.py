"""Human-readable rendering of deterministic evaluation metrics."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def _pct(value: object) -> str:
    return f"{float(value) * 100:.1f}%"


def render_metrics_markdown(metrics: Mapping[str, Any], *, title: str = "ProofTrail evaluation") -> str:
    first_bad = metrics["first_bad_event"]
    coverage = metrics["evidence_coverage"]
    lines = [
        f"# {title}",
        "",
        f"Cases scored: **{metrics['case_count']}**",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Family-mean accuracy | {_pct(metrics['family_mean_accuracy'])} |",
        f"| Overall accuracy | {_pct(metrics['overall_accuracy'])} |",
        f"| Macro-F1 | {_pct(metrics['macro_f1'])} |",
        f"| First-bad-event hit rate | {_pct(first_bad['hit_rate'])} ({first_bad['hits']}/{first_bad['eligible']}) |",
        f"| Evidence coverage | {_pct(coverage['rate'])} ({coverage['cited']}/{coverage['total']}) |",
        "",
        "## By scenario family",
        "",
        "| Family | Accuracy | Correct | Total |",
        "|---|---:|---:|---:|",
    ]
    for family_id, row in metrics["per_family"].items():
        lines.append(
            f"| {family_id} | {_pct(row['accuracy'])} | {row['correct']} | {row['total']} |"
        )
    lines.extend([
        "",
        "> Provisional runs may include labels that have not yet been human-verified. "
        "The JSON field `verified_only` states which mode produced this report.",
        "",
    ])
    return "\n".join(lines)


def write_metrics_report(
    output_dir: str | Path,
    metrics: Mapping[str, Any],
    *,
    title: str = "ProofTrail evaluation",
) -> tuple[Path, Path]:
    """Write machine-readable and review-friendly versions atomically enough for CLI use."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "metrics.json"
    markdown_path = directory / "report.md"
    json_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    markdown_path.write_text(render_metrics_markdown(metrics, title=title), encoding="utf-8", newline="\n")
    return json_path, markdown_path
