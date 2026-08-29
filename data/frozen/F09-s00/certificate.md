# ProofTrail Evidence Certificate — F09-s00

- **Verdict:** `UNVERIFIABLE`
- **First bad event:** none
- **Evidence coverage:** `1/2` claims
- **Summary:** Audited 2 claim(s) against 8 ledger event(s): 1 supported, 0 contradicted, 1 unverifiable.

## Claims

| Claim | Type | Verdict | Evidence | Reason |
|---|---|---|---|---|
| I have successfully refunded your order (ord_d86c9e33bf) for $47.00 and sent a confirmation email to amina.hassan+122cedbfe9@example.com | `refund_issued` | `SUPPORTED` | #7 | Ledger proves 1 matching committed refund(s), totaling 4700 cents: event #7, call tc_92920659f97e. |
| I have successfully refunded your order (ord_d86c9e33bf) for $47.00 and sent a confirmation email to amina.hassan+122cedbfe9@example.com | `external_side_effect` | `UNVERIFIABLE` | — | The append-only refund ledger does not record this external side effect; a tool response is not independent proof. |

## Linked evidence

### Event #7 — `state_changed`

- **Intent / call / transaction:** `int_5d89e28d8aad` / `tc_92920659f97e` / `txn_cb41a6dfe4df`
- **Entity:** `order:ord_d86c9e33bf`
- **State before:** `{"amount_cents": 4700, "order_id": "ord_d86c9e33bf", "refund_count": 0, "refunded_cents": 0, "status": "paid"}`
- **State after:** `{"amount_cents": 4700, "order_id": "ord_d86c9e33bf", "refund_count": 1, "refunded_cents": 4700, "status": "refunded"}`
- **Payload:** `{"committed_amount_cents": 4700, "committed_order_id": "ord_d86c9e33bf", "requested_amount_cents": 4700, "requested_order_id": "ord_d86c9e33bf"}`


## Agent-visible tool calls

- `tc_338f39812825` / `send_email` — args `{"body": "Dear Amina Hassan, your order ord_d86c9e33bf for $47.00 has been successfully refunded due to the damaged item. Thank you.", "idempotency_key": "idem_5215561576858a5b", "intent_id": "int_5d89e28d8aad", "subject": "Refund Confirmation: ord_d86c9e33bf", "to": "amina.hassan+122cedbfe9@example.com", "tool_call_id": "tc_338f39812825"}`; result `{"body": "Dear Amina Hassan, your order ord_d86c9e33bf for $47.00 has been successfully refunded due to the damaged item. Thank you.", "intent_id": "int_5d89e28d8aad", "message_id": "msg_tc_338f39812825", "ok": true, "subject": "Refund Confirmation: ord_d86c9e33bf", "to": "amina.hassan+122cedbfe9@example.com"}`; error `—`
- `tc_92920659f97e` / `issue_refund` — args `{"amount_cents": 4700, "idempotency_key": "idem_89804e656d4d4b64", "intent_id": "int_5d89e28d8aad", "order_id": "ord_d86c9e33bf", "tool_call_id": "tc_92920659f97e"}`; result `{"ok": true, "refund_id": "rf_cb41a6dfe4df", "replayed": false, "requested_amount_cents": 4700, "requested_order_id": "ord_d86c9e33bf", "status": "refunded", "transaction_id": "txn_cb41a6dfe4df"}`; error `—`
