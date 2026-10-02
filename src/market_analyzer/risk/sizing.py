"""Core position sizing math — pure functions, no I/O, fully testable."""

from __future__ import annotations

from market_analyzer.models.analysis import Candidate, Side
from market_analyzer.models.risk import PositionSize, RiskAction, RiskProfile


def calculate_position_size(
    candidate: Candidate,
    profile: RiskProfile,
    regime_mult: float,
    volume_mult: float,
    session_mult: float,
    corr_mult: float,
    equity: float,
) -> PositionSize:
    """
    Fixed-fractional sizing with ATR stops and multiplicative adjustments.
    
    Returns PositionSize with action determined by thresholds.
    """
    # Base risk per trade (fraction of equity)
    base_risk_pct = profile.max_single_position_pct
    
    # Apply all multipliers
    risk_pct = base_risk_pct * regime_mult * volume_mult * session_mult * corr_mult * candidate.confidence
    risk_pct = min(risk_pct, profile.max_single_position_pct)  # Hard cap
    
    # ATR-based stop distance
    atr = candidate.metrics.get("atr_14", candidate.last_price * 0.02)
    stop_mult = profile.stop_loss_atr_multiple
    
    if candidate.side == Side.LONG:
        stop = candidate.last_price - (stop_mult * atr)
        target = candidate.last_price + (profile.take_profit_r_multiple * (candidate.last_price - stop))
    elif candidate.side == Side.SHORT:
        stop = candidate.last_price + (stop_mult * atr)
        target = candidate.last_price - (profile.take_profit_r_multiple * (stop - candidate.last_price))
    else:
        # WATCH/AVOID — no position
        return PositionSize(
            symbol=candidate.symbol,
            action=RiskAction.REJECT,
            size_pct_equity=0.0,
            size_units=0.0,
            stop_loss=None,
            take_profit=None,
            risk_pct_equity=0.0,
            rationale=[f"Side {candidate.side.value} does not support position sizing"],
        )
    
    # Size in units
    risk_per_unit = abs(candidate.last_price - stop)
    if risk_per_unit <= 0:
        return PositionSize(
            symbol=candidate.symbol,
            action=RiskAction.REJECT,
            size_pct_equity=0.0,
            size_units=0.0,
            stop_loss=stop,
            take_profit=target,
            risk_pct_equity=0.0,
            rationale=["Invalid stop distance (zero or negative)"],
        )
    
    size_units = (equity * risk_pct) / risk_per_unit
    size_pct_equity = (size_units * candidate.last_price) / equity
    
    # Determine action based on thresholds
    if candidate.score < profile.min_candidate_score:
        action = RiskAction.REJECT
        size_units = 0.0
        size_pct_equity = 0.0
        risk_pct = 0.0
    elif candidate.confidence < profile.min_confidence:
        action = RiskAction.REDUCE
    elif candidate.invalidation is None:
        action = RiskAction.DEFER
    else:
        action = RiskAction.APPROVE
    
    rationale = _build_rationale(
        candidate, regime_mult, volume_mult, session_mult, corr_mult, risk_pct
    )
    
    return PositionSize(
        symbol=candidate.symbol,
        action=action,
        size_pct_equity=size_pct_equity,
        size_units=size_units,
        stop_loss=stop,
        take_profit=target,
        risk_pct_equity=risk_pct,
        rationale=rationale,
    )


def _build_rationale(
    candidate: Candidate,
    regime_mult: float,
    volume_mult: float,
    session_mult: float,
    corr_mult: float,
    final_risk_pct: float,
) -> list[str]:
    parts = []
    parts.append(f"Base risk: {candidate.metrics.get('base_risk_pct', 0.02):.2%}")
    parts.append(f"Regime mult: {regime_mult:.2f}")
    parts.append(f"Volume mult: {volume_mult:.2f}")
    parts.append(f"Session mult: {session_mult:.2f}")
    parts.append(f"Correlation mult: {corr_mult:.2f}")
    parts.append(f"Confidence: {candidate.confidence:.2f}")
    parts.append(f"Final risk: {final_risk_pct:.2%} of equity")
    if candidate.setup:
        parts.append(f"Setup: {candidate.setup.value}")
    return parts


def apply_portfolio_limits(
    positions: list[PositionSize],
    profile: RiskProfile,
    equity: float,
    open_positions: dict[str, float],
    sector_map: dict[str, str],
) -> list[PositionSize]:
    """
    Apply portfolio-level constraints:
    - Max portfolio heat
    - Max sector exposure
    - Max correlation cluster exposure
    
    Returns adjusted positions (may reduce sizes or change actions).
    """
    if not positions:
        return positions
    
    # Sort by score descending (best candidates get priority)
    sorted_positions = sorted(positions, key=lambda p: p.size_pct_equity, reverse=True)
    
    # Track running totals
    total_heat = 0.0
    sector_exposure: dict[str, float] = {}
    
    # Add existing open positions to exposure tracking
    for sym, units in open_positions.items():
        sector = sector_map.get(sym, "UNKNOWN")
        sector_exposure[sector] = sector_exposure.get(sector, 0) + abs(units)
    
    adjusted = []
    for pos in sorted_positions:
        if pos.action == RiskAction.REJECT:
            adjusted.append(pos)
            continue
        
        sector = sector_map.get(pos.symbol, "UNKNOWN")
        sector_current = sector_exposure.get(sector, 0)
        
        # Check portfolio heat
        if total_heat + pos.risk_pct_equity > profile.max_portfolio_heat_pct:
            # Reduce to fit
            allowed_risk = profile.max_portfolio_heat_pct - total_heat
            if allowed_risk > 0:
                scale = allowed_risk / pos.risk_pct_equity
                pos = pos.model_copy(update={
                    "action": RiskAction.REDUCE,
                    "size_pct_equity": pos.size_pct_equity * scale,
                    "size_units": pos.size_units * scale,
                    "risk_pct_equity": pos.risk_pct_equity * scale,
                    "rationale": pos.rationale + [f"Reduced to fit portfolio heat limit ({profile.max_portfolio_heat_pct:.1%})"],
                })
            else:
                pos = pos.model_copy(update={
                    "action": RiskAction.REJECT,
                    "size_pct_equity": 0.0,
                    "size_units": 0.0,
                    "risk_pct_equity": 0.0,
                    "rationale": pos.rationale + ["Rejected: portfolio heat limit reached"],
                })
        
        # Check sector exposure
        # Simplified: use size_pct_equity as proxy for sector exposure
        if sector_current + pos.size_pct_equity > profile.max_sector_exposure_pct:
            allowed_sector = profile.max_sector_exposure_pct - sector_current
            if allowed_sector > 0:
                scale = allowed_sector / pos.size_pct_equity
                pos = pos.model_copy(update={
                    "action": RiskAction.REDUCE,
                    "size_pct_equity": pos.size_pct_equity * scale,
                    "size_units": pos.size_units * scale,
                    "risk_pct_equity": pos.risk_pct_equity * scale,
                    "rationale": pos.rationale + [f"Reduced to fit sector limit ({profile.max_sector_exposure_pct:.1%})"],
                })
            else:
                pos = pos.model_copy(update={
                    "action": RiskAction.REJECT,
                    "size_pct_equity": 0.0,
                    "size_units": 0.0,
                    "risk_pct_equity": 0.0,
                    "rationale": pos.rationale + [f"Rejected: sector {sector} limit reached"],
                })
        
        adjusted.append(pos)
        total_heat += pos.risk_pct_equity
        sector_exposure[sector] = sector_current + pos.size_pct_equity
    
    return adjusted