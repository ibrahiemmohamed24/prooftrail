"""Free-tier Gemini REST adapter behind the provider-neutral ``ModelClient``.

The adapter intentionally uses the documented ``generateContent`` REST API and
the Python standard library.  This keeps judge replay dependency-free while a
real recording run can use a free Google AI Studio key.  Provider response
parts are preserved byte-for-byte at the JSON level, including Gemini 3
``thoughtSignature`` fields required for multi-step function calling.

Safety and honesty boundaries:

* The API key is read only from ``GEMINI_API_KEY`` and is sent in an HTTP
  header.  It is never placed in a URL, prompt hash, trace, cache, or log.
* A caller must explicitly confirm that the key's AI Studio plan says ``Free``.
  Only then is billed cost recorded as USD 0.00.  Token usage and a paid-tier
  list-price equivalent remain in metadata for transparent reporting.
* Requests are paced for free-tier quotas.  Network/429/5xx failures are retried
  with bounded backoff; tool execution remains outside this adapter and is
  therefore never repeated by a provider retry.
"""
from __future__ import annotations

import json
import os
import socket
import time
from copy import deepcopy
from dataclasses import dataclass
from email.message import Message
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from ..schemas import Usage
from .interfaces import ModelResponse, ToolCall, ToolSpec, prompt_sha256

GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
GEMINI_FREE_TIER_ENV = "PROOFTRAIL_GEMINI_FREE_TIER"
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
GEMINI_PROVIDER_NAME = "google-gemini"
DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# Models documented with a Gemini Developer API free tier on 2026-08-29.
# Access still depends on the active project's quota, which the user verifies
# in AI Studio before setting GEMINI_FREE_TIER_ENV=1.
FREE_TIER_MODELS = frozenset(
    {
        "gemini-3.7-flash",
        "gemini-3.1-flash-lite",
        "gemini-3-flash-preview",
    }
)

# Paid-tier standard prices, USD per 1M tokens, used only to report an
# equivalent value.  They are never presented as billed free-tier spend.
LIST_PRICE_PER_MTOK: dict[str, tuple[float, float]] = {
    "gemini-3.7-flash": (0.75, 3.75),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3-flash-preview": (0.50, 3.00),
}

TRANSIENT_STATUS_CODES = frozenset({408, 409, 429, 500, 502, 503, 504})
_TRUE_VALUES = frozenset({"1", "true", "yes", "free"})


class MissingGeminiApiKeyError(RuntimeError):
    """No Gemini key was supplied and the provider environment variable is unset."""


class FreeTierConfirmationError(RuntimeError):
    """The caller did not attest that the selected AI Studio project is Free."""


class GeminiResponseError(RuntimeError):
    """The provider returned a syntactically valid response with no candidate."""


@dataclass
class GeminiTransportError(RuntimeError):
    """HTTP/network failure carrying retry metadata without exposing secrets."""

    message: str
    status_code: int | None = None
    retry_after_seconds: float | None = None

    def __str__(self) -> str:
        status = f" (HTTP {self.status_code})" if self.status_code is not None else ""
        return f"{self.message}{status}"


Transport = Callable[[str, Mapping[str, str], Mapping[str, Any], float], Mapping[str, Any]]


def _confirmed(value: bool | None) -> bool:
    if value is not None:
        return value
    return os.environ.get(GEMINI_FREE_TIER_ENV, "").strip().casefold() in _TRUE_VALUES


def list_price_equivalent_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return paid-tier equivalent cost for context, never billed free-tier cost."""

    prices = LIST_PRICE_PER_MTOK.get(model)
    if prices is None:
        return 0.0
    input_price, output_price = prices
    return round((input_tokens * input_price + output_tokens * output_price) / 1_000_000, 6)


def to_gemini_tool(spec: ToolSpec) -> dict[str, Any]:
    """Translate one provider-neutral tool using Gemini's JSON-Schema field."""

    return {
        "name": spec.name,
        "description": spec.description,
        "parametersJsonSchema": deepcopy(spec.input_schema),
    }


def to_gemini_contents(
    messages: Sequence[Mapping[str, Any]],
) -> tuple[str | None, list[dict[str, Any]]]:
    """Convert the recorder transcript into ``(system, contents)``.

    Assistant ``provider_content`` is copied as-is so thought signatures stay
    on the exact parts where Gemini returned them.  Consecutive tool results are
    grouped into one user content item, matching Gemini's parallel-call format.
    """

    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []
    provider_ids: dict[str, str | None] = {}
    pending_results: list[dict[str, Any]] = []

    def flush_results() -> None:
        if pending_results:
            contents.append({"role": "user", "parts": list(pending_results)})
            pending_results.clear()

    for message in messages:
        role = message.get("role")
        if role == "system":
            if contents or pending_results:
                raise ValueError("system messages must precede the conversation")
            system_parts.append(str(message.get("content", "")))
            continue
        if role == "user":
            flush_results()
            contents.append({"role": "user", "parts": [{"text": str(message.get("content", ""))}]})
            continue
        if role == "assistant":
            flush_results()
            calls = list(message.get("tool_calls") or [])
            for call in calls:
                provider_ids[str(call["id"])] = call.get("provider_call_id")
            raw_parts = message.get("provider_content")
            if raw_parts:
                parts = deepcopy(list(raw_parts))
            else:
                parts: list[dict[str, Any]] = []
                text = str(message.get("content") or "")
                if text:
                    parts.append({"text": text})
                for call in calls:
                    function_call: dict[str, Any] = {
                        "name": call["name"],
                        "args": deepcopy(dict(call.get("arguments") or {})),
                    }
                    provider_id = provider_ids[str(call["id"])]
                    if provider_id:
                        function_call["id"] = provider_id
                    parts.append({"functionCall": function_call})
            if parts:
                contents.append({"role": "model", "parts": parts})
            continue
        if role == "tool":
            call_id = str(message["tool_call_id"])
            response = deepcopy(message.get("content"))
            if not isinstance(response, Mapping):
                response = {"result": response}
            function_response: dict[str, Any] = {
                "name": str(message["name"]),
                "response": dict(response),
            }
            provider_id = provider_ids.get(call_id)
            if provider_id:
                function_response["id"] = provider_id
            pending_results.append({"functionResponse": function_response})
            continue
        raise ValueError(f"unsupported message role {role!r}")

    flush_results()
    system = "\n\n".join(part for part in system_parts if part) or None
    return system, contents


def _stop_reason(finish_reason: str | None, has_tool_calls: bool) -> str:
    if has_tool_calls:
        return "tool_use"
    normalized = (finish_reason or "STOP").upper()
    return {
        "STOP": "end_turn",
        "MAX_TOKENS": "max_tokens",
        "SAFETY": "safety",
        "RECITATION": "recitation",
        "BLOCKLIST": "blocklist",
        "PROHIBITED_CONTENT": "prohibited_content",
    }.get(normalized, normalized.casefold())


def from_gemini_response(
    payload: Mapping[str, Any],
    *,
    model: str,
    prompt_hash: str,
    attempts: int = 1,
) -> ModelResponse:
    """Translate a Gemini ``GenerateContentResponse`` into ``ModelResponse``."""

    candidates = list(payload.get("candidates") or [])
    if not candidates:
        feedback = payload.get("promptFeedback") or {}
        reason = feedback.get("blockReason") if isinstance(feedback, Mapping) else None
        raise GeminiResponseError(f"Gemini returned no candidates; block_reason={reason or 'unknown'}")

    candidate = dict(candidates[0])
    content = candidate.get("content") or {}
    parts = deepcopy(list(content.get("parts") or [])) if isinstance(content, Mapping) else []
    texts: list[str] = []
    calls: list[ToolCall] = []
    for part in parts:
        if "text" in part and not part.get("thought"):
            text = str(part.get("text") or "")
            if text:
                texts.append(text)
        function_call = part.get("functionCall")
        if isinstance(function_call, Mapping):
            calls.append(
                ToolCall(
                    name=str(function_call["name"]),
                    arguments=deepcopy(dict(function_call.get("args") or {})),
                    provider_call_id=function_call.get("id"),
                )
            )

    usage_raw = dict(payload.get("usageMetadata") or {})
    input_tokens = int(usage_raw.get("promptTokenCount") or 0)
    candidate_tokens = int(usage_raw.get("candidatesTokenCount") or 0)
    thought_tokens = int(usage_raw.get("thoughtsTokenCount") or 0)
    output_tokens = candidate_tokens + thought_tokens
    equivalent = list_price_equivalent_usd(model, input_tokens, output_tokens)
    finish_reason = candidate.get("finishReason")
    stop_reason = _stop_reason(str(finish_reason) if finish_reason else None, bool(calls))

    metadata: dict[str, Any] = {
        "provider": GEMINI_PROVIDER_NAME,
        "pricing_tier": "free",
        "billed_cost_usd": 0.0,
        "list_price_equivalent_usd": equivalent,
        "requested_model": model,
        "model": payload.get("modelVersion") or model,
        "response_id": payload.get("responseId"),
        "prompt_sha256": prompt_hash,
        "stop_reason": stop_reason,
        "provider_finish_reason": finish_reason,
        "attempts": attempts,
        "usage": {
            "input_tokens": input_tokens,
            "candidate_tokens": candidate_tokens,
            "thought_tokens": thought_tokens,
            "output_tokens": output_tokens,
            "total_tokens": int(usage_raw.get("totalTokenCount") or input_tokens + output_tokens),
            "service_tier": usage_raw.get("serviceTier"),
            "cost_usd": 0.0,
            "list_price_equivalent_usd": equivalent,
        },
        "tool_call_ids": [call.provider_call_id for call in calls],
    }
    if payload.get("modelStatus") is not None:
        metadata["model_status"] = deepcopy(payload["modelStatus"])

    return ModelResponse(
        text="\n".join(texts).strip(),
        tool_calls=tuple(calls),
        usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=0.0, llm_calls=1),
        stop_reason=stop_reason,
        raw_content=tuple(parts),
        metadata=metadata,
    )


def _retry_after(headers: Message | Mapping[str, str] | None) -> float | None:
    if headers is None:
        return None
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


def urllib_transport(
    url: str,
    headers: Mapping[str, str],
    payload: Mapping[str, Any],
    timeout_seconds: float,
) -> Mapping[str, Any]:
    """POST JSON with urllib while redacting the key from raised errors."""

    data = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=data, headers=dict(headers), method="POST")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - fixed Google host
            try:
                return json.loads(response.read().decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise GeminiTransportError("Gemini returned invalid JSON", status_code=502) from exc
    except HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw)
            detail = parsed.get("error", {}).get("message") or "Gemini API request failed"
        except (OSError, ValueError, AttributeError):
            detail = "Gemini API request failed"
        raise GeminiTransportError(
            str(detail), status_code=exc.code, retry_after_seconds=_retry_after(exc.headers)
        ) from exc
    except (URLError, TimeoutError, socket.timeout, ConnectionError) as exc:
        raise GeminiTransportError(f"Gemini network error: {type(exc).__name__}") from exc


class GeminiModelClient:
    """``ModelClient`` implementation for free-tier Gemini GenerateContent."""

    is_live_model = True

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        free_tier_confirmed: bool | None = None,
        transport: Transport = urllib_transport,
        base_url: str = DEFAULT_BASE_URL,
        max_retries: int = 5,
        retry_base_delay: float = 2.0,
        max_retry_delay: float = 60.0,
        min_interval_seconds: float = 4.0,
        timeout_seconds: float = 180.0,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        label: str = "live-free-tier",
    ):
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        selected_model = model or DEFAULT_GEMINI_MODEL
        if selected_model not in FREE_TIER_MODELS:
            raise FreeTierConfirmationError(
                f"{selected_model!r} is not in ProofTrail's reviewed free-tier allowlist; "
                "select a documented free model before recording billed cost as $0"
            )
        if not _confirmed(free_tier_confirmed):
            raise FreeTierConfirmationError(
                f"verify that the API key's Plan column says Free in Google AI Studio, then set "
                f"{GEMINI_FREE_TIER_ENV}=1 in the current shell"
            )
        key = api_key or os.environ.get(GEMINI_API_KEY_ENV, "").strip()
        if not key:
            raise MissingGeminiApiKeyError(
                f"set {GEMINI_API_KEY_ENV} in the environment (never in code or a committed file)"
            )

        self.model_name = selected_model
        self.label = label
        self.max_retries = max_retries
        self._api_key = key
        self._transport = transport
        self._base_url = base_url.rstrip("/")
        self._retry_base_delay = retry_base_delay
        self._max_retry_delay = max_retry_delay
        self._min_interval_seconds = max(0.0, min_interval_seconds)
        self._timeout_seconds = timeout_seconds
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request_at: float | None = None
        self.calls: list[dict[str, Any]] = []

    def build_request(
        self,
        *,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[ToolSpec],
        max_output_tokens: int,
        effort: str,
    ) -> dict[str, Any]:
        system, contents = to_gemini_contents(messages)
        request: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_output_tokens,
                "thinkingConfig": {"thinkingLevel": effort},
            },
        }
        if system:
            request["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            request["tools"] = [{"functionDeclarations": [to_gemini_tool(tool) for tool in tools]}]
            request["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}
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
            messages=messages,
            tools=tools,
            max_output_tokens=max_output_tokens,
            effort=effort,
        )
        prompt_hash = prompt_sha256(
            model=self.model_name,
            messages=messages,
            tools=tools,
            max_output_tokens=max_output_tokens,
            effort=effort,
        )
        payload, attempts = self._call_with_retry(request)
        response = from_gemini_response(
            payload, model=self.model_name, prompt_hash=prompt_hash, attempts=attempts
        )
        self.calls.append(
            {
                "prompt_sha256": prompt_hash,
                "attempts": attempts,
                "stop_reason": response.stop_reason,
                "usage": deepcopy(response.metadata["usage"]),
                "tool_calls": [call.name for call in response.tool_calls],
            }
        )
        return response

    def _call_with_retry(self, payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], int]:
        endpoint = (
            f"{self._base_url}/models/{quote(self.model_name, safe='-._')}:generateContent"
        )
        # Deliberately use a header, not ?key=..., so traces and proxy URL logs
        # cannot contain the credential.
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "x-goog-api-key": self._api_key,
        }
        attempts = 0
        while True:
            attempts += 1
            self._pace()
            try:
                result = self._transport(endpoint, headers, payload, self._timeout_seconds)
                self._last_request_at = self._monotonic()
                return result, attempts
            except GeminiTransportError as exc:
                self._last_request_at = self._monotonic()
                transient = exc.status_code is None or exc.status_code in TRANSIENT_STATUS_CODES
                if not transient or attempts > self.max_retries:
                    raise
                exponential = self._retry_base_delay * (2 ** (attempts - 1))
                requested = exc.retry_after_seconds or 0.0
                self._sleep(min(self._max_retry_delay, max(exponential, requested)))

    def _pace(self) -> None:
        if self._last_request_at is None or self._min_interval_seconds <= 0:
            return
        elapsed = self._monotonic() - self._last_request_at
        remaining = self._min_interval_seconds - elapsed
        if remaining > 0:
            self._sleep(remaining)


__all__ = [
    "DEFAULT_GEMINI_MODEL",
    "FREE_TIER_MODELS",
    "GEMINI_API_KEY_ENV",
    "GEMINI_FREE_TIER_ENV",
    "FreeTierConfirmationError",
    "GeminiModelClient",
    "GeminiResponseError",
    "GeminiTransportError",
    "MissingGeminiApiKeyError",
    "from_gemini_response",
    "list_price_equivalent_usd",
    "to_gemini_contents",
    "to_gemini_tool",
]
