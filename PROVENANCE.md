# Provenance and AI use

This document records the archived competition snapshot. Active development
continues in `ibrahiemmohamed24/prooftrail`, which preserves its existing Git
history and subsequent frontend contributions. Historical sole-participant
statements below apply to the competition submission.

The detailed tool-by-tool responsibility statement and representative coding
agent traces are in `docs/AI_TOOL_DISCLOSURE.md` and
`docs/CODEX_TRAJECTORIES.md`.

## Sole human author

ProofTrail is an individual submission by **Ibrahiem Mohamed**
(`github:ibrahiemmohamed24`). The author selected the problem, directed every
development iteration, chose the acceptance criteria, ran the evaluation,
personally reviewed and attested all 40 benchmark decisions, and prepared the
final submission. There is no human co-author.

Some OpenAI Codex development sessions were run on a second computer whose
local Git author configuration belonged to that computer's owner. That machine
metadata did not represent human authorship. The final submission repository
was exported from the verified tracked tree and initialized with the sole
author's GitHub-linked identity. Exporting the snapshot did not alter the code,
frozen traces, review decisions, hashes or benchmark results.

## Development AI assistance

**OpenAI Codex was the only AI coding assistant used to build and document the
project.** Codex helped generate and revise code, tests, documentation, review
reading aids and CLI transcription material under the author's direction.
The author decided what to build, inspected the outputs, executed all commands
used as evidence and accepted the final changes.

Codex did not make or attest any human-review decision. For the seven amended
cases, it helped format conclusions the author had already reached; the author
personally selected each decision and executed every case-specific
`--attest-reviewed` acknowledgement.

## Runtime and evaluation models

Runtime model use is separate from development assistance:

- The committed 40-case refund-agent dataset and the three B1 baseline runs
  were recorded with Google Gemini `gemini-3.1-flash-lite` on synthetic data.
- Gemini was the system under test and the comparison baseline, not a coding
  assistant for the project.
- An optional Anthropic adapter is included and tested over a local mock
  transport, but no Anthropic live output contributes to the reported result.
- ProofTrail itself makes zero model calls during auditing.

## Evidence provenance

- `data/frozen/` contains 40 real-model traces, provisional labels and a
  hash-validating manifest: 10 scenario families × 4 deterministic seeds.
- `data/replay/gemini/` contains the prompt-hash response caches used to freeze
  those traces: 175 calls, billed `$0.00`.
- `data/replay/auditors/` and `evidence/runs/benchmark/b1/` contain three
  independent B1 runs: 120 accepted outputs, billed `$0.00`.
- `data/reviews/v1/` contains 40 source-bound decisions by the sole author:
  33 `APPROVE`, 7 `AMEND`, 0 `ABSTAIN`.
- `comparison.verified.{json,md}` is generated offline from those committed
  artifacts and reports `headline_eligible: true`.
- The five-second F02 demonstration uses `ScriptedModelClient` and is labelled
  as a fixture. It demonstrates the failure shape and is not represented as a
  real-model result.

## Privacy and cost boundary

All benchmark data is synthetic. No API key, customer record or personal data
is committed. The Gemini Free Tier route sent only synthetic benchmark prompts
to Google and recorded billed cost `$0.00`; list-price equivalents remain in
the artifacts for transparency. Reproduction uses committed caches and needs
no key or network access.

## Remaining external artifact

The solution video is recorded outside Git and linked from `README.md` and
`docs/SUBMISSION_REPORT.md` after upload.
