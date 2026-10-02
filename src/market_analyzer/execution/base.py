"""Abstract contract for trade execution clients (TradingView & Simulator)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from market_analyzer.models.execution import OrderRequest, OrderResult


class ExecutionClient(ABC):
    """Execution interface to submit orders, adjust stop loss, and poll status."""

    name: str

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection or session with TradingView/Broker."""

    @abstractmethod
    async def place_order(self, request: OrderRequest) -> OrderResult:
        """Submit a new order with bracket stop-loss and take-profit targets."""

    @abstractmethod
    async def modify_stop_loss(self, order_id: str, new_stop_loss: float) -> bool:
        """Shift stop loss to a new price level (e.g. breakeven)."""

    @abstractmethod
    async def close_position(self, order_id: str) -> bool:
        """Close an open position immediately at market."""

    @abstractmethod
    async def get_position_status(self, order_id: str) -> dict[str, Any]:
        """Poll current broker status of an active order/position."""

    @abstractmethod
    async def aclose(self) -> None:
        """Clean up background sessions or browser processes."""
