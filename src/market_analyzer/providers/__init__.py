"""Pluggable market data providers."""

from market_analyzer.providers.base import (
    MarketDataProvider,
    ProviderCapabilities,
    ProviderError,
)
from market_analyzer.providers.fallback import FallbackDataProvider
from market_analyzer.providers.finnhub import FinnhubDataProvider
from market_analyzer.providers.twelvedata import TwelveDataProvider

__all__ = [
    "FallbackDataProvider",
    "FinnhubDataProvider",
    "MarketDataProvider",
    "ProviderCapabilities",
    "ProviderError",
    "TwelveDataProvider",
]
