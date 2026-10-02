from __future__ import annotations

from market_analyzer.models.analysis import Candidate, SetupType, Side
from market_analyzer.models.profile import ScoringWeights
from market_analyzer.pipeline.rank import rank_candidates, score_candidate


def _candidate(score_side: Side = Side.LONG) -> Candidate:
    return Candidate(
        symbol="AAA.NS",
        name="AAA",
        setup=SetupType.MOMENTUM_BREAKOUT,
        side=score_side,
        score=0.0,
        last_price=1000.0,
        confidence=0.8,
        metrics={
            "rsi_14": 60.0,
            "trend_alignment": 0.8,
            "atr_pct": 2.0,
            "volume_ratio": 2.0,
            "volatility_20": 0.2,
            "ret_5": 0.01,
            "news_sentiment": 0.5,
        },
    )


def test_weights_normalise_to_one():
    normalised = ScoringWeights().normalised()
    assert abs(sum(normalised.values()) - 1.0) < 1e-9


def test_score_within_bounds():
    scored = score_candidate(_candidate(), ScoringWeights(), avg_volume=1_000_000, age_seconds=0)
    assert 0.0 <= scored.score <= 100.0
    assert scored.score > 0


def test_watch_is_capped_below_actionable():
    weights = ScoringWeights()
    long_score = score_candidate(_candidate(Side.LONG), weights, 1_000_000, 0).score
    watch_score = score_candidate(_candidate(Side.WATCH), weights, 1_000_000, 0).score
    assert watch_score <= 60.0
    assert long_score >= watch_score


def test_stale_data_scores_lower():
    weights = ScoringWeights()
    fresh = score_candidate(_candidate(), weights, 1_000_000, 0).score
    stale = score_candidate(_candidate(), weights, 1_000_000, 3000).score
    assert stale < fresh


def test_rank_is_sorted_descending():
    candidates = [_candidate()]
    ranked = rank_candidates(candidates, ScoringWeights(), {"AAA.NS": 1_000_000}, {"AAA.NS": 0})
    assert ranked == sorted(ranked, key=lambda c: c.score, reverse=True)
