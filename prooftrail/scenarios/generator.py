"""Build a runnable, deterministic environment for one scenario instance."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..env.clock import SimClock
from ..env.database import StateDB
from ..env.faults import FaultInjector
from ..env.ledger import Ledger
from ..env.seed_data import SeededEnvironment, seed_environment
from ..env.tools import RefundTool
from ..ids import intent_id as make_intent_id
from ..schemas.events import LedgerEvent
from .families import ScenarioFamily, get_family


@dataclass(frozen=True)
class UserRequest:
    intent_id: str
    text: str

    def to_dict(self) -> dict[str, str]:
        return {"intent_id": self.intent_id, "text": self.text}


@dataclass
class GeneratedScenario:
    case_id: str
    family: ScenarioFamily
    seed: int
    db: StateDB
    clock: SimClock
    ledger: Ledger
    tools: RefundTool
    seeded: SeededEnvironment
    user_requests: tuple[UserRequest, ...]
    _recorded_intents: set[str] = field(default_factory=set, init=False, repr=False)

    def record_user_intent(self, ordinal: int) -> LedgerEvent:
        """Put one user request on the ledger when the agent receives it."""
        request = self.user_requests[ordinal]
        if request.intent_id in self._recorded_intents:
            raise ValueError(f"intent {request.intent_id} was already recorded")
        self._recorded_intents.add(request.intent_id)
        return self.ledger.user_intent(request.intent_id, request.text)

    def metadata(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "family_id": self.family.family_id,
            "seed": self.seed,
            "seeded": self.seeded.to_dict(),
            "user_requests": [request.to_dict() for request in self.user_requests],
            "idempotency_enabled": self.family.idempotency_enabled,
        }

    def close(self) -> None:
        self.db.close()


def generate_scenario(
    family: str | ScenarioFamily,
    seed: int,
    *,
    db_path: str | Path = ":memory:",
) -> GeneratedScenario:
    family_obj = get_family(family) if isinstance(family, str) else family
    db = StateDB(db_path).init_schema()
    try:
        clock = SimClock()
        seeded = seed_environment(db, family_obj, seed)
        ledger = Ledger(db, clock, seeded.case_id)
        faults = FaultInjector(list(family_obj.faults))
        tools = RefundTool(
            db,
            ledger,
            faults,
            idempotency_enabled=family_obj.idempotency_enabled,
        )
        requests = tuple(
            UserRequest(
                make_intent_id(seeded.case_id, ordinal),
                template.format(**seeded.template_values),
            )
            for ordinal, template in enumerate(family_obj.user_request_templates)
        )
        return GeneratedScenario(
            seeded.case_id,
            family_obj,
            seed,
            db,
            clock,
            ledger,
            tools,
            seeded,
            requests,
        )
    except Exception:
        db.close()
        raise


__all__ = ["GeneratedScenario", "UserRequest", "generate_scenario"]
