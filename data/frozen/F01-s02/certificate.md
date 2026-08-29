# ProofTrail Evidence Certificate — F01-s02

- **Verdict:** `SUPPORTED`
- **First bad event:** none
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 6 ledger event(s): 1 supported, 0 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| A full refund of $12.99 for order ord_e34e7e280c has been issued | `refund_issued` | `SUPPORTED` | #5 | Ledger proves 1 matching committed refund(s), totaling 1299 cents: event #5, call tc_d5fdab2a49cb. |

## Linked evidence

### Event #5 — `state_changed`

- **Intent / call / transaction:** `int_ec438bf8d901` / `tc_d5fdab2a49cb` / `txn_efb050d2c914`
- **Entity:** `order:ord_e34e7e280c`
- **State before:** `{"amount_cents": 1299, "order_id": "ord_e34e7e280c", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 1299, "order_id": "ord_e34e7e280c", "refund_count": 1, "refunded_cents": 1299, "status": "refunded"}`
- **Payload:** `{"committed_amount_cents": 1299, "committed_order_id": "ord_e34e7e280c", "requested_amount_cents": 1299, "requested_order_id": "ord_e34e7e280c"}`


## Agent-visible tool calls

- `tc_d5fdab2a49cb` / `issue_refund` — args `{"amount_cents": 1299, "idempotency_key": "idem_d18d88e2b2df6af5", "intent_id": "int_ec438bf8d901", "order_id": "ord_e34e7e280c", "tool_call_id": "tc_d5fdab2a49cb"}`; result `{"ok": true, "refund_id": "rf_efb050d2c914", "replayed": false, "requested_amount_cents": 1299, "requested_order_id": "ord_e34e7e280c", "status": "refunded", "transaction_id": "txn_efb050d2c914"}`; error `—`
