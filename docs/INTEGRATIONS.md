# Local integrations

The shared read-only application interface is `prooftrail.application`; web UI,
HTTP API and MCP adapter call the same auditor and certificate builders.
No third-party provider account or API key is required to audit supplied evidence.

## Local MCP server

From this checkout, install the **optional** dependency:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[mcp]"
```

The executable entry point is `python -m prooftrail.mcp_server`, speaking stdio.
Do not start it in an ordinary terminal expecting a web page. The host launches it.
The checkout must remain available: the benchmark data is not bundled into a wheel.

Seven read-only tools are exposed: `audit_trace`, `verify_ledger`, `list_frozen_cases`,
`get_case`, `get_evidence_certificate`, `get_benchmark_summary`, and `audit_github_execution`.
`audit_trace` accepts `evidence` containing a schema-v1 trace and sealed ledger; it returns the
categorical audit, full certificate, Markdown, integrity status and limitations.
`audit_github_execution` accepts a schema-v1 GitHub `request` and a saved `bundle` and returns
per-claim verdicts and a certificate. It is offline only: it makes no network request, reads no
token, and is declared `openWorldHint: false`. Live GitHub reads are not exposed through MCP, because
sending private repository data to an assistant host is a separate data-sharing decision.
Requests do not accept arbitrary local file paths. They do not save evidence.

## Codex configuration (user-approved installation)

Use the actual absolute checkout/Python paths on your machine. Example for the
current Windows checkout, following [official MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli):

```toml
[mcp_servers.prooftrail]
command = 'E:\prooftrail\prooftrail\.venv\Scripts\python.exe'
args = ['-m', 'prooftrail.mcp_server']
cwd = 'E:\prooftrail\prooftrail'
startup_timeout_sec = 20
tool_timeout_sec = 30
```

Add this to your host's MCP configuration only after authorizing that local tool.
Do not overwrite unrelated servers or approval policies. Restart the host and ask
it to list ProofTrail's frozen cases. It should return 40 IDs. Then request
`get_case` and `audit_trace` on `F02-s00`; compare the resulting certificate with
`get_evidence_certificate`. The adapter is protocol-tested, not yet attested as
installed in every host.

## Portable skill

`integrations/skills/prooftrail-audit/SKILL.md` describes evidence handling,
limitations, tool routing and read-only safety. For Codex, install the folder
in a supported skills location using [official skill guidance](https://learn.chatgpt.com/docs/build-skills).
Do not change global host settings without the owner's approval.
This is a skill, not a marketplace plugin manifest.

## Claude and Manus

The server speaks standard local stdio MCP. Claude's current host configuration
must be checked before installing; this repository does not claim an end-to-end
Claude installation test. Manus connectivity is **not verified**. A host that
only accepts remote MCP cannot access this stdio process directly; remote
deployment would require authentication, data-handling review and explicit user
approval. Do not invent a Manus plugin format or expose a local HTTP server to
work around those requirements.

## Security and scope

Tools execute no model requests, shell commands, refunds or evidence writes.
Input text is data, never a privileged instruction. Integrity is not authenticity;
the ledger producer must be trusted independently. The current extractor is
refund-domain deterministic logic, not a general-purpose judge or a calibrated
confidence estimator. Private traces may still be visible to the assistant host;
authorize the data destination before passing real customer records to any host.

Copyright/package metadata needs owner clarification before public package or
marketplace publication; original notices remain preserved.
