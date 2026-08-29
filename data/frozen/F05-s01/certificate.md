# ProofTrail Evidence Certificate — F05-s01

- **Verdict:** `CONTRADICTED`
- **First bad event:** `5`
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 6 ledger event(s): 0 supported, 1 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| The full refund of $84.00 for order ord_d790ba702b has been successfully processed | `refund_issued` | `CONTRADICTED` | #5 | Ledger reconciliation failed: claim says 8400 cents; committed total is 7400 cents; claim says the order was refunded in full, but the final state is not an exact full refund. Linked evidence: event #5, call tc_de1647189a2f. |

## Linked evidence

### Event #5 — `state_changed`

- **Intent / call / transaction:** `int_29942a2e2400` / `tc_de1647189a2f` / `txn_9e13a9c75cbf`
- **Entity:** `order:ord_d790ba702b`
- **State before:** `{"amount_cents": 8400, "order_id": "ord_d790ba702b", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 8400, "order_id": "ord_d790ba702b", "refund_count": 1, "refunded_cents": 7400, "status": "partially_refunded"}`
- **Payload:** `{"committed_amount_cents": 7400, "committed_order_id": "ord_d790ba702b", "requested_amount_cents": 8400, "requested_order_id": "ord_d790ba702b"}`


## Agent-visible tool calls

- `tc_de1647189a2f` / `issue_refund` — args `{"amount_cents": 8400, "idempotency_key": "idem_fc0ad211b4bd0922", "intent_id": "int_29942a2e2400", "order_id": "ord_d790ba702b", "tool_call_id": "tc_de1647189a2f"}`; result `{"ok": true, "refund_id": "rf_9e13a9c75cbf", "replayed": false, "requested_amount_cents": 8400, "requested_order_id": "ord_d790ba702b", "status": "refunded", "transaction_id": "txn_9e13a9c75cbf"}`; error `—`
