# AI Tool Disclosure

Scope: this is the historical disclosure for the archived competition snapshot
in `prooftrail-submission`. Statements about sole participation and reinitialized
Git history apply to that snapshot, not to all subsequent work in the active
`prooftrail` repository. Later UI development and integration retain their
original contributor history in the active repository.

This disclosure separates human judgment, coding-agent assistance, runtime
model use and deterministic software. It is part of the submission package.

## Sole participant

**Ibrahiem Mohamed** (`github:ibrahiemmohamed24`) is the sole human participant.
He selected the ProofTrail problem, set scope and acceptance criteria, directed
the coding agent, ran the live and replay commands, supplied the user-owned API
key through environment variables, inspected failures, decided which changes
to accept, personally reviewed all 40 benchmark cases and executed every human
attestation.

Some Codex sessions were run on a second computer because the first Codex
session had reached its usage limit. That computer initially supplied the wrong
local Git author metadata. Its owner did not provide code, design decisions or
review judgments. The final repository was initialized from the verified
tracked snapshot with the participant's GitHub-linked identity.

### Public repository history note

The public repository begins with a single publication snapshot on August 31.
That commit timestamp is not presented as the development timeline. Iteration
dates in `CHANGELOG.md` are supported by frozen run metadata, prompt-hash
caches, benchmark specifications, review timestamps and generated evidence.
The repository was reinitialized only to correct machine-derived Git author
metadata; the verified tree and evidence were preserved.

## Tools and responsibilities

| Tool or component | Role | What it did not do | Evidence |
|---|---|---|---|
| OpenAI Codex | The only AI coding assistant. Generated and revised code, tests and documentation; ran or proposed terminal checks; diagnosed failures; prepared review reading aids and formatted already-decided amendments under human direction. Current local CLI reports `codex-cli 0.151.0-alpha.7.2`; exact model identifiers for earlier sessions were not retained, so none is invented here. | Did not choose or attest human labels, provide an API key, approve consequential actions or make the final submission decision. | `docs/CODEX_TRAJECTORIES.md`, `CHANGELOG.md`, tests and generated artifacts. |
| Google Gemini `gemini-3.1-flash-lite` | Runtime model for the refund agent under test and the B1 baseline auditor. | Was not used as a coding assistant and did not define benchmark truth. | `data/replay/gemini/`, `data/replay/auditors/`, `data/frozen/manifest.json`. |
| ProofTrail | Deterministic auditor over the frozen trace and append-only ledger. | Makes no model call and cannot approve a review decision. | `prooftrail/auditor/`, verified comparison. |
| ScriptedModelClient | Deterministic five-second demonstration fixture. | Is not represented as a real-model run or benchmark evidence. | `evidence/runs/demo-f02/`. |
| Human reviewer | The sole participant, acting case by case with source-bound attestation. | No bulk approval; no AI or script attested on the reviewer's behalf. | `data/reviews/v1/`, `docs/HUMAN_REVIEW_RESULTS.md`. |

## Instructions that shaped each agent

- Refund-agent system instructions: `prooftrail/agent/prompts.py`
  (SHA-256 `2edcd453cc0e4a0881c8d57573bdec3bef84db39732b435b6ececd15f4756813`).
- B1 system and user-prompt builder: `prooftrail/baselines/prompts.py`
  (file SHA-256 `6e6cbde25e02b7c105ae3283c023c9097dc3da6aa4284f4e3310a68910db4a4a`).
- Codex received iterative natural-language instructions from the participant;
  representative instruction/action/feedback sequences are preserved in
  `docs/CODEX_TRAJECTORIES.md`.

Provider response caches also record prompt hashes for every accepted runtime
model completion. Replays fail on a prompt or model mismatch.

## Before and during the challenge

Before the challenge build there was no runnable ProofTrail solution, frozen
dataset, executable same-evidence baseline, verified benchmark or submission
package. The foundation, stateful environment, auditors, real-model traces,
human-review workflow, evaluation and submission materials were built during
the August 28–31 challenge window. `CHANGELOG.md` records each meaningful
iteration and the evidence that shaped the next decision.

## Consequential-action boundary

All refunds, customers and orders are synthetic and run in a local SQLite
simulation. No real refund, email or customer system is accessible. Human
approval is required for benchmark truth: the reporting command fails closed
until all source-bound review decisions are valid and complete.

## Credentials and privacy

Keys were supplied only through environment variables and removed after live
recording. No secret appears in the repository or the representative
trajectories. Local absolute paths, account tokens and unrelated conversation
content are omitted from the curated Codex trajectory excerpts. The secret
scanner runs locally and in CI.
