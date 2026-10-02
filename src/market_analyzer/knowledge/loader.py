"""Load curated YAML knowledge files safely and validate them."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from market_analyzer.knowledge.sources import TrustedSources
from market_analyzer.models.knowledge import KnowledgeRecord

#: `data_sources/` holds source-allowlist config, which has its own schema.
#: It is loaded separately so the generic record loader never mis-parses it.
_NON_RECORD_DIRS = {"data_sources", "pending"}


def _safe_load(path: Path) -> Any:
    # safe_load never constructs arbitrary Python objects from the file.
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_file(path: Path) -> list[KnowledgeRecord]:
    """Load a YAML file containing one record or a list of records."""
    data = _safe_load(path)
    if data is None:
        return []
    if isinstance(data, dict):
        # Support both a bare record and a `records:` wrapper.
        if "records" in data and isinstance(data["records"], list):
            raw_records = data["records"]
        else:
            raw_records = [data]
    elif isinstance(data, list):
        raw_records = data
    else:
        raise ValueError(f"{path}: expected a mapping or list at the top level")

    records: list[KnowledgeRecord] = []
    for index, raw in enumerate(raw_records):
        try:
            records.append(KnowledgeRecord.model_validate(raw))
        except Exception as exc:  # noqa: BLE001 - report which record failed
            raise ValueError(f"{path}: record #{index} is invalid: {exc}") from exc
    return records


def load_directory(directory: Path) -> list[KnowledgeRecord]:
    records: list[KnowledgeRecord] = []
    if not directory.exists():
        return records
    for path in _iter_yaml(directory):
        if _is_non_record_file(directory, path):
            continue
        records.extend(load_file(path))
    return records


def load_pending_records(directory: Path) -> list[dict[str, Any]]:
    """Load all records from the pending/ directory (not validated as KnowledgeRecord)."""
    
    records: list[dict[str, Any]] = []
    pending_dir = directory / "pending"
    if not pending_dir.exists():
        return records
    for path in sorted(pending_dir.rglob("*.yaml")):
        data = _safe_load(path)
        if data is None:
            continue
        if isinstance(data, dict):
            records.append(data)
        elif isinstance(data, list):
            records.extend(data)
    return records


def _iter_yaml(directory: Path):
    yield from sorted(directory.rglob("*.yaml"))
    yield from sorted(directory.rglob("*.yml"))


def _is_non_record_file(directory: Path, path: Path) -> bool:
    relative = path.relative_to(directory)
    return bool(relative.parts) and relative.parts[0] in _NON_RECORD_DIRS


def load_trusted_sources(directory: Path) -> TrustedSources | None:
    """Load the source allowlist, if one has been configured."""
    candidates = [
        directory / "data_sources" / "trusted_sources.yaml",
        directory / "data_sources" / "trusted_sources.yml",
    ]
    for path in candidates:
        if path.exists():
            return TrustedSources.model_validate(_safe_load(path) or {})
    return None
