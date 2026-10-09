# Local evidence control room

The active repository is https://github.com/ibrahiemmohamed24/prooftrail.
The competition snapshot remains archived at
https://github.com/ibrahiemmohamed24/prooftrail-submission.

## Windows quickstart

From the repository root:

```powershell
python -m prooftrail.web --port 8766
```

Open http://127.0.0.1:8766. Use **New audit** to select or paste a schema-v1
`case.json` (trace + sealed ledger). Use **Load frozen example** for a working
sample. Run the audit and download its JSON/Markdown certificate. Evidence stays
in memory; closing the server does not save it. No API key or cloud account is needed.

For the read-only static export instead:

```powershell
python -m prooftrail ui build
python -m http.server 8000 --bind 127.0.0.1 --directory evidence/ui
```

Open http://127.0.0.1:8000. Stop the server with Ctrl+C.
You may also open `evidence/ui/index.html` directly. No provider key is needed.

## Implemented

- Verified benchmark overview and explicit dataset limitations.
- All 40 cases with verdict/family/review/model/first-bad filters, text search,
  ascending/descending case sorting and URL-persisted selections.
- Agent report, claim cards, cited ledger events and first harmful event.
- Evidence inspector with state before/after and agent-visible tool calls.
- Printable certificates and original JSON/Markdown downloads.
- Bundled fonts and local assets using the navy/orange brand palette.
- Deterministic static output, generated under ignored `evidence/ui/`.
- Raw ledger chain verification during view-model loading.
- New audit: file/paste input, validation, loading/error states, exact claim
  evidence sequences, integrity verdict and JSON/Markdown downloads.
- New audit also offers **GitHub pull request and required checks** as an
  evidence type (the refund workflow is the default). It audits a saved bundle or
  a synthetic example offline, or reads `api.github.com` read-only in live mode.
  The page has no token field. Results show each claim, required check, evidence
  source with collection times, warnings, limitations, and JSON/Markdown downloads.
  API: `GET /api/v1/github/examples`, `GET /api/v1/github/examples/<id>`,
  `POST /api/v1/github/audits`. See [GITHUB_VERIFIER.md](GITHUB_VERIFIER.md).
- Separate Benchmark page with per-family accuracy, repeated-run stability,
  failures, ablation results and limitations from committed comparison data.
- Separate Integrations page and local HTTP API backed by the same Python engine.
- Optional stdio MCP adapter and portable audit skill; see `INTEGRATIONS.md`.

The viewer renders existing artifacts. It does not edit frozen traces or make
model calls. Rebuild it after changes to evidence; a previously built site is
a snapshot and does not monitor source files for updates.

## Design and limits

The implementation extends the existing Python-generated HTML and vanilla JS
rather than introducing a second React build chain. The HTTP boundary uses the
standard library, preserving the zero-mandatory-dependency offline core. The
optional MCP adapter uses the official SDK pinned separately.

This is a **local, single-user refund-domain application**, not a hosted SaaS.
It has no login, remote hosting, background jobs or interactive label editor.
It deliberately does not create provider calls, mutate refunds, fix tools, or
write uploads into the frozen benchmark. Unsupported language may be uncheckable.

The server binds only to loopback; Host/Origin checks reject cross-site access.
JSON requests are capped at 2 MiB, nesting at 40 levels and ledgers at 2,000
events. Unknown schema fields, duplicate keys and invalid types are rejected.
Frozen reads use allow-listed case IDs, never caller-supplied filesystem paths.
No request bodies are logged. Do not expose this development server through a
tunnel or bind it publicly: production deployment needs a separate security design.

Hash integrity is not source authenticity: a party able to fabricate an entire
ledger can also seal it. Trust the source separately from the audit verdict.
Host-specific installation and Manus compatibility are not established by the
local stdio smoke test. Marketplace publishing remains separate work.

## Metadata follow-up

The historical `LICENSE` and package author metadata name Fatma Ramadan while
the competition disclosure names Ibrahiem Mohamed. Ownership/provenance needs
clarification before publishing a new package or plugin; integration preserves
the existing notice rather than silently replacing a copyright holder.
