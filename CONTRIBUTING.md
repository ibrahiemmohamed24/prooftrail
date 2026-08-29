# Contributing to ProofTrail

## One-time setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
```

## Branch and pull-request workflow

Never develop directly on `main`.

```powershell
git switch main
git pull --ff-only
git switch -c feat/short-description

# edit and verify
python -m pytest
python -m prooftrail demo --json
python scripts\check_no_secrets.py

git add .
git diff --cached --check
git commit -m "feat: describe the change"
git push -u origin feat/short-description
gh pr create --base main --fill
```

Use `fix/…`, `docs/…`, or `test/…` prefixes when they describe the work more
accurately. Keep one independent concern per pull request.

## Definition of done

- New behaviour has tests; the full suite passes.
- Replay remains zero-network unless the command explicitly requests live mode.
- Baseline and ProofTrail fairness constraints remain intact.
- Generated labels are never marked human-verified without actual review.
- `PROJECT_STATUS.md` and `CHANGELOG.md` reflect any milestone change.
- No `.env`, API key, virtual environment, cache, database or personal data is committed.

Frozen benchmark traces and replay responses are intentional repository data;
review them for secrets and size before committing.
