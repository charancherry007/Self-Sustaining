"""Unit tests for the AI Strategy Planner and asymmetric execution playbooks."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from market_analyzer.ai.base import AiAnalyst
from market_analyzer.models.analysis import (
    Candidate,
    DataQualityReport,
    MarketAnalysis,
    MarketRegime,
    SetupType,
    Side,
)
from market_analyzer.models.risk import (
    PositionSize,
    RiskAction,
    RiskAssessment,
)
from market_analyzer.models.strategy import (
    ExecutionTactic,
    OrderType,
    StrategyPlan,
)
from market_analyzer.strategy.planner import StrategyPlanner


def _make_mock_analysis() -> MarketAnalysis:
    cand_nas = Candidate(
        symbol="NAS100",
        name="Nasdaq 100",
        setup=SetupType.TREND_PULLBACK,
        side=Side.LONG,
        score=85.0,
        last_price=20000.0,
        confidence=0.88,
        metrics={"rsi_14": 46.5, "atr_14": 150.0},
    )
    cand_gold = Candidate(
        symbol="XAUUSD",
        name="Gold Spot",
        setup=SetupType.MOMENTUM_BREAKOUT,
        side=Side.LONG,
        score=78.0,
        last_price=2650.0,
        confidence=0.82,
        metrics={"rsi_14": 62.0, "atr_14": 25.0},
    )
    return MarketAnalysis(
        run_id="test-run-1",
        profile_id="FOCUSED_SYMBOLS",
        generated_at=datetime.now(timezone.utc),
        data_as_of=datetime.now(timezone.utc),
        data_realtime=True,
        provider="twelvedata",
        regime=MarketRegime.BULLISH,
        summary="Bullish continuation with pullbacks across tech and gold.",
        candidates=[cand_nas, cand_gold],
        data_quality=DataQualityReport(
            provider="twelvedata",
            realtime=True,
            instruments_requested=2,
            instruments_ok=2,
            instruments_stale=0,
            instruments_failed=0,
        ),
    )


def _make_mock_assessment() -> RiskAssessment:
    pos_nas = PositionSize(
        symbol="NAS100",
        action=RiskAction.APPROVE,
        size_pct_equity=0.03,
        size_units=0.15,
        stop_loss=19800.0,
        take_profit=20500.0,
        risk_pct_equity=0.003,
        rationale=["Solid risk profile with clean ATR invalidation"],
    )
    pos_gold = PositionSize(
        symbol="XAUUSD",
        action=RiskAction.REDUCE,
        size_pct_equity=0.02,
        size_units=0.75,
        stop_loss=2620.0,
        take_profit=2720.0,
        risk_pct_equity=0.002,
        rationale=["Position reduced for portfolio heat limits"],
    )
    return RiskAssessment(
        run_id="test-risk-1",
        analysis_run_id="test-run-1",
        risk_profile_id="CONSERVATIVE",
        generated_at=datetime.now(timezone.utc),
        portfolio_equity=100_000.0,
        portfolio_heat_pct=0.005,
        approved=[pos_nas],
        reduced=[pos_gold],
        deferred=[],
        rejected=[],
        correlation_warnings=[],
        regime_adjustment=1.0,
    )


@pytest.mark.asyncio
async def test_deterministic_strategy_planner():
    """Verify deterministic strategy planning produces asymmetric R:R >= 2.5:1."""
    analysis = _make_mock_analysis()
    assessment = _make_mock_assessment()

    # Pass disabled AI analyst to trigger deterministic calculation
    mock_ai = AsyncMock(spec=AiAnalyst)
    mock_ai.enabled = False

    planner = StrategyPlanner(ai=mock_ai)
    plan: StrategyPlan = await planner.plan(analysis, assessment, portfolio_equity=100_000.0)

    assert plan.plan_id.startswith("strat-")
    assert len(plan.playbooks) == 2
    assert plan.blended_rr_ratio >= 2.5

    for pb in plan.playbooks:
        assert pb.risk_reward_ratio >= 2.5
        assert pb.tactic == ExecutionTactic.PULLBACK_LIMIT
        assert pb.order_type == OrderType.LIMIT
        assert pb.max_loss_usd > 0
        assert pb.projected_profit_usd >= pb.max_loss_usd * 2.5

        # Check exit stages
        assert len(pb.exit_stages) == 3
        weights = sum(s.percentage_of_position for s in pb.exit_stages)
        assert pytest.approx(weights, 0.01) == 1.0

        # Check TP1 breakeven trigger
        tp1 = pb.exit_stages[0]
        assert tp1.percentage_of_position == 0.50
        assert tp1.target_r_multiple == 1.5
        assert "Breakeven" in (tp1.trail_rule or "")

        # Check invalidation notes
        assert len(pb.invalidation_conditions) >= 1
        assert len(pb.execution_notes) >= 1


@pytest.mark.asyncio
async def test_empty_positions_strategy_plan():
    """Verify empty positions generate a neutral observational plan."""
    analysis = _make_mock_analysis()
    empty_assessment = RiskAssessment(
        run_id="test-risk-empty",
        analysis_run_id="test-run-1",
        risk_profile_id="CONSERVATIVE",
        generated_at=datetime.now(timezone.utc),
        portfolio_equity=100_000.0,
        portfolio_heat_pct=0.0,
        approved=[],
        reduced=[],
        deferred=[],
        rejected=[],
        correlation_warnings=[],
        regime_adjustment=0.5,
    )

    mock_ai = AsyncMock(spec=AiAnalyst)
    mock_ai.enabled = False

    planner = StrategyPlanner(ai=mock_ai)
    plan = await planner.plan(analysis, empty_assessment)

    assert len(plan.playbooks) == 0
    assert plan.blended_rr_ratio == 0.0
    assert len(plan.contingency_plans) > 0


@pytest.mark.asyncio
async def test_ai_strategy_planner_mock():
    """Verify AI response parsing and validation."""
    analysis = _make_mock_analysis()
    assessment = _make_mock_assessment()

    mock_ai_json = """
    {
      "overall_market_bias": "BULLISH",
      "contingency_plans": ["Monitor bond yields"],
      "playbooks": [
        {
          "symbol": "NAS100",
          "action": "LONG",
          "tactic": "pullback_limit",
          "order_type": "limit",
          "entry_price": 19950.0,
          "stop_loss": 19800.0,
          "breakeven_trigger": 20175.0,
          "risk_reward_ratio": 3.2,
          "exit_stages": [
            {
              "label": "TP1 (Scale 50%)",
              "target_price": 20175.0,
              "percentage_of_position": 0.50,
              "target_r_multiple": 1.5,
              "trail_rule": "Move Stop Loss to Entry Price ($19,950.00)"
            },
            {
              "label": "TP2 (Scale 30%)",
              "target_price": 20400.0,
              "percentage_of_position": 0.30,
              "target_r_multiple": 3.0,
              "trail_rule": "Hold runner"
            },
            {
              "label": "Runner (Hold 20%)",
              "target_price": 20700.0,
              "percentage_of_position": 0.20,
              "target_r_multiple": 5.0,
              "trail_rule": "Trail 2x ATR behind 20-EMA"
            }
          ],
          "invalidation_conditions": ["Loss of 19,800 prior to fill"],
          "execution_notes": ["Limit order at pullback level"]
        }
      ]
    }
    """

    mock_ai = AsyncMock(spec=AiAnalyst)
    mock_ai.enabled = True
    mock_ai.chat = AsyncMock(return_value=mock_ai_json)

    planner = StrategyPlanner(ai=mock_ai)
    plan = await planner.plan(analysis, assessment, portfolio_equity=100_000.0)

    assert plan.overall_market_bias == "BULLISH"
    assert len(plan.playbooks) == 1
    assert plan.playbooks[0].symbol == "NAS100"
    assert plan.playbooks[0].risk_reward_ratio >= 2.5
    assert plan.playbooks[0].exit_stages[0].percentage_of_position == 0.50
