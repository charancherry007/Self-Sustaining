"""Market data provider contract.

Every provider is read-only: it authenticates nothing and cannot place orders.
Adding a genuine real-time broker/exchange feed means implementing this
interface and changing one line of config.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict

from market_analyzer.models.quote import Candle, Quote


class ProviderCapabilities(BaseModel):
    """Declared properties of a provider, surfaced in analysis output."""

    model_config = ConfigDict(frozen=True)

    realtime: bool = False
    delayed: bool = True
    supports_intraday: bool = True
    supports_daily: bool = True
    max_intraday_lookback_days: int = 7
    notes: str = ""


class ProviderError(RuntimeError):
    """Raised when a provider cannot serve a request."""


class MarketDataProvider(ABC):
    """Source of numerical market data. Implementations must be read-only."""

    name: str
    #: True only for exchange-grade live data. Delayed sources set False so the
    #: analysis output can be rejected downstream by the risk layer.
    realtime: bool = False
    capabilities: ProviderCapabilities = ProviderCapabilities()

    @abstractmethod
    async def get_quote(self, symbol: str) -> Quote:
        """Fetch the latest quote for a single symbol."""

    @abstractmethod
    async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """Fetch latest quotes for many symbols. Missing symbols may be omitted."""

    @abstractmethod
    async def get_candles(
        self, symbol: str, interval: str, lookback: int, provider_symbol: str | None = None
    ) -> list[Candle]:
        """Fetch OHLCV candles ascending by timestamp.

        Args:
            symbol: The profile's symbol (used for tracking).
            interval: Candle interval (e.g., "5m", "1d").
            lookback: Number of candles to fetch.
            provider_symbol: Optional symbol to use for the API call (e.g., "QQQ" for "NAS100").

        Implementations must raise `ProviderError` on failure rather than
        returning an empty list, so the pipeline can distinguish "no data"
        from "provider broken".
        """
