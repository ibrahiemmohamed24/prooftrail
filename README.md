# ProofTrail

**Evidence-linked auditing of what an AI agent *says* it did versus what the ledger *proves* it did.**

> Status: offline milestone plus a live provider (≈55% of the submission plan; the 40 frozen
> cases complete the 55 → 75 step). The $47 → $94 path runs end to end: stateful tools, trace
> recording, ledger reconciliation, first-bad-event detection, certificates, fair-baseline
> contract, metrics and CLI. A real Anthropic adapter with a budget guard, prompt hashing and a
> no-key replay cache is in place. **139 tests pass (94% coverage), none of them touch the network.**
> The frozen 40-case benchmark, human label verification and final competition assets are still
> pending. See [PROJECT_STATUS.md](PROJECT_STATUS.md) for the stable scoring model and handoff target.

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
evidence of real-model behaviour. Live LLM traces are generated with the
command below and frozen once, after which judges replay them with no key.

---

## Live run — one real-model case, then replay it for free

```powershell
python -m pip install -e ".[dev,live]"     # adds the anthropic SDK
$env:ANTHROPIC_API_KEY = "<your key>"      # never committed; read from the environment only
$env:PROOFTRAIL_BUDGET_USD = "30"          # hard spend ceiling across ALL live runs

python -m prooftrail agent run --live --fresh --family F02 --seed 0   # record a NEW trace
python -m prooftrail agent run --replay --family F02 --seed 0          # no key, no network
```

`--fresh` discards `data/replay/F02-s00.json` before recording. Without it a live
run first serves every prompt it already has in that cache and only calls the API
for prompts it has not seen — useful to resume an interrupted recording cheaply,
but it means the result is a continuation of the earlier trace, not a fresh
sample of model behaviour. A cache recorded with a different model is refused
before any request is sent.

What a live run records, per assistant turn, inside `evidence/runs/live/<case>/case.json`:

| Field | Where |
|---|---|
| model name | `trace.model`, `messages[].provider.model` |
| prompt hash (sha256 of model + transcript + tools + caps) | `messages[].provider.prompt_sha256` |
| input / output / cache tokens and USD cost | `messages[].provider.usage`, summed in `trace.usage` |
| stop reason (`tool_use`, `end_turn`, `max_tokens`, `refusal`) | `messages[].provider.stop_reason` |
| provider tool-call ids and verbatim content blocks (thinking included) | `messages[].tool_calls[].provider_call_id`, `messages[].provider_content` |

Freezing the dataset uses the same machinery for all 40 cases:

```powershell
python -m prooftrail freeze --live --case F02-s00,F03-s00,F10-s00   # smoke first
python -m prooftrail freeze --live --all --skip-frozen              # then everything
python -m prooftrail replay --all                                   # judges: no key
python -m prooftrail manifest                                       # 40/40 + invariants
```

Guard rails: the `BudgetGuard` refuses any call whose worst-case cost would push
the cumulative spend in `data/replay/cost_ledger.jsonl` past `PROOFTRAIL_BUDGET_USD`
(worst case = every UTF-8 byte of the request counted as an input token, the full
output cap, and every retry attempt billed; models without a configured price are refused);
transient network / 429 / 5xx failures are retried at most three times, and a retry
only re-sends the model request — tool actions are never re-executed. Every live
response is written to `data/replay/<case>.json` keyed by prompt hash, so `--replay`
reproduces the identical trace with zero API calls and fails loudly on any divergence.

### Zero-billed real calls with Gemini Free Tier

The competition does not require a paid provider. ProofTrail can record the same
real tool-using agent loop with Google's documented Gemini Free Tier. Gemini
3.7 Flash supports function calling; Egypt is an available region. The free
tier bills input and output tokens at USD 0, subject to the active project's
rate limits. Free-tier content may be used by Google to improve its products,
so this path is restricted to ProofTrail's synthetic benchmark data.

Create a key in [Google AI Studio](https://aistudio.google.com/apikey) and check
that its **Plan** column says **Free**. Do not enable billing and do not paste the
key into this repository or a chat. In PowerShell:

```powershell
$geminiSecret = Read-Host "Gemini API key" -AsSecureString
$env:GEMINI_API_KEY = [System.Net.NetworkCredential]::new("", $geminiSecret).Password
$env:PROOFTRAIL_GEMINI_FREE_TIER = "1"
$env:PROOFTRAIL_MODEL = "gemini-3.1-flash-lite"

python -m prooftrail agent run --live --provider gemini --family F02 --seed 0 --fresh
Remove-Item Env:GEMINI_API_KEY
python -m prooftrail agent run --replay --provider gemini --family F02 --seed 0
```

The REST adapter has no third-party dependency. It records model version,
prompt hash, provider function-call IDs, token usage, stop reason and Gemini 3
thought signatures. `cost_usd` is the billed Free Tier amount (`0.0`); provider
metadata also records a paid-tier list-price equivalent so the report does not
hide the economic value of the calls. Requests are paced and replay caches make
a quota-interrupted 40-case recording resumable. See Google's official
[pricing](https://ai.google.dev/gemini-api/docs/pricing),
[function-calling guide](https://ai.google.dev/gemini-api/docs/function-calling),
and [available regions](https://ai.google.dev/gemini-api/docs/available-regions).

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
| Live providers | Anthropic paid adapter or Gemini Free Tier REST adapter + prompt-hash replay | ✅ offline provider tests; real traces pending |
| Live benchmark | 40 frozen traces, human-approved labels, repeats | ⏳ |

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
