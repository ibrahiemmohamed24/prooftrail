# Provenance

This repository had no Git history when the 2026-08-28 implementation milestone
started, so this record states only what can be established from the inspected
files and the current work session.

## Present before this milestone

- Event, trace and verdict schemas.
- Deterministic identity helpers.
- SQLite customer/order/refund state.
- Append-only hash-chained ledger.
- Fault declarations and ten scenario-family specifications.
- Foundation tests and architecture documents.

Those files formed a tested foundation but there was no tool implementation,
agent loop, auditor, baseline runner, evaluator, CLI or end-to-end demo.

## Added or materially completed in this milestone

- Stateful refund tools, deterministic seed data and scenario generation.
- Atomic business-state plus `STATE_CHANGED` writes.
- Provider-neutral agent loop, recorder and explicit scripted replay fixture.
- Claim extraction contract, deterministic evidence linking/reconciliation,
  temporal verifier and JSON/Markdown evidence certificate.
- Fair B1 input/output contract, offline metrics, runner and report rendering.
- CLI, reproducible F02 demo, 98-test suite, license and secret scanner.

## Still to be produced

- Live-provider adapter and real-model traces.
- Forty frozen benchmark cases and cached model responses.
- Human-approved labels and repeated B1/ProofTrail comparison.
- Final trajectories, video and submission report.

No generated demo output is described as a real-model result.
