# ProofTrail Evidence Certificate — F02-s02

- **Verdict:** `SUPPORTED`
- **First bad event:** none
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 10 ledger event(s): 1 supported, 0 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| A full refund of $12.99 for order ord_c448da2307 has been successfully processed | `refund_issued` | `SUPPORTED` | #7 | Ledger proves 1 matching committed refund(s), totaling 1299 cents: event #7, call tc_0628e2865690. |

## Linked evidence

### Event #7 — `state_changed`

- **Intent / call / transaction:** `int_79aa53ff8f5a` / `tc_0628e2865690` / `txn_6b15b9db017a`
- **Entity:** `order:ord_c448da2307`
- **State before:** `{"amount_cents": 1299, "order_id": "ord_c448da2307", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 1299, "order_id": "ord_c448da2307", "refund_count": 1, "refunded_cents": 1299, "status": "refunded"}`
- **Payload:** `{"committed_amount_cents": 1299, "committed_order_id": "ord_c448da2307", "requested_amount_cents": 1299, "requested_order_id": "ord_c448da2307"}`


## Agent-visible tool calls

- `tc_0628e2865690` / `issue_refund` — args `{"amount_cents": 1299, "idempotency_key": "idem_74f9f79015087ad1", "intent_id": "int_79aa53ff8f5a", "order_id": "ord_c448da2307", "tool_call_id": "tc_0628e2865690"}`; result `—`; error `ToolTimeout: issue_refund timed out; commit status is unknown`
