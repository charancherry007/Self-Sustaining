"""Candidate setup detection.

Each setup is a pure function of the latest indicator row, so it is fully
deterministic and testable. Thresholds are intentionally strict: the goal is
a short, high-quality list, not a long list of speculative ideas.
"""

from __future__ import annotations

from market_analyzer.models.analysis import Candidate, SetupType, Side
from market_analyzer.models.profile import Instrument

# Reject instruments that are too thin to enter or exit reliably.
MIN_LIQUIDITY_RATIO = 0.5
MAX_SPREAD_BPS = 50.0


def _trend_alignment(m: dict[str, float]) -> float:
    """+1 strong uptrend, -1 strong downtrend, 0 mixed."""
    score = 0.0
    if m["sma_20"] > m["sma_50"]:
        score += 0.5
    else:
        score -= 0.5
    if m["close"] > m["sma_20"]:
        score += 0.3
    else:
        score -= 0.3
    if m["ema_12"] > m["ema_26"]:
        score += 0.2
    else:
        score -= 0.2
    return score


def compute_liquidation_points(
    metrics: dict[str, float],
    last_price: float,
    candles: list[Any] | None = None,
) -> dict[str, float]:
    """Calculate structural liquidation points and liquidity pool levels.

    Liquidation points represent structural price thresholds where stop-loss orders
    and leveraged position liquidations cluster:
      - Upper Liquidation (Buy-Side Liquidity / Short Liquidation Pool):
        Clustered just above recent swing highs / resistance (range_20_high + buffer).
      - Lower Liquidation (Sell-Side Liquidity / Long Liquidation Pool):
        Clustered just below recent swing lows / support (range_20_low - buffer).
      - Estimated 50x high-leverage liquidation boundaries.
    """
    atr = metrics.get("atr_14", 0.0)
    if atr <= 0:
        atr = last_price * 0.015

    range_high = float(metrics.get("range_20_high", last_price))
    range_low = float(metrics.get("range_20_low", last_price))

    if candles and len(candles) >= 10:
        highs = [float(getattr(c, "high", last_price)) for c in candles[-20:]]
        lows = [float(getattr(c, "low", last_price)) for c in candles[-20:]]
        if highs:
            range_high = max(highs)
        if lows:
            range_low = min(lows)

    # Upper liquidation pool: short stop/margin liquidation cluster sitting above swing high
    upper_liq = max(range_high + (0.25 * atr), last_price * 1.002)
    # Lower liquidation pool: long stop/margin liquidation cluster sitting below swing low
    lower_liq = min(range_low - (0.25 * atr), last_price * 0.998)

    # High leverage 50x estimates
    est_50x_short = last_price * 1.02
    est_50x_long = last_price * 0.98

    decimals = 2 if last_price >= 10 else 4
    return {
        "upper": round(upper_liq, decimals),
        "lower": round(lower_liq, decimals),
        "short_cluster": round(max(upper_liq, est_50x_short), decimals),
        "long_cluster": round(min(lower_liq, est_50x_long), decimals),
    }


def compute_breakout_price(
    setup: SetupType,
    side: Side,
    metrics: dict[str, float],
    last_price: float,
) -> float | None:
    """Return the structural breakout price level for momentum breakout setups."""
    if setup == SetupType.MOMENTUM_BREAKOUT:
        if side == Side.SHORT:
            val = float(metrics.get("range_20_low", last_price))
        else:
            val = float(metrics.get("range_20_high", last_price))
        return round(val, 2 if val >= 10 else 4)
    return None


def detect_candidate(
    instrument: Instrument,
    metrics: dict[str, float],
    last_price: float,
    news_sentiment: float | None = None,
    allow_volume_gates: bool = True,
    source: str = "provider",
    candles: list[Any] | None = None,
) -> Candidate | None:
    """Return a candidate if the setup qualifies, else None.

    `news_sentiment` is optional (0..1). When web research is disabled it is
    None and contributes nothing to the decision.

    `allow_volume_gates` must be False on a partial-volume feed (e.g. IEX-only,
    where consolidated volume is unavailable). A self-referential
    `volume_ratio` (current bar vs the instrument's own recent average) stays
    valid on such a feed, but setups whose *entry criteria* are absolute volume
    thresholds are not trustworthy, so they are skipped rather than silently
    producing noise.
    """
    rsi = metrics["rsi_14"]
    trend = _trend_alignment(metrics)
    vol_pct = metrics["atr_pct"]
    from_high = metrics["pct_from_high_20"]
    ret_5 = metrics["ret_5"]

    setup = SetupType.NONE
    side = Side.WATCH
    rationale: list[str] = []
    invalidation: float | None = None
    volume_notes: list[str] = []

    if allow_volume_gates:
        if metrics["volume_ratio"] <= 0 or metrics["volume_ratio"] < MIN_LIQUIDITY_RATIO:
            return None
    else:
        volume_notes.append(
            "volume-gated setups disabled (partial-volume feed); "
            "volume_ratio not used as an entry condition"
        )

    # Breakout: pushing above the 20-bar high on strong volume, in an uptrend.
    if (
        trend > 0.3
        and from_high > -0.5
        and 45 < rsi < 78
        and (not allow_volume_gates or metrics["volume_ratio"] > 1.5)
    ):
        setup = SetupType.MOMENTUM_BREAKOUT
        side = Side.LONG
        invalidation = metrics["sma_20"] * 0.995
        if allow_volume_gates:
            rationale.append(
                f"breakout above 20-bar high with volume ratio {metrics['volume_ratio']:.2f}"
            )
        else:
            rationale.append("breakout above 20-bar high; volume confirmation skipped")

    # Pullback: uptrend intact, price dipped to support, RSI reset toward 50.
    elif (
        trend > 0.2
        and 0 <= from_high < -3.0
        and 40 <= rsi <= 58
        and (not allow_volume_gates or metrics["volume_ratio"] < 1.0)
    ):
        setup = SetupType.TREND_PULLBACK
        side = Side.LONG
        invalidation = metrics["sma_50"] * 0.99
        rationale.append(f"pullback into support within an uptrend, RSI {rsi:.1f}")

    # Trend continuation: steady upward drift without extreme extension.
    elif trend > 0.4 and ret_5 > 0 and 50 <= rsi <= 72 and vol_pct < 4.0:
        setup = SetupType.TREND_CONTINUATION
        side = Side.LONG
        invalidation = metrics["sma_20"] * 0.98
        rationale.append(f"uptrend intact, 5-bar return {ret_5 * 100:.1f}%")

    # Downtrend continuation, only flagged when volatility is not extreme.
    elif trend < -0.5 and ret_5 < 0 and 28 <= rsi <= 50 and vol_pct < 4.0:
        setup = SetupType.TREND_CONTINUATION
        side = Side.SHORT
        invalidation = metrics["sma_20"] * 1.02
        rationale.append(f"downtrend intact, 5-bar return {ret_5 * 100:.1f}%")

    if setup is SetupType.NONE:
        return None

    confidence = min(max((abs(trend) + 0.5) / 1.5, 0.0), 1.0)
    breakout_price = compute_breakout_price(setup, side, metrics, last_price)
    liquidation_points = compute_liquidation_points(metrics, last_price, candles=candles)

    metrics_out = {
        "rsi_14": rsi,
        "trend_alignment": trend,
        "atr_pct": vol_pct,
        "volume_ratio": metrics["volume_ratio"],
        "volatility_20": metrics["volatility_20"],
        "sma_20": metrics["sma_20"],
        "sma_50": metrics["sma_50"],
        "pct_from_high_20": from_high,
        "ret_5": ret_5,
        "liquidation_upper": liquidation_points["upper"],
        "liquidation_lower": liquidation_points["lower"],
    }
    if breakout_price is not None:
        metrics_out["breakout_price"] = breakout_price
        rationale.append(
            f"breakout price: ${breakout_price:,.2f}"
            if breakout_price >= 10
            else f"breakout price: ${breakout_price:,.4f}"
        )

    if news_sentiment is not None:
        metrics_out["news_sentiment"] = news_sentiment
        # Strong negative news downgrades an otherwise long setup to watch.
        if news_sentiment < 0.3 and side is Side.LONG:
            side = Side.WATCH
            rationale.append("downgraded to watch: negative news sentiment")

    return Candidate(
        symbol=instrument.symbol,
        name=instrument.name,
        sector=instrument.sector,
        setup=setup,
        side=side,
        score=0.0,  # filled in by rank.py
        last_price=last_price,
        entry_reference=last_price,
        invalidation=invalidation,
        confidence=confidence,
        breakout_price=breakout_price,
        liquidation_points=liquidation_points,
        rationale=rationale + volume_notes,
        metrics=metrics_out,
        sources=[source],
    )

