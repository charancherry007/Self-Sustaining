"""Unit tests for FinnhubDataProvider and FallbackDataProvider."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from market_analyzer.models.quote import Candle, Quote
from market_analyzer.providers.base import ProviderError
from market_analyzer.providers.fallback import FallbackDataProvider, is_rate_limit_error
from market_analyzer.providers.finnhub import FinnhubDataProvider


def test_finnhub_requires_api_key() -> None:
    with pytest.raises(ValueError):
        FinnhubDataProvider(api_key="")


def test_finnhub_symbol_mapping() -> None:
    provider = FinnhubDataProvider(api_key="test_key")
    assert provider._map_symbol("NAS100") == "QQQ"
    assert provider._map_symbol("US500") == "SPY"
    assert provider._map_symbol("XAUUSD") == "GLD"
    assert provider._map_symbol("XAGUSD") == "SLV"
    assert provider._map_symbol("BTCUSD") == "BINANCE:BTCUSDT"
    assert provider._map_symbol("EUR/USD") == "FXE"
    assert provider._map_symbol("AAPL") == "AAPL"


@pytest.mark.asyncio
async def test_finnhub_get_quote_success() -> None:
    provider = FinnhubDataProvider(api_key="test_key")
    mock_payload = {
        "c": 500.25,
        "h": 505.00,
        "l": 498.50,
        "o": 499.00,
        "pc": 497.00,
        "t": 1700000000,
    }

    with patch.object(provider, "_throttled_request", new=AsyncMock(return_value=mock_payload)):
        quote = await provider.get_quote("SPY")
        assert quote.symbol == "SPY"
        assert quote.last == 500.25
        assert quote.bid == 498.50
        assert quote.ask == 505.00
        assert quote.source == "finnhub"
        assert quote.realtime is True


@pytest.mark.asyncio
async def test_finnhub_get_candles_with_synthesis_fallback() -> None:
    provider = FinnhubDataProvider(api_key="test_key")

    mock_quote = Quote(
        symbol="EUR/USD",
        last=1.0850,
        bid=1.0845,
        ask=1.0855,
        timestamp=datetime.now(timezone.utc),
        source="finnhub",
        realtime=True,
    )

    with patch.object(provider, "_throttled_request", side_effect=ProviderError("finnhub access restricted (403)")), \
         patch.object(provider, "get_quote", new=AsyncMock(return_value=mock_quote)):
        candles = await provider.get_candles("EUR/USD", "5m", 30)
        assert len(candles) == 30
        assert candles[-1].close == 1.0850
        assert all(isinstance(c, Candle) for c in candles)


def test_is_rate_limit_error() -> None:
    assert is_rate_limit_error(ProviderError("twelvedata rate limit exceeded (429)"))
    assert is_rate_limit_error(RuntimeError("API error: You have reached your limit of 8 credits per minute"))
    assert is_rate_limit_error(Exception("Too Many Requests"))
    assert not is_rate_limit_error(ValueError("Symbol not found: INVALID"))


@pytest.mark.asyncio
async def test_fallback_provider_switches_on_rate_limit() -> None:
    primary = MagicMock()
    primary.name = "twelvedata"
    primary.realtime = True

    secondary = MagicMock()
    secondary.name = "finnhub"
    secondary.realtime = True

    # Primary raises rate limit error
    primary.get_quote = AsyncMock(side_effect=ProviderError("twelvedata rate limit exceeded (429)"))

    fallback_quote = Quote(
        symbol="EUR/USD",
        last=1.0850,
        timestamp=datetime.now(timezone.utc),
        source="finnhub",
        realtime=True,
    )
    secondary.get_quote = AsyncMock(return_value=fallback_quote)

    fallback = FallbackDataProvider(primary=primary, secondary=secondary)

    # First call encounters rate limit on primary and switches to secondary seamlessly
    result = await fallback.get_quote("EUR/USD")
    assert result.symbol == "EUR/USD"
    assert result.source == "finnhub"
    assert fallback.active_provider_name == "finnhub"
    assert primary.get_quote.call_count == 1
    assert secondary.get_quote.call_count == 1

    # Second call uses secondary directly without hitting primary
    await fallback.get_quote("USD/JPY")
    assert primary.get_quote.call_count == 1  # Not incremented
    assert secondary.get_quote.call_count == 2
