"""Yahoo Finance provider via yfinance.

IMPORTANT: yfinance is an unofficial community library. Yahoo data may be
delayed, rate-limited, and occasionally unavailable. This provider therefore
reports `realtime = False` so the analysis output is labelled as delayed and
the risk layer can refuse it when `data.require_realtime` is set.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import yfinance as yf

from market_analyzer.models.quote import Candle, Quote
from market_analyzer.providers.base import (
    MarketDataProvider,
    ProviderCapabilities,
    ProviderError,
)

# Yahoo limits how far back intraday bars can be fetched.
_INTERVAL_PERIOD = {
    "1m": "7d",
    "2m": "60d",
    "5m": "60d",
    "15m": "60d",
    "30m": "60d",
    "60m": "730d",
    "1h": "730d",
    "1d": "10y",
    "1wk": "10y",
}


class YahooFinanceProvider(MarketDataProvider):
    name = "yahoo"
    realtime = False
    capabilities = ProviderCapabilities(
        realtime=False,
        delayed=True,
        max_intraday_lookback_days=60,
        notes="Unofficial yfinance. Delayed and rate-limited; not exchange-grade.",
    )

    def __init__(self, throttle_seconds: float = 1.0, timeout_seconds: float = 20.0) -> None:
        self.throttle_seconds = throttle_seconds
        self.timeout_seconds = timeout_seconds
        self._lock = asyncio.Lock()
        self._last_request_at: float = 0.0

    async def _throttle(self) -> None:
        """Space out requests so we do not hammer the upstream endpoint."""
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            wait = self._last_request_at + self.throttle_seconds - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_at = loop.time()

    async def get_quote(self, symbol: str) -> Quote:
        await self._throttle()
        return await asyncio.wait_for(self._fetch_quote(symbol), self.timeout_seconds)

    async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        results: dict[str, Quote] = {}
        for symbol in symbols:
            try:
                results[symbol] = await self.get_quote(symbol)
            except (TimeoutError, ProviderError):
                continue
        return results

    async def _fetch_quote(self, symbol: str) -> Quote:
        def work() -> Quote:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            last = float(info.get("last_price") or 0.0)
            if last <= 0:
                raise ProviderError(f"no usable price for {symbol}")
            return Quote(
                symbol=symbol,
                last=last,
                volume=float(info.get("last_volume") or 0.0) or None,
                currency=info.get("currency"),
                timestamp=datetime.now(timezone.utc),
                source=self.name,
                realtime=False,
            )

        try:
            return await asyncio.to_thread(work)
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalise upstream failures
            raise ProviderError(f"yahoo quote failed for {symbol}: {exc}") from exc

    async def get_candles(
        self, symbol: str, interval: str, lookback: int, provider_symbol: str | None = None
    ) -> list[Candle]:
        await self._throttle()
        return await asyncio.wait_for(
            self._fetch_candles(symbol, interval, lookback, provider_symbol), self.timeout_seconds
        )

    async def _fetch_candles(
        self, symbol: str, interval: str, lookback: int, provider_symbol: str | None = None
    ) -> list[Candle]:
        period = _INTERVAL_PERIOD.get(interval)
        if period is None:
            raise ProviderError(f"unsupported interval {interval!r} for provider {self.name}")

        def work() -> list[Candle]:
            api_symbol = provider_symbol or symbol
            frame = yf.Ticker(api_symbol).history(
                period=period, interval=interval, auto_adjust=False, actions=False
            )
            if frame.empty:
                raise ProviderError(f"no candles returned for {symbol} @ {interval}")
            candles = [
                Candle(
                    symbol=symbol,
                    timestamp=_as_utc(index),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]),
                    source=self.name,
                )
                for index, row in frame.iterrows()
            ]
            return candles[-lookback:]

        try:
            return await asyncio.to_thread(work)
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"yahoo candles failed for {symbol} @ {interval}: {exc}") from exc


def _as_utc(index) -> datetime:
    """Normalise a pandas Timestamp to a timezone-aware UTC datetime."""
    stamp = index.to_pydatetime() if hasattr(index, "to_pydatetime") else index
    if stamp.tzinfo is None:
        return stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)
