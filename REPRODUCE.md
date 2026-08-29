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

## Honesty boundary

`prooftrail demo` uses a class named `ScriptedModelClient` and records the mode
as `scripted-offline-demo-not-a-real-llm-run`. The one-case 100% result proves
the pipeline works; it is not the competition headline result. The real agent
run and the 40 frozen traces are done (`data/frozen/`, Gemini Free Tier, billed
$0.00, replayable with no key). What remains before any headline number is
human verification of the provisional labels and the B1 run over the
byte-identical trace-plus-ledger inputs.
