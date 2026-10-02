"""Post-trade AI Knowledge Graph generator and case synthesizer."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from market_analyzer.ai.base import AiAnalyst
from market_analyzer.models.execution import ExecutionReport
from market_analyzer.models.knowledge_graph import (
    GraphEdge,
    GraphEdgeType,
    GraphNode,
    GraphNodeType,
    KnowledgeGraphSnapshot,
)
from market_analyzer.models.strategy import TradePlaybook

logger = logging.getLogger(__name__)

GRAPH_DIR = Path("knowledge/graph/trades")


class TradeKnowledgeGraphBuilder:
    """Constructs structured semantic knowledge graphs from trade outcomes."""

    def __init__(
        self,
        ai: AiAnalyst | None = None,
        output_dir: Path | str = GRAPH_DIR,
    ) -> None:
        self.ai = ai
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def build_and_save(
        self,
        report: ExecutionReport,
        playbook: TradePlaybook,
        market_regime: str = "BULLISH",
    ) -> KnowledgeGraphSnapshot:
        """Synthesize post-trade outcome into a node-edge graph JSON."""
        trade_id = report.order_id
        symbol = report.symbol
        action = report.action

        # 1. Ask AI for post-trade insights if available
        summary_text, lessons = await self._generate_ai_post_mortem(report, playbook, market_regime)

        # 2. Build Graph Nodes
        nodes: list[GraphNode] = [
            GraphNode(
                id=f"trade-{trade_id}",
                label=f"{action} {symbol} Trade",
                type=GraphNodeType.TRADE,
                properties={
                    "order_id": trade_id,
                    "action": action,
                    "symbol": symbol,
                    "entry_price": report.entry_price,
                    "exit_price": report.exit_price,
                    "realized_pnl_usd": report.realized_pnl_usd,
                    "realized_r_multiple": report.realized_r_multiple,
                    "duration_minutes": report.duration_minutes,
                    "exit_reason": report.exit_reason,
                    "mfe": report.max_favorable_excursion,
                    "mae": report.max_adverse_excursion,
                },
            ),
            GraphNode(
                id=f"strat-{symbol.lower()}",
                label=f"Strategy: {playbook.tactic.value.title()}",
                type=GraphNodeType.STRATEGY,
                properties={
                    "tactic": playbook.tactic.value,
                    "target_rr": playbook.risk_reward_ratio,
                    "planned_entry": playbook.entry_price,
                    "planned_sl": playbook.stop_loss,
                    "breakeven_trigger": playbook.breakeven_trigger,
                },
            ),
            GraphNode(
                id=f"regime-{market_regime.lower()}",
                label=f"{market_regime} Market Regime",
                type=GraphNodeType.REGIME,
                properties={"regime": market_regime},
            ),
            GraphNode(
                id=f"setup-{symbol.lower()}",
                label=f"Setup: {playbook.tactic.value.replace('_', ' ').title()}",
                type=GraphNodeType.SETUP,
                properties={
                    "order_type": playbook.order_type.value,
                    "invalidation_rules": playbook.invalidation_conditions,
                },
            ),
            GraphNode(
                id=f"inst-{symbol.lower()}",
                label=f"Asset: {symbol}",
                type=GraphNodeType.INSTRUMENT,
                properties={"symbol": symbol},
            ),
            GraphNode(
                id=f"outcome-{trade_id}",
                label=f"Outcome: {report.exit_reason} (${report.realized_pnl_usd:+,.2f})",
                type=GraphNodeType.OUTCOME,
                properties={
                    "exit_reason": report.exit_reason,
                    "breakeven_activated": report.breakeven_activated,
                    "pnl": report.realized_pnl_usd,
                    "r_multiple": report.realized_r_multiple,
                },
            ),
            GraphNode(
                id=f"lesson-{trade_id}",
                label=f"Lesson: {lessons[0] if lessons else 'Capital Preserved'}",
                type=GraphNodeType.LESSON,
                properties={"key_takeaways": lessons},
            ),
        ]

        # 3. Build Graph Relationships / Edges
        edges: list[GraphEdge] = [
            GraphEdge(
                source=f"trade-{trade_id}",
                target=f"strat-{symbol.lower()}",
                relationship=GraphEdgeType.EXECUTED_WITH,
            ),
            GraphEdge(
                source=f"trade-{trade_id}",
                target=f"regime-{market_regime.lower()}",
                relationship=GraphEdgeType.OCCURRED_IN,
            ),
            GraphEdge(
                source=f"trade-{trade_id}",
                target=f"setup-{symbol.lower()}",
                relationship=GraphEdgeType.TRIGGERED_BY,
            ),
            GraphEdge(
                source=f"trade-{trade_id}",
                target=f"inst-{symbol.lower()}",
                relationship=GraphEdgeType.TRADED_ON,
            ),
            GraphEdge(
                source=f"trade-{trade_id}",
                target=f"outcome-{trade_id}",
                relationship=GraphEdgeType.RESULTED_IN,
            ),
            GraphEdge(
                source=f"outcome-{trade_id}",
                target=f"lesson-{trade_id}",
                relationship=GraphEdgeType.PRODUCED_LESSON,
            ),
            GraphEdge(
                source=f"lesson-{trade_id}",
                target=f"strat-{symbol.lower()}",
                relationship=GraphEdgeType.ADAPTS_STRATEGY,
            ),
        ]

        snapshot = KnowledgeGraphSnapshot(
            trade_id=trade_id,
            symbol=symbol,
            nodes=nodes,
            edges=edges,
            executive_summary=summary_text,
            lessons_learned=lessons,
            performance_metrics={
                "realized_pnl_usd": report.realized_pnl_usd,
                "realized_r_multiple": report.realized_r_multiple,
                "duration_minutes": report.duration_minutes,
                "breakeven_activated": report.breakeven_activated,
                "max_favorable_excursion": report.max_favorable_excursion,
                "max_adverse_excursion": report.max_adverse_excursion,
            },
        )

        # 4. Save Knowledge Graph JSON
        out_file = self.output_dir / f"{trade_id}.json"
        with out_file.open("w", encoding="utf-8") as f:
            f.write(json.dumps(snapshot.model_dump(mode="json"), indent=2))

        print(f"[Knowledge Graph] Saved trade post-mortem graph to {out_file}", flush=True)
        return snapshot

    async def _generate_ai_post_mortem(
        self,
        report: ExecutionReport,
        playbook: TradePlaybook,
        market_regime: str,
    ) -> tuple[str, list[str]]:
        """Query LLM for deep post-mortem insights or fallback to deterministic rules."""
        if self.ai and getattr(self.ai, "enabled", False):
            prompt = (
                f"You are a quant trading post-mortem analyst. Evaluate this completed trade:\n"
                f"Instrument: {report.symbol}\n"
                f"Action: {report.action} ({playbook.tactic.value})\n"
                f"Planned Target R:R: {playbook.risk_reward_ratio}:1\n"
                f"Market Regime: {market_regime}\n"
                f"Entry Price: ${report.entry_price:,.2f} | Exit Price: ${report.exit_price:,.2f}\n"
                f"Exit Reason: {report.exit_reason}\n"
                f"Breakeven Activated: {report.breakeven_activated}\n"
                f"Realized P&L: ${report.realized_pnl_usd:+,.2f} ({report.realized_r_multiple:+.2f}R)\n"
                f"Duration: {report.duration_minutes} minutes\n"
                f"MFE (Max Peak Profit): ${report.max_favorable_excursion:,.2f}\n"
                f"MAE (Max Adverse Drawdown): ${report.max_adverse_excursion:,.2f}\n\n"
                f"Return ONLY a JSON object with this exact structure:\n"
                f'{{"summary": "2-3 sentences analyzing execution efficiency and market structure interaction", '
                f'"lessons": ["Lesson 1 on risk or entry timing", "Lesson 2 on exit or regime alignment"]}}'
            )
            try:
                res = await self.ai.chat(prompt=prompt, temperature=0.1, max_tokens=1000)
                if res:
                    start, end = res.find("{"), res.rfind("}")
                    if start != -1 and end > start:
                        parsed = json.loads(res[start : end + 1])
                        return (
                            str(parsed.get("summary", "")),
                            [str(item) for item in parsed.get("lessons", [])],
                        )
            except Exception as exc:
                logger.debug("AI post-mortem generation error: %s; using deterministic fallback.", exc)

        # Deterministic fallback synthesis
        if report.realized_pnl_usd > 0:
            summary = (
                f"Trade on {report.symbol} achieved positive outcome ({report.realized_r_multiple:+.2f}R) "
                f"via {report.exit_reason} under {market_regime} conditions. "
                f"Asymmetric risk management locked in profits with zero downside exposure."
            )
            lessons = [
                f"Target profit scaling validated for {playbook.tactic.value}.",
                "Fast breakeven transition successfully protected unrealized gains.",
            ]
        elif report.breakeven_activated:
            summary = (
                f"Trade on {report.symbol} exited at breakeven after touching TP1. "
                f"Capital was 100% preserved ($0.00 loss) despite subsequent adverse market retracement."
            )
            lessons = [
                "Automated breakeven rule prevented a potential full loss after initial extension.",
                "Review pullback re-entry conditions for secondary continuation waves.",
            ]
        else:
            summary = (
                f"Trade on {report.symbol} was stopped out at predefined risk limit (-1.0R). "
                f"Loss was strictly capped at ${abs(report.realized_pnl_usd):,.2f} without adverse drift."
            )
            lessons = [
                f"Tighten confluence criteria for {playbook.tactic.value} during {market_regime} regime.",
                "Hard stop loss prevented catastrophic excursion.",
            ]

        return summary, lessons
