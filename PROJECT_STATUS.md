# ProofTrail Project Status

> Update this file in every pull request that changes milestone completion.

## Snapshot

- **Overall completion:** 75 / 100
- **Last verified:** 2026-08-29
- **Default branch:** `main`
- **Offline tests:** 194 passed, 0 skipped (no test uses the network or an API key; the Anthropic SDK is exercised over an in-process mock transport, Gemini over a fake transport; the 40 committed frozen cases are loaded, chain-verified and checked for family-blindness by the dataset tests)
- **Real spend to date:** $0.00 — all 175 recorded LLM calls went through the Gemini Free Tier (`gemini-3.1-flash-lite`), billed at $0; list-price equivalent $0.061
- **Statement coverage:** 94%
- **Working demo:** F02 claims one $47 refund; the ledger proves two commits and $94; ProofTrail returns `CONTRADICTED` with first bad event `#6`.
- **Live providers:** paid `AnthropicModelClient` plus a tested zero-billed `GeminiModelClient` Free Tier route behind the same `ModelClient`; both use the prompt-hash replay cache. The validated Gemini default is `gemini-3.1-flash-lite`.
- **Frozen dataset:** `data/frozen/` holds 40/40 real-model traces (10 families × 4 seeds), replayable with `python -m prooftrail replay --provider gemini --all` and no key; `manifest.json` reports every invariant `yes`. ProofTrail verdicts: 17 `SUPPORTED`, 16 `CONTRADICTED`, 7 `UNVERIFIABLE`.
- **Honesty boundary:** the demo still uses `ScriptedModelClient`. Every frozen label is ledger-derived and `verified_by_human: false`; no human has reviewed a single case, no B1-vs-ProofTrail number exists, and the 40/40 agreement between ProofTrail verdicts and provisional labels is a consistency check against the same ledger, not a benchmark result.

## Scoring model

The weights below are stable. Change earned points only when the stated
definition of done is satisfied and linked evidence exists in the PR.

| Area | Weight | Earned | Definition of done |
|---|---:|---:|---|
| Foundation | 10 | 10 | Schemas, deterministic IDs, packaging and core tests work |
| Stateful environment | 20 | 20 | SQLite state, atomic ledger, faults and 10 scenario families work |
| Offline agent + ProofTrail | 20 | 20 | Tool loop, replay fixture, reconciliation, temporal checks and certificates work end to end |
| Fair baseline + evaluation | 15 | 5 | B1 contract and metrics exist; full points require repeated B1/PT comparison, costs and ablations |
| Live agent + frozen dataset | 20 | 20 | Real provider adapter plus 40 frozen, replayable traces with recorded usage |
| Verified benchmark | 10 | 0 | Human-approved labels, family-balanced results and failure analysis |
| Submission experience | 5 | 0 | Final README/report, short demo video and optional evidence viewer |
| **Total** | **100** | **75** | |

## Completed milestone: 55 → 75

1. Real LLM provider adapter behind the existing `ModelClient` protocol. **Done**
   (`feat/live-llm-provider`, merged into this branch): adapter, budget guard,
   bounded retry that never re-runs a tool, prompt hash + usage + cost + stop
   reason recorded per turn, replay cache, CLI, fake-provider tests.
2. Forty frozen traces: 10 families × 4 fixed seeds, replayable without an API key. **Done: 40/40**
   (`feat/free-gemini-provider`): recorded with `python -m prooftrail freeze --live
   --provider gemini --all --skip-frozen` on the Gemini Free Tier
   (`gemini-3.1-flash-lite`), resumed across several quota/network pauses with no
   case re-recorded. Evidence in this repository:
   - `data/frozen/<case>/{case.json,labels.provisional.json,summary.json,certificate.md,...}` for all 40 cases;
   - `data/replay/gemini/<case>.json` prompt-hash caches for all 40 cases;
   - `data/frozen/manifest.json`: `40/40 cases frozen`, 175 LLM calls, 142,227 input /
     16,950 output tokens, 133 tool calls, 330 ledger events, `cost_usd: 0.0`,
     `list_price_equivalent_usd: 0.060977`, `models: ["gemini-3.1-flash-lite"]`,
     `providers: ["google-gemini"]`, all seven invariants `true`, `problems: []`;
   - `python -m prooftrail replay --provider gemini --all` with no key in the
     environment: `Replayed 40/40 cases with no API key; 0 failure(s).`
   - manifest hashes are line-ending independent (`sha256_file` normalises CRLF to LF),
     so the same checks pass from a `git archive`/Linux clone, not only a Windows working tree.

Definition-of-done checklist:

- Live calls record model, prompt hash, tool calls, token usage and cost. **Yes** (every assistant turn carries `provider.prompt_sha256` and `provider.usage.cost_usd`; asserted per case by `tests/test_freeze.py`).
- A budget guard prevents unexpected spend. **Yes for the paid route** (`BudgetGuard` on Anthropic). The Gemini Free Tier route has no billing to guard; it rejects `--budget-usd` (exit 7) so nobody can mistake it for a funded run, and the manifest asserts `cost_usd == 0.0`.
- `data/frozen/<case>/case.json` exists for all 40 cases. **Yes.**
- Cached/replay mode reproduces the same trace inputs with no network. **Yes** (`replay --all` exits non-zero on any byte divergence from the frozen bundle; 0 failures).
- No API key or personal data is committed. **Yes** (`scripts/check_no_secrets.py` passed; the dataset is fully synthetic).
- `python -m pytest`, `python -m prooftrail demo`, and the secret scan pass. **Yes** (194 passed; demo unchanged: `CONTRADICTED`, event `#6`).

Known limits of this dataset (stated, not hidden):

- One provider and one model only (`gemini-3.1-flash-lite`); the manifest fails on any mix. A paid-model dataset would be a separate `data/frozen/` snapshot.
- Free Tier content may be used by Google to improve its products; the benchmark contains no real people or data, which is why the route was acceptable.
- `F07`, `F09` and `F10` produced `UNVERIFIABLE` outcomes on some seeds; these are recorded as-is and must be examined in the failure analysis of the next milestone, not re-rolled.

## Next milestone: 75 → 90

- **Verified benchmark (10):** human review of the 40 provisional labels, family-balanced results, failure analysis of the 7 `UNVERIFIABLE` cases.
- **Fair baseline + evaluation (remaining 10):** repeated B1 vs ProofTrail comparison over the byte-identical frozen inputs, cost table, ablations.

Human verification and headline benchmark numbers belong to that milestone;
generated labels must remain explicitly provisional until reviewed.

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
