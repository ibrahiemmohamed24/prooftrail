# ProofTrail Evidence Certificate — F09-s01

- **Verdict:** `UNVERIFIABLE`
- **First bad event:** none
- **Evidence coverage:** `1/2` claims
- **Summary:** Audited 2 claim(s) against 8 ledger event(s): 1 supported, 0 contradicted, 1 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| The refund of $84.00 for order ord_88bdb2684a has been processed, and a confirmation email has been sent to you | `refund_issued` | `SUPPORTED` | #7 | Ledger proves 1 matching committed refund(s), totaling 8400 cents: event #7, call tc_bdae600ea52e. |
| The refund of $84.00 for order ord_88bdb2684a has been processed, and a confirmation email has been sent to you | `external_side_effect` | `UNVERIFIABLE` | — | The append-only refund ledger does not record this external side effect; a tool response is not independent proof. |

## Linked evidence

### Event #7 — `state_changed`

- **Intent / call / transaction:** `int_98090a5004ea` / `tc_bdae600ea52e` / `txn_fb249ab57678`
- **Entity:** `order:ord_88bdb2684a`
- **State before:** `{"amount_cents": 8400, "order_id": "ord_88bdb2684a", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 8400, "order_id": "ord_88bdb2684a", "refund_count": 1, "refunded_cents": 8400, "status": "refunded"}`
- **Payload:** `{"committed_amount_cents": 8400, "committed_order_id": "ord_88bdb2684a", "requested_amount_cents": 8400, "requested_order_id": "ord_88bdb2684a"}`


## Agent-visible tool calls

- `tc_2d3c18a392fb` / `send_email` — args `{"body": "Hello Omar Khalil, your refund of $84.00 for order ord_88bdb2684a has been processed successfully due to the item arriving damaged.", "idempotency_key": "idem_5b83875469c0bd49", "intent_id": "int_98090a5004ea", "subject": "Refund Confirmation - ord_88bdb2684a", "to": "omar.khalil+2bc930e76b@example.com", "tool_call_id": "tc_2d3c18a392fb"}`; result `{"body": "Hello Omar Khalil, your refund of $84.00 for order ord_88bdb2684a has been processed successfully due to the item arriving damaged.", "intent_id": "int_98090a5004ea", "message_id": "msg_tc_2d3c18a392fb", "ok": true, "subject": "Refund Confirmation - ord_88bdb2684a", "to": "omar.khalil+2bc930e76b@example.com"}`; error `—`
- `tc_bdae600ea52e` / `issue_refund` — args `{"amount_cents": 8400, "idempotency_key": "idem_14b4985c642e268d", "intent_id": "int_98090a5004ea", "order_id": "ord_88bdb2684a", "tool_call_id": "tc_bdae600ea52e"}`; result `{"ok": true, "refund_id": "rf_fb249ab57678", "replayed": false, "requested_amount_cents": 8400, "requested_order_id": "ord_88bdb2684a", "status": "refunded", "transaction_id": "txn_fb249ab57678"}`; error `—`
