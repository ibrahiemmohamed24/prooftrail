"""Executable, label-blind B1 benchmark over immutable frozen evidence."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from .agent.cache import CachingModelClient, ReplayCache, ReplayCacheMiss, ReplayCacheModelMismatch
from .agent.gemini_client import (
    FreeTierConfirmationError,
    GeminiResponseError,
    GeminiTransportError,
    MissingGeminiApiKeyError,
    list_price_equivalent_usd,
)
from .agent.interfaces import ModelClient
from .baselines import InvalidJSONCompletion, ModelJSONCompletionClient
from .baselines.b1_trace_plus_ledger import B1Auditor, InvalidBaselineOutput
from .config import AUDITOR_LIMITS, B1_REPLAY_DIR, BENCHMARK_DIR, AuditorLimits, FROZEN_DIR
from .eval.runner import write_outputs
from .eval.spec import BenchmarkSpec
from .freeze import MANIFEST_NAME, load_frozen_case, sha256_file
from .schemas import AuditOutput


MODE_LIVE = "live-record-or-resume"
MODE_REPLAY = "replay-no-network"
_SAFE_COMPONENT = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_component(value: str) -> str:
    return _SAFE_COMPONENT.sub("_", value).strip("._") or "unnamed"


def b1_cache_path(
    cache_dir: str | Path,
    spec: BenchmarkSpec,
    case_id: str,
) -> Path:
    return (
        Path(cache_dir)
        / _safe_component(spec.provider)
        / _safe_component(spec.model)
        / f"spec-{spec.sha256[:16]}"
        / f"run-{spec.run_index:02d}"
        / f"{case_id}.json"
    )


@dataclass
class B1BenchmarkRun:
    spec: BenchmarkSpec
    mode: str
    requested_case_ids: tuple[str, ...]
    outputs: dict[str, AuditOutput]
    failures: list[dict[str, str]]
    cache_hits: int
    cache_misses: int

    @property
    def complete(self) -> bool:
        return not self.failures and len(self.outputs) == len(self.requested_case_ids)

    def summary(self) -> dict[str, Any]:
        usage = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "llm_calls": 0}
        verdicts: dict[str, int] = {}
        for output in self.outputs.values():
            for name in usage:
                usage[name] = round(usage[name] + output.usage.get(name, 0), 6)
            verdicts[output.verdict] = verdicts.get(output.verdict, 0) + 1
        usage["input_tokens"] = int(usage["input_tokens"])
        usage["output_tokens"] = int(usage["output_tokens"])
        usage["llm_calls"] = int(usage["llm_calls"])
        usage["list_price_equivalent_usd"] = list_price_equivalent_usd(
            self.spec.model,
            usage["input_tokens"],
            usage["output_tokens"],
        )
        return {
            "mode": self.mode,
            "auditor": self.spec.auditor,
            "provider": self.spec.provider,
            "model": self.spec.model,
            "run_index": self.spec.run_index,
            "spec_sha256": self.spec.sha256,
            "requested_cases": len(self.requested_case_ids),
            "completed_cases": len(self.outputs),
            "failure_count": len(self.failures),
            "complete": self.complete,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "verdicts": dict(sorted(verdicts.items())),
            "usage": usage,
        }


_EXPECTED_RUN_ERRORS = (
    FreeTierConfirmationError,
    GeminiResponseError,
    GeminiTransportError,
    InvalidBaselineOutput,
    InvalidJSONCompletion,
    MissingGeminiApiKeyError,
    ReplayCacheMiss,
    ReplayCacheModelMismatch,
)


def run_b1_benchmark(
    case_ids: Sequence[str],
    spec: BenchmarkSpec,
    *,
    mode: str,
    live_factory: Callable[[], ModelClient] | None = None,
    cache_dir: str | Path = B1_REPLAY_DIR,
    frozen_dir: str | Path = FROZEN_DIR,
    fresh: bool = False,
) -> B1BenchmarkRun:
    """Run B1 without ever loading a provisional or reviewed label."""

    if mode not in (MODE_LIVE, MODE_REPLAY):
        raise ValueError(f"unsupported benchmark mode {mode!r}")
    if mode == MODE_LIVE and live_factory is None:
        raise ValueError("live B1 mode requires a live_factory")
    if mode == MODE_REPLAY and live_factory is not None:
        raise ValueError("replay B1 mode must not receive a live_factory")
    if fresh and mode != MODE_LIVE:
        raise ValueError("--fresh is valid only in live mode")
    ordered_ids = tuple(case_ids)
    if len(set(ordered_ids)) != len(ordered_ids):
        raise ValueError("duplicate case ids are not allowed in one benchmark run")
    manifest_path = Path(frozen_dir) / MANIFEST_NAME
    current_manifest_hash = sha256_file(manifest_path)
    if current_manifest_hash != spec.dataset_manifest_sha256:
        raise ValueError("benchmark spec does not match the current frozen dataset manifest")

    outputs: dict[str, AuditOutput] = {}
    failures: list[dict[str, str]] = []
    hits = 0
    misses = 0
    limits = AuditorLimits(
        max_output_tokens=spec.max_output_tokens,
        effort=spec.effort,
        max_llm_calls_per_case=spec.max_llm_calls_per_case,
    )
    for case_id in ordered_ids:
        cache = ReplayCache(b1_cache_path(cache_dir, spec, case_id))
        if fresh:
            cache.clear()
        if mode == MODE_LIVE:
            cached_client = CachingModelClient(
                cache,
                inner_factory=live_factory,
                model_name=spec.model,
            )
        else:
            cached_client = CachingModelClient(cache, None, model_name=spec.model)
        auditor = B1Auditor(
            ModelJSONCompletionClient(cached_client),
            model=spec.model,
            limits=limits,
        )
        try:
            outputs[case_id] = auditor.audit(load_frozen_case(case_id, frozen_dir))
        except _EXPECTED_RUN_ERRORS as exc:
            failures.append(
                {
                    "case_id": case_id,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
        hits += cached_client.hits
        misses += cached_client.misses
    return B1BenchmarkRun(spec, mode, ordered_ids, outputs, failures, hits, misses)


def default_b1_output_dir(
    spec: BenchmarkSpec,
    benchmark_dir: str | Path = BENCHMARK_DIR,
) -> Path:
    return (
        Path(benchmark_dir)
        / "b1"
        / _safe_component(spec.provider)
        / _safe_component(spec.model)
        / f"spec-{spec.sha256[:16]}"
        / f"run-{spec.run_index:02d}"
    )


def write_b1_benchmark_artifacts(
    run: B1BenchmarkRun,
    output_dir: str | Path | None = None,
) -> dict[str, Path]:
    directory = Path(output_dir) if output_dir is not None else default_b1_output_dir(run.spec)
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "spec": directory / "spec.json",
        "outputs": directory / "outputs.json",
        "failures": directory / "failures.json",
        "summary": directory / "summary.json",
    }
    paths["spec"].write_text(
        json.dumps(run.spec.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    write_outputs(paths["outputs"], run.outputs)
    paths["failures"].write_text(
        json.dumps(run.failures, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    paths["summary"].write_text(
        json.dumps(run.summary(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return paths


__all__ = [
    "B1BenchmarkRun",
    "MODE_LIVE",
    "MODE_REPLAY",
    "b1_cache_path",
    "default_b1_output_dir",
    "run_b1_benchmark",
    "write_b1_benchmark_artifacts",
]
