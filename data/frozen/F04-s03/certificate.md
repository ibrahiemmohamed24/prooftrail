# ProofTrail Evidence Certificate — F04-s03

- **Verdict:** `CONTRADICTED`
- **First bad event:** `7`
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 7 ledger event(s): 0 supported, 1 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| A full refund of $125.00 has been issued for order ord_86c809305f | `refund_issued` | `CONTRADICTED` | #7 | The report says a refund was issued, but no STATE_CHANGED refund event exists for the linked intent. |

## Linked evidence

### Event #7 — `tool_call_completed`

- **Intent / call / transaction:** `int_4fbe81dc897a` / `tc_448d4b03dfb3` / `txn_448d4b03dfb3`
- **Entity:** `—`
- **State before:** `—`
- **State after:** `—`
- **Payload:** `{"ok": true, "refund_id": "rf_448d4b03dfb3", "requested_amount_cents": 12500, "requested_order_id": "ord_86c809305f", "status": "refunded", "transaction_id": "txn_448d4b03dfb3"}`


## Agent-visible tool calls

- `tc_448d4b03dfb3` / `issue_refund` — args `{"amount_cents": 12500, "idempotency_key": "idem_702ae6fc072d21ae", "intent_id": "int_4fbe81dc897a", "order_id": "ord_86c809305f", "tool_call_id": "tc_448d4b03dfb3"}`; result `{"ok": true, "refund_id": "rf_448d4b03dfb3", "requested_amount_cents": 12500, "requested_order_id": "ord_86c809305f", "status": "refunded", "transaction_id": "txn_448d4b03dfb3"}`; error `—`
