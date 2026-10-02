# Environment variables

All configuration is optional. Every variable has a working default, so the
project runs with **no `.env` at all**. `.env` exists to override defaults per
machine without editing tracked files.

## How values are resolved

For both packages the precedence is:

```
real environment variable  >  .env at the project root  >  config/app.yaml or model default
```

- `.env` is loaded automatically from the repository root on import.
- Real environment variables always win, so CI and containers are unaffected by
  a developer's `.env`. Set `PYTHON_DONT_WRITEBYTECODE`-style isolation yourself
  if you need `.env` ignored entirely.
- `MARKET_ANALYZER_CONFIG` and `MARKET_ANALYZER_MARKETS_DIR` relocate config
  files; relative paths resolve against the project root.

## `.env.example`

Copy to `.env` at the project root. `.env` is git-ignored; `.env.example` is not.

```bash
# ---------------------------------------------------------------------------
# market_analyzer — runtime overrides for config/app.yaml
# ---------------------------------------------------------------------------

# Which data provider to use. twelvedata | yahoo | realtime
#   twelvedata = Twelve Data API. Real-time multi-asset (equities, indices via
#                ETF proxies, forex, metals, crypto). Needs TWELVEDATA_API_KEY.
#   yahoo      = yfinance. Unofficial and DELAYED. Fails require_realtime=true.
#   realtime   = requires an adapter in providers/realtime.py; not built yet.
MARKET_ANALYZER_PROVIDER=twelvedata

# Refuse to analyse anything the provider cannot prove is real-time.
# Leave TRUE for anything that might inform a trade. Set false ONLY for
# historical/backtest research. Truthy: 1/true/yes/on
MARKET_ANALYZER_REQUIRE_REALTIME=true

# A bar older than this is treated as stale and fails validation (seconds).
# Must be >= 30. Keep this well below the provider's actual delivery delay.
MARKET_ANALYZER_STALE_AFTER_SECONDS=900

# Minimum delay between provider requests (seconds, float >= 0).
MARKET_ANALYZER_THROTTLE_SECONDS=0.5

# Default market profile when none is passed on the CLI or in an MCP call.
# Must match a file in config/markets/<id lowercased>.yaml
#   FOCUSED_SYMBOLS | INDIA_CASH_EQUITIES | US_CASH_EQUITIES
MARKET_ANALYZER_PROFILE=FOCUSED_SYMBOLS

# Optional path overrides. Relative paths resolve against the project root.
# MARKET_ANALYZER_CONFIG=config/app.yaml
# MARKET_ANALYZER_MARKETS_DIR=config/markets

# Web research bridge (the analyzer -> web_search_mcp stdio client).
# Off by default: market analysis must not depend on web availability.
MARKET_ANALYZER_WEB_RESEARCH_ENABLED=false
# Interpreter used to launch the search MCP server. Leave UNSET to use
# sys.executable, which keeps the subprocess in this same virtualenv. Set it
# only if you must pin a specific interpreter.
# MARKET_ANALYZER_WEB_RESEARCH_COMMAND=

# ---------------------------------------------------------------------------
# Twelve Data market data — SECRET
# ---------------------------------------------------------------------------
# DATA ONLY. Sent to api.twelvedata.com. No trading endpoints are called.
# Format: KEY=VALUE, one per line. Unparseable .env is SILENTLY IGNORED.
TWELVEDATA_API_KEY=your_twelvedata_key

# ---------------------------------------------------------------------------
# OpenRouter (advisory AI) — SECRET
# ---------------------------------------------------------------------------
# The model may summarise and classify. It cannot produce prices, scores, or
# trade decisions, and cannot approve its own knowledge proposals. Every
# failure degrades to a neutral result; the run never fails because of it.
OPENROUTER_API_KEY=sk-or-v1-your_key

# Optional. Primary model, tried first; built-in free models remain as
# fallbacks. Free-tier model availability changes without notice.
# OPENROUTER_MODEL=qwen/qwen3-235b-a22b:free
# OPENROUTER_TIMEOUT_SECONDS=30

# Must also be true in config/app.yaml (ai.enabled) to take effect.
MARKET_ANALYZER_AI_ENABLED=false

# ---------------------------------------------------------------------------
# web_search_mcp — settings for the search MCP server
# ---------------------------------------------------------------------------

# DuckDuckGo region bias. us-en for US-focused assets.
WEB_SEARCH_REGION=us-en

# Max results per query.
WEB_SEARCH_MAX_RESULTS=5

# HTTP timeout for page fetches (seconds, float).
WEB_SEARCH_FETCH_TIMEOUT_SECONDS=15.0

# Extracted page text is truncated to this many characters.
WEB_SEARCH_MAX_CHARS_PER_PAGE=4000

# Comma-separated allowlist. Leave EMPTY to use the version-controlled
# knowledge/core/data_sources/trusted_sources.yaml instead. Populating this
# OVERRIDES the YAML allowlist.
# WEB_SEARCH_ALLOWED_DOMAINS=reuters.com,bloomberg.com,cnbc.com

# Leave TRUE. When true, a host outside the allowlist is refused; when the
# allowlist is empty this blocks ALL fetching, which is the correct default.
WEB_SEARCH_ENFORCE_ALLOWLIST=true

# Override the allowlist source file. Absolute, or relative to project root.
# WEB_SEARCH_KNOWLEDGE_SOURCES_FILE=knowledge/core/data_sources/trusted_sources.yaml

# Identify your client honestly. Put a real contact address here before
# deploying anywhere public.
WEB_SEARCH_USER_AGENT=trading-system-research/0.1 (+read-only research client; contact=you@example.com)

# ---------------------------------------------------------------------------
# Deprecated (kept for reference only)
# ---------------------------------------------------------------------------
# Alpaca and DATA_PROVIDER_* variables are no longer used.
# ALPACA_API_KEY=
# ALPACA_SECRET_KEY=
# ALPACA_FEED=
# DATA_PROVIDER_API_KEY=
# DATA_PROVIDER_API_SECRET=
```

## Variable reference

| Variable | Default | Consumed by | Purpose |
|---|---|---|---|
| `MARKET_ANALYZER_PROVIDER` | `twelvedata` | `config.py` | Selects the data provider |
| `MARKET_ANALYZER_REQUIRE_REALTIME` | `true` | `config.py` | Fail closed on delayed data |
| `MARKET_ANALYZER_STALE_AFTER_SECONDS` | `900` | `config.py` | Staleness threshold |
| `MARKET_ANALYZER_THROTTLE_SECONDS` | `0.5` | `config.py` | Request pacing |
| `MARKET_ANALYZER_PROFILE` | `FOCUSED_SYMBOLS` | `config.py` | Default profile id |
| `MARKET_ANALYZER_CONFIG` | `config/app.yaml` | `config.py` | App config location |
| `MARKET_ANALYZER_MARKETS_DIR` | `config/markets` | `config.py` | Profile directory |
| `MARKET_ANALYZER_WEB_RESEARCH_ENABLED` | `false` | `config.py` | Enables the research bridge |
| `MARKET_ANALYZER_WEB_RESEARCH_COMMAND` | *(unset → `sys.executable`)* | `config.py` | Interpreter for the search MCP |
| `MARKET_ANALYZER_AI_ENABLED` | `false` | `config.py` | Enables the advisory AI layer |
| `TWELVEDATA_API_KEY` | *(required for provider `twelvedata`)* | `providers/twelvedata.py` | Twelve Data key — **secret** |
| `OPENROUTER_API_KEY` | *(unset → AI disabled)* | `ai/openrouter.py` | OpenRouter key — **secret** |
| `OPENROUTER_MODEL` | see above | `ai/openrouter.py` | Primary model, fallbacks retained |
| `OPENROUTER_TIMEOUT_SECONDS` | `30` | `ai/openrouter.py` | Model call timeout |
| `WEB_SEARCH_REGION` | `us-en` | `web_search_mcp/config.py` | Search region bias |
| `WEB_SEARCH_MAX_RESULTS` | `5` | `web_search_mcp/config.py` | Result cap per query |
| `WEB_SEARCH_FETCH_TIMEOUT_SECONDS` | `15.0` | `web_search_mcp/config.py` | HTTP timeout |
| `WEB_SEARCH_MAX_CHARS_PER_PAGE` | `4000` | `web_search_mcp/config.py` | Text truncation |
| `WEB_SEARCH_ALLOWED_DOMAINS` | *(empty)* | `web_search_mcp/config.py` | Allowlist override |
| `WEB_SEARCH_ENFORCE_ALLOWLIST` | `true` | `web_search_mcp/config.py` | Allowlist enforcement |
| `WEB_SEARCH_KNOWLEDGE_SOURCES_FILE` | `knowledge/core/data_sources/trusted_sources.yaml` | `web_search_mcp/config.py` | Allowlist source file |
| `WEB_SEARCH_USER_AGENT` | see above | `web_search_mcp/config.py` | HTTP user agent |

## Renamed variables

- `WEB_SEARCH_ENABLED` → `MARKET_ANALYZER_WEB_RESEARCH_ENABLED`. The
  `WEB_SEARCH_` prefix now belongs exclusively to the `web_search_mcp` package,
  so the two packages cannot collide on the same name.
- `ALPACA_*` and `DATA_PROVIDER_*` → `TWELVEDATA_API_KEY`. The old names were
  never read after the Twelve Data migration.

## Secrets

There are two secrets now, and both are optional:

- **Twelve Data** (`TWELVEDATA_API_KEY`) — required for real-time multi-asset
  data. Data-only; no trading endpoints are contacted.
- **OpenRouter** (`OPENROUTER_API_KEY`) — required only for the advisory AI
  layer. Without it the AI degrades to a no-op and nothing else changes.

Supply both **only** through the environment: never in `config/`, never in
`knowledge/`, never in prompts, never in `.env.example`. If you paste a key
into a tracked file by accident, rotate it.

### `.env` format

`python-dotenv` accepts `KEY=VALUE` lines, blank lines, and `#` comments.
Anything else — notes, a `key: value` separator, a pasted markdown fence — is
**silently skipped with only a warning on stderr**, so a malformed `.env`
looks exactly like an empty one. Verify with:

```bash
market-analyzer doctor
```

A provider that reports `UNAVAILABLE` with no obvious cause almost always means
a malformed `.env`, not a bad key.
