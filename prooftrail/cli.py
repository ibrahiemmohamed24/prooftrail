"""Command-line entry point for ProofTrail."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from .agent.anthropic_client import AnthropicModelClient, MissingApiKeyError
from .agent.budget import BudgetExceededError, BudgetGuard
from .agent.cache import CachingModelClient, ReplayCache, ReplayCacheMiss
from .agent.gemini_client import (
    DEFAULT_GEMINI_MODEL,
    FreeTierConfirmationError,
    GeminiModelClient,
    GeminiResponseError,
    GeminiTransportError,
    MissingGeminiApiKeyError,
)
from .agent.runner import MODE_LIVE, MODE_REPLAY, run_case, write_case_artifacts
from .config import EVIDENCE_DIR, MODEL, REPLAY_DIR
from .demo import run_killer_demo, write_demo_artifacts
from .eval.metrics import evaluate_outputs
from .eval.report import write_metrics_report
from .eval.runner import write_outputs
from .ids import case_id as make_case_id
from .scenarios import FAMILIES, FAMILY_IDS


DEFAULT_DEMO_DIR = EVIDENCE_DIR / "demo-f02"
DEFAULT_LIVE_DIR = EVIDENCE_DIR / "live"
PROVIDERS = ("anthropic", "gemini")
DEFAULT_PROVIDER = os.environ.get("PROOFTRAIL_PROVIDER", "anthropic")


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

    agent = commands.add_parser("agent", help="run the refund agent with a real or replayed model")
    agent_commands = agent.add_subparsers(dest="agent_command", required=True)
    run = agent_commands.add_parser(
        "run",
        help="run one family x seed; --live calls the provider, --replay needs no key",
    )
    mode = run.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true", help="call the selected real provider and record the replay cache")
    mode.add_argument("--replay", action="store_true", help="serve recorded responses; no network, no API key")
    run.add_argument(
        "--provider",
        choices=PROVIDERS,
        default=DEFAULT_PROVIDER if DEFAULT_PROVIDER in PROVIDERS else "anthropic",
        help="live provider and replay namespace (gemini supports a no-billing free tier)",
    )
    run.add_argument("--family", required=True, choices=FAMILY_IDS)
    run.add_argument("--seed", type=int, default=0)
    run.add_argument(
        "--model",
        default=None,
        help=f"override the provider model (Anthropic default: {MODEL}; Gemini default: {DEFAULT_GEMINI_MODEL})",
    )
    run.add_argument("--budget-usd", type=float, default=None, help="override PROOFTRAIL_BUDGET_USD")
    run.add_argument("--cache-dir", type=Path, default=REPLAY_DIR, help="replay cache directory")
    run.add_argument("--output", type=Path, default=None, help="evidence directory (default evidence/runs/live/<case>)")
    run.add_argument("--fresh", action="store_true", help="discard this case's replay cache before a live run")
    run.add_argument("--json", action="store_true", help="print only the JSON summary")
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


def build_live_client(*, model: str | None, budget: BudgetGuard, label: str) -> AnthropicModelClient:
    """Factory for the real provider; tests replace it with a fake-backed client."""

    return AnthropicModelClient(model=model, budget=budget, label=label)


def build_gemini_client(*, model: str | None, label: str) -> GeminiModelClient:
    """Factory for the real free-tier provider; tests replace its transport."""

    return GeminiModelClient(model=model or DEFAULT_GEMINI_MODEL, label=label)


def replay_cache_path(cache_dir: Path, case_id: str) -> Path:
    return Path(cache_dir) / f"{case_id}.json"


def _agent_run(args: argparse.Namespace) -> int:
    case_id = make_case_id(args.family, args.seed)
    cache_root = Path(args.cache_dir)
    if cache_root.resolve() == REPLAY_DIR.resolve() and args.provider == "gemini":
        cache_root = cache_root / "gemini"
    cache = ReplayCache(replay_cache_path(cache_root, case_id))
    output_dir = args.output or (
        DEFAULT_LIVE_DIR / "gemini" / case_id
        if args.provider == "gemini"
        else DEFAULT_LIVE_DIR / case_id
    )

    if args.live and args.provider == "gemini" and args.budget_usd is not None:
        print("error: --budget-usd is for paid providers; Gemini free tier bills $0", file=sys.stderr)
        return 7

    try:
        if args.live:
            if args.fresh:
                cache.clear()
            if args.provider == "gemini":
                budget = None
                inner = build_gemini_client(model=args.model, label=case_id)
            else:
                budget = BudgetGuard.from_env(
                    limit_usd=args.budget_usd,
                    ledger_path=cache_root / "cost_ledger.jsonl",
                )
                inner = build_live_client(model=args.model, budget=budget, label=case_id)
            client = CachingModelClient(cache, inner)
            mode = MODE_LIVE
        else:
            replay_model = args.model
            if replay_model is None and args.provider == "gemini" and not cache.path.exists():
                replay_model = DEFAULT_GEMINI_MODEL
            client = CachingModelClient(cache, None, model_name=replay_model)
            mode = MODE_REPLAY
        run = run_case(args.family, args.seed, model_client=client, mode=mode)
    except MissingApiKeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except BudgetExceededError as exc:
        print(f"error: budget guard stopped the run: {exc}", file=sys.stderr)
        return 3
    except ReplayCacheMiss as exc:
        print(f"error: replay cache miss: {exc}", file=sys.stderr)
        return 4
    except (MissingGeminiApiKeyError, FreeTierConfirmationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 5
    except (GeminiTransportError, GeminiResponseError) as exc:
        print(f"error: Gemini provider failed: {exc}", file=sys.stderr)
        return 6

    paths = write_case_artifacts(run, output_dir)
    summary = run.summary()
    summary["replay_cache"] = str(cache.path)
    summary["cache_hits"] = client.hits
    summary["cache_misses"] = client.misses
    summary["provider"] = args.provider
    if args.live and budget is not None:
        summary["budget_spent_usd"] = budget.spent_usd
        summary["budget_limit_usd"] = budget.limit_usd
    if args.live and args.provider == "gemini":
        summary["pricing_tier"] = "free"
        summary["billed_cost_usd"] = 0.0
    if args.json:
        print(json.dumps(summary, sort_keys=True))
        return 0

    usage = summary["usage"]
    print(f"ProofTrail agent run: {case_id} ({summary['mode']})")
    print(f"Model         : {summary['model']}")
    print(f"Agent claimed : {summary['agent_claim']}")
    print(
        "Ledger proved : "
        f"{summary['actual_refund_count']} commits, "
        f"${summary['actual_refunded_cents'] / 100:.2f} refunded on the primary order"
    )
    print(f"Verdict       : {summary['verdict']}")
    print(f"First bad     : {summary['first_bad_event_seq']}")
    print(f"Hash chain    : {'valid' if summary['ledger_chain_valid'] else 'INVALID'}")
    print(f"Tool calls    : {summary['tool_call_count']}   stop reason: {summary['stop_reason']}")
    print(
        f"Usage         : {usage['llm_calls']} calls, {usage['input_tokens']} in / "
        f"{usage['output_tokens']} out tokens, ${usage['cost_usd']:.4f}"
    )
    print(f"Replay cache  : {cache.path} ({client.hits} hits, {client.misses} misses)")
    if args.live and budget is not None:
        print(f"Budget        : ${budget.spent_usd:.4f} of ${budget.limit_usd:.2f} spent (all runs)")
    if args.live and args.provider == "gemini":
        print("Billing       : Gemini Free Tier confirmed; billed cost $0.00")
    print(f"Certificate   : {paths['certificate_markdown'].resolve()}")
    print(f"Labels        : provisional, verified_by_human={summary['labels_human_verified']}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "demo":
        return _demo(args)
    if args.command == "cases":
        return _cases(args)
    if args.command == "eval-demo":
        return _eval_demo(args)
    if args.command == "agent" and args.agent_command == "run":
        return _agent_run(args)
    raise AssertionError(f"unhandled command {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
