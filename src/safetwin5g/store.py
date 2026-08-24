"""Append-only JSONL persistence for intervention records."""

from __future__ import annotations

import json
from pathlib import Path

from .contracts import InterventionRecord


class InterventionStore:
    def __init__(self, path: Path):
        self.path = path

    def append(self, record: InterventionRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":")))
            handle.write("\n")

    def load(self) -> list[InterventionRecord]:
        records: list[InterventionRecord] = []
        if not self.path.exists():
            return records
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, start=1):
                if not raw.strip():
                    continue
                try:
                    payload = json.loads(raw)
                    records.append(InterventionRecord.from_dict(payload))
                except (json.JSONDecodeError, ValueError) as exc:
                    raise ValueError(f"invalid intervention at line {line_number}: {exc}") from exc
        return records
