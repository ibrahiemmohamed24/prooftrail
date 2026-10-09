# Control room validation — 2026-10-09

Local branch: `feat/control-room-app`. This is validation of the local
refund-domain application, not a claim of production or marketplace readiness.

## Automated evidence

- Full suite: **291 passed**, including the optional MCP adapter.
- All 40 uploaded frozen inputs reproduce the original certificates exactly;
  application calls leave their input objects unchanged and persist nothing.
- Real HTTP requests cover page/API routes, audit results and certificate reads.
  Tests reject invalid types, duplicate keys, non-finite JSON, unknown fields,
  oversized/deep input, empty/unsealed ledgers, tampered hash chains, arbitrary
  case paths and cross-origin access.
- A real stdio MCP subprocess is initialized by the official SDK client;
  six tools are discovered, marked read-only, and a recorded case is audited
  with an exact certificate match. Invalid case paths return a tool error.
- Both JavaScript files pass `node --check`.
- Skill Creator's validator reports `Skill is valid!`.
- `pip check`: no broken requirements. Credential-pattern scan passes.
- Static build: **176 files**, including local fonts, original certificates,
  separate audit/benchmark/integration pages and comparison JSON.
- Human truth remains **40/40 accepted**. Verified comparison remains ProofTrail
  100% versus B1 85% mean over three runs. `git diff --exit-code -- data evidence`
  confirms no tracked benchmark input, review or result changes.

## Browser checks

- Actual example loading and POST audit produce CONTRADICTED for F04-s00,
  with verbatim claim, evidence sequence 5 and downloadable JSON/Markdown.
- Empty evidence produces a validation message rather than a successful verdict.
- Searching F04 and descending sort show 4/40; URL state survives reload.
- First-bad-event filter shows 16/40.
- Desktop 1440, phone 390 and tablet 1024 checks show no horizontal page
  overflow on inspected pages. Mobile filters open as a usable dialog.
- No captured browser console errors on the tested integration page.

## Explicitly not attested

Host installation in Codex/Claude/Manus, real customer-data ingestion, remote
hosting, authorization for multiple users, calibrated confidence, general-domain
claim extraction and marketplace publication are not validated. Copyright and
package author metadata remain unchanged pending the owner's clarification.
