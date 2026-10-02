"""MCP-backed web research adapter.

Talks to the companion `web-search-mcp` server over stdio. That server owns
the actual HTTP fetching and domain allowlisting; this adapter is the bridge.

If the MCP server is unreachable, the analyzer degrades to a no-op rather than
failing, so market analysis never depends on web availability.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from market_analyzer.research.base import WebResearchProvider

_START_TIMEOUT = 20.0
_CALL_TIMEOUT = 30.0


class McpWebResearchProvider(WebResearchProvider):
    name = "mcp_web"

    def __init__(
        self,
        command: str = "python",
        args: list[str] | None = None,
        cwd: str | None = None,
    ) -> None:
        self.command = command
        self.args = args or ["-m", "web_search_mcp"]
        self.cwd = cwd
        self._session: Any = None
        self._stack: Any = None
        self._tools: dict[str, Any] = {}

    async def _ensure_session(self) -> Any:
        if self._session is not None:
            return self._session

        from contextlib import AsyncExitStack

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        self._stack = AsyncExitStack()
        params = StdioServerParameters(command=self.command, args=self.args, cwd=self.cwd)
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        listed = await self._session.list_tools()
        self._tools = {tool.name: tool for tool in listed.tools}
        return self._session

    async def aclose(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
            self._session = None

    async def search(
        self,
        query: str,
        limit: int = 5,
        freshness_hours: int = 24,
        source_tiers: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            session = await self._ensure_session()
            if "web_search" not in self._tools:
                return []
            args: dict[str, Any] = {"query": query, "limit": limit}
            if freshness_hours:
                args["freshness_hours"] = freshness_hours
            if source_tiers:
                args["source_tiers"] = source_tiers
            result = await session.call_tool("web_search", args, timeout=_CALL_TIMEOUT)
        except Exception:  # noqa: BLE001 - degrade gracefully
            return []

        results: list[dict[str, Any]] = []
        for block in getattr(result, "content", []) or []:
            text = getattr(block, "text", None)
            if not text:
                continue
            import json

            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, list):
                results.extend(item for item in parsed if isinstance(item, dict))
            elif isinstance(parsed, dict):
                results.append(parsed)
        return results[:limit]

    async def fetch(self, url: str, max_chars: int = 4000) -> dict[str, Any]:
        try:
            session = await self._ensure_session()
            if "fetch_page" not in self._tools:
                return {"url": url, "fetched_at": datetime.now(timezone.utc).isoformat(),
                        "text": "", "ok": False, "error": "fetch_page tool unavailable"}
            result = await session.call_tool(
                "fetch_page", {"url": url, "max_chars": max_chars}, timeout=_CALL_TIMEOUT
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "url": url,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "text": "",
                "ok": False,
                "error": str(exc),
            }

        for block in getattr(result, "content", []) or []:
            text = getattr(block, "text", None)
            if text:
                import json

                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"url": url, "fetched_at": datetime.now(timezone.utc).isoformat(),
                            "text": text[:max_chars], "ok": True}
        return {"url": url, "fetched_at": datetime.now(timezone.utc).isoformat(),
                "text": "", "ok": False}
