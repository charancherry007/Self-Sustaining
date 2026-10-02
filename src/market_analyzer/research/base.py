"""Web research contract.

The analyzer may consult qualitative sources (news, filings, macro releases)
but never treats web content as numerical truth. Web text is untrusted input
and cannot influence risk limits or tool permissions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class WebResearchProvider(ABC):
    name: str

    @abstractmethod
    async def search(
        self,
        query: str,
        limit: int = 5,
        freshness_hours: int = 24,
        source_tiers: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return results as dicts with keys:

        title, url, publisher, published_at, snippet, source_tier
        """

    @abstractmethod
    async def fetch(self, url: str, max_chars: int = 4000) -> dict[str, Any]:
        """Return dict with keys: url, fetched_at, text, ok, error."""


class NullResearchProvider(WebResearchProvider):
    """Used when web research is disabled. Keeps the pipeline unchanged."""

    name = "null"

    async def search(
        self,
        query: str,
        limit: int = 5,
        freshness_hours: int = 24,
        source_tiers: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        return []

    async def fetch(self, url: str, max_chars: int = 4000) -> dict[str, Any]:
        return {"url": url, "fetched_at": datetime.now().isoformat(), "text": "", "ok": False}
