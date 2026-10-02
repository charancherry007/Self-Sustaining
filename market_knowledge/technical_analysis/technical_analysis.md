# 03 — Technical Analysis

Technical analysis studies information derived primarily from price, volume, and
related market variables. Indicators are measurement tools, not guarantees of future
returns.

## Trend
A trend can be described using sequences such as higher highs/higher lows or lower
highs/lower lows. Moving averages are common trend summaries.

### SMA
SMA_n(t) = average of the previous n observations.

### EMA
An exponential moving average weights recent observations more heavily than older ones.

Possible hypothesis:
"When a short moving average rises above a longer moving average, subsequent returns
may differ from baseline returns."

This is a hypothesis to test, not a fact.

## Momentum
Momentum strategies examine whether recent price strength/weakness contains information
about subsequent returns.

Common measures:
- Rate of change
- RSI
- MACD
- Stochastic oscillator

## Volatility
Common measures:
- Rolling standard deviation of returns
- ATR
- Bollinger Band width
- Realized volatility

Volatility can be used for position sizing or regime classification without assuming
that it predicts direction.

## Volume
Volume can provide context for price movements. Examples include volume averages,
volume changes, and VWAP. Volume definitions vary by asset and provider.

## Support and resistance
These are price areas that traders may interpret as locations of repeated buying/selling
interest. They are subjective and should be converted into measurable rules before
being backtested.

## Indicator combination
Combining many indicators can create apparent historical performance through overfitting.
Every additional rule increases the number of possible strategies.

## Technical-analysis experiment template
1. Define the signal mathematically.
2. Define the entry.
3. Define the exit.
4. Define position sizing.
5. Define holding period.
6. Include fees and slippage.
7. Test on an in-sample period.
8. Test on unseen data.
9. Compare against a baseline.
10. Record all parameters before seeing the final result.

## Failure modes
- Look-ahead bias
- Parameter overfitting
- Multiple-testing/data mining
- Regime dependence
- Ignoring execution costs
- Ignoring liquidity
