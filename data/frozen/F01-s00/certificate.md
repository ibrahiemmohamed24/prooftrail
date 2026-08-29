# ProofTrail Evidence Certificate — F01-s00

- **Verdict:** `SUPPORTED`
- **First bad event:** none
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 6 ledger event(s): 1 supported, 0 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| A full refund of $47.00 for order ord_e9a88538a8 has been processed | `refund_issued` | `SUPPORTED` | #5 | Ledger proves 1 matching committed refund(s), totaling 4700 cents: event #5, call tc_90eab611e563. |

## Linked evidence

### Event #5 — `state_changed`

- **Intent / call / transaction:** `int_d8d35fcaf252` / `tc_90eab611e563` / `txn_b8afdbfbbb7f`
- **Entity:** `order:ord_e9a88538a8`
- **State before:** `{"amount_cents": 4700, "order_id": "ord_e9a88538a8", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 4700, "order_id": "ord_e9a88538a8", "refund_count": 1, "refunded_cents": 4700, "status": "refunded"}`
- **Payload:** `{"committed_amount_cents": 4700, "committed_order_id": "ord_e9a88538a8", "requested_amount_cents": 4700, "requested_order_id": "ord_e9a88538a8"}`


## Agent-visible tool calls

- `tc_90eab611e563` / `issue_refund` — args `{"amount_cents": 4700, "idempotency_key": "idem_77cbec01ad6c9663", "intent_id": "int_d8d35fcaf252", "order_id": "ord_e9a88538a8", "tool_call_id": "tc_90eab611e563"}`; result `{"ok": true, "refund_id": "rf_b8afdbfbbb7f", "replayed": false, "requested_amount_cents": 4700, "requested_order_id": "ord_e9a88538a8", "status": "refunded", "transaction_id": "txn_b8afdbfbbb7f"}`; error `—`
