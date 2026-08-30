# ProofTrail

**Evidence-linked auditing of what an AI agent *says* it did versus what the ledger *proves* it did.**

> Same evidence. Independent truth. Frozen traces.

## The result

<!-- UPDATE-AFTER-VERIFIED-REPORT: replace this block with the outcome table from
     evidence/runs/benchmark/comparison/comparison.verified.md once
     `python -m prooftrail review verify --require-complete` passes. -->

**Verified result: not yet available.** Human review of the 40 labels is
`0/40` (`python -m prooftrail review status`), and the benchmark report refuses
verified mode until every case carries an accepted human decision.

What is already committed and replays with **no API key**:

- 40 real traces of a tool-using refund agent (`gemini-3.1-flash-lite`, Gemini
  Free Tier, billed **$0.00**), frozen in `data/frozen/`;
- three independent runs of the fair one-shot LLM baseline **B1** over the same
  evidence (120 accepted outputs, billed $0.00);
- a provisional diagnostic, machine-marked `headline_eligible: false`, in which
  B1 scores 85.0% ± 2.04 pp family-mean accuracy and deterministic ProofTrail
  agrees with all 40 ledger-derived provisional labels at zero model cost. This
  is a diagnostic, not a result: the labels are not human-reviewed yet.

## The killer case in five seconds

```powershell
python -m prooftrail demo
```

```text
Agent claimed : I refunded $47.00 for order ord_82efdfe20a.
Ledger proved : 2 commits, $94.00 refunded
Verdict       : CONTRADICTED
First bad     : ledger event #6
Hash chain    : valid
```

The timeout is **not** the bad event — the first refund had already committed.
The first harmful action is the second `state_changed` under the same intent,
event #6. ProofTrail hands a reviewer that one event instead of a transcript.

This command runs `ScriptedModelClient`, a deterministic offline fixture, and
records `mode: scripted-offline-demo-not-a-real-llm-run`. It shows the failure
shape; it is not real-model evidence. The real F02 traces are different — see
[docs/TRAJECTORIES.md](docs/TRAJECTORIES.md): the real agent called
`list_refunds` after the timeout and did **not** double-refund.

## The problem

The engineer or support lead who owns an agent that performs irreversible
actions (refunds, cancellations, account changes) reads transcripts to answer
one question: *did it actually do what it claims?* The transcript records what
the agent *believed*. Only the system of record says what *happened* — and the
worst cases (a double refund after a post-commit timeout, a tool that says
`ok: true` and commits nothing) look completely normal in the transcript.

ProofTrail returns a verdict per report — `SUPPORTED` / `CONTRADICTED` /
`UNVERIFIABLE` — with every material claim linked to the ledger events that
support or contradict it, and the first event where things went wrong.

## One diagram

```text
Real LLM refund agent ──► mock refund tools ──► SQLite state + append-only hash-chained ledger
                                                          │
                              frozen trace + raw ledger ◄─┘   (family / seed / case id stripped)
                              ├── B1  fair baseline: one-shot LLM judges the same evidence (3 runs)
                              └── ProofTrail: deterministic claim extraction → evidence linking
                                              → state reconciliation → temporal verification
                                              → evidence certificate  (0 model calls)
                                                          │
                              ledger-derived provisional label ──► explicit human decision ──► benchmark truth
```

Three rules: **same evidence** (B1 and ProofTrail get the identical
`auditor_view`), **independent truth** (labels come from the ledger, then from a
named human, never from any model), **frozen traces** (the agent runs once;
everything else replays).

## Quickstart — zero API calls

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest                                      # 212 passed, no network
python -m prooftrail demo                             # scripted killer case
python -m prooftrail replay --provider gemini --all   # 40 real traces, byte-for-byte, no key
python -m prooftrail manifest --provider gemini       # 40/40, invariants
```

macOS/Linux: `python3 -m venv .venv && . .venv/bin/activate`, same commands.
Full judge walkthrough with expected outputs: [docs/JUDGE_CHECKLIST.md](docs/JUDGE_CHECKLIST.md).

## Comparison — same evidence, three B1 runs

<!-- UPDATE-AFTER-VERIFIED-REPORT: replace with comparison.verified.md outcome table. -->

**Verified table: pending human review.** The provisional diagnostic below is
reproduced for transparency only; every label in it is ledger-derived and
`verified_by_human: false`.

| Auditor (provisional labels — not headline) | Family-mean accuracy | Macro-F1 | First-bad hit rate | Evidence coverage | Model calls |
|---|---:|---:|---:|---:|---:|
| B1 one-shot LLM, 3-run mean ± SD | 85.0% ± 2.0% | 86.5% ± 1.4% | 66.7% ± 7.8% | 86.1% ± 1.1% | 1 / case |
| ProofTrail (deterministic) | 100.0% | 100.0% | 100.0% | 81.5% | 0 |

- B1 verdict unanimity across runs: 35/40. It is wrong in **all three runs** on
  every F04 case (phantom success: it trusts `tool_call_completed{ok:true}`
  over an empty ledger) and flips verdict on F06-s00/s01/s03 and F07-s02/s03.
- Disabling ProofTrail's temporal verifier changes **0** verdicts on this
  dataset. We report that as a negative result; no gain is claimed for it.
- ProofTrail's 40/40 is a consistency check against labels derived from the
  same ledger until the human review lands.

Regenerate: `python -m prooftrail benchmark report --allow-provisional`
(diagnostic) or `python -m prooftrail benchmark report` (verified; fails by
design until the review is complete).

## Cost

| Item | Billed | List-price equivalent |
|---|---:|---:|
| Agent: 40 cases, 175 calls, 142,227 in / 16,950 out tokens | $0.00 | $0.061 |
| B1: 3 × 40 predictions, 891,687 in / 190,214 out tokens | $0.00 | $0.508 ($0.004235 per prediction) |
| ProofTrail: 40 audits | $0.00 | $0.00 (no model calls) |

All recording used the Gemini Free Tier on synthetic data; list prices are
recorded per call so the economic value is not hidden. Human review time will be
recorded in a time log during the review, never estimated; see
[docs/HUMAN_REVIEW_RESULTS.md](docs/HUMAN_REVIEW_RESULTS.md) (pending).

## Review integrity

- `labels.provisional.json` is derived from the ledger and always says
  `verified_by_human: false`; it is never edited.
- A named person records one decision per case —
  `python -m prooftrail review decide --case F04-s00 --approve|--amend|--abstain … --attest-reviewed` —
  bound by SHA-256 to the dataset manifest, frozen case, provisional label,
  exact review material and ledger tip. There is no `--all`.
- `ABSTAIN` is honest and valid; it removes the case from any headline.
- `python -m prooftrail benchmark report` refuses verified mode until
  `review verify --require-complete` passes. No AI, script or author may
  attest for the reviewer. Procedure: [docs/HUMAN_REVIEW.md](docs/HUMAN_REVIEW.md);
  reading aid: [docs/REVIEW_FOCUS_v1.md](docs/REVIEW_FOCUS_v1.md).

## Architecture

| Layer | Where | LLM? |
|---|---|---|
| Stateful world, fault injection, atomic state + ledger commit | `prooftrail/env/` | no |
| Ten scenario families, deterministic seeds, provisional truth | `prooftrail/scenarios/` | no |
| Refund agent loop, Anthropic (paid, budget-guarded) and Gemini (free) adapters, prompt-hash replay | `prooftrail/agent/` | yes — data creation only |
| Freeze / replay / manifest integrity | `prooftrail/freeze.py` | no |
| B1 one-shot baseline, strict JSON, explicit spec per run, fail-closed | `prooftrail/baselines/`, `prooftrail/benchmark.py` | yes |
| ProofTrail: deterministic extractor → linker → reconciler → temporal verifier → certificate | `prooftrail/auditor/` | **no** |
| Family-balanced metrics, hash-validated comparison, ablation | `prooftrail/eval/`, `prooftrail/benchmark_report.py` | no |
| Source-bound human review packs, decisions, manifest | `prooftrail/review.py` | no |

ProofTrail's claim extractor is deterministic and refund-domain specific. An
LLM-backed extractor is a planned ablation, not part of any reported number.
Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Limitations

- Synthetic refund domain; nothing here transfers to other domains untested.
- One provider and one model (`gemini-3.1-flash-lite`) for both agent and B1.
- The deterministic claim extractor is narrow; unfamiliar phrasing surfaces as
  `UNVERIFIABLE`, not as a confident verdict.
- The temporal verifier showed no measured gain on dataset v1.
- Single, author-affiliated reviewer; no inter-annotator agreement.
- Human time *with vs without* ProofTrail was not measured and is not claimed.

## Demo video

<!-- UPDATE-AFTER-VERIFIED-REPORT: add the link. -->

Link: **to be added by the authors after the verified report exists** — script
and recording rules in [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

## Reproduction

[REPRODUCE.md](REPRODUCE.md) covers the offline path, recording a new dataset
on either provider, freezing, B1 runs and the clean-clone verification list.
Recording is optional: every number in this repository replays from committed
caches without a key. Keys, when used, are read from the environment only;
`scripts/check_no_secrets.py` runs in CI.

## Repository map

```text
prooftrail/              package (stdlib-only core; the Anthropic SDK is optional, for --live)
data/frozen/<case>/      40 immutable real-model cases + provisional labels + manifest
data/replay/gemini/      agent response caches (prompt-hash keyed)
data/replay/auditors/    three B1 cache namespaces (spec-hashed)
data/reviews/v1/         human decisions, review manifest, time log
evidence/runs/           demo bundle, live smoke bundle, B1 run artifacts, comparison reports
docs/                    ARCHITECTURE, SCENARIO_FAMILIES, HUMAN_REVIEW, HUMAN_REVIEW_RESULTS,
                         REVIEW_FOCUS_v1, SUBMISSION_REPORT, TRAJECTORIES, DEMO_SCRIPT, JUDGE_CHECKLIST
scripts/                 check_no_secrets.py, gen_review_focus.py
tests/                   212 offline tests (mock transports; no network)
PROJECT_STATUS.md        scoring model and earned points; CHANGELOG.md evidence-backed rows
```

## Improvement changelog (historical; provisional rows stay labelled)

| # | Date | Change | Family-mean acc. (B1 → PT) | Notes |
|---|---|---|---|---|
| 0 | 2026-08-28 | Foundation: schemas, SQLite state, hash-chained ledger, families | — | No end-to-end path |
| 1 | 2026-08-28 | Atomic tools + agent replay + deterministic auditor + certificate + CLI | — | F02 demo detects event #6; scripted fixture |
| 2 | 2026-08-29 | 40 real traces frozen (Gemini Free Tier, $0.00) | — | replay 40/40 without a key |
| 3 | 2026-08-30 | Three real B1 repeats + strict offline comparison + no-temporal ablation | 85.0% ± 2.04 pp → 100% | **Provisional only**; `headline_eligible: false` |
| 4 | — | Human review of all 40 labels → verified report | *pending* | fills the tables above |

License: MIT.
