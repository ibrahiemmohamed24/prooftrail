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
- Fair B1 input/output contract, explicit-spec live/cache/replay batch runner,
  offline metrics and report rendering.
- CLI, reproducible F02 demo, 212-test suite, license and secret scanner.
- Paid Anthropic and zero-billed Gemini Free Tier provider adapters, with
  provider-neutral tool calls, usage metadata and prompt-hash replay.
- Forty real-model frozen traces and their provider-response replay caches,
  recorded on Gemini Free Tier using synthetic data only.
- Three independent 40-case B1 response sets, explicit specs and replay caches,
  plus a hash-validating offline comparison and no-temporal ProofTrail ablation.
- Source-bound human-review packs and per-case decision validation. No human
  decision has been produced by the tooling or claimed as complete.

## Still to be produced

- Human-approved labels (currently 0/40).
- A headline-eligible rerender of the committed comparison after those reviews.
- Final trajectories, video and submission report.

No generated demo output is described as a real-model result.

The Gemini free route sends only the synthetic refund benchmark to Google. Per
Google's Free Tier terms, that content may be used to improve Google products.
No customer data, personal data or repository credential is sent.
