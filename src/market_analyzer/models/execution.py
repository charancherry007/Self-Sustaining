"""Trade execution, order lifecycle, and position tracking schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    CLOSED = "closed"


class PositionLifecycleState(str, Enum):
    WAITING_FOR_FILL = "waiting_for_fill"
    ACTIVE = "active"
    TP1_REACHED_BREAKEVEN_ACTIVE = "tp1_reached_breakeven_active"
    TP2_REACHED = "tp2_reached"
    CLOSED_PROFIT = "closed_profit"
    CLOSED_STOPPED_OUT = "closed_stopped_out"
    CLOSED_BREAKEVEN = "closed_breakeven"
    CLOSED_MANUAL = "closed_manual"


class OrderRequest(BaseModel):
    """Instruction to submit a trade to TradingView or broker."""

    model_config = ConfigDict(frozen=True)

    order_id: str
    symbol: str
    action: str  # "LONG" | "SHORT"
    order_type: str = "limit"  # "limit" | "market" | "stop_limit"
    quantity: float = Field(gt=0)
    entry_price: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    breakeven_trigger: float = Field(gt=0)
    take_profit_1: float = Field(gt=0)
    take_profit_2: float | None = None
    runner_trail_atr: float | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: list[str] = Field(default_factory=list)


class OrderResult(BaseModel):
    """Immediate acknowledgement and confirmation from TradingView/broker."""

    model_config = ConfigDict(frozen=True)

    order_id: str
    broker_order_id: str
    symbol: str
    status: OrderStatus
    fill_price: float | None = None
    message: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_response: dict[str, Any] = Field(default_factory=dict)


class ExecutionReport(BaseModel):
    """Complete post-trade lifecycle report for knowledge synthesis."""

    model_config = ConfigDict(frozen=True)

    order_id: str
    symbol: str
    action: str
    status: PositionLifecycleState
    entry_price: float
    exit_price: float
    initial_stop_loss: float
    current_stop_loss: float
    take_profit_1: float
    take_profit_2: float | None = None
    breakeven_activated: bool = False
    quantity: float
    realized_pnl_usd: float
    realized_r_multiple: float
    entry_time: datetime
    exit_time: datetime
    duration_minutes: float
    max_favorable_excursion: float  # Maximum peak profit in price or USD
    max_adverse_excursion: float    # Maximum drawdown experienced during trade
    exit_reason: str                # e.g., "TP1_SCALE_AND_BE", "TP2_HIT", "STOP_LOSS_HIT"
