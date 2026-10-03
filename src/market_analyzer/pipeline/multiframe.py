"""Multi-timeframe signal fusion.

Pure functions, no I/O. Input: dict[timeframe] -> indicator dict.
Output: fused metrics + dominant trend + per-TF setup labels.
"""

from __future__ import annotations

from market_analyzer.models.analysis import SetupType, Side
from market_analyzer.pipeline.features import add_indicators, to_frame
from market_analyzer.models.quote import Candle


def compute_mtf_indicators(candles_by_tf: dict[str, list[Candle]]) -> dict[str, dict[str, float]]:
    """Run add_indicators() on each timeframe independently."""
    out = {}
    for tf, candles in candles_by_tf.items():
        if len(candles) < 30:
            continue
        df = add_indicators(to_frame(candles))
        if not df.empty:
            row = df.iloc[-1]
            out[tf] = {
                k: (0.0 if v != v else float(v))
                for k, v in row.items() if k != "timestamp"
            }
    return out


def classify_tf_trend(metrics: dict[str, float]) -> str:
    """Single-TF trend: bullish / bearish / neutral."""
    trend = 0
    if metrics.get("sma_20", 0) > metrics.get("sma_50", 0):
        trend += 1
    else:
        trend -= 1
    if metrics.get("close", 0) > metrics.get("sma_20", 0):
        trend += 1
    else:
        trend -= 1
    if metrics.get("ema_12", 0) > metrics.get("ema_26", 0):
        trend += 1
    else:
        trend -= 1
    if trend >= 2:
        return "bullish"
    if trend <= -2:
        return "bearish"
    return "neutral"


def detect_tf_setup(
    instrument,
    metrics: dict[str, float],
    tf: str,
    allow_volume_gates: bool,
) -> SetupType | None:
    """Return the SetupType for a single timeframe, or None."""
    rsi = metrics.get("rsi_14", 50.0)
    trend = _trend_alignment(metrics)
    vol_pct = metrics.get("atr_pct", 0.0)
    from_high = metrics.get("pct_from_high_20", 0.0)
    ret_5 = metrics.get("ret_5", 0.0)
    volume_ratio = metrics.get("volume_ratio", 0.0)

    # Volume gate
    if allow_volume_gates and (volume_ratio <= 0 or volume_ratio < 0.5):
        return None

    # Breakout: pushing above the 20-bar high on strong volume, in an uptrend.
    if (
        trend > 0.3
        and from_high > -0.5
        and 45 < rsi < 78
        and (not allow_volume_gates or volume_ratio > 1.5)
    ):
        return SetupType.MOMENTUM_BREAKOUT

    # Pullback: uptrend intact, price dipped to support, RSI reset toward 50.
    elif (
        trend > 0.2
        and 0 >= from_high > -3.0
        and 40 <= rsi <= 58
        and (not allow_volume_gates or volume_ratio < 1.0)
    ):
        return SetupType.TREND_PULLBACK

    # Trend continuation: steady upward drift without extreme extension.
    elif trend > 0.4 and ret_5 > 0 and 50 <= rsi <= 72 and vol_pct < 4.0:
        return SetupType.TREND_CONTINUATION

    # Downtrend continuation, only flagged when volatility is not extreme.
    elif trend < -0.5 and ret_5 < 0 and 28 <= rsi <= 50 and vol_pct < 4.0:
        return SetupType.TREND_CONTINUATION

    return None


def _trend_alignment(m: dict[str, float]) -> float:
    """+1 strong uptrend, -1 strong downtrend, 0 mixed."""
    score = 0.0
    if m.get("sma_20", 0) > m.get("sma_50", 0):
        score += 0.5
    else:
        score -= 0.5
    if m.get("close", 0) > m.get("sma_20", 0):
        score += 0.3
    else:
        score -= 0.3
    if m.get("ema_12", 0) > m.get("ema_26", 0):
        score += 0.2
    else:
        score -= 0.2
    return score


def fuse_mtf_signals(
    mtf_metrics: dict[str, dict[str, float]],
    instrument,
    allow_volume_gates: bool,
) -> tuple[dict[str, float], str, dict[str, SetupType]]:
    """
    Core fusion logic.
    Returns: (fused_metrics, dominant_trend, per_tf_setups)
    """
    # 1. Trend per TF
    tf_trends = {tf: classify_tf_trend(m) for tf, m in mtf_metrics.items()}

    # 2. Dominant trend = 4h trend (macro bias)
    dominant = tf_trends.get("4h", "neutral")

    # 3. Trend agreement score (how many TFs agree with 4h)
    agree = sum(1 for t in tf_trends.values() if t == dominant)
    total = len(tf_trends)
    trend_agreement = agree / total if total else 0.0

    # 4. RSI alignment (all TFs in constructive zone?)
    rsi_vals = {tf: m.get("rsi_14", 50) for tf, m in mtf_metrics.items()}
    rsi_alignment = sum(1 for r in rsi_vals.values() if 40 <= r <= 70) / len(rsi_vals) if rsi_vals else 0.0

    # 5. Volume confirmation on 15m (if consolidated)
    vol_conf = 0.0
    if "15m" in mtf_metrics:
        vr = mtf_metrics["15m"].get("volume_ratio", 0)
        vol_conf = 1.0 if vr > 1.2 else (0.5 if vr > 0.8 else 0.0)

    # 6. Per-TF setup labels (for transparency)
    per_tf_setups = {}
    for tf in ("4h", "1h", "15m"):
        if tf in mtf_metrics:
            per_tf_setups[tf] = detect_tf_setup(instrument, mtf_metrics[tf], tf, allow_volume_gates)

    fused = {
        "tf_trend_agreement": trend_agreement,
        "tf_rsi_alignment": rsi_alignment,
        "tf_volume_confirmation": vol_conf,
        "tf_dominant_trend_bullish": 1.0 if dominant == "bullish" else (0.0 if dominant == "bearish" else 0.5),
    }

    return fused, dominant, per_tf_setups


def detect_candidate_mtf(
    instrument,
    mtf_metrics_obj,
    last_price: float,
    allow_volume_gates: bool = True,
    source: str = "provider",
    candles: list | None = None,
):
    """
    Multi-timeframe candidate detection.
    Entry on 15m, filtered by 4h/1h trend alignment.
    Returns a Candidate with mtf_metrics and mtf_setup populated, or None.
    """
    from market_analyzer.models.analysis import Candidate, MultiTimeframeMetrics

    fused = mtf_metrics_obj.fused
    dominant = mtf_metrics_obj.dominant_trend
    per_tf = mtf_metrics_obj.mtf_setup

    # HARD FILTER: 4h trend must support the trade direction
    entry_tf = "15m"
    entry_metrics = mtf_metrics_obj.by_timeframe.get(entry_tf, {})
    if not entry_metrics:
        return None

    # Determine side from 15m setup
    entry_setup = per_tf.get(entry_tf)
    if entry_setup in (SetupType.MOMENTUM_BREAKOUT, SetupType.TREND_PULLBACK, SetupType.TREND_CONTINUATION):
        # For trend continuation, check ret_5 direction
        if entry_setup == SetupType.TREND_CONTINUATION:
            ret_5 = entry_metrics.get("ret_5", 0)
            side = Side.LONG if ret_5 > 0 else Side.SHORT
        else:
            side = Side.LONG
    else:
        return None

    # Trend gate: 4h must agree (or be neutral)
    if dominant == "bearish" and side == Side.LONG:
        return None
    if dominant == "bullish" and side == Side.SHORT:
        return None

    # 1h must not contradict
    tf_1h_trend = classify_tf_trend(mtf_metrics_obj.by_timeframe.get("1h", {}))
    if tf_1h_trend == "bearish" and side == Side.LONG:
        return None
    if tf_1h_trend == "bullish" and side == Side.SHORT:
        return None

    # Now run normal 15m detection with the gated metrics
    # Import here to avoid circular dependency
    from market_analyzer.pipeline.candidates import detect_candidate as detect_candidate_single

    candidate = detect_candidate_single(
        instrument,
        entry_metrics,
        last_price,
        allow_volume_gates=allow_volume_gates,
        source=source,
        candles=candles,
    )
    if candidate:
        # Attach MTF data
        candidate = candidate.model_copy(update={
            "mtf_metrics": mtf_metrics_obj,
            "mtf_setup": per_tf,
        })
    return candidate