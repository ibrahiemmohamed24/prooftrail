# ProofTrail Evidence Certificate — F08-s03

- **Verdict:** `CONTRADICTED`
- **First bad event:** `7`
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 8 ledger event(s): 0 supported, 1 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| The refund of $125.00 for your order ord_2f7716716d has been processed successfully | `refund_issued` | `CONTRADICTED` | #7 | Ledger reconciliation failed: claim says 12500 cents; committed total is 6250 cents. Linked evidence: event #7, call tc_ec68dc375f5b. |

## Linked evidence

### Event #7 — `state_changed`

- **Intent / call / transaction:** `int_e1d3940a47f8` / `tc_ec68dc375f5b` / `txn_0c1109bf0d41`
- **Entity:** `order:ord_2f7716716d`
- **State before:** `{"amount_cents": 12500, "order_id": "ord_2f7716716d", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 12500, "order_id": "ord_2f7716716d", "refund_count": 1, "refunded_cents": 6250, "status": "partially_refunded"}`
- **Payload:** `{"committed_amount_cents": 6250, "committed_order_id": "ord_2f7716716d", "requested_amount_cents": 12500, "requested_order_id": "ord_2f7716716d"}`


## Agent-visible tool calls

- `tc_ec68dc375f5b` / `issue_refund` — args `{"amount_cents": 12500, "idempotency_key": "idem_c88a2d942396431d", "intent_id": "int_e1d3940a47f8", "order_id": "ord_2f7716716d", "tool_call_id": "tc_ec68dc375f5b"}`; result `{"ok": true, "refund_id": "rf_0c1109bf0d41", "replayed": false, "requested_amount_cents": 12500, "requested_order_id": "ord_2f7716716d", "status": "refunded", "transaction_id": "txn_0c1109bf0d41"}`; error `—`
