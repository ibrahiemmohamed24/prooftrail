import http.client
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from prooftrail import application as app
from prooftrail.web import make_handler


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


def request(port, method, path, body=None, headers=None):
    client = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    client.request(method, path, body, headers or {})
    response = client.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    client.close()
    return result


@pytest.mark.parametrize("path", ["/", "/audit.html", "/benchmark.html", "/integrations.html", "/assets/control-room.js",
                                      "/api/v1/health", "/api/v1/overview", "/api/v1/cases", "/api/v1/benchmark",
                                      "/api/v1/cases/F02-s00", "/api/v1/cases/F02-s00/certificate", "/certificates/F02-s00.md"])
def test_routes(server, path):
    status, headers, body = request(server, "GET", path)
    assert status == 200
    assert body
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "Access-Control-Allow-Origin" not in headers


def test_real_audit(server):
    status, _, raw = request(server, "POST", "/api/v1/audits", json.dumps(app.get_case("F02-s00")), {"Content-Type": "application/json"})
    assert status == 200
    assert json.loads(raw)["certificate"] == app.get_evidence_certificate("F02-s00")


@pytest.mark.parametrize("headers", [{"Host": "evil.example"}, {"Origin": "https://evil.example"}, {"Sec-Fetch-Site": "cross-site"}])
def test_origin_and_host_rejected(server, headers):
    assert request(server, "GET", "/api/v1/cases", headers=headers)[0] == 403


def test_bad_requests(server):
    assert request(server, "GET", "/../../.env")[0] == 404
    assert request(server, "GET", "/api/v1/cases/../../.env")[0] == 404
    assert request(server, "POST", "/api/v1/audits", "{}")[0] == 415
    assert request(server, "POST", "/api/v1/audits", "{", {"Content-Type": "application/json"})[0] == 422
    assert request(server, "POST", "/api/v1/audits", "{}", {"Content-Type": "application/json", "Content-Length": str(app.MAX_BYTES + 1)})[0] == 413
    assert request(server, "POST", "/api/v1/ledgers/verify", json.dumps({"ledger": app.get_case("F02-s00")["ledger"]}), {"Content-Type": "application/json"})[0] == 200
