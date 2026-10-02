"""Fallback market data provider wrapping TwelveData and Finnhub.

Automatically detects TwelveData rate limits at runtime and switches seamlessly
to Finnhub without throwing errors or interrupting the analysis pipeline.
"""

from __future__ import annotations

import logging

from market_analyzer.models.quote import Candle, Quote
from market_analyzer.providers.base import (
    MarketDataProvider,
    ProviderCapabilities,
)

logger = logging.getLogger(__name__)


def is_rate_limit_error(exc: Exception) -> bool:
    """Detect if an exception is due to API quota or rate limiting."""
    msg = str(exc).lower()
    return any(
        phrase in msg
        for phrase in (
            "429",
            "rate limit",
            "rate_limit",
            "credits",
            "credit limit",
            "too many requests",
            "plan restriction",
            "reached your limit",
        )
    )


class FallbackDataProvider(MarketDataProvider):
    """Dual-feed provider with automatic failover to Finnhub upon rate limits."""

    name = "fallback"

    def __init__(
        self,
        primary: MarketDataProvider,
        secondary: MarketDataProvider,
        switch_on_rate_limit: bool = True,
    ) -> None:
        self.primary = primary
        self.secondary = secondary
        self.switch_on_rate_limit = switch_on_rate_limit
        self._primary_rate_limited = False
        self.realtime = primary.realtime or secondary.realtime
        self.capabilities = ProviderCapabilities(
            realtime=True,
            delayed=False,
            supports_intraday=True,
            supports_daily=True,
            notes=f"Primary: {primary.name} with runtime fallback to {secondary.name}",
        )

    @property
    def active_provider_name(self) -> str:
        return self.secondary.name if self._primary_rate_limited else self.primary.name

    async def aclose(self) -> None:
        if hasattr(self.primary, "aclose"):
            await self.primary.aclose()
        if hasattr(self.secondary, "aclose"):
            await self.secondary.aclose()

    async def get_quote(self, symbol: str) -> Quote:
        """Fetch quote from primary, falling back to secondary if rate-limited."""
        if not self._primary_rate_limited:
            try:
                return await self.primary.get_quote(symbol)
            except Exception as exc:
                if self.switch_on_rate_limit and is_rate_limit_error(exc):
                    self._primary_rate_limited = True
                    msg = (
                        f"[Fallback] {self.primary.name.upper()} rate limit reached! "
                        f"Seamlessly switching data feed to {self.secondary.name.upper()} for {symbol} quote."
                    )
                    print(msg, flush=True)
                    logger.warning(msg)
                else:
                    raise

        # Secondary (Finnhub) fallback
        return await self.secondary.get_quote(symbol)

    async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """Fetch multiple quotes with runtime fallback."""
        if not self._primary_rate_limited:
            try:
                return await self.primary.get_quotes(symbols)
            except Exception as exc:
                if self.switch_on_rate_limit and is_rate_limit_error(exc):
                    self._primary_rate_limited = True
                    msg = (
                        f"[Fallback] {self.primary.name.upper()} rate limit reached! "
                        f"Seamlessly switching data feed to {self.secondary.name.upper()} for batch quotes."
                    )
                    print(msg, flush=True)
                    logger.warning(msg)
                else:
                    raise

        return await self.secondary.get_quotes(symbols)

    async def get_candles(
        self,
        symbol: str,
        interval: str,
        lookback: int,
        provider_symbol: str | None = None,
    ) -> list[Candle]:
        """Fetch candles with runtime rate-limit fallback to Finnhub."""
        if not self._primary_rate_limited:
            try:
                return await self.primary.get_candles(
                    symbol=symbol,
                    interval=interval,
                    lookback=lookback,
                    provider_symbol=provider_symbol,
                )
            except Exception as exc:
                if self.switch_on_rate_limit and is_rate_limit_error(exc):
                    self._primary_rate_limited = True
                    msg = (
                        f"[Fallback] {self.primary.name.upper()} rate limit reached! "
                        f"Seamlessly switching data feed to {self.secondary.name.upper()} for {symbol} candles."
                    )
                    print(msg, flush=True)
                    logger.warning(msg)
                else:
                    raise

        # Secondary (Finnhub) fallback
        return await self.secondary.get_candles(
            symbol=symbol,
            interval=interval,
            lookback=lookback,
            provider_symbol=provider_symbol,
        )
