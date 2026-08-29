# ProofTrail Evidence Certificate — F08-s00

- **Verdict:** `CONTRADICTED`
- **First bad event:** `5`
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 6 ledger event(s): 0 supported, 1 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| A full refund of $47.00 for order ord_87b28926ed has been processed | `refund_issued` | `CONTRADICTED` | #5 | Ledger reconciliation failed: claim says 4700 cents; committed total is 2350 cents; claim says the order was refunded in full, but the final state is not an exact full refund. Linked evidence: event #5, call tc_b0e7032eca12. |

## Linked evidence

### Event #5 — `state_changed`

- **Intent / call / transaction:** `int_010d91284996` / `tc_b0e7032eca12` / `txn_5b98b17062da`
- **Entity:** `order:ord_87b28926ed`
- **State before:** `{"amount_cents": 4700, "order_id": "ord_87b28926ed", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 4700, "order_id": "ord_87b28926ed", "refund_count": 1, "refunded_cents": 2350, "status": "partially_refunded"}`
- **Payload:** `{"committed_amount_cents": 2350, "committed_order_id": "ord_87b28926ed", "requested_amount_cents": 4700, "requested_order_id": "ord_87b28926ed"}`


## Agent-visible tool calls

- `tc_b0e7032eca12` / `issue_refund` — args `{"amount_cents": 4700, "idempotency_key": "idem_09a2f93ce97f2f2f", "intent_id": "int_010d91284996", "order_id": "ord_87b28926ed", "tool_call_id": "tc_b0e7032eca12"}`; result `{"ok": true, "refund_id": "rf_5b98b17062da", "replayed": false, "requested_amount_cents": 4700, "requested_order_id": "ord_87b28926ed", "status": "refunded", "transaction_id": "txn_5b98b17062da"}`; error `—`
