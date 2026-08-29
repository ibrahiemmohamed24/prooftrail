# ProofTrail — Architecture & File Map

> Three words: **same evidence, independent truth, frozen traces.**

## Pipeline

```
Real LLM Refund Agent            (runs ONCE, at data-creation time, --live)
        │
        ▼
Mock Tools ──► SQLite State + Append-only Event Ledger (hash-chained)
        │
        ▼
Frozen Trace + Same Raw Ledger   (data/frozen/<case>/case.json — committed)
        ├── B0: one-shot LLM, sees TRACE ONLY            (operational reference)
        ├── B1: one-shot LLM, sees TRACE + LEDGER        (the official fair baseline)
        └── ProofTrail:
              LLM Claim Extractor          (1 call — same model, same caps as B1)
                      ▼
              Deterministic Reconciler     (0 tokens)
              + Temporal / Intent Verifier (0 tokens)
                      ▼
              Evidence Certificate         (template, not a second LLM)
        │
        ▼
Evaluator: Macro-F1 over instances, accuracy per family,
           unweighted mean over families, first-bad-event hit rate,
           evidence coverage, cost & tokens per case.
```

## Fairness rules (enforced in code, see `prooftrail/config.py`)

| Rule | Where enforced |
|---|---|
| One model for every role | `config.MODEL` — only a *global* override exists |
| Same max output tokens / effort / max LLM calls for B0, B1, ProofTrail | `config.AUDITOR_LIMITS` (one frozen dataclass) |
| Same raw evidence | `schemas.trace.FrozenCase` is the *only* input type an auditor accepts |
| Same output schema | `schemas.verdict.AuditOutput` + `validate_audit_output()` on raw LLM JSON |
| Hidden labels | `labels.json` lives next to `case.json`; loaders in `auditor/` and `baselines/` never open it |
| Frozen traces | agent runs only under `--live`; default is `--replay` from `data/frozen/` + `data/replay/` |

## Ground truth is independent of any model

1. **Ledger facts** (deterministic): refund count per intent, committed cents per order,
   entity of each `STATE_CHANGED`, presence of `IDEMPOTENT_REPLAY`, fired faults.
2. **Claim labels** (human-verified): `ground_truth.py` proposes per-claim statuses from
   the ledger facts; each case gets `verified_by_human: true` only after manual review.
   Unverified cases are reported separately and never enter the headline number.

## Repository map — status of every file

Legend: ✅ written · ◐ working subset · ⏳ planned · 🔒 generated data

```
prooftrail/
├── README.md                          ✅ user / bottleneck / value / changelog skeleton
├── pyproject.toml                     ✅ stdlib-only core; anthropic only in [live]
├── requirements.txt                   ✅ pinned
├── requirements-dev.txt               ✅ pinned
├── .gitignore  .gitattributes         ✅ LF everywhere; frozen data is committed
├── .env.example                       ✅ API key + budget ceiling
├── REPRODUCE.md                       ✅ zero-key demo/test/eval commands + honesty boundary
├── PROVENANCE.md                      ✅ inspected starting state and milestone additions
├── CHANGELOG.md                       ✅ Improvement Changelog through offline milestone
├── .github/workflows/eval.yml         ✅ pytest + zero-key demo/eval + secret scan
│
├── prooftrail/
│   ├── __init__.py                    ✅
│   ├── config.py                      ✅ model, pricing, budget, fairness caps, paths, seeds
│   ├── ids.py                         ✅ intent_id / tool_call_id / transaction_id / idempotency_key
│   ├── cli.py  __main__.py            ◐ `{cases,demo,eval-demo}` work; live/frozen commands pending
│   ├── demo.py                        ✅ F02 zero-network end-to-end orchestration + artifacts
│   │
│   ├── schemas/                       — the contracts everything else obeys
│   │   ├── __init__.py                ✅
│   │   ├── events.py                  ✅ LedgerEvent (hash-chained) + verify_chain()
│   │   ├── trace.py                   ✅ AgentTrace, ToolCallRecord, FrozenCase, Usage
│   │   └── verdict.py                 ✅ Status, ClaimType, AuditOutput, GroundTruth, validator
│   │
│   ├── env/                           — the mock world the agent acts on
│   │   ├── __init__.py                ✅
│   │   ├── clock.py                   ✅ deterministic simulated time
│   │   ├── database.py                ✅ SQLite: customers/orders/refunds + append-only ledger table
│   │   ├── ledger.py                  ✅ Ledger.append / events / verify_chain / to_json
│   │   ├── faults.py                  ✅ FaultKind, FaultSpec, FaultInjector, ToolTimeout
│   │   ├── tools.py                   ✅ lookup_customer / lookup_order / list_refunds / issue_refund / send_email
│   │   └── seed_data.py               ✅ (family, seed) → customers & orders, deterministic
│   │
│   ├── agent/                         — the REAL refund agent we audit (live only)
│   │   ├── __init__.py                ✅
│   │   ├── interfaces.py adapters.py  ✅ provider-neutral model/tool boundary
│   │   ├── prompts.py tool_defs.py    ✅ system prompt + JSON tool schemas
│   │   ├── refund_agent.py            ✅ manual tool-use loop, max_turns, records everything
│   │   ├── recorder.py                ✅ builds AgentTrace incl. usage/cost
│   │   ├── scripted.py replay.py      ✅ explicit offline fixture + stable JSON replay
│   │   └── live_provider.py           ⏳ real model SDK adapter
│   │
│   ├── scenarios/                     — families, instances, hidden labels, freezing
│   │   ├── __init__.py                ✅
│   │   ├── families.py                ✅ the 10 families (pressure conditions, not labels)
│   │   ├── generator.py               ✅ family × seed → env + user requests
│   │   ├── ground_truth.py            ✅ ledger → provisional GroundTruth (never self-approves)
│   │   └── freeze.py                  ⏳ run agent once, write data/frozen/<case>/{case,labels}.json
│   │
│   ├── llm/                           — the only place that talks to the API
│   │   ├── __init__.py                ⏳
│   │   ├── client.py                  ⏳ Anthropic SDK wrapper: budget guard, usage, retries
│   │   ├── cache.py                   ⏳ replay cache: sha256(request) → response (data/replay/)
│   │   └── pricing.py                 ⏳ thin wrapper over config.cost_usd
│   │
│   ├── baselines/                     — fair comparators (same model, caps, evidence, schema)
│   │   ├── __init__.py                ✅
│   │   ├── prompts.py                 ✅ B1 trace+ledger prompt and exact evidence payload
│   │   ├── b0_trace_only.py           ⏳
│   │   └── b1_trace_plus_ledger.py    ✅ one-call protocol, shared caps/schema, fail-closed output
│   │
│   ├── auditor/                       — ProofTrail itself
│   │   ├── __init__.py                ✅
│   │   ├── claim_extractor.py         ◐ typed contract + offline fallback; LLM implementation pending
│   │   ├── evidence_linker.py         ✅ claims ↔ candidate ledger events (deterministic)
│   │   ├── reconciler.py              ✅ amounts / entities / counts vs STATE_CHANGED
│   │   ├── temporal_verifier.py       ✅ retry/intent/idempotency + first bad event
│   │   ├── certificate.py             ✅ template-rendered JSON + Markdown certificate
│   │   └── pipeline.py                ✅ FrozenCase → AuditOutput
│   │
│   └── eval/
│       ├── __init__.py                ✅
│       ├── metrics.py                 ✅ macro-F1, family-mean, first-bad hit, coverage
│       ├── runner.py                  ◐ generic offline runner; repeated live runs pending
│       ├── cost.py                    ⏳ tokens/cost/human-time rows
│       └── report.py                  ✅ Markdown + JSON metrics reports
│
├── tests/
│   ├── conftest.py                    ✅ in-memory env fixtures
│   ├── test_ids.py                    ✅
│   ├── test_ledger.py                 ✅ chain, tamper detection, append-only triggers
│   ├── test_database.py               ✅ refund semantics incl. representable double refund
│   ├── test_faults.py                 ✅
│   ├── test_families.py               ✅ 10 families, balance, killer + controls
│   ├── test_schemas.py                ✅ validator, round-trips, verdict aggregation
│   ├── test_tools.py                  ✅ every FaultKind produces the intended ledger shape
│   ├── test_generator.py              ✅ stable 40-instance generation
│   ├── test_ground_truth.py           ✅ independent provisional facts/labels
│   ├── test_auditor.py                ✅ extraction/reconciliation/temporal/certificate
│   ├── test_agent*.py                 ✅ loop, integration and replay round-trips
│   ├── test_demo.py test_cli.py       ✅ full F02 + command/artifact contract
│   ├── test_metrics.py                ✅
│   └── test_replay_cache.py           ⏳
│
├── scripts/
│   ├── go_no_go.py                    ⏳ the 6-hour gate: 5 families × 2 seeds, B1 vs ProofTrail
│   ├── check_no_secrets.py            ✅ credential-shaped string scan
│   └── run_eval.ps1 / run_eval.sh     ⏳ wrappers for judges
│
├── data/
│   ├── frozen/<case>/case.json        🔒 trace + ledger (auditor input)
│   ├── frozen/<case>/labels.json      🔒 hidden ground truth
│   ├── replay/*.json                  🔒 cached LLM responses
│   └── replay/cost_ledger.jsonl       🔒 every live call, cost, model
│
├── evidence/runs/<date_iter>/         🔒 command.txt env.txt output.log metrics.json (append-only)
├── trajectories/INDEX.md              ⏳ Claude Code sessions used to build this
└── docs/
    ├── ARCHITECTURE.md                ✅ this file
    ├── SCENARIO_FAMILIES.md           ✅
    ├── METRICS.md                     ⏳ exact definitions + why family-mean
    ├── GO_NO_GO.md                    ⏳ decision record after the 6-hour gate
    └── DECISIONS.md                   ⏳ ADRs (why no confidence score, why no 2nd LLM, ...)
```

Current state: a working offline milestone at roughly **55% of the submission
plan**, with **98 passing tests** and 93% measured statement coverage. The core
F02 path is complete; the percentage remains deliberately conservative because
the real-model adapter, frozen 40-case data, human verification, repeated B1
comparison and final submission media do not exist yet.

## Data flow at the type level

```
ScenarioFamily ──generator──► (StateDB, [UserRequest], FaultInjector)
                                     │  refund_agent (live) / replay
                                     ▼
                              AgentTrace + [LedgerEvent]  ──freeze──► FrozenCase (case.json)
                                     │                                GroundTruth (labels.json)
                                     ▼
                     B0 / B1 / auditor.pipeline  ──► AuditOutput
                                     │
                                     ▼
                     eval.metrics(AuditOutput, GroundTruth) ──► metrics.json + report.md
```
