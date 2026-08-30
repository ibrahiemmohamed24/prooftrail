# Judge checklist — verify ProofTrail in 15 minutes, no API key

Everything below runs offline from a fresh clone. Nothing needs a provider key,
a network connection or a paid account. Expected outputs are quoted from the
committed artifacts; any mismatch is a finding, not a tolerance.

## 0. Fresh clone

```powershell
git clone https://github.com/ibrahiemmohamed24/prooftrail.git
cd prooftrail
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

(macOS/Linux: `python3 -m venv .venv && . .venv/bin/activate`.)

## 1. Tests — no network, no key

```powershell
python -m pytest
```

- [ ] Ends with `212 passed` (0 skipped). No test touches the network; the
      Anthropic SDK is exercised over an in-process mock transport and Gemini
      over a fake transport.

## 2. Killer demo (scripted fixture — clearly labelled as such)

```powershell
python -m prooftrail demo
```

- [ ] `Agent claimed : I refunded $47.00 for order ord_82efdfe20a.`
- [ ] `Ledger proved : 2 commits, $94.00 refunded`
- [ ] `Verdict       : CONTRADICTED`, `First bad     : ledger event #6`, `Hash chain    : valid`
- [ ] The `Mode` line says it is a scripted offline fixture, not a real LLM run.
- [ ] `evidence/runs/demo-f02/certificate.md` links each claim to ledger events.

## 3. Real-model frozen dataset replays byte-for-byte

```powershell
python -m prooftrail replay --provider gemini --all
python -m prooftrail manifest --provider gemini
```

- [ ] `Replayed 40/40 cases with no API key; 0 failure(s).`
- [ ] Manifest: `40/40 cases frozen`, `175 LLM calls`, `142227 in / 16950 out tokens`,
      `billed $0.0000`, model `gemini-3.1-flash-lite`, all seven invariants `yes`.
- [ ] `data/frozen/<case>/summary.json` says `"mode": "live-llm-run"` (real model),
      unlike the demo's `scripted-offline-demo-not-a-real-llm-run`.

## 4. Fair baseline B1 replays from committed caches (3 independent runs)

```powershell
0..2 | ForEach-Object {
    python -m prooftrail benchmark b1 --replay --all --provider gemini --model gemini-3.1-flash-lite --run-index $_ --json
    if ($LASTEXITCODE -ne 0) { throw "B1 replay run $_ failed" }
}
```

- [ ] Each run: `"cache_hits": 40, "cache_misses": 0`, `"mode": "replay-no-network"`,
      `"cost_usd": 0.0`, its own `spec_sha256`.
- [ ] `git status --short` is still clean afterwards (replays never rewrite artifacts).

## 5. Human-review integrity

```powershell
python -m prooftrail review status
python -m prooftrail review verify --require-complete
python -m prooftrail benchmark report
```

- [ ] `review status` prints the accepted/abstained/pending counts; compare with
      `docs/HUMAN_REVIEW_RESULTS.md`.
- [ ] If the review is complete: `review verify --require-complete` exits 0 and
      `benchmark report` writes `evidence/runs/benchmark/comparison/comparison.verified.{json,md}`
      with `"label_mode": "verified"` and `"headline_eligible": true`.
- [ ] If the review is **not** complete: both commands exit non-zero **by design**
      (`human-reviewed truth is not headline eligible`). Then only the diagnostic
      exists: `python -m prooftrail benchmark report --allow-provisional` writes
      `comparison.provisional.{json,md}` with `"headline_eligible": false`. A
      provisional file must never be presented as a result.
- [ ] `git diff -- data/frozen data/replay/gemini data/replay/auditors` is empty:
      review never edits frozen evidence.
- [ ] Open any `data/reviews/v1/decisions/<case>.review.json`: it names a real
      reviewer, carries `"attested": true`, a case-specific rationale and the
      source hashes that `review verify` re-checks against `data/frozen/`.

## 6. Same evidence, independent truth

- [ ] `prooftrail/baselines/b1_trace_plus_ledger.py` and `prooftrail/auditor/pipeline.py`
      both consume `FrozenCase.auditor_view()` — trace + raw ledger with family,
      seed and case id stripped.
- [ ] Labels are derived from the ledger (`prooftrail/scenarios/`), never from any
      model output; `labels.provisional.json` keeps `verified_by_human: false`.
- [ ] ProofTrail's claim extraction is deterministic (0 LLM calls, `usage.llm_calls: 0`
      in the comparison JSON). The only LLMs in the benchmark are the agent under
      test and the B1 baseline.

## 7. Cost and secrets

```powershell
python scripts/check_no_secrets.py
git diff --check
```

- [ ] `Secret scan passed`.
- [ ] Billed provider spend across the repository is `$0.00` (Gemini Free Tier);
      list-price equivalents are recorded separately in the manifest and B1 summaries.
- [ ] No personal absolute paths in committed docs:
      `git grep -n -E '[A-Za-z]:[/\\](Users|Documents and Settings)[/\\][^<]' -- docs README.md REPRODUCE.md`
      returns nothing.

## 8. What to read if you have five more minutes

- `docs/SUBMISSION_REPORT.md` — the full write-up, limitations first.
- `docs/TRAJECTORIES.md` — six real traces walked event by event.
- `evidence/runs/benchmark/comparison/comparison.verified.md` (or the provisional
  diagnostic if the review is incomplete).
- `docs/HUMAN_REVIEW_RESULTS.md` — who reviewed, how long it took, what changed.
