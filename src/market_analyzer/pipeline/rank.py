"""Weighted candidate ranking.

Each component is normalised to 0..1, then combined using the weights defined
in the market profile YAML. Keeping weights in config means the strategy can
be tuned (and backtested) without editing code.
"""

from __future__ import annotations

from market_analyzer.models.analysis import Candidate, Side
from market_analyzer.models.profile import ScoringWeights

# Liquidity: log-scaled average volume relative to a large-cap baseline.
# Values below ~1.0 get near-zero scores; above ~1.0 saturate near 1.0.
_LIQ_LOG_BASELINE = 16.0

# Returned instead of a log-scaled score when absolute volume cannot be
# trusted (partial-volume feeds such as IEX-only).
_NEUTRAL_LIQUIDITY = 0.5


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def mtf_trend_agreement_score(candidate: Candidate) -> float:
    """Score based on multi-timeframe trend agreement (0..1)."""
    if not candidate.mtf_metrics:
        return 0.5  # neutral when MTF not available
    return _clamp01(candidate.mtf_metrics.fused.get("tf_trend_agreement", 0.5))


def mtf_rsi_alignment_score(candidate: Candidate) -> float:
    """Score based on RSI alignment across timeframes (0..1)."""
    if not candidate.mtf_metrics:
        return 0.5  # neutral when MTF not available
    return _clamp01(candidate.mtf_metrics.fused.get("tf_rsi_alignment", 0.5))


def mtf_volume_confirmation_score(candidate: Candidate) -> float:
    """Score based on volume confirmation on entry timeframe (0..1)."""
    if not candidate.mtf_metrics:
        return 0.5  # neutral when MTF not available
    return _clamp01(candidate.mtf_metrics.fused.get("tf_volume_confirmation", 0.5))


def liquidity_score(candidate: Candidate, avg_volume: float, use_absolute: bool = True) -> float:
    """Score liquidity from absolute traded volume.

    `use_absolute=False` returns a neutral constant. Required on feeds where
    volume is not consolidated (IEX-only): the absolute numbers are a fraction
    of the real market, and the log baseline below was calibrated against
    consolidated volume, so scoring them would systematically understate every
    instrument rather than fail loudly.
    """
    if not use_absolute:
        return _NEUTRAL_LIQUIDITY

    import math

    if avg_volume <= 0:
        return 0.0
    return _clamp01(math.log10(avg_volume + 1) / _LIQ_LOG_BASELINE)


def trend_score(candidate: Candidate) -> float:
    trend = candidate.metrics.get("trend_alignment", 0.0)
    direction = 1.0 if candidate.side in (Side.LONG, Side.SHORT) else 0.5
    return _clamp01(abs(trend) * direction)


def momentum_score(candidate: Candidate) -> float:
    rsi = candidate.metrics.get("rsi_14", 50.0)
    ret_5 = candidate.metrics.get("ret_5", 0.0)
    # Prefer constructive RSI without being overbought.
    rsi_component = 1.0 - abs(rsi - 60.0) / 40.0
    return _clamp01(0.6 * rsi_component + 0.4 * _clamp01(ret_5 * 20 + 0.5))


def volatility_score(candidate: Candidate) -> float:
    atr_pct = candidate.metrics.get("atr_pct", 0.0)
    # Penalise both dead and violent instruments.
    return _clamp01(1.0 - abs(atr_pct - 2.0) / 6.0)


def freshness_score(candidate: Candidate, age_seconds: float | None) -> float:
    if age_seconds is None:
        return 0.0
    return _clamp01(1.0 - age_seconds / 600.0)


def news_score(candidate: Candidate) -> float:
    return _clamp01(candidate.metrics.get("news_sentiment", 0.5))


def score_candidate(
    candidate: Candidate,
    weights: ScoringWeights,
    avg_volume: float,
    age_seconds: float | None,
    use_absolute_volume: bool = True,
) -> Candidate:
    components = {
        "liquidity": liquidity_score(candidate, avg_volume, use_absolute_volume),
        "trend_alignment": trend_score(candidate),
        "momentum": momentum_score(candidate),
        "volatility_fit": volatility_score(candidate),
        "data_freshness": freshness_score(candidate, age_seconds),
        "news_sentiment": news_score(candidate),
        # Multi-timeframe components (neutral when MTF not available)
        "mtf_trend_agreement": mtf_trend_agreement_score(candidate),
        "mtf_rsi_alignment": mtf_rsi_alignment_score(candidate),
        "mtf_volume_confirmation": mtf_volume_confirmation_score(candidate),
    }
    normalised = weights.normalised()
    total = sum(normalised[key] * value for key, value in components.items())
    # Watch-only candidates are capped so actionable setups always rank higher.
    cap = 60.0 if candidate.side is Side.WATCH else 100.0
    return candidate.model_copy(update={"score": round(total * cap, 2)})


def rank_candidates(
    candidates: list[Candidate],
    weights: ScoringWeights,
    volumes: dict[str, float],
    ages: dict[str, float | None],
    use_absolute_volume: bool = True,
) -> list[Candidate]:
    scored = [
        score_candidate(
            candidate,
            weights,
            volumes.get(candidate.symbol, 0.0),
            ages.get(candidate.symbol),
            use_absolute_volume,
        )
        for candidate in candidates
    ]
    return sorted(scored, key=lambda c: c.score, reverse=True)
