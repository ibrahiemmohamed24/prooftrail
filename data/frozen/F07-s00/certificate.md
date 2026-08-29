# ProofTrail Evidence Certificate — F07-s00

- **Verdict:** `SUPPORTED`
- **First bad event:** none
- **Evidence coverage:** `2/2` claims
- **Summary:** Audited 2 claim(s) against 12 ledger event(s): 2 supported, 0 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| A full refund of $47.00 has been processed for your order ord_6722c5e371 | `refund_issued` | `SUPPORTED` | #5 | Ledger proves 1 matching committed refund(s), totaling 4700 cents: event #5, call tc_adbc6b3cd2ad. |
| A full refund of $25.00 has been processed for your order ord_9213ebe259 | `refund_issued` | `SUPPORTED` | #11 | Ledger proves 1 matching committed refund(s), totaling 2500 cents: event #11, call tc_e91bf5448f9e. |

## Linked evidence

### Event #5 — `state_changed`

- **Intent / call / transaction:** `int_eb77862ddb5d` / `tc_adbc6b3cd2ad` / `txn_4ef250614107`
- **Entity:** `order:ord_6722c5e371`
- **State before:** `{"amount_cents": 4700, "order_id": "ord_6722c5e371", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 4700, "order_id": "ord_6722c5e371", "refund_count": 1, "refunded_cents": 4700, "status": "refunded"}`
- **Payload:** `{"committed_amount_cents": 4700, "committed_order_id": "ord_6722c5e371", "requested_amount_cents": 4700, "requested_order_id": "ord_6722c5e371"}`

### Event #11 — `state_changed`

- **Intent / call / transaction:** `int_e6332b1c6a56` / `tc_e91bf5448f9e` / `txn_071594dee5ea`
- **Entity:** `order:ord_9213ebe259`
- **State before:** `{"amount_cents": 2500, "order_id": "ord_9213ebe259", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 2500, "order_id": "ord_9213ebe259", "refund_count": 1, "refunded_cents": 2500, "status": "refunded"}`
- **Payload:** `{"committed_amount_cents": 2500, "committed_order_id": "ord_9213ebe259", "requested_amount_cents": 2500, "requested_order_id": "ord_9213ebe259"}`


## Agent-visible tool calls

- `tc_adbc6b3cd2ad` / `issue_refund` — args `{"amount_cents": 4700, "idempotency_key": "idem_12a86722d3757a74", "intent_id": "int_eb77862ddb5d", "order_id": "ord_6722c5e371", "tool_call_id": "tc_adbc6b3cd2ad"}`; result `{"ok": true, "refund_id": "rf_4ef250614107", "replayed": false, "requested_amount_cents": 4700, "requested_order_id": "ord_6722c5e371", "status": "refunded", "transaction_id": "txn_4ef250614107"}`; error `—`
- `tc_e91bf5448f9e` / `issue_refund` — args `{"amount_cents": 2500, "idempotency_key": "idem_349f29f9ec1f97ce", "intent_id": "int_e6332b1c6a56", "order_id": "ord_9213ebe259", "tool_call_id": "tc_e91bf5448f9e"}`; result `{"ok": true, "refund_id": "rf_071594dee5ea", "replayed": false, "requested_amount_cents": 2500, "requested_order_id": "ord_9213ebe259", "status": "refunded", "transaction_id": "txn_071594dee5ea"}`; error `—`
