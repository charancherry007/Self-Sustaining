"""Active trade lifecycle monitor and automated breakeven stop-loss adjuster."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from market_analyzer.execution.base import ExecutionClient
from market_analyzer.models.execution import (
    ExecutionReport,
    OrderRequest,
    PositionLifecycleState,
)
from market_analyzer.providers.base import MarketDataProvider

logger = logging.getLogger(__name__)


class TradeMonitor:
    """Monitors live trade progress, enforces breakeven shifts, and records outcomes."""

    def __init__(
        self,
        client: ExecutionClient,
        provider: MarketDataProvider | None = None,
        poll_interval_seconds: float = 3.0,
    ) -> None:
        self.client = client
        self.provider = provider
        self.poll_interval = poll_interval_seconds
        self._active_orders: dict[str, dict[str, Any]] = {}
        self._completed_reports: list[ExecutionReport] = []
        self._on_trade_closed_handlers: list[Callable[[ExecutionReport], Any]] = []

    def register_on_closed_handler(self, handler: Callable[[ExecutionReport], Any]) -> None:
        """Register a callback to be triggered when a position reaches a terminal exit."""
        self._on_trade_closed_handlers.append(handler)

    def track_order(self, request: OrderRequest) -> None:
        """Register an order into the active monitoring registry."""
        self._active_orders[request.order_id] = {
            "request": request,
            "lifecycle_state": PositionLifecycleState.ACTIVE,
            "current_price": request.entry_price,
            "highest_price": request.entry_price,
            "lowest_price": request.entry_price,
            "breakeven_activated": False,
            "entry_time": datetime.now(timezone.utc),
            "exit_time": None,
            "exit_price": None,
            "exit_reason": None,
            "realized_pnl": 0.0,
            "realized_r": 0.0,
        }
        print(
            f"[Trade Monitor] Started active monitoring for {request.action} {request.symbol} "
            f"(Target TP1: ${request.take_profit_1:,.2f} | BE Trigger: ${request.breakeven_trigger:,.2f})",
            flush=True,
        )

    def process_price_update(self, order_id: str, current_price: float) -> ExecutionReport | None:
        """Evaluate a price tick against breakeven and exit thresholds."""
        item = self._active_orders.get(order_id)
        if not item or item.get("exit_time") is not None:
            return None

        req: OrderRequest = item["request"]
        item["current_price"] = current_price
        item["highest_price"] = max(item["highest_price"], current_price)
        item["lowest_price"] = min(item["lowest_price"], current_price)

        action = req.action.upper()
        entry = req.entry_price
        sl = req.stop_loss
        tp1 = req.take_profit_1
        tp2 = req.take_profit_2
        risk_dist = abs(entry - sl) if abs(entry - sl) > 0 else 1.0

        # 1. Check TP1 / Breakeven trigger
        if not item["breakeven_activated"]:
            hit_tp1 = (action == "LONG" and current_price >= tp1) or (action == "SHORT" and current_price <= tp1)
            if hit_tp1:
                item["breakeven_activated"] = True
                item["lifecycle_state"] = PositionLifecycleState.TP1_REACHED_BREAKEVEN_ACTIVE

                print(
                    f"\n[Trade Monitor] 🎯 TP1 REACHED for {req.symbol} at ${current_price:,.2f}! "
                    f"Automatically shifting Stop Loss to Breakeven at ${entry:,.2f}. Trade risk is now $0.00!",
                    flush=True,
                )
                logger.info("TP1 hit for %s; adjusting SL to breakeven %s", req.symbol, entry)
                # Dispatch stop loss modification to execution client
                asyncio.create_task(self.client.modify_stop_loss(req.order_id, entry))

        # 2. Check Stop Loss trigger (either initial or breakeven)
        active_sl = entry if item["breakeven_activated"] else sl
        hit_sl = (action == "LONG" and current_price <= active_sl) or (action == "SHORT" and current_price >= active_sl)

        # 3. Check Final Target (TP2)
        hit_tp2 = tp2 and ((action == "LONG" and current_price >= tp2) or (action == "SHORT" and current_price <= tp2))

        terminal_exit = hit_sl or hit_tp2

        if terminal_exit:
            exit_time = datetime.now(timezone.utc)
            item["exit_time"] = exit_time
            exit_price = active_sl if hit_sl else (tp2 or current_price)
            item["exit_price"] = exit_price

            if hit_tp2:
                item["lifecycle_state"] = PositionLifecycleState.CLOSED_PROFIT
                item["exit_reason"] = "TP2_FULL_TARGET_HIT"
            elif item["breakeven_activated"]:
                item["lifecycle_state"] = PositionLifecycleState.CLOSED_BREAKEVEN
                item["exit_reason"] = "BREAKEVEN_STOP_OUT"
            else:
                item["lifecycle_state"] = PositionLifecycleState.CLOSED_STOPPED_OUT
                item["exit_reason"] = "INITIAL_STOP_LOSS_HIT"

            # Calculate realized P&L and realized R-multiple
            pnl_per_unit = (exit_price - entry) if action == "LONG" else (entry - exit_price)
            realized_pnl = round(pnl_per_unit * req.quantity, 2)
            realized_r = round(pnl_per_unit / risk_dist, 2)

            duration = (exit_time - item["entry_time"]).total_seconds() / 60.0

            # Compute MFE and MAE
            if action == "LONG":
                mfe = (item["highest_price"] - entry) * req.quantity
                mae = (entry - item["lowest_price"]) * req.quantity
            else:
                mfe = (entry - item["lowest_price"]) * req.quantity
                mae = (item["highest_price"] - entry) * req.quantity

            report = ExecutionReport(
                order_id=req.order_id,
                symbol=req.symbol,
                action=req.action,
                status=item["lifecycle_state"],
                entry_price=entry,
                exit_price=exit_price,
                initial_stop_loss=sl,
                current_stop_loss=active_sl,
                take_profit_1=tp1,
                take_profit_2=tp2,
                breakeven_activated=item["breakeven_activated"],
                quantity=req.quantity,
                realized_pnl_usd=realized_pnl,
                realized_r_multiple=realized_r,
                entry_time=item["entry_time"],
                exit_time=exit_time,
                duration_minutes=round(duration, 1),
                max_favorable_excursion=round(max(0.0, mfe), 2),
                max_adverse_excursion=round(max(0.0, mae), 2),
                exit_reason=item["exit_reason"],
            )

            self._completed_reports.append(report)
            print(
                f"[Trade Monitor] 🏁 TRADE CLOSED: {req.symbol} ({report.exit_reason}) | "
                f"P&L: ${realized_pnl:+,.2f} ({realized_r:+.2f}R) in {duration:.1f}m\n",
                flush=True,
            )

            # Fire registered post-mortem handlers
            for handler in self._on_trade_closed_handlers:
                try:
                    handler(report)
                except Exception as exc:
                    logger.error("Handler error on trade closed: %s", exc)

            return report

        return None

    async def poll_active_trades(self, max_cycles: int = 10) -> list[ExecutionReport]:
        """Poll market data provider for live ticks on active orders."""
        completed: list[ExecutionReport] = []

        for _ in range(max_cycles):
            active_ids = [k for k, v in self._active_orders.items() if v.get("exit_time") is None]
            if not active_ids:
                break

            for order_id in active_ids:
                item = self._active_orders[order_id]
                sym = item["request"].symbol
                try:
                    if self.provider:
                        quote = await self.provider.get_quote(sym)
                        rep = self.process_price_update(order_id, quote.last)
                        if rep:
                            completed.append(rep)
                except Exception as exc:
                    logger.debug("Failed polling quote for %s: %s", sym, exc)

            await asyncio.sleep(self.poll_interval)

        return completed

    def get_order_state(self, order_id: str) -> dict[str, Any] | None:
        """Retrieve current tracking details for an active order."""
        return self._active_orders.get(order_id)
