"""Market profile schema: which market, which instruments, how to score them."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AssetClass(StrEnum):
    EQUITY = "equity"
    INDEX = "index"
    FX = "fx"
    COMMODITY = "commodity"
    CRYPTO = "crypto"
    ETF = "etf"


class VolumeKind(StrEnum):
    CONSOLIDATED = "consolidated"
    TICK = "tick"
    VENUE = "venue"
    UNKNOWN = "unknown"
    NONE = "none"


class Instrument(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str
    exchange: str = "UNKNOWN"
    sector: str | None = None
    currency: str = "USD"
    lot_size: int = Field(default=1, ge=1)

    # Feed routing and honesty fields
    asset_class: AssetClass = AssetClass.EQUITY
    provider_symbol: str | None = None
    timezone: str = "America/New_York"
    session: str = "equity_us"
    volume_kind: VolumeKind = VolumeKind.UNKNOWN
    proxy_of: str | None = None

    @property
    def base_symbol(self) -> str:
        return self.symbol.split(".")[0]


class ScoringWeights(BaseModel):
    """Relative importance of each ranking component.

    Values are normalised at load time, so they need not sum to 1.0.
    `news_sentiment` stays neutral (0.5) while web research is disabled.
    """

    liquidity: float = Field(default=0.20, ge=0)
    trend_alignment: float = Field(default=0.25, ge=0)
    momentum: float = Field(default=0.20, ge=0)
    volatility_fit: float = Field(default=0.15, ge=0)
    data_freshness: float = Field(default=0.10, ge=0)
    news_sentiment: float = Field(default=0.10, ge=0)
    # Multi-timeframe fusion weights
    mtf_trend_agreement: float = Field(default=0.15, ge=0)
    mtf_rsi_alignment: float = Field(default=0.10, ge=0)
    mtf_volume_confirmation: float = Field(default=0.05, ge=0)

    @model_validator(mode="after")
    def _at_least_one_weight(self) -> ScoringWeights:
        if sum(self.model_dump().values()) <= 0:
            raise ValueError("at least one scoring weight must be greater than zero")
        return self

    def normalised(self) -> dict[str, float]:
        raw = self.model_dump()
        total = sum(raw.values())
        return {key: value / total for key, value in raw.items()}


class Timeframes(BaseModel):
    intraday: str = "5m"
    trend: str = "1d"
    
    # New: explicit multi-timeframe list (ordered coarse → fine)
    intraday_multi: list[str] = Field(default_factory=lambda: ["4h", "1h", "15m"])
    
    @model_validator(mode="after")
    def _ensure_consistency(self) -> "Timeframes":
        if self.intraday not in self.intraday_multi:
            # Append at the end (finest timeframe) to maintain coarse→fine order
            self.intraday_multi = [*self.intraday_multi, self.intraday]
        return self


class MarketProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    display_name: str
    timezone: str = "Asia/Kolkata"
    exchange: str = "NSE"
    currency: str = "INR"
    benchmark: str | None = None
    segments: list[str] = Field(default_factory=list)
    timeframes: Timeframes = Field(default_factory=Timeframes)
    min_history_candles: int = Field(default=30, ge=5)
    max_lookback: int = Field(default=250, ge=30)
    max_candidates: int = Field(default=10, ge=1)
    scoring_weights: ScoringWeights = Field(default_factory=ScoringWeights)
    universe: list[Instrument] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_symbols(self) -> MarketProfile:
        symbols = [item.symbol for item in self.universe]
        duplicates = {s for s in symbols if symbols.count(s) > 1}
        if duplicates:
            raise ValueError(f"duplicate symbols in universe: {sorted(duplicates)}")
        return self

    def symbols(self) -> list[str]:
        return [item.symbol for item in self.universe]

    def instrument(self, symbol: str) -> Instrument | None:
        for item in self.universe:
            if item.symbol == symbol:
                return item
        return None
