# ProofTrail Evidence Certificate — F06-s01

- **Verdict:** `CONTRADICTED`
- **First bad event:** `5`
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 6 ledger event(s): 0 supported, 1 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| I have processed your full refund of $84.00 for order ord_8df9f2187e | `refund_issued` | `CONTRADICTED` | #5 | Ledger reconciliation failed: claim names order ord_8df9f2187e, but the commit target is ord_81c65f0a4e; claim says the order was refunded in full, but the final state is not an exact full refund. Linked evidence: event #5, call tc_959452430c45. |

## Linked evidence

### Event #5 — `state_changed`

- **Intent / call / transaction:** `int_42559cddc5fc` / `tc_959452430c45` / `txn_5043db783e62`
- **Entity:** `order:ord_81c65f0a4e`
- **State before:** `{"amount_cents": 3150, "order_id": "ord_81c65f0a4e", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 3150, "order_id": "ord_81c65f0a4e", "refund_count": 1, "refunded_cents": 8400, "status": "refunded"}`
- **Payload:** `{"committed_amount_cents": 8400, "committed_order_id": "ord_81c65f0a4e", "requested_amount_cents": 8400, "requested_order_id": "ord_8df9f2187e"}`


## Agent-visible tool calls

- `tc_959452430c45` / `issue_refund` — args `{"amount_cents": 8400, "idempotency_key": "idem_eacccce4860efc4d", "intent_id": "int_42559cddc5fc", "order_id": "ord_8df9f2187e", "tool_call_id": "tc_959452430c45"}`; result `{"ok": true, "refund_id": "rf_5043db783e62", "replayed": false, "requested_amount_cents": 8400, "requested_order_id": "ord_8df9f2187e", "status": "refunded", "transaction_id": "txn_5043db783e62"}`; error `—`
