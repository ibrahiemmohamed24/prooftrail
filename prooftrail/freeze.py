"""Freeze real-model traces once; replay and verify them forever.

Layout (all committed on purpose):

    data/frozen/<case-id>/case.json               real AgentTrace + hash-chained ledger
    data/frozen/<case-id>/labels.provisional.json  ledger-derived, verified_by_human=false
    data/frozen/<case-id>/summary.json             mode, model, usage, verdict, chain status
    data/frozen/<case-id>/certificate.md           human review aid
    data/frozen/manifest.json                      40/40 inventory, totals and invariants
    data/replay/<case-id>.json                     prompt-hash keyed model responses
    data/replay/cost_ledger.jsonl                  every live call and its real cost

Nothing here reads a family's ``expected_verdict``. Labels come from the
ledger; the family and seed are stored only as evaluator metadata and are
stripped by ``FrozenCase.auditor_view`` before any auditor sees a case.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .agent.budget import BudgetGuard
from .agent.cache import CachingModelClient, ReplayCache, ReplayCacheModelMismatch
from .agent.interfaces import ModelClient
from .agent.runner import MODE_LIVE, MODE_REPLAY, CaseRun, run_case, write_case_artifacts
from .config import FROZEN_DIR, REPLAY_DIR, SCENARIO_CONFIG
from .ids import case_id as make_case_id
from .scenarios import FAMILY_IDS
from .schemas import FrozenCase, GroundTruth
from .schemas.events import verify_chain

MANIFEST_NAME = "manifest.json"
CASE_FILE = "case.json"
LABELS_FILE = "labels.provisional.json"
SUMMARY_FILE = "summary.json"
MANIFEST_SCHEMA_VERSION = 1

LiveClientFactory = Callable[..., ModelClient]


# --------------------------------------------------------------------------- #
# Case inventory helpers
# --------------------------------------------------------------------------- #
def all_case_ids() -> tuple[str, ...]:
    """The 10 x 4 fixed case ids, in family-then-seed order."""

    return tuple(
        make_case_id(family, seed) for family in FAMILY_IDS for seed in SCENARIO_CONFIG.seeds
    )


def parse_case_id(case_id: str) -> tuple[str, int]:
    family, separator, seed = case_id.partition("-s")
    if family not in FAMILY_IDS or separator != "-s" or not seed.isdigit():
        raise ValueError(f"malformed case id {case_id!r}; expected e.g. F02-s00")
    return family, int(seed)


def case_dir(frozen_dir: str | Path, case_id: str) -> Path:
    return Path(frozen_dir) / case_id


def replay_cache_path(cache_dir: str | Path, case_id: str) -> Path:
    return Path(cache_dir) / f"{case_id}.json"


def sha256_file(path: Path) -> str:
    """sha256 of a text artifact with CRLF normalised to LF.

    Git stores every text file as LF (``.gitattributes``: ``eol=lf``), but a
    Windows checkout, or an artifact written in text mode, may hold CRLF on
    disk. Hashing the normalised bytes keeps ``case_sha256``/``labels_sha256``
    identical in a working tree, in ``git archive`` and in a Linux clone.
    """

    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_frozen_case(case_id: str, frozen_dir: str | Path = FROZEN_DIR) -> FrozenCase:
    path = case_dir(frozen_dir, case_id) / CASE_FILE
    return FrozenCase.from_dict(json.loads(path.read_text(encoding="utf-8")))


def load_frozen_labels(case_id: str, frozen_dir: str | Path = FROZEN_DIR) -> GroundTruth:
    path = case_dir(frozen_dir, case_id) / LABELS_FILE
    return GroundTruth.from_dict(json.loads(path.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------- #
# Smoke checks: what must hold before spending on all 40 cases
# --------------------------------------------------------------------------- #
def smoke_checks(run: CaseRun) -> dict[str, bool]:
    """Machine-checkable version of the pre-flight list for live runs."""

    trace = run.case.trace
    assistant_turns = [m for m in trace.messages if m["role"] == "assistant"]
    tool_messages = [m for m in trace.messages if m["role"] == "tool"]
    timeouts_hidden = True
    for record in trace.tool_calls:
        if record.error and record.error.startswith("ToolTimeout"):
            if "unknown" not in record.error or "txn_" in record.error:
                timeouts_hidden = False
    for message in tool_messages:
        content = message.get("content")
        if isinstance(content, dict) and "error" in content and "ToolTimeout" in str(content["error"]):
            if "transaction_id" in content or "txn_" in json.dumps(content):
                timeouts_hidden = False

    return {
        "is_live_run": run.mode == MODE_LIVE,
        "model_called_tools": len(trace.tool_calls) > 0,
        "every_turn_has_provider_metadata": bool(assistant_turns)
        and all("provider" in m and m["provider"].get("prompt_sha256") for m in assistant_turns),
        "every_tool_call_has_a_tool_message": len(tool_messages) == len(trace.tool_calls),
        "timeout_hides_commit_status": timeouts_hidden,
        "ledger_chain_valid": run.ledger_chain_valid,
        "usage_recorded": trace.usage.llm_calls > 0 and trace.usage.input_tokens > 0,
        # A recorded cost may legitimately be $0.00 (free tier); what must hold
        # is that every turn carries an explicit provider cost figure.
        "cost_recorded": bool(assistant_turns)
        and all("cost_usd" in (m.get("provider", {}).get("usage") or {}) for m in assistant_turns),
        "labels_not_human_verified": run.ground_truth.verified_by_human is False,
        "final_report_present": bool(trace.final_report.strip()),
    }


# --------------------------------------------------------------------------- #
# Freeze (live) and replay (no key)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FreezeResult:
    case_id: str
    run: CaseRun
    paths: dict[str, Path]
    checks: dict[str, bool]
    cache_hits: int
    cache_misses: int

    @property
    def ok(self) -> bool:
        return all(self.checks.values())

    def summary(self) -> dict[str, Any]:
        summary = self.run.summary()
        summary["checks"] = dict(self.checks)
        summary["checks_ok"] = self.ok
        summary["cache_hits"] = self.cache_hits
        summary["cache_misses"] = self.cache_misses
        summary["frozen_dir"] = str(self.paths["case"].parent)
        return summary


def freeze_case(
    case_id: str,
    *,
    live_factory: LiveClientFactory,
    budget: BudgetGuard | None,
    model: str | None = None,
    cache_dir: str | Path = REPLAY_DIR,
    frozen_dir: str | Path = FROZEN_DIR,
    fresh: bool = False,
) -> FreezeResult:
    """Run one case against the real model and write its frozen bundle.

    ``budget`` is ``None`` for zero-billed providers; paid providers must pass
    a ``BudgetGuard``. ``live_factory`` receives ``model``, ``budget``, ``label``.
    """

    family, seed = parse_case_id(case_id)
    cache = ReplayCache(replay_cache_path(cache_dir, case_id))
    if fresh:
        cache.clear()

    def build_live() -> ModelClient:
        return live_factory(model=model, budget=budget, label=case_id)

    if cache.model is not None:
        # Resume: serve every recorded turn first; the live client (and its
        # key / quota / budget) is only touched if a prompt is missing.
        if model is not None and model != cache.model:
            raise ReplayCacheModelMismatch(
                f"replay cache {cache.path} was recorded with {cache.model!r}; refusing to continue "
                f"{case_id} with {model!r} (use --fresh to re-record)"
            )
        client = CachingModelClient(cache, inner_factory=build_live, model_name=cache.model)
    else:
        client = CachingModelClient(cache, build_live())
    run = run_case(family, seed, model_client=client, mode=MODE_LIVE)
    paths = write_case_artifacts(run, case_dir(frozen_dir, case_id))
    return FreezeResult(case_id, run, paths, smoke_checks(run), client.hits, client.misses)


@dataclass(frozen=True)
class ReplayResult:
    case_id: str
    run: CaseRun
    matches_frozen: bool
    differences: tuple[str, ...] = field(default_factory=tuple)
    cache_hits: int = 0

    def summary(self) -> dict[str, Any]:
        summary = self.run.summary()
        summary["matches_frozen"] = self.matches_frozen
        summary["differences"] = list(self.differences)
        summary["cache_hits"] = self.cache_hits
        return summary


def _diff_frozen(replayed: FrozenCase, frozen: FrozenCase) -> tuple[str, ...]:
    problems: list[str] = []
    a, b = replayed.to_dict(), frozen.to_dict()
    for key in ("case_id", "family_id", "seed", "schema_version"):
        if a[key] != b[key]:
            problems.append(f"{key}: replay={a[key]!r} frozen={b[key]!r}")
    for key in ("model", "system_prompt_sha256", "final_report", "stop_reason", "usage"):
        if a["trace"][key] != b["trace"][key]:
            problems.append(f"trace.{key} differs")
    if len(a["trace"]["messages"]) != len(b["trace"]["messages"]):
        problems.append(
            f"trace.messages: replay has {len(a['trace']['messages'])}, frozen has {len(b['trace']['messages'])}"
        )
    elif a["trace"]["messages"] != b["trace"]["messages"]:
        problems.append("trace.messages content differs")
    if a["trace"]["tool_calls"] != b["trace"]["tool_calls"]:
        problems.append("trace.tool_calls differ")
    if a["ledger"] != b["ledger"]:
        replay_hashes = [e["hash"] for e in a["ledger"]]
        frozen_hashes = [e["hash"] for e in b["ledger"]]
        first = next((i + 1 for i, (x, y) in enumerate(zip(replay_hashes, frozen_hashes)) if x != y), None)
        problems.append(
            f"ledger differs (replay {len(a['ledger'])} events, frozen {len(b['ledger'])}, first divergent seq {first})"
        )
    return tuple(problems)


def replay_case(
    case_id: str,
    *,
    cache_dir: str | Path = REPLAY_DIR,
    frozen_dir: str | Path = FROZEN_DIR,
) -> ReplayResult:
    """Re-run a case from the replay cache and compare it to the frozen bundle."""

    family, seed = parse_case_id(case_id)
    cache_path = replay_cache_path(cache_dir, case_id)
    if not cache_path.exists():
        raise FileNotFoundError(f"no replay cache for {case_id} at {cache_path}")
    client = CachingModelClient(ReplayCache(cache_path), None)
    run = run_case(family, seed, model_client=client, mode=MODE_REPLAY)
    frozen = load_frozen_case(case_id, frozen_dir)
    differences = _diff_frozen(run.case, frozen)
    return ReplayResult(case_id, run, not differences, differences, client.hits)


# --------------------------------------------------------------------------- #
# Manifest
# --------------------------------------------------------------------------- #
def turn_list_price(message: Mapping[str, Any]) -> float:
    """Paid-tier price of one assistant turn.

    Free-tier providers record ``list_price_equivalent_usd`` next to a billed
    ``cost_usd`` of 0; paid providers record the real charge as ``cost_usd``.
    """

    usage = message.get("provider", {}).get("usage") or {}
    if "list_price_equivalent_usd" in usage:
        return float(usage["list_price_equivalent_usd"])
    return float(usage.get("cost_usd", 0.0))


def _auditor_view_is_blind(case: FrozenCase) -> bool:
    view = case.auditor_view()
    text = json.dumps(view, sort_keys=True, ensure_ascii=False)
    forbidden_keys = {"family_id", "seed", "case_id", "expected_verdict"}
    if forbidden_keys & set(view) or forbidden_keys & set(view["trace"]):
        return False
    return case.family_id not in text and case.case_id not in text


def build_manifest(
    *,
    frozen_dir: str | Path = FROZEN_DIR,
    cache_dir: str | Path = REPLAY_DIR,
    expected: Sequence[str] | None = None,
) -> dict[str, Any]:
    expected_ids = tuple(expected) if expected is not None else all_case_ids()
    cases: list[dict[str, Any]] = []
    missing: list[str] = []
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "list_price_equivalent_usd": 0.0,
        "llm_calls": 0,
        "tool_calls": 0,
        "ledger_events": 0,
    }
    families: dict[str, dict[str, Any]] = {}
    models: set[str] = set()
    providers: set[str] = set()
    problems: list[str] = []

    for case_id in expected_ids:
        family = parse_case_id(case_id)[0]
        bucket = families.setdefault(family, {"expected": 0, "frozen": 0, "case_ids": []})
        bucket["expected"] += 1
        directory = case_dir(frozen_dir, case_id)
        case_path = directory / CASE_FILE
        labels_path = directory / LABELS_FILE
        if not case_path.exists() or not labels_path.exists():
            missing.append(case_id)
            continue
        try:
            case = load_frozen_case(case_id, frozen_dir)
            labels = load_frozen_labels(case_id, frozen_dir)
        except Exception as exc:  # a corrupt bundle is a problem, not a crash
            missing.append(case_id)
            problems.append(f"{case_id}: cannot load frozen bundle ({type(exc).__name__}: {exc})")
            continue

        chain_valid, bad_seq = verify_chain(case.ledger)
        if not chain_valid:
            problems.append(f"{case_id}: ledger hash chain invalid at seq {bad_seq}")
        if case.case_id != case_id or case.family_id != family:
            problems.append(f"{case_id}: bundle metadata mismatch ({case.case_id}, {case.family_id})")
        if labels.verified_by_human is not False:
            problems.append(f"{case_id}: labels are marked human-verified; only provisional labels are allowed here")
        if labels.case_id != case_id:
            problems.append(f"{case_id}: labels belong to {labels.case_id}")
        if not _auditor_view_is_blind(case):
            problems.append(f"{case_id}: auditor view leaks family or case identity")
        usage = case.trace.usage
        assistant_turns = [m for m in case.trace.messages if m["role"] == "assistant"]
        if usage.llm_calls <= 0 or usage.input_tokens <= 0:
            problems.append(f"{case_id}: trace has no recorded usage")
        if not all("cost_usd" in (m.get("provider", {}).get("usage") or {}) for m in assistant_turns):
            problems.append(f"{case_id}: a model turn has no recorded cost figure")
        case_providers = {m.get("provider", {}).get("provider") for m in assistant_turns}
        case_providers.discard(None)
        provider = sorted(case_providers)[0] if len(case_providers) == 1 else None
        if len(case_providers) != 1:
            problems.append(f"{case_id}: expected exactly one provider per trace, found {sorted(case_providers)}")
        list_price = round(sum(turn_list_price(m) for m in assistant_turns), 6)
        cache_path = replay_cache_path(cache_dir, case_id)
        cache_entries = len(ReplayCache(cache_path)) if cache_path.exists() else 0
        if cache_entries == 0:
            problems.append(f"{case_id}: replay cache missing or empty ({cache_path})")
        summary_path = directory / SUMMARY_FILE
        summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}

        models.add(case.trace.model)
        if provider is not None:
            providers.add(provider)
        totals["input_tokens"] += usage.input_tokens
        totals["output_tokens"] += usage.output_tokens
        totals["cost_usd"] = round(totals["cost_usd"] + usage.cost_usd, 6)
        totals["list_price_equivalent_usd"] = round(totals["list_price_equivalent_usd"] + list_price, 6)
        totals["llm_calls"] += usage.llm_calls
        totals["tool_calls"] += len(case.trace.tool_calls)
        totals["ledger_events"] += len(case.ledger)
        bucket["frozen"] += 1
        bucket["case_ids"].append(case_id)
        cases.append(
            {
                "case_id": case_id,
                "family_id": case.family_id,
                "seed": case.seed,
                "model": case.trace.model,
                "provider": provider,
                "mode": summary.get("mode"),
                "stop_reason": case.trace.stop_reason,
                "tool_calls": len(case.trace.tool_calls),
                "ledger_events": len(case.ledger),
                "ledger_chain_valid": chain_valid,
                "usage": usage.to_dict(),
                "list_price_equivalent_usd": list_price,
                "prooftrail_verdict": summary.get("verdict"),
                "prooftrail_first_bad_event_seq": summary.get("first_bad_event_seq"),
                "provisional_label_verdict": labels.verdict,
                "labels_verified_by_human": labels.verified_by_human,
                "replay_cache_entries": cache_entries,
                "case_sha256": sha256_file(case_path),
                "labels_sha256": sha256_file(labels_path),
            }
        )

    frozen_count = len(cases)
    if len(models) > 1:
        problems.append(f"dataset mixes models: {sorted(models)}; every case must use the same model")
    if len(providers) > 1:
        problems.append(f"dataset mixes providers: {sorted(providers)}")
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "dataset": "prooftrail-frozen-v1",
        "expected_cases": len(expected_ids),
        "frozen_cases": frozen_count,
        "complete": frozen_count == len(expected_ids) and not problems,
        "status": f"{frozen_count}/{len(expected_ids)} cases frozen",
        "models": sorted(models),
        "providers": sorted(providers),
        "totals": totals,
        "families": families,
        "missing": missing,
        "problems": problems,
        "invariants": {
            "all_chains_valid": all(c["ledger_chain_valid"] for c in cases) if cases else False,
            "all_labels_provisional": all(c["labels_verified_by_human"] is False for c in cases) if cases else False,
            "auditor_view_family_blind": not any("leaks" in p for p in problems) and bool(cases),
            "all_usage_recorded": all(c["usage"]["llm_calls"] > 0 and c["usage"]["input_tokens"] > 0 for c in cases) if cases else False,
            "all_replay_caches_present": all(c["replay_cache_entries"] > 0 for c in cases) if cases else False,
            "single_model": len(models) == 1,
            "single_provider": len(providers) == 1,
        },
        "human_verification": "none yet; every label is provisional and no B1-vs-ProofTrail number may be published from this manifest",
        "cases": cases,
    }
    return manifest


def write_manifest(manifest: dict[str, Any], frozen_dir: str | Path = FROZEN_DIR) -> Path:
    path = Path(frozen_dir) / MANIFEST_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def manifest_problems(manifest: dict[str, Any]) -> list[str]:
    problems = list(manifest.get("problems", []))
    missing = manifest.get("missing", [])
    if missing:
        problems.append(f"{len(missing)} case(s) not frozen: {', '.join(missing[:6])}{' ...' if len(missing) > 6 else ''}")
    return problems


__all__ = [
    "CASE_FILE",
    "LABELS_FILE",
    "MANIFEST_NAME",
    "SUMMARY_FILE",
    "FreezeResult",
    "ReplayResult",
    "all_case_ids",
    "build_manifest",
    "case_dir",
    "freeze_case",
    "load_frozen_case",
    "load_frozen_labels",
    "manifest_problems",
    "parse_case_id",
    "replay_cache_path",
    "replay_case",
    "smoke_checks",
    "write_manifest",
]
