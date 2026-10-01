# Market Analyzer -- Project Summary

**Last Updated:** 2026-10-02  
**Component:** Market Analyzer + Web Search MCP + Risk Engine + AI Strategy Planner  
**Environment:** Windows / PowerShell / Python 3.14 / Single Virtualenv (`.venv`) / `D:\Git Repos\Self Sustaining\`

---

## Current Status (Verified 2026-10-02)

- **Test Suite:** 70 passed, 0 failed (100% passing rate across all 10 test suites including `test_forex.py`, `test_strategy.py`, and `test_risk.py`).
- **Version Control:** Standalone directory (Git uninitialized; no commit hash).
- **Runtime Environment:** Windows / Python 3.14 / Unified repository layout (`pyproject.toml` defines `trading-system` packaging `market_analyzer`, `web_search_mcp`, and `strategy`).
- **Network Capabilities:** Outbound network egress is active and functional (TwelveData REST API and OpenRouter LLMs respond with HTTP 200).
- **Data Provider Policy:** `twelvedata` exclusively (`require_realtime: true`). `DataConfig` validator strictly allows `{"twelvedata"}` and requires `TWELVEDATA_API_KEY`.
- **Market Profile & Universe Lockdown:** Defaults to `FOCUSED_SYMBOLS` (`config/markets/focused_symbols.yaml`) targeting 5 multi-asset instruments: NAS100 (QQQ), US500 (SPY), XAUUSD (Gold), XAGUSD (Silver via SLV proxy), BTCUSD (Bitcoin).
- **Forex Market Symbol Search:** Integrated searchbox allowing any custom fiat Forex currency pair (e.g. `EUR/USD`, `GBP/USD`, `USD/JPY`, `AUD/CAD`). Non-forex symbols (equities, crypto) are strictly rejected.
- **AI-Driven Market Analysis:** Embedded in `MarketAnalyzer.run()`. OpenRouter LLMs generate executive cross-asset synthesis, regime analysis, and setup assessments stored in `MarketAnalysis.ai_analysis`.
- **AI-Driven Risk Engine:** `RiskEngine` evaluates candidates using AI models. OpenRouter models calculate position sizing, stop-loss / take-profit levels, portfolio heat, correlation warnings, and trade actions (`APPROVE`, `REDUCE`, `DEFER`, `REJECT`).
- **AI Strategy Planner Agent:** `StrategyPlanner` in `src/market_analyzer/strategy/planner.py` consumes Market Analysis and Risk Assessment artefacts to generate actionable asymmetric execution playbooks:
  - Minimum 2.5:1 Risk-to-Reward ratio (typical 3:1 - 4:1).
  - Confluence pullback limit orders to tighten stop distance and reduce adverse excursions.
  - Multi-stage exits: TP1 (50% scale at 1.5R + Breakeven stop move), TP2 (30% scale at 3.0R), Runner (20% dynamic ATR trailing stop).
  - Deterministic mathematical fallback guarantees 100% system availability even offline or under API outage.
- **Streamlit Web Application (`app.py`):** Interactive web UI with top-centered title "Market Analyzer", predefined focused symbol selector, Forex pair searchbox, equity configuration, and a unified container housing the triad: Market Analyzer, AI Risk Officer, and Strategy Planner Playbook cards.
- **Approved Knowledge Base:** 5 approved records in `knowledge/core/approved_lessons/focused_symbols.yaml` covering cross-asset diversification, precious metals, crypto sessions, and invalidation rules.
- **MCP Server:** 19 tools verified operational via live stdio client handshake.

---

## What Is Built & Verified

### Packaging Structure

| Package / Module | Version | Location | Status |
|------------------|---------|----------|--------|
| `trading-system` (Root) | 0.1.0 | `.` | Single unified pyproject.toml |
| `market_analyzer` | 0.1.0 | `src/market_analyzer` | Core pipeline, providers, risk engine, strategy planner, MCP |
| `web_search_mcp` | 0.1.0 | `src/web_search_mcp` | DuckDuckGo search + Trafilatura scraper MCP server |

### Core Architecture

```
src/
|-- market_analyzer/
|   |-- ai/             # OpenRouter LLM integration (market synthesis, chat)
|   |-- knowledge/      # Knowledge retriever, loader, and writers
|   |-- mcp/            # 19-tool MCP server (market + risk + advisory)
|   |-- models/         # Pydantic v2 schemas (market, risk, analysis, strategy)
|   |-- pipeline/       # Validation -> Indicators -> Candidate detection -> AI analysis
|   |-- providers/      # Twelve Data feed with SLV proxy fallback
|   |-- research/       # Web research bridge to web_search_mcp
|   |-- risk/           # AI-driven risk engine (AI sizing, portfolio heat, rationales)
|   |-- strategy/       # AI strategy planner (asymmetric playbooks, multi-stage exits)
|   |-- storage/        # JSONL event logger and JSON snapshot store
|   |-- cli.py          # Typer CLI (run, doctor, profiles, universe, risk, strategy)
|   \-- config.py       # Pydantic v2 configuration (TwelveData only, FOCUSED_SYMBOLS only)
|-- web_search_mcp/
|   |-- fetch.py        # Web scraping and text extraction with SSRF protection
|   |-- search.py       # DuckDuckGo search integration
|   \-- server.py       # FastMCP / MCPServer endpoint
\-- app.py              # Streamlit interactive application
```

### Data Provider

| Provider | Implementation Class | Real-time | Status |
|----------|----------------------|-----------|--------|
| **TwelveData** | `TwelveDataProvider` | [x] Yes | **Active & Exclusive** (wired in `config/app.yaml`) |
| Yahoo Finance | Retired | [ ] No | Removed per TwelveData-only directive |
| Realtime Stub | Retired | [ ] No | Removed per TwelveData-only directive |
| Mock Provider | DELETED | [ ] No | Removed per design directive |

> **Directive enforced:** Twelve Data is the sole permitted data source. `DataConfig` schema validation fails if any other provider is specified. Universe is strictly constrained to `NAS100`, `US500`, `XAUUSD`, `XAGUSD`, and `BTCUSD`.

### MCP Server (19 Tools) -- Verified via Stdio Handshake

| Category | Count | Tool Identifiers |
|----------|-------|------------------|
| **Market Analysis** | 8 | `resolve_market_profile`, `get_market_universe`, `run_market_analysis`, `get_analysis_result`, `list_analysis_runs`, `query_approved_knowledge`, `query_operational_logs`, `get_provider_capabilities` |
| **Risk Assessment** | 8 | `assess_risk`, `get_risk_assessment`, `list_risk_runs`, `get_risk_profile`, `list_risk_profiles`, `explain_risk_decision`, `simulate_portfolio_heat`, `list_pending_risk_proposals` |
| **Advisory AI** | 3 | `summarize_analysis`, `extract_news_events`, `propose_knowledge_lesson` |

---

## CLI Commands (Verified Working)

```powershell
# Market analysis diagnostics and live runs
.\.venv\Scripts\python.exe -m market_analyzer doctor
.\.venv\Scripts\python.exe -m market_analyzer profiles
.\.venv\Scripts\python.exe -m market_analyzer universe --profile FOCUSED_SYMBOLS
.\.venv\Scripts\python.exe -m market_analyzer run --profile FOCUSED_SYMBOLS --limit 5

# Risk assessment commands (AI-driven evaluation & sizing)
.\.venv\Scripts\python.exe -m market_analyzer risk profiles
.\.venv\Scripts\python.exe -m market_analyzer risk profile --profile CONSERVATIVE
.\.venv\Scripts\python.exe -m market_analyzer risk assess --analysis-run <run_id> --equity 100000
.\.venv\Scripts\python.exe -m market_analyzer risk pending --limit 20

# AI Strategy Planner commands (Asymmetric execution playbooks)
.\.venv\Scripts\python.exe -m market_analyzer strategy plan --analysis-run <run_id> --equity 100000

# Streamlit Web Application
.\.venv\Scripts\streamlit.exe run app.py
```

---

## Key Config & Knowledge Files

| File | Purpose |
|------|---------|
| `config/app.yaml` | Main app config (`provider: twelvedata`, `ai.enabled: true`, caching, logging) |
| `config/markets/focused_symbols.yaml` | 5-symbol multi-asset profile (NAS100, US500, XAUUSD, XAGUSD, BTCUSD) |
| `config/risk/conservative.yaml` | Risk profile parameters (heat limit, max single position size, regime multipliers) |
| `knowledge/core/approved_lessons/focused_symbols.yaml` | 5 approved rules for multi-asset focus universe |
| `knowledge/core/data_sources/trusted_sources.yaml` | Domain tier allowlist for research queries |

---

## Verified State (`doctor` Output)

```text
config file:   D:\Git Repos\Self Sustaining\config\app.yaml
config:        loaded (provider=twelvedata)
profiles:      FOCUSED_SYMBOLS
active:        FOCUSED_SYMBOLS
provider:      twelvedata (realtime=True)
volume gates:  DISABLED (setups needing absolute volume are skipped)
ai layer:      enabled (advisory only)
knowledge:     5 record(s) from D:\Git Repos\Self Sustaining\knowledge\core
```

---

## Test & Verification Commands

```powershell
# Run full test suite (67 tests passing)
.\.venv\Scripts\python.exe -m pytest tests/ -v

# Run code style and lint checks
.\.venv\Scripts\ruff.exe check src tests

# Test MCP server stdio handshake and tool enumeration
.\.venv\Scripts\python.exe -c "
import asyncio
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
async def test():
    params = StdioServerParameters(command=r'.\.venv\Scripts\python.exe', args=['-m', 'market_analyzer.mcp.server'])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(f'Total Tools: {len(tools.tools)}')
asyncio.run(test())
"
```