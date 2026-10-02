# 10 — Behavioral Finance

Behavioral finance studies systematic patterns in human financial decision-making.
These concepts can also be useful as diagnostic labels for an AI's trading behavior,
without assuming that the AI literally experiences human emotions.

## Loss aversion
Humans may respond differently to losses and gains. For an AI, investigate whether
its behavior changes after losses in a way that harms expected outcomes.

## Overconfidence
Diagnostic pattern:
- Increasing position size after a short winning streak.
- Treating uncertain forecasts as certain.
- Ignoring contradictory evidence.

## Recency bias
Overweighting very recent outcomes can cause an agent to abandon a strategy too quickly.

## Confirmation bias
Searching only for information supporting an existing position can distort decisions.

## Revenge-trading analogue
After a loss, increasing risk primarily to recover the loss is a potentially dangerous
behavioral pattern.

## FOMO analogue
Entering because price has already moved sharply without a predefined decision rule.

## Anchoring
Giving excessive weight to a prior price or arbitrary reference point.

## Diagnostic use
The evaluation engine can flag:
- Position-size changes after losses
- Trading frequency spikes
- Strategy changes after small samples
- Repeated re-entry after stop-outs
- Increasing leverage after drawdowns

These are observations, not psychological diagnoses.

## Agent reflection questions
- Did I change risk because evidence changed or because recent P&L changed?
- Did I seek disconfirming evidence?
- Am I reacting to one trade or a statistically meaningful sample?
- Did my assumptions change?
- What evidence would make me abandon this hypothesis?
