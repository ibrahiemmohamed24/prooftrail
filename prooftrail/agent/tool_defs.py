"""Model-facing tool definitions and adapters for the refund environment."""
from __future__ import annotations

from collections.abc import Callable

from .adapters import DispatchToolSuite, ToolSuiteAction
from .interfaces import ToolSpec


LOOKUP_CUSTOMER = ToolSpec(
    "lookup_customer",
    "Look up a customer by their internal customer ID.",
    {
        "type": "object",
        "properties": {"customer_id": {"type": "string"}},
        "required": ["customer_id"],
        "additionalProperties": False,
    },
)

LOOKUP_ORDER = ToolSpec(
    "lookup_order",
    "Look up an order and its current refund state.",
    {
        "type": "object",
        "properties": {"order_id": {"type": "string"}},
        "required": ["order_id"],
        "additionalProperties": False,
    },
)

LIST_REFUNDS = ToolSpec(
    "list_refunds",
    "List committed refund records for an order.",
    {
        "type": "object",
        "properties": {"order_id": {"type": "string"}},
        "required": ["order_id"],
        "additionalProperties": False,
    },
)

ISSUE_REFUND = ToolSpec(
    "issue_refund",
    "Issue a refund in integer cents. A timeout means the outcome is unknown.",
    {
        "type": "object",
        "properties": {
            "order_id": {"type": "string"},
            "amount_cents": {"type": "integer", "minimum": 1},
        },
        "required": ["order_id", "amount_cents"],
        "additionalProperties": False,
    },
)

SEND_EMAIL = ToolSpec(
    "send_email",
    "Send an external email confirmation. This side effect is not in the payment ledger.",
    {
        "type": "object",
        "properties": {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["to", "subject", "body"],
        "additionalProperties": False,
    },
)

REFUND_TOOL_SPECS = (LOOKUP_CUSTOMER, LOOKUP_ORDER, LIST_REFUNDS, ISSUE_REFUND, SEND_EMAIL)


def build_refund_tool_actions(
    suite: DispatchToolSuite,
    sequence_reader: Callable[[], int | None],
) -> tuple[ToolSuiteAction, ...]:
    """Connect the provider-neutral agent loop to a stateful tool suite."""

    actions = []
    for spec in REFUND_TOOL_SPECS:
        actions.append(
            ToolSuiteAction(
                suite=suite,
                spec=spec,
                pass_idempotency_key=spec.name == "issue_refund",
                sequence_reader=None if spec.name == "send_email" else sequence_reader,
            )
        )
    return tuple(actions)


__all__ = [
    "ISSUE_REFUND",
    "LIST_REFUNDS",
    "LOOKUP_CUSTOMER",
    "LOOKUP_ORDER",
    "REFUND_TOOL_SPECS",
    "SEND_EMAIL",
    "build_refund_tool_actions",
]
