# ProofTrail Evidence Certificate — F01-s01

- **Verdict:** `SUPPORTED`
- **First bad event:** none
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 8 ledger event(s): 1 supported, 0 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| A full refund of $84.00 has been issued for your order ord_8c4be40f03 | `refund_issued` | `SUPPORTED` | #7 | Ledger proves 1 matching committed refund(s), totaling 8400 cents: event #7, call tc_e75178ac3145. |

## Linked evidence

### Event #7 — `state_changed`

- **Intent / call / transaction:** `int_41ea92931ec6` / `tc_e75178ac3145` / `txn_8edd86ff6e80`
- **Entity:** `order:ord_8c4be40f03`
- **State before:** `{"amount_cents": 8400, "order_id": "ord_8c4be40f03", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 8400, "order_id": "ord_8c4be40f03", "refund_count": 1, "refunded_cents": 8400, "status": "refunded"}`
- **Payload:** `{"committed_amount_cents": 8400, "committed_order_id": "ord_8c4be40f03", "requested_amount_cents": 8400, "requested_order_id": "ord_8c4be40f03"}`


## Agent-visible tool calls

- `tc_e75178ac3145` / `issue_refund` — args `{"amount_cents": 8400, "idempotency_key": "idem_6564385f8980e51d", "intent_id": "int_41ea92931ec6", "order_id": "ord_8c4be40f03", "tool_call_id": "tc_e75178ac3145"}`; result `{"ok": true, "refund_id": "rf_8edd86ff6e80", "replayed": false, "requested_amount_cents": 8400, "requested_order_id": "ord_8c4be40f03", "status": "refunded", "transaction_id": "txn_8edd86ff6e80"}`; error `—`
