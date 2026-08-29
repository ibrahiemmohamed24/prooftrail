# ProofTrail Evidence Certificate — F05-s03

- **Verdict:** `CONTRADICTED`
- **First bad event:** `5`
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 6 ledger event(s): 0 supported, 1 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| The refund of $125.00 for order ord_3f4d1a82de has been successfully processed | `refund_issued` | `CONTRADICTED` | #5 | Ledger reconciliation failed: claim says 12500 cents; committed total is 11500 cents. Linked evidence: event #5, call tc_a05265711297. |

## Linked evidence

### Event #5 — `state_changed`

- **Intent / call / transaction:** `int_d5ed55aa39b4` / `tc_a05265711297` / `txn_e8451372c978`
- **Entity:** `order:ord_3f4d1a82de`
- **State before:** `{"amount_cents": 12500, "order_id": "ord_3f4d1a82de", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 12500, "order_id": "ord_3f4d1a82de", "refund_count": 1, "refunded_cents": 11500, "status": "partially_refunded"}`
- **Payload:** `{"committed_amount_cents": 11500, "committed_order_id": "ord_3f4d1a82de", "requested_amount_cents": 12500, "requested_order_id": "ord_3f4d1a82de"}`


## Agent-visible tool calls

- `tc_a05265711297` / `issue_refund` — args `{"amount_cents": 12500, "idempotency_key": "idem_64f2f36453dddfc9", "intent_id": "int_d5ed55aa39b4", "order_id": "ord_3f4d1a82de", "tool_call_id": "tc_a05265711297"}`; result `{"ok": true, "refund_id": "rf_e8451372c978", "replayed": false, "requested_amount_cents": 12500, "requested_order_id": "ord_3f4d1a82de", "status": "refunded", "transaction_id": "txn_e8451372c978"}`; error `—`
