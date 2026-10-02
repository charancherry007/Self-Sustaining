"""AI-driven risk analyst — advisory only, never makes decisions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace

from market_analyzer.ai import AiAnalyst, build_ai_analyst
from market_analyzer.models.analysis import MarketAnalysis
from market_analyzer.models.risk import (
    PositionSize,
    RiskAction,
    RiskAssessment,
    RiskNarrative,
    RiskProfile,
)


@dataclass(frozen=True)
class _RiskNarrativeInternal:
    """Internal mutable version for building."""
    regime_interpretation: str
    tail_risks: list[str]
    candidate_commentary: dict[str, str]
    sizing_rationale: dict[str, str]
    rule_adjustment_proposals: list[dict]
    confidence: float
    model: str
    prompt_hash: str
    untrusted: bool = True
    
    def to_public(self) -> RiskNarrative:
        return RiskNarrative(
            regime_interpretation=self.regime_interpretation,
            tail_risks=self.tail_risks,
            candidate_commentary=self.candidate_commentary,
            sizing_rationale=self.sizing_rationale,
            rule_adjustment_proposals=self.rule_adjustment_proposals,
            confidence=self.confidence,
            model=self.model,
            prompt_hash=self.prompt_hash,
            untrusted=self.untrusted,
        )


class AiRiskAnalyst:
    """
    Advisory AI for risk assessment. Never makes decisions.
    All outputs require deterministic validation.
    """

    def __init__(self, ai: AiAnalyst | None = None):
        self.ai = ai or build_ai_analyst(enabled=True)

    async def analyze(
        self,
        analysis: MarketAnalysis,
        base_assessment: RiskAssessment,
        risk_profile: RiskProfile,
        portfolio_context: dict,
    ) -> RiskNarrative:
        """
        Generate risk narrative. Returns neutral narrative on any failure.
        """
        if not self.ai.enabled or not risk_profile.ai_enabled:
            return self._neutral_narrative()

        prompt = self._build_prompt(analysis, base_assessment, risk_profile, portfolio_context)
        
        try:
            response = await self.ai.chat(
                prompt, 
                temperature=risk_profile.ai_temperature, 
                max_tokens=risk_profile.ai_max_tokens,
                timeout=risk_profile.ai_timeout_seconds,
            )
            narrative = self._parse_narrative(response, risk_profile.ai_model or getattr(self.ai, "models", ["openrouter"])[0])
            narrative = replace(narrative, prompt_hash=self._hash_prompt(prompt))
            return narrative.to_public()
        except Exception:
            return self._neutral_narrative()

    async def assess_risk_with_ai(
        self,
        analysis: MarketAnalysis,
        risk_profile: RiskProfile,
        portfolio_equity: float,
        open_positions: dict[str, float],
    ) -> tuple[list[PositionSize], list[PositionSize], list[PositionSize], list[PositionSize], float, list[str], RiskNarrative]:
        """Run complete risk assessment and position sizing using AI only."""
        approved: list[PositionSize] = []
        reduced: list[PositionSize] = []
        rejected: list[PositionSize] = []
        deferred: list[PositionSize] = []
        correlation_warnings: list[str] = []
        portfolio_heat_pct = 0.0

        if not self.ai.enabled or not risk_profile.ai_enabled:
            narrative = self._neutral_narrative()
            return approved, reduced, rejected, deferred, portfolio_heat_pct, correlation_warnings, narrative

        prompt = self._build_risk_assessment_prompt(analysis, risk_profile, portfolio_equity, open_positions)
        try:
            model_name = risk_profile.ai_model or getattr(self.ai, "models", ["openrouter"])[0]
            response = await self.ai.chat(
                prompt,
                temperature=risk_profile.ai_temperature,
                max_tokens=risk_profile.ai_max_tokens,
                timeout=risk_profile.ai_timeout_seconds,
            )
            json_str = self._extract_json(response)
            if not json_str:
                raise ValueError("No JSON found in AI response")
            data = json.loads(json_str)

            portfolio_heat_pct = max(0.0, min(1.0, float(data.get("portfolio_heat_pct", 0.0))))
            correlation_warnings = [str(w) for w in data.get("correlation_warnings", [])]

            for item in data.get("decisions", []):
                sym = str(item.get("symbol", "")).upper()
                action_str = str(item.get("action", "reject")).lower()
                action = RiskAction.REJECT
                if action_str in ("approve", "approved"):
                    action = RiskAction.APPROVE
                elif action_str in ("reduce", "reduced"):
                    action = RiskAction.REDUCE
                elif action_str in ("defer", "deferred"):
                    action = RiskAction.DEFER

                size_pct = max(0.0, min(risk_profile.max_single_position_pct, float(item.get("size_pct_equity", 0.0))))
                size_units = float(item.get("size_units")) if item.get("size_units") is not None else None
                stop_loss = float(item.get("stop_loss")) if item.get("stop_loss") is not None else None
                take_profit = float(item.get("take_profit")) if item.get("take_profit") is not None else None
                risk_pct = max(0.0, min(0.1, float(item.get("risk_pct_equity", 0.005))))
                rationale = [str(r) for r in item.get("rationale", [])]

                pos = PositionSize(
                    symbol=sym,
                    action=action,
                    size_pct_equity=size_pct,
                    size_units=size_units,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    risk_pct_equity=risk_pct,
                    rationale=rationale,
                )
                if action == RiskAction.APPROVE:
                    approved.append(pos)
                elif action == RiskAction.REDUCE:
                    reduced.append(pos)
                elif action == RiskAction.DEFER:
                    deferred.append(pos)
                else:
                    rejected.append(pos)

            narrative_data = data.get("ai_narrative") or data
            narrative = RiskNarrative(
                regime_interpretation=str(narrative_data.get("regime_interpretation", analysis.regime.value))[:500],
                tail_risks=[str(r)[:200] for r in narrative_data.get("tail_risks", [])[:10]],
                candidate_commentary={str(k): str(v)[:200] for k, v in narrative_data.get("candidate_commentary", {}).items()},
                sizing_rationale={str(k): str(v)[:200] for k, v in narrative_data.get("sizing_rationale", {}).items()},
                rule_adjustment_proposals=[],
                confidence=max(0.0, min(1.0, float(narrative_data.get("confidence", 0.85)))),
                model=model_name,
                prompt_hash=self._hash_prompt(prompt),
                untrusted=True,
            )
            return approved, reduced, rejected, deferred, portfolio_heat_pct, correlation_warnings, narrative
        except Exception as exc:
            narrative = self._neutral_narrative_internal(getattr(self.ai, "models", ["openrouter"])[0], str(exc)).to_public()
            return approved, reduced, rejected, deferred, portfolio_heat_pct, correlation_warnings, narrative

    def _build_risk_assessment_prompt(
        self,
        analysis: MarketAnalysis,
        risk_profile: RiskProfile,
        portfolio_equity: float,
        open_positions: dict[str, float],
    ) -> str:
        candidates_fmt = self._format_candidates(analysis.candidates)
        knowledge_fmt = self._format_knowledge(analysis.knowledge_refs)
        ai_synthesis = ""
        if analysis.ai_analysis:
            ai_synthesis = f"\nAI Market Synthesis: {analysis.ai_analysis.get('market_synthesis', '')}\nRisk Tone: {analysis.ai_analysis.get('risk_tone', '')}\n"

        return f"""You are the automated AI Risk Engine for a multi-asset trading system.
Evaluate the market analysis and candidate setups, and decide exact risk-controlled position sizing and actions using AI.

=== MARKET ANALYSIS ===
Profile: {analysis.profile_id}
Regime: {analysis.regime.value} -- {"; ".join(analysis.regime_rationale)}
Provider: {analysis.provider} (realtime={analysis.data_realtime})
Warnings: {"; ".join(analysis.warnings) if analysis.warnings else "none"}
{ai_synthesis}

=== CANDIDATES TO ASSESS ===
{candidates_fmt}

=== PORTFOLIO CONTEXT ===
Equity: ${portfolio_equity:,.2f}
Current Open Positions: {open_positions}
Risk Profile: {risk_profile.id}
Max Portfolio Heat: {risk_profile.max_portfolio_heat_pct:.1%}
Max Single Position Size: {risk_profile.max_single_position_pct:.1%}
Stop Loss ATR Multiple: {risk_profile.stop_loss_atr_multiple}
Take Profit R Multiple: {risk_profile.take_profit_r_multiple}

=== KNOWLEDGE RULES ===
{knowledge_fmt}

=== INSTRUCTIONS ===
For EACH candidate, determine:
- action: "approve" | "reduce" | "defer" | "reject"
- size_pct_equity: between 0.0 and {risk_profile.max_single_position_pct} (e.g. 0.015 for 1.5%)
- size_units: units based on price and equity ((size_pct_equity * equity) / last_price)
- stop_loss: absolute price level
- take_profit: absolute price level
- risk_pct_equity: risk percentage of equity (e.g. 0.003)
- rationale: list of strings justifying the sizing and risk decision

Also provide portfolio-level heat estimate, correlation warnings, and market regime commentary.
Return ONLY valid JSON matching this exact structure:
{{
  "portfolio_heat_pct": 0.02,
  "correlation_warnings": ["..."],
  "decisions": [
    {{
      "symbol": "SYMBOL",
      "action": "approve|reduce|defer|reject",
      "size_pct_equity": 0.015,
      "size_units": 10.5,
      "stop_loss": 100.0,
      "take_profit": 110.0,
      "risk_pct_equity": 0.003,
      "rationale": ["Reason 1", "Reason 2"]
    }}
  ],
  "ai_narrative": {{
    "regime_interpretation": "1-2 sentences",
    "tail_risks": ["..."],
    "candidate_commentary": {{"SYMBOL": "..."}},
    "sizing_rationale": {{"SYMBOL": "..."}},
    "confidence": 0.9
  }}
}}
"""

    def _build_prompt(
        self,
        analysis: MarketAnalysis,
        base_assessment: RiskAssessment,
        risk_profile: RiskProfile,
        portfolio_context: dict,
    ) -> str:
        
        candidates_fmt = self._format_candidates(analysis.candidates)
        knowledge_fmt = self._format_knowledge(analysis.knowledge_refs)
        
        return f"""You are a senior risk analyst. Provide concise, actionable risk commentary.
Your output is ADVISORY ONLY. Hard limits are enforced by deterministic rules.

=== MARKET ANALYSIS ===
Profile: {analysis.profile_id}
Regime: {analysis.regime.value} — {"; ".join(analysis.regime_rationale)}
Provider: {analysis.provider} (realtime={analysis.data_realtime})
Data Quality: OK={analysis.data_quality.instruments_ok}, \
Stale={analysis.data_quality.instruments_stale}, \
Failed={analysis.data_quality.instruments_failed}
Warnings: {"; ".join(analysis.warnings) if analysis.warnings else "none"}

=== CANDIDATES ===
{candidates_fmt}

=== BASE ASSESSMENT (DETERMINISTIC) ===
Portfolio Equity: ${portfolio_context.get('equity', 0):,.0f}
Open Positions: {portfolio_context.get('open_positions', {})}
Max Portfolio Heat: {risk_profile.max_portfolio_heat_pct:.1%}
Max Single Position: {risk_profile.max_single_position_pct:.1%}
Regime Multiplier: \
{risk_profile.regime_multipliers.get(analysis.regime.value, 1.0):.2f}
Approved: {[(p.symbol, f"{p.size_pct_equity:.2%}") \
for p in base_assessment.approved]}
Reduced: {[(p.symbol, f"{p.size_pct_equity:.2%}") \
for p in base_assessment.reduced]}
Rejected: {[(p.symbol, p.rationale[0] if p.rationale else "no rationale") \
for p in base_assessment.rejected]}
Deferred: {[(p.symbol, p.rationale[0] if p.rationale else "no rationale") \
for p in base_assessment.deferred]}

=== RISK PROFILE ===
{risk_profile.model_dump_json(indent=2)}

=== KNOWLEDGE (RULES & LESSONS) ===
{knowledge_fmt}

=== TASK ===
Provide a JSON object with EXACTLY these fields:
{{
  "regime_interpretation": "1-2 sentences on regime nuance mechanical \
indicators miss",
  "tail_risks": ["specific, dated risks: earnings, events, macro"],
  "candidate_commentary": {{"SYMBOL": "1 sentence on setup quality \
beyond score"}},
  "sizing_rationale": {{"SYMBOL": "why size is appropriate or should adjust"}},
  "rule_adjustment_proposals": [
    {{"rule_id": "RISK-XXX", "proposed_change": "specific config change", \
"reasoning": "why"}}
  ],
  "confidence": 0.0-1.0
}}

CONSTRAINTS:
- Never suggest violating hard limits (max_heat, max_position)
- Never recommend a trade the deterministic engine rejected
- Be specific: "Fed meeting Dec 18" not "macro uncertainty"
- If unsure, say so in rationale and lower confidence
- No markdown, pure JSON only
"""

    def _format_candidates(self, candidates: list) -> str:
        if not candidates:
            return "No candidates."
        lines = []
        for c in candidates:
            atr = c.metrics.get("atr_14")
            atr_str = f"{atr:.4f}" if isinstance(atr, (int, float)) else str(atr or "N/A")
            vol = c.metrics.get("volume_ratio")
            vol_str = f"{vol:.2f}" if isinstance(vol, (int, float)) else str(vol or "N/A")
            rsi = c.metrics.get("rsi_14")
            rsi_str = f"{rsi:.1f}" if isinstance(rsi, (int, float)) else str(rsi or "N/A")
            lines.append(
                f"  {c.symbol}: {c.setup.value} {c.side.value} "
                f"score={c.score:.1f} conf={c.confidence:.2f} "
                f"price={c.last_price:.2f} inv={c.invalidation or 'N/A'} "
                f"metrics={{atr_14={atr_str}, vol_ratio={vol_str}, rsi_14={rsi_str}}}"
            )
        return "\n".join(lines)

    def _format_knowledge(self, refs: list[str]) -> str:
        if not refs:
            return "No knowledge references."
        return "\n".join(f"  - {r}" for r in refs)

    def _parse_narrative(self, response: str, model: str) -> _RiskNarrativeInternal:
        """Parse AI response into narrative. Returns neutral on parse failure."""
        # Extract JSON from response
        json_str = self._extract_json(response)
        if not json_str:
            return self._neutral_narrative_internal(model, "no_json")
        
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return self._neutral_narrative_internal(model, "json_decode_error")
        
        # Validate required fields
        required = [
            "regime_interpretation", "tail_risks", "candidate_commentary",
            "sizing_rationale", "rule_adjustment_proposals", "confidence"
        ]
        for field in required:
            if field not in data:
                return self._neutral_narrative_internal(model, f"missing_field_{field}")
        
        # Clamp confidence
        confidence = max(0.0, min(1.0, float(data["confidence"])))
        
        return _RiskNarrativeInternal(
            regime_interpretation=str(data["regime_interpretation"])[:500],
            tail_risks=[str(r)[:200] for r in data["tail_risks"][:10]],
            candidate_commentary={
                str(k): str(v)[:200] for k, v in data["candidate_commentary"].items()
            },
            sizing_rationale={
                str(k): str(v)[:200] for k, v in data["sizing_rationale"].items()
            },
            rule_adjustment_proposals=[
                {str(k): str(v)[:300] for k, v in p.items()}
                for p in data["rule_adjustment_proposals"][:5]
            ],
            confidence=confidence,
            model=model,
            prompt_hash="",  # Filled in after
        )  # noqa: E501

    def _extract_json(self, text: str) -> str | None:
        """Extract first valid JSON object from text."""
        text = text.strip()
        # Try direct parse
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass
        
        # Try to find JSON block
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            candidate = text[start:end+1]
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass
        
        return None

    def _hash_prompt(self, prompt: str) -> str:
        return hashlib.sha256(prompt.encode()).hexdigest()[:16]

    def _neutral_narrative(self) -> RiskNarrative:
        return RiskNarrative(
            regime_interpretation="AI disabled or unavailable; using deterministic assessment only.",
            tail_risks=[],
            candidate_commentary={},
            sizing_rationale={},
            rule_adjustment_proposals=[],
            confidence=0.0,
            model="none",
            prompt_hash="",
            untrusted=True,
        )

    def _neutral_narrative_internal(self, model: str, reason: str) -> _RiskNarrativeInternal:
        return _RiskNarrativeInternal(
            regime_interpretation=f"AI analysis failed: {reason}",
            tail_risks=[],
            candidate_commentary={},
            sizing_rationale={},
            rule_adjustment_proposals=[],
            confidence=0.0,
            model=model,
            prompt_hash="",
            untrusted=True,
        )