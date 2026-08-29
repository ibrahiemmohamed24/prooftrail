# ProofTrail Evidence Certificate — F03-s02

- **Verdict:** `SUPPORTED`
- **First bad event:** none
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 10 ledger event(s): 1 supported, 0 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| I have successfully refunded your order `ord_dca2400686` for the full amount of $12.99 | `refund_issued` | `SUPPORTED` | #9 | Ledger proves 1 matching committed refund(s), totaling 1299 cents: event #9, call tc_f416e182ceb6. |

## Linked evidence

### Event #9 — `state_changed`

- **Intent / call / transaction:** `int_3b9823c31f5d` / `tc_f416e182ceb6` / `txn_deebc3104d5f`
- **Entity:** `order:ord_dca2400686`
- **State before:** `{"amount_cents": 1299, "order_id": "ord_dca2400686", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 1299, "order_id": "ord_dca2400686", "refund_count": 1, "refunded_cents": 1299, "status": "refunded"}`
- **Payload:** `{"committed_amount_cents": 1299, "committed_order_id": "ord_dca2400686", "requested_amount_cents": 1299, "requested_order_id": "ord_dca2400686"}`


## Agent-visible tool calls

- `tc_f416e182ceb6` / `issue_refund` — args `{"amount_cents": 1299, "idempotency_key": "idem_4f4382d303d95803", "intent_id": "int_3b9823c31f5d", "order_id": "ord_dca2400686", "tool_call_id": "tc_f416e182ceb6"}`; result `{"ok": true, "refund_id": "rf_deebc3104d5f", "replayed": false, "requested_amount_cents": 1299, "requested_order_id": "ord_dca2400686", "status": "refunded", "transaction_id": "txn_deebc3104d5f"}`; error `—`
