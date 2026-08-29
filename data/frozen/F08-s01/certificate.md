# ProofTrail Evidence Certificate — F08-s01

- **Verdict:** `CONTRADICTED`
- **First bad event:** `5`
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 6 ledger event(s): 0 supported, 1 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| I have processed a full refund of $84.00 for your order ord_cde43d32d7 | `refund_issued` | `CONTRADICTED` | #5 | Ledger reconciliation failed: claim says 8400 cents; committed total is 4200 cents; claim says the order was refunded in full, but the final state is not an exact full refund. Linked evidence: event #5, call tc_359b0b335482. |

## Linked evidence

### Event #5 — `state_changed`

- **Intent / call / transaction:** `int_8b9869db5cb0` / `tc_359b0b335482` / `txn_ec8db58e517b`
- **Entity:** `order:ord_cde43d32d7`
- **State before:** `{"amount_cents": 8400, "order_id": "ord_cde43d32d7", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 8400, "order_id": "ord_cde43d32d7", "refund_count": 1, "refunded_cents": 4200, "status": "partially_refunded"}`
- **Payload:** `{"committed_amount_cents": 4200, "committed_order_id": "ord_cde43d32d7", "requested_amount_cents": 8400, "requested_order_id": "ord_cde43d32d7"}`


## Agent-visible tool calls

- `tc_359b0b335482` / `issue_refund` — args `{"amount_cents": 8400, "idempotency_key": "idem_ce116a3a1ab8a77b", "intent_id": "int_8b9869db5cb0", "order_id": "ord_cde43d32d7", "tool_call_id": "tc_359b0b335482"}`; result `{"ok": true, "refund_id": "rf_ec8db58e517b", "replayed": false, "requested_amount_cents": 8400, "requested_order_id": "ord_cde43d32d7", "status": "refunded", "transaction_id": "txn_ec8db58e517b"}`; error `—`
