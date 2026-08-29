"""Prompt-hash keyed replay cache.

A live run records every ``(prompt sha256 -> ModelResponse)`` pair into one
JSON file per case under ``data/replay/``. Replay mode serves the same
responses with no network and no API key; a cache miss is an error rather
than a silent fallback, because it means the replayed inputs diverged from the
frozen run.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .interfaces import ModelClient, ModelResponse, ToolSpec, prompt_sha256

CACHE_SCHEMA_VERSION = 1


class ReplayCacheMiss(LookupError):
    """The prompt was never recorded; replay cannot continue without a network call."""


class ReplayCacheModelMismatch(ValueError):
    """The cache was recorded with a different model than the one requested."""


class ReplayCache:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.model: str | None = None
        self._entries: dict[str, dict[str, Any]] = {}
        self._order: list[str] = []
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if raw.get("schema_version") != CACHE_SCHEMA_VERSION:
            raise ValueError(f"unsupported replay cache schema in {self.path}")
        self.model = raw.get("model")
        self._entries = dict(raw.get("entries", {}))
        self._order = list(raw.get("order", []))

    def save(self) -> Path:
        """Write atomically: a crash mid-write can never leave a truncated cache."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "model": self.model,
            "order": list(self._order),
            "entries": self._entries,
        }
        tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
        tmp.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(tmp, self.path)
        return self.path

    def clear(self) -> None:
        self._entries = {}
        self._order = []
        self.model = None
        if self.path.exists():
            self.path.unlink()

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, key: str) -> bool:
        return key in self._entries

    @property
    def order(self) -> tuple[str, ...]:
        return tuple(self._order)

    def get(self, key: str) -> ModelResponse | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        return ModelResponse.from_dict(entry["response"])

    def put(self, key: str, response: ModelResponse, *, model: str) -> None:
        if self.model is None:
            self.model = model
        elif self.model != model:
            raise ReplayCacheModelMismatch(
                f"replay cache {self.path} was recorded with {self.model!r}, not {model!r}"
            )
        if key not in self._entries:
            self._order.append(key)
        self._entries[key] = {"response": response.to_dict()}
        self.save()

    def responses(self) -> tuple[ModelResponse, ...]:
        return tuple(ModelResponse.from_dict(self._entries[key]["response"]) for key in self._order)

    def total_usage(self) -> dict[str, Any]:
        totals: dict[str, Any] = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "llm_calls": 0}
        for response in self.responses():
            totals["input_tokens"] += response.usage.input_tokens
            totals["output_tokens"] += response.usage.output_tokens
            totals["cost_usd"] = round(totals["cost_usd"] + response.usage.cost_usd, 6)
            totals["llm_calls"] += response.usage.llm_calls
        return totals


class CachingModelClient:
    """Serve cached responses; record from ``inner`` on a miss when it exists."""

    def __init__(
        self,
        cache: ReplayCache,
        inner: ModelClient | None = None,
        *,
        model_name: str | None = None,
        inner_factory: Callable[[], ModelClient] | None = None,
    ):
        """``inner`` serves misses immediately; ``inner_factory`` builds it lazily.

        The lazy form exists for resumable recordings: a case whose every
        prompt is already cached is completed without constructing the live
        client at all, so no API key, quota or budget is touched. The factory
        runs on the first miss only, and the cache's recorded model is the
        contract it must honour.
        """

        if inner is not None and inner_factory is not None:
            raise ValueError("pass either inner or inner_factory, not both")
        self.cache = cache
        self._inner = inner
        self._inner_factory = inner_factory
        if inner is not None:
            self.model_name = inner.model_name
        else:
            self.model_name = model_name or cache.model or "replay-cache-without-model"
        # Check before any completion so a mismatch can never trigger a paid
        # API call that would only fail when the response is saved.
        if cache.model is not None and cache.model != self.model_name:
            raise ReplayCacheModelMismatch(
                f"replay cache {cache.path} was recorded with {cache.model!r} but "
                f"{self.model_name!r} was requested; pass --fresh to re-record or use --model {cache.model}"
            )
        self.is_live_model = bool(inner is not None and inner.is_live_model) or inner_factory is not None
        self.hits = 0
        self.misses = 0

    @property
    def inner(self) -> ModelClient | None:
        return self._inner

    @property
    def live_client_built(self) -> bool:
        return self._inner is not None

    def _resolve_inner(self) -> ModelClient | None:
        if self._inner is None and self._inner_factory is not None:
            built = self._inner_factory()
            if built.model_name != self.model_name:
                raise ReplayCacheModelMismatch(
                    f"replay cache {self.cache.path} was recorded with {self.model_name!r} but the live "
                    f"client was built for {built.model_name!r}"
                )
            self._inner = built
        return self._inner

    def complete(
        self,
        *,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[ToolSpec],
        max_output_tokens: int,
        effort: str,
    ) -> ModelResponse:
        key = prompt_sha256(
            model=self.model_name,
            messages=messages,
            tools=tools,
            max_output_tokens=max_output_tokens,
            effort=effort,
        )
        cached = self.cache.get(key)
        if cached is not None:
            self.hits += 1
            return cached
        inner = self._resolve_inner()
        if inner is None:
            raise ReplayCacheMiss(
                f"no cached response for prompt {key[:12]} in {self.cache.path}; "
                "the replayed inputs diverged from the recorded run or the case was never recorded"
            )
        response = inner.complete(
            messages=messages, tools=tools, max_output_tokens=max_output_tokens, effort=effort
        )
        self.misses += 1
        self.cache.put(key, response, model=self.model_name)
        return response


__all__ = [
    "CACHE_SCHEMA_VERSION",
    "CachingModelClient",
    "ReplayCache",
    "ReplayCacheMiss",
    "ReplayCacheModelMismatch",
]
