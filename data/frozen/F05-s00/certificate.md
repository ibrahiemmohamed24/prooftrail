# ProofTrail Evidence Certificate — F05-s00

- **Verdict:** `CONTRADICTED`
- **First bad event:** `7`
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 8 ledger event(s): 0 supported, 1 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| The full refund of $47.00 for order ord_e178a7bf54 has been processed successfully | `refund_issued` | `CONTRADICTED` | #7 | Ledger reconciliation failed: claim says 4700 cents; committed total is 3700 cents; claim says the order was refunded in full, but the final state is not an exact full refund. Linked evidence: event #7, call tc_bea24826ac1e. |

## Linked evidence

### Event #7 — `state_changed`

- **Intent / call / transaction:** `int_b4e84438fdc9` / `tc_bea24826ac1e` / `txn_a0fdd75852c9`
- **Entity:** `order:ord_e178a7bf54`
- **State before:** `{"amount_cents": 4700, "order_id": "ord_e178a7bf54", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 4700, "order_id": "ord_e178a7bf54", "refund_count": 1, "refunded_cents": 3700, "status": "partially_refunded"}`
- **Payload:** `{"committed_amount_cents": 3700, "committed_order_id": "ord_e178a7bf54", "requested_amount_cents": 4700, "requested_order_id": "ord_e178a7bf54"}`


## Agent-visible tool calls

- `tc_bea24826ac1e` / `issue_refund` — args `{"amount_cents": 4700, "idempotency_key": "idem_e5f5c7ed1df1b5f5", "intent_id": "int_b4e84438fdc9", "order_id": "ord_e178a7bf54", "tool_call_id": "tc_bea24826ac1e"}`; result `{"ok": true, "refund_id": "rf_a0fdd75852c9", "replayed": false, "requested_amount_cents": 4700, "requested_order_id": "ord_e178a7bf54", "status": "refunded", "transaction_id": "txn_a0fdd75852c9"}`; error `—`
