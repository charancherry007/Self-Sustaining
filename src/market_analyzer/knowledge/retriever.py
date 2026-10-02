"""Filter curated knowledge for a market profile / instrument."""

from __future__ import annotations

from datetime import datetime, timezone

from market_analyzer.models.knowledge import KnowledgeRecord


def _is_expired(record: KnowledgeRecord, now: datetime) -> bool:
    return record.expires_at is not None and record.expires_at < now


def _not_yet_valid(record: KnowledgeRecord, now: datetime) -> bool:
    return record.valid_from is not None and record.valid_from > now


def _applies_to(record: KnowledgeRecord, symbol: str | None) -> bool:
    if symbol is None or not record.applies_to:
        # An empty applies_to means "market-wide".
        return not record.applies_to
    base = symbol.split(".")[0]
    for pattern in record.applies_to:
        if pattern in (symbol, base):
            return True
        if pattern.endswith("*") and base.startswith(pattern[:-1]):
            return True
    return False


class KnowledgeRetriever:
    def __init__(self, records: list[KnowledgeRecord], approved_only: bool = True) -> None:
        self._records = records

    def retrieve(
        self,
        market: str,
        symbol: str | None = None,
        limit: int = 20,
        now: datetime | None = None,
    ) -> list[KnowledgeRecord]:
        now = now or datetime.now(timezone.utc)
        matches: list[KnowledgeRecord] = []
        for record in self._records:
            if record.market.upper() != market.upper():
                continue
            if _is_expired(record, now) or _not_yet_valid(record, now):
                continue
            if not _applies_to(record, symbol):
                continue
            matches.append(record)

        # Rules first, then highest-confidence lessons.
        matches.sort(key=lambda r: (r.kind.value != "rule", -r.confidence))
        return matches[:limit]
