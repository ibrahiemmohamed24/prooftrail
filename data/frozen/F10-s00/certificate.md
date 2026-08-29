# ProofTrail Evidence Certificate — F10-s00

- **Verdict:** `SUPPORTED`
- **First bad event:** none
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 8 ledger event(s): 1 supported, 0 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| The refund for your order ord_6d4e788586 in the amount of $47.00 has been successfully processed | `refund_issued` | `SUPPORTED` | #5 | Ledger proves 1 matching committed refund(s), totaling 4700 cents: event #5, call tc_9b4150018de9. |

## Linked evidence

### Event #5 — `state_changed`

- **Intent / call / transaction:** `int_deed34d36199` / `tc_9b4150018de9` / `txn_071503ed50b2`
- **Entity:** `order:ord_6d4e788586`
- **State before:** `{"amount_cents": 4700, "order_id": "ord_6d4e788586", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 4700, "order_id": "ord_6d4e788586", "refund_count": 1, "refunded_cents": 4700, "status": "refunded"}`
- **Payload:** `{"committed_amount_cents": 4700, "committed_order_id": "ord_6d4e788586", "requested_amount_cents": 4700, "requested_order_id": "ord_6d4e788586"}`


## Agent-visible tool calls

- `tc_9b4150018de9` / `issue_refund` — args `{"amount_cents": 4700, "idempotency_key": "idem_461c7f261fe2b832", "intent_id": "int_deed34d36199", "order_id": "ord_6d4e788586", "tool_call_id": "tc_9b4150018de9"}`; result `—`; error `ToolTimeout: issue_refund timed out; commit status is unknown`
