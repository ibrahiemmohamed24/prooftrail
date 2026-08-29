"""Shared fixtures: an in-memory environment per test."""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from prooftrail.env import Ledger, SimClock, StateDB


def pytest_configure(config) -> None:
    """Keep pytest away from a broken or locked system TEMP directory.

    Some managed Windows machines point TEMP at ``C:\\SADP_Temp`` even when
    the current user cannot read it. A unique project-local base also prevents
    pytest from trying to delete a stale directory left by another process.
    An explicit command-line ``--basetemp`` still takes precedence.
    """

    if config.option.basetemp is None:
        project_root = Path(__file__).resolve().parents[1]
        run_id = f"run-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        temp_root = project_root / ".test-runs"
        temp_root.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = str(temp_root / run_id)


@pytest.fixture
def db() -> StateDB:
    d = StateDB(":memory:").init_schema()
    d.insert_customer("cus_a", "Amina Hassan", "amina@example.com")
    d.insert_order("ord_1", "cus_a", 8400, "2026-08-20T10:00:00+00:00")
    d.insert_order("ord_2", "cus_a", 2500, "2026-08-21T10:00:00+00:00")
    yield d
    d.close()


@pytest.fixture
def clock() -> SimClock:
    return SimClock()


@pytest.fixture
def ledger(db: StateDB, clock: SimClock) -> Ledger:
    return Ledger(db, clock, case_id="TEST-s00")
