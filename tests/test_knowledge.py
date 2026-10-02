from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from market_analyzer.knowledge.loader import load_file
from market_analyzer.knowledge.retriever import KnowledgeRetriever
from market_analyzer.models.knowledge import KnowledgeKind, KnowledgeRecord, ReviewStatus


def _record(**overrides) -> KnowledgeRecord:
    base = {
        "kind": KnowledgeKind.LESSON,
        "review_status": ReviewStatus.APPROVED,
        "market": "INDIA_CASH_EQUITIES",
        "title": "Test lesson",
        "body": "Body text",
        "confidence": 0.8,
    }
    base.update(overrides)
    return KnowledgeRecord.model_validate(base)


def test_shipped_seed_knowledge_is_valid():
    path = (
        Path(__file__).resolve().parents[1]
        / "knowledge"
        / "core"
        / "approved_lessons"
        / "india_cash_equities.yaml"
    )
    records = load_file(path)
    assert len(records) >= 4
    assert any(r.kind == KnowledgeKind.RULE for r in records)


def test_filter_by_market():
    retriever = KnowledgeRetriever([_record(market="OTHER"), _record()])
    matches = retriever.retrieve("INDIA_CASH_EQUITIES")
    assert len(matches) == 1


def test_expired_records_excluded():
    expired = _record(expires_at=datetime.now(timezone.utc) - timedelta(days=1))
    retriever = KnowledgeRetriever([expired, _record()])
    assert len(retriever.retrieve("INDIA_CASH_EQUITIES")) == 1


def test_glob_applies_to():
    retriever = KnowledgeRetriever([_record(applies_to=["TCS*"])])
    assert len(retriever.retrieve("INDIA_CASH_EQUITIES", symbol="TCS.NS")) == 1
    assert len(retriever.retrieve("INDIA_CASH_EQUITIES", symbol="INFY.NS")) == 0


def test_rules_rank_before_lessons():
    rule = _record(kind=KnowledgeKind.RULE, title="Rule", confidence=0.5)
    lesson = _record(title="Lesson", confidence=0.9)
    retriever = KnowledgeRetriever([lesson, rule])
    matches = retriever.retrieve("INDIA_CASH_EQUITIES")
    assert matches[0].kind == KnowledgeKind.RULE
