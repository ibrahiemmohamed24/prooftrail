"""Deterministic simulated clock.

Real wall-clock time would make ledger hashes differ between runs and between
machines, which would break "frozen traces". Every event instead gets a
timestamp from this clock, which advances by a fixed step per tick.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..config import SIM_CLOCK_START, SIM_CLOCK_STEP_SECONDS


class SimClock:
    def __init__(self, start: str = SIM_CLOCK_START, step_seconds: int = SIM_CLOCK_STEP_SECONDS):
        self._t = datetime.fromisoformat(start).astimezone(timezone.utc)
        self._step = timedelta(seconds=step_seconds)
        self.ticks = 0

    def now(self) -> str:
        return self._t.isoformat()

    def tick(self, n: int = 1) -> str:
        """Advance ``n`` steps and return the new time."""
        self._t += self._step * n
        self.ticks += n
        return self.now()

    def jump(self, seconds: int) -> str:
        """Simulate a delay (e.g. a network timeout window)."""
        self._t += timedelta(seconds=seconds)
        return self.now()
