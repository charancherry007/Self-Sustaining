"""Real-time provider slot.

The user requires a genuine real-time feed from day one. yfinance cannot
provide that, so this module exists as the explicit integration point for a
broker or exchange streaming API.

To enable it:
  1. Pick a provider with an official API and market-data subscription.
     India: Angel One SmartAPI, Zerodha Kite Connect, Upstox, Dhan, Fyers, or
     a licensed exchange feed vendor.
     US: a redistributor of the NYSE BQT (consolidated) and/or Nasdaq
     TotalView feeds, or IEX for a real-time but IEX-only volume view.
  2. Implement `RealtimeProvider` below against that provider's WebSocket /
     streaming quote endpoint, mapping payloads into `Quote`/`Candle`.
  3. Set `data.provider: realtime` in config/app.yaml (or export
     MARKET_ANALYZER_PROVIDER=realtime).

Until then the analyzer refuses to label its output as real-time, and the
config flag `data.require_realtime: true` will fail the run outright rather
than silently analysing delayed data.

See docs/REAL_TIME.md for the full integration checklist.
"""

from __future__ import annotations

from market_analyzer.models.quote import Candle, Quote
from market_analyzer.providers.base import (
    MarketDataProvider,
    ProviderCapabilities,
    ProviderError,
)

_REQUIREMENTS = """
Implementing a real-time provider requires:
  - Broker/exchange API credentials supplied via environment variables
    (never stored in config files or knowledge files).
  - A streaming subscription (WebSocket or polling) for LTP and volume.
  - Symbol master mapping from the broker's instrument list.
  - Reconnection and heartbeat handling.
  - Clock sync, because freshness validation depends on accurate timestamps.
"""


class RealtimeUnavailableError(ProviderError):
    """Raised when no real-time adapter has been configured yet."""


class RealtimeProvider(MarketDataProvider):
    """Skeleton base class for a genuine real-time adapter."""

    name = "realtime"
    realtime = True
    capabilities = ProviderCapabilities(
        realtime=True,
        delayed=False,
        notes="Not implemented yet; see docs/REAL_TIME.md.",
    )

    def __init__(self, api_key_env: str, api_secret_env: str) -> None:
        self._api_key_env = api_key_env
        self._api_secret_env = api_secret_env
        raise RealtimeUnavailableError(
            "No real-time adapter configured. " + _REQUIREMENTS
        )

    async def get_quote(self, symbol: str) -> Quote:  # pragma: no cover - stub
        raise RealtimeUnavailableError(_REQUIREMENTS)

    async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:  # pragma: no cover
        raise RealtimeUnavailableError(_REQUIREMENTS)

    async def get_candles(
        self, symbol: str, interval: str, lookback: int
    ) -> list[Candle]:  # pragma: no cover - stub
        raise RealtimeUnavailableError(_REQUIREMENTS)
