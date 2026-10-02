"""Append-only writers for trade cases and analysis runs.

The LLM never writes to approved knowledge directly. It can only append to
`knowledge/pending/`, which a human later reviews and promotes.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class CaseWriter:
    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "cases.jsonl"

    def append(self, case: dict[str, Any]) -> None:
        record = {"ts": datetime.now(timezone.utc).isoformat(), **case}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str, separators=(",", ":")) + "\n")

    def read_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        out: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return out[-limit:]


class PendingLessonWriter:
    """Writes unreviewed lessons as individual YAML files for human review."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def write(self, lesson: dict[str, Any]) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        slug = str(lesson.get("title", "lesson")).lower().replace(" ", "-")[:48]
        path = self.directory / f"{stamp}-{slug}.yaml"
        import yaml

        with path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(lesson, handle, sort_keys=False, allow_unicode=True)
        return path

    def append(self, record: dict[str, Any]) -> Path:
        """Append a generic record (used for risk rule proposals)."""
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        kind = record.get("kind", "proposal")
        path = self.directory / f"{stamp}-{kind}.yaml"
        import yaml

        with path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(record, handle, sort_keys=False, allow_unicode=True)
        return path
