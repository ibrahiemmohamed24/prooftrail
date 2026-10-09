import copy

import pytest

from prooftrail.github.contract import ContractError, parse_request
from prooftrail.github.examples import scenario_packs

BASE_REQUEST = scenario_packs()[0]["request"]


def _with(**changes):
    request = copy.deepcopy(BASE_REQUEST)
    request.update(changes)
    return request


def test_valid_request_round_trips_to_the_same_dictionary():
    parsed = parse_request(BASE_REQUEST)
    assert parsed.repository.full_name == "example-owner/example-repo"
    assert parsed.pull_request == 4
    assert parsed.to_dict() == BASE_REQUEST


@pytest.mark.parametrize("change", [
    {"schema_version": "1"}, {"schema_version": True}, {"schema_version": 2},
    {"domain": "refund"}, {"unexpected": 1},
    {"pull_request": True}, {"pull_request": 0}, {"pull_request": -1}, {"pull_request": 2 ** 40},
    {"pull_request": "4"},
    {"expected_head_sha": "A" * 40}, {"expected_head_sha": "abc"}, {"expected_head_sha": "g" * 40},
    {"expected_base_branch": "../main"}, {"expected_base_branch": "-main"}, {"expected_base_branch": "main/"},
    {"expected_base_branch": "main.lock"}, {"expected_base_branch": "feat//x"}, {"expected_base_branch": ""},
    {"expected_base_branch": "https://github.com/x/y"},
    {"required_checks": []}, {"required_checks": ["replay", "replay"]}, {"required_checks": [" replay"]},
    {"required_checks": ["replay\n"]}, {"required_checks": [""]}, {"required_checks": ["x" * 201]},
    {"required_checks": ["check-%d" % index for index in range(21)]},
    {"claims": []}, {"claims": [{"id": "c1", "type": "pr_exists"}, {"id": "c1", "type": "base_branch"}]},
    {"claims": [{"id": "c1", "type": "refund_issued"}]},
    {"claims": [{"id": "c1", "type": "pr_exists", "url": "https://evil.example"}]},
    {"claims": [{"id": "../c", "type": "pr_exists"}]},
])
def test_invalid_requests_are_rejected(change):
    with pytest.raises(ContractError):
        parse_request(_with(**change))


@pytest.mark.parametrize("repository", [
    {"owner": "https://github.com/x", "name": "y"}, {"owner": "x/y", "name": "z"},
    {"owner": "-bad", "name": "z"}, {"owner": "x", "name": ".."}, {"owner": "x", "name": "a b"},
    {"owner": "x", "name": ""}, {"owner": "x"}, {"owner": "x", "name": "y", "host": "evil.example"},
])
def test_invalid_repository_identifiers_are_rejected(repository):
    with pytest.raises(ContractError):
        parse_request(_with(repository=repository))


def test_unsupported_claim_types_are_accepted_so_they_can_be_classified_explicitly():
    parsed = parse_request(_with(claims=[{"id": "d1", "type": "production_deployment"},
                                         {"id": "t1", "type": "all_tests_passed"}]))
    assert [claim.claim_type for claim in parsed.claims] == ["production_deployment", "all_tests_passed"]
