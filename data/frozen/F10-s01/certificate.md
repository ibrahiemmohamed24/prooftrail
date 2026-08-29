# ProofTrail Evidence Certificate — F10-s01

- **Verdict:** `SUPPORTED`
- **First bad event:** none
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 8 ledger event(s): 1 supported, 0 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| The refund of $84.00 for your order ord_44a76805fb has been processed successfully | `refund_issued` | `SUPPORTED` | #5 | Ledger proves 1 matching committed refund(s), totaling 8400 cents: event #5, call tc_b511ae918f01. |

## Linked evidence

### Event #5 — `state_changed`

- **Intent / call / transaction:** `int_a76ef2d14643` / `tc_b511ae918f01` / `txn_d6871211e103`
- **Entity:** `order:ord_44a76805fb`
- **State before:** `{"amount_cents": 8400, "order_id": "ord_44a76805fb", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 8400, "order_id": "ord_44a76805fb", "refund_count": 1, "refunded_cents": 8400, "status": "refunded"}`
- **Payload:** `{"committed_amount_cents": 8400, "committed_order_id": "ord_44a76805fb", "requested_amount_cents": 8400, "requested_order_id": "ord_44a76805fb"}`


## Agent-visible tool calls

- `tc_b511ae918f01` / `issue_refund` — args `{"amount_cents": 8400, "idempotency_key": "idem_fbfc71d8bdad8489", "intent_id": "int_a76ef2d14643", "order_id": "ord_44a76805fb", "tool_call_id": "tc_b511ae918f01"}`; result `—`; error `ToolTimeout: issue_refund timed out; commit status is unknown`
