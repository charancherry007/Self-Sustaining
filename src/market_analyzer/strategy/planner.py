"""AI Trading Strategy Planner Engine.

Ingests `MarketAnalysis` and `RiskAssessment` artefacts to formulate
actionable, asymmetric execution playbooks focusing on high upside
and strictly capped downside risk.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from market_analyzer.ai import AiAnalyst, build_ai_analyst
from market_analyzer.config import AppConfig, load_app_config
from market_analyzer.models.analysis import Candidate, MarketAnalysis, Side
from market_analyzer.models.risk import PositionSize, RiskAssessment
from market_analyzer.models.strategy import (
    ExecutionTactic,
    ExitStage,
    OrderType,
    StrategyPlan,
    TradePlaybook,
)

logger = logging.getLogger(__name__)

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class StrategyPlanner:
    """Generates asymmetric trade playbooks from Market & Risk artefacts."""

    def __init__(
        self,
        config: AppConfig | None = None,
        ai: AiAnalyst | None = None,
    ) -> None:
        self.config = config or load_app_config()
        self.ai = ai or build_ai_analyst(enabled=True)

    async def plan(
        self,
        analysis: MarketAnalysis,
        assessment: RiskAssessment,
        portfolio_equity: float = 100_000.0,
    ) -> StrategyPlan:
        """Produce an actionable StrategyPlan with asymmetric risk-reward playbooks."""
        plan_id = f"strat-{uuid.uuid4().hex[:8]}"

        # Identify candidates approved or reduced by Risk Engine
        actionable_positions: list[PositionSize] = [
            p for p in (assessment.approved + assessment.reduced)
            if p.size_pct_equity > 0
        ]

        cand_map: dict[str, Candidate] = {c.symbol: c for c in analysis.candidates}

        # If no positions approved, return an observational contingency plan
        if not actionable_positions:
            return self._empty_plan(plan_id, analysis, assessment)

        # Attempt AI generation if enabled
        if self.ai and getattr(self.ai, "enabled", False):
            try:
                ai_plan = await self._generate_ai_plan(
                    plan_id=plan_id,
                    analysis=analysis,
                    assessment=assessment,
                    positions=actionable_positions,
                    cand_map=cand_map,
                    portfolio_equity=portfolio_equity,
                )
                if ai_plan and ai_plan.playbooks:
                    return ai_plan
            except Exception as exc:
                logger.warning("AI strategy generation encountered an error: %s. Using deterministic fallback.", exc)

        # Fallback to deterministic asymmetric playbook calculation
        return self._deterministic_plan(
            plan_id=plan_id,
            analysis=analysis,
            assessment=assessment,
            positions=actionable_positions,
            cand_map=cand_map,
            portfolio_equity=portfolio_equity,
        )

    async def _generate_ai_plan(
        self,
        plan_id: str,
        analysis: MarketAnalysis,
        assessment: RiskAssessment,
        positions: list[PositionSize],
        cand_map: dict[str, Candidate],
        portfolio_equity: float,
    ) -> StrategyPlan | None:
        """Call OpenRouter LLM to construct asymmetric playbooks."""
        prompt = self._build_prompt(analysis, assessment, positions, cand_map, portfolio_equity)

        response = await self.ai.chat(
            prompt=prompt,
            temperature=0.2,
            max_tokens=3000,
            timeout=25.0,
        )
        if not response:
            return None

        json_str = self._extract_json(response)
        if not json_str:
            return None

        data = json.loads(json_str)
        playbooks: list[TradePlaybook] = []

        for item in data.get("playbooks", []):
            try:
                playbook = self._parse_playbook(item, cand_map, positions, portfolio_equity)
                if playbook:
                    playbooks.append(playbook)
            except Exception as exc:
                logger.debug("Failed parsing playbook item: %s", exc)

        if not playbooks:
            return None

        # Calculate totals
        total_risk = sum(p.max_loss_usd for p in playbooks)
        total_profit = sum(p.projected_profit_usd for p in playbooks)
        blended_rr = (total_profit / total_risk) if total_risk > 0 else 3.0

        return StrategyPlan(
            plan_id=plan_id,
            analysis_run_id=analysis.run_id,
            risk_run_id=assessment.run_id,
            generated_at=datetime.now(timezone.utc),
            playbooks=playbooks,
            overall_market_bias=str(data.get("overall_market_bias", analysis.regime.value.upper())),
            blended_rr_ratio=round(blended_rr, 2),
            total_risk_usd=round(total_risk, 2),
            total_target_profit_usd=round(total_profit, 2),
            contingency_plans=[str(c) for c in data.get("contingency_plans", [])],
        )

    def _build_prompt(
        self,
        analysis: MarketAnalysis,
        assessment: RiskAssessment,
        positions: list[PositionSize],
        cand_map: dict[str, Candidate],
        portfolio_equity: float,
    ) -> str:
        """Build structured prompt for AI Strategy Planner."""
        pos_summaries = []
        for p in positions:
            cand = cand_map.get(p.symbol)
            atr = cand.metrics.get("atr_14", 0.0) if cand else 0.0
            rsi = cand.metrics.get("rsi_14", 50.0) if cand else 50.0
            last_p = cand.last_price if cand else (p.stop_loss or 100.0)
            side = cand.side.value if cand else "long"

            pos_summaries.append(
                f"- Symbol: {p.symbol}\n"
                f"  Side: {side.upper()}\n"
                f"  Action: {p.action.value}\n"
                f"  Last Price: {last_p}\n"
                f"  ATR(14): {atr}\n"
                f"  RSI(14): {rsi}\n"
                f"  Allocated Equity: {p.size_pct_equity:.2%}\n"
                f"  Units: {p.size_units}\n"
                f"  Initial Stop Loss: {p.stop_loss}\n"
                f"  Max Risk % Equity: {p.risk_pct_equity:.2%}"
            )

        positions_block = "\n".join(pos_summaries)

        return f"""You are the Lead Quantitative Strategy Planner for an elite hedge fund.
Your task is to take Market Analysis and Risk Assessment outputs and create an ASYMMETRIC, HIGH-PROFIT / LOW-LOSS execution playbook for each candidate.

CORE ASYMMETRIC RULES (NON-NEGOTIABLE):
1. Risk-to-Reward Ratio: Minimum 2.5:1 (blended R:R must be >= 2.5). Every dollar risked must target at least $2.50 to $4.00 profit.
2. Limit Pullback Entries: Do not chase market momentum. Use 'pullback_limit' to buy dips at dynamic support (e.g. EMA 20, VWAP retest) for longs, or sell rallies for shorts. This tightens the stop distance and expands R:R.
3. 3-Stage Profit Scaling & Fast De-risking:
   - TP1 (Scale 50% @ 1.5R): Take 50% profit off the table. MANDATORY: Move Stop Loss to Entry Price (Breakeven trigger). Risk becomes $0.00.
   - TP2 (Scale 30% @ 3.0R): Capture key swing objective.
   - Runner (Hold 20%): Trail dynamically using 2x ATR(14) behind trend structure to capture mega trends.
4. Hard Invalidation: State 2 concrete conditions that cancel the order before fill (e.g., breakdown below key level).

MARKET REGIME: {analysis.regime.value.upper()}
PORTFOLIO EQUITY: ${portfolio_equity:,.2f}
RISK HEAT: {assessment.portfolio_heat_pct:.2%}

APPROVED CANDIDATES:
{positions_block}

Respond ONLY with a valid JSON object matching this schema:
{{
  "overall_market_bias": "BULLISH|BEARISH|NEUTRAL",
  "contingency_plans": ["Contingency action 1", "Contingency action 2"],
  "playbooks": [
    {{
      "symbol": "SYMBOL",
      "action": "LONG|SHORT",
      "tactic": "pullback_limit|breakout_confirm",
      "order_type": "limit|stop_limit",
      "entry_price": 100.0,
      "stop_loss": 98.0,
      "breakeven_trigger": 101.5,
      "risk_reward_ratio": 3.1,
      "exit_stages": [
        {{
          "label": "TP1 (Scale 50%)",
          "target_price": 101.5,
          "percentage_of_position": 0.50,
          "target_r_multiple": 1.5,
          "trail_rule": "Move Stop Loss to Entry Price ($100.0)"
        }},
        {{
          "label": "TP2 (Scale 30%)",
          "target_price": 103.0,
          "percentage_of_position": 0.30,
          "target_r_multiple": 3.0,
          "trail_rule": "Hold runner"
        }},
        {{
          "label": "Runner (Hold 20%)",
          "target_price": 105.0,
          "percentage_of_position": 0.20,
          "target_r_multiple": 5.0,
          "trail_rule": "Trail 2x ATR behind 20-EMA"
        }}
      ],
      "invalidation_conditions": [
        "Price trades below support before limit order is filled",
        "Higher timeframe trend flips against setup"
      ],
      "execution_notes": [
        "Place limit order GTC",
        "Set alert at Breakeven trigger level"
      ]
    }}
  ]
}}
"""

    def _parse_playbook(
        self,
        item: dict[str, Any],
        cand_map: dict[str, Candidate],
        positions: list[PositionSize],
        portfolio_equity: float,
    ) -> TradePlaybook | None:
        """Parse and mathematically validate a single playbook item."""
        symbol = str(item.get("symbol", "")).upper()
        cand = cand_map.get(symbol)
        pos = next((p for p in positions if p.symbol == symbol), None)
        if not pos:
            return None

        action = str(item.get("action", "LONG")).upper()
        tactic_str = str(item.get("tactic", "pullback_limit")).lower()
        tactic = ExecutionTactic.PULLBACK_LIMIT
        if "breakout" in tactic_str:
            tactic = ExecutionTactic.BREAKOUT_CONFIRM
        elif "mean" in tactic_str:
            tactic = ExecutionTactic.MEAN_REVERSION

        order_type_str = str(item.get("order_type", "limit")).lower()
        order_type = OrderType.LIMIT
        if "stop" in order_type_str:
            order_type = OrderType.STOP_LIMIT
        elif "market" in order_type_str:
            order_type = OrderType.MARKET

        entry_price = float(item.get("entry_price", cand.last_price if cand else 100.0))
        stop_loss = float(item.get("stop_loss", pos.stop_loss or (entry_price * 0.98)))
        risk_dist = abs(entry_price - stop_loss)
        if risk_dist <= 0:
            risk_dist = entry_price * 0.01
            stop_loss = entry_price - risk_dist if action == "LONG" else entry_price + risk_dist

        breakeven_trigger = float(
            item.get("breakeven_trigger", entry_price + (1.5 * risk_dist) if action == "LONG" else entry_price - (1.5 * risk_dist))
        )

        # Parse exit stages
        raw_stages = item.get("exit_stages", [])
        exit_stages: list[ExitStage] = []
        if raw_stages:
            for s in raw_stages:
                exit_stages.append(
                    ExitStage(
                        label=str(s.get("label", "TP")),
                        target_price=float(s.get("target_price", entry_price + 2 * risk_dist)),
                        percentage_of_position=float(s.get("percentage_of_position", 0.33)),
                        target_r_multiple=float(s.get("target_r_multiple", 2.0)),
                        trail_rule=str(s.get("trail_rule")) if s.get("trail_rule") else None,
                    )
                )
        else:
            # Generate standard 3-stage asymmetric exits
            exit_stages = self._build_standard_exit_stages(action, entry_price, risk_dist)

        # Calculate exact asymmetric metrics
        # Enforce blended R:R >= 2.5:1
        blended_r = sum(stage.percentage_of_position * stage.target_r_multiple for stage in exit_stages)
        if blended_r < 2.5:
            # Upgrade stages to enforce asymmetric edge
            exit_stages = self._build_standard_exit_stages(action, entry_price, risk_dist)
            blended_r = sum(stage.percentage_of_position * stage.target_r_multiple for stage in exit_stages)

        max_loss_usd = pos.risk_pct_equity * portfolio_equity
        if pos.size_units and pos.size_units > 0:
            max_loss_usd = max(max_loss_usd, pos.size_units * risk_dist)
        if max_loss_usd <= 0:
            max_loss_usd = portfolio_equity * 0.005  # 0.5% default

        projected_profit_usd = max_loss_usd * blended_r

        return TradePlaybook(
            symbol=symbol,
            action=action,
            tactic=tactic,
            order_type=order_type,
            entry_price=round(entry_price, 4),
            stop_loss=round(stop_loss, 4),
            breakeven_trigger=round(breakeven_trigger, 4),
            risk_reward_ratio=round(blended_r, 2),
            max_loss_usd=round(max_loss_usd, 2),
            projected_profit_usd=round(projected_profit_usd, 2),
            exit_stages=exit_stages,
            invalidation_conditions=[str(c) for c in item.get("invalidation_conditions", [
                "Immediate cancellation if price gaps past stop loss prior to fill",
                "Invalidate if adverse higher-timeframe candle closes beyond support",
            ])],
            execution_notes=[str(n) for n in item.get("execution_notes", [
                "Set limit entry with GTC (Good 'Til Cancelled)",
                f"On TP1 trigger, immediately shift Stop Loss to Breakeven at ${entry_price:,.2f}",
            ])],
        )

    def _build_standard_exit_stages(
        self,
        action: str,
        entry_price: float,
        risk_dist: float,
    ) -> list[ExitStage]:
        """Construct standard 3-tier asymmetric exits (TP1 50% @ 1.5R + BE, TP2 30% @ 3.0R, Runner 20% @ 5.0R)."""
        is_long = action == "LONG"
        tp1_price = entry_price + (1.5 * risk_dist) if is_long else entry_price - (1.5 * risk_dist)
        tp2_price = entry_price + (3.0 * risk_dist) if is_long else entry_price - (3.0 * risk_dist)
        runner_price = entry_price + (5.0 * risk_dist) if is_long else entry_price - (5.0 * risk_dist)

        return [
            ExitStage(
                label="TP1 (Scale 50%)",
                target_price=round(tp1_price, 4),
                percentage_of_position=0.50,
                target_r_multiple=1.5,
                trail_rule=f"Move Stop Loss to Entry Price (Breakeven at ${entry_price:,.2f})",
            ),
            ExitStage(
                label="TP2 (Scale 30%)",
                target_price=round(tp2_price, 4),
                percentage_of_position=0.30,
                target_r_multiple=3.0,
                trail_rule="Lock in swing gains; maintain breakeven stop",
            ),
            ExitStage(
                label="Runner (Hold 20%)",
                target_price=round(runner_price, 4),
                percentage_of_position=0.20,
                target_r_multiple=5.0,
                trail_rule="Trail 2x ATR behind dynamic 20-EMA trend",
            ),
        ]

    def _deterministic_plan(
        self,
        plan_id: str,
        analysis: MarketAnalysis,
        assessment: RiskAssessment,
        positions: list[PositionSize],
        cand_map: dict[str, Candidate],
        portfolio_equity: float,
    ) -> StrategyPlan:
        """Deterministic calculation guaranteeing asymmetric R:R >= 2.5:1 when AI is disabled."""
        playbooks: list[TradePlaybook] = []

        for p in positions:
            cand = cand_map.get(p.symbol)
            last_price = cand.last_price if cand else 100.0
            atr = cand.metrics.get("atr_14", last_price * 0.015) if cand else (last_price * 0.015)
            side = cand.side if cand else Side.LONG
            is_long = side in (Side.LONG, Side.WATCH)
            action = "LONG" if is_long else "SHORT"

            # Entry: slight pullback limit (0.25 ATR in direction of discount)
            if is_long:
                entry_price = round(last_price - (0.25 * atr), 4)
                stop_loss = round(p.stop_loss or (entry_price - (1.2 * atr)), 4)
                risk_dist = max(entry_price - stop_loss, entry_price * 0.005)
                breakeven_trigger = round(entry_price + (1.5 * risk_dist), 4)
            else:
                entry_price = round(last_price + (0.25 * atr), 4)
                stop_loss = round(p.stop_loss or (entry_price + (1.2 * atr)), 4)
                risk_dist = max(stop_loss - entry_price, entry_price * 0.005)
                breakeven_trigger = round(entry_price - (1.5 * risk_dist), 4)

            exit_stages = self._build_standard_exit_stages(action, entry_price, risk_dist)
            blended_r = sum(stage.percentage_of_position * stage.target_r_multiple for stage in exit_stages)

            max_loss_usd = max(p.risk_pct_equity * portfolio_equity, 250.0)
            if p.size_units and p.size_units > 0:
                max_loss_usd = max(max_loss_usd, p.size_units * risk_dist)
            projected_profit_usd = max_loss_usd * blended_r

            playbook = TradePlaybook(
                symbol=p.symbol,
                action=action,
                tactic=ExecutionTactic.PULLBACK_LIMIT,
                order_type=OrderType.LIMIT,
                entry_price=entry_price,
                stop_loss=stop_loss,
                breakeven_trigger=breakeven_trigger,
                risk_reward_ratio=round(blended_r, 2),
                max_loss_usd=round(max_loss_usd, 2),
                projected_profit_usd=round(projected_profit_usd, 2),
                exit_stages=exit_stages,
                invalidation_conditions=[
                    f"Cancel order if price trades beyond ${stop_loss:,.2f} before entry triggers",
                    "Cancel order if spread expands beyond 0.15% prior to fill",
                ],
                execution_notes=[
                    f"Submit limit order at ${entry_price:,.2f} to avoid chasing",
                    f"When price reaches ${breakeven_trigger:,.2f} (TP1), advance Stop Loss to Entry",
                    "Trail remaining 20% position using 2x ATR(14)",
                ],
            )
            playbooks.append(playbook)

        total_risk = sum(p.max_loss_usd for p in playbooks)
        total_profit = sum(p.projected_profit_usd for p in playbooks)
        blended_rr = (total_profit / total_risk) if total_risk > 0 else 2.65

        return StrategyPlan(
            plan_id=plan_id,
            analysis_run_id=analysis.run_id,
            risk_run_id=assessment.run_id,
            generated_at=datetime.now(timezone.utc),
            playbooks=playbooks,
            overall_market_bias=analysis.regime.value.upper(),
            blended_rr_ratio=round(blended_rr, 2),
            total_risk_usd=round(total_risk, 2),
            total_target_profit_usd=round(total_profit, 2),
            contingency_plans=[
                "Maintain strict stop discipline; never widen a stop loss during adverse moves",
                "Execute TP1 scale-out mechanically to achieve risk-neutral status",
            ],
        )

    def _empty_plan(
        self,
        plan_id: str,
        analysis: MarketAnalysis,
        assessment: RiskAssessment,
    ) -> StrategyPlan:
        """Return neutral plan when Risk Engine approved zero positions."""
        return StrategyPlan(
            plan_id=plan_id,
            analysis_run_id=analysis.run_id,
            risk_run_id=assessment.run_id,
            generated_at=datetime.now(timezone.utc),
            playbooks=[],
            overall_market_bias=analysis.regime.value.upper(),
            blended_rr_ratio=0.0,
            total_risk_usd=0.0,
            total_target_profit_usd=0.0,
            contingency_plans=[
                "No positions approved by Risk Engine under current market regime and limits.",
                "Maintain 100% cash preservation and monitor watchlist for clearer setups.",
            ],
        )

    def _extract_json(self, text: str) -> str | None:
        """Extract JSON block or raw JSON object."""
        match = _JSON_BLOCK.search(text)
        if match:
            return match.group(1).strip()
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end > brace_start:
            return text[brace_start : brace_end + 1].strip()
        return None
