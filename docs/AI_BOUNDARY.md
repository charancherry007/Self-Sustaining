# AI boundary

The AI layer is advisory. It reads completed artefacts and untrusted web text,
and returns typed output. It cannot influence a trade.

## Multi-Timeframe Analysis Integration (New in v0.1.0)

The AI market analyst now receives multi-timeframe context for each candidate:

- **4h (macro trend)**: Dominant trend bias (bullish/bearish/neutral)
- **1h (intermediate structure)**: Trend alignment with macro
- **15m (entry trigger)**: Setup type and execution signal

Key MTF metrics passed to the model per candidate:
- `tf_trend_agreement` (0..1): Fraction of timeframes agreeing with 4h trend
- `tf_rsi_alignment` (0..1): Fraction of TFs with constructive RSI (40-70)
- `tf_volume_confirmation` (0..1): 15m volume vs. 20-period average
- `dominant_trend`: 4h trend direction
- `mtf_setup`: Per-TF setup labels (e.g., `4h: trend_continuation`, `1h: trend_pullback`, `15m: momentum_breakout`)

Entry logic enforced by the deterministic pipeline: 15m setup must align with 4h/1h trend (bullish 4h + long 15m = valid). The AI interprets this MTF context but cannot override the trend gate.

---

## What the model may do

- Summarise an already-computed analysis in plain language.
- Classify news into typed events (earnings, guidance, analyst action, M&A,
  regulatory, management change, macro) with a direction and severity.
- Draft a candidate lesson for a human to review.

## What the model may never do

- Produce or alter a price, indicator, score, or position size.
- Decide whether a candidate is tradable.
- Touch risk limits or the risk gate.
- Write to approved knowledge, or promote its own proposals.

This is **structural, not a prompt instruction.** The return types in
`ai/models.py` contain no field in which a price or score could be expressed.
A test asserts that no AI model exposes any of `price`, `score`, `entry`,
`size`, `quantity`, `stop`, or `target`. Adding such a field would fail CI, so
the boundary cannot be eroded by accident.

## Failure behaviour

Free-tier models are rate-limited and frequently return 503. Every failure path
degrades to a neutral result rather than raising:

| Situation | Result |
|---|---|
| No `OPENROUTER_API_KEY` | `NullAiProvider`; pipeline unchanged |
| `ai.enabled: false` | `NullAiProvider`; pipeline unchanged |
| All models 503/429 | Empty events; `degraded: true` on the narrative |
| Malformed JSON | Parsed defensively; empty result, no crash |
| Three consecutive failures | Circuit opens for 5 minutes |
| Slow model | Bounded by `OPENROUTER_TIMEOUT_SECONDS` |

A market run never fails because AI is unavailable.

## Injection safety

Web page and news-snippet text is untrusted. It is wrapped in `<untrusted>` tags
and the system prompt states that it is data, not instructions. The model
classifies it; it does not execute it. This reduces but does not eliminate
prompt-injection risk, which is why nothing downstream trusts an AI field for
anything load-bearing.

## Knowledge proposals

`propose_knowledge_lesson` returns a draft with `review_status: pending`,
tagged `ai-draft`, and **does not write it to disk**. Promotion to
`knowledge/core/approved_lessons/` is a deliberate human action.

The model cannot self-approve: `review_status` is pinned to `PENDING`, and the
`approved_only: true` gate in `KnowledgeConfig` is unchanged.

## Cost control

- `ai.max_symbols_per_run` (default 5) caps how many symbols reach the model
  per run.
- Extraction is **batch per symbol**, never one call per instrument across the
  universe.
- `OPENROUTER_MODEL` sets the primary model; built-in free models remain as
  fallbacks, because free-tier availability changes without notice.

## Why not MCP sampling

MCP exposes a "sampling" feature that lets a server ask the *client's* LLM to
do work. It is deliberately unused here. Behaviour would then depend on
whichever MCP client happened to be connected, which is unacceptable for a
component whose output feeds risk review. Calling the model API directly means
the model, the prompt, and the parameters are fixed and auditable per run.