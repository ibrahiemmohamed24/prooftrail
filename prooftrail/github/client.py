"""Read-only live collection from the GitHub REST API.

Only api.github.com is contacted, and only through fixed endpoint shapes built
from validated request fields. Redirects are refused instead of followed, so an
Authorization header never reaches another host. Every request has a timeout,
every response a byte limit, pagination a page limit, and the whole collection
a deadline. Errors become observations, never exceptions carrying credentials.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from .contract import GithubRequest
from .evidence import (CheckRunRecord, CommitStatusRecord, EvidenceSnapshot, Observation, Provenance,
                       PullRequestRecord, RepositoryRecord)

API_HOST = "api.github.com"
API_BASE = f"https://{API_HOST}"
API_VERSION = "2022-11-28"
TOKEN_ENVIRONMENT = ("PROOFTRAIL_GITHUB_TOKEN", "GITHUB_TOKEN")
PAGE_SIZE = 100
DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_DEADLINE_SECONDS = 20.0
DEFAULT_MAX_BYTES = 2_000_000
DEFAULT_MAX_PAGES = 5
REDIRECT_STATUSES = (301, 302, 303, 307, 308)
USER_AGENT = "prooftrail-github-verifier/1"

Transport = Callable[[str, dict[str, str], float], tuple[int, dict[str, str], bytes]]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None  # surface the 3xx response instead of following it


_OPENER = urllib.request.build_opener(_NoRedirect)


def _lower_headers(headers: Any) -> dict[str, str]:
    return {key.lower(): value for key, value in headers.items()} if headers is not None else {}


def urllib_transport(max_bytes: int = DEFAULT_MAX_BYTES) -> Transport:
    """Default transport. Returns (status, headers, body) for every HTTP status."""

    def send(url: str, headers: dict[str, str], timeout: float) -> tuple[int, dict[str, str], bytes]:
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with _OPENER.open(request, timeout=timeout) as response:
                return response.status, _lower_headers(response.headers), response.read(max_bytes + 1)
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read(max_bytes + 1)
            except OSError:
                body = b""
            return exc.code, _lower_headers(exc.headers), body
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise TimeoutError("request timed out") from exc
            raise OSError("request could not be completed") from exc

    return send


@dataclass(frozen=True)
class _Result:
    status: str
    http_status: int | None
    data: Any = None


def _interpret(status: int, headers: dict[str, str], body: bytes, max_bytes: int) -> _Result:
    if 200 <= status < 300:
        if len(body) > max_bytes:
            return _Result("too_large", status)
        try:
            return _Result("ok", status, json.loads(body.decode("utf-8")))
        except (UnicodeDecodeError, ValueError):
            return _Result("invalid_response", status)
    if status in REDIRECT_STATUSES:
        return _Result("redirect_refused", status)
    if status == 401:
        return _Result("unauthorized", status)
    if status == 404:
        return _Result("not_found", status)
    if status in (403, 429):
        if status == 429 or headers.get("x-ratelimit-remaining") == "0" or "retry-after" in headers:
            return _Result("rate_limited", status)
        return _Result("forbidden", status)
    if status >= 500:
        return _Result("unavailable", status)
    return _Result("invalid_response", status)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def token_from_environment(environ: Mapping[str, str] | None = None) -> str | None:
    """Read an optional read-only token from the environment. It is never printed or stored."""
    source = os.environ if environ is None else environ
    for name in TOKEN_ENVIRONMENT:
        value = source.get(name, "").strip()
        if value:
            return value
    return None


def _is_text(value: Any) -> bool:
    return isinstance(value, str)


def _repository_record(data: Any) -> RepositoryRecord | None:
    if not isinstance(data, dict) or not _is_text(data.get("full_name")):
        return None
    if type(data.get("private")) is not bool or not _is_text(data.get("default_branch")):
        return None
    return RepositoryRecord(full_name=data["full_name"], private=data["private"], default_branch=data["default_branch"])


def _pull_record(data: Any) -> PullRequestRecord | None:
    if not isinstance(data, dict):
        return None
    base = data.get("base") if isinstance(data.get("base"), dict) else {}
    head = data.get("head") if isinstance(data.get("head"), dict) else {}
    base_repo = base.get("repo") if isinstance(base.get("repo"), dict) else {}
    head_repo = head.get("repo") if isinstance(head.get("repo"), dict) else {}
    if type(data.get("number")) is not int or not _is_text(data.get("state")) or type(data.get("merged")) is not bool:
        return None
    if not _is_text(base.get("ref")) or not _is_text(head.get("ref")) or not _is_text(head.get("sha")):
        return None
    return PullRequestRecord(
        number=data["number"], state=data["state"], merged=data["merged"],
        merged_at=data["merged_at"] if _is_text(data.get("merged_at")) else None,
        title=data["title"] if _is_text(data.get("title")) else "",
        html_url=data["html_url"] if _is_text(data.get("html_url")) else None,
        base_ref=base["ref"], base_repo=base_repo.get("full_name") if _is_text(base_repo.get("full_name")) else None,
        head_ref=head["ref"], head_sha=head["sha"],
        head_repo=head_repo.get("full_name") if _is_text(head_repo.get("full_name")) else None,
    )


def _check_run_record(item: Any) -> CheckRunRecord | None:
    if not isinstance(item, dict) or type(item.get("id")) is not int:
        return None
    if not _is_text(item.get("name")) or not _is_text(item.get("head_sha")) or not _is_text(item.get("status")):
        return None
    conclusion = item.get("conclusion")
    if conclusion is not None and not _is_text(conclusion):
        return None
    app = item.get("app") if isinstance(item.get("app"), dict) else {}
    producer = app.get("slug") if _is_text(app.get("slug")) else "unknown"
    return CheckRunRecord(
        run_id=item["id"], name=item["name"], head_sha=item["head_sha"], status=item["status"],
        conclusion=conclusion, producer=producer,
        started_at=item.get("started_at") if _is_text(item.get("started_at")) else None,
        completed_at=item.get("completed_at") if _is_text(item.get("completed_at")) else None,
        html_url=item.get("html_url") if _is_text(item.get("html_url")) else None,
    )


def _commit_status_record(item: Any, sha: str) -> CommitStatusRecord | None:
    if not isinstance(item, dict) or not _is_text(item.get("context")) or not _is_text(item.get("state")):
        return None
    return CommitStatusRecord(
        context=item["context"], state=item["state"], sha=sha,
        updated_at=item.get("updated_at") if _is_text(item.get("updated_at")) else None,
        target_url=item.get("target_url") if _is_text(item.get("target_url")) else None,
    )


class GithubCollector:
    """Collects one snapshot for one request. Create a new collector for each audit."""

    def __init__(self, *, token: str | None = None, transport: Transport | None = None,
                 clock: Callable[[], str] | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS,
                 deadline: float = DEFAULT_DEADLINE_SECONDS, max_pages: int = DEFAULT_MAX_PAGES,
                 max_bytes: int = DEFAULT_MAX_BYTES, monotonic: Callable[[], float] | None = None) -> None:
        self._token = token
        self._max_bytes = max_bytes
        self._transport = transport or urllib_transport(max_bytes)
        self._clock = clock or _utc_now
        self._timeout = timeout
        self._deadline = deadline
        self._max_pages = max_pages
        self._monotonic = monotonic or time.monotonic
        self._started = self._monotonic()

    def _get(self, path: str, params: Mapping[str, Any] | None = None) -> _Result:
        if not path.startswith("/repos/") or "://" in path:
            raise ValueError("Only repository endpoints are allowed.")
        if self._monotonic() - self._started > self._deadline:
            return _Result("timeout", None)
        query = urllib.parse.urlencode(dict(params or {}))
        url = f"{API_BASE}{path}" + (f"?{query}" if query else "")
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": API_VERSION,
                   "User-Agent": USER_AGENT}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            status, response_headers, body = self._transport(url, headers, self._timeout)
        except TimeoutError:
            return _Result("timeout", None)
        except OSError:
            return _Result("unavailable", None)
        return _interpret(status, response_headers, body, self._max_bytes)

    def _observe(self, name: str, endpoint: str, result: _Result, *, pages: int, complete: bool) -> Observation:
        return Observation(name=name, endpoint=endpoint, status=result.status, http_status=result.http_status,
                           collected_at=self._clock(), pages=pages, complete=complete)

    def _paginate(self, path: str, list_key: str, extra: Mapping[str, Any] | None = None
                  ) -> tuple[list[Any], int, _Result]:
        """Fetch list pages with a page cap. Returns raw items, pages used and a status result."""
        items: list[Any] = []
        pages = 0
        result = _Result("ok", None)
        for page in range(1, self._max_pages + 1):
            result = self._get(path, {"per_page": PAGE_SIZE, "page": page, **dict(extra or {})})
            if result.status != "ok":
                return items, pages, result
            data = result.data if isinstance(result.data, dict) else {}
            batch = data.get(list_key)
            total = data.get("total_count")
            if not isinstance(batch, list) or type(total) is not int:
                return items, pages, _Result("invalid_response", result.http_status)
            pages += 1
            items.extend(batch)
            if len(batch) < PAGE_SIZE or len(items) >= total:
                if len(items) != total:
                    return items, pages, _Result("pagination_limit", result.http_status)
                return items, pages, _Result("ok", result.http_status)
        return items, pages, _Result("pagination_limit", result.http_status)

    def _pull(self, path: str) -> tuple[PullRequestRecord | None, _Result]:
        result = self._get(path)
        if result.status != "ok":
            return None, result
        record = _pull_record(result.data)
        if record is None:
            return None, _Result("invalid_response", result.http_status)
        return record, result

    def collect(self, request: GithubRequest) -> EvidenceSnapshot:
        owner, name = request.repository.owner, request.repository.name
        sha = request.expected_head_sha
        collected_at = self._clock()

        repo_path = f"/repos/{owner}/{name}"
        repo_result = self._get(repo_path)
        repository = _repository_record(repo_result.data) if repo_result.status == "ok" else None
        if repo_result.status == "ok" and repository is None:
            repo_result = _Result("invalid_response", repo_result.http_status)
        repo_obs = self._observe("repository", repo_path, repo_result,
                                 pages=1 if repo_result.status == "ok" else 0,
                                 complete=repo_result.status == "ok")

        pr_path = f"/repos/{owner}/{name}/pulls/{request.pull_request}"
        pull, pr_result = self._pull(pr_path)
        pr_obs = self._observe("pull_request", pr_path, pr_result,
                               pages=1 if pr_result.status == "ok" else 0,
                               complete=pr_result.status == "ok")

        runs_path = f"/repos/{owner}/{name}/commits/{sha}/check-runs"
        raw_runs, run_pages, runs_result = self._paginate(runs_path, "check_runs", {"filter": "all"})
        runs = [_check_run_record(item) for item in raw_runs]
        if runs_result.status == "ok" and any(item is None for item in runs):
            runs_result = _Result("invalid_response", runs_result.http_status)
        runs_obs = self._observe("check_runs", runs_path, runs_result, pages=run_pages,
                                 complete=runs_result.status == "ok")

        status_path = f"/repos/{owner}/{name}/commits/{sha}/status"
        raw_statuses, status_pages, statuses_result = self._paginate(status_path, "statuses")
        statuses = [_commit_status_record(item, sha) for item in raw_statuses]
        if statuses_result.status == "ok" and any(item is None for item in statuses):
            statuses_result = _Result("invalid_response", statuses_result.http_status)
        statuses_obs = self._observe("commit_statuses", status_path, statuses_result, pages=status_pages,
                                     complete=statuses_result.status == "ok")

        recheck, recheck_result = self._pull(pr_path)
        recheck_obs = self._observe("pull_request_recheck", pr_path, recheck_result,
                                    pages=1 if recheck_result.status == "ok" else 0,
                                    complete=recheck_result.status == "ok")

        return EvidenceSnapshot(
            provenance=Provenance(kind="live", label=f"Live GitHub REST API read at {collected_at}",
                                  synthetic=False, collected_at=collected_at, api_host=API_HOST),
            repository=repository,
            pull_request=pull,
            recheck_head_sha=recheck.head_sha if recheck is not None else None,
            check_runs=tuple(item for item in runs if item is not None),
            commit_statuses=tuple(item for item in statuses if item is not None),
            observations=(repo_obs, pr_obs, runs_obs, statuses_obs, recheck_obs),
        )


def collect_live(request: GithubRequest, *, token: str | None = None, environ: Mapping[str, str] | None = None,
                 transport: Transport | None = None, clock: Callable[[], str] | None = None,
                 **limits: Any) -> EvidenceSnapshot:
    """Collect read-only evidence. The token comes from the argument or the environment only."""
    resolved = token if token is not None else token_from_environment(environ)
    return GithubCollector(token=resolved, transport=transport, clock=clock, **limits).collect(request)
