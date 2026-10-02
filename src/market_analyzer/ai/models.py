"""Typed outputs the AI layer is allowed to produce.

DESIGN CONSTRAINT: nothing in this module can express a price, a score, a
position size, or a risk limit. That is deliberate and structural rather than a
convention. The AI can describe and classify; it cannot compute, and it cannot
authorise. If a future requirement needs the model to influence a number, that
must be a different component with its own audit trail, not a field added here.

Every model is marked `untrusted=True` and carries the model id that produced
it, so downstream consumers can always trace a claim back to its origin.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from market_analyzer.models.knowledge import KnowledgeKind, ReviewStatus


class NewsEventType(StrEnum):
    EARNINGS = "earnings"
    GUIDANCE = "guidance"
    ANALYST_ACTION = "analyst_action"
    M_AND_A = "m_and_a"
    REGULATORY = "regulatory"
    MANAGEMENT = "management"
    PRODUCT = "product"
    MACRO = "macro"
    OTHER = "other"


class Direction(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class AiResult(BaseModel):
    """Common provenance fields for every AI output."""

    model_config = ConfigDict(extra="forbid")

    untrusted: bool = True
    model: str = "unknown"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Populated on degradation so callers can tell "nothing found" from
    # "the model was unavailable".
    degraded: bool = False
    degrade_reason: str | None = None


class NewsEvent(AiResult):
    """A single typed, sourced event extracted from a news snippet or page."""

    symbol: str
    kind: NewsEventType = NewsEventType.OTHER
    direction: Direction = Direction.NEUTRAL
    # 0..1 importance, not probability of price movement.
    severity: float = Field(default=0.5, ge=0, le=1)
    summary: str = Field(max_length=400)
    source_url: str | None = None
    source_publisher: str | None = None


class AnalysisNarrative(AiResult):
    """Plain-language reading of a completed analysis artefact.

    The narrative is generated FROM the typed artefact, so it can restate and
    explain but cannot introduce a number that is not already present.
    """

    run_id: str
    regime: str
    summary: str = Field(max_length=1500)
    highlights: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)
    # Which candidate symbols the narrative refers to, for traceability.
    symbols: list[str] = Field(default_factory=list)


class KnowledgeProposal(AiResult):
    """A draft lesson for a human to review.

    `review_status` is pinned to PENDING and cannot be set to APPROVED by the
    model. Promotion is a human action; the AI only ever drafts.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(max_length=120)
    market: str
    lesson: str = Field(max_length=1000)
    kind: KnowledgeKind = KnowledgeKind.LESSON
    applies_to: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0, le=1)
    review_status: ReviewStatus = ReviewStatus.PENDING
    evidence_symbols: list[str] = Field(default_factory=list)

    def to_record(self) -> dict:
        """Serialise to the curated-knowledge YAML shape (pending, never approved)."""
        return {
            "schema_version": 1,
            "kind": self.kind.value,
            "review_status": self.review_status.value,
            "market": self.market,
            "applies_to": self.applies_to,
            "title": self.title,
            "body": self.lesson,
            "source": f"ai:{self.model}",
            "confidence": self.confidence,
            "created_at": self.generated_at.isoformat(),
            "tags": sorted({*self.tags, "ai-draft"}),
        }
