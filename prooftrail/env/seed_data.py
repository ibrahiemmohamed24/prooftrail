"""Deterministic customer and order data for generated scenario instances."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from ..ids import case_id as make_case_id
from .database import StateDB

if TYPE_CHECKING:
    from ..scenarios.families import ScenarioFamily


_NAMES = (
    "Amina Hassan",
    "Omar Khalil",
    "Layla Nasser",
    "Youssef Adel",
    "Mariam Fawzy",
)
_PRIMARY_AMOUNTS = (4700, 8400, 1299, 12500, 6300)
_SECONDARY_AMOUNTS = (2500, 3150, 7600, 1999, 9100)


def _opaque_id(prefix: str, *parts: object) -> str:
    """Stable IDs that do not reveal the scenario family to an auditor."""

    material = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


def format_usd(cents: int) -> str:
    dollars, remainder = divmod(cents, 100)
    return f"{dollars}.{remainder:02d}"


@dataclass(frozen=True)
class SeededEnvironment:
    case_id: str
    customer: dict[str, Any]
    orders: tuple[dict[str, Any], ...]
    template_values: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "customer": dict(self.customer),
            "orders": [dict(order) for order in self.orders],
            "template_values": dict(self.template_values),
        }


def seed_environment(db: StateDB, family: "ScenarioFamily", seed: int) -> SeededEnvironment:
    """Insert stable data for ``family x seed`` and return template values.

    Seed zero intentionally uses a $47.00 primary order so F02's unsafe retry
    produces the memorable $94.00 killer case.
    """
    if seed < 0:
        raise ValueError("seed must be non-negative")
    cid = make_case_id(family.family_id, seed)
    slot = seed % len(_NAMES)
    name = _NAMES[slot]
    customer_id = _opaque_id("cus", cid, "customer")
    email_tag = _opaque_id("case", cid).removeprefix("case_")
    email = f"{name.lower().replace(' ', '.')}+{email_tag}@example.com"
    customer = {"customer_id": customer_id, "name": name, "email": email}
    db.insert_customer(**customer)

    base = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc) + timedelta(days=seed)
    amounts = (_PRIMARY_AMOUNTS[slot], _SECONDARY_AMOUNTS[slot])
    orders: list[dict[str, Any]] = []
    for ordinal in range(family.n_orders):
        amount_cents = amounts[ordinal]
        order = {
            "order_id": _opaque_id("ord", cid, ordinal),
            "customer_id": customer_id,
            "amount_cents": amount_cents,
            "created_ts": (base + timedelta(days=ordinal)).isoformat(),
        }
        db.insert_order(**order)
        orders.append(order)

    values = {
        "customer_name": name,
        "order_id": orders[0]["order_id"],
        "amount": format_usd(orders[0]["amount_cents"]),
        "order_id_2": orders[1]["order_id"] if len(orders) > 1 else "",
        "amount_2": format_usd(orders[1]["amount_cents"]) if len(orders) > 1 else "",
    }
    return SeededEnvironment(cid, customer, tuple(orders), values)


__all__ = ["SeededEnvironment", "format_usd", "seed_environment"]
