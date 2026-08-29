"""Command-line entry point for the offline ProofTrail milestone."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .config import EVIDENCE_DIR
from .demo import run_killer_demo, write_demo_artifacts
from .eval.metrics import evaluate_outputs
from .eval.report import write_metrics_report
from .eval.runner import write_outputs
from .scenarios import FAMILIES


DEFAULT_DEMO_DIR = EVIDENCE_DIR / "demo-f02"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prooftrail",
        description="Audit an agent's action claims against independent ledger evidence.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    demo = commands.add_parser("demo", help="run the offline $47 -> $94 killer case")
    demo.add_argument("--seed", type=int, default=0)
    demo.add_argument("--output", type=Path, default=DEFAULT_DEMO_DIR)
    demo.add_argument("--json", action="store_true", help="print only the JSON summary")

    cases = commands.add_parser("cases", help="list the ten scenario families")
    cases.add_argument("--json", action="store_true")

    evaluate = commands.add_parser("eval-demo", help="score the provisional offline demo")
    evaluate.add_argument("--seed", type=int, default=0)
    evaluate.add_argument("--output", type=Path, default=DEFAULT_DEMO_DIR)
    return parser


def _demo(args: argparse.Namespace) -> int:
    run = run_killer_demo(seed=args.seed)
    paths = write_demo_artifacts(run, args.output)
    summary = run.summary()
    if args.json:
        print(json.dumps(summary, sort_keys=True))
        return 0

    print("ProofTrail killer demo: complete")
    print(f"Agent claimed : {summary['agent_claim']}")
    print(
        "Ledger proved : "
        f"{summary['actual_refund_count']} commits, "
        f"${summary['actual_refunded_cents'] / 100:.2f} refunded"
    )
    print(f"Verdict       : {summary['verdict']}")
    print(f"First bad     : ledger event #{summary['first_bad_event_seq']}")
    print(f"Hash chain    : {'valid' if summary['ledger_chain_valid'] else 'INVALID'}")
    print(f"Certificate   : {paths['certificate_markdown'].resolve()}")
    print("Mode          : scripted offline fixture; real-LLM dataset is still pending")
    return 0


def _cases(args: argparse.Namespace) -> int:
    rows = [
        {
            "family_id": family.family_id,
            "name": family.name,
            "difficulty": family.difficulty,
            "expected_verdict": family.expected_verdict,
            "one_line": family.one_line,
        }
        for family in FAMILIES
    ]
    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
    else:
        for row in rows:
            print(
                f"{row['family_id']}  {row['name']:<38} "
                f"{row['difficulty']:<6}  {row['expected_verdict']}"
            )
    return 0


def _eval_demo(args: argparse.Namespace) -> int:
    run = run_killer_demo(seed=args.seed)
    write_demo_artifacts(run, args.output)
    outputs = {run.case.case_id: run.audit}
    truths = {run.case.case_id: run.ground_truth}
    metrics = evaluate_outputs(outputs, truths, include_unverified=True)
    write_outputs(args.output / "outputs.json", outputs)
    json_path, markdown_path = write_metrics_report(
        args.output,
        metrics,
        title="ProofTrail provisional offline demo",
    )
    print("Provisional demo evaluation complete (not a headline benchmark).")
    print(f"Family-mean accuracy : {metrics['family_mean_accuracy'] * 100:.1f}%")
    print(f"First-bad-event hit  : {metrics['first_bad_event']['hit_rate'] * 100:.1f}%")
    print(f"Metrics JSON         : {json_path.resolve()}")
    print(f"Report               : {markdown_path.resolve()}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "demo":
        return _demo(args)
    if args.command == "cases":
        return _cases(args)
    if args.command == "eval-demo":
        return _eval_demo(args)
    raise AssertionError(f"unhandled command {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
