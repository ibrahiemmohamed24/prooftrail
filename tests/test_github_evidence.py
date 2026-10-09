import copy
import json

import pytest

from prooftrail.github.contract import ContractError
from prooftrail.github.evidence import bundle_sha256, load_bundle
from prooftrail.github.examples import scenario_packs

BUNDLE = scenario_packs()[0]["bundle"]


def _mutated(mutator):
    bundle = copy.deepcopy(BUNDLE)
    mutator(bundle)
    return bundle


def test_bundle_round_trips_without_loss():
    assert load_bundle(BUNDLE).to_bundle() == BUNDLE


def test_hash_ignores_key_order_and_detects_any_change():
    reordered = dict(reversed(list(BUNDLE.items())))
    assert bundle_sha256(reordered) == bundle_sha256(BUNDLE)
    changed = _mutated(lambda bundle: bundle["pull_request"]["head"].update(sha="d" * 40))
    assert bundle_sha256(changed) != bundle_sha256(BUNDLE)
    assert len(bundle_sha256(BUNDLE)) == 64
    assert bundle_sha256(json.loads(json.dumps(BUNDLE))) == bundle_sha256(BUNDLE)


@pytest.mark.parametrize("mutator", [
    lambda bundle: bundle.update(bundle_schema_version=2),
    lambda bundle: bundle.update(extra=1),
    lambda bundle: bundle.pop("observations"),
    lambda bundle: bundle["provenance"].update(synthetic=False),
    lambda bundle: bundle["provenance"].update(fixture_note=""),
    lambda bundle: bundle["provenance"].update(kind="unknown"),
    lambda bundle: bundle["provenance"].update(kind="offline_bundle"),
    lambda bundle: bundle["check_runs"][0].update(head_sha="xyz"),
    lambda bundle: bundle["check_runs"][0].update(status=None),
    lambda bundle: bundle["check_runs"][0].update(unexpected="field"),
    lambda bundle: bundle.update(check_runs=[copy.deepcopy(bundle["check_runs"][0])] * 501),
    lambda bundle: bundle["observations"][0].update(status="maybe"),
    lambda bundle: bundle["observations"][0].update(name="other"),
    lambda bundle: bundle["pull_request"].update(number=0),
    lambda bundle: bundle["pull_request"]["base"].update(extra=1),
    lambda bundle: bundle["repository"].update(full_name="no-slash"),
])
def test_malformed_bundles_are_rejected(mutator):
    with pytest.raises(ContractError):
        load_bundle(_mutated(mutator))


def test_saved_live_captures_are_not_labelled_synthetic():
    captured = _mutated(lambda bundle: bundle["provenance"].update(
        kind="saved_live_capture", synthetic=False, fixture_note=None))
    snapshot = load_bundle(captured)
    assert snapshot.provenance.synthetic is False
    assert snapshot.provenance.kind == "saved_live_capture"
