import copy
import http.client
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from prooftrail import application as app
from prooftrail.github.evidence import load_bundle
from prooftrail.github.examples import scenario_packs
from prooftrail.web import make_handler

PACKS = {pack["id"]: pack for pack in scenario_packs()}
PACK = PACKS["synthetic-correct-open-pr"]


@pytest.fixture(scope="module")
def server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port = server.server_port
    server.RequestHandlerClass = make_handler(port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield port
    server.shutdown()
    server.server_close()
    thread.join()


def _request(port, method, path, body=None, headers=None):
    client = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    client.request(method, path, body, headers or {})
    response = client.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    client.close()
    return result


def test_offline_application_call_returns_verdict_certificate_and_no_network_use():
    result = app.audit_github_request({"mode": "offline", "request": PACK["request"], "bundle": PACK["bundle"]})
    assert result["verdict"] == "SUPPORTED"
    assert result["network_used"] is False
    assert result["certificate"]["source"]["synthetic"] is True


def test_uploaded_live_label_cannot_claim_runtime_network_use(monkeypatch):
    pack = copy.deepcopy(PACK)
    pack["bundle"]["provenance"].update(kind="live", synthetic=False, fixture_note=None)
    def forbidden_collect(*args, **kwargs):
        raise AssertionError("Offline evidence must never invoke the collector")
    monkeypatch.setattr(app, "collect_live", forbidden_collect)
    result = app.audit_github_request({"mode": "offline", "request": pack["request"], "bundle": pack["bundle"]})
    assert result["network_used"] is False
    assert result["certificate"]["network_used"] is False
    assert "**Network used:** no" in result["certificate_markdown"]
    assert any("does not authenticate" in warning for warning in result["warnings"])


def test_live_mode_reads_through_the_collector_and_refuses_a_bundle(monkeypatch):
    calls = []
    pack = PACKS["synthetic-merged-pr"]

    def fake_collect(request):
        calls.append(request.repository.full_name)
        return load_bundle(pack["bundle"])

    monkeypatch.setattr(app, "collect_live", fake_collect)
    result = app.audit_github_request({"mode": "live", "request": pack["request"]})
    assert calls == ["example-owner/example-repo"]
    assert result["verdict"] == "SUPPORTED"
    with pytest.raises(app.InvalidEvidence):
        app.audit_github_request({"mode": "live", "request": pack["request"], "bundle": pack["bundle"]})


@pytest.mark.parametrize("payload", [
    {"mode": "cloud", "request": PACK["request"], "bundle": PACK["bundle"]},
    {"mode": "offline", "request": PACK["request"]},
    {"mode": "offline", "request": PACK["request"], "bundle": PACK["bundle"], "token": "x"},
    {"mode": "offline", "request": {"schema_version": 1}, "bundle": PACK["bundle"]},
    {"mode": "offline", "request": PACK["request"], "bundle": {"bundle_schema_version": 1}},
    ["not", "an", "object"],
])
def test_invalid_github_requests_are_refused_before_any_audit(payload):
    with pytest.raises(app.InvalidEvidence):
        app.audit_github_request(payload)


def test_examples_hide_expected_verdicts_and_refuse_unknown_identifiers():
    listing = app.list_github_examples()
    assert listing["examples"]
    assert any(item["synthetic"] for item in listing["examples"])
    assert all(item["synthetic"] or item["id"].startswith("live-capture-") for item in listing["examples"])
    pack = app.get_github_example("synthetic-correct-open-pr")
    assert "expected" not in pack
    with pytest.raises(KeyError):
        app.get_github_example("../secret")


def test_configured_token_is_reported_as_a_boolean_only(monkeypatch):
    monkeypatch.setenv("PROOFTRAIL_GITHUB_TOKEN", "github_pat_SHOULD_NOT_APPEAR")
    listing = app.list_github_examples()
    assert listing["live_token_configured"] is True
    assert "SHOULD_NOT_APPEAR" not in json.dumps(listing)


def test_examples_are_listed_and_served_over_http(server):
    status, _, raw = _request(server, "GET", "/api/v1/github/examples")
    assert status == 200
    assert json.loads(raw)["examples"]
    status, _, raw = _request(server, "GET", "/api/v1/github/examples/synthetic-correct-open-pr")
    assert status == 200
    assert "expected" not in json.loads(raw)
    assert _request(server, "GET", "/api/v1/github/examples/..%2F..%2Fsecret")[0] == 404


def test_offline_github_audit_over_http(server):
    body = json.dumps({"mode": "offline", "request": PACK["request"], "bundle": PACK["bundle"]})
    status, headers, raw = _request(server, "POST", "/api/v1/github/audits", body,
                                    {"Content-Type": "application/json"})
    assert status == 200
    assert json.loads(raw)["verdict"] == "SUPPORTED"
    assert headers["Cache-Control"] == "no-store"


def test_live_mode_with_a_bundle_is_rejected_over_http(server):
    body = json.dumps({"mode": "live", "request": PACK["request"], "bundle": PACK["bundle"]})
    assert _request(server, "POST", "/api/v1/github/audits", body, {"Content-Type": "application/json"})[0] == 422


def test_github_endpoint_requires_json_and_the_local_origin(server):
    assert _request(server, "POST", "/api/v1/github/audits", "{}")[0] == 415
    headers = {"Content-Type": "application/json", "Origin": "https://evil.example"}
    assert _request(server, "POST", "/api/v1/github/audits", "{}", headers)[0] == 403
