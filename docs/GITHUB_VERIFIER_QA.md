# GitHub execution verifier: validation record

Branch `feat/github-execution-verifier`, stacked on open PR #4 (`feat/control-room-app`).
This records what was run and what it showed. It is not a production or commercial claim.

## Automated tests

- Full suite (`python -m pytest`, Python 3.14 locally): **445 passed, 2 skipped**. The skipped
  tests are the live GitHub tests, which run only with `PROOFTRAIL_LIVE_TESTS=1`.
- With `PROOFTRAIL_LIVE_TESTS=1`: `tests/test_github_live.py` **2 passed** (about 32 s).
- Secret scan (`scripts/check_no_secrets.py`): passed.
- JavaScript (`node --check`) passes for `github-audit.js` and `control-room.js`.
- Python 3.11 syntax: checked with a token-level script that flags f-string forms Python 3.11
  rejects. No issues were found. Tests were not run on 3.11 or 3.12 on this machine; CI uses 3.12.

## Synthetic scenarios (18 fixtures plus a merged-PR case)

Hand-written expected verdicts, checked against the engine by `tests/test_github_rules.py`:
correct open PR (SUPPORTED); PR in another repository; wrong base; head mismatch; merge claim on
an open PR; merged PR (SUPPORTED); checks on an older SHA only; failed check; pending check; skipped
check; required check missing from incomplete evidence; rerun after failure; two producers for one
name; head changed during collection; rate limit; forbidden checks; timed-out PR read; unsupported
claims; PR not found. Every scenario is labelled synthetic.

## Live evidence (read-only, unauthenticated, public repository)

Repository `ibrahiemmohamed24/prooftrail`, PR #4 (open), expected head
`ae327d60aeaafda41a18a5f88168960f680238e4`, expected base `main`, required checks `replay` and
`mcp-adapter`. Collected at 2026-10-09T11:33:14Z; all five observations `ok` and complete.

| Claim | Verdict | Reason code |
|---|---|---|
| c1 `pr_exists` | SUPPORTED | `pr_found_in_expected_repository` |
| c2 `base_branch` | SUPPORTED | `base_branch_matches` |
| c3 `head_sha` | SUPPORTED | `head_sha_matches` (head unchanged on the second read) |
| c4 `pr_merged` | CONTRADICTED | `not_merged` |
| c5 `required_checks_passed` | SUPPORTED | `required_checks_succeeded` |

Overall: CONTRADICTED, because the merge claim is false. The required checks each had two
successful check-run attempts on the SHA (the push and pull_request events both created one). The
latest attempt by id was used and the earlier one is listed as superseded.

Merged PR #3 (live test): `pr_exists`, `base_branch` and `pr_merged` are all SUPPORTED. The merged
flag is the only fact the merge claim establishes.

The saved capture is committed as `examples/github/live-capture-ibrahiemmohamed24-prooftrail-pr4.json`.
It is labelled `saved_live_capture` and not synthetic. The PR may move later; the capture does not.

## Browser checks (headless Chrome, DevTools Protocol)

Viewports 1440x900, 1024x768 and 390x844, against the local control room:

- New audit with **GitHub** selected: the synthetic example audit returns `SUPPORTED` at all three
  sizes. The refund panel is hidden. The page has no console errors.
- Horizontal overflow (`scrollWidth` compared with `clientWidth`) is zero at every size, measured
  on the form and on the result.
- Live read of PR #4 from the form: `SUPPORTED`, status "Read from GitHub".
- Malformed bundle JSON: refused with "The bundle is not valid JSON" and no request is sent.
- Refund workflow, unchanged: frozen example returns `CONTRADICTED` with the usual status.
- On a 390 px phone, result tables become labelled cards (CLAIM, TYPE, VERDICT, REASON, EVIDENCE),
  checked in a screenshot after the change. Before the change they were squeezed and clipped.

Screenshots were reviewed by eye. No automated visual-regression baseline exists.

## Known issues and limits

- `prooftrail/ui/assets/control-room.js` (from PR #4) contains mojibake in some status strings
  (for example `â€¦`). It was not changed on this branch. The new `github-audit.js` uses ASCII only.
- Live mode was exercised only without a token and against a public repository. Token-authenticated
  requests and rate-limit behaviour were not tested live. Rate-limit handling is tested offline with
  fixed responses.
- Private repositories were not tested. Check-run access on private repositories is not documented
  for fine-grained tokens (see `GITHUB_VERIFIER.md`); the verifier reports `source_forbidden` rather
  than a failure if access is missing.
- The REST API version is pinned to `2022-11-28`, the default and supported until March 10, 2028.
  The latest version is `2026-03-10` and was not tested.
- Browser checks used Chrome only. No other browser, device or assistive-technology test was run.
- CI has not yet run on this branch.
