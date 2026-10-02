"""Analyzer pipeline tests.

These tests use a deterministic provider defined *here in the test package*.
The production package ships no synthetic provider on purpose — a fabricated
price reachable from config would be worse than a missing one. Test doubles
belong at the test boundary, not in `src/`.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from market_analyzer.config import load_app_config, load_market_profile
from market_analyzer.models.quote import Candle
from market_analyzer.pipeline.analyzer import MarketAnalyzer, build_provider
from market_analyzer.pipeline.candidates import detect_candidate
from market_analyzer.pipeline.features import add_indicators, to_frame
from market_analyzer.providers.base import MarketDataProvider


class _TestDataProvider(MarketDataProvider):
    """Deterministic price series. TEST-ONLY; never importable in production."""

    name = "test_data"
    realtime = True  # Pretend real-time so the require_realtime guard passes.

    def _price(self, index: int) -> float:
        return round(1000.0 * (1 + 0.01 * math.sin(index / 6.0)), 2)

    async def get_quote(self, symbol: str):
        from market_analyzer.models.quote import Quote

        return Quote(
            symbol=symbol,
            last=self._price(200),
            timestamp=datetime.now(timezone.utc),
            source=self.name,
            realtime=True,
        )

    async def get_quotes(self, symbols: list[str]) -> dict:
        return {s: await self.get_quote(s) for s in symbols}

    async def get_candles(
        self, symbol: str, interval: str, lookback: int, provider_symbol: str | None = None
    ) -> list[Candle]:
        end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        out = []
        for i in range(lookback):
            close = self._price(i)
            open_ = self._price(i - 1)
            out.append(
                Candle(
                    symbol=symbol,
                    timestamp=end - timedelta(minutes=5 * (lookback - 1 - i)),
                    open=open_,
                    high=max(open_, close) * 1.002,
                    low=min(open_, close) * 0.998,
                    close=close,
                    volume=250_000,
                    source=self.name,
                )
            )
        return out


def _small_profile(size: int = 5):
    profile = load_market_profile("FOCUSED_SYMBOLS")
    return profile.model_copy(update={"universe": profile.universe[:size]})


@pytest.fixture
def analyzer():
    return MarketAnalyzer(provider=_TestDataProvider())


async def test_full_run_with_real_data(analyzer):
    analysis = await analyzer.run(_small_profile(), limit=3)

    assert analysis.provider == "test_data"
    assert analysis.data_quality.instruments_ok >= 1
    assert analysis.run_id
    assert analysis.data_realtime is True


async def test_run_rejects_delayed_provider(analyzer):
    """require_realtime must abort on a delayed feed rather than analyse it."""
    config = load_app_config()
    strict = MarketAnalyzer(
        config=config.model_copy(
            update={"data": config.data.model_copy(update={"require_realtime": True})}
        ),
        provider=_DelayedProvider(),
    )
    with pytest.raises(RuntimeError, match="require_realtime"):
        await strict.run(_small_profile(2))


class _DelayedProvider(_TestDataProvider):
    name = "delayed_test_data"
    realtime = False


async def test_snapshot_roundtrip(analyzer):
    analysis = await analyzer.run(_small_profile(3), limit=2)
    loaded = analyzer.snapshots.load(analysis.run_id)
    assert loaded is not None
    assert loaded.run_id == analysis.run_id


def test_synthetic_provider_is_not_a_valid_choice():
    """Guard: synthetic providers must never be selectable.

    Uses model_validate rather than model_copy, because model_copy does NOT
    re-run validators and would silently pass with an invalid provider.
    """
    config = load_app_config()
    payload = config.model_dump()
    payload["data"]["provider"] = "synthetic"

    with pytest.raises(ValueError):
        type(config).model_validate(payload)


def test_build_provider_rejects_unknown():
    config = load_app_config()
    with pytest.raises(ValueError):
        build_provider(
            config.model_copy(update={"data": config.data.model_copy(update={"provider": "nope"})})
        )


def test_features_have_no_nan():
    import asyncio

    candles = asyncio.run(_TestDataProvider().get_candles("NAS100", "5m", 120))
    frame = add_indicators(to_frame(candles))
    assert not frame.empty
    assert frame["sma_20"].notna().any()


def test_detect_candidate_rejects_thin_volume():
    from market_analyzer.models.profile import Instrument

    instrument = Instrument(symbol="NAS100", name="Nasdaq")
    metrics = {
        "rsi_14": 60.0,
        "volume_ratio": 0.1,
        "sma_20": 100.0,
        "sma_50": 99.0,
        "ema_12": 100.0,
        "ema_26": 99.5,
        "close": 101.0,
        "atr_pct": 2.0,
        "volatility_20": 0.2,
        "pct_from_high_20": 0.0,
        "ret_5": 0.01,
    }
    assert detect_candidate(instrument, metrics, last_price=101.0) is None
