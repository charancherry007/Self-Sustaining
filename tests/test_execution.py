"""Unit and integration tests for execution engine, trade monitor, and knowledge graph."""

from __future__ import annotations

import pytest

from market_analyzer.execution.monitor import TradeMonitor
from market_analyzer.execution.simulator import SimulatedExecutionClient
from market_analyzer.knowledge.graph import TradeKnowledgeGraphBuilder
from market_analyzer.models.execution import (
    ExecutionReport,
    OrderRequest,
    OrderStatus,
    PositionLifecycleState,
)
from market_analyzer.models.strategy import (
    ExecutionTactic,
    ExitStage,
    OrderType,
    TradePlaybook,
)


@pytest.mark.asyncio
async def test_simulated_execution_client_lifecycle() -> None:
    client = SimulatedExecutionClient()
    connected = await client.connect()
    assert connected is True

    req = OrderRequest(
        order_id="test-ord-1",
        symbol="EUR/USD",
        action="LONG",
        order_type="limit",
        quantity=10000.0,
        entry_price=1.0800,
        stop_loss=1.0760,
        breakeven_trigger=1.0860,
        take_profit_1=1.0860,
        take_profit_2=1.0920,
    )

    res = await client.place_order(req)
    assert res.status == OrderStatus.OPEN
    assert res.fill_price == 1.0800

    # Modify SL to breakeven
    mod = await client.modify_stop_loss("test-ord-1", 1.0800)
    assert mod is True

    status = await client.get_position_status("test-ord-1")
    assert status["stop_loss"] == 1.0800
    assert status["breakeven_activated"] is True

    # Close position
    closed = await client.close_position("test-ord-1")
    assert closed is True


@pytest.mark.asyncio
async def test_trade_monitor_tp1_breakeven_and_tp2_exit() -> None:
    client = SimulatedExecutionClient()
    monitor = TradeMonitor(client=client)

    closed_reports: list[ExecutionReport] = []
    monitor.register_on_closed_handler(lambda r: closed_reports.append(r))

    req = OrderRequest(
        order_id="test-ord-2",
        symbol="GBP/USD",
        action="LONG",
        order_type="limit",
        quantity=10000.0,
        entry_price=1.2500,
        stop_loss=1.2460,          # 40 pip risk
        breakeven_trigger=1.2560,  # 60 pip TP1 (+1.5R)
        take_profit_1=1.2560,
        take_profit_2=1.2620,      # 120 pip TP2 (+3.0R)
    )

    await client.place_order(req)
    monitor.track_order(req)

    # 1. Normal price tick
    rep1 = monitor.process_price_update("test-ord-2", 1.2520)
    assert rep1 is None
    state1 = monitor.get_order_state("test-ord-2")
    assert state1["breakeven_activated"] is False

    # 2. Price hits TP1 (1.2560) -> automated breakeven shift
    rep2 = monitor.process_price_update("test-ord-2", 1.2565)
    assert rep2 is None
    state2 = monitor.get_order_state("test-ord-2")
    assert state2["breakeven_activated"] is True
    assert state2["lifecycle_state"] == PositionLifecycleState.TP1_REACHED_BREAKEVEN_ACTIVE

    # 3. Price continues to TP2 (1.2620) -> terminal exit in profit
    rep3 = monitor.process_price_update("test-ord-2", 1.2625)
    assert rep3 is not None
    assert rep3.status == PositionLifecycleState.CLOSED_PROFIT
    assert rep3.exit_reason == "TP2_FULL_TARGET_HIT"
    assert rep3.realized_pnl_usd > 0
    assert rep3.realized_r_multiple >= 3.0
    assert len(closed_reports) == 1


@pytest.mark.asyncio
async def test_trade_knowledge_graph_builder(tmp_path) -> None:
    builder = TradeKnowledgeGraphBuilder(ai=None, output_dir=tmp_path)

    playbook = TradePlaybook(
        symbol="EUR/USD",
        action="LONG",
        tactic=ExecutionTactic.PULLBACK_LIMIT,
        order_type=OrderType.LIMIT,
        entry_price=1.0800,
        stop_loss=1.0760,
        breakeven_trigger=1.0860,
        risk_reward_ratio=3.0,
        max_loss_usd=400.0,
        projected_profit_usd=1200.0,
        exit_stages=[
            ExitStage(label="TP1", target_price=1.0860, percentage_of_position=0.5, target_r_multiple=1.5),
            ExitStage(label="TP2", target_price=1.0920, percentage_of_position=0.5, target_r_multiple=3.0),
        ],
    )

    from datetime import datetime, timezone
    report = ExecutionReport(
        order_id="kg-test-1",
        symbol="EUR/USD",
        action="LONG",
        status=PositionLifecycleState.CLOSED_PROFIT,
        entry_price=1.0800,
        exit_price=1.0920,
        initial_stop_loss=1.0760,
        current_stop_loss=1.0800,
        take_profit_1=1.0860,
        take_profit_2=1.0920,
        breakeven_activated=True,
        quantity=10000.0,
        realized_pnl_usd=1200.0,
        realized_r_multiple=3.0,
        entry_time=datetime.now(timezone.utc),
        exit_time=datetime.now(timezone.utc),
        duration_minutes=45.0,
        max_favorable_excursion=1250.0,
        max_adverse_excursion=50.0,
        exit_reason="TP2_FULL_TARGET_HIT",
    )

    snapshot = await builder.build_and_save(report, playbook, market_regime="BULLISH")

    assert snapshot.trade_id == "kg-test-1"
    assert snapshot.symbol == "EUR/USD"
    assert len(snapshot.nodes) >= 6
    assert len(snapshot.edges) >= 6
    assert any(n.type.value == "trade" for n in snapshot.nodes)
    assert any(n.type.value == "outcome" for n in snapshot.nodes)
    assert any(n.type.value == "lesson" for n in snapshot.nodes)

    # Check file written
    out_file = tmp_path / "kg-test-1.json"
    assert out_file.exists()
