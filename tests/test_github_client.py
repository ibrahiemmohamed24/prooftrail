import http.server
import json
import threading
import time
from urllib.parse import parse_qs, urlsplit

import pytest

from prooftrail.github import client as gh
from prooftrail.github.audit import audit as run_audit
from prooftrail.github.contract import parse_request
from prooftrail.github.examples import OWNER, REPO, scenario_packs

PACKS = {pack["id"]: pack for pack in scenario_packs()}
CLOCK = lambda: "2026-10-09T10:00:00Z"  # noqa: E731 - deterministic collection time for tests
EXPECTED = "a" * 40


def _request(pack_id):
    return parse_request(PACKS[pack_id]["request"])


def _github_pull(pull):
    base_repo, head_repo = pull["base"]["repo"], pull["head"]["repo"]
    return {
        "number": pull["number"], "state": pull["state"], "merged": pull["merged"],
        "merged_at": pull["merged_at"], "title": pull["title"], "html_url": pull["html_url"],
        "base": {"ref": pull["base"]["ref"], "repo": None if base_repo is None else {"full_name": base_repo}},
        "head": {"ref": pull["head"]["ref"], "sha": pull["head"]["sha"],
                 "repo": None if head_repo is None else {"full_name": head_repo}},
    }


def _github_run(run):
    return {"id": run["id"], "name": run["name"], "head_sha": run["head_sha"], "status": run["status"],
            "conclusion": run["conclusion"], "app": {"slug": run["producer"]}, "started_at": run["started_at"],
            "completed_at": run["completed_at"], "html_url": run["html_url"]}


def _encode(payload):
    return json.dumps(payload).encode("utf-8")


class FakeGithub:
    """Answers the collector's requests with GitHub-shaped JSON, filtered and paged like the real API."""

    def __init__(self, *, pull, runs=(), statuses=(), recheck_head=None, check_total=None,
                 pull_response=None, repo_response=None, checks_response=None):
        self.pull = pull
        self.runs = list(runs)
        self.statuses = list(statuses)
        self.recheck_head = recheck_head
        self.check_total = check_total
        self.pull_response = pull_response
        self.repo_response = repo_response
        self.checks_response = checks_response
        self.pull_calls = 0
        self.calls = []

    def __call__(self, url, headers, timeout):
        self.calls.append((url, dict(headers)))
        split = urlsplit(url)
        query = parse_qs(split.query)
        page = int(query.get("page", ["1"])[0])
        per_page = int(query.get("per_page", ["30"])[0])
        if split.path == f"/repos/{OWNER}/{REPO}":
            if self.repo_response:
                return self.repo_response
            return 200, {}, _encode({"full_name": f"{OWNER}/{REPO}", "private": False, "default_branch": "main"})
        if split.path == f"/repos/{OWNER}/{REPO}/pulls/4":
            self.pull_calls += 1
            if self.pull_response:
                return self.pull_response
            pull = json.loads(json.dumps(self.pull))
            if self.pull_calls > 1 and self.recheck_head:
                pull["head"]["sha"] = self.recheck_head
            return 200, {}, _encode(pull)
        parts = split.path.split("/")
        if len(parts) == 7 and parts[4] == "commits" and parts[6] == "check-runs":
            if self.checks_response:
                return self.checks_response
            items = [run for run in self.runs if run["head_sha"] == parts[5]]
            total = self.check_total if self.check_total is not None else len(items)
            start = (page - 1) * per_page
            return 200, {}, _encode({"total_count": total, "check_runs": items[start:start + per_page]})
        if len(parts) == 7 and parts[4] == "commits" and parts[6] == "status":
            start = (page - 1) * per_page
            return 200, {}, _encode({"total_count": len(self.statuses),
                                     "statuses": self.statuses[start:start + per_page]})
        return 404, {}, b"{}"


def fake_for(pack_id, **overrides):
    bundle = PACKS[pack_id]["bundle"]
    options = {
        "pull": _github_pull(bundle["pull_request"]) if bundle["pull_request"] else None,
        "runs": [_github_run(run) for run in bundle["check_runs"]],
        "statuses": [{"context": item["context"], "state": item["state"], "updated_at": item["updated_at"],
                      "target_url": item["target_url"]} for item in bundle["commit_statuses"]],
        "recheck_head": bundle["pull_request_recheck_head_sha"],
    }
    options.update(overrides)
    return FakeGithub(**options)


def test_live_collection_reproduces_the_correct_pr_verdicts():
    fake = fake_for("synthetic-correct-open-pr")
    request = _request("synthetic-correct-open-pr")
    snapshot = gh.collect_live(request, transport=fake, clock=CLOCK, environ={})
    result = run_audit(request, snapshot)
    assert result["verdict"] == "SUPPORTED"
    assert snapshot.provenance.kind == "live"
    assert result["network_used"] is True
    assert all(item.status == "ok" and item.complete for item in snapshot.observations)
    assert all("Authorization" not in headers for _, headers in fake.calls)


def test_token_is_sent_only_to_the_api_host_and_never_appears_in_outputs():
    secret = "github_pat_TEST_ONLY_NOT_A_REAL_TOKEN"
    fake = fake_for("synthetic-correct-open-pr")
    request = _request("synthetic-correct-open-pr")
    snapshot = gh.collect_live(request, token=secret, transport=fake, clock=CLOCK, environ={})
    result = run_audit(request, snapshot)
    assert fake.calls
    for url, headers in fake.calls:
        assert url.startswith("https://api.github.com/")
        assert headers["Authorization"] == f"Bearer {secret}"
    rendered = json.dumps(result["certificate"]) + result["certificate_markdown"] + json.dumps(snapshot.to_bundle())
    assert secret not in rendered


def test_token_comes_from_the_environment_only_when_configured():
    assert gh.token_from_environment({"PROOFTRAIL_GITHUB_TOKEN": " abc "}) == "abc"
    assert gh.token_from_environment({"GITHUB_TOKEN": "xyz"}) == "xyz"
    assert gh.token_from_environment({"PROOFTRAIL_GITHUB_TOKEN": "  "}) is None
    assert gh.token_from_environment({}) is None


def test_collector_refuses_anything_that_is_not_a_repository_path():
    collector = gh.GithubCollector(transport=fake_for("synthetic-correct-open-pr"), clock=CLOCK)
    with pytest.raises(ValueError):
        collector._get("https://evil.example/repos/x/y")
    with pytest.raises(ValueError):
        collector._get("/user")


@pytest.mark.parametrize(("status", "headers", "expected"), [
    (401, {}, "unauthorized"),
    (403, {}, "forbidden"),
    (403, {"x-ratelimit-remaining": "0"}, "rate_limited"),
    (403, {"retry-after": "60"}, "rate_limited"),
    (429, {}, "rate_limited"),
    (404, {}, "not_found"),
    (500, {}, "unavailable"),
    (302, {"location": "https://evil.example/"}, "redirect_refused"),
    (418, {}, "invalid_response"),
])
def test_http_errors_become_observations_not_exceptions(status, headers, expected):
    collector = gh.GithubCollector(transport=lambda url, request_headers, timeout: (status, headers, b"{}"), clock=CLOCK)
    assert collector._get("/repos/x/y").status == expected


def test_invalid_json_and_oversized_bodies_are_rejected():
    invalid = gh.GithubCollector(transport=lambda u, h, t: (200, {}, b"not json"), clock=CLOCK)
    assert invalid._get("/repos/x/y").status == "invalid_response"
    oversized = gh.GithubCollector(transport=lambda u, h, t: (200, {}, b'{"a": "' + b"x" * 100 + b'"}'),
                                   clock=CLOCK, max_bytes=50)
    assert oversized._get("/repos/x/y").status == "too_large"


def test_timeouts_and_connection_failures_are_reported_differently():
    def timed_out(url, headers, timeout):
        raise TimeoutError("slow")

    def unreachable(url, headers, timeout):
        raise OSError("connection refused")

    assert gh.GithubCollector(transport=timed_out, clock=CLOCK)._get("/repos/x/y").status == "timeout"
    assert gh.GithubCollector(transport=unreachable, clock=CLOCK)._get("/repos/x/y").status == "unavailable"


def test_pagination_collects_every_page_and_reports_completeness():
    runs = [{"id": 1000 + index, "name": "replay", "head_sha": EXPECTED, "status": "completed",
             "conclusion": "success", "app": {"slug": "github-actions"}} for index in range(250)]
    request = _request("synthetic-correct-open-pr")
    snapshot = gh.collect_live(request, transport=fake_for("synthetic-correct-open-pr", runs=runs),
                               clock=CLOCK, environ={})
    observation = snapshot.observation("check_runs")
    assert (observation.status, observation.complete, observation.pages) == ("ok", True, 3)
    assert len(snapshot.check_runs) == 250


def test_pagination_stops_at_the_page_limit_and_reports_incomplete_evidence():
    runs = [{"id": index, "name": "replay", "head_sha": EXPECTED, "status": "completed",
             "conclusion": "success", "app": {"slug": "github-actions"}} for index in range(500)]
    request = _request("synthetic-correct-open-pr")
    snapshot = gh.collect_live(request, transport=fake_for("synthetic-correct-open-pr", runs=runs, check_total=1000),
                               clock=CLOCK, environ={}, max_pages=5)
    observation = snapshot.observation("check_runs")
    assert (observation.status, observation.complete, observation.pages) == ("pagination_limit", False, 5)
    result = run_audit(request, snapshot)
    assert all(check["status"] == "UNVERIFIABLE" for check in result["required_checks"])
    assert all(check["reason_code"] == "incomplete_evidence" for check in result["required_checks"])


def test_rate_limited_pull_request_produces_unverifiable_claims_not_a_false_accusation():
    fake = fake_for("synthetic-correct-open-pr",
                    pull_response=(403, {"x-ratelimit-remaining": "0"}, b"{}"))
    request = _request("synthetic-correct-open-pr")
    result = run_audit(request, gh.collect_live(request, transport=fake, clock=CLOCK, environ={}))
    assert [claim["status"] for claim in result["claims"][:3]] == ["UNVERIFIABLE"] * 3
    assert result["claims"][0]["reason_code"] == "source_rate_limited"


def test_missing_repository_is_not_reported_as_a_missing_pull_request():
    fake = fake_for("synthetic-correct-open-pr", repo_response=(404, {}, b"{}"))
    request = _request("synthetic-correct-open-pr")
    result = run_audit(request, gh.collect_live(request, transport=fake, clock=CLOCK, environ={}))
    assert result["claims"][0]["status"] == "UNVERIFIABLE"
    assert result["claims"][0]["reason_code"] == "repository_not_found_or_inaccessible"


def test_deadline_turns_later_requests_into_timeouts():
    now = {"t": 0.0}
    calls = []

    def slow_transport(url, headers, timeout):
        calls.append(url)
        now["t"] += 100.0
        return 200, {}, _encode({"full_name": f"{OWNER}/{REPO}", "private": False, "default_branch": "main"})

    collector = gh.GithubCollector(transport=slow_transport, clock=CLOCK, deadline=20.0,
                                   monotonic=lambda: now["t"])
    snapshot = collector.collect(_request("synthetic-correct-open-pr"))
    assert len(calls) == 1
    assert all(item.status == "timeout" for item in snapshot.observations[1:])


def test_collection_reads_the_pull_request_again_to_detect_head_changes():
    fake = fake_for("synthetic-correct-open-pr", recheck_head="b" * 40)
    request = _request("synthetic-correct-open-pr")
    snapshot = gh.collect_live(request, transport=fake, clock=CLOCK, environ={})
    assert fake.pull_calls == 2
    result = run_audit(request, snapshot)
    assert result["claims"][2]["reason_code"] == "head_changed_during_collection"


def _serve(handler_class):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_redirects_are_refused_and_never_followed_by_the_real_transport():
    hits = []

    class Target(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            return None

    target = _serve(Target)

    class Source(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(301)
            self.send_header("Location", f"http://127.0.0.1:{target.server_port}/stolen")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            return None

    source = _serve(Source)
    try:
        status, _, _ = gh.urllib_transport()(f"http://127.0.0.1:{source.server_port}/repos/x/y",
                                             {"Authorization": "Bearer SECRET"}, 2.0)
        assert status == 301
        assert hits == []
    finally:
        source.shutdown()
        target.shutdown()


def test_real_socket_timeout_is_raised_as_a_timeout():
    class Slow(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(1.0)
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            return None

    server = _serve(Slow)
    try:
        with pytest.raises(TimeoutError):
            gh.urllib_transport()(f"http://127.0.0.1:{server.server_port}/", {}, 0.2)
    finally:
        server.shutdown()
