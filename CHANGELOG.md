# Improvement Changelog

## 2026-10-09 — GitHub execution verifier

- Observation: the refund auditor could not check claims about a coding agent's
  pull request, its revision or its required CI checks.
- Change: added a `github` domain with a versioned request contract, bundle and
  live evidence sources, deterministic rules, JSON and Markdown certificates,
  the local New audit option, HTTP route `POST /api/v1/github/audits`, CLI
  `github audit|examples`, and MCP tool `audit_github_execution` (offline only).
- Live collection is read-only, host-pinned to `api.github.com`, does not follow
  redirects, and bounds timeouts, response size, pages and total time. Errors become
  `UNVERIFIABLE` observations; no credential is printed, stored or certified.
- Tests: 445 offline tests pass; two read-only live tests against
  `ibrahiemmohamed24/prooftrail` pass with `PROOFTRAIL_LIVE_TESTS=1`.
- Limits: deterministic rules only; no code review, deployment, or test-count
  verification; a green check is not a test report.

## 2026-10-09 — local control room and adapter boundary

- Observation: the static viewer could only display existing evidence; operators
  could not submit new traces or route the same auditor through a host tool.
- Change: added a shared read-only application interface, local-only HTTP server,
  in-memory upload audit workflow and exact certificate downloads. Reused existing
  HTML/JS rather than adding a second frontend toolchain or mandatory dependencies.
- Added URL-persisted search/sort/filter controls and separate measured Benchmark
  and Integrations pages. The zero-effect temporal ablation is shown explicitly.
- Added optional SDK-backed stdio MCP tools and a portable evidence-audit skill.
- Evidence: all 40 supplied frozen cases reproduce their original certificates;
  tests reject invalid JSON, unknown fields, empty/unsealed ledgers, path traversal
  and cross-origin requests. A real stdio client discovers all six tools and
  audits an existing case. Browser checks exercise the actual HTTP upload path.
- Limits: refund-domain only, no remote SaaS or auth, no claim of Manus/host
  installation or marketplace publication, no invented confidence. Historical
  frozen evidence and human labels are unchanged.

This is the evidence-linked history of meaningful design iterations. Each row
states the observed limitation, the change it motivated, the evidence produced
and the decision that followed. Historical provisional results remain labelled
and are never presented as the verified headline.

| # | Date | Observation or failure | Change | Evidence and next decision |
|---:|---|---|---|---|
| 0 | 2026-08-28 | A transcript cannot establish whether a refund committed. | Built deterministic IDs, SQLite customer/order/refund state and an append-only hash-chained ledger. | Foundation tests established reproducible state and event ordering; next, make tool side effects atomic with ledger writes. |
| 1 | 2026-08-28 | A timeout can occur before or after commit, so a stateless mock cannot localize the harmful retry. | Added stateful refund tools, atomic `state_changed` writes, six injected fault modes and ten scenario families. | The scripted F02 fixture proves two commits and `$94` after a `$47` claim, with the first harmful write at event `#6`; next, produce a usable certificate. |
| 2 | 2026-08-28 | A verdict alone leaves an operator reading the whole transcript. | Added deterministic claim extraction, evidence linking, state reconciliation, first-bad localization and JSON/Markdown evidence certificates. | The offline end-to-end demo returns `CONTRADICTED`, cites event `#6` and validates the ledger chain; next, test organic model behaviour rather than only a fixture. |
| 3 | 2026-08-29 | Scripted behaviour is not evidence of how a real tool-using agent responds to ambiguous tool results. | Added a provider-neutral agent loop, Gemini Free Tier adapter, prompt-hash caching, resumable freeze/replay and manifest integrity checks. | Froze 40 real traces (10 families × 4 seeds): 175 model calls, 133 tool calls, billed `$0.00`; replay succeeds 40/40 with no key. Real F02 did not double-refund, so the fixture remains explicitly separate. |
| 4 | 2026-08-30 | Comparing ProofTrail with an LLM that sees less evidence would guarantee the improvement by construction. | Added B1, a strict one-shot LLM baseline that receives the identical anonymized frozen trace plus raw ledger; recorded three independent runs with separate cache/spec hashes. | 120/120 accepted B1 outputs replay offline. The provisional comparison measured 85.0% ± 2.04 pp family-mean accuracy for B1 versus 100% for ProofTrail, but publishing stayed blocked pending human truth. |
| 5 | 2026-08-30 | Ledger-derived labels are not an independent final benchmark, and bulk approval would weaken integrity. | Added per-case source-bound `APPROVE` / `AMEND` / `ABSTAIN` decisions, hash validation and a report that fails closed until review is complete. | The sole author reviewed 40/40 cases: 33 approve, 7 amend, 0 abstain, 298 active minutes. `review verify --require-complete` passes and the verified report is `headline_eligible: true`. |
| 6 | 2026-08-30 | A complex temporal verifier might look impressive without contributing measured value. | Added a no-temporal ablation and repeat-stability analysis. | Removing the temporal verifier changed 0/40 verdicts or first-bad locations; B1 was wrong on every F04 case in all three runs and changed verdict across five F06/F07 cases. Decision: credit deterministic amount/count/entity reconciliation, not unmeasured complexity. |
| 7 | 2026-08-31 | The submission package must make the intended user, agent instructions, measured improvement, reproducibility, trajectories, main failure mode and hot take directly discoverable. | Reorganized the final README/report, added an official-package checklist, disclosed OpenAI Codex development assistance, linked exact prompt sources, expanded the under-five-minute video script and linked the uploaded solution video. | Code, changelog, reproduction guide, trajectories and video link are ready for submission. |

## Active repository integration — 2026-10-09

Integrated the final competition documentation and video reference into the
active `prooftrail` repository alongside the static UI introduced in `af79e4f`.
Preserved the existing contributor history and identical frozen evidence,
replay caches, review decisions and benchmark reports. The viewer now verifies
raw ledger chains, exports the original certificates, and keeps desktop filters
in their layout rather than overlaying the cases table. CI builds the viewer;
generated pages are ignored. Future API/MCP/skill integrations remain planned.

## Verified headline


From `evidence/runs/benchmark/comparison/comparison.verified.{json,md}`:

- Cases: 40 across 10 equally weighted families.
- B1 family-mean accuracy: **85.0% ± 2.04 percentage points** over three runs.
- ProofTrail family-mean accuracy: **100.0%** against accepted human truth.
- B1 verdict unanimity: **35/40**.
- ProofTrail model calls during audit: **0**.
- Recorded provider spend: **$0.00**.

## Main failure mode and hot take

The main failure is treating a timeout or successful-looking tool response as
proof of a committed side effect. The transcript is an untrusted witness once
an agent can change state. Models should interpret language and choose tools;
deterministic reconciliation against the system-of-record ledger should decide
what happened. The zero-gain temporal ablation reinforces a practical rule:
add the smallest verifier justified by measured failures.

## Evidence index

- Frozen real-agent traces and manifest: `data/frozen/`, `data/replay/gemini/`
- Repeated B1 artifacts: `evidence/runs/benchmark/b1/`, `data/replay/auditors/`
- Human decisions and manifest: `data/reviews/v1/`
- Verified comparison: `evidence/runs/benchmark/comparison/comparison.verified.{json,md}`
- Selected trajectories: `docs/TRAJECTORIES.md`
- Reproduction commands and expected outputs: `REPRODUCE.md`, `docs/JUDGE_CHECKLIST.md`
