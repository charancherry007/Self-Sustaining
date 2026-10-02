"""Risk assessment schemas.

`RiskAssessment` is the single artefact handed to the Execution component.
It carries deterministic sizing, AI advisory narrative (marked untrusted),
and full audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class RiskAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    REDUCE = "reduce"          # Size cut but not zero
    DEFER = "defer"            # Wait for better entry / more data


class PositionSize(BaseModel):
    """Sizing decision for a single candidate."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    action: RiskAction
    size_pct_equity: Annotated[float, Field(ge=0, le=1)]      # Fraction of portfolio equity
    size_units: float | None = None                           # Shares/contracts (if price known)
    stop_loss: float | None = None                            # Absolute price
    take_profit: float | None = None                          # Absolute price
    risk_pct_equity: Annotated[float, Field(ge=0, le=0.1)]    # Max loss per trade as % equity
    rationale: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class RiskNarrative:
    """AI-generated risk commentary. ALWAYS marked untrusted."""

    regime_interpretation: str
    tail_risks: list[str]
    candidate_commentary: dict[str, str]
    sizing_rationale: dict[str, str]
    rule_adjustment_proposals: list[dict]
    confidence: float
    model: str
    prompt_hash: str
    untrusted: bool = True


class RiskProfile(BaseModel):
    """Risk limits and sizing parameters."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    display_name: str

    # Portfolio-level limits
    max_portfolio_heat_pct: Annotated[float, Field(gt=0, le=0.5)] = 0.06
    max_single_position_pct: Annotated[float, Field(gt=0, le=0.1)] = 0.02
    max_sector_exposure_pct: Annotated[float, Field(gt=0, le=0.5)] = 0.10
    max_correlation_cluster_pct: Annotated[float, Field(gt=0, le=0.5)] = 0.15

    # Regime adjustments (multiplicative on base size)
    regime_multipliers: dict[str, float] = Field(default_factory=lambda: {
        "bullish": 1.0,
        "bearish": 0.5,
        "range_bound": 0.75,
        "high_volatility": 0.3,
        "unknown": 0.25,
    })

    # Stop / target
    stop_loss_atr_multiple: Annotated[float, Field(gt=0)] = 2.0
    take_profit_r_multiple: Annotated[float, Field(gt=0)] = 2.0

    # Candidate filters
    min_candidate_score: Annotated[float, Field(ge=0, le=100)] = 60
    min_confidence: Annotated[float, Field(ge=0, le=1)] = 0.5

    # Quality penalties (multiplicative)
    volume_gate_penalty: Annotated[float, Field(gt=0, le=1)] = 0.5
    session_penalty: Annotated[float, Field(gt=0, le=1)] = 0.5

    # Correlation
    correlation_lookback_days: int = 60
    correlation_threshold: Annotated[float, Field(ge=0, le=1)] = 0.75

    # AI settings
    ai_enabled: bool = True
    ai_model: str | None = None
    ai_temperature: float = 0.1
    ai_max_tokens: int = 2000
    ai_timeout_seconds: int = 30


class RiskAssessment(BaseModel):
    """Complete risk assessment for a market analysis run."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    analysis_run_id: str
    generated_at: datetime
    portfolio_equity: float
    open_positions: dict[str, float] = Field(default_factory=dict)

    approved: list[PositionSize] = Field(default_factory=list)
    reduced: list[PositionSize] = Field(default_factory=list)
    rejected: list[PositionSize] = Field(default_factory=list)
    deferred: list[PositionSize] = Field(default_factory=list)

    portfolio_heat_pct: float = 0.0
    correlation_warnings: list[str] = Field(default_factory=list)
    regime_adjustment: float = 1.0
    risk_rules_applied: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    # AI-driven enhancements
    ai_narrative: RiskNarrative | None = None
    ai_proposals_pending: list[str] = Field(default_factory=list)

    # Audit trail
    deterministic_base: RiskAssessment | None = None
    schema_version: int = 1