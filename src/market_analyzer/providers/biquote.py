"""Biquote.io multi-asset provider.

Covers Forex, Crypto, Metals, Indices (via ETFs), Stocks, Commodities.
Data-only: no trading endpoints, no order placement.

Key features:
- No API key required
- 15,000 requests/minute rate limit
- Native batch quotes endpoint
- OHLCV candles with real volume for stocks/ETFs (Yahoo Finance aggregation)
- Tick volume for Forex/Metals/Crypto (MT5 feed)
- SignalR WebSocket for real-time streaming
- Economic calendar, news, market stats included
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from market_analyzer.models.quote import Candle, Quote
from market_analyzer.providers.base import MarketDataProvider, ProviderCapabilities, ProviderError
from market_analyzer.providers.session import MarketCalendar, SessionState, get_calendar
from market_analyzer.telemetry import log_api_error, log_api_request, log_api_response

BASE_URL = "https://biquote.io/api"

# Interval mapping: analyzer interval -> biquote interval
_INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}

# Default max lookback per interval (biquote supports up to 1000 bars)
_MAX_LOOKBACK = {
    "1m": 1000,
    "5m": 1000,
    "15m": 1000,
    "30m": 1000,
    "1h": 1000,
    "4h": 1000,
    "1d": 1000,
}


class BiquoteProvider(MarketDataProvider):
    name = "biquote"
    realtime = True  # Capable of real-time via WebSocket; REST is near-real-time

    capabilities = ProviderCapabilities(
        realtime=True,
        delayed=True,
        supports_intraday=True,
        supports_daily=True,
        max_intraday_lookback_days=365,
        notes=(
            "Biquote.io API - no auth required. "
            "15,000 req/min rate limit. "
            "OHLCV from Yahoo Finance (stocks/ETFs) and MT5 (FX/Metals/Crypto). "
            "Real volume for stocks/ETFs; tick volume for FX/Metals/Crypto. "
            "Indices via ETF proxies (QQQUSDT, SPYUSDT). "
            "SignalR WebSocket at /hubs/tick for true streaming."
        ),
    )

    def __init__(
        self,
        throttle_seconds: float = 0.1,  # Much faster than Twelve Data
        timeout_seconds: float = 15.0,
    ) -> None:
        self._throttle = throttle_seconds
        self._timeout = timeout_seconds
        self._last_request = 0.0
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _throttled_request(self, path: str, params: dict | None = None) -> dict:
        client = await self._get_client()
        params = params or {}
        url = f"{BASE_URL}{path}"
        max_retries = 3

        sym = params.get("symbol", "") or (params.get("symbols", [""])[0] if params.get("symbols") else "")
        if not sym and path.startswith("/"):
            sym = path.lstrip("/").split("/")[0]
        interval = params.get("interval", "")
        req_details = f"symbol={sym}" + (f", interval={interval}" if interval else "")

        for attempt in range(max_retries):
            now = asyncio.get_event_loop().time()
            wait = self._throttle - (now - self._last_request)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = asyncio.get_event_loop().time()

            log_api_request("Biquote API", f"GET {path}", req_details)
            start_time = time.perf_counter()

            try:
                resp = await client.get(url, params=params)
                elapsed = time.perf_counter() - start_time

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", "60"))
                    log_api_error("Biquote API", f"GET {path} [{sym}]", elapsed, f"HTTP 429 Rate Limit Exceeded (retry after {retry_after}s)")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(min(retry_after, 30))
                        continue
                    raise ProviderError(f"biquote rate limit exceeded (429), retry after {retry_after}s")
                if resp.status_code == 400:
                    log_api_error("Biquote API", f"GET {path} [{sym}]", elapsed, f"HTTP 400 Bad Request")
                    raise ProviderError(f"biquote bad request: {resp.text[:200]}")
                if resp.status_code == 404:
                    log_api_error("Biquote API", f"GET {path} [{sym}]", elapsed, "HTTP 404 Not Found")
                    raise ProviderError(f"biquote symbol not found or no data: {sym}")
                if resp.status_code >= 400:
                    log_api_error("Biquote API", f"GET {path} [{sym}]", elapsed, f"HTTP {resp.status_code}")
                    raise ProviderError(f"biquote HTTP {resp.status_code}: {resp.text[:200]}")

                data = resp.json()
                
                # Check for error response format
                if isinstance(data, dict) and data.get("error") == "rate_limited":
                    retry_after = int(data.get("message", "60").split()[-2]) if "retry after" in data.get("message", "").lower() else 60
                    log_api_error("Biquote API", f"GET {path} [{sym}]", elapsed, f"Rate limited: {data.get('message')}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(min(retry_after, 30))
                        continue
                    raise ProviderError(f"biquote rate limited: {data.get('message')}")

                vals = 0
                if isinstance(data, dict):
                    if "values" in data:
                        vals = len(data.get("values", []))
                    elif "bars" in data:
                        vals = len(data.get("bars", []))
                    elif "items" in data:
                        vals = len(data.get("items", []))
                    elif "close" in data or "bid" in data or "mid" in data:
                        vals = 1
                elif isinstance(data, list):
                    vals = len(data)
                
                resp_info = f"{vals} items" if vals else "OK"
                log_api_response("Biquote API", f"GET {path} [{sym}]", elapsed, resp.status_code, resp_info)
                return data
            except httpx.HTTPError as exc:
                elapsed = time.perf_counter() - start_time
                log_api_error("Biquote API", f"GET {path} [{sym}]", elapsed, f"Request failed: {exc}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2.0)
                    continue
                raise ProviderError(f"biquote request failed: {exc}") from exc
        raise ProviderError("biquote request failed after retries")

    def _normalize_timestamp(self, ts_str: str) -> datetime:
        """Parse ISO 8601 timestamp to UTC-aware datetime."""
        # biquote uses ISO 8601: '2026-10-02T20:00:00Z'
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))

    def _determine_realtime(self, quote_ts: datetime, instrument_session: str) -> bool:
        """Check if quote timestamp is fresh for the instrument's session."""
        now = datetime.now(timezone.utc)
        age = (now - quote_ts).total_seconds()
        cal = get_calendar(instrument_session)
        if cal.is_open(now):
            return age <= 30  # within 30 seconds during open session
        # Outside session: last quote could be from previous close
        return age <= 3600  # within 1 hour of session close

    def _to_api_symbol(self, symbol: str, provider_symbol: str | None = None) -> str:
        """Resolve any user, profile, or provider symbol to the exact Biquote API format.

        Biquote REST URLs are /{symbol} and /{symbol}/ohlc, so the symbol segment
        must NEVER contain slashes (e.g. 'BTC/USD' -> 'BTCUSD', 'BTC/USDT' -> 'BTCUSDT').
        Also routes index ETFs (NAS100/QQQ -> QQQUSDT, US500/SPY -> SPYUSDT).
        """
        raw = (provider_symbol or symbol or "").strip().upper()
        cleaned = raw.replace("/", "").replace("-", "").replace(" ", "")

        mapping = {
            "NAS100": "QQQUSDT",
            "US500": "SPYUSDT",
            "QQQ": "QQQUSDT",
            "SPY": "SPYUSDT",
            "DIA": "DIAUSDT",
            "IWM": "IWMUSDT",
        }
        if cleaned in mapping:
            return mapping[cleaned]

        base_clean = symbol.replace("/", "").replace("-", "").replace(" ", "").strip().upper()
        if base_clean in mapping:
            return mapping[base_clean]

        return cleaned

    async def get_quote(self, symbol: str) -> Quote:
        """Fetch the latest quote for a single symbol."""
        api_symbol = self._to_api_symbol(symbol)
        data = await self._throttled_request(f"/{api_symbol}")
        ts = self._normalize_timestamp(data.get("timestamp", ""))
        # Determine session type from symbol
        session = self.session_for(symbol)
        realtime = self._determine_realtime(ts, session)
        
        # biquote uses 'mid' as the price for FX/CFD (last/volume are 0)
        price = Decimal(str(data.get("mid", data.get("close", data.get("last", 0)))))
        
        return Quote(
            symbol=symbol,
            last=price,
            bid=Decimal(str(data["bid"])) if data.get("bid") else None,
            ask=Decimal(str(data["ask"])) if data.get("ask") else None,
            volume=int(data.get("volume", 0)) if data.get("volume") else None,
            timestamp=ts,
            source=self.name,
            realtime=realtime,
        )

    async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """Fetch latest quotes for many symbols using batch endpoint."""
        if not symbols:
            return {}
        
        # Use batch endpoint: /api/latest?symbols=EURUSD&symbols=XAUUSD&symbols=BTCUSD
        # Map symbols without slashes for the API call
        api_symbols = [self._to_api_symbol(s) for s in symbols]
        sym_map = {self._to_api_symbol(s): s for s in symbols}
        params = {"symbols": api_symbols}
        data = await self._throttled_request("/latest", params)
        
        results: dict[str, Quote] = {}
        for api_sym, tick in data.items():
            if not isinstance(tick, dict):
                continue
            try:
                ts = self._normalize_timestamp(tick.get("timestamp", ""))
                orig_sym = sym_map.get(api_sym, api_sym)
                session = self.session_for(orig_sym)
                realtime = self._determine_realtime(ts, session)
                price = Decimal(str(tick.get("mid", tick.get("close", tick.get("last", 0)))))
                
                results[orig_sym] = Quote(
                    symbol=orig_sym,
                    last=price,
                    bid=Decimal(str(tick["bid"])) if tick.get("bid") else None,
                    ask=Decimal(str(tick["ask"])) if tick.get("ask") else None,
                    volume=int(tick.get("volume", 0)) if tick.get("volume") else None,
                    timestamp=ts,
                    source=self.name,
                    realtime=realtime,
                )
            except (KeyError, ValueError):
                continue  # Skip malformed entries
        
        return results

    async def get_candles(
        self,
        symbol: str,
        interval: str,
        lookback: int,
        provider_symbol: str | None = None,
    ) -> list[Candle]:
        """Fetch OHLCV candles from biquote."""
        api_symbol = self._to_api_symbol(symbol, provider_symbol)
        bq_interval = _INTERVAL_MAP.get(interval)
        if not bq_interval:
            raise ProviderError(f"unsupported interval {interval!r}")
        max_lb = _MAX_LOOKBACK.get(bq_interval, 1000)
        if lookback > max_lb:
            raise ProviderError(f"lookback {lookback} exceeds max {max_lb} for {interval}")

        data = await self._throttled_request(
            f"/{api_symbol}/ohlc",
            {
                "interval": bq_interval,
                "limit": lookback,
            },
        )
        
        bars = data.get("bars", [])
        if not bars:
            raise ProviderError(f"no candles returned for {api_symbol} {interval}")

        candles: list[Candle] = []
        for row in bars:  # biquote returns oldest first (chronological)
            try:
                ts = self._normalize_timestamp(row["openTime"])
                # Volume: 0 for FX/CFD, real volume for stocks/ETFs
                volume = int(row.get("volume", 0)) if row.get("volume") else 0
                candles.append(
                    Candle(
                        symbol=symbol,  # Use the profile symbol for tracking
                        timestamp=ts,
                        open=Decimal(str(row["open"])),
                        high=Decimal(str(row["high"])),
                        low=Decimal(str(row["low"])),
                        close=Decimal(str(row["close"])),
                        volume=volume,
                        source=self.name,
                    )
                )
            except (KeyError, ValueError) as exc:
                raise ProviderError(f"malformed candle row: {row}") from exc

        if not candles:
            raise ProviderError(f"no valid candles for {api_symbol} {interval}")

        # Always sort candles in ascending chronological order (oldest -> newest)
        candles.sort(key=lambda c: c.timestamp)

        # De-duplicate any candles with identical timestamps
        deduped: list[Candle] = []
        seen_ts = set()
        for c in candles:
            if c.timestamp not in seen_ts:
                seen_ts.add(c.timestamp)
                deduped.append(c)

        return deduped

    # Provider introspection for analyzer/MCP
    def feed_for(self, symbol: str) -> str:
        return "biquote"

    def _normalize_symbol(self, symbol: str) -> str:
        """Map profile symbols to provider symbols for introspection."""
        return self._to_api_symbol(symbol)

    def volume_kind_for(self, symbol: str) -> str:
        """Return volume kind for a symbol."""
        norm = self._normalize_symbol(symbol)
        
        # MT5 source (FX, Metals, Crypto) = tick volume
        if norm in ("XAUUSD", "XAGUSD", "BTCUSD"):
            return "tick"
        
        # aggr source (stocks, ETFs) = consolidated volume
        if norm.endswith("USDT") and norm not in ("BTCUSDT", "ETHUSDT"):  # ETFs/stocks
            return "consolidated"
        
        # Crypto on aggr = venue volume
        if norm in ("BTCUSDT", "ETHUSDT"):
            return "venue"
        
        from market_analyzer.models.profile import AssetClass
        from market_analyzer.pipeline.symbols import parse_custom_symbol
        is_valid, asset_class, _, _, _ = parse_custom_symbol(symbol)
        if is_valid:
            if asset_class == AssetClass.CRYPTO:
                return "venue"
            if asset_class == AssetClass.FX:
                return "tick"
        return "unknown"

    def session_for(self, symbol: str) -> str:
        """Return session type for a symbol."""
        norm = self._normalize_symbol(symbol)
        
        if norm in ("XAUUSD", "XAGUSD"):
            return "fx_metals"
        if norm in ("BTCUSD", "BTCUSDT", "ETHUSDT"):
            return "crypto_24_7"
        
        from market_analyzer.models.profile import AssetClass
        from market_analyzer.pipeline.symbols import parse_custom_symbol
        is_valid, asset_class, _, _, _ = parse_custom_symbol(symbol)
        if is_valid:
            if asset_class == AssetClass.CRYPTO:
                return "crypto_24_7"
            if asset_class == AssetClass.FX:
                return "fx_metals"
        
        # Stocks/ETFs (US equity hours)
        return "equity_us"

    @property
    def volume_is_consolidated(self) -> bool:
        """Biquote provides consolidated volume for stocks/ETFs but tick/venue for FX/Metals/Crypto."""
        return False

    # Additional biquote-specific methods
    async def get_active_symbols(self) -> list[dict]:
        """Get all symbols with live data."""
        return await self._throttled_request("/active")

    async def search_symbols(self, query: str, live_only: bool = False, limit: int = 25) -> list[dict]:
        """Search symbols by name/description."""
        params = {"q": query, "limit": min(limit, 200)}
        if live_only:
            params["liveOnly"] = "true"
        return await self._throttled_request("/symbols/search", params)

    async def get_symbol_info(self, symbol: str) -> dict:
        """Get detailed symbol metadata."""
        return await self._throttled_request(f"/symbols/{symbol}")

    async def get_market_gainers(self, type_: str | None = None, exchange: str | None = None, limit: int = 10) -> dict:
        """Get top gainers."""
        params = {"limit": limit}
        if type_:
            params["type"] = type_
        if exchange:
            params["exchange"] = exchange
        return await self._throttled_request("/market/gainers", params)

    async def get_market_losers(self, type_: str | None = None, exchange: str | None = None, limit: int = 10) -> dict:
        """Get top losers."""
        params = {"limit": limit}
        if type_:
            params["type"] = type_
        if exchange:
            params["exchange"] = exchange
        return await self._throttled_request("/market/losers", params)

    async def get_market_most_active(self, limit: int = 10) -> dict:
        """Get most active by intraday range."""
        return await self._throttled_request("/market/most-active", {"limit": limit})

    async def get_market_summary(self) -> dict:
        """Get overall market snapshot."""
        return await self._throttled_request("/market/summary")

    async def get_news(self, symbol: str | None = None, language: str = "en", country: str = "US", max_results: int = 10) -> list[dict]:
        """Get financial news."""
        params = {"language": language, "country": country, "maxResults": min(max_results, 50)}
        if symbol:
            params["symbol"] = symbol
        return await self._throttled_request("/news/market", params)

    async def get_hn_news(self, query: str | None = None, max_results: int = 10) -> list[dict]:
        """Get Hacker News stories."""
        params = {"maxResults": min(max_results, 50)}
        if query:
            params["q"] = query
        return await self._throttled_request("/news/hn", params)

    async def get_economic_calendar(self, from_date: str | None = None, to_date: str | None = None,
                                     countries: str | None = None, importance: str | None = None,
                                     type_: str | None = None, limit: int = 200) -> list[dict]:
        """Get economic calendar events."""
        params = {"limit": min(limit, 500)}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        if countries:
            params["countries"] = countries
        if importance:
            params["importance"] = importance
        if type_:
            params["type"] = type_
        return await self._throttled_request("/calendar", params)

    async def get_upcoming_events(self, limit: int = 20, countries: str | None = None, importance: str | None = None) -> list[dict]:
        """Get upcoming high-impact events."""
        params = {"limit": min(limit, 500)}
        if countries:
            params["countries"] = countries
        if importance:
            params["importance"] = importance
        return await self._throttled_request("/calendar/upcoming", params)

    async def get_calendar_countries(self) -> list[dict]:
        """Get available country codes."""
        return await self._throttled_request("/calendar/countries")

    async def get_event_history(self, event_id: str, limit: int = 24) -> list[dict]:
        """Get historical releases for a recurring event series."""
        return await self._throttled_request(f"/calendar/{event_id}/history", {"limit": min(limit, 500)})

    async def health_check(self) -> dict:
        """Check service health."""
        return await self._throttled_request("/health")