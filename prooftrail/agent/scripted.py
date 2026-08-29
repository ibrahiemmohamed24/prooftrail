"""Deterministic offline model adapter used for demos and replay tests.

This class is intentionally named and marked as *scripted*. It does not call,
simulate, benchmark or claim to be a real LLM; it simply returns a fixed list
of provider-neutral turns. Live traces must use a separate ``ModelClient``
adapter whose ``is_live_model`` flag is true.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from ..ids import idempotency_key as make_idempotency_key
from .interfaces import ModelResponse, ToolCall, ToolSpec


class ScriptExhaustedError(RuntimeError):
    pass


class ScriptedModelClient:
    """Return pre-recorded responses in order, with zero network access."""

    is_live_model = False

    def __init__(
        self,
        responses: Sequence[ModelResponse],
        *,
        model_name: str = "scripted-replay-not-a-real-llm",
    ):
        if not responses:
            raise ValueError("a scripted client needs at least one response")
        self.model_name = model_name
        self._responses = tuple(ModelResponse.from_dict(r.to_dict()) for r in responses)
        self._position = 0
        self.calls: list[dict[str, Any]] = []

    @property
    def remaining(self) -> int:
        return len(self._responses) - self._position

    @property
    def responses(self) -> tuple[ModelResponse, ...]:
        return tuple(ModelResponse.from_dict(r.to_dict()) for r in self._responses)

    def complete(
        self,
        *,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[ToolSpec],
        max_output_tokens: int,
        effort: str,
    ) -> ModelResponse:
        self.calls.append(
            {
                "messages": deepcopy(list(messages)),
                "tools": [t.to_dict() for t in tools],
                "max_output_tokens": max_output_tokens,
                "effort": effort,
            }
        )
        if self._position >= len(self._responses):
            raise ScriptExhaustedError(
                f"script exhausted after {self._position} completion calls"
            )
        response = self._responses[self._position]
        self._position += 1
        return ModelResponse.from_dict(response.to_dict())

    @classmethod
    def blind_refund_retry_demo(
        cls,
        *,
        order_id: str,
        intent_id: str,
        amount_cents: int = 4700,
    ) -> "ScriptedModelClient":
        """Build the deterministic $47 killer-demo behaviour.

        The first call is followed by a blind retry regardless of the tool
        result. The final report claims one refund even if both attempts
        committed. This is an offline fixture, not evidence of real-model
        behaviour.
        """
        business_args = {"order_id": order_id, "amount_cents": amount_cents}
        idem = make_idempotency_key(intent_id, "issue_refund", business_args)
        call_args = {
            **business_args,
            "intent_id": intent_id,
            "idempotency_key": idem,
        }
        amount = f"{amount_cents / 100:.2f}"
        return cls(
            [
                ModelResponse(tool_calls=(ToolCall("issue_refund", dict(call_args)),)),
                ModelResponse(tool_calls=(ToolCall("issue_refund", dict(call_args)),)),
                ModelResponse(
                    text=f"I refunded ${amount} for order {order_id}.",
                    stop_reason="end_turn",
                ),
            ]
        )
