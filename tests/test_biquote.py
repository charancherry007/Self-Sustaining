"""Unit tests for BiquoteProvider."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from market_analyzer.models.quote import Candle
from market_analyzer.providers.biquote import BiquoteProvider


def test_biquote_initialization() -> None:
    provider = BiquoteProvider(throttle_seconds=0.05)
    assert provider.name == "biquote"
    assert provider.realtime is True
    assert provider.capabilities.realtime is True
    assert provider.capabilities.supports_intraday is True
    assert provider.capabilities.supports_daily is True


def test_biquote_normalize_timestamp() -> None:
    provider = BiquoteProvider()
    dt = provider._normalize_timestamp("2026-10-02T20:00:00Z")
    assert dt.year == 2026
    assert dt.month == 10
    assert dt.day == 2
    assert dt.hour == 20
    assert dt.tzinfo is not None


def test_biquote_to_api_symbol() -> None:
    provider = BiquoteProvider()
    assert provider._to_api_symbol("BTCUSDT") == "BTCUSDT"
    assert provider._to_api_symbol("BTC/USDT") == "BTCUSDT"
    assert provider._to_api_symbol("BTC/USD") == "BTCUSD"
    assert provider._to_api_symbol("BTCUSD") == "BTCUSD"
    assert provider._to_api_symbol("XAUUSD", provider_symbol="XAU/USD") == "XAUUSD"
    assert provider._to_api_symbol("XAGUSD", provider_symbol="XAG/USD") == "XAGUSD"
    assert provider._to_api_symbol("NAS100") == "QQQUSDT"
    assert provider._to_api_symbol("US500") == "SPYUSDT"
    assert provider._to_api_symbol("NAS100", provider_symbol="QQQ") == "QQQUSDT"
    assert provider._to_api_symbol("US500", provider_symbol="SPY") == "SPYUSDT"
    assert provider._to_api_symbol("EUR/USD") == "EURUSD"


@pytest.mark.asyncio
async def test_biquote_get_quote() -> None:
    provider = BiquoteProvider()
    mock_payload = {
        "timestamp": "2026-10-02T20:00:00Z",
        "mid": 1.0850,
        "bid": 1.0848,
        "ask": 1.0852,
        "volume": 1200,
    }

    with patch.object(provider, "_throttled_request", new=AsyncMock(return_value=mock_payload)):
        quote = await provider.get_quote("EURUSD")
        assert quote.symbol == "EURUSD"
        assert quote.last == 1.085
        assert quote.bid == 1.0848
        assert quote.ask == 1.0852
        assert quote.volume == 1200
        assert quote.source == "biquote"


@pytest.mark.asyncio
async def test_biquote_get_quotes_batch() -> None:
    provider = BiquoteProvider()
    mock_payload = {
        "EURUSD": {
            "timestamp": "2026-10-02T20:00:00Z",
            "mid": 1.0850,
            "bid": 1.0848,
            "ask": 1.0852,
            "volume": 500,
        },
        "BTCUSD": {
            "timestamp": "2026-10-02T20:00:00Z",
            "mid": 65000.0,
            "bid": 64990.0,
            "ask": 65010.0,
            "volume": 25,
        },
    }

    with patch.object(provider, "_throttled_request", new=AsyncMock(return_value=mock_payload)):
        quotes = await provider.get_quotes(["EURUSD", "BTCUSD"])
        assert "EURUSD" in quotes
        assert "BTCUSD" in quotes
        assert quotes["EURUSD"].last == 1.085
        assert quotes["BTCUSD"].last == 65000.0


@pytest.mark.asyncio
async def test_biquote_get_candles() -> None:
    provider = BiquoteProvider()
    mock_payload = {
        "bars": [
            {
                "openTime": "2026-10-02T19:55:00Z",
                "open": 1.0840,
                "high": 1.0855,
                "low": 1.0835,
                "close": 1.0850,
                "volume": 100,
            },
            {
                "openTime": "2026-10-02T20:00:00Z",
                "open": 1.0850,
                "high": 1.0860,
                "low": 1.0845,
                "close": 1.0855,
                "volume": 150,
            },
        ]
    }

    with patch.object(provider, "_throttled_request", new=AsyncMock(return_value=mock_payload)):
        candles = await provider.get_candles("EURUSD", "5m", 2)
        assert len(candles) == 2
        assert candles[0].close == 1.0850
        assert candles[1].close == 1.0855
        assert all(isinstance(c, Candle) for c in candles)
