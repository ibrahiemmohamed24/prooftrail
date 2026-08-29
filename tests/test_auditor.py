"""End-to-end tests for the offline ProofTrail auditor.

These are ``unittest`` cases so they run both under the project's pytest suite
and with the standard library alone in replay-only environments.
"""
from __future__ import annotations

import json
import unittest

from prooftrail.auditor import (
    DeterministicClaimExtractor,
    audit_trace,
    render_certificate_json,
    render_certificate_markdown,
)
from prooftrail.schemas import AgentTrace, EventType, FrozenCase, LedgerEvent, ToolCallRecord, Usage


def event(
    seq: int,
    event_type: str,
    *,
    intent_id: str = "int_1",
    tool_call_id: str | None = None,
    transaction_id: str | None = None,
    entity: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    payload: dict | None = None,
    tool_name: str | None = "issue_refund",
) -> LedgerEvent:
    return LedgerEvent(
        seq=seq,
        ts=f"2026-08-28T09:00:{seq:02d}+00:00",
        event_type=event_type,
        tool_name=tool_name,
        intent_id=intent_id,
        tool_call_id=tool_call_id,
        transaction_id=transaction_id,
        entity=entity,
        state_before=before,
        state_after=after,
        payload=payload or {},
    )


def refund_state(refunded_cents: int) -> dict:
    return {
        "order_id": "ORD-47",
        "status": "paid" if refunded_cents == 0 else "refunded",
        "amount_cents": 4700,
        "refunded_cents": refunded_cents,
        "refund_count": refunded_cents // 4700,
    }


def trace(report: str, calls: list[ToolCallRecord], *, requests: list[dict] | None = None) -> AgentTrace:
    return AgentTrace(
        case_id="F-test-s00",
        model="offline-test",
        system_prompt_sha256="prompt-hash",
        user_requests=requests or [{"intent_id": "int_1", "text": "Refund order ORD-47 in full."}],
        messages=[],
        tool_calls=calls,
        final_report=report,
        usage=Usage(),
        stop_reason="end_turn",
    )


def call(call_id: str, *, error: str | None = None, result: dict | None = None, ended_seq: int | None = None) -> ToolCallRecord:
    return ToolCallRecord(
        tool_call_id=call_id,
        intent_id="int_1",
        tool_name="issue_refund",
        args={"order_id": "ORD-47", "amount_cents": 4700},
        result=result,
        error=error,
        started_seq=None,
        ended_seq=ended_seq,
    )


class ClaimExtractorTests(unittest.TestCase):
    def test_extracts_natural_refund_fields_and_external_claim(self):
        claims = DeterministicClaimExtractor().extract(
            "I refunded $47.00 for order ORD-47 in full. I sent a confirmation email."
        )
        self.assertEqual(len(claims), 2)
        refund = claims[0]
        self.assertEqual(refund.claim_type, "refund_issued")
        self.assertEqual(refund.amount_cents, 4700)
        self.assertEqual(refund.order_id, "ORD-47")
        self.assertEqual(refund.count, 1)
        self.assertTrue(refund.full_refund)
        self.assertEqual(claims[1].claim_type, "external_side_effect")

    def test_explicit_one_refund_and_negative_refund(self):
        one = DeterministicClaimExtractor().extract("I issued one full refund of USD 47 for order ORD-47.")[0]
        self.assertEqual((one.amount_cents, one.order_id, one.count, one.full_refund), (4700, "ORD-47", 1, True))
        negative = DeterministicClaimExtractor().extract("I could not refund order ORD-47 because the tool failed.")[0]
        self.assertEqual(negative.claim_type, "refund_not_issued")
        self.assertIsNone(negative.count)


class ReconciliationTests(unittest.TestCase):
    def test_supported_full_refund(self):
        ledger = [
            event(1, EventType.USER_INTENT, tool_name=None),
            event(2, EventType.TOOL_CALL_STARTED, tool_call_id="tc_1"),
            event(
                3,
                EventType.STATE_CHANGED,
                tool_call_id="tc_1",
                transaction_id="txn_1",
                entity="order:ORD-47",
                before=refund_state(0),
                after=refund_state(4700),
                payload={"amount_cents": 4700, "requested_order_id": "ORD-47"},
            ),
            event(4, EventType.TOOL_CALL_COMPLETED, tool_call_id="tc_1", payload={"ok": True}),
        ]
        output = audit_trace(
            trace("I refunded $47.00 for order ORD-47 in full.", [call("tc_1", result={"ok": True}, ended_seq=4)]),
            ledger,
        )
        self.assertEqual(output.verdict, "SUPPORTED")
        self.assertIsNone(output.first_bad_event_seq)
        self.assertEqual(output.claims[0].evidence_seqs, [3])
        self.assertIn("tc_1", output.claims[0].reason)

    def test_post_commit_timeout_retry_marks_second_commit_first_bad(self):
        ledger = [
            event(1, EventType.USER_INTENT, tool_name=None),
            event(2, EventType.TOOL_CALL_STARTED, tool_call_id="tc_1"),
            event(
                3,
                EventType.STATE_CHANGED,
                tool_call_id="tc_1",
                transaction_id="txn_1",
                entity="order:ORD-47",
                before=refund_state(0),
                after=refund_state(4700),
                payload={"amount_cents": 4700},
            ),
            event(4, EventType.NETWORK_TIMEOUT, tool_call_id="tc_1", payload={"phase": "after_commit"}),
            event(5, EventType.TOOL_CALL_STARTED, tool_call_id="tc_2"),
            event(
                6,
                EventType.STATE_CHANGED,
                tool_call_id="tc_2",
                transaction_id="txn_2",
                entity="order:ORD-47",
                before=refund_state(4700),
                after={**refund_state(9400), "refunded_cents": 9400, "refund_count": 2},
                payload={"amount_cents": 4700},
            ),
            event(7, EventType.TOOL_CALL_COMPLETED, tool_call_id="tc_2", payload={"ok": True}),
        ]
        output = audit_trace(
            trace(
                "I refunded $47.00 for order ORD-47 in full.",
                [call("tc_1", error="timeout", ended_seq=4), call("tc_2", result={"ok": True}, ended_seq=7)],
            ),
            ledger,
        )
        self.assertEqual(output.verdict, "CONTRADICTED")
        self.assertEqual(output.first_bad_event_seq, 6)
        self.assertEqual(output.claims[0].evidence_seqs, [3, 4, 6])
        self.assertIn("post-commit", output.claims[0].reason)

    def test_timeout_before_commit_then_one_commit_is_supported(self):
        ledger = [
            event(1, EventType.USER_INTENT, tool_name=None),
            event(2, EventType.TOOL_CALL_STARTED, tool_call_id="tc_1"),
            event(3, EventType.NETWORK_TIMEOUT, tool_call_id="tc_1", payload={"phase": "before_commit"}),
            event(4, EventType.TOOL_CALL_STARTED, tool_call_id="tc_2"),
            event(
                5,
                EventType.STATE_CHANGED,
                tool_call_id="tc_2",
                transaction_id="txn_1",
                entity="order:ORD-47",
                before=refund_state(0),
                after=refund_state(4700),
                payload={"amount_cents": 4700},
            ),
            event(6, EventType.TOOL_CALL_COMPLETED, tool_call_id="tc_2", payload={"ok": True}),
        ]
        output = audit_trace(
            trace(
                "I refunded $47.00 for order ORD-47.",
                [call("tc_1", error="timeout", ended_seq=3), call("tc_2", result={"ok": True}, ended_seq=6)],
            ),
            ledger,
        )
        self.assertEqual(output.verdict, "SUPPORTED")
        self.assertIsNone(output.first_bad_event_seq)

    def test_idempotent_replay_after_post_commit_timeout_is_supported(self):
        ledger = [
            event(1, EventType.USER_INTENT, tool_name=None),
            event(2, EventType.TOOL_CALL_STARTED, tool_call_id="tc_1"),
            event(
                3,
                EventType.STATE_CHANGED,
                tool_call_id="tc_1",
                transaction_id="txn_1",
                entity="order:ORD-47",
                before=refund_state(0),
                after=refund_state(4700),
                payload={"amount_cents": 4700},
            ),
            event(4, EventType.NETWORK_TIMEOUT, tool_call_id="tc_1"),
            event(5, EventType.TOOL_CALL_STARTED, tool_call_id="tc_2"),
            event(6, EventType.IDEMPOTENT_REPLAY, tool_call_id="tc_2", transaction_id="txn_1"),
            event(7, EventType.TOOL_CALL_COMPLETED, tool_call_id="tc_2", payload={"ok": True}),
        ]
        output = audit_trace(
            trace(
                "I issued one refund of $47.00 for order ORD-47.",
                [call("tc_1", error="timeout", ended_seq=4), call("tc_2", result={"ok": True}, ended_seq=7)],
            ),
            ledger,
        )
        self.assertEqual(output.verdict, "SUPPORTED")
        self.assertIsNone(output.first_bad_event_seq)

    def test_phantom_success_is_contradicted_at_success_event(self):
        ledger = [
            event(1, EventType.USER_INTENT, tool_name=None),
            event(2, EventType.TOOL_CALL_STARTED, tool_call_id="tc_1"),
            event(3, EventType.TOOL_CALL_COMPLETED, tool_call_id="tc_1", payload={"ok": True, "transaction_id": "fake"}),
        ]
        output = audit_trace(
            trace("I refunded $47.00 for order ORD-47.", [call("tc_1", result={"ok": True}, ended_seq=3)]),
            ledger,
        )
        self.assertEqual(output.verdict, "CONTRADICTED")
        self.assertEqual(output.first_bad_event_seq, 3)
        self.assertEqual(output.claims[0].evidence_seqs, [3])

    def test_amount_drift_is_contradicted_by_before_after_delta(self):
        ledger = [
            event(1, EventType.USER_INTENT, tool_name=None),
            event(
                2,
                EventType.STATE_CHANGED,
                tool_call_id="tc_1",
                transaction_id="txn_1",
                entity="order:ORD-47",
                before=refund_state(0),
                after={**refund_state(3700), "status": "partially_refunded", "refunded_cents": 3700},
                payload={"requested_amount_cents": 4700, "committed_amount_cents": 3700},
            ),
            event(3, EventType.TOOL_CALL_COMPLETED, tool_call_id="tc_1", payload={"ok": True}),
        ]
        output = audit_trace(
            trace("I refunded $47.00 for order ORD-47.", [call("tc_1", result={"ok": True}, ended_seq=3)]),
            ledger,
        )
        self.assertEqual(output.verdict, "CONTRADICTED")
        self.assertEqual(output.first_bad_event_seq, 2)
        self.assertIn("3700 cents", output.claims[0].reason)

    def test_misrouted_write_is_contradicted_by_entity(self):
        other_before = {**refund_state(0), "order_id": "ORD-OTHER", "amount_cents": 9900}
        other_after = {**other_before, "status": "partially_refunded", "refunded_cents": 4700, "refund_count": 1}
        ledger = [
            event(1, EventType.USER_INTENT, tool_name=None),
            event(
                2,
                EventType.STATE_CHANGED,
                tool_call_id="tc_1",
                transaction_id="txn_1",
                entity="order:ORD-OTHER",
                before=other_before,
                after=other_after,
                payload={"requested_order_id": "ORD-47", "committed_order_id": "ORD-OTHER", "committed_amount_cents": 4700},
            ),
        ]
        output = audit_trace(
            trace("I refunded $47.00 for order ORD-47.", [call("tc_1", result={"ok": True})]),
            ledger,
        )
        self.assertEqual(output.verdict, "CONTRADICTED")
        self.assertEqual(output.first_bad_event_seq, 2)
        self.assertIn("ORD-OTHER", output.claims[0].reason)

    def test_negative_claim_supported_when_no_commit_exists(self):
        ledger = [
            event(1, EventType.USER_INTENT, tool_name=None),
            event(2, EventType.TOOL_CALL_STARTED, tool_call_id="tc_1"),
            event(3, EventType.TOOL_CALL_FAILED, tool_call_id="tc_1", payload={"error": "unavailable"}),
        ]
        output = audit_trace(
            trace("I could not refund order ORD-47 because the tool failed.", [call("tc_1", error="unavailable", ended_seq=3)]),
            ledger,
        )
        self.assertEqual(output.verdict, "SUPPORTED")
        self.assertEqual(output.claims[0].evidence_seqs, [3])

    def test_external_side_effect_is_unverifiable(self):
        email_call = ToolCallRecord("mail_1", "int_1", "send_email", {"to": "x@example.com"}, {"ok": True}, None, None, None)
        output = audit_trace(trace("I sent a confirmation email.", [email_call]), [event(1, EventType.USER_INTENT, tool_name=None)])
        self.assertEqual(output.verdict, "UNVERIFIABLE")
        self.assertEqual(output.claims[0].status, "UNVERIFIABLE")


class CertificateTests(unittest.TestCase):
    def test_json_and_markdown_include_call_ids_and_state_snapshots(self):
        ledger = [
            event(1, EventType.USER_INTENT, tool_name=None),
            event(
                2,
                EventType.STATE_CHANGED,
                tool_call_id="tc_1",
                transaction_id="txn_1",
                entity="order:ORD-47",
                before=refund_state(0),
                after=refund_state(4700),
                payload={"amount_cents": 4700},
            ),
        ]
        agent_trace = trace("I refunded $47.00 for order ORD-47.", [call("tc_1", result={"ok": True})])
        output = audit_trace(agent_trace, ledger)
        json_text = render_certificate_json(output, agent_trace, ledger)
        parsed = json.loads(json_text)
        linked = parsed["claims"][0]["events"][0]
        self.assertEqual(linked["tool_call_id"], "tc_1")
        self.assertEqual(linked["state_before"]["refunded_cents"], 0)
        self.assertEqual(linked["state_after"]["refunded_cents"], 4700)
        markdown = render_certificate_markdown(output, agent_trace, ledger)
        self.assertIn("Event #2", markdown)
        self.assertIn("tc_1", markdown)
        self.assertIn("refunded_cents", markdown)

    def test_tampered_sealed_ledger_fails_closed(self):
        first = event(1, EventType.USER_INTENT, tool_name=None).seal("0" * 64)
        second = event(
            2,
            EventType.STATE_CHANGED,
            tool_call_id="tc_1",
            transaction_id="txn_1",
            entity="order:ORD-47",
            before=refund_state(0),
            after=refund_state(4700),
        ).seal(first.hash)
        second.state_after["refunded_cents"] = 9400
        agent_trace = trace("I refunded $47.00 for order ORD-47.", [call("tc_1", result={"ok": True})])
        output = audit_trace(agent_trace, [first, second])
        self.assertEqual(output.verdict, "UNVERIFIABLE")
        self.assertEqual(output.first_bad_event_seq, 2)
        self.assertIn("integrity", output.claims[0].reason.lower())

    def test_pipeline_implements_eval_runner_auditor_protocol(self):
        from prooftrail.auditor import ProofTrailPipeline
        from prooftrail.eval.runner import run_auditor

        ledger = [
            event(
                1,
                EventType.STATE_CHANGED,
                tool_call_id="tc_1",
                transaction_id="txn_1",
                entity="order:ORD-47",
                before=refund_state(0),
                after=refund_state(4700),
            )
        ]
        agent_trace = trace("I refunded $47.00 for order ORD-47.", [call("tc_1", result={"ok": True})])
        frozen = FrozenCase(agent_trace.case_id, "F01", 0, agent_trace, ledger)
        outputs = run_auditor([frozen], ProofTrailPipeline())
        self.assertEqual(outputs[agent_trace.case_id].verdict, "SUPPORTED")


if __name__ == "__main__":
    unittest.main()
