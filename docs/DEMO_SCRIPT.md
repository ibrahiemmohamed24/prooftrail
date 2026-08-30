# Demo video script (2:30, target ≤ 3:00)

Ready to record now that the verified report exists. Every number spoken on
camera must be read from `evidence/runs/benchmark/comparison/comparison.verified.md`
at recording time — do not use the provisional diagnostic and do not record
before `python -m prooftrail review verify --require-complete` exits 0.

Before recording:

- Fresh terminal in a clean clone with the venv activated; no `GEMINI_API_KEY`
  or `ANTHROPIC_API_KEY` in the environment (`Get-ChildItem Env: | Where-Object Name -like "*API_KEY*"` is empty).
- Hide the OS user name in the prompt (`function prompt { "PS prooftrail> " }`),
  close notification centres, mail and chat clients, and do not show file
  explorer paths that contain the user name.
- Font size ≥ 16 pt; terminal width ≥ 110 columns so the demo lines do not wrap.
- Keep `docs/TRAJECTORIES.md` and the verified Markdown report open in a second window.

## 0:00–0:20 — the problem, in one sentence

Say: *"An agent's final message is written by the same model that can be lied to
by a flaky tool. ProofTrail checks what the agent says it did against what the
system of record proves it did, and points at the first event where they diverge."*

Show: the README diagram (agent → tools → ledger; B1 and ProofTrail both read the
frozen trace + ledger).

## 0:20–0:50 — the killer case, scripted fixture

Run:

```powershell
python -m prooftrail demo
```

Say, while it prints: *"This is a deterministic offline fixture, not a real
model run — it exists so you can see the failure shape in five seconds. The
agent says it refunded $47 once. The ledger shows two commits and $94."*

Point at: `Verdict: CONTRADICTED`, `First bad: ledger event #6`, `Hash chain: valid`,
and the `Mode:` line that says the run is scripted.

## 0:50–1:15 — event #6, state before/after

Open `evidence/runs/demo-f02/certificate.md`. Scroll to the claim table.

Say: *"The timeout at event #4 is not the mistake — the first refund had already
committed. The first harmful action is the second `state_changed` under the same
intent, event #6: `refunded_cents` goes from 4700 to 9400. That is the event a
human should look at, instead of a whole transcript."*

## 1:15–1:45 — same evidence for B1 and ProofTrail, real model traces

Run:

```powershell
python -m prooftrail replay --provider gemini --all
```

Say: *"These are forty real traces from a Gemini refund agent, frozen once and
replayed here with no API key — 175 model calls, billed $0. Both auditors get the
identical input: the trace plus the raw ledger, with the scenario family stripped.
B1 is a one-shot LLM asked to judge it. ProofTrail is deterministic — zero model
calls — it extracts the action claims and reconciles them against ledger writes."*

Show one real trace from `docs/TRAJECTORIES.md` — F04-s00 (tool says
`refunded`, ledger has no write; B1 believed the tool in all three runs).

## 1:45–2:10 — the verified comparison

Open `evidence/runs/benchmark/comparison/comparison.verified.md`.

Read the outcome table **from the file**: B1 family-mean accuracy (mean ± SD
over three runs), ProofTrail family-mean accuracy, first-bad hit rates, B1
verdict unanimity, billed cost `$0.00` and the list-price equivalent per
prediction. Then say the honest caveat that is also printed in the report:
*"Removing ProofTrail's temporal verifier changed no verdict on this dataset —
amount, count and entity reconciliation already catch these cases. We report
that, we do not hide it."*

Do not read any number from `comparison.provisional.md`.

## 2:10–2:30 — the human-review guard, replay without a key

Run:

```powershell
python -m prooftrail review status
python -m prooftrail review verify --require-complete
```

Say: *"The headline exists only because a named person reviewed all forty labels
one by one — there is no bulk approval, every decision is hash-bound to the frozen
case, and the report refuses verified mode otherwise. Everything you just saw ran
with no API key."*

## Closing card (5 s)

- `github.com/ibrahiemmohamed24/prooftrail`
- One command: `python -m pip install -e ".[dev]" && python -m pytest && python -m prooftrail replay --provider gemini --all`
- "Same evidence. Independent truth. Frozen traces."

## Publishing

- Upload the video outside Git (YouTube unlisted or a competition drive). Put
  the link in the README "Demo video" section and in `docs/SUBMISSION_REPORT.md` §17.
- Do not commit the video file unless the competition rules require it.
- Re-check the recording for: API keys, personal absolute paths, notifications,
  personal accounts, any non-synthetic data.
