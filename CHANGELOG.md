# Improvement Changelog

| Iteration | Date | Change | Evidence | Decision |
|---:|---|---|---|---|
| 0 | 2026-08-28 | Foundation schemas, identities, SQLite state, ledger, faults and ten families | 40 foundation tests | Continue: architecture viable, no end-to-end path yet |
| 1 | 2026-08-28 | Added atomic tools, deterministic cases and F02/F10 controls | Tool/fault integration tests | Keep independent ledger snapshots; timeout alone is not labelled harmful |
| 2 | 2026-08-28 | Added provider-neutral agent loop and explicit offline retry fixture | Trace proves two distinct calls under one intent | Keep real LLM outside deterministic smoke test; freeze it later |
| 3 | 2026-08-28 | Added hybrid auditor and evidence certificates | F02: `CONTRADICTED`, first bad event `#6` | Keep language extraction replaceable; keep reconciliation deterministic |
| 4 | 2026-08-28 | Added fair B1 contract, metrics, CLI and reproduction path | 98 tests; zero-key CLI demo | Do not publish headline delta until real frozen data and human labels exist |
| 5 | 2026-08-29 | Routed pytest temp files away from inaccessible `C:\\SADP_Temp` and disabled its unwritable cache | `python -m pytest` passed twice: 98/98 | Keep the default test command portable on managed Windows machines |
