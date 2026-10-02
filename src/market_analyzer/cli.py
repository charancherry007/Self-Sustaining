"""Command line interface.

    python -m market_analyzer run --profile INDIA_CASH_EQUITIES --limit 5
    python -m market_analyzer profiles
    python -m market_analyzer universe
    python -m market_analyzer doctor
    python -m market_analyzer risk assess --analysis-run <run_id> --equity 100000
"""

from __future__ import annotations

import asyncio
import json

import typer

from market_analyzer.config import (
    default_profile_id,
    list_profiles,
    load_app_config,
    load_market_profile,
)
from market_analyzer.pipeline.analyzer import MarketAnalyzer, build_provider
from market_analyzer.risk.config import list_risk_profiles, load_risk_profile
from market_analyzer.risk.engine import RiskEngine
from market_analyzer.storage.snapshots import SnapshotStore

app = typer.Typer(help="Market Analyzer — read-only market analysis + risk assessment.")

# Risk subcommands
risk_app = typer.Typer(help="Risk assessment commands.")
app.add_typer(risk_app, name="risk")


@app.command()
def run(
    profile: str = typer.Option("", help="Profile id. Defaults to MARKET_ANALYZER_PROFILE."),
    limit: int = typer.Option(5, help="Max candidates to return."),
    enrich_news: bool = typer.Option(False, help="Consult web sources for news."),
    as_json: bool = typer.Option(False, help="Print raw JSON instead of a table."),
) -> None:
    """Run an analysis for a market profile."""
    analyzer = MarketAnalyzer()
    market_profile = load_market_profile(profile.upper() if profile else None)
    try:
        analysis = asyncio.run(
            analyzer.run(market_profile, limit=limit, enrich_news=enrich_news)
        )
    finally:
        # Releases the search MCP subprocess when web research is enabled.
        asyncio.run(analyzer.aclose())
    if as_json:
        typer.echo(json.dumps(json.loads(analysis.model_dump_json()), indent=2))
        return

    typer.echo(f"run_id:       {analysis.run_id}")
    typer.echo(f"profile:      {analysis.profile_id}")
    typer.echo(f"provider:     {analysis.provider}")
    typer.echo(f"data_realtime:{analysis.data_realtime}")
    typer.echo(f"regime:       {analysis.regime.value}")
    typer.echo("")
    typer.echo(analysis.summary)
    typer.echo("")
    if analysis.candidates:
        header = f"{'SYMBOL':<14}{'SIDE':<7}{'SETUP':<22}{'SCORE':>7}{'PRICE':>12}"
        typer.echo(header)
        typer.echo("-" * len(header))
        for c in analysis.candidates:
            typer.echo(
                f"{c.symbol:<14}{c.side.value:<7}{c.setup.value:<22}"
                f"{c.score:>7.1f}{c.last_price:>12.2f}"
            )
    else:
        typer.echo("No candidates. NO_TRADE.")

    for warning in analysis.warnings:
        typer.secho(f"warning: {warning}", fg="yellow")
    typer.echo("")
    typer.echo(f"data quality: ok={analysis.data_quality.instruments_ok} "
               f"stale={analysis.data_quality.instruments_stale} "
               f"failed={analysis.data_quality.instruments_failed}")


@app.command()
def profiles() -> None:
    """List available market profiles."""
    for profile_id in list_profiles():
        typer.echo(profile_id)


@app.command()
def universe(profile: str = typer.Option("", help="Profile id.")) -> None:
    """List the instruments in a profile."""
    market_profile = load_market_profile(profile.upper() if profile else None)
    typer.echo(f"{market_profile.display_name} -- {len(market_profile.universe)} instruments")
    for item in market_profile.universe:
        typer.echo(f"  {item.symbol:<14}{item.sector or '-':<16}{item.name}")


@app.command()
def doctor() -> None:
    """Check config, provider, and knowledge wiring."""
    config = load_app_config()
    typer.echo(f"config file:   {config.config_path}")
    typer.echo(f"config:        loaded (provider={config.data.provider})")
    typer.echo(f"profiles:      {', '.join(list_profiles()) or 'none'}")
    typer.echo(f"active:        {default_profile_id()}")

    try:
        provider = build_provider(config)
        typer.echo(f"provider:      {provider.name} (realtime={provider.realtime})")
    except Exception as exc:  # noqa: BLE001 - doctor should report, not crash
        typer.secho(f"provider:      UNAVAILABLE -- {exc}", fg="red")
        typer.echo("")
        typer.echo("The Alpaca provider needs ALPACA_API_KEY and ALPACA_SECRET_KEY")
        typer.echo("in .env. The file must be KEY=VALUE, one per line.")
        return

    # Feed honesty, surfaced up front: this is the single fact most likely to
    # be misread as "the data is fully real-time".
    feed = getattr(provider, "feed", None)
    consolidated = getattr(provider, "volume_is_consolidated", True)
    if feed:
        typer.echo(f"feed:          {feed}")
        if not consolidated:
            typer.secho(
                "volume:        NOT consolidated - volume-derived signals are unreliable",
                fg="yellow",
            )
    session = getattr(provider, "session_state", None)
    if session is not None:
        typer.echo(f"session:       {session().value}")

    volume_gates = consolidated
    typer.echo(
        f"volume gates:  {'enabled' if volume_gates else 'DISABLED'}"
        + ("" if volume_gates
           else " (setups needing absolute volume are skipped)")
    )
    typer.echo(f"ai layer:      {'enabled' if config.ai.enabled else 'disabled'} (advisory only)")

    knowledge_dir = config.resolve(config.knowledge.core_directory)
    analyzer = MarketAnalyzer(config, provider=provider)
    records = analyzer.knowledge.retrieve(default_profile_id(), limit=100)
    typer.echo(f"knowledge:     {len(records)} record(s) from {knowledge_dir}")


# ==================== RISK SUBCOMMANDS ====================

@risk_app.command("assess")
def risk_assess(
    analysis_run: str = typer.Option(..., "--analysis-run", help="Market analysis run ID."),
    risk_profile: str = typer.Option("CONSERVATIVE", "--profile", help="Risk profile ID."),
    equity: float = typer.Option(100_000, "--equity", help="Portfolio equity in base currency."),
    positions: str = typer.Option(
        "{}", "--positions", 
        help="Open positions as JSON: '{\"AAPL\": 100, \"MSFT\": -50}'"
    ),
    as_json: bool = typer.Option(False, "--as-json", help="Print raw JSON."),
    no_ai: bool = typer.Option(False, "--no-ai", help="Disable AI narrative."),
) -> None:
    """Run risk assessment on a completed market analysis."""
    import json as json_lib
    
    store = SnapshotStore(
        load_app_config().resolve(load_app_config().output.directory),
        load_app_config().output.retain_runs,
    )
    analysis = store.load(analysis_run)
    if analysis is None:
        typer.secho(f"Analysis run not found: {analysis_run}", fg="red")
        raise typer.Exit(1)
    
    try:
        open_positions = json_lib.loads(positions)
    except json_lib.JSONDecodeError as e:
        typer.secho(f"Invalid --positions JSON: {e}", fg="red")
        raise typer.Exit(1) from e
    
    engine = RiskEngine()
    if no_ai:
        from market_analyzer.ai import build_ai_analyst
        from market_analyzer.risk.ai import AiRiskAnalyst

        engine.ai = AiRiskAnalyst(ai=build_ai_analyst(enabled=False))
    
    assessment = asyncio.run(engine.assess(
        analysis=analysis,
        risk_profile_id=risk_profile,
        portfolio_equity=equity,
        open_positions=open_positions,
    ))
    
    if as_json:
        typer.echo(json_lib.dumps(json_lib.loads(assessment.model_dump_json()), indent=2))
        return
    
    # Human-readable output
    typer.echo(f"risk_run_id:  {assessment.run_id}")
    typer.echo(f"analysis_run: {assessment.analysis_run_id}")
    typer.echo(f"equity:       ${assessment.portfolio_equity:,.0f}")
    typer.echo(f"heat:         {assessment.portfolio_heat_pct:.2%} (max 6%)")
    typer.echo(f"regime_mult:  {assessment.regime_adjustment:.2f}")
    typer.echo("")
    
    def print_positions(label: str, positions: list, color: str = None):
        if not positions:
            return
        typer.secho(f"{label} ({len(positions)}):", fg=color, bold=True)
        for p in positions:
            action_color = {
                "approve": "green",
                "reduce": "yellow", 
                "reject": "red",
                "defer": "blue",
            }.get(p.action.value, "white")
            typer.secho(
                f"  {p.symbol:<12} {p.action.value:<8} "
                f"size={p.size_pct_equity:.2%} units={p.size_units:>8.0f} "
                f"risk={p.risk_pct_equity:.2%} stop={p.stop_loss or 'N/A'} "
                f"target={p.take_profit or 'N/A'}",
                fg=action_color
            )
            for r in p.rationale:
                typer.echo(f"    -> {r}")
        typer.echo("")
    
    print_positions("APPROVED", assessment.approved, "green")
    print_positions("REDUCED", assessment.reduced, "yellow")
    print_positions("REJECTED", assessment.rejected, "red")
    print_positions("DEFERRED", assessment.deferred, "blue")
    
    if assessment.correlation_warnings:
        typer.secho("Correlation warnings:", fg="yellow")
        for w in assessment.correlation_warnings:
            typer.secho(f"  ! {w}", fg="yellow")
        typer.echo("")
    
    if assessment.ai_narrative:
        typer.secho("AI Narrative (UNTRUSTED):", fg="magenta", bold=True)
        typer.secho(f"  Regime: {assessment.ai_narrative.regime_interpretation}", fg="magenta")
        if assessment.ai_narrative.tail_risks:
            typer.secho("  Tail risks:", fg="magenta")
            for t in assessment.ai_narrative.tail_risks:
                typer.secho(f"    - {t}", fg="magenta")
        if assessment.ai_narrative.candidate_commentary:
            typer.secho("  Candidate commentary:", fg="magenta")
            for sym, c in assessment.ai_narrative.candidate_commentary.items():
                typer.secho(f"    {sym}: {c}", fg="magenta")
        if assessment.ai_narrative.rule_adjustment_proposals:
            typer.secho("  Rule proposals (pending review):", fg="magenta")
            for p in assessment.ai_narrative.rule_adjustment_proposals:
                typer.secho(f"    {p.get('rule_id')}: {p.get('proposed_change')}", fg="magenta")
        typer.echo(f"  Confidence: {assessment.ai_narrative.confidence:.0%}")
        typer.echo("")
    
    for w in assessment.warnings:
        typer.secho(f"warning: {w}", fg="yellow")


@risk_app.command("profiles")
def risk_profiles() -> None:
    """List available risk profiles."""
    for pid in list_risk_profiles():
        typer.echo(pid)


@risk_app.command("profile")
def risk_profile_show(profile: str = typer.Option("CONSERVATIVE", help="Profile ID.")) -> None:
    """Show risk profile details."""
    rp = load_risk_profile(profile)
    typer.echo(json.dumps(json.loads(rp.model_dump_json()), indent=2))


@risk_app.command("pending")
def risk_pending(
    limit: int = typer.Option(20, help="Max proposals to show."),
) -> None:
    """List pending AI risk rule proposals awaiting human review."""
    from market_analyzer.knowledge.loader import load_pending_records
    
    config = load_app_config()
    records = load_pending_records(config.resolve(config.knowledge.cases_directory))
    
    proposals = []
    for r in records:
        if r.get("kind") == "risk_rule_proposal" and r.get("status") == "pending_review":
            proposals.append(r)
    
    proposals.sort(key=lambda x: x.get("submitted_at", ""), reverse=True)
    
    if not proposals:
        typer.echo("No pending proposals.")
        return
    
    for p in proposals[:limit]:
        prop = p.get("proposal", {})
        typer.echo(f"ID: {p.get('id', 'unknown')}")
        typer.echo(f"  Source: {p.get('source')}")
        typer.echo(f"  Risk Profile: {p.get('risk_profile')}")
        typer.echo(f"  Rule ID: {prop.get('rule_id')}")
        typer.echo(f"  Proposed: {prop.get('proposed_change')}")
        typer.echo(f"  Reasoning: {prop.get('reasoning')}")
# Strategy subcommands
strategy_app = typer.Typer(help="AI Strategy Planner commands.")
app.add_typer(strategy_app, name="strategy")


@strategy_app.command("plan")
def strategy_plan_cmd(
    analysis_run: str = typer.Option(..., "--analysis-run", help="Market analysis run ID."),
    risk_profile: str = typer.Option("CONSERVATIVE", "--profile", help="Risk profile ID."),
    equity: float = typer.Option(100_000, "--equity", help="Portfolio equity in base currency."),
    as_json: bool = typer.Option(False, "--as-json", help="Print raw JSON."),
    no_ai: bool = typer.Option(False, "--no-ai", help="Disable AI narrative & use deterministic planner."),
) -> None:
    """Generate asymmetric execution playbooks from a completed market analysis."""
    import json as json_lib

    from market_analyzer.ai import build_ai_analyst
    from market_analyzer.strategy.planner import StrategyPlanner

    store = SnapshotStore(
        load_app_config().resolve(load_app_config().output.directory),
        load_app_config().output.retain_runs,
    )
    analysis = store.load(analysis_run)
    if analysis is None:
        typer.secho(f"Analysis run not found: {analysis_run}", fg="red")
        raise typer.Exit(1)

    engine = RiskEngine()
    if no_ai:
        from market_analyzer.risk.ai import AiRiskAnalyst
        engine.ai = AiRiskAnalyst(ai=build_ai_analyst(enabled=False))

    assessment = asyncio.run(
        engine.assess(
            analysis=analysis,
            risk_profile_id=risk_profile,
            portfolio_equity=equity,
            open_positions={},
        )
    )

    planner = StrategyPlanner(
        ai=build_ai_analyst(enabled=not no_ai),
    )
    plan = asyncio.run(
        planner.plan(
            analysis=analysis,
            assessment=assessment,
            portfolio_equity=equity,
        )
    )

    if as_json:
        typer.echo(json_lib.dumps(json_lib.loads(plan.model_dump_json()), indent=2))
        return

    # Human-readable output (pure ASCII)
    typer.secho(f"=== Strategy Plan: {plan.plan_id} ===", fg="cyan", bold=True)
    typer.echo(f"Market Bias:      {plan.overall_market_bias}")
    typer.echo(f"Blended R:R:      {plan.blended_rr_ratio:.2f} : 1")
    typer.echo(f"Total Risk:       ${plan.total_risk_usd:,.2f}")
    typer.echo(f"Target Profit:    ${plan.total_target_profit_usd:,.2f}")
    typer.echo("")

    if not plan.playbooks:
        typer.secho("No active playbooks generated (capital preservation mode).", fg="yellow")
        for c in plan.contingency_plans:
            typer.echo(f"  * {c}")
        return

    for pb in plan.playbooks:
        color = "green" if pb.action == "LONG" else "red"
        typer.secho(f"[{pb.action}] {pb.symbol} ({pb.tactic.value.title()})", fg=color, bold=True)
        typer.echo(f"  Order:      {pb.order_type.value.upper()} @ ${pb.entry_price:,.2f}")
        typer.echo(f"  Stop Loss:  ${pb.stop_loss:,.2f}")
        typer.echo(f"  BE Trigger: ${pb.breakeven_trigger:,.2f}")
        typer.echo(f"  R:R Ratio:  {pb.risk_reward_ratio:.2f} : 1 (-${pb.max_loss_usd:,.0f} / +${pb.projected_profit_usd:,.0f})")
        typer.echo("  Profit Roadmap:")
        for stage in pb.exit_stages:
            trail_msg = f" [{stage.trail_rule}]" if stage.trail_rule else ""
            typer.echo(f"    - {stage.label}: ${stage.target_price:,.2f} (+{stage.target_r_multiple:.1f}R){trail_msg}")
        if pb.invalidation_conditions:
            typer.echo("  Invalidation Rules:")
            for inv in pb.invalidation_conditions:
                typer.echo(f"    ! {inv}")
        typer.echo("")


if __name__ == "__main__":
    app()

