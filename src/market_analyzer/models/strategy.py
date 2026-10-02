"""Trading strategy and execution playbook schemas.

`StrategyPlan` is the artefact produced by the AI Strategy Planner agent.
It consumes `MarketAnalysis` and `RiskAssessment` to generate tactical,
asymmetric trade playbooks with multi-stage exits and fast breakeven de-risking.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class OrderType(str, Enum):
    LIMIT = "limit"
    STOP_LIMIT = "stop_limit"
    MARKET = "market"


class ExecutionTactic(str, Enum):
    PULLBACK_LIMIT = "pullback_limit"       # Retest of dynamic EMA/support
    BREAKOUT_CONFIRM = "breakout_confirm"   # Structural break confirmation
    MEAN_REVERSION = "mean_reversion"       # Range boundary fade


class ExitStage(BaseModel):
    """A single profit-taking stage."""

    model_config = ConfigDict(frozen=True)

    label: str                              # e.g., "TP1 (Scale 50%)", "TP2 (Scale 30%)", "Runner (20%)"
    target_price: float
    percentage_of_position: Annotated[float, Field(ge=0.0, le=1.0)]
    target_r_multiple: float               # e.g., 1.5, 3.0, 5.0
    trail_rule: str | None = None          # e.g., "Move Stop to Breakeven", "Trail 2x ATR"


class TradePlaybook(BaseModel):
    """Actionable asymmetric trading plan for a specific instrument."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    action: str                             # "LONG" | "SHORT"
    tactic: ExecutionTactic
    order_type: OrderType
    entry_price: float                      # Optimal limit entry
    stop_loss: float                        # Initial hard stop
    breakeven_trigger: float                # Level that shifts stop to entry
    risk_reward_ratio: float                # Blended R:R (minimum 2.5:1 enforced)
    max_loss_usd: float                     # Max risk in dollars
    projected_profit_usd: float             # Blended target profit in dollars
    exit_stages: list[ExitStage] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)
    execution_notes: list[str] = Field(default_factory=list)


class StrategyPlan(BaseModel):
    """Complete portfolio strategy plan across approved candidates."""

    model_config = ConfigDict(frozen=True)

    plan_id: str
    analysis_run_id: str
    risk_run_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    playbooks: list[TradePlaybook] = Field(default_factory=list)
    overall_market_bias: str
    blended_rr_ratio: float
    total_risk_usd: float
    total_target_profit_usd: float
    contingency_plans: list[str] = Field(default_factory=list)
