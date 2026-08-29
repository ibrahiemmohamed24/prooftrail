# ProofTrail Evidence Certificate — F06-s02

- **Verdict:** `CONTRADICTED`
- **First bad event:** `5`
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 6 ledger event(s): 0 supported, 1 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| A full refund of $12.99 for order ord_3c175c8baf has been processed successfully (Refund ID: rf_fef13aa92267) | `refund_issued` | `CONTRADICTED` | #5 | Ledger reconciliation failed: claim names order ord_3c175c8baf, but the commit target is ord_453470945e; claim says the order was refunded in full, but the final state is not an exact full refund. Linked evidence: event #5, call tc_d09bc0f8698a. |

## Linked evidence

### Event #5 — `state_changed`

- **Intent / call / transaction:** `int_29bb063792f0` / `tc_d09bc0f8698a` / `txn_fef13aa92267`
- **Entity:** `order:ord_453470945e`
- **State before:** `{"amount_cents": 7600, "order_id": "ord_453470945e", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 7600, "order_id": "ord_453470945e", "refund_count": 1, "refunded_cents": 1299, "status": "partially_refunded"}`
- **Payload:** `{"committed_amount_cents": 1299, "committed_order_id": "ord_453470945e", "requested_amount_cents": 1299, "requested_order_id": "ord_3c175c8baf"}`


## Agent-visible tool calls

- `tc_d09bc0f8698a` / `issue_refund` — args `{"amount_cents": 1299, "idempotency_key": "idem_7934add509085514", "intent_id": "int_29bb063792f0", "order_id": "ord_3c175c8baf", "tool_call_id": "tc_d09bc0f8698a"}`; result `{"ok": true, "refund_id": "rf_fef13aa92267", "replayed": false, "requested_amount_cents": 1299, "requested_order_id": "ord_3c175c8baf", "status": "refunded", "transaction_id": "txn_fef13aa92267"}`; error `—`
