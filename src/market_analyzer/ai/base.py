"""AI contract for the analyzer.

BOUNDARY
--------
The model reads a completed analysis artefact and/or untrusted web text, and
returns typed advisory output. It must never:

  * produce or alter a price, indicator, score, or position size
  * decide whether a candidate is tradable
  * touch risk limits or the risk gate
  * promote its own knowledge proposals to approved

That is enforced by the return types in `ai.models`, which have no numeric
trading fields to fill in.

FAILURE POLICY
--------------
Free-tier models are rate-limited and frequently return 503. Every method
degrades to an empty/neutral result rather than raising, so a missing model can
never take down a market run. `degraded` is set on the result so callers can
distinguish "nothing found" from "the model was unavailable".
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from market_analyzer.ai.models import AnalysisNarrative, KnowledgeProposal, NewsEvent


class AiAnalyst(ABC):
    name: str
    enabled: bool = True

    @abstractmethod
    async def extract_events(
        self,
        symbol: str,
        items: list[dict[str, Any]],
    ) -> list[NewsEvent]:
        """Extract typed events from research results.

        `items` are raw research dicts (title/url/snippet/publisher) and are
        UNTRUSTED input. Implementations must not follow instructions found
        inside them.
        """

    @abstractmethod
    async def narrate_analysis(self, analysis: dict[str, Any]) -> AnalysisNarrative:
        """Explain an already-computed analysis artefact in plain language."""

    @abstractmethod
    async def propose_lesson(
        self,
        market: str,
        observations: list[dict[str, Any]],
    ) -> KnowledgeProposal | None:
        """Draft a candidate lesson for human review. Never auto-approves."""

    async def analyze_market(self, market_data: dict[str, Any]) -> dict[str, Any]:
        """Analyze market data for focused instruments using AI."""
        raise NotImplementedError("analyze_market not implemented by this provider")

    async def chat(
        self,
        prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 2000,
        timeout: int = 30,
    ) -> str:
        """Generic chat completion for market or risk tasks."""
        raise NotImplementedError("chat not implemented by this provider")

    async def aclose(self) -> None:
        """Release any resources. No-op by default.

        Intentionally not abstract: a provider with nothing to close should
        not be forced to write a no-op override.
        """
        return None


class NullAiProvider(AiAnalyst):
    """Used when AI is disabled or no API key is present.

    Keeps the pipeline identical to before the AI layer existed.
    """

    name = "null"
    enabled = False

    def _degraded(self, reason: str) -> None:
        self._reason = reason

    async def extract_events(self, symbol: str, items: list[dict[str, Any]]) -> list[NewsEvent]:
        return []

    async def narrate_analysis(self, analysis: dict[str, Any]) -> AnalysisNarrative:
        run_id = str(analysis.get("run_id", "unknown"))
        return AnalysisNarrative(
            run_id=run_id,
            regime=str(analysis.get("regime", "unknown")),
            summary="AI narrative unavailable; no model configured.",
            degraded=True,
            degrade_reason="no AI provider configured",
            model=self.name,
        )

    async def propose_lesson(
        self, market: str, observations: list[dict[str, Any]]
    ) -> KnowledgeProposal | None:
        return None

    async def analyze_market(self, market_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "market_synthesis": "AI market analysis disabled (NullAiProvider active).",
            "risk_tone": "neutral",
            "cross_asset_dynamics": "None",
            "candidate_analysis": {},
            "catalysts_and_risks": [],
        }

    async def chat(
        self,
        prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 2000,
        timeout: int = 30,
    ) -> str:
        return "{}"
