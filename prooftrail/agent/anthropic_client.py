"""Live Anthropic Messages API adapter behind the ``ModelClient`` protocol.

Design rules:

* The core package stays stdlib-only. ``anthropic`` is imported lazily and
  only when a real SDK client has to be built; tests inject a fake client.
* Each completion records model name, prompt hash, token usage, cost, stop
  reason and provider tool-call ids in ``ModelResponse.metadata``.
* Provider content blocks (thinking / text / tool_use) are kept verbatim in
  ``ModelResponse.raw_content`` and echoed back unchanged on later turns.
* Transient failures (network, timeout, 429, 5xx) are retried a bounded number
  of times. Only the *model request* is retried. Tool execution lives in
  ``RefundAgent`` and happens exactly once per returned tool call, so a retry
  can never re-run a refund.
* The optional ``BudgetGuard`` is consulted before every request and updated
  with real usage afterwards.
"""
from __future__ import annotations

import json
import os
import time
from copy import deepcopy
from typing import Any, Callable, Mapping, Sequence

from ..config import MODEL, cost_usd, pricing_for
from ..schemas import Usage
from .budget import BudgetGuard
from .interfaces import ModelResponse, ToolCall, ToolSpec, prompt_sha256

API_KEY_ENV = "ANTHROPIC_API_KEY"
PROVIDER_NAME = "anthropic"

# Anthropic first-party multipliers relative to the input price.
CACHE_READ_MULTIPLIER = 0.1
CACHE_WRITE_MULTIPLIER = 1.25

TRANSIENT_STATUS_CODES = frozenset({408, 409, 429, 500, 502, 503, 504, 529})
TRANSIENT_CLASS_NAMES = frozenset(
    {
        "APIConnectionError",
        "APITimeoutError",
        "RateLimitError",
        "InternalServerError",
        "OverloadedError",
        "ServiceUnavailableError",
        "ConnectionError",
        "TimeoutError",
    }
)


class MissingApiKeyError(RuntimeError):
    """No API key was supplied and the provider environment variable is unset."""


class ProviderTransientError(RuntimeError):
    """A retryable provider failure (used by fakes and tests)."""


def is_transient_error(exc: BaseException) -> bool:
    """Classify an exception as retryable without importing the SDK."""

    if isinstance(exc, ProviderTransientError):
        return True
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status in TRANSIENT_STATUS_CODES
    return any(cls.__name__ in TRANSIENT_CLASS_NAMES for cls in type(exc).__mro__)


# --------------------------------------------------------------------------- #
# Provider-neutral transcript  ->  Anthropic request
# --------------------------------------------------------------------------- #
def to_anthropic_tool(spec: ToolSpec) -> dict[str, Any]:
    return {
        "name": spec.name,
        "description": spec.description,
        "input_schema": deepcopy(spec.input_schema),
    }


def _tool_result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, sort_keys=True, ensure_ascii=False, default=str)


def to_anthropic_messages(
    messages: Sequence[Mapping[str, Any]],
) -> tuple[str | None, list[dict[str, Any]]]:
    """Convert the recorder transcript into ``(system, messages)``.

    * The leading ``system`` message becomes the top-level system prompt.
    * Assistant turns that carry ``provider_content`` are replayed verbatim
      (thinking blocks included). Otherwise text + tool_use blocks are built
      from the neutral fields, using ProofTrail's tool_call ids.
    * Consecutive ``tool`` messages are merged into one user message holding
      every ``tool_result`` block, as the API requires for parallel calls.
    """

    system_parts: list[str] = []
    out: list[dict[str, Any]] = []
    id_map: dict[str, str] = {}
    pending_results: list[dict[str, Any]] = []

    def flush_results() -> None:
        if pending_results:
            out.append({"role": "user", "content": list(pending_results)})
            pending_results.clear()

    for message in messages:
        role = message.get("role")
        if role == "system":
            if out or pending_results:
                raise ValueError("system messages must precede the conversation")
            system_parts.append(str(message.get("content", "")))
        elif role == "user":
            flush_results()
            out.append(
                {"role": "user", "content": [{"type": "text", "text": str(message.get("content", ""))}]}
            )
        elif role == "assistant":
            flush_results()
            calls = list(message.get("tool_calls") or [])
            for call in calls:
                id_map[call["id"]] = call.get("provider_call_id") or call["id"]
            provider_content = message.get("provider_content")
            if provider_content:
                content = deepcopy(list(provider_content))
            else:
                content = []
                text = str(message.get("content") or "")
                if text:
                    content.append({"type": "text", "text": text})
                for call in calls:
                    content.append(
                        {
                            "type": "tool_use",
                            "id": id_map[call["id"]],
                            "name": call["name"],
                            "input": deepcopy(dict(call.get("arguments") or {})),
                        }
                    )
            if content:
                out.append({"role": "assistant", "content": content})
        elif role == "tool":
            call_id = str(message["tool_call_id"])
            block: dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": id_map.get(call_id, call_id),
                "content": _tool_result_text(message.get("content")),
            }
            if message.get("is_error"):
                block["is_error"] = True
            pending_results.append(block)
        else:
            raise ValueError(f"unsupported message role {role!r}")

    flush_results()
    system = "\n\n".join(part for part in system_parts if part) or None
    return system, out


# --------------------------------------------------------------------------- #
# Anthropic response  ->  provider-neutral ModelResponse
# --------------------------------------------------------------------------- #
def _as_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, Mapping):
        return dict(obj)
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        return dump(mode="json", exclude_none=True)
    return {key: value for key, value in vars(obj).items() if value is not None}


def compute_cost_usd(
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read_input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
) -> float:
    base = cost_usd(model, input_tokens, output_tokens)
    input_price = pricing_for(model)[0]
    cache_cost = (
        cache_read_input_tokens * input_price * CACHE_READ_MULTIPLIER
        + cache_creation_input_tokens * input_price * CACHE_WRITE_MULTIPLIER
    ) / 1_000_000
    return round(base + cache_cost, 6)


def from_anthropic_message(
    message: Any,
    *,
    model: str,
    prompt_hash: str,
    attempts: int = 1,
) -> ModelResponse:
    texts: list[str] = []
    calls: list[ToolCall] = []
    raw_blocks: list[dict[str, Any]] = []
    for block in message.content:
        data = _as_dict(block)
        raw_blocks.append(data)
        kind = data.get("type")
        if kind == "text":
            texts.append(str(data.get("text", "")))
        elif kind == "tool_use":
            calls.append(
                ToolCall(
                    name=str(data["name"]),
                    arguments=dict(data.get("input") or {}),
                    provider_call_id=data.get("id"),
                )
            )

    usage_raw = _as_dict(getattr(message, "usage", None))
    input_tokens = int(usage_raw.get("input_tokens") or 0)
    output_tokens = int(usage_raw.get("output_tokens") or 0)
    cache_read = int(usage_raw.get("cache_read_input_tokens") or 0)
    cache_write = int(usage_raw.get("cache_creation_input_tokens") or 0)
    cost = compute_cost_usd(
        model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_write,
    )
    usage = Usage(
        input_tokens=input_tokens + cache_read + cache_write,
        output_tokens=output_tokens,
        cost_usd=cost,
        llm_calls=1,
    )
    stop_reason = getattr(message, "stop_reason", None)
    metadata: dict[str, Any] = {
        "provider": PROVIDER_NAME,
        "requested_model": model,
        "model": getattr(message, "model", None) or model,
        "response_id": getattr(message, "id", None),
        "prompt_sha256": prompt_hash,
        "stop_reason": stop_reason,
        "attempts": attempts,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_input_tokens": cache_read,
            "cache_creation_input_tokens": cache_write,
            "cost_usd": cost,
        },
        "tool_call_ids": [call.provider_call_id for call in calls],
    }
    stop_details = getattr(message, "stop_details", None)
    if stop_details is not None:
        metadata["stop_details"] = _as_dict(stop_details)

    return ModelResponse(
        text="\n".join(texts).strip(),
        tool_calls=tuple(calls),
        usage=usage,
        stop_reason=stop_reason,
        raw_content=tuple(raw_blocks),
        metadata=metadata,
    )


# --------------------------------------------------------------------------- #
# The client
# --------------------------------------------------------------------------- #
class AnthropicModelClient:
    """``ModelClient`` implementation over the Anthropic Messages API."""

    is_live_model = True

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        client: Any | None = None,
        budget: BudgetGuard | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        timeout_seconds: float = 300.0,
        label: str = "live",
    ):
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        self.model_name = model or MODEL
        # Fail here, before any key is read or any request is built: a model
        # without a configured price can never be budgeted honestly.
        pricing_for(self.model_name)
        self.budget = budget
        self.max_retries = max_retries
        self.label = label
        self._retry_base_delay = retry_base_delay
        self._sleep = sleep
        self.calls: list[dict[str, Any]] = []
        self._client = client if client is not None else self._build_sdk_client(api_key, timeout_seconds)

    @staticmethod
    def _build_sdk_client(api_key: str | None, timeout_seconds: float) -> Any:
        key = api_key or os.environ.get(API_KEY_ENV, "").strip()
        if not key:
            raise MissingApiKeyError(
                f"set {API_KEY_ENV} in the environment (never in code or .env.example) to run live"
            )
        try:
            import anthropic  # local import keeps the core package dependency-free
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise RuntimeError('install the live extra: python -m pip install -e ".[live]"') from exc
        # SDK retries are disabled so the bounded retry policy below is the only one.
        return anthropic.Anthropic(api_key=key, max_retries=0, timeout=timeout_seconds)

    def build_request(
        self,
        *,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[ToolSpec],
        max_output_tokens: int,
        effort: str,
    ) -> dict[str, Any]:
        system, api_messages = to_anthropic_messages(messages)
        request: dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": max_output_tokens,
            "messages": api_messages,
            "tools": [to_anthropic_tool(tool) for tool in tools],
            "output_config": {"effort": effort},
        }
        if system:
            request["system"] = system
        return request

    def complete(
        self,
        *,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[ToolSpec],
        max_output_tokens: int,
        effort: str,
    ) -> ModelResponse:
        request = self.build_request(
            messages=messages, tools=tools, max_output_tokens=max_output_tokens, effort=effort
        )
        prompt_hash = prompt_sha256(
            model=self.model_name,
            messages=messages,
            tools=tools,
            max_output_tokens=max_output_tokens,
            effort=effort,
        )
        if self.budget is not None:
            estimate = self.budget.estimate_call_cost(
                self.model_name,
                prompt_bytes=len(json.dumps(request, default=str, ensure_ascii=False).encode("utf-8")),
                max_output_tokens=max_output_tokens,
                attempts=self.max_retries + 1,
            )
            self.budget.authorize(estimate, description=f"{self.label} prompt {prompt_hash[:12]}")

        message, attempts = self._call_with_retry(request)
        response = from_anthropic_message(
            message, model=self.model_name, prompt_hash=prompt_hash, attempts=attempts
        )
        if self.budget is not None:
            self.budget.record(
                model=self.model_name,
                label=self.label,
                usage=response.metadata["usage"],
                prompt_sha256=prompt_hash,
                response_id=response.metadata.get("response_id"),
            )
        self.calls.append(
            {
                "prompt_sha256": prompt_hash,
                "attempts": attempts,
                "stop_reason": response.stop_reason,
                "usage": dict(response.metadata["usage"]),
                "tool_calls": [call.name for call in response.tool_calls],
            }
        )
        return response

    def _call_with_retry(self, request: Mapping[str, Any]) -> tuple[Any, int]:
        attempts = 0
        while True:
            attempts += 1
            try:
                return self._client.messages.create(**request), attempts
            except Exception as exc:
                if not is_transient_error(exc) or attempts > self.max_retries:
                    raise
                self._sleep(self._retry_base_delay * (2 ** (attempts - 1)))


__all__ = [
    "API_KEY_ENV",
    "AnthropicModelClient",
    "MissingApiKeyError",
    "ProviderTransientError",
    "compute_cost_usd",
    "from_anthropic_message",
    "is_transient_error",
    "to_anthropic_messages",
    "to_anthropic_tool",
]
