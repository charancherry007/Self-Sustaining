"""Twelve Data multi-asset provider.

Covers equities, indices (via ETF proxies), forex, metals, crypto.
Data-only: no trading endpoints, no order placement.

Real-time claims are made only when the API returns fresh timestamps during
the instrument's trading session. The `require_realtime` gate in the analyzer
will reject stale data.
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

BASE_URL = "https://api.twelvedata.com"

# Interval mapping: analyzer interval -> Twelve Data interval
_INTERVAL_MAP = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1day",
}

# Default max lookback per interval (conservative bounds)
_MAX_LOOKBACK = {
    "1min": 7,
    "5min": 60,
    "15min": 200,  # Increased for MTF: ~50 hours = 2+ trading days for 20-period indicators
    "30min": 200,
    "1h": 730,
    "4h": 730,
    "1day": 3650,
}


class TwelveDataProvider(MarketDataProvider):
    name = "twelvedata"
    # Real-time status is determined per-request by checking timestamps.
    # This avoids hard-coding an entitlement assumption.
    realtime = True  # Provider is capable of real-time data (plan-dependent)

    capabilities = ProviderCapabilities(
        realtime=True,
        delayed=True,
        supports_intraday=True,
        supports_daily=True,
        max_intraday_lookback_days=60,
        notes=(
            "Twelve Data API. Real-time depends on account entitlement. "
            "Indices via ETF proxies (QQQ/SPY). "
            "XAG/USD requires Grow+ plan. Volume tick/venue for FX/crypto."
        ),
    )

    def __init__(
        self,
        api_key: str,
        throttle_seconds: float = 0.5,
        timeout_seconds: float = 15.0,
    ) -> None:
        if not api_key:
            raise ProviderError("twelvedata provider requires TWELVEDATA_API_KEY")
        self._api_key = api_key
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

    async def _throttled_request(self, path: str, params: dict) -> dict:
        client = await self._get_client()
        params = {**params, "apikey": self._api_key}
        url = f"{BASE_URL}{path}"
        max_retries = 3

        sym = params.get("symbol", "")
        interval = params.get("interval", "")
        req_details = f"symbol={sym}" + (f", interval={interval}" if interval else "")

        for attempt in range(max_retries):
            now = asyncio.get_event_loop().time()
            wait = self._throttle - (now - self._last_request)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = asyncio.get_event_loop().time()

            log_api_request("TwelveData API", f"GET {path}", req_details)
            start_time = time.perf_counter()

            try:
                resp = await client.get(url, params=params)
                elapsed = time.perf_counter() - start_time

                if resp.status_code == 429:
                    log_api_error("TwelveData API", f"GET {path} [{sym}]", elapsed, "HTTP 429 Rate Limit Exceeded")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(4.0 * (attempt + 1))
                        continue
                    raise ProviderError("twelvedata rate limit exceeded (429)")
                if resp.status_code == 401:
                    log_api_error("TwelveData API", f"GET {path} [{sym}]", elapsed, "HTTP 401 Authentication Failed")
                    raise ProviderError("twelvedata authentication failed (401)")
                if resp.status_code == 403:
                    log_api_error("TwelveData API", f"GET {path} [{sym}]", elapsed, "HTTP 403 Access Denied")
                    raise ProviderError("twelvedata access denied (403) - check plan entitlements")
                if resp.status_code == 404:
                    log_api_error("TwelveData API", f"GET {path} [{sym}]", elapsed, "HTTP 404 Symbol Not Found")
                    raise ProviderError(
                        f"twelvedata symbol not found: {params.get('symbol', 'unknown')}"
                    )
                if resp.status_code >= 400:
                    log_api_error("TwelveData API", f"GET {path} [{sym}]", elapsed, f"HTTP {resp.status_code}")
                    raise ProviderError(f"twelvedata HTTP {resp.status_code}: {resp.text[:200]}")

                data = resp.json()
                if data.get("status") == "error":
                    msg = data.get("message", "unknown error")
                    log_api_error("TwelveData API", f"GET {path} [{sym}]", elapsed, f"API error: {msg}")
                    if any(w in msg.lower() for w in ("minute", "limit", "credits", "try again")) and attempt < max_retries - 1:
                        await asyncio.sleep(5.0 * (attempt + 1))
                        continue
                    if "plan" in msg.lower() or "upgrade" in msg.lower():
                        raise ProviderError(f"twelvedata plan restriction: {msg}")
                    raise ProviderError(f"twelvedata error: {msg}")

                vals = len(data.get("values", []))
                resp_info = f"{vals} candles" if vals else ("quote" if "close" in data or "last" in data else "OK")
                log_api_response("TwelveData API", f"GET {path} [{sym}]", elapsed, resp.status_code, resp_info)
                return data
            except httpx.HTTPError as exc:
                elapsed = time.perf_counter() - start_time
                log_api_error("TwelveData API", f"GET {path} [{sym}]", elapsed, f"Request failed: {exc}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2.0)
                    continue
                raise ProviderError(f"twelvedata request failed: {exc}") from exc
        raise ProviderError("twelvedata request failed after retries")

    def _get_calendar(self, session: str) -> MarketCalendar:
        return get_calendar(session)

    def _session_state(self, symbol: str, instrument_session: str) -> SessionState:
        cal = self._get_calendar(instrument_session)
        return cal.state(datetime.now(timezone.utc))

    def _is_session_open(self, instrument_session: str) -> bool:
        return self._session_state("", instrument_session) is SessionState.OPEN

    def _normalize_timestamp(self, ts_str: str) -> datetime:
        """Parse Twelve Data timestamp strings to UTC-aware datetime."""
        # Formats: '2026-10-01 17:05:00' or '2026-09-30'
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(ts_str, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        # Fallback: try ISO format
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))

    def _determine_realtime(self, quote_ts: datetime, instrument_session: str) -> bool:
        """Check if quote timestamp is fresh for the instrument's session."""
        now = datetime.now(timezone.utc)
        age = (now - quote_ts).total_seconds()
        if self._is_session_open(instrument_session):
            return age <= 30  # within 30 seconds during open session
        # Outside session: last quote could be from previous close
        return age <= 3600  # within 1 hour of session close

    async def get_quote(self, symbol: str) -> Quote:
        data = await self._throttled_request("/quote", {"symbol": symbol, "timezone": "UTC"})
        ts = self._normalize_timestamp(data.get("datetime", ""))
        realtime = self._determine_realtime(ts, "equity_us")  # default; override in get_quotes
        return Quote(
            symbol=symbol,
            last=Decimal(str(data.get("close", data.get("last", 0)))),
            bid=Decimal(str(data.get("bid", 0))) if data.get("bid") else None,
            ask=Decimal(str(data.get("ask", 0))) if data.get("ask") else None,
            volume=int(data.get("volume", 0)) if data.get("volume") else None,
            timestamp=ts,
            source="twelvedata",
            realtime=realtime,
        )

    async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        # Twelve Data doesn't have a batch quote endpoint; iterate
        results: dict[str, Quote] = {}
        for sym in symbols:
            try:
                results[sym] = await self.get_quote(sym)
            except ProviderError:
                # Skip unavailable symbols rather than failing the whole batch
                continue
        return results

    async def get_candles(
        self,
        symbol: str,
        interval: str,
        lookback: int,
        provider_symbol: str | None = None,
    ) -> list[Candle]:
        # Use provider_symbol for the API call if provided (e.g., "QQQ" for "NAS100")
        api_symbol = provider_symbol or symbol
        td_interval = _INTERVAL_MAP.get(interval)
        if not td_interval:
            raise ProviderError(f"unsupported interval {interval!r}")
        max_lb = _MAX_LOOKBACK.get(td_interval, 60)
        if lookback > max_lb:
            raise ProviderError(f"lookback {lookback} exceeds max {max_lb} for {interval}")

        try:
            data = await self._throttled_request(
                "/time_series",
                {
                    "symbol": api_symbol,
                    "interval": td_interval,
                    "outputsize": lookback,
                    "timezone": "UTC",
                },
            )
        except ProviderError:
            if api_symbol in ("XAG/USD", "XAGUSD"):
                # Fallback to SLV ETF proxy if XAG/USD is not covered by current subscription
                data = await self._throttled_request(
                    "/time_series",
                    {
                        "symbol": "SLV",
                        "interval": td_interval,
                        "outputsize": lookback,
                        "timezone": "UTC",
                    },
                )
            else:
                raise
        values = data.get("values", [])
        if not values:
            raise ProviderError(f"no candles returned for {api_symbol} {interval}")

        candles: list[Candle] = []
        for row in reversed(values):  # API returns newest first; we need oldest first
            try:
                ts = self._normalize_timestamp(row["datetime"])
                candles.append(
                    Candle(
                        symbol=symbol,  # Use the profile symbol for tracking
                        timestamp=ts,
                        open=Decimal(str(row["open"])),
                        high=Decimal(str(row["high"])),
                        low=Decimal(str(row["low"])),
                        close=Decimal(str(row["close"])),
                        volume=int(row.get("volume", 0)) if row.get("volume") else 0,
                        source=self.name,
                    )
                )
            except (KeyError, ValueError) as exc:
                raise ProviderError(f"malformed candle row: {row}") from exc

        if not candles:
            raise ProviderError(f"no valid candles for {api_symbol} {interval}")
        return candles

    # Provider introspection for analyzer/MCP
    def feed_for(self, symbol: str) -> str:
        return "twelvedata"

    def _normalize_symbol(self, symbol: str) -> str:
        """Map profile symbols to provider symbols for introspection."""
        mapping = {
            "XAUUSD": "XAU/USD",
            "XAGUSD": "XAG/USD",
            "BTCUSD": "BTC/USD",
            "NAS100": "QQQ",
            "US500": "SPY",
        }
        if symbol in mapping:
            return mapping[symbol]
        from market_analyzer.pipeline.symbols import parse_custom_symbol
        is_valid, _, provider_sym, _, _ = parse_custom_symbol(symbol)
        if is_valid and provider_sym:
            return provider_sym
        return symbol

    def volume_kind_for(self, symbol: str) -> str:
        norm = self._normalize_symbol(symbol)
        if norm in ("XAU/USD", "XAG/USD"):
            return "tick"
        if norm == "BTC/USD":
            return "venue"
        from market_analyzer.models.profile import AssetClass
        from market_analyzer.pipeline.symbols import parse_custom_symbol
        is_valid, asset_class, _, _, _ = parse_custom_symbol(symbol)
        if is_valid:
            if asset_class == AssetClass.CRYPTO:
                return "venue"
            if asset_class == AssetClass.FX:
                return "tick"
        return "consolidated"

    def session_for(self, symbol: str) -> str:
        norm = self._normalize_symbol(symbol)
        if norm == "XAU/USD":
            return "fx_metals"
        if norm == "BTC/USD":
            return "crypto_24_7"
        # XAG/USD proxies to SLV ETF on standard plan, which trades US equity hours
        if norm in ("XAG/USD", "XAGUSD", "SLV"):
            return "equity_us"
        from market_analyzer.models.profile import AssetClass
        from market_analyzer.pipeline.symbols import parse_custom_symbol
        is_valid, asset_class, _, _, _ = parse_custom_symbol(symbol)
        if is_valid:
            if asset_class == AssetClass.CRYPTO:
                return "crypto_24_7"
            if asset_class == AssetClass.FX:
                return "fx_metals"
        return "equity_us"

    @property
    def volume_is_consolidated(self) -> bool:
        """Whether this provider's feed carries consolidated market volume.

        Twelve Data provides consolidated volume for equities/ETFs but tick/venue
        volume for FX, metals, and crypto. Since the focused profile includes
        non-equity assets, we return False to be conservative.
        """
        return False