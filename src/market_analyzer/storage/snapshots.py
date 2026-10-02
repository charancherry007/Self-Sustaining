"""Write analysis snapshots as JSON, one file per run.

JSON (not YAML) because snapshots are machine-generated artefacts consumed by
the risk/strategy components and by diffing tools. Retrieval is by run_id.
"""

from __future__ import annotations

import json
from pathlib import Path

from market_analyzer.models.analysis import MarketAnalysis


class SnapshotStore:
    def __init__(self, directory: Path, retain_runs: int = 200) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.retain_runs = retain_runs

    def _path(self, run_id: str) -> Path:
        return self.directory / f"{run_id}.json"

    def save(self, analysis: MarketAnalysis) -> Path:
        path = self._path(analysis.run_id)
        payload = analysis.model_dump(mode="json")
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=False)
        self._prune()
        return path

    def load(self, run_id: str) -> MarketAnalysis | None:
        path = self._path(run_id)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return MarketAnalysis.model_validate(json.load(handle))

    def list_runs(self, limit: int = 20) -> list[str]:
        files = sorted(self.directory.glob("*.json"))
        return [f.stem for f in files[-limit:]]

    def _prune(self) -> None:
        files = sorted(self.directory.glob("*.json"))
        for stale in files[: max(0, len(files) - self.retain_runs)]:
            stale.unlink(missing_ok=True)
