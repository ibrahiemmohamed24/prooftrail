"""ProofTrail — evidence-linked auditing of agent action claims.

Three words drive every design decision in this package:

* **same evidence**    — the baseline auditors (B0/B1) and ProofTrail read the
  exact same frozen trace and the exact same raw ledger. Nothing is hidden from
  the baseline that ProofTrail can see.
* **independent truth** — ground truth is derived from the append-only ledger,
  never from what any model says.
* **frozen traces**    — the real LLM refund agent runs once at data-creation
  time; every evaluation afterwards replays the recorded traces.
"""

__version__ = "0.1.0"
