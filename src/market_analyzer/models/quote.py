"""Normalised quote and candle schemas.

Every provider (Yahoo today, a broker/exchange feed tomorrow) must map its
native payloads into these models so the pipeline never sees vendor formats.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Quote(BaseModel):
    """A point-in-time price snapshot for one instrument."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    last: float = Field(ge=0)
    bid: float | None = Field(default=None, ge=0)
    ask: float | None = Field(default=None, ge=0)
    volume: float | None = Field(default=None, ge=0)
    currency: str | None = None
    timestamp: datetime
    source: str
    # False for delayed sources. Propagated into the analysis output so
    # downstream risk/execution components can refuse delayed data.
    realtime: bool = False

    @property
    def age_seconds(self) -> float | None:
        from datetime import timezone

        if self.timestamp.tzinfo is None:
            return None
        return (datetime.now(timezone.utc) - self.timestamp).total_seconds()


class Candle(BaseModel):
    """A single OHLCV bar. Collections must be sorted ascending by timestamp."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timestamp: datetime
    open: float = Field(ge=0)
    high: float = Field(ge=0)
    low: float = Field(ge=0)
    close: float = Field(ge=0)
    volume: float = Field(ge=0)
    source: str

    @property
    def is_valid_ohlc(self) -> bool:
        return (
            self.high >= max(self.open, self.close)
            and self.low <= min(self.open, self.close)
            and self.high >= self.low
        )


class CandleBundle(BaseModel):
    """All timeframes for one symbol, aligned by fetch time."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    fetch_timestamp: datetime
    timeframes: dict[str, list[Candle]]  # "4h" -> [Candle, ...], "1h" -> [...], etc.
