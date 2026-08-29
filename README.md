# ProofTrail

**Evidence-linked auditing of what an AI agent *says* it did versus what the ledger *proves* it did.**

> Status: working offline milestone (≈55% of the submission plan). The $47 → $94 path now runs
> end to end: stateful tools, trace recording, ledger reconciliation, first-bad-event detection,
> certificates, fair-baseline contract, metrics and CLI. **98 tests pass.** The real-LLM adapter,
> frozen 40-case benchmark, human label verification and final competition assets are still pending.
> See [PROJECT_STATUS.md](PROJECT_STATUS.md) for the stable scoring model and current handoff target.

---

## Who this is for, and what hurts

**Intended user:** the engineer or support lead who owns a tool-using agent that performs
irreversible actions (refunds, cancellations, account changes) and who today reads agent
transcripts by hand to answer one question: *"did it actually do what it claims?"*

**Bottleneck:** an agent's final message is written by the same model that may have been
lied to by a flaky tool, timed out mid-commit, or retried blindly. Reading the transcript
tells you what the agent *believed*. Only the system of record tells you what *happened*.
Today reconciling the two is a manual, per-case job — and the worst cases (double refund
after a post-commit timeout) look completely normal in the transcript.

**Value:** a verdict per report (`SUPPORTED` / `CONTRADICTED` / `UNVERIFIABLE`) with every
claim linked to the ledger events that support or contradict it, plus the **first event where
things went wrong** — so the human reviews one event instead of one transcript.

---

## The idea in one diagram

```
Real LLM Refund Agent ──► Mock Tools ──► SQLite State + Append-only Ledger
                                                   │
                    Frozen Trace + Same Raw Ledger ◄┘
                    ├── B1  (fair baseline): one-shot LLM sees trace + ledger
                    └── ProofTrail: LLM claim extraction → deterministic reconciliation
                                    + temporal/intent verification → evidence certificate
```

Three rules that make the comparison worth anything:

1. **Same evidence** — B1 and ProofTrail get byte-identical input (same model, same caps, same schema).
2. **Independent truth** — labels come from the ledger, never from any model's opinion.
3. **Frozen traces** — the agent runs once; every evaluation replays. Judges need no API key.

---

## Quickstart — zero API calls

PowerShell / VS Code terminal:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest

# See all 10 scenario families
python -m prooftrail cases

# Run the killer case and write a review certificate
python -m prooftrail demo

# Score the provisional demo and write metrics/report files
python -m prooftrail eval-demo
```

The main artifact is written to:

```text
evidence/runs/demo-f02/certificate.md
```

Expected terminal result:

```text
Agent claimed : I refunded $47.00 for order ord_82efdfe20a.
Ledger proved : 2 commits, $94.00 refunded
Verdict       : CONTRADICTED
First bad     : ledger event #6
Hash chain    : valid
```

This command deliberately uses `ScriptedModelClient`, a deterministic offline
fixture. It proves the integration and replay path; it is **not** reported as
evidence of real-model behaviour. Live LLM traces will be generated and frozen
once in the next milestone, after which judges will replay them with no key.

---

## What exists right now

| Area | Files | Tested |
|---|---|---|
| Contracts | `schemas/{events,trace,verdict}.py` | ✅ |
| Identity model | `ids.py` — intent / tool_call / transaction / idempotency | ✅ |
| Environment | Stateful refund tools + six fault modes + atomic state/ledger commit | ✅ |
| Scenarios | 10 families, deterministic seed data, generator, provisional ground truth | ✅ |
| Agent | Provider-neutral tool loop, trace recorder and explicit offline replay client | ✅ |
| ProofTrail | Claims → evidence → reconciliation → temporal verifier → certificate | ✅ |
| Fair baseline | B1 one-call contract sees the same trace + ledger and fails closed | ✅ contract; data pending |
| Evaluation | Family weighting, Macro-F1, first-bad hit rate, coverage, reports | ✅ |
| Reproduction | CLI demo + JSON/Markdown evidence + secret scan | ✅ offline milestone |
| Live benchmark | Real model adapter, 40 frozen traces, human-approved labels, repeats | ⏳ |

Run `pytest` from this folder.

---

## Evaluation design (what the tables will contain)

* **Primary metric:** verdict accuracy, averaged *per family* then across families (unweighted),
  so no family can dominate. Macro-F1 over all instances reported alongside.
* **Secondary:** first-bad-event hit rate, evidence coverage (claims with ≥1 cited event).
* **Required rows:** primary outcome · human time per task · cost per task — for B0, B1, ProofTrail.
* **Cases:** 10 families × 4 seeds = 40 instances, all with human-verified labels.
* **Repeats:** every LLM-dependent number is mean ± spread over 3 runs.

See [docs/SCENARIO_FAMILIES.md](docs/SCENARIO_FAMILIES.md).

---

## Improvement Changelog

_Entries are appended after every eval iteration. None yet — the harness comes before the solution._

| # | Date | Change | Family-mean acc. (B1 → PT) | Notes |
|---|---|---|---|---|
| 0 | 2026-08-28 | Foundation: schemas, SQLite state, hash-chained ledger, families | — | No end-to-end path |
| 1 | 2026-08-28 | Atomic tools + agent replay + hybrid auditor + certificate + CLI | Pending real B1 run | F02 demo detects event #6; provisional only |

---

## Main observed failure mode & hot take

In the offline integration run, the timeout is **not** the bad event. The first
refund had already committed, so the first harmful action is the second
`STATE_CHANGED` under the same intent at event #6. Treating every timeout retry
as wrong would also misclassify F03; treating every repeated call as wrong would
misclassify F10's idempotent replay.

The provisional hot take is that an LLM does not need to perform arithmetic or
state reconciliation. Its useful role is extracting claims from free text;
deterministic code should compare amounts, entities, intents and event order.
The actual B1-versus-ProofTrail result remains deliberately blank until both run
on the same frozen real-model traces.
