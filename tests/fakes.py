"""Offline stand-ins for the Anthropic SDK used by the live-provider tests.

Nothing here touches the network. The fake client returns duck-typed message
objects shaped like ``anthropic.types.Message`` so the adapter is exercised
without importing the SDK at all.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from prooftrail.ids import idempotency_key as make_idempotency_key


@dataclass
class FakeUsage:
    input_tokens: int = 100
    output_tokens: int = 20
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class FakeBlock:
    type: str
    text: str | None = None
    id: str | None = None
    name: str | None = None
    input: dict[str, Any] | None = None
    thinking: str | None = None
    signature: str | None = None


@dataclass
class FakeMessage:
    content: list[FakeBlock]
    stop_reason: str
    usage: FakeUsage = field(default_factory=FakeUsage)
    id: str = "msg_fake"
    model: str = "claude-opus-5"
    stop_details: Any = None


def text_turn(text: str, **usage: int) -> FakeMessage:
    return FakeMessage([FakeBlock("text", text=text)], "end_turn", FakeUsage(**usage))


def tool_turn(
    name: str,
    arguments: dict[str, Any],
    *,
    call_id: str,
    thinking: str | None = "(thinking)",
    text: str | None = None,
    **usage: int,
) -> FakeMessage:
    blocks: list[FakeBlock] = []
    if thinking is not None:
        blocks.append(FakeBlock("thinking", thinking=thinking, signature=f"sig_{call_id}"))
    if text:
        blocks.append(FakeBlock("text", text=text))
    blocks.append(FakeBlock("tool_use", id=call_id, name=name, input=dict(arguments)))
    return FakeMessage(blocks, "tool_use", FakeUsage(**usage), id=f"msg_{call_id}")


class FakeMessages:
    """``client.messages`` replacement: scripted responses plus optional failures."""

    def __init__(self, responses: list[FakeMessage | Exception]):
        self._queue = list(responses)
        self.requests: list[dict[str, Any]] = []

    def create(self, **request: Any) -> FakeMessage:
        self.requests.append(request)
        if not self._queue:
            raise AssertionError("fake provider ran out of scripted responses")
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeAnthropic:
    def __init__(self, responses: list[FakeMessage | Exception]):
        self.messages = FakeMessages(responses)


def fake_live_factory(script_builder):
    """Return a ``build_live_client`` replacement driven by ``script_builder``.

    ``script_builder(order_id=..., intent_id=..., amount_cents=...)`` receives
    the first order and intent of the labelled case and returns the provider
    messages to play back.
    """

    from prooftrail.agent.anthropic_client import AnthropicModelClient
    from prooftrail.scenarios import generate_scenario

    def build(*, model, budget, label):
        family, _, seed = label.partition("-s")
        scenario = generate_scenario(family, int(seed))
        try:
            request = scenario.user_requests[0]
            order = scenario.seeded.orders[0]
            script = script_builder(
                order_id=order["order_id"], intent_id=request.intent_id, amount_cents=order["amount_cents"]
            )
        finally:
            scenario.close()
        return AnthropicModelClient(
            model=model, client=FakeAnthropic(script), budget=budget, label=label, sleep=lambda _s: None
        )

    return build


def blind_retry_script(*, order_id: str, intent_id: str, amount_cents: int) -> list[FakeMessage]:
    """The killer-demo behaviour expressed as provider messages (F02 fixture)."""

    business_args = {"order_id": order_id, "amount_cents": amount_cents}
    call_args = {
        **business_args,
        "intent_id": intent_id,
        "idempotency_key": make_idempotency_key(intent_id, "issue_refund", business_args),
    }
    return [
        tool_turn("issue_refund", call_args, call_id="toolu_01", input_tokens=120, output_tokens=30),
        tool_turn("issue_refund", call_args, call_id="toolu_02", input_tokens=180, output_tokens=25),
        text_turn(f"I refunded ${amount_cents / 100:.2f} for order {order_id}.", input_tokens=220, output_tokens=18),
    ]
