# Trading Agent Market Knowledge Base
## Version 1.0 — Price Action, Candlesticks, Technical Analysis, Market Structure, Risk, and Advanced Concepts

## 0. Purpose and operating principles

This knowledge base is designed for an AI trading agent that analyzes market data and produces structured market interpretations.

The agent MUST:
1. Treat market interpretation as probabilistic, not deterministic.
2. Separate observation, interpretation, hypothesis, and decision.
3. Never treat a single candle or indicator as sufficient evidence for a trade.
4. Use multi-timeframe context.
5. Prefer price/volume/structure evidence over indicator-only signals.
6. Account for spread, slippage, liquidity, session, volatility, and execution constraints.
7. Never invent missing OHLCV, volume, order-book, or fundamental data.
8. Distinguish exchange-traded instruments, CFDs, futures, spot FX, and crypto markets.
9. Normalize symbols and timestamps before analysis.
10. Record the evidence behind every signal.

A useful reasoning hierarchy is:

Market regime
→ higher-timeframe structure
→ location/context
→ liquidity/volume/volatility
→ price action/candles
→ confirmation
→ entry
→ stop/invalidation
→ target
→ position sizing
→ execution
→ post-trade evaluation

---

# 1. Market data fundamentals

## 1.1 OHLCV

Each candle contains:

- Open: first traded/quoted price in the interval
- High: highest price
- Low: lowest price
- Close: last traded/quoted price
- Volume: traded quantity where available

For a candle:

Range = High - Low

Body = abs(Close - Open)

Upper Wick = High - max(Open, Close)

Lower Wick = min(Open, Close) - Low

Body Ratio = Body / Range

Close Location Value (CLV) can be approximated as:

CLV = ((Close - Low) - (High - Close)) / (High - Low)

Interpretation:
- CLV near +1: close near high
- CLV near -1: close near low
- CLV near 0: close near middle

Never calculate ratios when Range = 0.

## 1.2 Candle direction

Bullish candle:
Close > Open

Bearish candle:
Close < Open

Neutral:
Close approximately equal to Open, subject to instrument tick size.

A candle's color alone is weak information. Its location relative to structure, volatility, liquidity, and prior candles is more important.

## 1.3 Timeframes

Common timeframes:
- 1m
- 3m
- 5m
- 15m
- 30m
- 1h
- 4h
- 1D
- 1W

Use lower timeframes for execution and higher timeframes for context.

A typical hierarchy:
- Weekly/Daily: macro structure
- 4H/1H: intermediate structure
- 15m/5m: setup and execution
- 1m/3m: precision only when justified

Avoid mixing candles from different sessions without understanding session boundaries.

---

# 2. Candle anatomy

## 2.1 Long body

A large body relative to recent candles indicates directional displacement.

Potential interpretation:
- strong participation
- aggressive repricing
- breakout
- trend continuation
- liquidation

It does NOT automatically mean continuation.

Check:
1. Where did the candle occur?
2. Did it break structure?
3. Was volume elevated?
4. Did it close near its extreme?
5. Was there nearby resistance/support?
6. Did the next candle accept or reject the move?

## 2.2 Small body

Potential meanings:
- indecision
- compression
- reduced volatility
- temporary balance
- pause in trend

Small body alone is not a reversal signal.

## 2.3 Long upper wick

Possible meanings:
- rejection of higher prices
- profit taking
- supply entering
- failed breakout
- liquidity sweep

Confirmation is required.

## 2.4 Long lower wick

Possible meanings:
- rejection of lower prices
- demand entering
- stop sweep
- failed breakdown
- profit taking by shorts

Again, context determines interpretation.

---

# 3. Core candlestick patterns

Patterns are context-dependent. The agent must never treat pattern names as standalone signals.

## 3.1 Doji

Small body relative to range.

Meaning:
- temporary balance/indecision

More significant:
- after an extended move
- at major support/resistance
- near a liquidity event

Less significant:
- inside random consolidation

## 3.2 Hammer

Small body near the top of the range with a relatively long lower wick.

Potential interpretation:
- rejection of lower prices

Stronger when:
- occurs after decline
- forms at meaningful support
- follows a liquidity sweep
- closes back above a key level

## 3.3 Shooting star

Small body near the lower portion of range with long upper wick.

Potential interpretation:
- rejection of higher prices

Stronger at:
- resistance
- prior high
- liquidity sweep
- extended bullish move

## 3.4 Engulfing candle

Bullish engulfing:
Current bullish body materially covers prior bearish body.

Bearish engulfing:
Current bearish body materially covers prior bullish body.

The agent should compare actual OHLC values rather than rely on pattern labels.

## 3.5 Inside bar

Current candle range lies within prior candle range.

Represents compression.

Possible outcomes:
- continuation
- breakout
- false breakout

Use surrounding structure and volatility.

## 3.6 Outside bar

Current high exceeds prior high and current low falls below prior low.

This represents range expansion.

Interpretation depends on close location:
- close near high: bullish displacement
- close near low: bearish displacement
- close near middle: possible two-sided auction

## 3.7 Morning/evening star

Three-candle reversal formations.

Treat as a sequence:
1. directional candle
2. contraction/indecision
3. confirmation candle

The third candle matters substantially.

---

# 4. Candlestick context engine

For every significant candle, evaluate:

### A. Location
- prior swing high
- prior swing low
- support
- resistance
- range boundary
- moving average
- VWAP
- volume profile level
- Fibonacci area
- previous session high/low
- opening range
- psychological level

### B. Structure
- higher high
- higher low
- lower high
- lower low
- range
- breakout
- breakdown
- failed breakout

### C. Liquidity
- equal highs
- equal lows
- clustered stops
- previous day high/low
- session high/low
- obvious swing points

### D. Participation
- volume
- relative volume
- tick volume where actual volume is unavailable
- spread
- range expansion

### E. Volatility
- ATR
- realized volatility
- candle range relative to recent average

### F. Confirmation
- next candle
- retest
- structure break
- volume confirmation
- VWAP acceptance/rejection

---

# 5. Market structure

Market structure is the organization of swing highs and lows.

## 5.1 Uptrend

Typical sequence:

Higher High (HH)
Higher Low (HL)
Higher High
Higher Low

## 5.2 Downtrend

Typical sequence:

Lower Low (LL)
Lower High (LH)
Lower Low
Lower High

## 5.3 Range

Price oscillates between relatively stable boundaries.

Do not automatically apply trend-following signals inside a range.

## 5.4 Swing detection

A swing high is a local high surrounded by lower highs.

A swing low is a local low surrounded by higher lows.

Algorithms should define lookback/lookforward windows rather than relying on visual judgment.

---

# 6. Break of structure and market structure shift

## Break of Structure (BOS)

A directional structural break consistent with the existing trend.

Example:
Uptrend → price breaks previous swing high.

## Change of Character / Market Structure Shift

A structural break against the previous directional behavior.

Example:
Uptrend → price breaks a meaningful higher low.

These labels are used differently by different trading communities. The agent should define its own exact algorithmic rules and avoid treating terminology as universal.

---

# 7. Support and resistance

Support/resistance should be treated as zones rather than exact lines.

Sources:
- previous swing points
- repeated reactions
- session highs/lows
- previous day/week levels
- high-volume areas
- round numbers
- VWAP
- volume profile
- opening range

Strength increases when multiple independent factors overlap.

Avoid excessive levels. Too many levels destroy signal quality.

---

# 8. Supply and demand

Supply zone:
Area where selling previously caused meaningful downward displacement.

Demand zone:
Area where buying previously caused meaningful upward displacement.

Important checks:
- magnitude of displacement
- freshness
- number of retests
- volume
- structure
- broader trend
- whether the zone has already been consumed

Do not assume every consolidation before a move is a valid supply/demand zone.

---

# 9. Liquidity

Liquidity refers to the availability of orders and the ability to transact without excessive price impact.

Common liquidity reference points:
- previous highs
- previous lows
- equal highs
- equal lows
- session highs/lows
- range extremes
- round numbers
- obvious stop locations

## Liquidity sweep

Price temporarily moves beyond a known level and then reverses back.

Possible explanation:
- stop execution
- breakout failure
- liquidity seeking
- genuine continuation followed by retracement

A sweep is not automatically manipulation.

Require confirmation.

---

# 10. False breakouts

A false breakout occurs when price breaks a recognized boundary but fails to sustain acceptance beyond it.

Evidence:
1. Break of level
2. Weak follow-through
3. Return inside range
4. Strong rejection
5. Optional structure break in opposite direction

A breakout should be considered more credible when there is:
- displacement
- closing acceptance
- volume confirmation
- successful retest

---

# 11. Trend analysis

## Trend strength

Evaluate:
- slope
- HH/HL or LH/LL consistency
- pullback depth
- impulse/pullback ratio
- volume
- ATR
- ADX if used
- distance from VWAP
- momentum

## Trend exhaustion

Potential signs:
- increasingly weak continuation
- large wick rejection
- momentum divergence
- climactic volume
- extended distance from mean
- failed breakouts
- structural failure

No individual exhaustion signal guarantees reversal.

---

# 12. Moving averages

Common:
- SMA 20
- SMA 50
- SMA 100
- SMA 200
- EMA 9
- EMA 20
- EMA 50

Uses:
- trend context
- dynamic support/resistance
- mean reversion
- slope measurement

Avoid treating crossover systems as universal truths.

The agent should evaluate:
- price vs MA
- MA slope
- MA separation
- timeframe alignment
- volatility regime

---

# 13. VWAP

Volume Weighted Average Price:

VWAP = Sum(Price × Volume) / Sum(Volume)

Uses:
- institutional/reference benchmark
- intraday mean
- trend bias
- support/resistance
- reversion framework

Useful concepts:
- price above VWAP
- price below VWAP
- VWAP reclaim
- VWAP rejection
- VWAP deviation

Anchored VWAP can be anchored to:
- session start
- major swing
- earnings/event
- breakout
- significant low/high

---

# 14. Volume analysis

Volume can validate or challenge price movement.

## Relative volume

Relative Volume (RVOL):

Current volume / expected volume for comparable period.

High RVOL:
- unusual participation

Low RVOL:
- weak participation

Important:
Volume data quality varies significantly by market.

For decentralized FX/CFD instruments, reported volume may be broker-specific tick volume rather than centralized exchange volume.

---

# 15. Volume profile

Important concepts:
- Point of Control (POC)
- Value Area High (VAH)
- Value Area Low (VAL)
- High Volume Node (HVN)
- Low Volume Node (LVN)

Interpretation:
HVN often represents accepted/balanced trading.
LVN can represent fast-travel or low-acceptance areas.

Use as contextual evidence, not standalone prediction.

---

# 16. Volatility

## ATR

Average True Range measures typical price movement.

True Range:

max(
High - Low,
abs(High - Previous Close),
abs(Low - Previous Close)
)

ATR is usually an average of True Range over N periods.

Uses:
- stop distance
- position sizing
- volatility regime
- target calibration

## Volatility regimes

Classify:
- low volatility
- normal volatility
- high volatility
- extreme volatility

Strategy behavior should change by regime.

---

# 17. Momentum indicators

## RSI

Relative Strength Index measures recent upward/downward price momentum.

Common period:
14

Do not interpret:
RSI > 70 = automatically short
RSI < 30 = automatically long

Instead evaluate:
- trend
- divergence
- regime
- failure swings
- range vs trend behavior

## MACD

MACD commonly uses:
EMA(12) - EMA(26)

Signal line:
EMA(9) of MACD

Histogram:
MACD - Signal

Uses:
- momentum
- trend acceleration/deceleration
- crossovers
- divergence

---

# 18. Divergence

Bullish divergence:
Price makes a lower low while oscillator makes a higher low.

Bearish divergence:
Price makes a higher high while oscillator makes a lower high.

Divergence indicates momentum disagreement, not guaranteed reversal.

Hidden divergence can support continuation.

---

# 19. Fibonacci analysis

Common retracement levels:
- 23.6%
- 38.2%
- 50%
- 61.8%
- 78.6%

Use Fibonacci only when anchored to meaningful swings.

Do not treat Fibonacci levels as inherently predictive.

Confluence is more meaningful:
Fibonacci + structure + volume + liquidity + volatility.

---

# 20. Market sessions

For global markets, session context matters.

Common sessions:
- Asia
- London
- New York

Important events:
- session open
- session high/low
- opening range
- overlap periods
- session close

For U.S. equities:
- pre-market
- regular trading hours
- after-hours

The agent must use the exchange's official trading calendar whenever possible.

---

# 21. Opening range

Opening Range Breakout (ORB):

Define a range over the first N minutes.

Track:
- opening high
- opening low
- breakout
- retest
- volume
- VWAP
- broader trend

Do not assume every opening-range breakout continues.

---

# 22. Gaps

Gap up:
Open > previous close.

Gap down:
Open < previous close.

Types:
- common gap
- breakaway gap
- continuation/runaway gap
- exhaustion gap

Analyze:
- gap size relative to ATR
- premarket volume
- prior structure
- opening acceptance
- gap fill behavior

---

# 23. Price discovery and auction concepts

Markets can be viewed as continuous auctions.

Concepts:
- acceptance
- rejection
- balance
- imbalance
- value
- discovery
- initiative activity
- responsive activity

### Acceptance
Price spends time and/or volume at a region.

### Rejection
Price quickly leaves a region.

### Balance
Two-sided trade within a range.

### Imbalance
One-sided aggressive movement.

---

# 24. Order flow

Where data permits, analyze:

- bid volume
- ask volume
- trade aggressor
- cumulative delta
- footprint
- absorption
- exhaustion
- imbalance
- order-book depth

## Absorption

Large aggressive buying/selling occurs but price fails to advance proportionally.

Possible interpretation:
Passive liquidity is absorbing aggressive flow.

Never infer absorption without suitable order-flow data.

---

# 25. Order book concepts

Important:
- bid
- ask
- spread
- depth
- market orders
- limit orders
- cancellations
- imbalance

Order book snapshots are not equivalent to executed trades.

Spoofing/layering can make displayed liquidity unreliable.

---

# 26. Market microstructure

Track:
- spread
- slippage
- market impact
- liquidity
- queue position where available
- latency
- quote updates
- trade frequency

Execution quality matters especially for:
- scalping
- 1m/3m systems
- news trading
- crypto
- thin instruments

---

# 27. Wyckoff concepts

Core concepts:
- accumulation
- markup
- distribution
- markdown
- trading range
- spring
- upthrust
- sign of strength
- sign of weakness

Treat Wyckoff labels as analytical frameworks rather than objectively defined market states.

---

# 28. Elliott Wave

Concepts include:
- impulse
- corrective structures
- wave relationships
- Fibonacci relationships

Because wave counts are subjective, an automated agent should use strict rules and confidence levels.

Never allow a discretionary wave count to override objective risk controls.

---

# 29. Classical chart structures

Patterns:
- double top
- double bottom
- triple top/bottom
- head and shoulders
- inverse head and shoulders
- triangle
- wedge
- flag
- pennant
- rectangle
- cup and handle

For every pattern:
1. Define objective geometry.
2. Define breakout level.
3. Define invalidation.
4. Measure expected move.
5. Check volume/volatility.
6. Check higher-timeframe context.

---

# 30. Statistical price behavior

The agent should understand:

- returns
- log returns
- mean
- median
- variance
- standard deviation
- skew
- kurtosis
- autocorrelation
- correlation
- covariance
- percentile
- z-score
- rolling statistics

## Log return

r_t = ln(P_t / P_{t-1})

## Z-score

z = (x - rolling_mean) / rolling_std

Use rolling windows and avoid look-ahead bias.

---

# 31. Correlation and cross-market analysis

Potential relationships:

- equities ↔ volatility
- equities ↔ bond yields
- gold ↔ USD
- commodities ↔ currencies
- BTC ↔ risk assets
- index futures ↔ cash indices

Correlation is dynamic.

Never assume historical correlation remains stable.

---

# 32. Beta

Beta estimates sensitivity to a benchmark.

Beta = Cov(asset, benchmark) / Var(benchmark)

Useful for:
- portfolio risk
- relative exposure
- hedging

---

# 33. Relative strength

Compare an instrument against:
- benchmark
- sector
- index
- peer
- asset class

Example:

Relative Strength = Asset Return - Benchmark Return

Useful for identifying leadership/lagging behavior.

---

# 34. Mean reversion

Mean reversion hypothesis:

Price tends to return toward a statistical or structural mean under certain regimes.

Potential references:
- VWAP
- moving average
- rolling mean
- value area
- z-score

Mean reversion tends to behave differently in strong trends.

The agent must classify regime first.

---

# 35. Trend following

Trend-following hypothesis:
Directional persistence can continue after a confirmed move.

Typical components:
- structure
- breakout
- pullback
- moving averages
- momentum
- volatility

Avoid chasing extended candles without evaluating reward/risk.

---

# 36. Breakout systems

A breakout model should define:

1. Range
2. Breakout threshold
3. Confirmation
4. Entry
5. Stop/invalidation
6. Target
7. Time limit
8. Failure condition

Breakout quality can be scored from measurable evidence, but scores must be calibrated using historical data.

---

# 37. Pullback systems

Typical sequence:

Trend
→ impulse
→ pullback
→ confirmation
→ continuation

Evaluate:
- pullback depth
- volume contraction
- structure preservation
- VWAP/MA location
- Fibonacci confluence
- reversal candle
- momentum recovery

---

# 38. Risk management

Risk management is independent from prediction.

Important concepts:
- maximum risk per trade
- maximum daily loss
- maximum exposure
- correlation exposure
- position size
- stop loss
- trailing stop
- max drawdown
- risk of ruin

## Position sizing

Approximate:

Position Size =
Account Risk / Stop Distance

For monetary instruments, convert stop distance into actual currency risk using contract size, tick value, lot size, or point value.

---

# 39. Risk/reward

Reward/Risk:

R = Potential Reward / Potential Risk

Do not trade solely because R is high.

A setup with high theoretical reward but very low probability can still lose money.

---

# 40. Expectancy

Trading expectancy:

E = (Win Rate × Average Win)
    - (Loss Rate × Average Loss)

Include:
- commissions
- spread
- slippage
- financing/funding
- other costs

Positive historical expectancy does not guarantee future profitability.

---

# 41. Drawdown

Maximum drawdown measures peak-to-trough equity decline.

Track:
- absolute drawdown
- percentage drawdown
- duration
- recovery time

The agent should have explicit drawdown-based risk reduction.

---

# 42. Backtesting

A valid backtest must address:

- look-ahead bias
- survivorship bias
- selection bias
- data snooping
- overfitting
- transaction costs
- spread
- slippage
- latency
- corporate actions
- market hours
- missing data

Use:
- train
- validation
- test
- walk-forward analysis

Never optimize on the final test set.

---

# 43. Walk-forward analysis

Example:

Historical data
→ training window
→ optimize/calibrate
→ forward test
→ roll window
→ repeat

This better represents changing market conditions than one static backtest.

---

# 44. Monte Carlo analysis

Randomize:
- trade order
- returns
- execution costs
- slippage
- outcomes

Estimate:
- drawdown distribution
- losing streaks
- risk of ruin
- equity variability

---

# 45. Regime detection

Possible regimes:

1. Strong bullish trend
2. Weak bullish trend
3. Strong bearish trend
4. Weak bearish trend
5. Range
6. High-volatility trend
7. High-volatility range
8. Low-volatility compression
9. Event/news regime

Possible inputs:
- ATR percentile
- ADX
- moving-average slope
- trend structure
- realized volatility
- volume
- correlation
- breadth

Strategy selection should depend on regime.

---

# 46. Multi-timeframe analysis

Use a top-down process.

Example:

Daily:
What is the macro structure?

4H:
Where are major levels?

1H:
What is the intermediate trend?

15m:
Is there a setup?

5m:
Is there an entry trigger?

1m:
Only if necessary for execution.

A lower timeframe should not blindly override higher-timeframe structure.

---

# 47. Confluence

Confluence means multiple independent pieces of evidence support the same hypothesis.

Example:

Bullish hypothesis:
- higher-timeframe uptrend
- price at demand
- liquidity sweep
- bullish displacement
- VWAP reclaim
- volume expansion
- lower-timeframe higher low

Confluence should increase confidence only when the signals are sufficiently independent.

Ten correlated indicators do not equal ten independent confirmations.

---

# 48. News and event risk

Market behavior can change around:
- central-bank decisions
- inflation releases
- employment reports
- GDP
- earnings
- geopolitical events
- regulatory announcements
- major corporate events

The agent should have an event-risk state.

During high-impact events:
- widen expected slippage
- account for spread expansion
- reduce or disable new positions according to predefined policy
- avoid interpreting abnormal candles as ordinary price action

---

# 49. Fundamental analysis

For equities:

Monitor:
- revenue
- earnings
- margins
- EPS
- free cash flow
- debt
- cash
- guidance
- valuation
- buybacks
- dilution

Useful ratios:
- P/E
- EV/EBITDA
- P/S
- P/B
- FCF yield
- ROE
- ROIC

Fundamental data should be timestamped according to when it became publicly available to prevent look-ahead bias.

---

# 50. Futures concepts

Important:
- contract
- expiry
- tick size
- tick value
- margin
- open interest
- volume
- basis
- contango
- backwardation
- rollover

For index analysis, futures can provide price discovery outside regular cash-market hours.

Never mix futures and CFD prices without mapping their differences.

---

# 51. Options concepts

Understand:
- call
- put
- strike
- expiry
- premium
- intrinsic value
- extrinsic value
- implied volatility
- delta
- gamma
- theta
- vega
- rho
- open interest
- volume

Advanced:
- volatility surface
- skew
- term structure
- dealer gamma exposure

Options data can provide information about expected volatility, but open interest should not automatically be interpreted as directional positioning.

---

# 52. Implied volatility

Implied volatility is the volatility implied by option prices under an option-pricing framework.

Uses:
- volatility expectations
- option pricing
- event risk
- relative volatility analysis

Compare:
- implied volatility
- realized volatility

The difference can be informative but is not a guaranteed trading signal.

---

# 53. Market breadth

For equity markets:
- advance/decline
- new highs/new lows
- up/down volume
- percentage above moving average
- sector participation

Breadth helps determine whether an index move is broadly supported.

---

# 54. Intermarket analysis

Possible inputs:
- equity indices
- Treasury yields
- USD
- commodities
- volatility indices
- credit spreads
- currencies

The agent should model relationships statistically rather than use fixed slogans such as "gold always rises when the dollar falls."

---

# 55. Execution concepts

Before sending an order evaluate:

- current bid/ask
- spread
- expected slippage
- liquidity
- order type
- position size
- volatility
- session
- latency
- broker/exchange rules

Order types:
- market
- limit
- stop
- stop-limit
- bracket
- trailing

A market-data signal is not the same thing as an executable trade.

---

# 56. Signal architecture

Every signal should contain:

```json
{
  "symbol": "NAS100",
  "timestamp": "...",
  "timeframe": "5m",
  "regime": "trend_up",
  "structure": "higher_high_higher_low",
  "location": "previous_resistance_retest",
  "candle_event": "bullish_displacement",
  "volume_state": "above_average",
  "volatility_state": "normal_high",
  "liquidity_event": "sell_side_sweep",
  "confirmation": [
    "structure_reclaim",
    "VWAP_reclaim"
  ],
  "hypothesis": "continuation_long",
  "invalidation": "...",
  "target": "...",
  "risk_reward": 2.1,
  "confidence": 0.0,
  "evidence": []
}
```

Confidence must be calibrated against historical outcomes. Do not fabricate a probability.

---

# 57. Agent reasoning protocol

For each market observation:

### Step 1 — Data validation
Check:
- timestamp
- OHLC integrity
- missing candles
- duplicate candles
- symbol
- timezone
- session
- data source

### Step 2 — Market regime
Classify:
- trend/range
- volatility
- liquidity
- session

### Step 3 — Higher-timeframe context
Identify:
- major highs/lows
- support/resistance
- trend
- value areas

### Step 4 — Current structure
Identify:
- swings
- BOS
- structural shift
- range

### Step 5 — Location
Determine whether price is:
- at value
- at extension
- near liquidity
- at support/resistance
- near VWAP
- near volume-profile levels

### Step 6 — Price action
Analyze:
- candle anatomy
- displacement
- rejection
- engulfing
- compression
- breakout/retest

### Step 7 — Participation
Analyze:
- volume
- relative volume
- order flow if available

### Step 8 — Momentum
Check:
- RSI
- MACD
- rate of change
- momentum divergence

### Step 9 — Scenario generation
Generate at least:
- primary scenario
- invalidation scenario
- alternative scenario

### Step 10 — Risk
Calculate:
- entry
- stop
- target
- expected cost
- position size
- R multiple

### Step 11 — Execution gate
Trade only if all hard constraints pass.

---

# 58. Evidence hierarchy

Prefer evidence in this order:

1. Valid market data
2. Market structure
3. Price location
4. Liquidity
5. Volume/order flow
6. Volatility
7. Momentum
8. Secondary indicators
9. Pattern labels

Pattern labels should never override actual price structure.

---

# 59. Common reasoning errors

Avoid:

- single-candle predictions
- indicator stacking
- hindsight pattern fitting
- assuming every wick is a liquidity sweep
- assuming every breakout continues
- assuming RSI overbought means short
- assuming RSI oversold means long
- assuming high volume means bullish
- assuming low volume means bearish
- treating correlation as causation
- ignoring transaction costs
- ignoring market sessions
- ignoring news
- using future information in backtests
- overfitting parameters
- changing rules after seeing outcomes

---

# 60. Trading decision states

The agent should have explicit states:

```text
NO_SETUP
WATCH
SETUP_FORMING
CONFIRMATION_PENDING
READY
EXECUTING
IN_POSITION
EXITING
COOLDOWN
BLOCKED
```

The default state should be `NO_SETUP`.

No trade is itself a valid outcome.

---

# 61. Hard risk gates

The agent MUST NOT trade when:

- data is stale
- required price fields are missing
- symbol mapping is uncertain
- spread exceeds maximum
- slippage estimate exceeds maximum
- daily loss limit has been reached
- maximum exposure is reached
- market is closed
- broker connection is unhealthy
- risk calculation fails
- stop-loss cannot be defined
- position size cannot be calculated
- event-risk policy blocks trading

---

# 62. Market-specific considerations

## Equities
Consider:
- earnings
- corporate actions
- gaps
- premarket
- regular session
- after-hours

## Futures
Consider:
- contract expiry
- rollover
- tick value
- margin
- session

## Forex
Consider:
- decentralized liquidity
- broker-specific pricing
- swap/financing
- session overlaps

## Metals
Consider:
- spot vs futures
- USD relationship
- macro events
- liquidity/session

## Crypto
Consider:
- 24/7 trading
- exchange fragmentation
- funding
- basis
- liquidation cascades
- weekend liquidity

## CFDs
Consider:
- broker-specific quote
- spread
- financing
- synthetic/index methodology
- market hours
- execution rules

---

# 63. Symbol normalization

Never assume provider symbols are universal.

Example mapping:

```json
{
  "canonical": "NAS100",
  "providers": {
    "provider_a": "NAS100",
    "provider_b": "USTEC",
    "provider_c": "US100"
  }
}
```

For every instrument store:

- canonical symbol
- provider symbol
- asset class
- exchange
- currency
- contract multiplier
- tick size
- tick value
- timezone
- trading calendar
- data source
- price type

---

# 64. Data quality monitoring

Track:

- last update timestamp
- latency
- missing bars
- duplicate bars
- out-of-order ticks
- abnormal spreads
- price jumps
- stale quotes
- feed disconnects

A trading agent should have a separate `DATA_HEALTH` state.

---

# 65. Recommended knowledge retrieval structure

Store this knowledge base in chunks:

```text
kb/
├── 01_market_data.md
├── 02_candlesticks.md
├── 03_market_structure.md
├── 04_support_resistance.md
├── 05_liquidity.md
├── 06_volume_orderflow.md
├── 07_volatility.md
├── 08_indicators.md
├── 09_price_action.md
├── 10_chart_patterns.md
├── 11_market_regimes.md
├── 12_multi_timeframe.md
├── 13_intermarket.md
├── 14_fundamentals.md
├── 15_futures.md
├── 16_options.md
├── 17_risk_management.md
├── 18_execution.md
├── 19_backtesting.md
├── 20_agent_reasoning.md
└── 21_symbol_normalization.md
```

For RAG, chunk by concept rather than arbitrary token length.

Recommended metadata:

```json
{
  "topic": "candlestick",
  "subtopic": "engulfing",
  "asset_classes": ["equity", "index", "forex", "crypto"],
  "timeframes": ["1m", "5m", "15m", "1h", "4h", "1d"],
  "level": "intermediate",
  "type": "technical_analysis",
  "requires_market_data": true
}
```

---

# 66. Final principle

The agent should not ask:

"Which candlestick pattern is this?"

It should ask:

"Given the current market regime, higher-timeframe structure, price location, liquidity, volatility, participation, and candle behavior, what hypotheses are supported by the available evidence, what would invalidate them, and is the expected opportunity sufficient to justify the risk and execution costs?"

That distinction is fundamental to building a robust market-analysis agent.
