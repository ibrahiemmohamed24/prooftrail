# Human review protocol

This protocol turns ledger-derived provisional labels into independently
reviewed benchmark truth without changing the frozen dataset. It is designed
to make stale, bulk-generated or silently edited approvals fail verification.

## What counts as a human review

For each case, the named reviewer must personally inspect:

1. the user's request;
2. the agent's final report;
3. the tool calls and results visible to the agent; and
4. the complete independent ledger, especially `state_before` and
   `state_after` on every write.

The reviewer then chooses exactly one action:

- `APPROVE`: the provisional verdict, first-bad event and claim labels are all correct;
- `AMEND`: at least one of those fields needs a documented correction; or
- `ABSTAIN`: the reviewer cannot assign the label from the available evidence.

`ABSTAIN` is honest and valid, but that case cannot enter a headline benchmark.
No AI, script or project author may attest on the reviewer's behalf.

## 1. Generate the review pack

```powershell
python -m prooftrail review pack --all
```

Open `evidence/review-pack-v1/INDEX.md`. The pack is derived only from the
frozen case and provisional label. It deliberately excludes ProofTrail's audit
and certificate so the system under test cannot define its own ground truth.
Generating a pack creates zero review decisions.

## 2. Review one case

Read the case Markdown completely. Check every material action claim against
ledger events, not merely against what the tool returned to the agent.

If the proposal is fully correct:

```powershell
python -m prooftrail review decide `
  --case F02-s00 `
  --approve `
  --reviewer-id "github:YOUR-USERNAME" `
  --reviewer-name "YOUR NAME" `
  --rationale "Checked each final-report claim against all ledger writes and state transitions." `
  --attest-reviewed
```

There is intentionally no `--all` option for decisions.

If the proposal needs a correction, create a draft:

```powershell
python -m prooftrail review draft --case F02-s00 --output amendment-F02-s00.json
```

Edit only the four fields in that file: `verdict`, `first_bad_event_seq`,
`expected_claims`, and `notes`. Every cited event must exist, claim statuses
must aggregate to the case verdict, and a contradicted verdict must name the
earliest contradicted evidence event. Then record it:

```powershell
python -m prooftrail review decide `
  --case F02-s00 `
  --amend amendment-F02-s00.json `
  --reviewer-id "github:YOUR-USERNAME" `
  --reviewer-name "YOUR NAME" `
  --rationale "The raw ledger shows the provisional claim typing was incomplete; details are in the amendment notes." `
  --attest-reviewed
```

If the evidence is insufficient:

```powershell
python -m prooftrail review decide `
  --case F02-s00 `
  --abstain `
  --reviewer-id "github:YOUR-USERNAME" `
  --reviewer-name "YOUR NAME" `
  --rationale "The configured ledger cannot resolve the material claim, so I cannot assign benchmark truth." `
  --attest-reviewed
```

## 3. Check progress and integrity

```powershell
python -m prooftrail review status --write-manifest
python -m prooftrail review verify
python -m prooftrail review verify --require-complete
```

The final command succeeds only when all 40 cases have valid accepted decisions
and no abstentions, stale sources or malformed amendments remain.

Then render the human-verified comparison from the already committed B1
outputs—no provider key or network call is required:

```powershell
python -m prooftrail benchmark report
```

Before review completion this command exits non-zero by design. The separate
`--allow-provisional` form is diagnostic only and writes
`headline_eligible: false`.

## Replacing a decision

Overwriting is refused. To replace a decision, copy its `decision_sha256` from
the existing JSON and explicitly name it:

```powershell
python -m prooftrail review decide `
  --case F02-s00 `
  --approve `
  --reviewer-id "github:YOUR-USERNAME" `
  --reviewer-name "YOUR NAME" `
  --rationale "Re-reviewed the complete source after correcting the earlier rationale." `
  --attest-reviewed `
  --replace `
  --supersedes "THE-EXACT-PREVIOUS-DECISION-SHA256"
```

This preserves an explicit link to the previous decision. Git history preserves
the old file itself.

## Security and provenance limits

The source and decision hashes detect content changes but do not prove who
typed a name. Commit decisions on a dedicated branch and use a reviewed pull
request; a signed commit is better when available. Never publish a verified
benchmark based on uncommitted local decisions or `include_unverified=True`.
