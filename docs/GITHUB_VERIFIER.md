# GitHub execution verifier

ProofTrail can check structured claims about one GitHub pull request and one revision.
It compares each claim with GitHub evidence for the same repository and commit, and returns
`SUPPORTED`, `CONTRADICTED` or `UNVERIFIABLE`, with reason codes, evidence references,
collection times and JSON and Markdown certificates.

It checks observable execution facts. It does not review code, does not prove that a change
fixes a bug, does not verify deployment, and does not claim that all tests passed.

Example claim: "I opened PR #4 against `main`, its current head is `ae327d6…`, and the required
checks `replay` and `mcp-adapter` succeeded on that revision."

## Request (schema version 1)

```json
{
  "schema_version": 1,
  "domain": "github",
  "repository": {"owner": "ibrahiemmohamed24", "name": "prooftrail"},
  "pull_request": 4,
  "expected_head_sha": "ae327d60aeaafda41a18a5f88168960f680238e4",
  "expected_base_branch": "main",
  "required_checks": ["replay", "mcp-adapter"],
  "claims": [
    {"id": "c1", "type": "pr_exists"},
    {"id": "c2", "type": "base_branch"},
    {"id": "c3", "type": "head_sha"},
    {"id": "c4", "type": "pr_merged"},
    {"id": "c5", "type": "required_checks_passed"}
  ]
}
```

The contract accepts no URLs, file paths, tokens or extra fields. Owner and repository names,
the 40-character lowercase SHA, branch names, check names (at most 20, no duplicates) and claims
(at most 20, unique IDs) are validated before anything is read.

## Claims

| Claim type | SUPPORTED means | CONTRADICTED means | UNVERIFIABLE means |
|---|---|---|---|
| `pr_exists` | GitHub returns the PR and its base repository is the requested one | the repository is readable and the PR does not exist, or GitHub reports a different base repository | the source is unavailable, forbidden, rate-limited or incomplete |
| `base_branch` | the PR targets the expected base branch | the PR targets another branch | the PR is unknown or its repository identity is unconfirmed |
| `head_sha` | the current head equals the expected SHA, and a second read agrees | the stable head differs from the expected SHA | the head changed during collection, the second read failed, or the PR is unknown |
| `pr_merged` | GitHub reports `merged=true` at collection time | the PR is open or closed without merging | the PR is unknown |
| `required_checks_passed` | every required name has a latest successful completion on the expected SHA | a required name failed, was skipped or neutral, or was not observed on the SHA in complete evidence | a result is pending, ambiguous, incomplete or unreadable |
| `production_deployment` | not supported in this milestone | never | always, with `unsupported_in_this_milestone` |
| `all_tests_passed` | not supported without a test report | never | always, with `no_test_report_evidence` |

What `pr_merged` proves: only that GitHub reported the PR as merged when it was read. It does not
prove that the merge commit equals the expected revision, and it does not prove deployment.

## How checks are decided

- A check run or commit status counts only when its SHA equals the expected SHA. Successful runs
  on older commits are listed as `other_sha_run_ids` and never used.
- A legacy commit status with no SHA is `UNVERIFIABLE` (`status_revision_unconfirmed`).
- Evidence must describe the requested PR number. A different number contradicts `pr_exists`
  and makes dependent claims `UNVERIFIABLE` (`pull_request_number_mismatch`).
- `queued`, `in_progress`, `waiting`, `requested` and `pending` are not success; they stay
  `UNVERIFIABLE` (`check_pending`).
- `success` is the only conclusion that counts as success. `failure`, `timed_out`, `cancelled` and
  `action_required` are contradictions. `neutral` and `skipped` are not success, so they
  contradict the claim (`check_not_successful`).
- GitHub records a separate check run for each trigger (push and pull request) and for each rerun.
  For one name and one producer, the highest run ID is the latest attempt. Earlier attempts are
  listed as superseded, and the reason says when the attempts disagree.
- When several producers report the same name on the same SHA (for example a check run and a
  commit status), no single result is chosen: the verdict is `UNVERIFIABLE` (`ambiguous_producers`).
- A required name missing from complete evidence is `CONTRADICTED` with
  `required_check_not_observed_on_expected_sha`. The reason says this does not prove the check never
  ran elsewhere. Missing data from a failed or incomplete source is `UNVERIFIABLE` instead.
- Pagination is bounded (5 pages of 100). A page limit, a count mismatch or a truncated list makes
  the evidence incomplete, and incomplete evidence never gives a confident check verdict.

Verdicts are aggregated the same way as the refund auditor: `CONTRADICTED` dominates, then
`UNVERIFIABLE`, otherwise `SUPPORTED`. No numerical confidence is reported.

## Evidence modes

**Offline (no network, no credentials).** Audits a saved bundle: a JSON snapshot of the repository,
the pull request, a second read of its head, check runs, commit statuses and the observation status of
each source. Its SHA-256 is computed over canonical JSON. The hash shows the bundle is unchanged since
it was hashed; it does not authenticate who produced it. Bundles declare their provenance:
`synthetic_fixture` (labelled as not production evidence), `saved_live_capture`, `offline_bundle` or `live`.
Declared provenance is untrusted. `network_used` is runtime-only metadata set by the collector,
never read from an uploaded bundle; an offline audit reports no network use even if the bundle
declares `kind=live`. Uploaded and saved evidence does not establish source authenticity or
the current state of GitHub.

Scenario packs with hand-written expected verdicts live in `examples/github/`. They are synthetic:
owner, SHAs and times are placeholders. The committed packs must match the generator byte for byte
(`tests/test_github_examples.py`).

**Live (read-only).** Reads these endpoints, all under `https://api.github.com`:

| Endpoint | Used for |
|---|---|
| `GET /repos/{owner}/{repo}` | repository identity and visibility |
| `GET /repos/{owner}/{repo}/pulls/{number}` | PR existence, base, head, merged flag |
| `GET /repos/{owner}/{repo}/commits/{sha}/check-runs?filter=all` | every check run attempt on the SHA |
| `GET /repos/{owner}/{repo}/commits/{sha}/status` | commit statuses (legacy contexts) on the SHA |
| `GET /repos/{owner}/{repo}/pulls/{number}` (again, at the end) | detects a head change during collection |

Safety controls:

- The host is fixed to `api.github.com`. Paths are built only from validated fields; absolute URLs are refused.
- Redirects are refused, not followed, so an `Authorization` header never reaches another host.
- Timeout 5 s per request, a 20 s deadline for the whole collection, 2 MB per response, 5 pages per list.
- Rate limits (`403`/`429` with `x-ratelimit-remaining: 0` or `retry-after`), `401`, `404`, `5xx`,
  invalid JSON and oversized responses become observations with a status. They never become exceptions
  that could expose a credential.
- Nothing is written to the audited repository. Nothing is persisted by ProofTrail.

## Token and permissions

Public repositories need no token. Unauthenticated requests share a limit of 60 per hour per IP
address (GitHub REST rate-limit documentation), which is enough for one audit at a time.

An optional read-only token can be set in the environment of the local server or CLI:

```powershell
$env:PROOFTRAIL_GITHUB_TOKEN = "<read-only token>"   # or GITHUB_TOKEN
```

The token is never printed, logged, stored, or included in observations, certificates or
bundles, and the web page has no field for it. Tests check that a fake token value does not appear in
any output.

Permissions checked against GitHub's documentation:

- `GET /repos/{owner}/{repo}`: Metadata, read.
- `GET /repos/{owner}/{repo}/pulls/{pull_number}`: Pull requests, read. The docs mark some endpoints
  with additional permissions, so verify this on a private repository before relying on it.
- `GET /repos/{owner}/{repo}/commits/{ref}/status`: Commit statuses, read.
- `GET /repos/{owner}/{repo}/commits/{ref}/check-runs`: the permission table does not list it. The Checks
  API documents that classic tokens need the `repo` scope for private repositories. Fine-grained access
  is not stated, so check-run access on private repositories is unverified. If the token cannot read
  check runs, the claim is `UNVERIFIABLE` with `source_forbidden`; it is never reported as a failure.

The verifier needs no write permission and never creates or changes pull requests, checks or settings.

## API version

Requests send `X-GitHub-Api-Version: 2022-11-28`. That is GitHub's default version and is supported
until March 10, 2028. The latest version is `2026-03-10`; moving to it is a separate change that
needs its own tests.

## Using it

```powershell
# Offline: audit a saved bundle (no network)
python -m prooftrail github audit --request request.json --bundle bundle.json

# Live: read api.github.com once and optionally keep the snapshot as a saved capture
python -m prooftrail github audit --request request.json --live --save-pack examples\github\live-capture.json

# Regenerate the synthetic packs
python -m prooftrail github examples --write examples\github
```

The local control room exposes the same engine: open **New audit**, choose **GitHub pull request
and required checks**, then use a synthetic example or paste a bundle (offline) or select live read.
The HTTP API is `POST /api/v1/github/audits` with `{"mode": "offline"|"live", "request": {...}, "bundle": {...}}`
(`bundle` only in offline mode). `GET /api/v1/github/examples` lists the allow-listed packs.

The MCP tool `audit_github_execution` audits a saved bundle only. It has no network access and no
live mode, because sending live (possibly private) repository data to an assistant host is a separate
data-sharing decision.

## What is not claimed

- Code review, bug fixing or test-quality judgements.
- Production deployment, environment state or that a merge reached production.
- That all tests passed or how many ran (a green check is not a test report).
- Authenticity of a bundle or of GitHub responses beyond what GitHub's TLS endpoint provides.
- Results for private repositories, GitHub Enterprise, other hosts or general-domain claims.
- Calibrated confidence. Verdicts are deterministic rules over recorded observations.

See `docs/GITHUB_VERIFIER_QA.md` for the tests, the live example and the browser checks.
