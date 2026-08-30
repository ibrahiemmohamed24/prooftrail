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
from .agent.cache import CachingModelClient, ReplayCache, ReplayCacheMiss, ReplayCacheModelMismatch
from .agent.gemini_client import (
    DEFAULT_GEMINI_MODEL,
    FreeTierConfirmationError,
    GeminiModelClient,
    GeminiResponseError,
    GeminiTransportError,
    MissingGeminiApiKeyError,
)
from .agent.runner import MODE_LIVE, MODE_REPLAY, run_case, write_case_artifacts
from .benchmark import (
    MODE_LIVE as B1_MODE_LIVE,
    MODE_REPLAY as B1_MODE_REPLAY,
    run_b1_benchmark,
    write_b1_benchmark_artifacts,
)
from .benchmark_report import (
    BenchmarkReportError,
    DEFAULT_COMPARISON_DIR,
    build_comparison_report_from_disk,
    write_comparison_report,
)
from .baselines.prompts import B1_JSON_SCHEMA
from .config import (
    B1_REPLAY_DIR,
    BENCHMARK_DIR,
    EVIDENCE_DIR,
    FROZEN_DIR,
    MODEL,
    REPLAY_DIR,
    REVIEW_DIR,
    REVIEW_PACK_DIR,
    UnknownModelPricingError,
)
from .demo import run_killer_demo, write_demo_artifacts
from .eval.metrics import evaluate_outputs
from .eval.report import write_metrics_report
from .eval.runner import write_outputs
from .eval.spec import build_b1_spec
from .freeze import (
    all_case_ids,
    build_manifest,
    freeze_case,
    manifest_problems,
    parse_case_id,
    replay_case,
    write_manifest,
)
from .ids import case_id as make_case_id
from .review import (
    ReviewValidationError,
    build_review_manifest,
    create_decision,
    load_amendment,
    write_amendment_draft,
    write_decision,
    write_review_manifest,
    write_review_pack,
)
from .scenarios import FAMILIES, FAMILY_IDS
from .schemas import ReviewAction


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
    run.add_argument("--fresh", action="store_true", help="discard this case's replay cache first; without it a live run resumes from cached turns")
    run.add_argument("--json", action="store_true", help="print only the JSON summary")

    freeze = commands.add_parser(
        "freeze",
        help="run the real model once per case and write data/frozen/<case>/ (uses the selected provider's key only on a cache miss)",
    )
    freeze.add_argument(
        "--live",
        action="store_true",
        required=True,
        help="explicit opt-in to call the selected provider on cache misses (Anthropic is billed under the budget guard; Gemini Free Tier is billed $0)",
    )
    which = freeze.add_mutually_exclusive_group(required=True)
    which.add_argument("--all", action="store_true", help="all 10 families x 4 seeds (40 cases)")
    which.add_argument("--case", action="append", metavar="CASE_ID", help="one case id, repeatable (e.g. F02-s00)")
    freeze.add_argument(
        "--provider",
        choices=PROVIDERS,
        default=DEFAULT_PROVIDER if DEFAULT_PROVIDER in PROVIDERS else "anthropic",
        help="live provider and replay cache namespace (gemini = zero-billed free tier)",
    )
    freeze.add_argument("--model", default=None, help=f"override the model (Anthropic default: {MODEL}; Gemini default: {DEFAULT_GEMINI_MODEL})")
    freeze.add_argument("--budget-usd", type=float, default=None, help="override PROOFTRAIL_BUDGET_USD (paid providers only)")
    freeze.add_argument("--cache-dir", type=Path, default=REPLAY_DIR)
    freeze.add_argument("--frozen-dir", type=Path, default=FROZEN_DIR)
    freeze.add_argument("--fresh", action="store_true", help="discard existing replay caches before recording")
    freeze.add_argument("--skip-frozen", action="store_true", help="skip cases whose case.json already exists")
    freeze.add_argument("--json", action="store_true")

    replay = commands.add_parser("replay", help="replay frozen cases from the cache; no key, no network")
    which = replay.add_mutually_exclusive_group(required=True)
    which.add_argument("--all", action="store_true")
    which.add_argument("--case", action="append", metavar="CASE_ID")
    replay.add_argument(
        "--provider",
        choices=PROVIDERS,
        default=DEFAULT_PROVIDER if DEFAULT_PROVIDER in PROVIDERS else "anthropic",
        help="live provider and replay cache namespace (gemini = zero-billed free tier)",
    )
    replay.add_argument("--cache-dir", type=Path, default=REPLAY_DIR)
    replay.add_argument("--frozen-dir", type=Path, default=FROZEN_DIR)
    replay.add_argument("--json", action="store_true")

    manifest = commands.add_parser("manifest", help="rebuild data/frozen/manifest.json and check the 40/40 invariants")
    manifest.add_argument(
        "--provider",
        choices=PROVIDERS,
        default=DEFAULT_PROVIDER if DEFAULT_PROVIDER in PROVIDERS else "anthropic",
        help="live provider and replay cache namespace (gemini = zero-billed free tier)",
    )
    manifest.add_argument("--cache-dir", type=Path, default=REPLAY_DIR)
    manifest.add_argument("--frozen-dir", type=Path, default=FROZEN_DIR)
    manifest.add_argument("--json", action="store_true")

    review = commands.add_parser(
        "review",
        help="prepare and record source-bound human review decisions (never auto-approves labels)",
    )
    review_commands = review.add_subparsers(dest="review_command", required=True)

    pack = review_commands.add_parser(
        "pack",
        help="write raw-evidence review aids; this does not create any decision",
    )
    which = pack.add_mutually_exclusive_group(required=True)
    which.add_argument("--all", action="store_true")
    which.add_argument("--case", action="append", metavar="CASE_ID")
    pack.add_argument("--frozen-dir", type=Path, default=FROZEN_DIR)
    pack.add_argument("--output", type=Path, default=REVIEW_PACK_DIR)
    pack.add_argument("--json", action="store_true")

    draft = review_commands.add_parser(
        "draft",
        help="copy one provisional proposal to an editable amendment draft",
    )
    draft.add_argument("--case", required=True, metavar="CASE_ID")
    draft.add_argument("--output", required=True, type=Path)
    draft.add_argument("--frozen-dir", type=Path, default=FROZEN_DIR)

    decide = review_commands.add_parser(
        "decide",
        help="record one explicit human decision; there is deliberately no --all",
    )
    decide.add_argument("--case", required=True, metavar="CASE_ID")
    action = decide.add_mutually_exclusive_group(required=True)
    action.add_argument("--approve", action="store_true")
    action.add_argument("--amend", type=Path, metavar="AMENDMENT_JSON")
    action.add_argument("--abstain", action="store_true")
    decide.add_argument("--reviewer-id", required=True)
    decide.add_argument("--reviewer-name", required=True)
    decide.add_argument("--rationale", required=True)
    decide.add_argument(
        "--attest-reviewed",
        action="store_true",
        help="attest that you personally reviewed the raw final report, tool calls and ledger",
    )
    decide.add_argument("--replace", action="store_true")
    decide.add_argument("--supersedes", default=None, metavar="DECISION_SHA256")
    decide.add_argument("--frozen-dir", type=Path, default=FROZEN_DIR)
    decide.add_argument("--review-dir", type=Path, default=REVIEW_DIR)
    decide.add_argument("--json", action="store_true")

    status = review_commands.add_parser("status", help="show pending, accepted, abstained and invalid decisions")
    status.add_argument("--frozen-dir", type=Path, default=FROZEN_DIR)
    status.add_argument("--review-dir", type=Path, default=REVIEW_DIR)
    status.add_argument("--write-manifest", action="store_true")
    status.add_argument("--json", action="store_true")

    verify = review_commands.add_parser("verify", help="validate every decision and its frozen source hashes")
    verify.add_argument("--frozen-dir", type=Path, default=FROZEN_DIR)
    verify.add_argument("--review-dir", type=Path, default=REVIEW_DIR)
    verify.add_argument("--require-complete", action="store_true")
    verify.add_argument("--json", action="store_true")

    benchmark = commands.add_parser(
        "benchmark",
        help="run label-blind auditors over byte-identical frozen evidence",
    )
    benchmark_commands = benchmark.add_subparsers(dest="benchmark_command", required=True)
    b1 = benchmark_commands.add_parser(
        "b1",
        help="run or replay the one-shot trace+ledger LLM baseline",
    )
    mode = b1.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true", help="record/resume Gemini Free Tier B1 responses")
    mode.add_argument("--replay", action="store_true", help="use only frozen B1 responses; no key or network")
    which = b1.add_mutually_exclusive_group(required=True)
    which.add_argument("--all", action="store_true")
    which.add_argument("--case", action="append", metavar="CASE_ID")
    b1.add_argument("--provider", choices=("gemini",), default="gemini")
    b1.add_argument("--model", default=DEFAULT_GEMINI_MODEL)
    b1.add_argument("--run-index", type=int, default=0)
    b1.add_argument("--cache-dir", type=Path, default=B1_REPLAY_DIR)
    b1.add_argument("--frozen-dir", type=Path, default=FROZEN_DIR)
    b1.add_argument("--output", type=Path, default=None)
    b1.add_argument("--fresh", action="store_true", help="discard this run's selected B1 caches before live calls")
    b1.add_argument("--json", action="store_true")

    report = benchmark_commands.add_parser(
        "report",
        help="compare three frozen B1 runs with ProofTrail and its temporal ablation; no network",
    )
    report.add_argument("--provider", choices=("gemini",), default="gemini")
    report.add_argument("--model", default=DEFAULT_GEMINI_MODEL)
    report.add_argument(
        "--run-index",
        dest="run_indices",
        action="append",
        type=int,
        help="B1 run index; repeat exactly three times (default: 0, 1, 2)",
    )
    report.add_argument(
        "--allow-provisional",
        action="store_true",
        help="explicitly create a non-headline diagnostic from unreviewed labels",
    )
    report.add_argument("--frozen-dir", type=Path, default=FROZEN_DIR)
    report.add_argument("--review-dir", type=Path, default=REVIEW_DIR)
    report.add_argument("--benchmark-dir", type=Path, default=BENCHMARK_DIR)
    report.add_argument("--output", type=Path, default=DEFAULT_COMPARISON_DIR)
    report.add_argument("--json", action="store_true")
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
    print(
        "Mode          : scripted offline fixture (not a real LLM run); the real-model "
        "dataset is in data/frozen/ - replay it with `prooftrail replay --provider gemini --all`"
    )
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


def build_gemini_client(
    *,
    model: str | None,
    label: str,
    json_response_schema: dict | None = None,
) -> GeminiModelClient:
    """Factory for the real free-tier provider; tests replace its transport."""

    return GeminiModelClient(
        model=model or DEFAULT_GEMINI_MODEL,
        label=label,
        json_response_schema=json_response_schema,
    )


def replay_cache_path(cache_dir: Path, case_id: str) -> Path:
    return Path(cache_dir) / f"{case_id}.json"


def provider_cache_root(cache_dir: Path, provider: str) -> Path:
    """Gemini caches live under ``data/replay/gemini/`` so providers never mix."""

    root = Path(cache_dir)
    if provider == "gemini" and root.resolve() == REPLAY_DIR.resolve():
        root = root / "gemini"
    return root


def live_factory_for(provider: str):
    """Return a ``(model, budget, label) -> ModelClient`` factory for ``provider``."""

    if provider == "gemini":
        return lambda *, model, budget, label: build_gemini_client(model=model, label=label)
    return build_live_client


def _agent_run(args: argparse.Namespace) -> int:
    case_id = make_case_id(args.family, args.seed)
    cache_root = provider_cache_root(args.cache_dir, args.provider)
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
    except (ReplayCacheModelMismatch, UnknownModelPricingError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 5

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


def _selected_case_ids(args: argparse.Namespace) -> list[str]:
    if args.all:
        return list(all_case_ids())
    selected: list[str] = []
    for raw in args.case:
        for case_id in raw.split(","):
            case_id = case_id.strip()
            if case_id:
                parse_case_id(case_id)  # validates
                selected.append(case_id)
    return selected


def _freeze(args: argparse.Namespace) -> int:
    case_ids = _selected_case_ids(args)
    cache_root = provider_cache_root(args.cache_dir, args.provider)
    if args.provider == "gemini":
        if args.budget_usd is not None:
            print("error: --budget-usd is for paid providers; Gemini free tier bills $0", file=sys.stderr)
            return 7
        budget = None
    else:
        budget = BudgetGuard.from_env(limit_usd=args.budget_usd, ledger_path=cache_root / "cost_ledger.jsonl")
    factory = live_factory_for(args.provider)
    results: list[dict] = []
    failures: list[str] = []
    stopped_early: str | None = None
    for case_id in case_ids:
        if args.skip_frozen and (Path(args.frozen_dir) / case_id / "case.json").exists():
            if not args.json:
                print(f"{case_id}: already frozen, skipped")
            continue
        try:
            result = freeze_case(
                case_id,
                live_factory=factory,
                budget=budget,
                model=args.model,
                cache_dir=cache_root,
                frozen_dir=args.frozen_dir,
                fresh=args.fresh,
            )
        except (MissingApiKeyError, MissingGeminiApiKeyError, FreeTierConfirmationError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        except (ReplayCacheModelMismatch, UnknownModelPricingError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 5
        except BudgetExceededError as exc:
            print(f"error: budget guard stopped the run at {case_id}: {exc}", file=sys.stderr)
            failures.append(f"{case_id}: budget")
            stopped_early = case_id
            break
        except (GeminiTransportError, GeminiResponseError) as exc:
            # Quota or network trouble: stop here so the run can be resumed later
            # with the same command; cached turns are then served without a call.
            print(f"error: Gemini provider failed at {case_id}: {exc}", file=sys.stderr)
            failures.append(f"{case_id}: provider failure ({exc})")
            stopped_early = case_id
            break
        summary = result.summary()
        summary["provider"] = args.provider
        results.append(summary)
        if not result.ok:
            failures.append(f"{case_id}: checks failed {[k for k, v in result.checks.items() if not v]}")
        if not args.json:
            usage = summary["usage"]
            flag = "ok " if result.ok else "FAIL"
            if budget is not None:
                billing = f"budget ${budget.spent_usd:.4f}/${budget.limit_usd:.2f}"
            else:
                billing = "billed $0.00 (free tier)"
            print(
                f"[{flag}] {case_id}: {summary['tool_call_count']} tool calls, verdict {summary['verdict']}, "
                f"first bad {summary['first_bad_event_seq']}, chain {'valid' if summary['ledger_chain_valid'] else 'INVALID'}, "
                f"{usage['llm_calls']} calls ({result.cache_hits} cached / {result.cache_misses} live), "
                f"{usage['input_tokens']} in / {usage['output_tokens']} out tokens, {billing}"
            )
            if not result.ok:
                print(f"       failed checks: {[k for k, v in result.checks.items() if not v]}")

    manifest = build_manifest(frozen_dir=args.frozen_dir, cache_dir=cache_root)
    manifest_path = write_manifest(manifest, args.frozen_dir)
    if args.json:
        print(json.dumps({"results": results, "failures": failures, "stopped_at": stopped_early, "manifest": manifest}, sort_keys=True))
    else:
        totals = manifest["totals"]
        print(
            f"Manifest      : {manifest_path} -> {manifest['status']}, "
            f"{totals['llm_calls']} calls, {totals['input_tokens']} in / {totals['output_tokens']} out tokens, "
            f"billed ${totals['cost_usd']:.4f} (list-price equivalent ${totals['list_price_equivalent_usd']:.4f})"
        )
        if budget is not None:
            print(f"Budget        : ${budget.spent_usd:.4f} of ${budget.limit_usd:.2f} spent (cumulative)")
        if stopped_early is not None:
            print(f"Stopped at    : {stopped_early}; rerun the same command with --skip-frozen to resume")
        for problem in manifest_problems(manifest):
            print(f"  - {problem}")
    if any("provider failure" in failure for failure in failures):
        return 6
    return 1 if failures else 0


def _replay(args: argparse.Namespace) -> int:
    case_ids = _selected_case_ids(args)
    cache_root = provider_cache_root(args.cache_dir, args.provider)
    rows: list[dict] = []
    failures: list[str] = []
    for case_id in case_ids:
        try:
            result = replay_case(case_id, cache_dir=cache_root, frozen_dir=args.frozen_dir)
        except FileNotFoundError as exc:
            failures.append(f"{case_id}: {exc}")
            if not args.json:
                print(f"[MISS] {case_id}: {exc}")
            continue
        except ReplayCacheMiss as exc:
            failures.append(f"{case_id}: replay cache miss")
            if not args.json:
                print(f"[MISS] {case_id}: {exc}")
            continue
        summary = result.summary()
        rows.append(summary)
        if not result.matches_frozen:
            failures.append(f"{case_id}: replay differs from frozen case ({'; '.join(result.differences)})")
        if not args.json:
            flag = "ok " if result.matches_frozen else "DIFF"
            print(
                f"[{flag}] {case_id}: {summary['cache_hits']} cached responses, verdict {summary['verdict']}, "
                f"chain {'valid' if summary['ledger_chain_valid'] else 'INVALID'}"
                + ("" if result.matches_frozen else f" -> {'; '.join(result.differences)}")
            )
    if args.json:
        print(json.dumps({"replayed": rows, "failures": failures}, sort_keys=True))
    else:
        print(f"Replayed {len(rows)}/{len(case_ids)} cases with no API key; {len(failures)} failure(s).")
    return 1 if failures else 0


def _manifest(args: argparse.Namespace) -> int:
    manifest = build_manifest(frozen_dir=args.frozen_dir, cache_dir=provider_cache_root(args.cache_dir, args.provider))
    path = write_manifest(manifest, args.frozen_dir)
    problems = manifest_problems(manifest)
    if args.json:
        print(json.dumps(manifest, sort_keys=True))
    else:
        totals = manifest["totals"]
        print(f"Manifest   : {path}")
        print(f"Status     : {manifest['status']} ({'complete' if manifest['complete'] else 'INCOMPLETE'})")
        print(f"Models     : {', '.join(manifest['models']) or '-'}   providers: {', '.join(manifest['providers']) or '-'}")
        print(
            f"Totals     : {totals['llm_calls']} LLM calls, {totals['input_tokens']} in / "
            f"{totals['output_tokens']} out tokens, billed ${totals['cost_usd']:.4f} "
            f"(list-price equivalent ${totals['list_price_equivalent_usd']:.4f})"
        )
        for name, value in manifest["invariants"].items():
            print(f"  {name:<28} {'yes' if value else 'NO'}")
        for problem in problems:
            print(f"  - {problem}")
    return 0 if manifest["complete"] else 1


def _review_pack(args: argparse.Namespace) -> int:
    case_ids = _selected_case_ids(args)
    try:
        written = write_review_pack(
            case_ids,
            frozen_dir=args.frozen_dir,
            output_dir=args.output,
        )
    except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        print(f"error: cannot build review pack: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(
            json.dumps(
                {
                    "case_count": len(written),
                    "output": str(Path(args.output).resolve()),
                    "decisions_created": 0,
                },
                sort_keys=True,
            )
        )
    else:
        print(f"Review pack  : {Path(args.output).resolve()}")
        print(f"Cases        : {len(written)}")
        print("Decisions    : 0 (a review pack never verifies labels)")
    return 0


def _review_draft(args: argparse.Namespace) -> int:
    try:
        parse_case_id(args.case)
        path = write_amendment_draft(args.case, args.output, frozen_dir=args.frozen_dir)
    except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        print(f"error: cannot write amendment draft: {exc}", file=sys.stderr)
        return 2
    print(f"Amendment draft: {path.resolve()} (not a review decision)")
    return 0


def _review_decide(args: argparse.Namespace) -> int:
    try:
        parse_case_id(args.case)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not args.attest_reviewed:
        print(
            "error: --attest-reviewed is required; no script or AI may attest on a human's behalf",
            file=sys.stderr,
        )
        return 2
    action = (
        ReviewAction.APPROVE
        if args.approve
        else ReviewAction.AMEND
        if args.amend is not None
        else ReviewAction.ABSTAIN
    )
    try:
        amendment = load_amendment(args.amend) if args.amend is not None else None
        decision = create_decision(
            args.case,
            action=action,
            reviewer_id=args.reviewer_id,
            reviewer_name=args.reviewer_name,
            rationale=args.rationale,
            attested=True,
            amendment=amendment,
            supersedes_decision_sha256=args.supersedes,
            frozen_dir=args.frozen_dir,
        )
        path = write_decision(
            decision,
            review_dir=args.review_dir,
            frozen_dir=args.frozen_dir,
            replace_existing=args.replace,
        )
        manifest = build_review_manifest(
            review_dir=args.review_dir,
            frozen_dir=args.frozen_dir,
        )
        manifest_path = write_review_manifest(manifest, review_dir=args.review_dir)
    except (ReviewValidationError, FileExistsError, FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        print(f"error: review decision was not recorded: {exc}", file=sys.stderr)
        return 2
    result = {
        "case_id": decision.case_id,
        "action": decision.action,
        "decision_sha256": decision.decision_sha256,
        "decision_path": str(path.resolve()),
        "review_manifest": str(manifest_path.resolve()),
        "headline_eligible": manifest["headline_eligible"],
    }
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(f"Recorded      : {decision.action} for {decision.case_id}")
        print(f"Decision hash : {decision.decision_sha256}")
        print(f"Decision file : {path.resolve()}")
        print(
            f"Review status : {manifest['counts']['accepted']}/{manifest['counts']['expected']} accepted; "
            f"headline eligible={'yes' if manifest['headline_eligible'] else 'no'}"
        )
    return 0


def _print_review_status(manifest: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(manifest, sort_keys=True))
        return
    counts = manifest["counts"]
    print(
        f"Review status : {counts['reviewed']}/{counts['expected']} reviewed, "
        f"{counts['accepted']} accepted, {counts['abstained']} abstained, "
        f"{counts['pending']} pending"
    )
    print(f"Complete      : {'yes' if manifest['review_complete'] else 'no'}")
    print(f"Headline ready: {'yes' if manifest['headline_eligible'] else 'no'}")
    for problem in manifest["problems"]:
        print(f"  - {problem}")


def _review_status(args: argparse.Namespace) -> int:
    manifest = build_review_manifest(review_dir=args.review_dir, frozen_dir=args.frozen_dir)
    if args.write_manifest:
        write_review_manifest(manifest, review_dir=args.review_dir)
    _print_review_status(manifest, as_json=args.json)
    return 1 if manifest["problems"] else 0


def _review_verify(args: argparse.Namespace) -> int:
    manifest = build_review_manifest(review_dir=args.review_dir, frozen_dir=args.frozen_dir)
    _print_review_status(manifest, as_json=args.json)
    if manifest["problems"]:
        return 1
    if args.require_complete and not manifest["headline_eligible"]:
        return 3
    return 0


def _benchmark_b1(args: argparse.Namespace) -> int:
    try:
        case_ids = _selected_case_ids(args)
        spec = build_b1_spec(
            provider=args.provider,
            model=args.model,
            run_index=args.run_index,
            frozen_dir=args.frozen_dir,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: invalid B1 benchmark specification: {exc}", file=sys.stderr)
        return 2
    if args.replay and args.fresh:
        print("error: --fresh is valid only with --live", file=sys.stderr)
        return 2

    shared_live_client: GeminiModelClient | None = None

    def live_factory() -> GeminiModelClient:
        nonlocal shared_live_client
        if shared_live_client is None:
            shared_live_client = build_gemini_client(
                model=spec.model,
                label=f"B1-run-{spec.run_index:02d}",
                json_response_schema=B1_JSON_SCHEMA,
            )
        return shared_live_client

    run = run_b1_benchmark(
        case_ids,
        spec,
        mode=B1_MODE_LIVE if args.live else B1_MODE_REPLAY,
        live_factory=live_factory if args.live else None,
        cache_dir=args.cache_dir,
        frozen_dir=args.frozen_dir,
        fresh=args.fresh,
    )
    paths = write_b1_benchmark_artifacts(run, args.output)
    summary = run.summary()
    if args.json:
        print(
            json.dumps(
                {
                    "summary": summary,
                    "failures": run.failures,
                    "paths": {name: str(path.resolve()) for name, path in paths.items()},
                },
                sort_keys=True,
            )
        )
    else:
        usage = summary["usage"]
        print(
            f"B1 run       : {summary['completed_cases']}/{summary['requested_cases']} cases, "
            f"{summary['failure_count']} failure(s)"
        )
        print(f"Spec hash    : {summary['spec_sha256']}")
        print(f"Model        : {summary['provider']} / {summary['model']} / run {summary['run_index']}")
        print(f"Cache        : {summary['cache_hits']} hits, {summary['cache_misses']} misses")
        print(
            f"Usage        : {usage['llm_calls']} calls, {usage['input_tokens']} in / "
            f"{usage['output_tokens']} out, billed ${usage['cost_usd']:.4f}"
        )
        print(f"Artifacts    : {paths['summary'].parent.resolve()}")
        for failure in run.failures:
            print(f"  - {failure['case_id']}: {failure['error_type']}: {failure['message']}")
    return 0 if run.complete else 1


def _benchmark_report(args: argparse.Namespace) -> int:
    try:
        report = build_comparison_report_from_disk(
            provider=args.provider,
            model=args.model,
            run_indices=tuple(args.run_indices or (0, 1, 2)),
            allow_provisional=args.allow_provisional,
            frozen_dir=args.frozen_dir,
            review_dir=args.review_dir,
            benchmark_dir=args.benchmark_dir,
        )
        paths = write_comparison_report(report, args.output)
    except (BenchmarkReportError, FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        print(f"error: cannot build benchmark comparison: {exc}", file=sys.stderr)
        return 2
    summary = {
        "label_mode": report["label_mode"],
        "headline_eligible": report["headline_eligible"],
        "case_count": report["dataset"]["case_count"],
        "b1_run_count": report["b1"]["run_count"],
        "b1_family_mean_accuracy": report["b1"]["metric_distribution"][
            "family_mean_accuracy"
        ],
        "prooftrail_family_mean_accuracy": report["prooftrail"]["metric_values"][
            "family_mean_accuracy"
        ],
        "b1_unanimous_rate": report["b1"]["stability"]["unanimous_rate"],
        "b1_billed_cost_usd": report["b1"]["usage"]["billed_cost_usd"],
        "paths": {name: str(path.resolve()) for name, path in paths.items()},
    }
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        status = "HEADLINE ELIGIBLE" if report["headline_eligible"] else "PROVISIONAL ONLY"
        print(f"Comparison    : {status}")
        print(
            f"Cases / runs : {report['dataset']['case_count']} / "
            f"{report['b1']['run_count']}"
        )
        b1_stats = report["b1"]["metric_distribution"]["family_mean_accuracy"]
        print(
            f"Family mean  : B1 {b1_stats['mean'] * 100:.1f}% ± "
            f"{b1_stats['stddev'] * 100:.1f}% -> "
            f"ProofTrail {report['prooftrail']['metric_values']['family_mean_accuracy'] * 100:.1f}%"
        )
        print(
            f"B1 stability : {report['b1']['stability']['unanimous_rate'] * 100:.1f}% "
            f"unanimous; billed ${report['b1']['usage']['billed_cost_usd']:.2f}"
        )
        print(f"Report       : {paths['markdown'].resolve()}")
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
    if args.command == "freeze":
        return _freeze(args)
    if args.command == "replay":
        return _replay(args)
    if args.command == "manifest":
        return _manifest(args)
    if args.command == "review" and args.review_command == "pack":
        return _review_pack(args)
    if args.command == "review" and args.review_command == "draft":
        return _review_draft(args)
    if args.command == "review" and args.review_command == "decide":
        return _review_decide(args)
    if args.command == "review" and args.review_command == "status":
        return _review_status(args)
    if args.command == "review" and args.review_command == "verify":
        return _review_verify(args)
    if args.command == "benchmark" and args.benchmark_command == "b1":
        return _benchmark_b1(args)
    if args.command == "benchmark" and args.benchmark_command == "report":
        return _benchmark_report(args)
    raise AssertionError(f"unhandled command {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
