# Representative Codex development trajectories

These are curated, privacy-safe excerpts from the real Codex-assisted build.
They preserve the participant instruction, Codex action, tool response, human
feedback/checkpoint and final evidence. Repeated setup chatter, absolute user
paths, credentials and unrelated discussion are omitted. No failure or
decision shown below is fabricated.

Codex was the development agent. Runtime trajectories for the refund agent and
B1 are documented separately in `docs/TRAJECTORIES.md` and the committed
provider caches.

## C1 — Replace a paid-only plan with a real zero-billed provider

**Human instruction.** Find a correct way to run real model calls without the
planned `$5` spend, keep the workflow reproducible and do not expose a key.

**Codex actions.** Added a provider-neutral Gemini REST adapter, Free Tier cost
metadata, retry and quota handling, provider-namespaced prompt-hash cache,
freeze/replay commands, tests and secret scanning. Codex initially suggested a
model name that did not complete successfully and asked the participant to
query the key's available model list rather than guess.

**Tool response and feedback.** The first direct generation attempt produced no
candidate (`Cannot index into a null array`). The participant returned the
available models, including `gemini-3.1-flash-lite`, then ran the corrected
command. The live tool loop completed with four model calls and three tool
calls:

```text
case_id=F02-s00
model=gemini-3.1-flash-lite
actual_refund_count=1
actual_refunded_cents=4700
verdict=SUPPORTED
cache_hits=0, cache_misses=4
billed_cost_usd=0.0
```

The participant then removed the key and requested replay. The replay returned
four cache hits, zero misses, the same claim/state/verdict and no network use.

**Result and next decision.** The real F02 agent behaved safely by checking
refund state after the timeout; the scripted double-refund remained a labelled
fixture rather than being passed off as organic model behaviour. Codex extended
the same resumable path to all 40 cases. Evidence:
`data/frozen/F02-s00/`, `data/replay/gemini/F02-s00.json`, and
`data/frozen/manifest.json` (40/40, 175 calls, billed `$0.00`).

## C2 — Make the baseline fair, strict and resumable

**Human instruction.** Give B1 exactly the same frozen trace plus ledger as
ProofTrail, run repeated real calls, preserve everything for zero-key replay,
and batch meaningful work without frequent commits.

**Codex actions.** Implemented the B1 prompt/strict JSON schema, spec hashing,
separate run-index cache namespaces, resumable execution and an offline report.
Both B1 and ProofTrail consume `FrozenCase.auditor_view()`; family, seed and
labels are absent from that view.

**Tool response.** The first 40-case run completed 38 cases but rejected two
malformed model responses:

```text
F07-s02 InvalidJSONCompletion: Unterminated string starting at
F10-s02 InvalidJSONCompletion: Unterminated string starting at
completed_cases=38, failure_count=2, complete=false
```

**Human feedback/checkpoint.** The participant stopped the multi-run loop rather
than counting malformed output, returned the exact failure JSON and reran after
Codex tightened the fail-closed/resume path. Accepted cases stayed cached;
failed completions were not silently repaired or scored.

**Result and next decision.** Three independent runs produced 120 accepted
outputs and replay with no key. B1 family-mean accuracy was 85.0% ± 2.04 pp and
verdict unanimity 35/40. Its persistent F04 error—trusting
`tool_call_completed{ok:true}` while the ledger held no state write—motivated
the main failure analysis and hot take. Evidence:
`evidence/runs/benchmark/b1/`, `data/replay/auditors/`, and
`comparison.verified.{json,md}`.

## C3 — Keep benchmark truth human and fail closed

**Human instruction.** Complete the 40-case review personally, progress in
small visible batches, preserve the frozen agent/B1 artifacts and prevent any
script or AI from bulk-approving labels.

**Codex actions.** Added immutable review packs, one-case-at-a-time
`APPROVE`/`AMEND`/`ABSTAIN` commands, case-specific attestation, SHA-256 binding,
stale/tamper detection, status reporting and a verified-report gate. Codex
generated reading aids and formatted amendment JSON only after the participant
had made the underlying decision.

**Human checkpoints and tool responses.** The participant inspected cases and
returned successive real status checkpoints:

```text
7/40 reviewed  -> 12/40 -> 16/40 -> 21/40 -> 26/40
-> 31/40 -> 33/40 -> 34/40 -> 40/40
```

For an amendment, the participant opened the case-specific JSON, validated it
with `ConvertFrom-Json`, then executed the individual review command. No bulk
decision command exists.

**Result.** `review verify --require-complete` reports 40 reviewed, 40 accepted,
0 abstained and `Headline ready: yes`. There are 33 approvals and seven
amendments; the amendments add ledger-supported refund claims but change no
verdict or first-bad event. Only then did `benchmark report` emit the verified,
headline-eligible comparison. Evidence: `data/reviews/v1/`,
`docs/HUMAN_REVIEW_RESULTS.md`, and the verified comparison.

## C4 — Human scope control and rejected complexity

**Human instruction.** Finish within the competition window, keep the core
verification story, defer the frontend and avoid automatic repair of financial
tools.

**Codex action.** Kept the deliverable CLI-first, produced JSON/Markdown
certificates, removed auto-fix from scope, and measured a no-temporal ablation
instead of assuming every verifier component helped.

**Tool response.** Removing the temporal verifier changed zero verdicts and
zero first-bad locations across 40 cases. The participant accepted the negative
result and required it to remain visible in the README, report and video.

**Result.** The final engineering claim credits deterministic amount, count,
entity and state reconciliation—not unmeasured complexity. The optional UI and
automatic tool patching are not part of the submitted solution.

## Runtime-agent trajectory index

- Refund agent instructions: `prooftrail/agent/prompts.py`
- B1 instructions: `prooftrail/baselines/prompts.py`
- Seven selected runtime traces and one clearly labelled scripted fixture:
  `docs/TRAJECTORIES.md`
- Complete refund-agent traces: `data/frozen/<case>/case.json`
- Complete refund-agent provider responses: `data/replay/gemini/`
- Complete B1 responses for three runs: `data/replay/auditors/b1/`

ProofTrail is deterministic code rather than a model-driven agent; its audit
path and citations are preserved in each `audit.json` and certificate.
