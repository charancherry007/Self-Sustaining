"""Streamlit Application for Market Analyzer, AI Risk Engine & Strategy Planner."""

from __future__ import annotations

import asyncio
import os
import uuid

import streamlit as st

from market_analyzer.ai import build_ai_analyst
from market_analyzer.config import load_app_config, load_market_profile
from market_analyzer.execution.monitor import TradeMonitor
from market_analyzer.execution.simulator import SimulatedExecutionClient
from market_analyzer.execution.tradingview_client import TradingViewClient
from market_analyzer.knowledge.graph import TradeKnowledgeGraphBuilder
from market_analyzer.models.execution import OrderRequest, OrderStatus
from market_analyzer.models.profile import AssetClass
from market_analyzer.pipeline.analyzer import MarketAnalyzer, build_provider
from market_analyzer.pipeline.symbols import create_custom_instrument, parse_custom_symbol
from market_analyzer.risk.engine import RiskEngine
from market_analyzer.strategy.planner import StrategyPlanner
from market_analyzer.telemetry import get_telemetry_summary

st.set_page_config(
    page_title="Market Analyzer",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Execution & Broker Settings Sidebar
st.sidebar.markdown("### ⚙️ Execution Settings")
broker_mode = st.sidebar.selectbox(
    "Broker Connection",
    options=["Simulated Broker (Sandbox)", "TradingView Paper Trading (Live Agent)"],
    index=0,
    help="Select whether to route orders to the real-time simulator or TradingView Paper Trading browser agent.",
)
tv_username = st.sidebar.text_input(
    "TradingView Username",
    value=os.getenv("TRADINGVIEW_USERNAME", ""),
    help="Username or email for TradingView automation.",
)
tv_password = st.sidebar.text_input(
    "TradingView Password",
    value=os.getenv("TRADINGVIEW_PASSWORD", ""),
    type="password",
    help="Password for TradingView automation.",
)
tv_headless = st.sidebar.checkbox(
    "Run Browser in Background (Headless)",
    value=False,
    help="Uncheck to display the live Chromium browser window during TradingView order placement.",
)

# Session State Registries
if "active_orders" not in st.session_state:
    st.session_state["active_orders"] = {}
if "completed_reports" not in st.session_state:
    st.session_state["completed_reports"] = []
if "knowledge_graphs" not in st.session_state:
    st.session_state["knowledge_graphs"] = []
if "sim_client" not in st.session_state:
    st.session_state["sim_client"] = SimulatedExecutionClient()
if "analysis_data" not in st.session_state:
    st.session_state["analysis_data"] = None
if "order_alert" not in st.session_state:
    st.session_state["order_alert"] = None

# Custom styling for centered title, modern card containers, and asymmetric playbooks
st.markdown(
    """
    <style>
    .centered-title {
        text-align: center;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-weight: 700;
        font-size: 2.6rem;
        margin-top: 0.5rem;
        margin-bottom: 1.5rem;
        color: #1E293B;
    }
    @media (prefers-color-scheme: dark) {
        .centered-title {
            color: #F8FAFC;
        }
    }
    .analyzer-container {
        border-radius: 12px;
        border: 1px solid rgba(148, 163, 184, 0.25);
        padding: 1.5rem;
        background-color: rgba(248, 250, 252, 0.5);
        margin-top: 1rem;
        margin-bottom: 2rem;
    }
    .playbook-card {
        border-radius: 10px;
        border: 1px solid rgba(148, 163, 184, 0.3);
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.95), rgba(241, 245, 249, 0.9));
        padding: 1.25rem;
        margin-bottom: 1.25rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }
    @media (prefers-color-scheme: dark) {
        .playbook-card {
            background: linear-gradient(135deg, rgba(30, 41, 59, 0.85), rgba(15, 23, 42, 0.85));
            border-color: rgba(255, 255, 255, 0.1);
        }
    }
    .badge-long {
        display: inline-block;
        background-color: #10B981;
        color: #FFFFFF;
        font-weight: 700;
        padding: 0.2rem 0.6rem;
        border-radius: 6px;
        font-size: 0.85rem;
    }
    .badge-short {
        display: inline-block;
        background-color: #EF4444;
        color: #FFFFFF;
        font-weight: 700;
        padding: 0.2rem 0.6rem;
        border-radius: 6px;
        font-size: 0.85rem;
    }
    .metric-pill {
        display: inline-block;
        background-color: rgba(59, 130, 246, 0.1);
        color: #2563EB;
        font-weight: 600;
        padding: 0.2rem 0.5rem;
        border-radius: 4px;
        font-size: 0.85rem;
        margin-right: 0.5rem;
    }
    .stage-card {
        border-radius: 8px;
        border: 1px dashed rgba(59, 130, 246, 0.4);
        padding: 0.75rem;
        background-color: rgba(239, 246, 255, 0.4);
        margin-top: 0.5rem;
    }
    @media (prefers-color-scheme: dark) {
        .metric-pill {
            background-color: rgba(59, 130, 246, 0.2);
            color: #93C5FD;
        }
        .stage-card {
            background-color: rgba(30, 58, 138, 0.15);
            border-color: rgba(96, 165, 250, 0.3);
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Top - Centered title as requested
st.markdown('<h1 class="centered-title">Market Analyzer</h1>', unsafe_allow_html=True)

# Load profile and symbols
config = load_app_config()
profile = load_market_profile("FOCUSED_SYMBOLS")
symbol_options = ["All Focused Symbols (NAS100, US500, XAUUSD, XAGUSD, BTCUSD)"] + [
    f"{inst.symbol} - {inst.name}" for inst in profile.universe
]

# Controls: Symbol dropdown, Forex searchbox, Data provider dropdown, Equity, and Analyze button
col_select, col_search, col_provider, col_equity, col_btn = st.columns([2.4, 2.2, 2.2, 1.6, 1.2])

with col_select:
    selected_option = st.selectbox(
        "Predefined Symbols",
        options=symbol_options,
        index=0,
        help="Select a predefined focused symbol or the entire multi-asset universe.",
    )

with col_search:
    search_symbol = st.text_input(
        "Search Symbol",
        value="",
        placeholder="e.g. EUR/USD, BTC/USD, ETH/USD",
        help="Input any desired Forex currency pair (e.g. EUR/USD, GBP/USD, USD/JPY) or Crypto pair (e.g. BTC/USD, ETH/USD, SOL/USD, BTCUSDT).",
    )

with col_provider:
    provider_choice = st.selectbox(
        "Data Feed Provider",
        options=[
            "Biquote (Market Feed)",
        ],
        index=0,
        help="Default real-time multi-asset market data feed powered by Biquote API.",
    )

with col_equity:
    equity = st.number_input(
        "Portfolio Equity ($)",
        min_value=1000.0,
        max_value=100_000_000.0,
        value=100_000.0,
        step=5000.0,
    )

with col_btn:
    st.write("")
    st.write("")
    analyze_clicked = st.button("Analyze", type="primary", width="stretch")

if analyze_clicked:
    # Determine symbol scope: custom forex or crypto search takes precedence if provided
    raw_search = search_symbol.strip() if search_symbol else ""
    if raw_search:
        is_valid, asset_class, provider_sym, clean_sym, err_msg = parse_custom_symbol(raw_search)
        if not is_valid or asset_class is None:
            st.error(
                f"**Invalid Symbol Error:** {err_msg}\n\n"
                "The searchbox supports **Forex pairs** (e.g. `EUR/USD`, `GBP/USD`, `USD/JPY`) "
                "and **Crypto pairs** (e.g. `BTC/USD`, `ETH/USD`, `SOL/USD`, `BTCUSDT`). "
                "For indices and commodities, select from the predefined symbols dropdown."
            )
            st.stop()

        custom_inst = create_custom_instrument(raw_search)
        if not custom_inst:
            st.error(f"Failed to create instrument for symbol '{raw_search}'.")
            st.stop()

        run_profile = profile.model_copy(update={"universe": [custom_inst]})
        asset_title = "Crypto" if asset_class == AssetClass.CRYPTO else "Forex"
        active_label = f"{asset_title}: {provider_sym}"
    else:
        # Determine symbol scope from dropdown
        if selected_option.startswith("All"):
            run_profile = profile
            active_label = "All Focused Symbols"
        else:
            chosen_symbol = selected_option.split(" - ")[0].strip()
            matched = [i for i in profile.universe if i.symbol == chosen_symbol]
            run_profile = profile.model_copy(update={"universe": matched})
            active_label = selected_option

    with st.spinner(f"Executing Market Analyzer, AI Risk Engine, & Strategy Planner for {active_label}..."):
        try:
            # 1. Market Analyzer
            provider_mode = "biquote"

            provider_inst = build_provider(config, provider_override=provider_mode)
            analyzer = MarketAnalyzer(config=config, provider=provider_inst)
            analysis = asyncio.run(analyzer.run(run_profile, limit=5))

            # 2. Risk Engine
            risk_engine = RiskEngine(config=config)
            assessment = asyncio.run(
                risk_engine.assess(
                    analysis=analysis,
                    risk_profile_id="CONSERVATIVE",
                    portfolio_equity=float(equity),
                    open_positions={},
                )
            )

            # 3. Strategy Planner Agent
            strategy_planner = StrategyPlanner(config=config)
            plan = asyncio.run(
                strategy_planner.plan(
                    analysis=analysis,
                    assessment=assessment,
                    portfolio_equity=float(equity),
                )
            )
            st.session_state["analysis_data"] = {
                "analysis": analysis,
                "assessment": assessment,
                "plan": plan,
                "active_label": active_label,
            }
            st.session_state["order_alert"] = None
        except Exception as exc:
            st.error(f"Analysis failed: {exc}")
            st.session_state["analysis_data"] = None


# Render order execution alerts if present
if st.session_state.get("order_alert"):
    alert = st.session_state["order_alert"]
    if alert.get("type") == "success":
        st.success(alert.get("message", ""))
    else:
        st.error(alert.get("message", ""))

if st.session_state.get("analysis_data"):
    analysis = st.session_state["analysis_data"]["analysis"]
    assessment = st.session_state["analysis_data"]["assessment"]
    plan = st.session_state["analysis_data"]["plan"]
    active_label = st.session_state["analysis_data"].get("active_label", "")
    # Div container enclosing output of Market Analyzer, Risk Analyzer, and Strategy Planner
    with st.container():
        st.markdown('<div class="analyzer-container">', unsafe_allow_html=True)

        # === SECTION 1: MARKET ANALYZER OUTPUT ===
        st.subheader("📊 Market Analyzer")

        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        m_col1.metric("Provider", f"{analysis.provider} (Real-time)")
        m_col2.metric("Regime", analysis.regime.value.upper())
        m_col3.metric("Candidates Detected", len(analysis.candidates))
        dq_str = (
            f"OK: {analysis.data_quality.instruments_ok} / "
            f"Stale: {analysis.data_quality.instruments_stale}"
        )
        m_col4.metric("Data Quality", dq_str)

        # AI Market Overview
        if analysis.summary:
            st.info(f"**AI Market Synthesis:**\n\n{analysis.summary}")

        # Candidate Setups Table
        if analysis.candidates:
            st.markdown("##### Detected Setups")
            cand_data = []
            for c in analysis.candidates:
                cand_data.append(
                    {
                        "Symbol": c.symbol,
                        "Side": c.side.value.upper(),
                        "Setup": c.setup.value,
                        "Score": round(c.score, 1),
                        "Last Price": f"${c.last_price:,.2f}",
                        "Confidence": f"{c.confidence:.0%}",
                        "RSI": round(c.metrics.get("rsi_14", 0.0), 1)
                        if "rsi_14" in c.metrics
                        else "-",
                        "ATR": round(c.metrics.get("atr_14", 0.0), 2)
                        if "atr_14" in c.metrics
                        else "-",
                    }
                )
            st.dataframe(cand_data, width="stretch")
        else:
            st.write("No actionable technical setups detected for current parameters.")

        st.divider()

        # === SECTION 2: RISK ANALYZER OUTPUT ===
        st.subheader("🛡️ Risk Analyzer (AI-Driven Assessment & Sizing)")

        r_col1, r_col2, r_col3 = st.columns(3)
        r_col1.metric("Portfolio Heat", f"{assessment.portfolio_heat_pct:.2%}", "Limit: 6.0%")
        r_col2.metric("Regime Multiplier", f"{assessment.regime_adjustment:.2f}")
        tot_str = (
            f"Appr: {len(assessment.approved)} | "
            f"Red: {len(assessment.reduced)} | "
            f"Def: {len(assessment.deferred)} | "
            f"Rej: {len(assessment.rejected)}"
        )
        r_col3.metric("Decisions", tot_str)

        # Position Sizing & Actions Table
        all_positions = (
            assessment.approved
            + assessment.reduced
            + assessment.deferred
            + assessment.rejected
        )
        if all_positions:
            st.markdown("##### Position Sizing & Decision Rationale")
            decisions_display = []
            for p in all_positions:
                p_rat = p.rationale[0] if p.rationale else "No rationale provided"
                decisions_display.append(
                    {
                        "Symbol": p.symbol,
                        "Action": p.action.value.upper(),
                        "Allocated Equity": f"{p.size_pct_equity:.2%}",
                        "Units": round(p.size_units, 4) if p.size_units else 0,
                        "Stop Loss": f"${p.stop_loss:,.2f}" if p.stop_loss else "-",
                        "Take Profit": f"${p.take_profit:,.2f}" if p.take_profit else "-",
                        "Risk % Equity": f"{p.risk_pct_equity:.2%}",
                        "Primary Rationale": p_rat,
                    }
                )
            st.dataframe(decisions_display, width="stretch")

        # Correlation & Tail Risk Warnings
        if assessment.correlation_warnings:
            st.warning(
                "**Correlation Warnings:**\n"
                + "\n".join(f"- {w}" for w in assessment.correlation_warnings)
            )

        # AI Risk Narrative
        if assessment.ai_narrative:
            with st.expander("AI Risk Officer Commentary & Tail Risks", expanded=True):
                st.write(
                    f"**Regime Analysis:** {assessment.ai_narrative.regime_interpretation}"
                )
                if assessment.ai_narrative.tail_risks:
                    st.write("**Identified Tail Risks:**")
                    for tr in assessment.ai_narrative.tail_risks:
                        st.write(f"- {tr}")
                if assessment.ai_narrative.candidate_commentary:
                    st.write("**Candidate Specific Commentary:**")
                    for sym, comm in assessment.ai_narrative.candidate_commentary.items():
                        st.write(f"- **{sym}**: {comm}")

        st.divider()

        # === SECTION 3: STRATEGY PLANNER (ASYMMETRIC EXECUTION PLAYBOOKS) ===
        st.subheader("🎯 Strategy Planner (Asymmetric Execution Playbooks)")
        st.caption("AI-driven execution playbooks with asymmetric reward-to-risk (minimum 2.5:1), pullback limit entries, and instant Breakeven de-risking.")

        s_col1, s_col2, s_col3, s_col4 = st.columns(4)
        s_col1.metric("Blended R:R Ratio", f"{plan.blended_rr_ratio:.2f} : 1")
        s_col2.metric("Total Max Risk", f"${plan.total_risk_usd:,.2f}")
        s_col3.metric("Projected Profit", f"${plan.total_target_profit_usd:,.2f}")
        s_col4.metric("Strategy Bias", plan.overall_market_bias)

        if plan.playbooks:
            st.markdown("##### Tactical Trade Playbooks")

            for pb in plan.playbooks:
                badge_class = "badge-long" if pb.action == "LONG" else "badge-short"
                with st.container():
                    st.markdown(
                        f"""
                        <div class="playbook-card">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                                <div>
                                    <span class="{badge_class}">{pb.action}</span>
                                    <strong style="font-size: 1.2rem; margin-left: 0.5rem;">{pb.symbol}</strong>
                                    <span style="color: #64748B; margin-left: 0.5rem;">({pb.tactic.value.replace('_', ' ').title()})</span>
                                </div>
                                <div>
                                    <span class="metric-pill">Order: {pb.order_type.value.upper()}</span>
                                    <span class="metric-pill">Target R:R: {pb.risk_reward_ratio:.1f} : 1</span>
                                </div>
                            </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    # Execution Parameters Row
                    pb_c1, pb_c2, pb_c3, pb_c4 = st.columns(4)
                    pb_c1.metric("Limit Entry", f"${pb.entry_price:,.2f}")
                    pb_c2.metric("Stop Loss", f"${pb.stop_loss:,.2f}")
                    pb_c3.metric("Breakeven Trigger", f"${pb.breakeven_trigger:,.2f}")
                    pb_c4.metric("Risk / Upside", f"-${pb.max_loss_usd:,.0f} / +${pb.projected_profit_usd:,.0f}")

                    # 3-Stage Profit Scaling Roadmap
                    st.markdown("**Three-Tier Profit Roadmap & De-risking:**")
                    stage_cols = st.columns(len(pb.exit_stages))
                    for idx, stage in enumerate(pb.exit_stages):
                        with stage_cols[idx]:
                            trail_info = f"<br><small style='color: #2563EB;'>{stage.trail_rule}</small>" if stage.trail_rule else ""
                            st.markdown(
                                f"""
                                <div class="stage-card">
                                    <strong>{stage.label}</strong><br>
                                    <span style="font-size: 1.1rem; font-weight: 700;">${stage.target_price:,.2f}</span>
                                    <span style="color: #10B981; font-weight: 600;"> (+{stage.target_r_multiple:.1f}R)</span>
                                    {trail_info}
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )

                    # Invalidation & Execution Notes
                    exp_cols = st.columns(2)
                    with exp_cols[0]:
                        if pb.invalidation_conditions:
                            with st.expander("⚠️ Invalidation Conditions (Cancel Order If)", expanded=False):
                                for inv in pb.invalidation_conditions:
                                    st.write(f"- {inv}")
                    with exp_cols[1]:
                        if pb.execution_notes:
                            with st.expander("📝 Execution & Order Routing Notes", expanded=False):
                                for note in pb.execution_notes:
                                    st.write(f"- {note}")

                    # Execution Trigger to TradingView / Simulator
                    st.write("")
                    exec_target = "TradingView" if "TradingView" in broker_mode else "Sandbox Simulator"
                    if st.button(
                        f"🚀 Execute {pb.action} {pb.symbol} on {exec_target}",
                        key=f"btn_exec_{pb.symbol}_{idx}",
                        type="primary",
                    ):
                        with st.spinner(f"Connecting to {exec_target} and routing order for {pb.symbol}..."):
                            order_id = f"ord-{pb.symbol.lower().replace('/', '')}-{uuid.uuid4().hex[:6]}"
                            risk_dist = abs(pb.entry_price - pb.stop_loss) if abs(pb.entry_price - pb.stop_loss) > 0 else 1.0
                            calc_qty = max(1.0, round(pb.max_loss_usd / risk_dist, 2))

                            order_req = OrderRequest(
                                order_id=order_id,
                                symbol=pb.symbol,
                                action=pb.action,
                                order_type=pb.order_type.value,
                                quantity=calc_qty,
                                entry_price=pb.entry_price,
                                stop_loss=pb.stop_loss,
                                breakeven_trigger=pb.breakeven_trigger,
                                take_profit_1=pb.exit_stages[0].target_price if pb.exit_stages else pb.entry_price * 1.02,
                                take_profit_2=pb.exit_stages[1].target_price if len(pb.exit_stages) > 1 else None,
                            )

                            if "TradingView" in broker_mode:
                                exec_client = TradingViewClient(
                                    username=tv_username,
                                    password=tv_password,
                                    headless=tv_headless,
                                )
                            else:
                                exec_client = st.session_state["sim_client"]

                            res = asyncio.run(exec_client.place_order(order_req))

                            if res.status == OrderStatus.REJECTED:
                                st.session_state["order_alert"] = {
                                    "type": "error",
                                    "message": f"❌ {exec_target} Order Rejected: {res.message}",
                                }
                            else:
                                st.session_state["active_orders"][order_id] = {
                                    "request": order_req,
                                    "playbook": pb,
                                    "regime": analysis.regime.value,
                                    "broker": exec_client.name,
                                    "status": res.status.value,
                                    "fill_price": res.fill_price or pb.entry_price,
                                    "current_price": pb.entry_price,
                                    "current_stop_loss": pb.stop_loss,
                                    "breakeven_activated": False,
                                    "broker_order_id": res.broker_order_id,
                                    "created_at": order_req.created_at,
                                }
                                st.session_state["order_alert"] = {
                                    "type": "success",
                                    "message": (
                                        f"✅ Order `{order_id}` routed to **{exec_client.name.upper()}**! "
                                        f"{order_req.action} {order_req.quantity} {order_req.symbol} @ ${order_req.entry_price:,.2f} | "
                                        f"Stop Loss: ${order_req.stop_loss:,.2f} | TP1: ${order_req.take_profit_1:,.2f}"
                                    ),
                                }
                        st.rerun()

                    st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("No active playbooks generated. Capital preservation rules active.")
            if plan.contingency_plans:
                st.write("**Contingency Guidelines:**")
                for cont in plan.contingency_plans:
                    st.write(f"- {cont}")

        st.markdown("</div>", unsafe_allow_html=True)

        # API Performance & Latency Telemetry
        telemetry = get_telemetry_summary()
        td_tel = telemetry.get("twelvedata", {})
        fh_tel = telemetry.get("finnhub", {})
        ai_tel = telemetry.get("openrouter_ai", {})

        with st.expander("⚡ API Latency & Real-Time Performance", expanded=True):
            tel_c1, tel_c2, tel_c3 = st.columns(3)
            with tel_c1:
                st.markdown("#### TwelveData API")
                st.metric("Avg Response Time", f"{td_tel.get('average_duration_seconds', 0.0):.2f}s", f"Last: {td_tel.get('last_duration_seconds', 0.0):.2f}s")
                st.caption(f"Requests: {td_tel.get('successful_requests', 0)} success / {td_tel.get('failed_requests', 0)} errors")
            with tel_c2:
                st.markdown("#### Finnhub API")
                st.metric("Avg Response Time", f"{fh_tel.get('average_duration_seconds', 0.0):.2f}s", f"Last: {fh_tel.get('last_duration_seconds', 0.0):.2f}s")
                st.caption(f"Requests: {fh_tel.get('successful_requests', 0)} success / {fh_tel.get('failed_requests', 0)} errors")
            with tel_c3:
                st.markdown("#### OpenRouter AI")
                st.metric("Avg Response Time", f"{ai_tel.get('average_duration_seconds', 0.0):.2f}s", f"Last: {ai_tel.get('last_duration_seconds', 0.0):.2f}s")
                st.caption(f"Requests: {ai_tel.get('successful_requests', 0)} success / {ai_tel.get('failed_requests', 0)} errors")

    # === SECTION 4: ACTIVE ORDERS & REAL-TIME TRADE MONITOR ===
    st.markdown('<div class="analyzer-container">', unsafe_allow_html=True)
    st.subheader("🎯 Active Orders & Trade Lifecycle Monitor")

    active_orders = st.session_state.get("active_orders", {})
    if not active_orders:
        st.info("No active positions currently tracked. Execute an order playbook above to start monitoring and de-risking.")
    else:
        for ord_id, ord_info in list(active_orders.items()):
            req: OrderRequest = ord_info["request"]
            pb = ord_info["playbook"]
            regime = ord_info["regime"]
            broker_name = ord_info.get("broker", "simulator").upper()

            action_badge = "badge-long" if req.action == "LONG" else "badge-short"
            be_status = (
                '<span class="badge-long">🛡️ Breakeven Active ($0 Risk)</span>'
                if ord_info.get("breakeven_activated")
                else f'<span style="background-color: #F59E0B; color: white; padding: 3px 8px; border-radius: 6px; font-weight: 600; font-size: 0.85rem;">⏳ Pending BE Shift at ${req.take_profit_1:,.2f}</span>'
            )

            st.markdown(
                f"""
                <div class="playbook-card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                        <div>
                            <span class="{action_badge}">{req.action}</span>
                            <strong style="font-size: 1.2rem; margin-left: 0.5rem;">{req.symbol}</strong>
                            <span style="color: #64748B; margin-left: 0.5rem;">[{ord_id}] via {broker_name}</span>
                        </div>
                        <div>
                            {be_status}
                        </div>
                    </div>
                """,
                unsafe_allow_html=True,
            )

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Entry Price", f"${req.entry_price:,.2f}")
            current_sl = ord_info.get("current_stop_loss", req.stop_loss)
            m2.metric("Stop Loss", f"${current_sl:,.2f}", "Breakeven" if ord_info.get("breakeven_activated") else None)
            m3.metric("Target TP1", f"${req.take_profit_1:,.2f}")
            tp2_str = f"${req.take_profit_2:,.2f}" if req.take_profit_2 else "-"
            m4.metric("Target TP2", tp2_str)

            # Monitor Action Controls
            ctl1, ctl2, ctl3 = st.columns(3)
            with ctl1:
                if st.button("📈 Check Live Price Tick", key=f"tick_{ord_id}", use_container_width=True):
                    # Fetch latest price
                    try:
                        prov = build_provider(config)
                        quote = asyncio.run(prov.get_quote(req.symbol))
                        curr_px = quote.last
                    except Exception:
                        curr_px = req.entry_price

                    monitor = TradeMonitor(client=st.session_state["sim_client"])
                    monitor.track_order(req)
                    report = monitor.process_price_update(ord_id, curr_px)
                    ord_info["current_price"] = curr_px
                    if monitor.get_order_state(ord_id).get("breakeven_activated"):
                        ord_info["breakeven_activated"] = True
                        ord_info["current_stop_loss"] = req.entry_price
                        st.toast(f"🎯 Breakeven Active! Stop loss moved to ${req.entry_price:,.2f}")
                    st.rerun()

            with ctl2:
                if st.button("🎯 Simulate TP1 Hit (+Breakeven)", key=f"sim_tp1_{ord_id}", use_container_width=True):
                    # Trigger TP1 level
                    tp1_price = req.take_profit_1
                    monitor = TradeMonitor(client=st.session_state["sim_client"])
                    monitor.track_order(req)
                    monitor.process_price_update(ord_id, tp1_price)
                    ord_info["breakeven_activated"] = True
                    ord_info["current_stop_loss"] = req.entry_price
                    ord_info["current_price"] = tp1_price
                    st.toast(f"🎯 TP1 Reached! Stop Loss shifted to Breakeven at ${req.entry_price:,.2f} ($0 Risk)!")
                    st.rerun()

            with ctl3:
                if st.button("🏁 Simulate Target Close & Knowledge Graph", key=f"sim_close_{ord_id}", use_container_width=True):
                    tp_final = req.take_profit_2 or (req.take_profit_1 * 1.01)
                    monitor = TradeMonitor(client=st.session_state["sim_client"])
                    monitor.track_order(req)
                    if ord_info.get("breakeven_activated"):
                        monitor._active_orders[ord_id]["breakeven_activated"] = True
                    report = monitor.process_price_update(ord_id, tp_final)
                    if report:
                        st.session_state["completed_reports"].append(report)
                        # Generate AI Knowledge Graph
                        ai_analyst = build_ai_analyst(enabled=config.ai.enabled)
                        kg_builder = TradeKnowledgeGraphBuilder(ai=ai_analyst)
                        kg_snapshot = asyncio.run(kg_builder.build_and_save(report, pb, regime))
                        st.session_state["knowledge_graphs"].append(kg_snapshot)
                        del active_orders[ord_id]
                        st.toast(f"🏆 Trade closed in profit (+${report.realized_pnl_usd:,.2f})! Knowledge Graph generated.")
                        st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # === SECTION 5: POST-TRADE KNOWLEDGE GRAPH EXPLORER ===
    kg_list = st.session_state.get("knowledge_graphs", [])
    if kg_list:
        st.markdown('<div class="analyzer-container">', unsafe_allow_html=True)
        st.subheader("🧠 Post-Trade Knowledge Graph & Strategy Learning")

        for idx, kg in enumerate(reversed(kg_list)):
            with st.expander(f"📊 Knowledge Graph: {kg.symbol} Trade ({kg.trade_id})", expanded=(idx == 0)):
                st.markdown(f"**Executive Post-Mortem Summary:**\n\n{kg.executive_summary}")

                # Performance Metrics Row
                pm = kg.performance_metrics
                p1, p2, p3, p4 = st.columns(4)
                p1.metric("Realized P&L", f"${pm.get('realized_pnl_usd', 0.0):+,.2f}")
                p2.metric("Realized R", f"{pm.get('realized_r_multiple', 0.0):+.2f}R")
                p3.metric("Duration", f"{pm.get('duration_minutes', 0.0):.1f} min")
                p4.metric("Breakeven Protected", "Yes (0% Risk)" if pm.get("breakeven_activated") else "No")

                # Knowledge Lessons Learned
                if kg.lessons_learned:
                    st.markdown("##### 💡 Synthesized Behavioral Lessons:")
                    for lsn in kg.lessons_learned:
                        st.markdown(f"- **{lsn}**")

                # Semantic Graph Representation (Nodes & Relationships)
                st.markdown("##### 🕸️ Semantic Graph Nodes & Edges:")
                node_cols = st.columns(len(kg.nodes))
                for n_idx, node in enumerate(kg.nodes):
                    with node_cols[n_idx % len(node_cols)]:
                        st.markdown(
                            f"""
                            <div style="border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 8px; padding: 0.5rem; text-align: center; background: rgba(59, 130, 246, 0.05); margin-bottom: 0.5rem;">
                                <small style="color: #64748B; font-weight: 700;">{node.type.value.upper()}</small><br>
                                <strong>{node.label}</strong>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                # Raw Graph JSON
                with st.expander("🔍 View Raw Knowledge Graph JSON", expanded=False):
                    st.json(kg.model_dump(mode="json"))

        st.markdown("</div>", unsafe_allow_html=True)
