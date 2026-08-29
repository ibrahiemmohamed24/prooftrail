import pytest

from prooftrail.scenarios import FAMILIES, FAMILY_IDS, get_family
from prooftrail.scenarios.families import ALL_TOOLS, LEDGERED_TOOLS, UNLEDGERED_TOOLS
from prooftrail.schemas import STATUSES


def test_ten_families_with_unique_ids():
    assert len(FAMILIES) == 10
    assert len(set(FAMILY_IDS)) == 10
    assert FAMILY_IDS == tuple(f"F{i:02d}" for i in range(1, 11))


def test_every_family_is_well_formed():
    for f in FAMILIES:
        assert f.expected_verdict in STATUSES
        assert f.user_request_templates, f.family_id
        assert f.one_line and f.what_it_tests, f.family_id
        assert f.difficulty in ("easy", "medium", "hard"), f.family_id
        for fault in f.faults:
            assert fault.tool in ALL_TOOLS


def test_expected_verdict_mix_is_balanced_enough():
    """A benchmark where every case is CONTRADICTED can be solved by 'always say no'."""
    verdicts = [f.expected_verdict for f in FAMILIES]
    assert verdicts.count("SUPPORTED") >= 3
    assert verdicts.count("CONTRADICTED") >= 3
    assert verdicts.count("UNVERIFIABLE") >= 1


def test_killer_scenario_and_its_controls():
    f02 = get_family("F02")
    f03 = get_family("F03")
    f10 = get_family("F10")
    assert not f02.idempotency_enabled and f10.idempotency_enabled
    assert f02.faults[0].kind == f10.faults[0].kind == "timeout_after_commit"
    assert f03.faults[0].kind == "timeout_before_commit"
    assert f02.expected_verdict == "CONTRADICTED"
    assert f03.expected_verdict == f10.expected_verdict == "SUPPORTED"


def test_two_order_families_declare_two_orders():
    for fid in ("F06", "F07"):
        assert get_family(fid).n_orders == 2
    assert len(get_family("F07").user_request_templates) == 2


def test_unledgered_tool_family_exists():
    assert "send_email" in UNLEDGERED_TOOLS and "send_email" not in LEDGERED_TOOLS
    assert get_family("F09").expected_verdict == "UNVERIFIABLE"
    assert "email" in get_family("F09").user_request_templates[0].lower()


def test_get_family_unknown():
    with pytest.raises(KeyError):
        get_family("F99")
