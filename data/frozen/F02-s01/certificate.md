# ProofTrail Evidence Certificate — F02-s01

- **Verdict:** `SUPPORTED`
- **First bad event:** none
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 8 ledger event(s): 1 supported, 0 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| The refund of $84.00 for order ord_f8a2364ea3 has been processed successfully | `refund_issued` | `SUPPORTED` | #5 | Ledger proves 1 matching committed refund(s), totaling 8400 cents: event #5, call tc_19ac0fb7f1f8. |

## Linked evidence

### Event #5 — `state_changed`

- **Intent / call / transaction:** `int_e2aa409631a2` / `tc_19ac0fb7f1f8` / `txn_d1c0b4acbaf8`
- **Entity:** `order:ord_f8a2364ea3`
- **State before:** `{"amount_cents": 8400, "order_id": "ord_f8a2364ea3", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 8400, "order_id": "ord_f8a2364ea3", "refund_count": 1, "refunded_cents": 8400, "status": "refunded"}`
- **Payload:** `{"committed_amount_cents": 8400, "committed_order_id": "ord_f8a2364ea3", "requested_amount_cents": 8400, "requested_order_id": "ord_f8a2364ea3"}`


## Agent-visible tool calls

- `tc_19ac0fb7f1f8` / `issue_refund` — args `{"amount_cents": 8400, "idempotency_key": "idem_2f66cc55c090ef4c", "intent_id": "int_e2aa409631a2", "order_id": "ord_f8a2364ea3", "tool_call_id": "tc_19ac0fb7f1f8"}`; result `—`; error `ToolTimeout: issue_refund timed out; commit status is unknown`
