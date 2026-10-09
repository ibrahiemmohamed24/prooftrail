import copy
import json

import pytest

from prooftrail import application as app


@pytest.mark.parametrize("case_id", app.list_frozen_cases())
def test_uploaded_frozen_evidence_matches_original_certificate(case_id):
    payload = app.get_case(case_id)
    original = copy.deepcopy(payload)
    result = app.audit_evidence(payload)
    expected = app.get_evidence_certificate(case_id)
    assert result["certificate"] == expected
    assert result["persisted"] is False
    assert result["model_calls"] == 0
    assert payload == original


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"x":NaN}', b'{"x":1e999}', b'not-json', b'\xff'])
def test_invalid_json(raw):
    with pytest.raises(app.InvalidEvidence):
        app.decode_json(raw)


def test_unknown_fields_types_and_empty_ledger_rejected():
    for change in (lambda p: p.update(labels={}),
                   lambda p: p["trace"].update(final_report=123),
                   lambda p: p["ledger"][0].update(seq=True),
                   lambda p: p.update(ledger=[]),
                   lambda p: p["ledger"][0].update(hash="")):
        payload = app.get_case("F02-s00")
        change(payload)
        with pytest.raises(app.InvalidEvidence):
            app.audit_evidence(payload)


def test_tampered_chain_yields_unverifiable_not_a_trusted_verdict():
    payload = app.get_case("F02-s00")
    payload["ledger"][0]["hash"] = "f" * 64
    result = app.audit_evidence(payload)
    assert result["ledger"]["valid"] is False
    assert result["audit"]["verdict"] == "UNVERIFIABLE"


@pytest.mark.parametrize("case_id", ["../../.env", "F99-s00", "F02-s00/../labels"])
def test_case_path_allowlist(case_id):
    with pytest.raises(KeyError):
        app.get_case(case_id)
    with pytest.raises(KeyError):
        app.get_evidence_certificate(case_id)


def test_depth_and_size_limits():
    with pytest.raises(app.InvalidEvidence):
        app.decode_json(b" " * (app.MAX_BYTES + 1))
    with pytest.raises(app.InvalidEvidence):
        app.decode_json(("[" * 42 + "0" + "]" * 42).encode())
