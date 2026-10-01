# Trading System

Component 1 of an AI trading orchestrator: **read-only market analysis**, plus the
**web research** service it depends on.

Both ship as MCP servers from a single package and a single virtual environment.

| Package | What it is | Entry point |
|---|---|---|
| `market_analyzer` | Analysis pipeline, exposed as an MCP server (8 tools) + CLI | `market-analyzer` |
| `web_search_mcp` | Allowlist-gated web search/fetch, exposed as an MCP server (2 tools) | `web-search-mcp` |

**This component never authenticates and never places orders.** It produces a
`MarketAnalysis` artefact for a downstream Risk Analyzer and Risk Governor.

## Layout

```
.
├── pyproject.toml            # one package, both servers
├── .mcp.json                 # client config for both MCP servers
├── .env.example              # copy to .env; every value is optional
├── config/
│   ├── app.yaml              # runtime settings for the analyzer
│   └── markets/              # one YAML file per market profile
├── knowledge/
│   └── core/
│       ├── approved_lessons/ # curated, version-controlled knowledge
│       └── data_sources/     # trusted source tiers = the web allowlist
├── docs/
│   ├── ENVIRONMENT.md        # every env var, with the .env.example body
│   └── REAL_TIME.md          # how to wire a genuine real-time feed
├── src/
│   ├── market_analyzer/      # models, providers, pipeline, knowledge, mcp
│   └── web_search_mcp/       # config, search, server
└── tests/                    # hermetic; no network
```

Generated at runtime and git-ignored: `runs/`, `logs/`, `data/cache/`,
`knowledge/cases/`.

## Install

```bash
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -e ".[dev]"
```

## Use

```bash
market-analyzer doctor        # config, provider, knowledge wiring
market-analyzer profiles      # available market profiles
market-analyzer universe      # instruments in a profile
market-analyzer run --limit 5 # analysis, ranked candidates
market-analyzer run --as-json
```

`run` will currently **fail closed** — see "Data providers" below.

### MCP servers

Both run over stdio. `.mcp.json` at the repo root is a ready-to-use client
config, but it points at an **absolute interpreter path** — update
`.venv/Scripts/python.exe` if you move the project or are on macOS/Linux
(`.venv/bin/python`).

```bash
python -m market_analyzer.mcp.server   # 8 tools
python -m web_search_mcp               # 2 tools, stdio; takes no CLI args
```

| `market_analyzer` tool | Purpose |
|---|---|
| `resolve_market_profile` | List profiles or inspect one |
| `get_market_universe` | Instruments in a profile |
| `run_market_analysis` | Full analysis, ranked candidates |
| `get_analysis_result` | Fetch a saved snapshot by run id |
| `list_analysis_runs` | Recent run ids |
| `query_approved_knowledge` | Curated knowledge for a market/symbol |
| `query_operational_logs` | Recent structured events |
| `get_provider_capabilities` | Is the data real-time or delayed? |

| `web_search_mcp` tool | Purpose |
|---|---|
| `web_search(query, limit, freshness_hours, source_tiers)` | DuckDuckGo search, allowlist-filtered |
| `fetch_page(url, max_chars)` | Fetch + extract readable text |

## What the analyzer does

1. Loads a market profile (currently `INDIA_CASH_EQUITIES` on NSE)
2. Fetches candles for the universe through a pluggable provider
3. Validates freshness and sanity — fail-closed
4. Computes indicators (SMA/EMA/MACD/RSI/ATR/volatility/volume)
5. Detects candidate setups deterministically
6. Ranks candidates with weights loaded from YAML
7. Classifies the market regime from the benchmark index
8. Saves a JSON snapshot, appends a JSONL case, returns the result

If nothing qualifies, it returns `NO_TRADE` rather than lowering thresholds.

## Configuration

`config/app.yaml` holds runtime settings. `config/markets/*.yaml` holds each
profile's universe, benchmark and scoring weights. Change either without code
edits.

Everything is overridable from the environment — see
[`docs/ENVIRONMENT.md`](docs/ENVIRONMENT.md) for the full list. Nothing is
required: the project runs with no `.env` at all.

## Data providers

- `yahoo` — `yfinance`. **Unofficial and delayed.** The only provider that works
  today.
- `realtime` — reserved slot for a broker/exchange adapter. See
  [`docs/REAL_TIME.md`](docs/REAL_TIME.md).

**There is no synthetic/mock provider.** A fabricated price reachable from config
would be worse than a missing one, so none ships in production code. Tests
define their provider inside `tests/`, which is never importable by `src/`.

Every analysis output carries `data_realtime`, and `data.require_realtime`
defaults to `true`, so the delayed `yahoo` feed **fails the run** rather than
being labelled real-time. Check `market-analyzer doctor` before treating any
candidate as tradeable.

## Web research safety

The analyzer needs qualitative context but must not have open internet access.
`web_search_mcp` therefore:

- requires no API key
- enforces a domain allowlist on both search and fetch
- blocks private/loopback hosts (SSRF guard, fails closed on DNS failure)
- skips login-walled content
- treats all fetched text as **untrusted data**, never instructions

The allowlist lives in version-controlled YAML
(`knowledge/core/data_sources/trusted_sources.yaml`), not in an env var, so it
is reviewable. `web_search_mcp` reads that file — there is no second, hardcoded
copy of the domain list in Python.

Web content may inform a **downgrade**; it can never authorise a trade.

## File formats

| Data | Format | Why |
|---|---|---|
| Config, profiles, approved knowledge | YAML | Human-editable, comments |
| Analysis snapshots | JSON | Machine-consumed, diffable |
| Cases, operational events | JSONL | Append-only, streamable |

YAML is always loaded with `yaml.safe_load`.

## Tests

```bash
pytest -q
```

Hermetic: the fake provider is defined inside `tests/`, so the suite never
touches the network. The one exception is `tests/test_research_bridge.py`, which
spawns the real search MCP subprocess to verify the stdio handshake but performs
no live search.

## Scope boundary

This is research tooling, not financial advice. It produces candidate setups for
a downstream risk layer to approve or reject; it does not decide to trade, and
it cannot promise profitable results.
