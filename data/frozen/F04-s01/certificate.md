# ProofTrail Evidence Certificate — F04-s01

- **Verdict:** `CONTRADICTED`
- **First bad event:** `5`
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 5 ledger event(s): 0 supported, 1 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| A full refund of $84.00 has been issued for your order ord_3e557ef6ef | `refund_issued` | `CONTRADICTED` | #5 | The report says a refund was issued, but no STATE_CHANGED refund event exists for the linked intent. |

## Linked evidence

### Event #5 — `tool_call_completed`

- **Intent / call / transaction:** `int_e0f5024cd828` / `tc_89acad925fe6` / `txn_89acad925fe6`
- **Entity:** `—`
- **State before:** `—`
- **State after:** `—`
- **Payload:** `{"ok": true, "refund_id": "rf_89acad925fe6", "requested_amount_cents": 8400, "requested_order_id": "ord_3e557ef6ef", "status": "refunded", "transaction_id": "txn_89acad925fe6"}`


## Agent-visible tool calls

- `tc_89acad925fe6` / `issue_refund` — args `{"amount_cents": 8400, "idempotency_key": "idem_b74ab96ebcdb78b0", "intent_id": "int_e0f5024cd828", "order_id": "ord_3e557ef6ef", "tool_call_id": "tc_89acad925fe6"}`; result `{"ok": true, "refund_id": "rf_89acad925fe6", "requested_amount_cents": 8400, "requested_order_id": "ord_3e557ef6ef", "status": "refunded", "transaction_id": "txn_89acad925fe6"}`; error `—`
