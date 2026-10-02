"""DuckDuckGo-backed search + page fetching.

Design constraints (deliberate, not accidental):
  * No API key required.
  * Domain allowlist is enforced on both search and fetch.
  * Fetched text is treated as UNTRUSTED and returned as data only.
  * Login-walled content is skipped.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from web_search_mcp.config import settings, tier_for


class BlockedURLError(ValueError):
    """Raised when a URL is disallowed by policy."""


def host_in_allowlist(host: str, allowed_domains: set[str] | None) -> bool:
    """Pure allowlist check (no DNS). Includes subdomain matching."""
    if not allowed_domains:
        return True
    host = host.lower()
    return any(host == d or host.endswith("." + d) for d in allowed_domains)


def _is_private_host(host: str) -> bool:
    """Guard against SSRF to loopback / link-local / private ranges.

    Fails closed: if DNS cannot resolve the host we treat it as unsafe,
    because an unresolvable name may point anywhere once rebinding occurs.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            return True
    return False


def validate_url(url: str, allowed_domains: set[str] | None = None) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise BlockedURLError(f"unsupported scheme in {url!r}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise BlockedURLError(f"missing host in {url!r}")
    if _is_private_host(host):
        raise BlockedURLError(f"refusing to fetch private or unresolvable host {host!r}")
    if settings.enforce_allowlist and not host_in_allowlist(host, allowed_domains):
        raise BlockedURLError(f"host {host!r} is not on the allowlist")
    return url


def search(
    query: str,
    limit: int | None = None,
    allowed_domains: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Search DuckDuckGo. Returns a list of result dicts."""
    from duckduckgo_search import DDGS

    limit = min(limit or settings.max_results, settings.max_results)
    out: list[dict[str, Any]] = []
    with DDGS() as ddgs:
        # Region bias comes from config so the same build can serve an Indian
        # or a US market profile.
        results = ddgs.text(
            query,
            region=settings.region,
            safesearch="moderate",
            max_results=limit * 2,
        )
        for item in results:
            url = item.get("href") or item.get("url") or ""
            if not url:
                continue
            host = (urlparse(url).hostname or "").lower()
            if allowed_domains and not any(
                host == d or host.endswith("." + d) for d in allowed_domains
            ):
                continue
            out.append(
                {
                    "title": item.get("title"),
                    "url": url,
                    "publisher": host,
                    "snippet": item.get("body") or "",
                    "source_tier": _tier_for(host),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            if len(out) >= limit:
                break
    return out


def _tier_for(host: str) -> str:
    """Trust tier for a host, resolved from knowledge/core/data_sources.

    The YAML file is the single source of truth; nothing is hardcoded here so
    that adding a domain there takes effect immediately.
    """
    return tier_for(host)


_LOGIN_MARKERS = re.compile(
    r"(sign in to continue|please log in|create a free account|subscription required)",
    re.IGNORECASE,
)


def fetch_page(
    url: str,
    max_chars: int | None = None,
    allowed_domains: set[str] | None = None,
) -> dict[str, Any]:
    """Fetch and extract readable text from a page.

    Returns {url, fetched_at, text, title, ok, error}. Never raises for
    network failures; the caller decides how to degrade.
    """
    max_chars = max_chars or settings.max_chars_per_page
    result: dict[str, Any] = {
        "url": url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "text": "",
        "title": "",
        "ok": False,
        "error": None,
        "untrusted": True,
    }
    try:
        validate_url(url, allowed_domains)
    except BlockedURLError as exc:
        result["error"] = str(exc)
        return result

    try:
        with httpx.Client(
            timeout=settings.fetch_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": settings.user_agent},
        ) as client:
            response = client.get(url)
            response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"fetch failed: {exc}"
        return result

    html = response.text
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    result["title"] = title

    if _LOGIN_MARKERS.search(soup.get_text(" ", strip=True)[:2000]):
        result["error"] = "login-walled content skipped"
        return result

    try:
        import trafilatura

        text = trafilatura.extract(html, include_comments=False, include_tables=False) or ""
    except Exception:  # noqa: BLE001 - fall back to naive text
        text = soup.get_text(" ", strip=True)

    if not text.strip():
        result["error"] = "no extractable text"
        return result

    result["text"] = text[:max_chars]
    result["ok"] = True
    return result
