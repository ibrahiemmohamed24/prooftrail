"""Explicit, serialisable benchmark configuration.

No evaluator run may inherit a provider or model from the agent dataset or an
ambient environment variable. The spec is written beside every output and is
part of the cache namespace.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..baselines.prompts import B1_JSON_SCHEMA, B1_SYSTEM_PROMPT
from ..config import AUDITOR_LIMITS, FROZEN_DIR
from ..freeze import MANIFEST_NAME, sha256_file


BENCHMARK_SPEC_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class BenchmarkSpec:
    schema_version: int
    auditor: str
    provider: str
    model: str
    max_output_tokens: int
    effort: str
    max_llm_calls_per_case: int
    run_index: int
    dataset_manifest_sha256: str
    system_prompt_sha256: str
    output_schema_sha256: str
    input_contract: str = "FrozenCase.auditor_view/v1"
    output_contract: str = "AuditOutput/v1"

    def __post_init__(self) -> None:
        if self.schema_version != BENCHMARK_SPEC_SCHEMA_VERSION:
            raise ValueError(f"unsupported benchmark spec version {self.schema_version}")
        if not self.auditor or not self.provider or not self.model:
            raise ValueError("auditor, provider and model must be explicit")
        if self.max_output_tokens <= 0 or self.max_llm_calls_per_case <= 0:
            raise ValueError("benchmark limits must be positive")
        if self.run_index < 0:
            raise ValueError("run_index must be >= 0")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["spec_sha256"] = self.sha256
        return value

    @property
    def sha256(self) -> str:
        value = asdict(self)
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_b1_spec(
    *,
    provider: str,
    model: str,
    run_index: int,
    frozen_dir: str | Path = FROZEN_DIR,
) -> BenchmarkSpec:
    manifest = Path(frozen_dir) / MANIFEST_NAME
    if not manifest.exists():
        raise FileNotFoundError(f"frozen dataset manifest is missing: {manifest}")
    return BenchmarkSpec(
        schema_version=BENCHMARK_SPEC_SCHEMA_VERSION,
        auditor="B1",
        provider=provider,
        model=model,
        max_output_tokens=AUDITOR_LIMITS.max_output_tokens,
        effort=AUDITOR_LIMITS.effort,
        max_llm_calls_per_case=AUDITOR_LIMITS.max_llm_calls_per_case,
        run_index=run_index,
        dataset_manifest_sha256=sha256_file(manifest),
        system_prompt_sha256=hashlib.sha256(B1_SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
        output_schema_sha256=hashlib.sha256(
            json.dumps(B1_JSON_SCHEMA, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    )


__all__ = ["BENCHMARK_SPEC_SCHEMA_VERSION", "BenchmarkSpec", "build_b1_spec"]
