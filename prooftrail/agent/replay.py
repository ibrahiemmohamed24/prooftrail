"""Stable JSON persistence for traces and scripted offline responses."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

from ..schemas import AgentTrace
from .interfaces import ModelResponse


def save_agent_trace(trace: AgentTrace, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(trace.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return target


def load_agent_trace(path: str | Path) -> AgentTrace:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return AgentTrace.from_dict(raw)


def save_scripted_responses(responses: Sequence[ModelResponse], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps([r.to_dict() for r in responses], indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return target


def load_scripted_responses(path: str | Path) -> tuple[ModelResponse, ...]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("scripted response file must contain a JSON list")
    return tuple(ModelResponse.from_dict(item) for item in raw)
