"""Append-only JSONL logger for operational events.

JSONL is chosen over YAML because events are appended constantly and must
never require a full rewrite. Consumers can `jq` it or replay it line by line.
Secrets are never logged: only symbols, ids, counts, and durations.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class JsonlEventLogger:
    def __init__(self, directory: Path, level: str = "info") -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "events.jsonl"
        self.level = level
        self._lock = threading.Lock()
        self._loggers: dict[str, Any] = {}

    def _emit(self, level: str, event: str, **fields: Any) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event": event,
            "pid": os.getpid(),
            **fields,
        }
        line = json.dumps(record, default=str, separators=(",", ":"))
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def debug(self, event: str, **fields: Any) -> None:
        if self.level == "debug":
            self._emit("debug", event, **fields)

    def info(self, event: str, **fields: Any) -> None:
        self._emit("info", event, **fields)

    def warning(self, event: str, **fields: Any) -> None:
        self._emit("warning", event, **fields)

    def error(self, event: str, **fields: Any) -> None:
        self._emit("error", event, **fields)

    def read_events(self, event: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Read back recent events. Used by the MCP `query_operational_logs` tool."""
        if not self.path.exists():
            return []
        out: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event and record.get("event") != event:
                    continue
                out.append(record)
        return out[-limit:]
