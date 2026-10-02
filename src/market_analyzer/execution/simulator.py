"""High-fidelity simulated execution engine for backtesting and offline testing."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from market_analyzer.execution.base import ExecutionClient
from market_analyzer.models.execution import (
    OrderRequest,
    OrderResult,
    OrderStatus,
    PositionLifecycleState,
)

logger = logging.getLogger(__name__)


class SimulatedExecutionClient(ExecutionClient):
    """Simulated broker providing paper execution and testing."""

    name = "simulator"

    def __init__(self) -> None:
        self.connected = False
        self._orders: dict[str, dict[str, Any]] = {}
        self._market_prices: dict[str, float] = {}

    async def connect(self) -> bool:
        self.connected = True
        logger.info("[Simulated Broker] Connected to paper trading engine.")
        return True

    async def place_order(self, request: OrderRequest) -> OrderResult:
        self.connected = True
        broker_order_id = f"sim-{uuid.uuid4().hex[:8]}"

        self._orders[request.order_id] = {
            "order_id": request.order_id,
            "broker_order_id": broker_order_id,
            "symbol": request.symbol,
            "action": request.action,
            "order_type": request.order_type,
            "quantity": request.quantity,
            "entry_price": request.entry_price,
            "current_price": request.entry_price,
            "stop_loss": request.stop_loss,
            "take_profit_1": request.take_profit_1,
            "take_profit_2": request.take_profit_2,
            "breakeven_trigger": request.breakeven_trigger,
            "breakeven_activated": False,
            "status": OrderStatus.OPEN,
            "lifecycle_state": PositionLifecycleState.ACTIVE,
            "fill_price": request.entry_price,
            "created_at": request.created_at,
            "filled_at": datetime.now(timezone.utc),
            "realized_pnl": 0.0,
            "max_price": request.entry_price,
            "min_price": request.entry_price,
        }

        print(
            f"[Simulated Broker] Order Placed: {request.action} {request.quantity} {request.symbol} "
            f"@ Limit ${request.entry_price:,.2f} | SL: ${request.stop_loss:,.2f} | TP1: ${request.take_profit_1:,.2f}",
            flush=True,
        )

        return OrderResult(
            order_id=request.order_id,
            broker_order_id=broker_order_id,
            symbol=request.symbol,
            status=OrderStatus.OPEN,
            fill_price=request.entry_price,
            message="Order filled in paper execution sandbox",
        )

    async def modify_stop_loss(self, order_id: str, new_stop_loss: float) -> bool:
        order = self._orders.get(order_id)
        if not order:
            return False

        old_sl = order["stop_loss"]
        order["stop_loss"] = new_stop_loss
        order["breakeven_activated"] = True
        order["lifecycle_state"] = PositionLifecycleState.TP1_REACHED_BREAKEVEN_ACTIVE

        print(
            f"[Simulated Broker] STOP LOSS MODIFIED for {order['symbol']}! "
            f"Old SL: ${old_sl:,.2f} -> New Breakeven SL: ${new_stop_loss:,.2f}",
            flush=True,
        )
        return True

    async def close_position(self, order_id: str) -> bool:
        order = self._orders.get(order_id)
        if not order:
            return False

        order["status"] = OrderStatus.CLOSED
        order["closed_at"] = datetime.now(timezone.utc)
        print(f"[Simulated Broker] Position closed for {order['symbol']}.", flush=True)
        return True

    async def get_position_status(self, order_id: str) -> dict[str, Any]:
        return self._orders.get(order_id, {})

    def update_price_tick(self, symbol: str, current_price: float) -> list[str]:
        """Update simulated market price and check for TP/SL trigger events."""
        self._market_prices[symbol] = current_price
        triggered_events: list[str] = []

        for order_id, order in self._orders.items():
            if order["symbol"] != symbol or order["status"] == OrderStatus.CLOSED:
                continue

            order["current_price"] = current_price
            order["max_price"] = max(order["max_price"], current_price)
            order["min_price"] = min(order["min_price"], current_price)

            action = order["action"]
            sl = order["stop_loss"]
            tp1 = order["take_profit_1"]
            tp2 = order["take_profit_2"]

            # Calculate current P&L
            qty = order["quantity"]
            entry = order["entry_price"]
            pnl = (current_price - entry) * qty if action == "LONG" else (entry - current_price) * qty
            order["unrealized_pnl"] = round(pnl, 2)

            # Check Stop Loss hit
            if (action == "LONG" and current_price <= sl) or (action == "SHORT" and current_price >= sl):
                order["status"] = OrderStatus.CLOSED
                order["exit_price"] = sl
                order["lifecycle_state"] = (
                    PositionLifecycleState.CLOSED_BREAKEVEN
                    if order.get("breakeven_activated")
                    else PositionLifecycleState.CLOSED_STOPPED_OUT
                )
                triggered_events.append(f"STOP_LOSS_HIT:{order_id}")

            # Check TP1 reached
            elif not order.get("breakeven_activated") and (
                (action == "LONG" and current_price >= tp1) or (action == "SHORT" and current_price <= tp1)
            ):
                order["lifecycle_state"] = PositionLifecycleState.TP1_REACHED_BREAKEVEN_ACTIVE
                triggered_events.append(f"TP1_REACHED:{order_id}")

            # Check TP2 reached
            elif tp2 and ((action == "LONG" and current_price >= tp2) or (action == "SHORT" and current_price <= tp2)):
                order["status"] = OrderStatus.CLOSED
                order["exit_price"] = tp2
                order["lifecycle_state"] = PositionLifecycleState.CLOSED_PROFIT
                triggered_events.append(f"TP2_REACHED:{order_id}")

        return triggered_events

    async def aclose(self) -> None:
        self.connected = False
