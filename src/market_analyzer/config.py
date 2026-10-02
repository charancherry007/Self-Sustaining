"""Configuration loading and validation.

Paths are resolved relative to the project root so the CLI and the MCP server
behave identically regardless of the working directory. Precedence is:
environment variable > ``.env`` at the project root > ``config/app.yaml``.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, model_validator

from market_analyzer.models.profile import MarketProfile

PACKAGE_DIR = Path(__file__).resolve().parent
# .../<root>/src/market_analyzer -> the project root is one level above src/
PROJECT_ROOT = PACKAGE_DIR.parents[1]

# Load .env before anything reads os.environ. override=False keeps real
# environment variables (CI, containers) authoritative over the file.
load_dotenv(PROJECT_ROOT / ".env", override=False)

APP_CONFIG_PATH = PROJECT_ROOT / "config" / "app.yaml"
MARKETS_DIR = PROJECT_ROOT / "config" / "markets"
DEFAULT_PROFILE = "FOCUSED_SYMBOLS"

_TRUTHY = {"1", "true", "yes", "on"}


def _env_path(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    if not raw:
        return default
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _env_bool(name: str) -> bool | None:
    raw = os.getenv(name)
    return None if raw is None else raw.strip().lower() in _TRUTHY


def _env_int(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


class DataConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # No synthetic/mock provider is selectable. Every configured provider must
    # return real market data or the run fails.
    provider: str = "twelvedata"
    cache_dir: str = "data/cache"
    cache_ttl_seconds: int = Field(default=60, ge=0)
    throttle_seconds: float = Field(default=0.5, ge=0)
    stale_after_seconds: int = Field(default=900, ge=30)
    max_concurrent_requests: int = Field(default=4, ge=1, le=32)
    # When True, the run aborts unless the provider is genuinely real-time.
    require_realtime: bool = True

    # Twelve Data API key. If not set here, TWELVEDATA_API_KEY env var is used.
    twelvedata_api_key: str | None = None
    finnhub_api_key: str | None = None

    @model_validator(mode="after")
    def _known_provider(self) -> DataConfig:
        allowed = {"twelvedata", "finnhub", "twelvedata_fallback", "fallback"}
        if self.provider not in allowed:
            raise ValueError(
                f"provider must be one of {allowed}, got {self.provider!r}. "
                "Only Twelve Data, Finnhub, or Fallback data feeds are permitted."
            )
        td_key = self.twelvedata_api_key or os.getenv("TWELVEDATA_API_KEY")
        fh_key = self.finnhub_api_key or os.getenv("FINNHUB_API_KEY")
        if self.provider == "twelvedata" and not td_key:
            raise ValueError("provider 'twelvedata' requires TWELVEDATA_API_KEY")
        if self.provider == "finnhub" and not fh_key:
            raise ValueError("provider 'finnhub' requires FINNHUB_API_KEY")
        if self.provider in ("twelvedata_fallback", "fallback") and not (td_key or fh_key):
            raise ValueError("fallback provider requires TWELVEDATA_API_KEY or FINNHUB_API_KEY")
        return self


class WebResearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    # Empty means "use sys.executable", so the spawned search MCP server runs in
    # this same virtualenv rather than whatever `python` resolves to on PATH.
    mcp_command: str = ""
    mcp_args: list[str] = Field(default_factory=lambda: ["-m", "web_search_mcp"])
    max_results_per_query: int = Field(default=5, ge=1, le=20)
    freshness_hours: int = Field(default=24, ge=1)
    timeout_seconds: int = Field(default=30, ge=5)


class AiConfig(BaseModel):
    """Advisory AI layer. Off by default and never load-bearing."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    # Hard cap on symbols sent to the model per run. Free-tier models are
    # rate-limited, so this bounds cost and latency by construction.
    max_symbols_per_run: int = Field(default=5, ge=1, le=50)
    # How many recent cases to show the model when drafting a lesson.
    observations_for_lesson: int = Field(default=20, ge=2, le=200)


class KnowledgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    core_directory: str = "knowledge/core"
    cases_directory: str = "knowledge/cases"
    approved_only: bool = True
    max_context_items: int = Field(default=20, ge=1, le=200)


class OutputConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    directory: str = "runs"
    retain_runs: int = Field(default=200, ge=1)


class LoggingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    directory: str = "logs"
    level: str = "info"


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str = "analyzer_only"
    data: DataConfig = Field(default_factory=DataConfig)
    web_research: WebResearchConfig = Field(default_factory=WebResearchConfig)
    ai: AiConfig = Field(default_factory=AiConfig)
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    # Populated by load_app_config so tooling can report which file was used.
    # Not part of the YAML document.
    config_path: Path | None = Field(default=None, exclude=True, repr=False)

    @model_validator(mode="after")
    def _analyzer_only(self) -> AppConfig:
        if self.mode != "analyzer_only":
            raise ValueError(
                "the market-analyzer component only supports mode='analyzer_only'; "
                "order placement belongs to the execution component"
            )
        return self

    def resolve(self, relative: str) -> Path:
        path = Path(relative)
        return path if path.is_absolute() else PROJECT_ROOT / path


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    # safe_load only: never construct arbitrary Python objects from YAML.
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"expected a YAML mapping in {path}, got {type(data).__name__}")
    return data


def _apply_env_overrides(raw: dict) -> dict:
    """Layer environment/.env overrides on top of the YAML config.

    Only keys that are actually set are touched, so config/app.yaml remains the
    single place where the defaults are documented.
    """
    data = raw.setdefault("data", {})
    provider = os.getenv("MARKET_ANALYZER_PROVIDER")
    if provider:
        data["provider"] = provider
    for env_name, key in (
        ("MARKET_ANALYZER_REQUIRE_REALTIME", "require_realtime"),
        ("MARKET_ANALYZER_STALE_AFTER_SECONDS", "stale_after_seconds"),
    ):
        override = _env_bool(env_name) if key == "require_realtime" else _env_int(env_name)
        if override is not None:
            data[key] = override
    throttle = os.getenv("MARKET_ANALYZER_THROTTLE_SECONDS")
    if throttle:
        data["throttle_seconds"] = float(throttle)
    if os.getenv("TWELVEDATA_API_KEY"):
        data["twelvedata_api_key"] = os.getenv("TWELVEDATA_API_KEY")
    if os.getenv("FINNHUB_API_KEY"):
        data["finnhub_api_key"] = os.getenv("FINNHUB_API_KEY")

    research = raw.setdefault("web_research", {})
    enabled = _env_bool("MARKET_ANALYZER_WEB_RESEARCH_ENABLED")
    if enabled is not None:
        research["enabled"] = enabled
    command = os.getenv("MARKET_ANALYZER_WEB_RESEARCH_COMMAND")
    if command:
        research["mcp_command"] = command

    ai = raw.setdefault("ai", {})
    ai_enabled = _env_bool("MARKET_ANALYZER_AI_ENABLED")
    if ai_enabled is not None:
        ai["enabled"] = ai_enabled
    return raw


@lru_cache(maxsize=1)
def load_app_config(path: Path | None = None) -> AppConfig:
    """Load, validate and cache the application config."""
    resolved = path or _env_path("MARKET_ANALYZER_CONFIG", APP_CONFIG_PATH)
    config = AppConfig.model_validate(_apply_env_overrides(_read_yaml(resolved)))
    return config.model_copy(update={"config_path": resolved})


def default_profile_id() -> str:
    """Profile used when the caller does not name one."""
    return (os.getenv("MARKET_ANALYZER_PROFILE") or DEFAULT_PROFILE).strip().upper()


@lru_cache(maxsize=8)
def load_market_profile(profile_id: str | None = None) -> MarketProfile:
    """Load the market profile. Strictly FOCUSED_SYMBOLS is permitted."""
    resolved_id = (profile_id or default_profile_id()).strip().upper()
    if resolved_id != "FOCUSED_SYMBOLS":
        raise ValueError(
            f"Only 'FOCUSED_SYMBOLS' market profile is permitted, got {resolved_id!r}."
        )
    markets_dir = _env_path("MARKET_ANALYZER_MARKETS_DIR", MARKETS_DIR)
    path = markets_dir / "focused_symbols.yaml"
    return MarketProfile.model_validate(_read_yaml(path))


def list_profiles() -> list[str]:
    """List available market profiles (strictly locked to FOCUSED_SYMBOLS)."""
    return ["FOCUSED_SYMBOLS"]


def clear_caches() -> None:
    load_app_config.cache_clear()
    load_market_profile.cache_clear()
