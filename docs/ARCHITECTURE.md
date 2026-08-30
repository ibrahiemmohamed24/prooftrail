# ProofTrail architecture

> Same evidence. Independent truth. Frozen traces.

This document describes the code that exists at the 85/100 milestone
(`feat/verified-benchmark`, closing on `feat/final-submission`). It deliberately
separates implemented paths from planned work; nothing described as planned is
part of any reported number.

## End-to-end data flow

```text
Real Gemini refund agent (data creation only)
        │ function calls
        ▼
Mock refund tools ──► SQLite state
        │                    │
        └──────────────► append-only, hash-chained ledger
                             │
                             ▼
                 FrozenCase: trace + raw ledger
                    │                    │
                    │                    ├── B1 baseline
                    │                    │   one-shot LLM over the same evidence
                    │                    │   explicit spec + live/frozen replay
                    │                    │
                    │                    └── ProofTrail today
                    │                        deterministic claim extraction
                    │                        + evidence linking
                    │                        + state reconciliation
                    │                        + temporal verification
                    │                        + evidence certificate
                    ▼
       provisional ledger-derived label (not benchmark truth yet)
                    │
                    ▼
       explicit, source-bound human review decision
                    │
                    ▼
       verified GroundTruth resolved in memory for evaluation
```

The refund agent runs only while creating the dataset. The committed 40-case
dataset and prompt-hash replay caches let a judge reproduce its exact traces
without a key, network access, or provider spend.

## Trust boundaries

### 1. Agent view versus system-of-record view

`AgentTrace.tool_calls` records what the agent experienced: returned results,
timeouts and exceptions. The ledger independently records what committed,
including `state_before`, `state_after`, intent, call and transaction IDs. A
post-commit timeout can therefore look uncertain to the agent while remaining
provable in the ledger.

### 2. Auditor input versus hidden labels

Every auditor accepts `FrozenCase`. `FrozenCase.auditor_view()` removes case,
family and seed metadata and returns only the trace and raw ledger. Auditors do
not import the ground-truth generator or open label/review files.

### 3. Provisional labels versus human-reviewed truth

`labels.provisional.json` is deterministic ledger-derived pre-annotation and
always keeps `verified_by_human: false`. It is never edited during review.
Human decisions live separately under `data/reviews/v1/decisions/` and bind:

- the dataset manifest hash;
- the frozen case hash;
- the provisional label hash;
- a canonical hash of the exact material shown to the reviewer; and
- the ledger tip hash.

An accepted decision resolves to `GroundTruth(verified_by_human=True)` only in
memory after all hashes, the ledger chain, the decision hash, reviewer identity,
UTC timestamp, rationale and explicit attestation validate. `ABSTAIN` is a valid
review outcome but produces no benchmark label. There is intentionally no bulk
approve command.

The hashes make changes detectable; they are not identity signatures. Reviewer
authenticity comes from Git history and should be strengthened with a signed
commit or an independently reviewed pull request.

## Current auditor implementations

| Auditor | Evidence | LLM calls per case | Current status |
|---|---|---:|---|
| B1 | family-blind trace + raw ledger | 1 | Three explicit-spec 40-case runs are committed; strict JSON, provider-namespaced caches, artifact hashes and no-network replay are verified |
| ProofTrail deterministic | the same family-blind trace + raw ledger | 0 | Implemented end to end; deterministic refund-domain extractor, linker, reconciler, temporal verifier and certificate |
| ProofTrail hybrid | the same evidence | 1 extractor call, then deterministic checks | Planned ablation; not implemented and not claimed in current results |

The current deterministic extractor is intentionally narrow and auditable. It
is not presented as a general natural-language parser. A future LLM extractor
must implement the same `ClaimExtractor` contract and be reported as a separate
configuration.

## Fair-comparison invariants

The comparison is fair only when the benchmark runner proves all of these:

| Invariant | Enforcement today |
|---|---|
| Same 40 frozen instances | `data/frozen/manifest.json` and per-file SHA-256 hashes |
| Same raw evidence | `FrozenCase.auditor_view()` and `b1_evidence_payload()` |
| No family/case leakage | frozen dataset tests inspect every auditor view |
| Same output contract | `AuditOutput` and fail-closed `validate_audit_output()` |
| Hidden labels | auditor modules never load provisional or reviewed labels |
| Verified labels only in headline metrics | `evaluate_outputs(..., include_unverified=False)` default |
| Family-balanced headline accuracy | unweighted mean across the ten families |
| Resource differences disclosed | usage is part of every `AuditOutput`; deterministic ProofTrail uses 0 calls while B1 uses 1 |

The B1 runner writes an explicit provider, model, limits, system-prompt hash and
dataset-manifest hash beside every output. It does not inherit the old
`config.MODEL` default. The offline comparison validates those specs and the
exact output/failure/summary hashes before scoring. A committed provisional
diagnostic exists, but no B1-versus-ProofTrail **headline** number exists until
the human review manifest is headline-eligible.

## Frozen dataset facts

- 40 cases: 10 scenario families × 4 fixed seeds.
- Real tool-using agent: Gemini `gemini-3.1-flash-lite` Free Tier.
- 175 recorded model calls; 142,227 input and 16,950 output tokens.
- Billed cost: `$0.00`; recorded list-price equivalent: `$0.060977`.
- 133 tool calls and 330 hash-chained ledger events.
- Replay: 40/40 from `data/replay/gemini/`, no key or network.
- Current ProofTrail outputs: 17 `SUPPORTED`, 16 `CONTRADICTED`, 7 `UNVERIFIABLE`.
- Human-reviewed labels: 0/40 at the start of this branch.
- B1: three independent 40-case runs, 120 accepted completions, 891,687 input
  and 190,214 output tokens, billed `$0.00` (list-price equivalent `$0.508242`).
- Provisional-only diagnostics: B1 family-mean accuracy `85.0% ± 2.04 pp`,
  verdict unanimity `35/40`; ProofTrail agreement with provisional labels
  `40/40`. Disabling temporal verification changes no verdict or first-bad
  localization on v1, so the report attributes no measured gain to it.

The 40/40 agreement previously observed between ProofTrail and provisional
labels is only an internal consistency check because both use the same ledger.
It is not a benchmark result.

## Repository map

```text
prooftrail/
├── agent/                  real/replay model boundary, tool-use loop, caches
│   ├── anthropic_client.py paid live adapter with budget guard
│   └── gemini_client.py    zero-billed live adapter used for frozen v1
├── env/                    SQLite world, fault injection and append-only ledger
├── scenarios/              ten families, deterministic instances, provisional truth
├── schemas/                trace, ledger, audit, ground-truth and review contracts
├── auditor/                deterministic ProofTrail pipeline and certificates
├── baselines/              B1 prompt, strict JSON adapter and fail-closed protocol
├── eval/                   runner, family-balanced metrics and reports
├── benchmark.py            explicit B1 live/cache/replay batch runner
├── benchmark_report.py     hash-validated repeats, costs, stability and ablations
├── freeze.py               freeze/replay/manifest integrity
├── review.py               review packs, decisions, validation and resolved truth
└── cli.py                  demo, live/replay/freeze/manifest/review commands

data/
├── frozen/<case>/          immutable case + provisional label + derived artifacts
├── replay/gemini/          committed real-model response caches
├── replay/auditors/b1/     three committed same-evidence B1 cache namespaces
└── reviews/v1/             human decisions and deterministic review manifest

docs/
├── ARCHITECTURE.md         this file
├── HUMAN_REVIEW.md         reviewer procedure and attestation boundary
├── HUMAN_REVIEW_RESULTS.md reviewer identity, counts, measured time (filled by the reviewer)
├── REVIEW_FOCUS_v1.md      generated per-case reading aid; records no decision
├── SCENARIO_FAMILIES.md    pressure conditions and controls
├── SUBMISSION_REPORT.md    final write-up; verified metrics only, limitations first
├── TRAJECTORIES.md         seven real traces walked event by event
├── DEMO_SCRIPT.md          2:30 video script and recording rules
└── JUDGE_CHECKLIST.md      15-minute offline verification with expected outputs

scripts/
├── check_no_secrets.py     credential-shaped string scan (CI and pre-merge)
└── gen_review_focus.py     deterministic generator for docs/REVIEW_FOCUS_v1.md
```

## Remaining work from 85 to 95

1. Have a real person use the completed review workflow on all 40 cases. The
   tooling cannot perform that attestation.
2. Inspect the seven current `UNVERIFIABLE` labels, four persistent B1 F04
   failures and five repeat-unstable F06/F07 cases rather than bulk-approving.
3. Rerun `benchmark report` without `--allow-provisional`. It will reuse the
   committed 120 B1 outputs and switch only the truth source to accepted
   source-bound decisions.

Final submission media and any optional evidence viewer belong after the
verified benchmark, not before it.

## Closing branch: what exists before the review

`feat/final-submission` adds only documents, templates and a deterministic
generator; it changes no code path, no frozen data and no B1 artifact. The
review decisions themselves, the verified comparison, the measured review time
and the demo video are the remaining inputs for 95 and 100 and cannot be
produced by tooling.
