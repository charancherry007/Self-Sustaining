from __future__ import annotations

from datetime import datetime, timedelta, timezone

from market_analyzer.models.quote import Candle
from market_analyzer.pipeline.validate import (
    candle_age_seconds,
    validate_candles,
    validate_quote,
)


def _candles(count: int = 40, stale_minutes: int = 0, price: float = 100.0) -> list[Candle]:
    end = datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)
    out = []
    for i in range(count):
        # i == count-1 is the newest bar, exactly at `end`.
        ts = end - timedelta(minutes=5 * (count - 1 - i))
        out.append(
            Candle(
                symbol="TEST.NS",
                timestamp=ts,
                open=price,
                high=price * 1.01,
                low=price * 0.99,
                close=price,
                volume=1000,
                source="test",
            )
        )
    return out


def test_fresh_candles_pass():
    assert validate_candles("TEST.NS", _candles(), stale_after_seconds=900) == []


def test_stale_candles_are_rejected():
    issues = validate_candles("TEST.NS", _candles(stale_minutes=120), stale_after_seconds=900)
    assert any("stale" in issue for issue in issues)


def test_empty_candles_rejected():
    assert validate_candles("TEST.NS", [], stale_after_seconds=900)


def test_unsorted_candles_flagged():
    candles = _candles()
    issues = validate_candles("TEST.NS", list(reversed(candles)), stale_after_seconds=900)
    assert any("ascending" in issue for issue in issues)


def test_invalid_ohlc_flagged():
    candles = _candles()
    bad = candles[5].model_copy(update={"high": candles[5].low * 0.5})
    candles[5] = bad
    issues = validate_candles("TEST.NS", candles, stale_after_seconds=900)
    assert any("invalid OHLC" in issue for issue in issues)


def test_candle_age_seconds():
    assert candle_age_seconds(_candles()) < 60


def test_crossed_quote_flagged():
    from market_analyzer.models.quote import Quote

    quote = Quote(
        symbol="TEST.NS",
        last=100,
        bid=101,
        ask=99,
        timestamp=datetime.now(timezone.utc),
        source="test",
    )
    issues = validate_quote(quote, stale_after_seconds=900)
    assert any("crossed" in issue for issue in issues)
