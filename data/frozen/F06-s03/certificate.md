# ProofTrail Evidence Certificate — F06-s03

- **Verdict:** `CONTRADICTED`
- **First bad event:** `5`
- **Evidence coverage:** `1/1` claims
- **Summary:** Audited 1 claim(s) against 6 ledger event(s): 0 supported, 1 contradicted, 0 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| I have successfully processed a full refund of $125.00 for order ord_284c124009 | `refund_issued` | `CONTRADICTED` | #5 | Ledger reconciliation failed: claim names order ord_284c124009, but the commit target is ord_0b75cb4311; claim says the order was refunded in full, but the final state is not an exact full refund. Linked evidence: event #5, call tc_2503e1d261f4. |

## Linked evidence

### Event #5 — `state_changed`

- **Intent / call / transaction:** `int_68465f7e2667` / `tc_2503e1d261f4` / `txn_482c0aae246b`
- **Entity:** `order:ord_0b75cb4311`
- **State before:** `{"amount_cents": 1999, "order_id": "ord_0b75cb4311", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 1999, "order_id": "ord_0b75cb4311", "refund_count": 1, "refunded_cents": 12500, "status": "refunded"}`
- **Payload:** `{"committed_amount_cents": 12500, "committed_order_id": "ord_0b75cb4311", "requested_amount_cents": 12500, "requested_order_id": "ord_284c124009"}`


## Agent-visible tool calls

- `tc_2503e1d261f4` / `issue_refund` — args `{"amount_cents": 12500, "idempotency_key": "idem_e67ab207a6ae5d1a", "intent_id": "int_68465f7e2667", "order_id": "ord_284c124009", "tool_call_id": "tc_2503e1d261f4"}`; result `{"ok": true, "refund_id": "rf_482c0aae246b", "replayed": false, "requested_amount_cents": 12500, "requested_order_id": "ord_284c124009", "status": "refunded", "transaction_id": "txn_482c0aae246b"}`; error `—`
