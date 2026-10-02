"""Validation layer: freshness and sanity checks.

The analyzer is fail-closed. If data is stale, malformed, or too thin, the
instrument is rejected rather than analysed on bad numbers.
"""

from __future__ import annotations

from datetime import datetime, timezone

from market_analyzer.models.analysis import DataQualityReport
from market_analyzer.models.quote import Candle, Quote


# Map interval string to seconds
INTERVAL_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
}


def interval_to_seconds(interval: str) -> int:
    """Convert interval string (e.g., '15m', '1h', '4h') to seconds."""
    return INTERVAL_SECONDS.get(interval, 900)  # default to 15m


def stale_threshold_for_interval(interval: str, base_threshold: int) -> int:
    """
    Calculate staleness threshold for a given interval.
    
    Uses the maximum of:
    - The configured base threshold (e.g., 900s for 15m)
    - 1.5x the interval duration (allows for normal candle formation delay)
    
    This ensures coarser timeframes (4h, 1d) aren't falsely flagged as stale.
    """
    interval_secs = interval_to_seconds(interval)
    return max(base_threshold, int(interval_secs * 1.5))


def candle_age_seconds(candles: list[Candle]) -> float | None:
    if not candles:
        return None
    newest = max(c.timestamp for c in candles)
    return (datetime.now(timezone.utc) - newest).total_seconds()


def validate_candles(
    symbol: str,
    candles: list[Candle],
    stale_after_seconds: int,
    interval: str | None = None,
    session_open: bool = True,
    session_close_utc: datetime | None = None,
) -> list[str]:
    """Return a list of issues. Empty list means the series looks usable."""
    issues: list[str] = []

    if not candles:
        return [f"{symbol}: no candles"]

    timestamps = [c.timestamp for c in candles]
    if timestamps != sorted(timestamps):
        issues.append(f"{symbol}: candles are not in ascending timestamp order")
    if len(set(timestamps)) != len(timestamps):
        issues.append(f"{symbol}: duplicate candle timestamps")

    bad_ohlc = [c.timestamp for c in candles if not c.is_valid_ohlc]
    if bad_ohlc:
        issues.append(f"{symbol}: {len(bad_ohlc)} candle(s) with invalid OHLC ordering")

    non_positive = [c for c in candles if c.close <= 0]
    if non_positive:
        issues.append(f"{symbol}: {len(non_positive)} candle(s) with non-positive close")

    newest = max(c.timestamp for c in candles)
    now = datetime.now(timezone.utc)

    # Use timeframe-aware staleness threshold if interval provided
    effective_stale_after = stale_after_seconds
    if interval:
        effective_stale_after = stale_threshold_for_interval(interval, stale_after_seconds)

    if session_open:
        age = (now - newest).total_seconds()
        if age > effective_stale_after:
            issues.append(f"{symbol}: data is stale ({age:.0f}s > {effective_stale_after}s)")
    else:
        # Outside market hours, bars naturally stop updating after the market closes.
        # Verify the newest bar is from or near the most recent session close.
        if session_close_utc:
            diff_from_close = abs((session_close_utc - newest).total_seconds())
            session_age = (now - session_close_utc).total_seconds()
            if diff_from_close > 7200 or session_age > (5 * 86400):
                issues.append(
                    f"{symbol}: closed session data is outdated ({diff_from_close:.0f}s from close)"
                )
        else:
            closed_max_age = 4 * 86400
            age = (now - newest).total_seconds()
            if age > closed_max_age:
                issues.append(f"{symbol}: closed market data is older than 4 days ({age:.0f}s)")

    return issues


def validate_quote(quote: Quote, stale_after_seconds: int) -> list[str]:
    issues: list[str] = []
    if quote.last <= 0:
        issues.append(f"{quote.symbol}: non-positive quote")
    if quote.bid is not None and quote.ask is not None and quote.bid > quote.ask:
        issues.append(f"{quote.symbol}: crossed market (bid > ask)")
    age = quote.age_seconds
    if age is not None and age > stale_after_seconds:
        issues.append(f"{quote.symbol}: quote is stale ({age:.0f}s)")
    return issues


def build_data_quality_report(
    provider: str,
    realtime: bool,
    requested: list[str],
    failed: set[str],
    stale: set[str],
    issues: list[str],
) -> DataQualityReport:
    return DataQualityReport(
        provider=provider,
        realtime=realtime,
        instruments_requested=len(requested),
        instruments_ok=len(requested) - len(failed) - len(stale),
        instruments_stale=len(stale),
        instruments_failed=len(failed),
        issues=issues[:50],
    )
