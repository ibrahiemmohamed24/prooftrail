# ProofTrail Evidence Certificate — F03-s01

- **Verdict:** `SUPPORTED`
- **First bad event:** none
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 10 ledger event(s): 1 supported, 0 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| I have successfully issued a full refund of $84.00 for your order ord_d31261d032 | `refund_issued` | `SUPPORTED` | #9 | Ledger proves 1 matching committed refund(s), totaling 8400 cents: event #9, call tc_bb8c3631564a. |

## Linked evidence

### Event #9 — `state_changed`

- **Intent / call / transaction:** `int_49859fe9cc82` / `tc_bb8c3631564a` / `txn_cae229eedc3a`
- **Entity:** `order:ord_d31261d032`
- **State before:** `{"amount_cents": 8400, "order_id": "ord_d31261d032", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 8400, "order_id": "ord_d31261d032", "refund_count": 1, "refunded_cents": 8400, "status": "refunded"}`
- **Payload:** `{"committed_amount_cents": 8400, "committed_order_id": "ord_d31261d032", "requested_amount_cents": 8400, "requested_order_id": "ord_d31261d032"}`


## Agent-visible tool calls

- `tc_bb8c3631564a` / `issue_refund` — args `{"amount_cents": 8400, "idempotency_key": "idem_028db0a9e8097ab1", "intent_id": "int_49859fe9cc82", "order_id": "ord_d31261d032", "tool_call_id": "tc_bb8c3631564a"}`; result `{"ok": true, "refund_id": "rf_cae229eedc3a", "replayed": false, "requested_amount_cents": 8400, "requested_order_id": "ord_d31261d032", "status": "refunded", "transaction_id": "txn_cae229eedc3a"}`; error `—`
