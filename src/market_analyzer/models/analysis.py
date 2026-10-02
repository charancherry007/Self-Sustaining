"""Analysis output schemas.

`MarketAnalysis` is the single artefact handed to the Risk Analyzer. It
carries provenance (sources, model version) and an explicit `data_realtime`
flag so the risk layer can refuse delayed data if required.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MarketRegime(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGE_BOUND = "range_bound"
    HIGH_VOLATILITY = "high_volatility"
    UNKNOWN = "unknown"


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"
    WATCH = "watch"
    AVOID = "avoid"


class SetupType(str, Enum):
    TREND_CONTINUATION = "trend_continuation"
    TREND_PULLBACK = "trend_pullback"
    MOMENTUM_BREAKOUT = "momentum_breakout"
    MEAN_REVERSION = "mean_reversion"
    NONE = "none"


class Candidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str
    sector: str | None = None
    setup: SetupType = SetupType.NONE
    side: Side = Side.WATCH
    score: float = Field(ge=0, le=100)

    last_price: float
    entry_reference: float | None = None
    invalidation: float | None = None
    confidence: float = Field(ge=0, le=1)

    rationale: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    sources: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None

    # Multi-timeframe analysis (optional, populated when MTF enabled)
    mtf_metrics: "MultiTimeframeMetrics | None" = None
    mtf_setup: dict[str, SetupType] = Field(default_factory=dict)


class MultiTimeframeMetrics(BaseModel):
    """Indicator values per timeframe, plus fused signals."""
    model_config = ConfigDict(frozen=True)

    by_timeframe: dict[str, dict[str, float]]  # {"4h": {"rsi_14": ..., "sma_20": ...}, "1h": {...}, "15m": {...}}
    fused: dict[str, float]                    # {"tf_rsi_alignment": 0.8, "tf_trend_agreement": 1.0, ...}
    dominant_trend: str                        # "bullish" | "bearish" | "neutral"
    entry_timeframe: str                       # which TF gave the entry signal ("15m")
    mtf_setup: dict[str, SetupType | None] = Field(default_factory=dict)  # per-TF setup labels (None = no setup)


class DataQualityReport(BaseModel):
    provider: str
    realtime: bool
    instruments_requested: int = 0
    instruments_ok: int = 0
    instruments_stale: int = 0
    instruments_failed: int = 0
    issues: list[str] = Field(default_factory=list)


class MarketAnalysis(BaseModel):
    run_id: str
    profile_id: str
    generated_at: datetime
    data_as_of: datetime | None
    data_realtime: bool
    provider: str
    regime: MarketRegime = MarketRegime.UNKNOWN
    regime_rationale: list[str] = Field(default_factory=list)
    summary: str = ""
    candidates: list[Candidate] = Field(default_factory=list)
    data_quality: DataQualityReport
    knowledge_refs: list[str] = Field(default_factory=list)
    news_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    ai_analysis: dict[str, Any] | None = None
    schema_version: int = 1
