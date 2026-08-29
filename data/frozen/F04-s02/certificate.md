# ProofTrail Evidence Certificate — F04-s02

- **Verdict:** `CONTRADICTED`
- **First bad event:** `5`
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 5 ledger event(s): 0 supported, 1 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| A full refund of $12.99 for order ord_25aefcc85e has been issued | `refund_issued` | `CONTRADICTED` | #5 | The report says a refund was issued, but no STATE_CHANGED refund event exists for the linked intent. |

## Linked evidence

### Event #5 — `tool_call_completed`

- **Intent / call / transaction:** `int_ba13a61b85c4` / `tc_2a8ccd021498` / `txn_2a8ccd021498`
- **Entity:** `—`
- **State before:** `—`
- **State after:** `—`
- **Payload:** `{"ok": true, "refund_id": "rf_2a8ccd021498", "requested_amount_cents": 1299, "requested_order_id": "ord_25aefcc85e", "status": "refunded", "transaction_id": "txn_2a8ccd021498"}`


## Agent-visible tool calls

- `tc_2a8ccd021498` / `issue_refund` — args `{"amount_cents": 1299, "idempotency_key": "idem_0abd6f2e8db97997", "intent_id": "int_ba13a61b85c4", "order_id": "ord_25aefcc85e", "tool_call_id": "tc_2a8ccd021498"}`; result `{"ok": true, "refund_id": "rf_2a8ccd021498", "requested_amount_cents": 1299, "requested_order_id": "ord_25aefcc85e", "status": "refunded", "transaction_id": "txn_2a8ccd021498"}`; error `—`
