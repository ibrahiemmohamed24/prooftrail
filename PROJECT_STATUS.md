# ProofTrail Project Status

> Update this file in every pull request that changes milestone completion.

## Snapshot

- **Overall completion:** 55 / 100
- **Last verified:** 2026-08-29
- **Default branch:** `main`
- **Offline tests:** 129 passed (no test uses the network or an API key; the SDK is exercised over an in-process mock transport)
- **Real spend to date:** $0.00 — live runs are deferred under the free plan until explicitly funded
- **Statement coverage:** 94%
- **Working demo:** F02 claims one $47 refund; the ledger proves two commits and $94; ProofTrail returns `CONTRADICTED` with first bad event `#6`.
- **Live provider:** `AnthropicModelClient` behind `ModelClient`, budget guard over `data/replay/cost_ledger.jsonl`, prompt-hash replay cache, `python -m prooftrail agent run --live|--replay --family F02 --seed 0`.
- **Honesty boundary:** the demo still uses `ScriptedModelClient`; no real-model trace has been frozen yet, so no benchmark number exists.

## Scoring model

The weights below are stable. Change earned points only when the stated
definition of done is satisfied and linked evidence exists in the PR.

| Area | Weight | Earned | Definition of done |
|---|---:|---:|---|
| Foundation | 10 | 10 | Schemas, deterministic IDs, packaging and core tests work |
| Stateful environment | 20 | 20 | SQLite state, atomic ledger, faults and 10 scenario families work |
| Offline agent + ProofTrail | 20 | 20 | Tool loop, replay fixture, reconciliation, temporal checks and certificates work end to end |
| Fair baseline + evaluation | 15 | 5 | B1 contract and metrics exist; full points require repeated B1/PT comparison, costs and ablations |
| Live agent + frozen dataset | 20 | 0 | Real provider adapter plus 40 frozen, replayable traces with recorded usage |
| Verified benchmark | 10 | 0 | Human-approved labels, family-balanced results and failure analysis |
| Submission experience | 5 | 0 | Final README/report, short demo video and optional evidence viewer |
| **Total** | **100** | **55** | |

## Current milestone: 55 → 75

Owner(s) should complete both items on feature branches:

1. Real LLM provider adapter behind the existing `ModelClient` protocol. **Done**
   (`feat/live-llm-provider`): adapter, budget guard, bounded retry that never
   re-runs a tool, prompt hash + usage + cost + stop reason recorded per turn,
   replay cache, CLI, fake-provider tests. Points for the "Live agent + frozen
   dataset" row stay at 0 until item 2 lands, because its definition of done
   covers both.
2. Forty frozen traces: 10 families × 4 fixed seeds, replayable without an API key. **Pending**
   (needs `ANTHROPIC_API_KEY` in the environment and a 2–3 case smoke run first).

The milestone is complete only when:

- Live calls record model, prompt hash, tool calls, token usage and cost.
- A budget guard prevents unexpected spend.
- `data/frozen/<case>/case.json` exists for all 40 cases.
- Cached/replay mode reproduces the same trace inputs with no network.
- No API key or personal data is committed.
- `python -m pytest`, `python -m prooftrail demo`, and the secret scan pass.

Human verification and headline benchmark numbers belong to the following
milestone; generated labels must remain explicitly provisional until reviewed.

## Required verification before every merge

```powershell
python -m pytest
python -m prooftrail demo --json
python scripts\check_no_secrets.py
git diff --check
```

## Handoff update rule

Every completed PR must:

1. Update the snapshot and earned points only if a definition of done changed.
2. Add one evidence-backed row to `CHANGELOG.md`.
3. State exact tests and commands run in the PR description.
4. List remaining risks or incomplete work without hiding them.

With this file current, a new contributor—or a new Codex session—can inspect
the repository and recalculate progress without relying on chat history.
