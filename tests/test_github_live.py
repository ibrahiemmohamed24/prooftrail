"""Live, read-only checks against the public GitHub REST API.

Skipped unless PROOFTRAIL_LIVE_TESTS=1 is set, so CI never needs credentials or network.
These tests assert only facts that stay true over time (a merged PR stays merged; a PR's
existence and base do not depend on new commits).
"""
import os

import pytest

from prooftrail.github.audit import audit as run_audit
from prooftrail.github.client import collect_live
from prooftrail.github.contract import parse_request

live = pytest.mark.skipif(os.environ.get("PROOFTRAIL_LIVE_TESTS") != "1",
                          reason="set PROOFTRAIL_LIVE_TESTS=1 to read api.github.com (read-only)")
OWNER = "ibrahiemmohamed24"
REPO = "prooftrail"


def _request(number, claims, base="main"):
    return parse_request({
        "schema_version": 1, "domain": "github", "repository": {"owner": OWNER, "name": REPO},
        "pull_request": number, "expected_head_sha": "e8470dda7ccdca2c3f899d30248e6cc2b10e6d93",
        "expected_base_branch": base, "required_checks": ["replay"],
        "claims": [{"id": f"c{index}", "type": kind} for index, kind in enumerate(claims, start=1)],
    })


@live
def test_merged_pull_request_is_supported_by_its_merged_flag():
    request = _request(3, ["pr_exists", "base_branch", "pr_merged"])
    result = run_audit(request, collect_live(request))
    statuses = [claim["status"] for claim in result["claims"]]
    assert statuses == ["SUPPORTED", "SUPPORTED", "SUPPORTED"]
    assert result["network_used"] is True
    assert result["source"]["api_host"] == "api.github.com"


@live
def test_unmerged_pull_request_contradicts_a_merge_claim():
    request = _request(4, ["pr_exists", "pr_merged"])
    result = run_audit(request, collect_live(request))
    assert result["claims"][0]["status"] == "SUPPORTED"
    assert result["claims"][1]["status"] == "CONTRADICTED"
    assert result["claims"][1]["reason_code"] in ("not_merged", "closed_without_merge")
