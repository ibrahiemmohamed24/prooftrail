from __future__ import annotations

import pytest

from prooftrail.scenarios import FAMILY_IDS, generate_scenario
from prooftrail.schemas import EventType


def test_seed_zero_is_the_47_dollar_killer_case():
    scenario = generate_scenario("F02", 0)
    try:
        assert scenario.seeded.orders[0]["amount_cents"] == 4700
        assert "$47.00" in scenario.user_requests[0].text
        assert scenario.seeded.orders[0]["order_id"] in scenario.user_requests[0].text
        assert "f02" not in scenario.seeded.orders[0]["order_id"].lower()
        assert "f02" not in scenario.seeded.customer["customer_id"].lower()
    finally:
        scenario.close()


def test_generation_is_byte_stable_at_the_metadata_level():
    first = generate_scenario("F06", 3)
    second = generate_scenario("F06", 3)
    try:
        assert first.metadata() == second.metadata()
        assert first.seeded.to_dict() == second.seeded.to_dict()
    finally:
        first.close()
        second.close()


def test_all_40_family_seed_instances_are_unique_and_valid():
    case_ids = set()
    for family_id in FAMILY_IDS:
        for seed in range(4):
            scenario = generate_scenario(family_id, seed)
            try:
                assert scenario.case_id not in case_ids
                case_ids.add(scenario.case_id)
                assert scenario.user_requests
                assert len(scenario.seeded.orders) == scenario.family.n_orders
                assert scenario.ledger.events() == []
            finally:
                scenario.close()
    assert len(case_ids) == 40


def test_two_request_family_has_distinct_intents():
    scenario = generate_scenario("F07", 0)
    try:
        assert len(scenario.user_requests) == 2
        assert scenario.user_requests[0].intent_id != scenario.user_requests[1].intent_id
        assert scenario.seeded.orders[0]["order_id"] in scenario.user_requests[0].text
        assert scenario.seeded.orders[1]["order_id"] in scenario.user_requests[1].text
    finally:
        scenario.close()


def test_user_intent_is_recorded_at_delivery_time_once():
    scenario = generate_scenario("F01", 0)
    try:
        assert scenario.ledger.events() == []
        event = scenario.record_user_intent(0)
        assert event.event_type == EventType.USER_INTENT
        assert event.intent_id == scenario.user_requests[0].intent_id
        with pytest.raises(ValueError, match="already recorded"):
            scenario.record_user_intent(0)
    finally:
        scenario.close()


def test_negative_seed_is_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        generate_scenario("F01", -1)
