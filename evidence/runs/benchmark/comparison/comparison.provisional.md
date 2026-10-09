# ProofTrail provisional benchmark diagnostic

> **PROVISIONAL DIAGNOSTIC ONLY: labels are ledger-derived and have not been approved by a human reviewer; no metric in this file is headline eligible.**

- Dataset: **40 cases / 10 families**
- B1 repeats: **3**
- Headline eligible: **no**

## Outcome

| Auditor / ablation | Family-mean accuracy | Overall accuracy | Macro-F1 | First-bad hit rate | Evidence coverage |
|---|---:|---:|---:|---:|---:|
| B1 all-LLM (3-run mean ± population SD) | 85.0% ± 2.0% | 85.0% ± 2.0% | 86.5% ± 1.4% | 66.7% ± 7.8% | 86.1% ± 1.1% |
| ProofTrail without temporal verifier | 100.0% | 100.0% | 100.0% | 100.0% | 81.5% |
| ProofTrail full | 100.0% | 100.0% | 100.0% | 100.0% | 81.5% |

## Cost and repeat stability

- Accepted B1 completions: **120** (891,687 input / 190,214 output tokens).
- Billed Free Tier cost: **$0.00**; list-price equivalent: **$0.5082** (**$0.004235 per prediction**).
- B1 verdict unanimity: **87.5%** (35/40 cases).
- ProofTrail model calls and billed cost: **0 / $0.00**.

## Failure analysis

- B1 wrong in all three runs: **4** case(s): F04-s00, F04-s01, F04-s02, F04-s03.
- B1 changed verdict across repeats: **5** case(s): F06-s00, F06-s01, F06-s03, F07-s02, F07-s03.
- ProofTrail verdict differs from the selected truth source: **0** case(s): none.
- Removing temporal verification changed verdict or first-bad localization in **0** case(s).

## Reproducibility boundary

Every B1 run row in the JSON report carries its spec hash plus hashes of the exact spec, outputs, failures and summary artifacts. The report command performs no network calls. Re-running it without `--allow-provisional` fails closed until all 40 source-bound human decisions are accepted.
