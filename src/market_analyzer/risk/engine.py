"""Risk engine orchestration — combines deterministic sizing with AI advisory."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from market_analyzer.config import AppConfig
from market_analyzer.knowledge.writer import PendingLessonWriter
from market_analyzer.models.analysis import MarketAnalysis
from market_analyzer.models.risk import RiskAssessment, RiskNarrative
from market_analyzer.providers.base import MarketDataProvider
from market_analyzer.risk.ai import AiRiskAnalyst
from market_analyzer.risk.config import load_risk_profile
from market_analyzer.risk.deterministic import DeterministicRiskEngine


class RiskEngine:
    """Main risk assessment engine. Combines deterministic rules with AI advisory."""

    def __init__(
        self,
        config: AppConfig | None = None,
        provider: MarketDataProvider | None = None,
        ai_analyst: AiRiskAnalyst | None = None,
    ) -> None:
        from market_analyzer.config import load_app_config
        from market_analyzer.pipeline.analyzer import build_provider
        
        self.config = config or load_app_config()
        self.provider = provider or build_provider(self.config)
        self.ai = ai_analyst or AiRiskAnalyst()
        self._deterministic = DeterministicRiskEngine(self.config, self.provider)

    async def assess(
        self,
        analysis: MarketAnalysis,
        risk_profile_id: str | None = None,
        portfolio_equity: float = 100_000,
        open_positions: dict[str, float] | None = None,
    ) -> RiskAssessment:
        """
        Run complete risk assessment.
        
        Args:
            analysis: MarketAnalysis from MarketAnalyzer
            risk_profile_id: Risk profile to use (default from config/env)
            portfolio_equity: Current portfolio equity in base currency
            open_positions: Dict of symbol -> current position size (units)
            
        Returns:
            RiskAssessment with deterministic sizing + AI narrative
        """
        risk_profile_id = risk_profile_id or self.config.risk.profile if hasattr(self.config, 'risk') else None
        risk_profile = load_risk_profile(risk_profile_id)
        open_positions = open_positions or {}
        
        # 1. HARD GATES (fail-closed, no trade on invalid/stale feed)
        self._validate_hard_gates(analysis)
        
        # 2. AI RISK ANALYSIS (AI performs evaluation, sizing, and risk decisions)
        approved, reduced, rejected, deferred, heat_pct, correlation_warns, ai_narrative = (
            await self.ai.assess_risk_with_ai(
                analysis=analysis,
                risk_profile=risk_profile,
                portfolio_equity=portfolio_equity,
                open_positions=open_positions,
            )
        )
        
        # Fallback to deterministic calculation only when AI is explicitly disabled
        base = None
        if not self.ai.ai.enabled and not approved and not reduced and not rejected and not deferred:
            base = await self._deterministic.assess(
                analysis, risk_profile.id, portfolio_equity, open_positions
            )
            approved = base.approved
            reduced = base.reduced
            rejected = base.rejected
            deferred = base.deferred
            heat_pct = base.portfolio_heat_pct
            correlation_warns = base.correlation_warnings

        # 3. SUBMIT AI PROPOSALS -> PENDING KNOWLEDGE (not auto-applied)
        pending_rule_ids = []
        for proposal in getattr(ai_narrative, "rule_adjustment_proposals", []):
            if proposal.get("rule_id"):
                await self._submit_rule_proposal(proposal, risk_profile.id)
                pending_rule_ids.append(proposal["rule_id"])
        
        # 4. FINAL ASSEMBLY -- Driven directly by AI analysis
        final = RiskAssessment(
            run_id=uuid.uuid4().hex[:12],
            analysis_run_id=analysis.run_id,
            generated_at=datetime.now(timezone.utc),
            portfolio_equity=portfolio_equity,
            open_positions=open_positions,
            approved=approved,
            reduced=reduced,
            rejected=rejected,
            deferred=deferred,
            portfolio_heat_pct=heat_pct,
            correlation_warnings=correlation_warns,
            regime_adjustment=risk_profile.regime_multipliers.get(analysis.regime.value, 1.0),
            risk_rules_applied=["AI_RISK_ANALYZER"],
            warnings=self._ai_warnings(ai_narrative),
            ai_narrative=ai_narrative,
            ai_proposals_pending=pending_rule_ids,
            deterministic_base=base,
        )
        
        return final

    def _validate_hard_gates(self, analysis: MarketAnalysis) -> None:
        """Non-negotiable gates. AI cannot override."""
        if self.config.data.require_realtime and not analysis.data_realtime:
            raise RuntimeError(
                "Risk assessment requires real-time data. "
                f"Provider '{analysis.provider}' reports realtime={analysis.data_realtime}."
            )
        if analysis.data_quality.instruments_ok == 0:
            raise RuntimeError("No valid market data for risk assessment")
        if analysis.data_quality.instruments_failed > len(analysis.candidates) * 0.5:
            raise RuntimeError(
                f"Too many failed instruments ({analysis.data_quality.instruments_failed}) "
                f"for reliable risk calculation"
            )

    def _ai_warnings(self, narrative: RiskNarrative) -> list[str]:
        warnings = []
        if narrative.confidence < 0.5:
            warnings.append(f"AI risk analyst confidence low ({narrative.confidence:.0%})")
        if narrative.rule_adjustment_proposals:
            warnings.append(
                f"AI proposed {len(narrative.rule_adjustment_proposals)} rule changes "
                "(pending human review in knowledge/pending)"
            )
        if narrative.tail_risks:
            warnings.append(f"AI identified {len(narrative.tail_risks)} tail risk(s)")
        return warnings

    async def _submit_rule_proposal(self, proposal: dict, risk_profile_id: str) -> None:
        """Write to knowledge/pending for human approval. Never auto-apply."""
        writer = PendingLessonWriter(self.config.resolve(self.config.knowledge.cases_directory))
        writer.append({
            "kind": "risk_rule_proposal",
            "source": f"ai_{proposal.get('model', 'unknown')}",
            "risk_profile": risk_profile_id,
            "proposal": proposal,
            "status": "pending_review",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        })


def build_risk_engine(config: AppConfig | None = None) -> RiskEngine:
    """Factory for CLI/MCP usage."""
    return RiskEngine(config=config)