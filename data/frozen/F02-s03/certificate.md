# ProofTrail Evidence Certificate — F02-s03

- **Verdict:** `SUPPORTED`
- **First bad event:** none
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 10 ledger event(s): 1 supported, 0 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| I have successfully processed your refund of $125.00 for order ord_cf538f20de | `refund_issued` | `SUPPORTED` | #7 | Ledger proves 1 matching committed refund(s), totaling 12500 cents: event #7, call tc_d022f84c3474. |

## Linked evidence

### Event #7 — `state_changed`

- **Intent / call / transaction:** `int_353f9dfccd77` / `tc_d022f84c3474` / `txn_560e2871e3a2`
- **Entity:** `order:ord_cf538f20de`
- **State before:** `{"amount_cents": 12500, "order_id": "ord_cf538f20de", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 12500, "order_id": "ord_cf538f20de", "refund_count": 1, "refunded_cents": 12500, "status": "refunded"}`
- **Payload:** `{"committed_amount_cents": 12500, "committed_order_id": "ord_cf538f20de", "requested_amount_cents": 12500, "requested_order_id": "ord_cf538f20de"}`


## Agent-visible tool calls

- `tc_d022f84c3474` / `issue_refund` — args `{"amount_cents": 12500, "idempotency_key": "idem_6cfa8fb661df6cc5", "intent_id": "int_353f9dfccd77", "order_id": "ord_cf538f20de", "tool_call_id": "tc_d022f84c3474"}`; result `—`; error `ToolTimeout: issue_refund timed out; commit status is unknown`
