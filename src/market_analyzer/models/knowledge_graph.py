"""Knowledge graph schema for trade post-mortems and reinforcement learning."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GraphNodeType(str, Enum):
    TRADE = "trade"
    STRATEGY = "strategy"
    REGIME = "regime"
    SETUP = "setup"
    INSTRUMENT = "instrument"
    OUTCOME = "outcome"
    LESSON = "lesson"


class GraphEdgeType(str, Enum):
    EXECUTED_WITH = "EXECUTED_WITH"
    OCCURRED_IN = "OCCURRED_IN"
    TRIGGERED_BY = "TRIGGERED_BY"
    TRADED_ON = "TRADED_ON"
    RESULTED_IN = "RESULTED_IN"
    PRODUCED_LESSON = "PRODUCED_LESSON"
    REINFORCES = "REINFORCES"
    ADAPTS_STRATEGY = "ADAPTS_STRATEGY"


class GraphNode(BaseModel):
    """A single entity or concept node in the trade knowledge graph."""

    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    type: GraphNodeType
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """A directed semantic relationship between two knowledge nodes."""

    model_config = ConfigDict(frozen=True)

    source: str
    target: str
    relationship: GraphEdgeType
    weight: float = 1.0
    properties: dict[str, Any] = Field(default_factory=dict)


class KnowledgeGraphSnapshot(BaseModel):
    """Structured knowledge graph output capturing trade execution and learning."""

    model_config = ConfigDict(frozen=True)

    trade_id: str
    symbol: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    executive_summary: str
    lessons_learned: list[str] = Field(default_factory=list)
    performance_metrics: dict[str, Any] = Field(default_factory=dict)
