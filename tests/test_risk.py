"""Tests for AI-only risk assessment engine."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from market_analyzer.models.analysis import (
    Candidate,
    DataQualityReport,
    MarketAnalysis,
    MarketRegime,
    SetupType,
    Side,
)
from market_analyzer.models.risk import RiskAction
from market_analyzer.risk.ai import AiRiskAnalyst
from market_analyzer.risk.engine import RiskEngine


def _sample_analysis(realtime: bool = True) -> MarketAnalysis:
    cand1 = Candidate(
        symbol="BTCUSD",
        name="Bitcoin",
        setup=SetupType.MOMENTUM_BREAKOUT,
        side=Side.LONG,
        score=85.0,
        last_price=85000.0,
        confidence=0.9,
        metrics={"atr_14": 1500.0, "volume_ratio": 1.5, "rsi_14": 62.0},
    )
    cand2 = Candidate(
        symbol="XAUUSD",
        name="Gold",
        setup=SetupType.TREND_PULLBACK,
        side=Side.LONG,
        score=78.0,
        last_price=4175.0,
        confidence=0.85,
        metrics={"atr_14": 30.0, "volume_ratio": 1.2, "rsi_14": 55.0},
    )
    return MarketAnalysis(
        run_id="test_run_123",
        profile_id="FOCUSED_SYMBOLS",
        generated_at=datetime.now(timezone.utc),
        data_as_of=datetime.now(timezone.utc),
        data_realtime=realtime,
        provider="twelvedata",
        regime=MarketRegime.BULLISH,
        regime_rationale=["Equities above 50 SMA", "Risk tone positive"],
        summary="Positive trend across multi-asset focus universe.",
        candidates=[cand1, cand2],
        data_quality=DataQualityReport(
            provider="twelvedata",
            realtime=realtime,
            instruments_requested=2,
            instruments_ok=2,
        ),
    )


class _StubAiAnalyst:
    """Mock AI Analyst returning structured risk decisions."""

    name = "stub_ai"
    enabled = True
    models = ("stub-model",)

    async def chat(self, prompt: str, **kwargs) -> str:
        return """{
            "portfolio_heat_pct": 0.025,
            "correlation_warnings": ["BTC and Gold show low correlation: good diversification"],
            "decisions": [
                {
                    "symbol": "BTCUSD",
                    "action": "approve",
                    "size_pct_equity": 0.02,
                    "size_units": 0.0235,
                    "stop_loss": 83000.0,
                    "take_profit": 89000.0,
                    "risk_pct_equity": 0.005,
                    "rationale": ["High quality momentum breakout", "Tight stop"]
                },
                {
                    "symbol": "XAUUSD",
                    "action": "reduce",
                    "size_pct_equity": 0.01,
                    "size_units": 0.239,
                    "stop_loss": 4120.0,
                    "take_profit": 4280.0,
                    "risk_pct_equity": 0.003,
                    "rationale": ["Pullback setup valid but approaching overhead resistance"]
                }
            ],
            "ai_narrative": {
                "regime_interpretation": "Bullish expansion regime",
                "tail_risks": ["Fed announcement next week"],
                "candidate_commentary": {"BTCUSD": "Leading breakout", "XAUUSD": "Hedge"},
                "sizing_rationale": {"BTCUSD": "Full 2% size", "XAUUSD": "Reduced to 1%"},
                "confidence": 0.92
            }
        }"""


@pytest.mark.asyncio
async def test_risk_hard_gate_rejects_delayed_feed():
    engine = RiskEngine()
    delayed_analysis = _sample_analysis(realtime=False)
    with pytest.raises(RuntimeError, match="requires real-time data"):
        await engine.assess(delayed_analysis)


@pytest.mark.asyncio
async def test_ai_risk_engine_assesses_and_sizes_candidates():
    mock_ai_risk_analyst = AiRiskAnalyst(ai=_StubAiAnalyst())
    engine = RiskEngine(ai_analyst=mock_ai_risk_analyst)
    analysis = _sample_analysis(realtime=True)

    assessment = await engine.assess(
        analysis=analysis,
        risk_profile_id="CONSERVATIVE",
        portfolio_equity=100000.0,
        open_positions={},
    )

    assert assessment.analysis_run_id == analysis.run_id
    assert assessment.portfolio_equity == 100000.0
    assert len(assessment.approved) == 1
    assert assessment.approved[0].symbol == "BTCUSD"
    assert assessment.approved[0].action == RiskAction.APPROVE
    assert assessment.approved[0].size_pct_equity == 0.02
    assert assessment.approved[0].stop_loss == 83000.0

    assert len(assessment.reduced) == 1
    assert assessment.reduced[0].symbol == "XAUUSD"
    assert assessment.reduced[0].action == RiskAction.REDUCE

    assert assessment.portfolio_heat_pct == 0.025
    assert len(assessment.correlation_warnings) >= 1
    assert assessment.ai_narrative is not None
    assert assessment.ai_narrative.confidence == 0.92
    assert "AI_RISK_ANALYZER" in assessment.risk_rules_applied
