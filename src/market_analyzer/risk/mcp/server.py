"""MCP server for Risk Analyzer tools."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver import MCPServer

from market_analyzer.config import load_app_config
from market_analyzer.models.analysis import MarketAnalysis
from market_analyzer.risk.config import load_risk_profile
from market_analyzer.risk.engine import build_risk_engine
from market_analyzer.storage.snapshots import SnapshotStore

mcp = MCPServer("market-risk-analyzer")


def _load_analysis(run_id: str) -> MarketAnalysis:
    """Load a MarketAnalysis from snapshot store."""
    config = load_app_config()
    store = SnapshotStore(config.resolve(config.output.directory), config.output.retain_runs)
    analysis = store.load(run_id)
    if analysis is None:
        raise ValueError(f"Analysis run not found: {run_id}")
    return analysis


@mcp.tool()
async def assess_risk(
    analysis_run_id: str,
    risk_profile: str = "CONSERVATIVE",
    portfolio_equity: float = 100_000,
    open_positions: dict[str, float] | None = None,
    include_ai_narrative: bool = True,
) -> dict[str, Any]:
    """
    Run risk assessment on a completed market analysis.
    
    Args:
        analysis_run_id: Run ID from MarketAnalyzer (e.g., "abc123def456")
        risk_profile: Risk profile ID (CONSERVATIVE, MODERATE, AGGRESSIVE)
        portfolio_equity: Current portfolio equity in base currency
        open_positions: Dict of symbol -> current position size (e.g., {"AAPL": 100, "MSFT": -50})
        include_ai_narrative: Whether to include AI risk commentary
        
    Returns:
        RiskAssessment as dict
    """
    config = load_app_config()
    engine = build_risk_engine(config)
    
    # Temporarily disable AI if not requested
    if not include_ai_narrative:
        from market_analyzer.ai import build_ai_analyst
        from market_analyzer.risk.ai import AiRiskAnalyst

        engine.ai = AiRiskAnalyst(ai=build_ai_analyst(enabled=False))
    
    analysis = _load_analysis(analysis_run_id)
    assessment = await engine.assess(
        analysis=analysis,
        risk_profile_id=risk_profile,
        portfolio_equity=portfolio_equity,
        open_positions=open_positions or {},
    )
    
    return json.loads(assessment.model_dump_json())


@mcp.tool()
async def get_risk_assessment(run_id: str) -> dict[str, Any]:
    """Retrieve a saved risk assessment by run ID."""
    config = load_app_config()
    store = SnapshotStore(config.resolve(config.output.directory), config.output.retain_runs)
    assessment = store.load(run_id)
    if assessment is None:
        raise ValueError(f"Risk assessment not found: {run_id}")
    return json.loads(assessment.model_dump_json())


@mcp.tool()
async def list_risk_runs(limit: int = 50) -> list[str]:
    """List recent risk assessment run IDs."""
    config = load_app_config()
    store = SnapshotStore(config.resolve(config.output.directory), config.output.retain_runs)
    return store.list_runs()[:limit]


@mcp.tool()
async def get_risk_profile(profile_id: str = "CONSERVATIVE") -> dict[str, Any]:
    """Get risk profile configuration."""
    profile = load_risk_profile(profile_id)
    return json.loads(profile.model_dump_json())


@mcp.tool()
async def list_risk_profiles() -> list[str]:
    """List available risk profiles."""
    from market_analyzer.risk.config import list_risk_profiles
    return list_risk_profiles()


@mcp.tool()
async def explain_risk_decision(
    assessment_run_id: str,
    symbol: str,
) -> dict[str, Any]:
    """Get detailed rationale for a specific sizing decision."""
    config = load_app_config()
    store = SnapshotStore(config.resolve(config.output.directory), config.output.retain_runs)
    assessment = store.load(assessment_run_id)
    if assessment is None:
        raise ValueError(f"Risk assessment not found: {assessment_run_id}")
    
    # Find the position
    all_positions = (
        assessment.approved + assessment.reduced + 
        assessment.rejected + assessment.deferred
    )
    pos = next((p for p in all_positions if p.symbol == symbol), None)
    if pos is None:
        raise ValueError(f"Symbol {symbol} not found in assessment {assessment_run_id}")
    
    return {
        "symbol": symbol,
        "action": pos.action.value,
        "size_pct_equity": pos.size_pct_equity,
        "size_units": pos.size_units,
        "stop_loss": pos.stop_loss,
        "take_profit": pos.take_profit,
        "risk_pct_equity": pos.risk_pct_equity,
        "rationale": pos.rationale,
        "ai_commentary": assessment.ai_narrative.candidate_commentary.get(symbol) if assessment.ai_narrative else None,
        "ai_sizing_rationale": assessment.ai_narrative.sizing_rationale.get(symbol) if assessment.ai_narrative else None,
    }


@mcp.tool()
async def simulate_portfolio_heat(
    analysis_run_id: str,
    risk_profile: str = "CONSERVATIVE",
    portfolio_equity: float = 100_000,
    hypothetical_positions: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    What-if: portfolio heat if hypothetical positions added.
    
    Runs risk assessment with additional open positions to see impact.
    """
    config = load_app_config()
    engine = build_risk_engine(config)
    
    analysis = _load_analysis(analysis_run_id)
    assessment = await engine.assess(
        analysis=analysis,
        risk_profile_id=risk_profile,
        portfolio_equity=portfolio_equity,
        open_positions=hypothetical_positions or {},
    )
    
    return {
        "portfolio_heat_pct": assessment.portfolio_heat_pct,
        "max_allowed": assessment.portfolio_equity * 0.06,  # From profile
        "approved_count": len(assessment.approved),
        "rejected_count": len(assessment.rejected),
        "correlation_warnings": assessment.correlation_warnings,
    }


@mcp.tool()
async def list_pending_risk_proposals(limit: int = 20) -> list[dict[str, Any]]:
    """List pending AI risk rule proposals awaiting human review."""
    from market_analyzer.config import load_app_config
    from market_analyzer.knowledge.loader import load_pending_records
    
    config = load_app_config()
    records = load_pending_records(config.resolve(config.knowledge.cases_directory))
    
    proposals = []
    for r in records:
        if r.get("kind") == "risk_rule_proposal" and r.get("status") == "pending_review":
            proposals.append({
                "id": r.get("id", "unknown"),
                "source": r.get("source"),
                "risk_profile": r.get("risk_profile"),
                "proposal": r.get("proposal"),
                "submitted_at": r.get("submitted_at"),
            })
    
    # Sort by submission time, newest first
    proposals.sort(key=lambda x: x.get("submitted_at", ""), reverse=True)
    return proposals[:limit]


if __name__ == "__main__":
    mcp.run()