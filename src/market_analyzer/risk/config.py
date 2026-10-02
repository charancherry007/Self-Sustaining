"""Risk profile loading and validation."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

from market_analyzer.config import PROJECT_ROOT
from market_analyzer.models.risk import RiskProfile

RISK_PROFILES_DIR = PROJECT_ROOT / "config" / "risk" / "profiles"
DEFAULT_RISK_PROFILE = "CONSERVATIVE"

load_dotenv(PROJECT_ROOT / ".env", override=False)


def _env_path(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    if not raw:
        return default
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"risk profile not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"expected a YAML mapping in {path}, got {type(data).__name__}")
    return data


@lru_cache(maxsize=8)
def load_risk_profile(profile_id: str | None = None) -> RiskProfile:
    """Load a risk profile by id, e.g. CONSERVATIVE."""
    profile_id = (profile_id or os.getenv("MARKET_ANALYZER_RISK_PROFILE") or DEFAULT_RISK_PROFILE).strip().upper()
    path = RISK_PROFILES_DIR / f"{profile_id.lower()}.yaml"
    return RiskProfile.model_validate(_read_yaml(path))


def list_risk_profiles() -> list[str]:
    if not RISK_PROFILES_DIR.exists():
        return []
    return sorted(p.stem.upper() for p in RISK_PROFILES_DIR.glob("*.yaml"))


def default_risk_profile_id() -> str:
    return (os.getenv("MARKET_ANALYZER_RISK_PROFILE") or DEFAULT_RISK_PROFILE).strip().upper()


def clear_risk_caches() -> None:
    load_risk_profile.cache_clear()