# 07 — Statistics for Trading

Statistics provides tools for describing uncertainty and testing hypotheses.

## Expected value
For discrete outcomes:

E[X] = sum(p_i * x_i)

A strategy can have a positive expected value while losing frequently, or a high win
rate while having negative expected value.

## Variance and standard deviation
These describe dispersion around the mean. They are useful for understanding return
variability but are not complete measures of risk.

## Correlation
Correlation measures linear co-movement. Correlation can change over time and does
not imply causation.

## Covariance
Covariance measures joint variability and is used in portfolio calculations.

## Regression
Regression can estimate relationships between variables. A statistically significant
coefficient is not automatically a tradable or causal relationship.

## Base rates
Before believing a new signal, compare it with:
- A no-skill/random baseline where appropriate
- Buy-and-hold
- Cash
- Simple benchmark strategies
- Previously established baselines

## Out-of-sample testing
A model should be evaluated on data not used to formulate its parameters.

A useful split:
- Training/in-sample: develop hypothesis.
- Validation: tune cautiously.
- Test/out-of-sample: final evaluation.

The test set should remain untouched until the strategy is frozen.

## Walk-forward testing
Repeatedly train/develop on an earlier window and test on a later window. This can
better approximate changing market conditions.

## Multiple testing
Trying hundreds of strategies and reporting only the best one creates selection bias.
Record all meaningful experiments, not just successful ones.

## Confidence intervals
A performance estimate has uncertainty. Small samples can produce unstable results.

## Monte Carlo analysis
Resampling trade sequences or returns can help explore the range of possible outcomes,
but it depends on assumptions and does not prove future profitability.

## Statistical significance vs economic significance
A small statistical effect may disappear after costs. An economically meaningful effect
must survive realistic execution assumptions.

## Bayesian reasoning
The agent can update beliefs as evidence accumulates:
prior belief -> new evidence -> updated belief.

The update should reflect evidence quality and sample size, not merely recent outcomes.
