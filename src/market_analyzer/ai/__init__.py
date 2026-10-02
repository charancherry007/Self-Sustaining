"""Advisory AI layer for the market analyzer.

Strictly downstream of the deterministic pipeline: it reads completed artefacts
and untrusted web text, and returns advisory output. See `ai/models.py` for the
structural boundary that stops it from producing prices, scores, or trade
decisions.
"""

from market_analyzer.ai.base import AiAnalyst, NullAiProvider
from market_analyzer.ai.models import (
    AnalysisNarrative,
    Direction,
    KnowledgeProposal,
    NewsEvent,
    NewsEventType,
)

__all__ = [
    "AiAnalyst",
    "AnalysisNarrative",
    "Direction",
    "KnowledgeProposal",
    "NewsEvent",
    "NewsEventType",
    "NullAiProvider",
    "build_ai_analyst",
]


def build_ai_analyst(enabled: bool = False) -> AiAnalyst:
    """Construct the configured AI analyst, or a no-op if unavailable.

    Never raises: a missing key degrades to NullAiProvider so the market
    pipeline is unaffected by AI availability.
    """
    import os

    if not enabled:
        return NullAiProvider()

    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return NullAiProvider()

    from market_analyzer.ai.openrouter import DEFAULT_MODELS, OpenRouterAiProvider

    primary = os.getenv("OPENROUTER_MODEL", "").strip()
    models = (
        (primary, *(m for m in DEFAULT_MODELS if m != primary)) if primary else DEFAULT_MODELS
    )

    try:
        return OpenRouterAiProvider(
            api_key=api_key,
            models=models,
            timeout_seconds=float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "30")),
        )
    except ValueError:
        return NullAiProvider()
