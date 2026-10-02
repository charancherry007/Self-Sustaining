from __future__ import annotations

import json

import pytest

from web_search_mcp.search import (
    BlockedURLError,
    host_in_allowlist,
    validate_url,
)

ALLOWED = {"nseindia.com", "livemint.com"}


def test_allowlist_matches_exact_domain():
    assert host_in_allowlist("nseindia.com", ALLOWED)


def test_allowlist_matches_subdomain():
    assert host_in_allowlist("api.livemint.com", ALLOWED)


def test_allowlist_rejects_other_domain():
    assert not host_in_allowlist("example.com", ALLOWED)


def test_allowlist_does_not_match_suffix_trick():
    # evil-nseindia.com must not pass: the check anchors on a dot boundary.
    assert not host_in_allowlist("evil-nseindia.com", ALLOWED)


def test_rejects_loopback():
    with pytest.raises(BlockedURLError):
        validate_url("http://127.0.0.1:8080/admin", ALLOWED)


def test_rejects_private_host():
    with pytest.raises(BlockedURLError):
        validate_url("http://192.168.1.1/", ALLOWED)


def test_rejects_bad_scheme():
    with pytest.raises(BlockedURLError):
        validate_url("file:///etc/passwd", ALLOWED)


def test_trusted_sources_file_is_discovered():
    """The allowlist must resolve from the project knowledge directory."""
    from web_search_mcp.config import allowed_domains, settings

    assert settings.knowledge_sources_path().exists(), "trusted_sources.yaml is missing"
    assert "nseindia.com" in allowed_domains()


def test_tier_lookup_comes_from_the_yaml_file():
    """Tiers must not be hardcoded in Python; the file is the source of truth."""
    from web_search_mcp.config import tier_for

    assert tier_for("nseindia.com") == "official"
    assert tier_for("sub.nseindia.com") == "official"  # parent-domain match
    assert tier_for("some-unknown-site.example") == "general"


def test_fetch_page_tool_is_callable():
    """Regression: the tool's own name shadowed the imported implementation.

    @mcp.tool() returns the decorated function, so `from ... import
    fetch_page` followed by a tool named `fetch_page` made the tool call itself
    and raise TypeError. Call the tool through the MCP registry instead.
    """
    import web_search_mcp.server as server

    tool = next(t for t in server.mcp._tool_manager.list_tools() if t.name == "fetch_page")
    # Blocked before any network I/O, so this stays hermetic.
    result = json.loads(tool.fn("http://127.0.0.1:9/x"))
    assert result["ok"] is False
    assert result["error"] is not None
