"""Spend ceiling for live model calls.

Every live completion is authorised *before* the request is sent, using a
conservative estimate, and recorded *after* it returns, using the provider's
real token counts. Spend is persisted to an append-only JSONL cost ledger so
the ceiling holds across processes and sessions, not just within one run.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ..config import COST_LEDGER_PATH, cost_usd

BUDGET_ENV = "PROOFTRAIL_BUDGET_USD"
DEFAULT_BUDGET_USD = 30.0

# Conservative pre-call estimate: ~3 characters per input token, and the full
# output cap is assumed to be used. Overestimating keeps the guard honest.
_CHARS_PER_INPUT_TOKEN = 3


class BudgetExceededError(RuntimeError):
    """Raised before a live call that could push cumulative spend past the cap."""


class CostLedger:
    """Append-only JSONL file of every live model call and its real cost."""

    def __init__(self, path: str | Path = COST_LEDGER_PATH):
        self.path = Path(path)

    def entries(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows

    def total_spent(self) -> float:
        return round(sum(float(row.get("cost_usd", 0.0)) for row in self.entries()), 6)

    def append(self, entry: Mapping[str, Any]) -> dict[str, Any]:
        row = dict(entry)
        row.setdefault("ts", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        row["cumulative_usd"] = round(self.total_spent() + float(row.get("cost_usd", 0.0)), 6)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
        return row


class BudgetGuard:
    """Refuse any live call whose worst-case cost would exceed the ceiling."""

    def __init__(self, limit_usd: float, ledger: CostLedger | None = None):
        if limit_usd <= 0:
            raise ValueError("budget limit must be a positive number of USD")
        self.limit_usd = float(limit_usd)
        self.ledger = ledger or CostLedger()

    @classmethod
    def from_env(
        cls,
        *,
        limit_usd: float | None = None,
        ledger_path: str | Path = COST_LEDGER_PATH,
    ) -> "BudgetGuard":
        if limit_usd is None:
            raw = os.environ.get(BUDGET_ENV, "").strip()
            limit_usd = float(raw) if raw else DEFAULT_BUDGET_USD
        return cls(limit_usd, CostLedger(ledger_path))

    @property
    def spent_usd(self) -> float:
        return self.ledger.total_spent()

    @property
    def remaining_usd(self) -> float:
        return round(self.limit_usd - self.spent_usd, 6)

    @staticmethod
    def estimate_call_cost(model: str, *, prompt_chars: int, max_output_tokens: int) -> float:
        estimated_input = max(1, prompt_chars // _CHARS_PER_INPUT_TOKEN)
        return cost_usd(model, estimated_input, max_output_tokens)

    def authorize(self, estimated_cost_usd: float, *, description: str = "") -> None:
        spent = self.spent_usd
        projected = round(spent + estimated_cost_usd, 6)
        if projected > self.limit_usd:
            label = f" {description}" if description else ""
            raise BudgetExceededError(
                f"refusing live call{label}: spent ${spent:.4f} + worst-case "
                f"${estimated_cost_usd:.4f} would exceed {BUDGET_ENV}=${self.limit_usd:.2f} "
                f"(ledger: {self.ledger.path})"
            )

    def record(
        self,
        *,
        model: str,
        label: str,
        usage: Mapping[str, Any],
        prompt_sha256: str,
        response_id: str | None = None,
    ) -> dict[str, Any]:
        entry = {
            "model": model,
            "label": label,
            "prompt_sha256": prompt_sha256,
            "response_id": response_id,
            "input_tokens": int(usage.get("input_tokens", 0)),
            "output_tokens": int(usage.get("output_tokens", 0)),
            "cache_read_input_tokens": int(usage.get("cache_read_input_tokens", 0)),
            "cache_creation_input_tokens": int(usage.get("cache_creation_input_tokens", 0)),
            "cost_usd": round(float(usage.get("cost_usd", 0.0)), 6),
        }
        return self.ledger.append(entry)


__all__ = [
    "BUDGET_ENV",
    "BudgetExceededError",
    "BudgetGuard",
    "CostLedger",
    "DEFAULT_BUDGET_USD",
]
