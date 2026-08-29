# ProofTrail Evidence Certificate — F04-s00

- **Verdict:** `CONTRADICTED`
- **First bad event:** `5`
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 5 ledger event(s): 0 supported, 1 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| A full refund of $47.00 has been issued for order ord_796d391e60 | `refund_issued` | `CONTRADICTED` | #5 | The report says a refund was issued, but no STATE_CHANGED refund event exists for the linked intent. |

## Linked evidence

### Event #5 — `tool_call_completed`

- **Intent / call / transaction:** `int_9a6aa3ba7270` / `tc_31619f801c2e` / `txn_31619f801c2e`
- **Entity:** `—`
- **State before:** `—`
- **State after:** `—`
- **Payload:** `{"ok": true, "refund_id": "rf_31619f801c2e", "requested_amount_cents": 4700, "requested_order_id": "ord_796d391e60", "status": "refunded", "transaction_id": "txn_31619f801c2e"}`


## Agent-visible tool calls

- `tc_31619f801c2e` / `issue_refund` — args `{"amount_cents": 4700, "idempotency_key": "idem_a682bb6d7d7d2d79", "intent_id": "int_9a6aa3ba7270", "order_id": "ord_796d391e60", "tool_call_id": "tc_31619f801c2e"}`; result `{"ok": true, "refund_id": "rf_31619f801c2e", "requested_amount_cents": 4700, "requested_order_id": "ord_796d391e60", "status": "refunded", "transaction_id": "txn_31619f801c2e"}`; error `—`
