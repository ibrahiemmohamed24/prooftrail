"""Small offline runner shared by the CLI and reproducibility scripts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping, Protocol

from ..schemas.trace import FrozenCase
from ..schemas.verdict import AuditOutput, GroundTruth
from .metrics import evaluate_outputs


class Auditor(Protocol):
    name: str

    def audit(self, case: FrozenCase) -> AuditOutput: ...


def run_auditor(cases: Iterable[FrozenCase], auditor: Auditor) -> dict[str, AuditOutput]:
    outputs: dict[str, AuditOutput] = {}
    for case in cases:
        if case.case_id in outputs:
            raise ValueError(f"duplicate case_id {case.case_id}")
        output = auditor.audit(case)
        if output.case_id != case.case_id:
            raise ValueError(
                f"auditor returned case_id {output.case_id!r} for {case.case_id!r}"
            )
        outputs[case.case_id] = output
    return outputs


def run_and_score(
    cases: Iterable[FrozenCase],
    truths: Mapping[str, GroundTruth],
    auditor: Auditor,
    *,
    include_unverified: bool = False,
) -> tuple[dict[str, AuditOutput], dict[str, object]]:
    outputs = run_auditor(cases, auditor)
    return outputs, evaluate_outputs(
        outputs, truths, include_unverified=include_unverified
    )


def write_outputs(path: str | Path, outputs: Mapping[str, AuditOutput]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            {case_id: output.to_dict() for case_id, output in sorted(outputs.items())},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return destination
