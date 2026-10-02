"""Integration test: analyzer research adapter <-> web-search MCP over stdio.

Runs the real MCP subprocess and performs a real handshake. It asserts on tool
availability and on the SSRF/allowlist policy, but never performs a live
network search (CI and sandboxes have no egress, and search is flaky).

To smoke-test a real search manually, start the server and call the adapter:

    from market_analyzer.research.mcp_web import McpWebResearchProvider
    await McpWebResearchProvider().search("nifty 50 today")
"""

from __future__ import annotations

import importlib.util
import sys

import pytest

from market_analyzer.research.mcp_web import McpWebResearchProvider

HAS_SERVER = importlib.util.find_spec("web_search_mcp") is not None

pytestmark = pytest.mark.skipif(
    not HAS_SERVER, reason="web_search_mcp package is not installed in this environment"
)


async def test_can_start_server_and_list_tools():
    provider = McpWebResearchProvider(command=sys.executable)
    try:
        session = await provider._ensure_session()
        assert session is not None
        assert "web_search" in provider._tools
        assert "fetch_page" in provider._tools
    finally:
        await provider.aclose()


async def test_unreachable_server_degrades_gracefully():
    """A dead MCP server must not raise; research is optional by design."""
    provider = McpWebResearchProvider(command="definitely-not-a-real-command-xyz")
    results = await provider.search("anything")
    assert results == []


async def test_allowlist_blocks_ssrf_via_fetch():
    """fetch_page must refuse loopback/private hosts."""
    from web_search_mcp.search import fetch_page

    result = fetch_page("http://127.0.0.1:9999/internal")
    assert result["ok"] is False
    assert result["error"] is not None
