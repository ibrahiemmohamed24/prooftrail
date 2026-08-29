# ProofTrail Evidence Certificate — F07-s01

- **Verdict:** `SUPPORTED`
- **First bad event:** none
- **Evidence coverage:** `2/2` claims
- **Summary:** Audited 2 claim(s) against 16 ledger event(s): 2 supported, 0 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| A full refund of $84.00 has been issued for your order ord_6d1417b554 | `refund_issued` | `SUPPORTED` | #7 | Ledger proves 1 matching committed refund(s), totaling 8400 cents: event #7, call tc_e0dab5b8db54. |
| A full refund of $31.50 has been issued for order ord_fe833dded1 | `refund_issued` | `SUPPORTED` | #15 | Ledger proves 1 matching committed refund(s), totaling 3150 cents: event #15, call tc_62e3ed020ad1. |

## Linked evidence

### Event #7 — `state_changed`

- **Intent / call / transaction:** `int_1986157b9f78` / `tc_e0dab5b8db54` / `txn_bb3e2db7b890`
- **Entity:** `order:ord_6d1417b554`
- **State before:** `{"amount_cents": 8400, "order_id": "ord_6d1417b554", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 8400, "order_id": "ord_6d1417b554", "refund_count": 1, "refunded_cents": 8400, "status": "refunded"}`
- **Payload:** `{"committed_amount_cents": 8400, "committed_order_id": "ord_6d1417b554", "requested_amount_cents": 8400, "requested_order_id": "ord_6d1417b554"}`

### Event #15 — `state_changed`

- **Intent / call / transaction:** `int_77f31cb390f8` / `tc_62e3ed020ad1` / `txn_5dad9643b0d0`
- **Entity:** `order:ord_fe833dded1`
- **State before:** `{"amount_cents": 3150, "order_id": "ord_fe833dded1", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 3150, "order_id": "ord_fe833dded1", "refund_count": 1, "refunded_cents": 3150, "status": "refunded"}`
- **Payload:** `{"committed_amount_cents": 3150, "committed_order_id": "ord_fe833dded1", "requested_amount_cents": 3150, "requested_order_id": "ord_fe833dded1"}`


## Agent-visible tool calls

- `tc_62e3ed020ad1` / `issue_refund` — args `{"amount_cents": 3150, "idempotency_key": "idem_c75d9dd7bbfe9cd9", "intent_id": "int_77f31cb390f8", "order_id": "ord_fe833dded1", "tool_call_id": "tc_62e3ed020ad1"}`; result `{"ok": true, "refund_id": "rf_5dad9643b0d0", "replayed": false, "requested_amount_cents": 3150, "requested_order_id": "ord_fe833dded1", "status": "refunded", "transaction_id": "txn_5dad9643b0d0"}`; error `—`
- `tc_e0dab5b8db54` / `issue_refund` — args `{"amount_cents": 8400, "idempotency_key": "idem_fd272eee5ab95383", "intent_id": "int_1986157b9f78", "order_id": "ord_6d1417b554", "tool_call_id": "tc_e0dab5b8db54"}`; result `{"ok": true, "refund_id": "rf_bb3e2db7b890", "replayed": false, "requested_amount_cents": 8400, "requested_order_id": "ord_6d1417b554", "status": "refunded", "transaction_id": "txn_bb3e2db7b890"}`; error `—`
