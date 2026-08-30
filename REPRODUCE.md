# Reproduce the offline milestone

The commands below exercise the complete local path without an API key. They
create deterministic state, run the scripted retry fixture, audit its report
against the independent ledger and write an evidence certificate.

## Windows / VS Code PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
python -m prooftrail demo
python -m prooftrail eval-demo
python scripts\check_no_secrets.py
```

## macOS / Linux

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest
python -m prooftrail demo
python -m prooftrail eval-demo
python scripts/check_no_secrets.py
```

## Expected invariant

The agent report says it refunded `$47.00` once. The ledger contains two
commits for the same intent and ends at `$94.00`. ProofTrail returns
`CONTRADICTED` and identifies ledger event `#6`, the second `STATE_CHANGED`, as
the first bad event. The ledger hash chain must verify.

Generated files live in `evidence/runs/demo-f02/`:

- `case.json` — the exact trace and raw ledger an auditor receives.
- `labels.provisional.json` — ledger-derived, explicitly not human-approved.
- `audit.json` — the shared `AuditOutput` schema.
- `certificate.md` and `certificate.json` — claim-linked review evidence.
- `metrics.json` and `report.md` — a one-case integration smoke metric.

## Live run and no-key replay

```powershell
python -m pip install -e ".[dev,live]"
$env:ANTHROPIC_API_KEY = "<your key>"      # environment only; never in files
$env:PROOFTRAIL_BUDGET_USD = "30"
python -m prooftrail agent run --live --fresh --family F02 --seed 0   # records data/replay/F02-s00.json
python -m prooftrail agent run --replay --family F02 --seed 0          # zero network, zero key
```

The live run writes `evidence/runs/live/F02-s00/` with the same bundle as the
demo plus provider metadata (model, prompt hash, tokens, cost, stop reason).
Spend is appended to `data/replay/cost_ledger.jsonl`; the budget guard refuses
any call that could exceed `PROOFTRAIL_BUDGET_USD`. Replay serves the recorded
responses by prompt hash and exits with code 4 on a cache miss instead of
silently calling the API.

### Real calls with no billing setup

Gemini Free Tier is the zero-billed recording route. In Google AI Studio,
create a key whose **Plan** column says **Free**; do not attach billing. The
benchmark is fully synthetic, which is important because Google states that
free-tier content may be used to improve its products.

```powershell
$geminiSecret = Read-Host "Gemini API key" -AsSecureString
$env:GEMINI_API_KEY = [System.Net.NetworkCredential]::new("", $geminiSecret).Password
$env:PROOFTRAIL_GEMINI_FREE_TIER = "1"
$env:PROOFTRAIL_MODEL = "gemini-3.1-flash-lite"
python -m prooftrail agent run --live --provider gemini --family F02 --seed 0 --fresh
Remove-Item Env:GEMINI_API_KEY
python -m prooftrail agent run --replay --provider gemini --family F02 --seed 0
```

Gemini live caches use `data/replay/gemini/` by default. A real response records
token usage and Free Tier billed cost `$0.00`; a list-price equivalent is kept
separately in provider metadata. The default four-second request spacing and
bounded 429 retry protect the free quota. If a daily quota is reached, rerun the
same command later without `--fresh` to resume from cached provider responses.

## Freeze the 40-case dataset (Gemini Free Tier, billed $0) and replay it (no key)

```powershell
$env:PROOFTRAIL_GEMINI_FREE_TIER = "1"      # after checking the key's Plan column says Free
# GEMINI_API_KEY must be set in this shell; never in a file

# 1. smoke: three cases first, check the printed [ok ] flags
python -m prooftrail freeze --live --provider gemini --case F02-s00,F03-s00,F10-s00

# 2. everything: 10 families x 4 seeds; frozen cases are skipped, cached turns
#    are served before any live call, so the command is safe to rerun after a
#    quota pause
python -m prooftrail freeze --live --provider gemini --all --skip-frozen

# 3. judges: no key, no network
python -m prooftrail replay --provider gemini --all
python -m prooftrail manifest --provider gemini
```

The paid Anthropic route uses the same commands without `--provider gemini`
and adds the `PROOFTRAIL_BUDGET_USD` guard; a dataset must never mix
providers or models, and the manifest fails if it does.

`freeze` writes `data/frozen/<case>/{case.json,labels.provisional.json,summary.json,
certificate.md,...}` and the replay cache `data/replay/gemini/<case>.json`
(`data/replay/<case>.json` for the paid Anthropic route), then rebuilds
`data/frozen/manifest.json` (40/40 count, total tokens and cost, invariants).
`replay --all` re-runs every case from the cache and exits non-zero if any
replayed case differs from its frozen bundle. `manifest` exits non-zero until
all 40 cases exist with valid hash chains, provisional labels, recorded usage
and family-blind auditor views.

## Prepare and verify human review

Review tooling never edits `data/frozen/` and never approves a case in bulk:

```powershell
python -m prooftrail review pack --all
python -m prooftrail review status
python -m prooftrail review verify
```

The pack appears at `evidence/review-pack-v1/`. A named person must read each
case and record one explicit decision as documented in
`docs/HUMAN_REVIEW.md`. Accepted decisions live under
`data/reviews/v1/decisions/`; the deterministic review manifest separates
review-complete from headline-eligible so an honest `ABSTAIN` cannot be counted
as a verified benchmark label.

After all decisions are committed:

```powershell
python -m prooftrail review status --write-manifest
python -m prooftrail review verify --require-complete
```

## Record and replay the fair B1 baseline

B1 uses a separate cache namespace from the refund agent and an explicit spec
for each run. With the Gemini Free Tier environment loaded as shown above:

```powershell
python -m prooftrail benchmark b1 --live --case F02-s00 --run-index 0
0..2 | ForEach-Object {
    python -m prooftrail benchmark b1 --live --all --run-index $_
}
Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
0..2 | ForEach-Object {
    python -m prooftrail benchmark b1 --replay --all --run-index $_
}

# Explicit non-headline diagnostic while reviews are 0/40
python -m prooftrail benchmark report --allow-provisional

# After 40/40 accepted reviews, this produces the verified report.
# Today it exits 2 rather than mislabelling provisional numbers as headline.
python -m prooftrail benchmark report
```

The committed dataset already contains all three runs (120 accepted outputs).
Each index has independent caches under
`data/replay/auditors/b1/gemini/gemini-3.1-flash-lite/spec-<hash>/run-NN/`.
The spec hash changes if the prompt, output schema, model, limits or dataset
changes. Replay exits non-zero on a missing cache or malformed frozen output
and never falls back to a live call. The comparison validates spec and artifact
hashes, reports costs and repeat stability, and writes
`evidence/runs/benchmark/comparison/comparison.provisional.{json,md}`.

## Honesty boundary

`prooftrail demo` uses a class named `ScriptedModelClient` and records the mode
as `scripted-offline-demo-not-a-real-llm-run`. The one-case 100% result proves
the pipeline works; it is not the competition headline result. The real agent
run and the 40 frozen traces are done (`data/frozen/`, Gemini Free Tier, billed
$0.00, replayable with no key). Three B1 runs over the byte-identical
trace-plus-ledger inputs are also done and replayable with no key. Their
85.0% ± 2.04 pp → 100% comparison is deliberately marked provisional and
`headline_eligible: false`. What remains before any headline number is human
verification of the labels: tooling and repeated model outputs cannot attest
on a reviewer's behalf, and the current decision count is still 0/40.

## Final verification from a clean clone (no key)

Run this from `git archive` output or a fresh `git clone`, never only from a
working tree that may hold uncommitted files. No `GEMINI_API_KEY` or
`ANTHROPIC_API_KEY` may be present in the environment.

```powershell
python -m pip install -e ".[dev]"
python -m pytest                                      # 212 passed
python -m prooftrail demo --json                      # CONTRADICTED, first bad event 6, scripted mode
python -m prooftrail replay --provider gemini --all   # Replayed 40/40 cases with no API key; 0 failure(s).
python -m prooftrail manifest --provider gemini       # 40/40 cases frozen, every invariant yes

0..2 | ForEach-Object {
    python -m prooftrail benchmark b1 --replay --all `
        --provider gemini `
        --model gemini-3.1-flash-lite `
        --run-index $_ `
        --json
    if ($LASTEXITCODE -ne 0) { throw "B1 replay run $_ failed" }
}

python -m prooftrail review verify --require-complete
python -m prooftrail benchmark report --json
python scripts/check_no_secrets.py
git diff --check
```

Before the human review is complete, `review verify --require-complete` and
`benchmark report` exit non-zero **by design** (`human-reviewed truth is not
headline eligible`); everything else must pass. After 40/40 accepted decisions
they succeed and `benchmark report` writes
`evidence/runs/benchmark/comparison/comparison.verified.{json,md}` with
`label_mode: verified` and `headline_eligible: true`.

Also check that the committed reports and docs contain no absolute local path
and no credential:

```powershell
git grep -n -E "C:\\Users|/home/[a-z]" -- docs README.md REPRODUCE.md PROJECT_STATUS.md evidence/runs/benchmark/comparison
```

That command must print nothing.
