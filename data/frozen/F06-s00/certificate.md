# ProofTrail Evidence Certificate — F06-s00

- **Verdict:** `CONTRADICTED`
- **First bad event:** `5`
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 6 ledger event(s): 0 supported, 1 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| The refund of $47.00 for order ord_042f72276d has been successfully processed | `refund_issued` | `CONTRADICTED` | #5 | Ledger reconciliation failed: claim names order ord_042f72276d, but the commit target is ord_21a85efd08. Linked evidence: event #5, call tc_895a57a8e0a9. |

## Linked evidence

### Event #5 — `state_changed`

- **Intent / call / transaction:** `int_5326fae5972b` / `tc_895a57a8e0a9` / `txn_f8d9c73157dc`
- **Entity:** `order:ord_21a85efd08`
- **State before:** `{"amount_cents": 2500, "order_id": "ord_21a85efd08", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 2500, "order_id": "ord_21a85efd08", "refund_count": 1, "refunded_cents": 4700, "status": "refunded"}`
- **Payload:** `{"committed_amount_cents": 4700, "committed_order_id": "ord_21a85efd08", "requested_amount_cents": 4700, "requested_order_id": "ord_042f72276d"}`


## Agent-visible tool calls

- `tc_895a57a8e0a9` / `issue_refund` — args `{"amount_cents": 4700, "idempotency_key": "idem_c2687907747cef12", "intent_id": "int_5326fae5972b", "order_id": "ord_042f72276d", "tool_call_id": "tc_895a57a8e0a9"}`; result `{"ok": true, "refund_id": "rf_f8d9c73157dc", "replayed": false, "requested_amount_cents": 4700, "requested_order_id": "ord_042f72276d", "status": "refunded", "transaction_id": "txn_f8d9c73157dc"}`; error `—`
