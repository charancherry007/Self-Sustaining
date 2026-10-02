# Real-time feed integration

## The requirement

You asked for a genuine real-time feed from day one. **yfinance cannot provide
that.** It is an unofficial wrapper around Yahoo Finance endpoints; data may be
delayed by up to roughly 15 minutes depending on the exchange, and it is rate-limited
and prone to breakage.

So the analyzer is architected for real time, but currently runs on delayed data
until you connect a real adapter. Rather than mislabeling delayed data as "real-time",
the system is explicit about the difference:

- `Quote.realtime` / `MarketAnalysis.data_realtime` carry the truth.
- `data.require_realtime: true` makes runs **fail outright** rather than silently
  analyse stale prices.

## Current state

| Provider | Status | Real-time? | Volume consolidated? |
|---|---|---|---|
| `twelvedata` | **Working** | **Yes (plan-dependent)** | **Equities/ETFs: Yes; FX/Metals/Crypto: Tick/Venue** |
| `yahoo` | Working | No — delayed, unofficial | Yes, but delayed |
| `realtime` | Stub only | Requires a direct exchange feed | — |

The `twelvedata` provider is implemented in
`src/market_analyzer/providers/twelvedata.py` and talks to `api.twelvedata.com`
over REST with `httpx`. It is the first provider that satisfies
`data.require_realtime` for multi-asset (equities, indices via ETF proxies,
forex, metals, crypto).

There is still no synthetic/mock provider. That invariant is enforced by
`DataConfig`, and covered by a test that constructs the config through
`model_validate` (not `model_copy`, which bypasses validators).

## The Twelve Data volume caveat — read this before trusting a signal

Twelve Data provides real-time prices across asset classes, but **volume
consolidation varies by asset class**:

| Asset class | Price | Volume | Plan notes |
|---|---|---|---|
| US equities / ETFs (QQQ, SPY) | Real-time | Consolidated (exchange-wide) | Grow+ |
| Spot FX (XAU/USD, XAG/USD) | Real-time | Tick volume (broker-dealer) | Grow+ |
| Crypto (BTC/USD) | Real-time | Venue volume (Binance) | Grow+ |

What this means in practice:

| Signal | Valid on Twelve Data? | Why |
|---|---|---|
| Price, OHLC, indicators, RSI, MACD, ATR | **Yes** | Prices are real-time |
| `volume_ratio` (current bar vs own average) | **Equities only** | Tick/venue volume is not market-wide |
| Absolute volume, VWAP, OBV | **Equities only** | Tick/venue volume is non-representative |
| Cross-symbol volume comparison | **Equities only** | Different asset classes = different volume types |

The system enforces this rather than trusting the operator to remember:

- `TwelveDataProvider.volume_kind_for(symbol)` returns `"consolidated"`,
  `"tick"`, or `"venue"` per symbol.
- With non-consolidated volume, `liquidity_score` returns a **neutral
  constant** instead of a log-scaled absolute value, so the component cannot
  systematically misstate liquidity.
- Volume-gated setups (breakout, pullback) are **disabled by default** because
  the focused profile includes FX/metals/crypto where volume is tick/venue.
  Only volume-independent setups (trend continuation) can qualify.
- Every analysis carries a warning naming the feed and the specific symbols
  with non-consolidated volume. `doctor` and the MCP `get_provider_capabilities`
  tool surface it too.

A useful self-test: run the focused profile. You should see a warning listing
`XAUUSD (tick)`, `XAGUSD (tick)`, `BTCUSD (venue)` as non-consolidated.

## Market session awareness

Real-time data is not the same as *recent* data. Outside trading hours the
newest bar on the wire is legitimately hours old, so a naive staleness check
would reject a perfectly good feed. `src/market_analyzer/providers/session.py`
supplies a `MarketCalendar` for US equities (09:30-16:00 `America/New_York`),
`FxMetalsCalendar` (24/5 with daily rollover break ~22:00-22:05 UTC), and
`CryptoCalendar` (24/7/365) so the analyzer can tell "stale feed" from "market
is shut". Closed sessions are reported as a warning, not as a data failure.

Holiday calendars are passed in as data rather than hardcoded. A profile or
deployment should supply the real calendar; an empty one means weekends only.

## Moving to a consolidated feed

If you later subscribe to a consolidated product (e.g. a direct exchange feed
or vendor with true consolidated tape):

1. Implement a new provider in `providers/` that returns `volume_kind_for`
   as `"consolidated"` for all symbols.
2. Re-check the liquidity score — the log baseline in `rank.py` was calibrated
   against consolidated equity volume and may need adjustment for the new
   volume scale.
3. Enable volume-gated setups only after confirming the candidate list
   changes meaningfully.

## Known miscalibration: liquidity log baseline

`rank.py` scores liquidity as `log10(avg_volume + 1) / 16.0`. A baseline of 16
corresponds to 1e16 shares/day. Real large-cap volumes are 1e7-1e9, so the
component is compressed into roughly the 0.4-0.6 range and discriminates poorly
between instruments.

This was found while building the Twelve Data handling and is **not** fixed,
because retuning it changes every historical score and is a strategy decision.
A test (`test_liquidity_log_baseline_is_not_saturating_real_volumes`) documents
the current behaviour so a future change is deliberate.

## Remaining constraints

- F&O, currency, and commodities need separate adapters and separate
  fee/margin models.
- Exchange-level depth (NYSE BQT, Nasdaq TotalView) is not available from a
  retail API and still needs an agreement plus certified infrastructure.
- Twelve Data's intraday history window is plan-dependent; the 5-minute lookback
  the analyzer needs (60 bars ≈ 5 hours) should be comfortably inside the
  Grow+ plan, but confirm on first live run.
- If the feed ever degrades, the honest position is that **this becomes a
  delayed-data research tool again**, and `require_realtime` will refuse to let
  it pretend otherwise.
