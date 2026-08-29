"""Scenario families and instance generation.

* ``families``     - the 10 pressure conditions we put the refund agent under
* ``generator``    - family x seed -> concrete environment + requests
* ``ground_truth`` - ledger -> hidden labels, never read by auditors
* ``prooftrail.freeze`` - run the real agent once, write data/frozen/<case>/ (top-level module)
"""
from .families import FAMILIES, FAMILY_IDS, ScenarioFamily, get_family
from .generator import GeneratedScenario, UserRequest, generate_scenario
from .ground_truth import derive_ledger_facts, propose_ground_truth

__all__ = [
    "FAMILIES",
    "FAMILY_IDS",
    "ScenarioFamily",
    "get_family",
    "GeneratedScenario",
    "UserRequest",
    "generate_scenario",
    "derive_ledger_facts",
    "propose_ground_truth",
]
