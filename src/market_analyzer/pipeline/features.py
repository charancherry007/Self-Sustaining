"""Indicator calculations.

Implemented with pandas/numpy only so results are reproducible across
environments. All thresholds used here are deliberately conservative defaults;
they are meant to be tuned with backtests, not intuition.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from market_analyzer.models.quote import Candle


def to_frame(candles: list[Candle]) -> pd.DataFrame:
    frame = pd.DataFrame(
        [
            {
                "timestamp": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ]
    )
    if frame.empty:
        return frame
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    return frame


def add_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame

    df = frame.copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]

    df["sma_20"] = close.rolling(20, min_periods=10).mean()
    df["sma_50"] = close.rolling(50, min_periods=25).mean()
    df["ema_12"] = close.ewm(span=12, adjust=False).mean()
    df["ema_26"] = close.ewm(span=26, adjust=False).mean()
    df["macd"] = df["ema_12"] - df["ema_26"]
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14, min_periods=7).mean()
    avg_loss = loss.rolling(14, min_periods=7).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    prev_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    df["atr_14"] = true_range.rolling(14, min_periods=7).mean()
    df["atr_pct"] = df["atr_14"] / close * 100

    df["ret_1"] = close.pct_change(1)
    df["ret_5"] = close.pct_change(5)
    df["volatility_20"] = df["ret_1"].rolling(20, min_periods=10).std() * np.sqrt(252)

    df["volume_sma_20"] = df["volume"].rolling(20, min_periods=10).mean()
    df["volume_ratio"] = df["volume"] / df["volume_sma_20"].replace(0, np.nan)

    df["range_20_high"] = high.rolling(20, min_periods=10).max()
    df["range_20_low"] = low.rolling(20, min_periods=10).min()

    # Distance from the 20-period high, used to detect breakouts.
    df["pct_from_high_20"] = (close - df["range_20_high"]) / close * 100

    return df


def latest_row(candles: list[Candle]) -> dict[str, float] | None:
    """Return the most recent indicator values as a plain dict."""
    df = add_indicators(to_frame(candles))
    if df.empty:
        return None
    row = df.iloc[-1]
    return {
        key: (0.0 if pd.isna(value) else float(value))
        for key, value in row.items()
        if key != "timestamp"
    }
