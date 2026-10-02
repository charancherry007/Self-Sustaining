"""Schema for curated knowledge records stored as YAML."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeKind(str, Enum):
    LESSON = "lesson"
    RULE = "rule"
    METADATA = "metadata"
    DATA_SOURCE = "data_source"
    FEE_SCHEDULE = "fee_schedule"


class ReviewStatus(str, Enum):
    APPROVED = "approved"
    PENDING = "pending"
    DEPRECATED = "deprecated"


class KnowledgeRecord(BaseModel):
    """One curated fact or lesson.

    `applies_to` holds symbols or glob-ish prefixes (e.g. `TECH*`); an empty
    list means the record applies to the whole market profile.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    kind: KnowledgeKind
    review_status: ReviewStatus = ReviewStatus.APPROVED
    market: str
    instrument: str | None = None
    applies_to: list[str] = Field(default_factory=list)
    title: str
    body: str
    source: str | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)
    created_at: datetime | None = None
    last_reviewed_at: datetime | None = None
    valid_from: datetime | None = None
    expires_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)
