"""Stateful mock tools exposed to the refund agent.

The return value is the agent's view.  The ledger is the independent view of
what happened.  Faults deliberately make those views disagree, while every
``issue_refund`` event keeps the requested order and amount in a stable payload
shape for later evidence linking.
"""
from __future__ import annotations

from typing import Any, Callable

from ..ids import entity_ref, idempotency_key as make_idempotency_key
from ..schemas.events import EventType, LedgerEvent
from .database import StateDB
from .faults import FaultInjector, FaultKind, FaultSpec, ToolTimeout
from .ledger import Ledger


class IdempotencyConflict(RuntimeError):
    """A caller reused an idempotency key with different refund arguments."""


class RefundTool:
    """A small stateful refund-tool suite backed by :class:`StateDB`.

    ``send_email`` is intentionally outside the ledger.  It models an external
    side effect that ProofTrail cannot verify from its system of record.
    """

    ISSUE_REFUND = "issue_refund"

    def __init__(
        self,
        db: StateDB,
        ledger: Ledger,
        faults: FaultInjector | None = None,
        *,
        idempotency_enabled: bool = True,
    ) -> None:
        self.db = db
        self.ledger = ledger
        self.faults = faults or FaultInjector()
        self.idempotency_enabled = idempotency_enabled
        self.sent_emails: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ #
    # Public dispatch API used by the future agent tool loop
    # ------------------------------------------------------------------ #
    def call(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        intent_id: str,
        tool_call_id: str,
    ) -> dict[str, Any]:
        handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "lookup_customer": self.lookup_customer,
            "lookup_order": self.lookup_order,
            "list_refunds": self.list_refunds,
            self.ISSUE_REFUND: self.issue_refund,
            "send_email": self.send_email,
        }
        try:
            handler = handlers[tool_name]
        except KeyError:
            raise KeyError(f"unknown tool {tool_name!r}") from None
        return handler(intent_id=intent_id, tool_call_id=tool_call_id, **dict(args))

    # ------------------------------------------------------------------ #
    # Read tools.  Their returned data and ledger payload are identical.
    # ------------------------------------------------------------------ #
    def lookup_customer(
        self, customer_id: str, *, intent_id: str, tool_call_id: str
    ) -> dict[str, Any]:
        args = {"customer_id": customer_id}
        self._started("lookup_customer", intent_id, tool_call_id, args)
        customer = self.db.get_customer(customer_id)
        result = (
            {"ok": True, "customer": customer}
            if customer is not None
            else {"ok": False, "error": "customer_not_found", "customer_id": customer_id}
        )
        self._completed("lookup_customer", intent_id, tool_call_id, result)
        return result

    def lookup_order(
        self, order_id: str, *, intent_id: str, tool_call_id: str
    ) -> dict[str, Any]:
        args = {"order_id": order_id}
        self._started("lookup_order", intent_id, tool_call_id, args)
        order = self.db.get_order(order_id)
        result = (
            {"ok": True, "order": order}
            if order is not None
            else {"ok": False, "error": "order_not_found", "order_id": order_id}
        )
        self._completed("lookup_order", intent_id, tool_call_id, result)
        return result

    def list_refunds(
        self, order_id: str, *, intent_id: str, tool_call_id: str
    ) -> dict[str, Any]:
        args = {"order_id": order_id}
        self._started("list_refunds", intent_id, tool_call_id, args)
        order = self.db.get_order(order_id)
        result = (
            {"ok": True, "order_id": order_id, "refunds": self.db.list_refunds(order_id)}
            if order is not None
            else {"ok": False, "error": "order_not_found", "order_id": order_id, "refunds": []}
        )
        self._completed("list_refunds", intent_id, tool_call_id, result)
        return result

    # ------------------------------------------------------------------ #
    # The mutating tool and all six injected failure modes
    # ------------------------------------------------------------------ #
    def issue_refund(
        self,
        order_id: str,
        amount_cents: int,
        *,
        intent_id: str,
        tool_call_id: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        requested = self._refund_payload(order_id, amount_cents)
        key = idempotency_key or make_idempotency_key(
            intent_id, self.ISSUE_REFUND, {"order_id": order_id, "amount_cents": amount_cents}
        )
        self._started(
            self.ISSUE_REFUND,
            intent_id,
            tool_call_id,
            requested,
            idempotency_key=key,
        )

        call_index = self.faults.record_call(self.ISSUE_REFUND)
        fault = self.faults.active(self.ISSUE_REFUND, call_index, tool_call_id)

        if not isinstance(amount_cents, int) or isinstance(amount_cents, bool) or amount_cents <= 0:
            return self._refund_error(
                requested,
                intent_id,
                tool_call_id,
                key,
                ValueError("amount_cents must be a positive integer"),
            )
        requested_order = self.db.get_order(order_id)
        if requested_order is None:
            return self._refund_error(
                requested,
                intent_id,
                tool_call_id,
                key,
                KeyError(f"order {order_id} not found"),
            )

        # A safe retry returns the original transaction without another commit.
        existing = self.db.find_refund_by_idempotency_key(key) if self.idempotency_enabled else None
        if existing is not None:
            if existing["order_id"] != order_id or existing["amount_cents"] != amount_cents:
                return self._refund_error(
                    requested,
                    intent_id,
                    tool_call_id,
                    key,
                    IdempotencyConflict("idempotency key was already used with different arguments"),
                )
            snapshot = self.db.snapshot_order(order_id)
            replay_payload = {
                **requested,
                "ok": True,
                "replayed": True,
                "transaction_id": existing["transaction_id"],
                "refund_id": existing["refund_id"],
            }
            self.ledger.append(
                EventType.IDEMPOTENT_REPLAY,
                tool_name=self.ISSUE_REFUND,
                intent_id=intent_id,
                tool_call_id=tool_call_id,
                transaction_id=existing["transaction_id"],
                idempotency_key=key,
                entity=entity_ref("order", order_id),
                state_before=snapshot,
                state_after=snapshot,
                payload=replay_payload,
            )
            self._completed(
                self.ISSUE_REFUND,
                intent_id,
                tool_call_id,
                replay_payload,
                transaction_id=existing["transaction_id"],
                idempotency_key=key,
            )
            return replay_payload

        if fault is not None and fault.kind == FaultKind.TIMEOUT_BEFORE_COMMIT:
            self._timeout(
                requested,
                intent_id,
                tool_call_id,
                key,
                phase="before_commit",
                fault=fault,
            )

        if fault is not None and fault.kind == FaultKind.PHANTOM_SUCCESS:
            plausible_suffix = tool_call_id.removeprefix("tc_")
            result = {
                **requested,
                "ok": True,
                "status": "refunded",
                "transaction_id": f"txn_{plausible_suffix}",
                "refund_id": f"rf_{plausible_suffix}",
            }
            self._completed(
                self.ISSUE_REFUND,
                intent_id,
                tool_call_id,
                result,
                transaction_id=result["transaction_id"],
                idempotency_key=key,
            )
            return result

        actual_order_id = order_id
        actual_amount_cents = amount_cents
        if fault is not None and fault.kind == FaultKind.AMOUNT_DRIFT:
            actual_amount_cents += int(fault.params.get("delta_cents", 0))
        elif fault is not None and fault.kind == FaultKind.PARTIAL_COMMIT:
            fraction = float(fault.params.get("fraction", 0.5))
            actual_amount_cents = int(round(amount_cents * fraction))
        elif fault is not None and fault.kind == FaultKind.MISROUTED_WRITE:
            actual_order_id = self._other_order_id(requested_order)

        if actual_amount_cents <= 0:
            return self._refund_error(
                requested,
                intent_id,
                tool_call_id,
                key,
                ValueError("fault produced a non-positive committed amount"),
            )

        before = self.db.snapshot_order(actual_order_id)
        transaction_id = self.ledger.next_transaction_id()
        refund_id = f"rf_{transaction_id.removeprefix('txn_')}"
        self.db.begin()
        try:
            after = self.db.apply_refund(
                refund_id=refund_id,
                order_id=actual_order_id,
                amount_cents=actual_amount_cents,
                transaction_id=transaction_id,
                intent_id=intent_id,
                idempotency_key=key,
                tool_call_id=tool_call_id,
                created_ts=self.ledger.clock.now(),
            )
            state_payload = {
                **requested,
                "committed_order_id": actual_order_id,
                "committed_amount_cents": actual_amount_cents,
            }
            self.ledger.append(
                EventType.STATE_CHANGED,
                tool_name=self.ISSUE_REFUND,
                intent_id=intent_id,
                tool_call_id=tool_call_id,
                transaction_id=transaction_id,
                idempotency_key=key,
                entity=entity_ref("order", actual_order_id),
                state_before=before,
                state_after=after,
                payload=state_payload,
            )
            self.db.commit()
        except Exception as exc:
            if self.db.conn.in_transaction:
                self.db.rollback()
            return self._refund_error(requested, intent_id, tool_call_id, key, exc)

        if fault is not None and fault.kind == FaultKind.TIMEOUT_AFTER_COMMIT:
            self._timeout(
                requested,
                intent_id,
                tool_call_id,
                key,
                phase="after_commit",
                fault=fault,
                transaction_id=transaction_id,
            )

        # Drift, partial and misroute faults lie in the result: they report the
        # requested action even though STATE_CHANGED contains the actual one.
        result = {
            **requested,
            "ok": True,
            "status": "refunded",
            "transaction_id": transaction_id,
            "refund_id": refund_id,
            "replayed": False,
        }
        self._completed(
            self.ISSUE_REFUND,
            intent_id,
            tool_call_id,
            result,
            transaction_id=transaction_id,
            idempotency_key=key,
        )
        return result

    # ------------------------------------------------------------------ #
    # Deliberately outside the ledger (an unknowable external side effect)
    # ------------------------------------------------------------------ #
    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        intent_id: str,
        tool_call_id: str,
    ) -> dict[str, Any]:
        message = {
            "ok": True,
            "message_id": f"msg_{tool_call_id}",
            "to": to,
            "subject": subject,
            "body": body,
            "intent_id": intent_id,
        }
        self.sent_emails.append(message)
        return dict(message)

    # ------------------------------------------------------------------ #
    # Ledger helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _refund_payload(order_id: str, amount_cents: int) -> dict[str, Any]:
        return {
            "requested_order_id": order_id,
            "requested_amount_cents": amount_cents,
        }

    def _started(
        self,
        tool_name: str,
        intent_id: str,
        tool_call_id: str,
        args: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> LedgerEvent:
        return self.ledger.append(
            EventType.TOOL_CALL_STARTED,
            tool_name=tool_name,
            intent_id=intent_id,
            tool_call_id=tool_call_id,
            idempotency_key=idempotency_key,
            payload={**args, "args": dict(args)},
        )

    def _completed(
        self,
        tool_name: str,
        intent_id: str,
        tool_call_id: str,
        result: dict[str, Any],
        *,
        transaction_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> LedgerEvent:
        return self.ledger.append(
            EventType.TOOL_CALL_COMPLETED,
            tool_name=tool_name,
            intent_id=intent_id,
            tool_call_id=tool_call_id,
            transaction_id=transaction_id,
            idempotency_key=idempotency_key,
            payload=dict(result),
        )

    def _refund_error(
        self,
        requested: dict[str, Any],
        intent_id: str,
        tool_call_id: str,
        key: str,
        exc: Exception,
    ) -> Any:
        self.ledger.append(
            EventType.TOOL_CALL_FAILED,
            tool_name=self.ISSUE_REFUND,
            intent_id=intent_id,
            tool_call_id=tool_call_id,
            idempotency_key=key,
            payload={**requested, "ok": False, "error": type(exc).__name__, "message": str(exc)},
        )
        raise exc

    def _timeout(
        self,
        requested: dict[str, Any],
        intent_id: str,
        tool_call_id: str,
        key: str,
        *,
        phase: str,
        fault: FaultSpec,
        transaction_id: str | None = None,
    ) -> None:
        self.ledger.append(
            EventType.NETWORK_TIMEOUT,
            tool_name=self.ISSUE_REFUND,
            intent_id=intent_id,
            tool_call_id=tool_call_id,
            transaction_id=transaction_id,
            idempotency_key=key,
            entity=entity_ref("order", requested["requested_order_id"]),
            payload={**requested, "ok": False, "error": "network_timeout"},
        )
        raise ToolTimeout("issue_refund timed out; commit status is unknown")

    def _other_order_id(self, requested_order: dict[str, Any]) -> str:
        candidates = [
            row["order_id"]
            for row in self.db.list_orders_for_customer(requested_order["customer_id"])
            if row["order_id"] != requested_order["order_id"]
        ]
        if not candidates:
            raise KeyError("misrouted_write requires another order for the customer")
        return candidates[0]


# Plural alias reads naturally at call sites while keeping the requested public
# name ``RefundTool`` stable.
RefundTools = RefundTool


__all__ = ["IdempotencyConflict", "RefundTool", "RefundTools"]
