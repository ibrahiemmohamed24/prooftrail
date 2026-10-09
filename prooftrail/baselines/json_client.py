"""Strict JSON audit completion over the existing provider-neutral client."""
from __future__ import annotations

import json
from typing import Any

from ..agent.interfaces import ModelClient
from ..schemas import Usage


class InvalidJSONCompletion(ValueError):
    """The provider did not return one plain JSON object."""


class ModelJSONCompletionClient:
    """Adapt a cached/live ``ModelClient`` to B1's one-shot JSON protocol.

    Parsing is intentionally strict. Markdown fences, prose around the object,
    tool calls and model mismatches are failures rather than silently repaired
    outputs.
    """

    def __init__(self, client: ModelClient):
        self.client = client

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
        max_output_tokens: int,
        effort: str,
    ) -> tuple[dict[str, Any], Usage]:
        if model != self.client.model_name:
            raise ValueError(
                f"audit requested model {model!r}, but the client is pinned to "
                f"{self.client.model_name!r}"
            )
        response = self.client.complete(
            messages=(
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ),
            tools=(),
            max_output_tokens=max_output_tokens,
            effort=effort,
        )
        if response.tool_calls:
            raise InvalidJSONCompletion("audit completion unexpectedly requested a tool")
        try:
            raw = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise InvalidJSONCompletion(f"audit completion is not plain JSON: {exc.msg}") from exc
        if not isinstance(raw, dict):
            raise InvalidJSONCompletion("audit completion must be one JSON object")
        return raw, response.usage


__all__ = ["InvalidJSONCompletion", "ModelJSONCompletionClient"]
