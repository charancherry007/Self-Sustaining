"""Settings for the web-search MCP server.

Configure via environment variables (see ``docs/ENVIRONMENT.md``). A single
``.env`` at the project root feeds both packages. No secrets are required:
the DuckDuckGo backend needs no API key.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR = Path(__file__).resolve().parent
# .../<root>/src/web_search_mcp -> the project root is one level above src/
PROJECT_ROOT = PACKAGE_DIR.parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WEB_SEARCH_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    max_results: int = 5
    fetch_timeout_seconds: float = 15.0
    max_chars_per_page: int = 4000
    # DuckDuckGo region bias. "in-en" matches the default INDIA_CASH_EQUITIES
    # profile; use "us-en" when analysing US cash equities.
    region: str = "in-en"
    # Comma-separated allowlist. Empty means "fall back to the trusted sources
    # file"; with enforce_allowlist=True an empty allowlist blocks everything,
    # which is the correct fail-closed default.
    allowed_domains: str = ""
    enforce_allowlist: bool = True
    # Absolute, or relative to the project root, override for the allowlist
    # source file.
    knowledge_sources_file: str = ""
    # Set a real contact address before deploying anywhere public.
    user_agent: str = (
        "trading-system-research/0.1 (+read-only research client; contact=you@example.com)"
    )

    @property
    def domain_set(self) -> set[str]:
        return {d.strip().lower() for d in self.allowed_domains.split(",") if d.strip()}

    def knowledge_sources_path(self) -> Path:
        if self.knowledge_sources_file:
            candidate = Path(self.knowledge_sources_file)
            return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate
        return PROJECT_ROOT / "knowledge" / "core" / "data_sources" / "trusted_sources.yaml"


settings = Settings()


@lru_cache(maxsize=1)
def _load_sources() -> dict:
    """Parse the version-controlled trusted sources file (cached)."""
    path = settings.knowledge_sources_path()
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


@lru_cache(maxsize=1)
def _tier_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for entry in _load_sources().get("source_tiers", []) or []:
        tier = str(entry.get("tier", "general")).lower()
        for domain in entry.get("domains", []) or []:
            mapping[str(domain).strip().lower()] = tier
    return mapping


def allowed_domains() -> set[str]:
    """Env-var allowlist if set, otherwise the trusted sources file.

    An empty result combined with ``enforce_allowlist=True`` blocks all fetching,
    which is the correct fail-closed behaviour.
    """
    return settings.domain_set or set(_tier_map())


def tier_for(host: str) -> str:
    """Trust tier for a hostname, matching parent domains too. No network I/O."""
    host = host.lower()
    parts = host.split(".")
    for index in range(len(parts) - 1):
        candidate = ".".join(parts[index:])
        if candidate in _tier_map():
            return _tier_map()[candidate]
    return "general"


def source_rules() -> dict:
    """Operational rules (page/char/time limits, untrusted-content flags)."""
    return _load_sources().get("rules", {}) or {}


def clear_source_caches() -> None:
    _load_sources.cache_clear()
    _tier_map.cache_clear()
