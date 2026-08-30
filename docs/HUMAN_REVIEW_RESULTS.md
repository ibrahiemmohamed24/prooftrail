# Human review results — frozen dataset v1

> **Status: complete and headline eligible.** `python -m prooftrail review
> verify --require-complete` passes with 40/40 accepted decisions, zero abstentions,
> zero invalid or stale records, and a source-bound manifest marked
> `headline_eligible: true`.

## 1. Reviewer identity

| Field | Value |
|---|---|
| GitHub identity used in every decision | `github:ibrahiemmohamed24` |
| Display name | Ibrahiem Mohamed |
| Relationship to the project | Project author and repository owner |
| Review branch and commit | `feat/final-submission`; see the commit containing `data/reviews/v1/decisions/` |

Decision files bind this identity to the dataset manifest, frozen case,
provisional label, exact review material and ledger tip. Git history and the
pull request provide the repository-level authenticity layer.

## 2. Scope and counts

| Metric | Value |
|---|---:|
| Cases in the dataset | 40 (10 families × 4 seeds) |
| Cases reviewed / accepted | 40 / 40 |
| `APPROVE` | 33 |
| `AMEND` | 7 |
| `ABSTAIN` | 0 |
| Invalid / stale decisions | 0 |
| `headline_eligible` | `true` |

The deterministic manifest is `data/reviews/v1/manifest.json`. Every accepted
decision has a case-specific rationale, UTC timestamp, explicit attestation and
hashes tying it to the immutable source material.

## 3. Review time (measured, not estimated)

The source log is `data/reviews/v1/time_log.csv`; breaks and discussion pauses
were excluded from active time.

| Metric | Value |
|---|---:|
| Sittings | 2 |
| Total active review time | 298 minutes |
| Mean active time per case | 7.45 minutes (reported as 7.5) |
| Median time per case | 4 minutes |
| Cases covered | 40 |

This measures time to establish ground truth from raw evidence. It is not a
controlled comparison of reviewer time with versus without ProofTrail.

## 4. Review method

For every case, the reviewer:

1. read the request, final report, agent-visible tool calls and full ledger in
   `evidence/review-pack-v1/<case>.review.md`;
2. identified each material claim (refund, amount, order, count and email);
3. matched action claims only to ledger `state_changed` writes, not to tool
   return values;
4. checked timeouts, retries, idempotent replays and the earliest contradicting
   event;
5. made the decision before using ProofTrail's `audit.json` or certificate as
   an answer key;
6. recorded one source-bound `APPROVE`, `AMEND` or `ABSTAIN` decision with an
   explicit `--attest-reviewed` acknowledgement.

## 5. Cases that needed extra attention

| Group | Cases | Decision |
|---|---|---|
| Email claim outside the ledger | F07-s02, F07-s03, F09-s00, F09-s01, F09-s02, F09-s03, F10-s02 | `AMEND`: retain `UNVERIFIABLE`, add the ledger-supported refund claim(s); verdict and first-bad event unchanged |
| B1 wrong in all three runs | F04-s00, F04-s01, F04-s02, F04-s03 | `APPROVE`: no `state_changed` exists, so the success report is contradicted despite `tool_call_completed{ok:true}` |
| B1 verdict changed across runs | F06-s00, F06-s01, F06-s03, F07-s02, F07-s03 | F06 labels approved from entity-level ledger evidence; F07 claim lists amended as described above |
| All amended cases | F07-s02, F07-s03, F09-s00, F09-s01, F09-s02, F09-s03, F10-s02 | Claim-list correction only; no verdict or first-bad change |
| Abstentions | none | No case lacked enough ledger evidence to choose a benchmark label |

## 6. Limitations and possible biases

- One author-affiliated reviewer; no inter-annotator agreement was measured.
- The reviewer could see the machine pre-annotation after inspecting the raw
  evidence, so anchoring remains possible despite the prescribed reading order.
- Dataset v1 is synthetic and restricted to refund workflows.
- Repeated structures create learning effects; later cases were generally
  reviewed faster.

## 7. What was not measured

Human time **with** ProofTrail's certificate versus **without** it was not
measured. No productivity delta is claimed. The benchmark measures audit
correctness, evidence coverage and first-bad localization, not reviewer speedup.

## 8. Integrity statement

- The reviewer personally read the 40 cases, selected every decision and
  executed every explicit attestation. No bulk-approval path was used.
- AI assistance generated reading aids and helped transcribe the reviewer's
  already-made conclusions into case-specific CLI rationales and amendment
  JSON. It did not choose a verdict, inspect evidence on the reviewer's behalf
  or execute the human attestation.
- `data/frozen/`, `data/replay/gemini/` and `data/replay/auditors/` were not
  modified during review; the corresponding Git diff is empty.
- The verified comparison is derived offline from the accepted decisions and
  the already committed B1 artifacts.

Signed off: Ibrahiem Mohamed (`github:ibrahiemmohamed24`), 2026-08-30.
