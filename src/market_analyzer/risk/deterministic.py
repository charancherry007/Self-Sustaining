"""Deterministic risk engine — pure rules, no AI. Same input always produces same output."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from market_analyzer.config import AppConfig, load_market_profile
from market_analyzer.models.analysis import MarketAnalysis, MarketRegime
from market_analyzer.models.risk import PositionSize, RiskAction, RiskAssessment, RiskProfile
from market_analyzer.providers.base import MarketDataProvider
from market_analyzer.risk.correlation import (
    correlation_penalty,
    correlation_warnings,
    fetch_correlation_matrix,
)
from market_analyzer.risk.sizing import apply_portfolio_limits, calculate_position_size


class DeterministicRiskEngine:
    """Pure rule-based sizing. No AI. Always produces same output for same input."""

    def __init__(self, config: AppConfig, provider: MarketDataProvider):
        self.config = config
        self.provider = provider
        self.profile: RiskProfile | None = None
        self.market_profile = None

    async def assess(
        self,
        analysis: MarketAnalysis,
        risk_profile_id: str,
        portfolio_equity: float,
        open_positions: dict[str, float] | None,
    ) -> RiskAssessment:
        
        from market_analyzer.risk.config import load_risk_profile
        self.profile = load_risk_profile(risk_profile_id)
        # Load market profile from analysis profile_id
        self.market_profile = load_market_profile(analysis.profile_id)
        open_positions = open_positions or {}
        
        # 1. Fetch correlation matrix
        candidate_symbols = [c.symbol for c in analysis.candidates]
        all_symbols = list(set(candidate_symbols) | set(open_positions.keys()))
        corr_matrix = await fetch_correlation_matrix(
            self.provider, all_symbols, self.profile.correlation_lookback_days
        )
        
        # 2. Build sector map
        sector_map = {}
        for c in analysis.candidates:
            instrument = self.market_profile.instrument(c.symbol)
            if instrument:
                sector_map[c.symbol] = instrument.sector or "UNKNOWN"
        for sym in open_positions:
            if sym not in sector_map:
                # Try to get from profile
                instrument = self.market_profile.instrument(sym)
                if instrument:
                    sector_map[sym] = instrument.sector or "UNKNOWN"
        
        # 3. Determine regime multiplier
        regime_mult = self.profile.regime_multipliers.get(analysis.regime.value, 1.0)
        
        # 4. Size each candidate
        sized = []
        for candidate in analysis.candidates:
            # Volume quality multiplier
            instrument = self.market_profile.instrument(candidate.symbol)
            volume_mult = 1.0
            if instrument and instrument.volume_kind in ("tick", "venue", "unknown", "none"):
                volume_mult = self.profile.volume_gate_penalty
            
            # Session multiplier
            session_mult = 1.0
            if hasattr(self.provider, "session_for") and instrument:
                session = self.provider.session_for(candidate.symbol)
                if hasattr(self.provider, "_is_session_open") and not self.provider._is_session_open(session):
                    session_mult = self.profile.session_penalty
            
            # Correlation penalty
            corr_mult = correlation_penalty(
                candidate.symbol, corr_matrix, open_positions, self.profile.correlation_threshold
            )
            
            pos = calculate_position_size(
                candidate=candidate,
                profile=self.profile,
                regime_mult=regime_mult,
                volume_mult=volume_mult,
                session_mult=session_mult,
                corr_mult=corr_mult,
                equity=portfolio_equity,
            )
            sized.append(pos)
        
        # 5. Apply portfolio-level limits
        sized = apply_portfolio_limits(
            sized, self.profile, portfolio_equity, open_positions, sector_map
        )
        
        # 6. Partition by action
        approved = [s for s in sized if s.action == RiskAction.APPROVE]
        reduced = [s for s in sized if s.action == RiskAction.REDUCE]
        rejected = [s for s in sized if s.action == RiskAction.REJECT]
        deferred = [s for s in sized if s.action == RiskAction.DEFER]
        
        # 7. Build risk rules applied list
        rules_applied = self._applied_rules(sized, analysis)
        
        # 8. Base warnings
        warnings = self._base_warnings(analysis)
        
        return RiskAssessment(
            run_id=uuid.uuid4().hex[:12],
            analysis_run_id=analysis.run_id,
            generated_at=datetime.now(timezone.utc),
            portfolio_equity=portfolio_equity,
            open_positions=open_positions,
            approved=approved,
            reduced=reduced,
            rejected=rejected,
            deferred=deferred,
            portfolio_heat_pct=sum(s.risk_pct_equity for s in approved),
            correlation_warnings=correlation_warnings(corr_matrix, approved, self.profile.correlation_threshold),
            regime_adjustment=regime_mult,
            risk_rules_applied=rules_applied,
            warnings=warnings,
        )

    def _applied_rules(self, positions: list[PositionSize], analysis: MarketAnalysis) -> list[str]:
        rules = []
        rules.append(f"max_portfolio_heat={self.profile.max_portfolio_heat_pct:.1%}")
        rules.append(f"max_single_position={self.profile.max_single_position_pct:.1%}")
        rules.append(f"regime_mult({analysis.regime.value})={self.profile.regime_multipliers.get(analysis.regime.value, 1.0):.2f}")
        rules.append(f"stop_atr_mult={self.profile.stop_loss_atr_multiple}")
        rules.append(f"target_r_mult={self.profile.take_profit_r_multiple}")
        
        # Volume penalties applied
        vol_penalized = [
            p.symbol for p in positions 
            if any("volume" in r.lower() for r in p.rationale)
        ]
        if vol_penalized:
            rules.append(f"volume_penalty({self.profile.volume_gate_penalty}): {', '.join(vol_penalized)}")
        
        # Session penalties
        sess_penalized = [
            p.symbol for p in positions 
            if any("session" in r.lower() for r in p.rationale)
        ]
        if sess_penalized:
            rules.append(f"session_penalty({self.profile.session_penalty}): {', '.join(sess_penalized)}")
        
        # Correlation penalties
        corr_penalized = [
            p.symbol for p in positions 
            if any("correlation" in r.lower() for r in p.rationale)
        ]
        if corr_penalized:
            rules.append(f"correlation_penalty: {', '.join(corr_penalized)}")
        
        return rules

    def _base_warnings(self, analysis: MarketAnalysis) -> list[str]:
        warnings = []
        
        # Data quality warnings
        if analysis.data_quality.instruments_stale > 0:
            warnings.append(
                f"{analysis.data_quality.instruments_stale} instrument(s) have stale data"
            )
        if analysis.data_quality.instruments_failed > 0:
            warnings.append(
                f"{analysis.data_quality.instruments_failed} instrument(s) failed to fetch"
            )
        
        # Volume honesty warnings (from analysis)
        for w in analysis.warnings:
            if "volume" in w.lower() or "consolidated" in w.lower():
                warnings.append(w)
        
        # Session warnings
        for w in analysis.warnings:
            if "session" in w.lower():
                warnings.append(w)
        
        # Regime warnings
        if analysis.regime == MarketRegime.HIGH_VOLATILITY:
            warnings.append("HIGH_VOLATILITY regime — sizes significantly reduced")
        elif analysis.regime == MarketRegime.UNKNOWN:
            warnings.append("UNKNOWN regime — conservative sizing applied")
        
        return warnings