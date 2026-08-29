# ProofTrail Evidence Certificate — F03-s03

- **Verdict:** `SUPPORTED`
- **First bad event:** none
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 12 ledger event(s): 1 supported, 0 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| I have successfully processed your full refund of $125.00 for order ord_9b2e690b0c | `refund_issued` | `SUPPORTED` | #11 | Ledger proves 1 matching committed refund(s), totaling 12500 cents: event #11, call tc_ba71881265c5. |

## Linked evidence

### Event #11 — `state_changed`

- **Intent / call / transaction:** `int_ab1103fa9dd0` / `tc_ba71881265c5` / `txn_fd7cf515d61a`
- **Entity:** `order:ord_9b2e690b0c`
- **State before:** `{"amount_cents": 12500, "order_id": "ord_9b2e690b0c", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 12500, "order_id": "ord_9b2e690b0c", "refund_count": 1, "refunded_cents": 12500, "status": "refunded"}`
- **Payload:** `{"committed_amount_cents": 12500, "committed_order_id": "ord_9b2e690b0c", "requested_amount_cents": 12500, "requested_order_id": "ord_9b2e690b0c"}`


## Agent-visible tool calls

- `tc_ba71881265c5` / `issue_refund` — args `{"amount_cents": 12500, "idempotency_key": "idem_a5ff60d6ada35096", "intent_id": "int_ab1103fa9dd0", "order_id": "ord_9b2e690b0c", "tool_call_id": "tc_ba71881265c5"}`; result `{"ok": true, "refund_id": "rf_fd7cf515d61a", "replayed": false, "requested_amount_cents": 12500, "requested_order_id": "ord_9b2e690b0c", "status": "refunded", "transaction_id": "txn_fd7cf515d61a"}`; error `—`
