# ProofTrail Evidence Certificate — F02-s00

- **Verdict:** `CONTRADICTED`
- **First bad event:** `6`
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 7 ledger event(s): 0 supported, 1 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| I refunded $47.00 for order ord_82efdfe20a | `refund_issued` | `CONTRADICTED` | #3, #4, #6 | Ledger reconciliation failed: claim says 4700 cents; committed total is 9400 cents; claim implies 1 committed refund(s); ledger proves 2; intent int_828e40455021 committed at event #3, then hit a post-commit timeout at event #4, then committed again at event #6; the second commit is the first bad event. Linked evidence: event #3, call tc_4fb484fa3ff3; event #6, call tc_f68aec01b320. |

## Linked evidence

### Event #3 — `state_changed`

- **Intent / call / transaction:** `int_828e40455021` / `tc_4fb484fa3ff3` / `txn_7eb5274010e4`
- **Entity:** `order:ord_82efdfe20a`
- **State before:** `{"amount_cents": 4700, "order_id": "ord_82efdfe20a", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 4700, "order_id": "ord_82efdfe20a", "refund_count": 1, "refunded_cents": 4700, "status": "refunded"}`
- **Payload:** `{"committed_amount_cents": 4700, "committed_order_id": "ord_82efdfe20a", "requested_amount_cents": 4700, "requested_order_id": "ord_82efdfe20a"}`

### Event #4 — `network_timeout`

- **Intent / call / transaction:** `int_828e40455021` / `tc_4fb484fa3ff3` / `txn_7eb5274010e4`
- **Entity:** `order:ord_82efdfe20a`
- **State before:** `—`
- **State after:** `—`
- **Payload:** `{"error": "network_timeout", "ok": false, "requested_amount_cents": 4700, "requested_order_id": "ord_82efdfe20a"}`

### Event #6 — `state_changed`

- **Intent / call / transaction:** `int_828e40455021` / `tc_f68aec01b320` / `txn_5656e2701020`
- **Entity:** `order:ord_82efdfe20a`
- **State before:** `{"amount_cents": 4700, "order_id": "ord_82efdfe20a", "refund_count": 1, "refunded_cents": 4700, "status": "refunded"}`
- **State after:** `{"amount_cents": 4700, "order_id": "ord_82efdfe20a", "refund_count": 2, "refunded_cents": 9400, "status": "refunded"}`
- **Payload:** `{"committed_amount_cents": 4700, "committed_order_id": "ord_82efdfe20a", "requested_amount_cents": 4700, "requested_order_id": "ord_82efdfe20a"}`


## Agent-visible tool calls

- `tc_4fb484fa3ff3` / `issue_refund` — args `{"amount_cents": 4700, "idempotency_key": "idem_2ca6157ef4b03c89", "intent_id": "int_828e40455021", "order_id": "ord_82efdfe20a", "tool_call_id": "tc_4fb484fa3ff3"}`; result `—`; error `ToolTimeout: issue_refund timed out; commit status is unknown`
- `tc_f68aec01b320` / `issue_refund` — args `{"amount_cents": 4700, "idempotency_key": "idem_2ca6157ef4b03c89", "intent_id": "int_828e40455021", "order_id": "ord_82efdfe20a", "tool_call_id": "tc_f68aec01b320"}`; result `{"ok": true, "refund_id": "rf_5656e2701020", "replayed": false, "requested_amount_cents": 4700, "requested_order_id": "ord_82efdfe20a", "status": "refunded", "transaction_id": "txn_5656e2701020"}`; error `—`
