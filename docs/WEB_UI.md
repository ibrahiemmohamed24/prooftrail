# Offline evidence viewer

The active repository is https://github.com/ibrahiemmohamed24/prooftrail.
The competition snapshot remains archived at
https://github.com/ibrahiemmohamed24/prooftrail-submission.

## Windows quickstart

From the repository root:

```powershell
python -m prooftrail ui build
python -m http.server 8000 --bind 127.0.0.1 --directory evidence/ui
```

Open http://127.0.0.1:8000. Stop the server with Ctrl+C.
You may also open `evidence/ui/index.html` directly. No provider key is needed.

## Implemented

- Verified benchmark overview and explicit dataset limitations.
- All 40 cases with verdict/family/review filters.
- Agent report, claim cards, cited ledger events and first harmful event.
- Evidence inspector with state before/after and agent-visible tool calls.
- Printable certificates and original JSON/Markdown downloads.
- Bundled fonts and local assets using the navy/orange brand palette.
- Deterministic static output, generated under ignored `evidence/ui/`.
- Raw ledger chain verification during view-model loading.

The viewer renders existing artifacts. It does not edit frozen traces or make
model calls. Rebuild it after changes to evidence; a previously built site is
a snapshot and does not monitor source files for updates.

## Remaining product work

There is no HTTP auditing API, upload workflow, authentication, React app,
MCP server, or Codex/Claude/Manus plugin in this version. Benchmark information
is on Overview rather than a separate benchmark route. Case search, sorting,
URL-persisted filters and interactive human review remain future work.

The next integration should wrap `audit_trace` and the existing certificate
builders in a platform-neutral application service, with thin HTTP/MCP/skill
adapters. Keep verdict and reconciliation logic in Python. Preserve the
competition evidence separately from new domain or provider datasets.

## Metadata follow-up

The historical `LICENSE` and package author metadata name Fatma Ramadan while
the competition disclosure names Ibrahiem Mohamed. Ownership/provenance needs
clarification before publishing a new package or plugin; integration preserves
the existing notice rather than silently replacing a copyright holder.
