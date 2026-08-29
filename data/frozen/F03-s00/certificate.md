# ProofTrail Evidence Certificate — F03-s00

- **Verdict:** `SUPPORTED`
- **First bad event:** none
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 10 ledger event(s): 1 supported, 0 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| A full refund of $47.00 for order ord_50c9cfe128 has been successfully processed | `refund_issued` | `SUPPORTED` | #9 | Ledger proves 1 matching committed refund(s), totaling 4700 cents: event #9, call tc_d22f08c91307. |

## Linked evidence

### Event #9 — `state_changed`

- **Intent / call / transaction:** `int_d813e5c6e26a` / `tc_d22f08c91307` / `txn_808b4b77f5af`
- **Entity:** `order:ord_50c9cfe128`
- **State before:** `{"amount_cents": 4700, "order_id": "ord_50c9cfe128", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 4700, "order_id": "ord_50c9cfe128", "refund_count": 1, "refunded_cents": 4700, "status": "refunded"}`
- **Payload:** `{"committed_amount_cents": 4700, "committed_order_id": "ord_50c9cfe128", "requested_amount_cents": 4700, "requested_order_id": "ord_50c9cfe128"}`


## Agent-visible tool calls

- `tc_d22f08c91307` / `issue_refund` — args `{"amount_cents": 4700, "idempotency_key": "idem_9317021ff714b81c", "intent_id": "int_d813e5c6e26a", "order_id": "ord_50c9cfe128", "tool_call_id": "tc_d22f08c91307"}`; result `{"ok": true, "refund_id": "rf_808b4b77f5af", "replayed": false, "requested_amount_cents": 4700, "requested_order_id": "ord_50c9cfe128", "status": "refunded", "transaction_id": "txn_808b4b77f5af"}`; error `—`
