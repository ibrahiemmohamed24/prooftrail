from pathlib import Path

import pytest

from prooftrail.config import PROJECT_ROOT
from prooftrail.github.examples import list_packs, load_pack, scenario_packs, write_synthetic_packs

COMMITTED = PROJECT_ROOT / "examples" / "github"


def test_committed_examples_match_the_generator_byte_for_byte(tmp_path):
    write_synthetic_packs(tmp_path)
    generated = sorted(path.name for path in tmp_path.glob("*.json"))
    committed = sorted(path.name for path in COMMITTED.glob("*.json") if not path.name.startswith("live-capture-"))
    assert generated == committed
    for name in generated:
        assert (tmp_path / name).read_bytes() == (COMMITTED / name).read_bytes(), name


def test_every_synthetic_pack_is_labelled_as_a_fixture():
    for pack in scenario_packs():
        assert pack["synthetic"] is True
        assert "Not production evidence" in pack["note"]
        assert pack["bundle"]["provenance"]["synthetic"] is True
        assert pack["bundle"]["provenance"]["kind"] == "synthetic_fixture"


def test_listing_is_the_allow_list_and_hostile_identifiers_are_refused():
    identifiers = {item["id"] for item in list_packs(COMMITTED)}
    assert "synthetic-correct-open-pr" in identifiers
    for hostile in ("../secret", "..", "synthetic-correct-open-pr/../x", "missing"):
        with pytest.raises(KeyError):
            load_pack(COMMITTED, hostile)


def test_loading_a_pack_returns_its_expected_block_only_for_tests():
    pack = load_pack(COMMITTED, "synthetic-merged-pr")
    assert pack["expected"]["verdict"] == "SUPPORTED"
    assert Path(COMMITTED / "synthetic-merged-pr.json").is_file()
