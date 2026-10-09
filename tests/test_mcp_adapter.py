import asyncio
import sys

import pytest

mcp = pytest.importorskip("mcp", reason="optional MCP adapter not installed")
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from prooftrail import application as app
from prooftrail.config import PROJECT_ROOT
from prooftrail.github.examples import scenario_packs

LEGACY_TOOLS = {"audit_trace", "verify_ledger", "list_frozen_cases", "get_case",
                "get_evidence_certificate", "get_benchmark_summary"}
GITHUB_TOOL = "audit_github_execution"


def test_real_stdio_mcp_tools():
    async def run():
        params = StdioServerParameters(command=sys.executable, args=["-m", "prooftrail.mcp_server"], cwd=str(PROJECT_ROOT))
        async with Client(params, read_timeout_seconds=20) as client:
            tools = await client.list_tools()
            names = {tool.name for tool in tools.tools}
            assert LEGACY_TOOLS <= names
            assert GITHUB_TOOL in names
            assert all(tool.annotations.read_only_hint for tool in tools.tools)
            github = next(tool for tool in tools.tools if tool.name == GITHUB_TOOL)
            assert github.annotations.open_world_hint is False
            assert set(github.input_schema["properties"]) == {"request", "bundle"}
            result = await client.call_tool("list_frozen_cases", {})
            assert len(result.structured_content["case_ids"]) == 40
            result = await client.call_tool("audit_trace", {"evidence": app.get_case("F02-s00")})
            assert not result.is_error
            assert result.structured_content["certificate"] == app.get_evidence_certificate("F02-s00")
            result = await client.call_tool("get_case", {"case_id": "../../.env"})
            assert result.is_error
    asyncio.run(run())


def test_real_stdio_github_tool_audits_a_saved_bundle_offline():
    pack = next(item for item in scenario_packs() if item["id"] == "synthetic-correct-open-pr")

    async def run():
        params = StdioServerParameters(command=sys.executable, args=["-m", "prooftrail.mcp_server"], cwd=str(PROJECT_ROOT))
        async with Client(params, read_timeout_seconds=20) as client:
            result = await client.call_tool(GITHUB_TOOL, {"request": pack["request"], "bundle": pack["bundle"]})
            assert not result.is_error
            assert result.structured_content["verdict"] == "SUPPORTED"
            assert result.structured_content["network_used"] is False
            assert result.structured_content["persisted"] is False
            # The SDK drops unknown arguments; the point is that a token never reaches the audit.
            ignored = await client.call_tool(GITHUB_TOOL, {"request": pack["request"], "bundle": pack["bundle"],
                                                           "token": "not-accepted"})
            assert ignored.structured_content["network_used"] is False
            assert "not-accepted" not in str(ignored.structured_content)
    asyncio.run(run())
