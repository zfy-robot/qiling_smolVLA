"""Durable failure reporting for long-running dataset collection."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any


class CollectionFailureReporter:
    """Append failure events to JSONL and maintain an atomic summary file."""

    def __init__(self, jsonl_path: Path, summary_path: Path, *, resume: bool) -> None:
        self.jsonl_path = Path(jsonl_path)
        self.summary_path = Path(summary_path)
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self.summary_path.parent.mkdir(parents=True, exist_ok=True)
        if not resume:
            self.jsonl_path.write_text("", encoding="utf-8")
        self.events = self._read_existing_events()
        self._write_summary(completed=False, accepted_episodes=0, target_episodes=0, skipped_grid_cells=[])

    def _read_existing_events(self) -> list[dict[str, Any]]:
        if not self.jsonl_path.is_file():
            return []
        events: list[dict[str, Any]] = []
        for line_number, line in enumerate(self.jsonl_path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid collection failure JSONL at {self.jsonl_path}:{line_number}"
                ) from exc
            if not isinstance(event, dict):
                raise ValueError(f"Failure event must be an object: {self.jsonl_path}:{line_number}")
            events.append(event)
        return events

    def record(self, event: dict[str, Any]) -> None:
        payload = {
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            **event,
        }
        with self.jsonl_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self.events.append(payload)

    def finalize(
        self,
        *,
        completed: bool,
        accepted_episodes: int,
        target_episodes: int,
        skipped_grid_cells: list[dict[str, int]],
        hdf5_path: Path | None = None,
    ) -> None:
        self._write_summary(
            completed=completed,
            accepted_episodes=accepted_episodes,
            target_episodes=target_episodes,
            skipped_grid_cells=skipped_grid_cells,
            hdf5_path=hdf5_path,
        )

    def _write_summary(
        self,
        *,
        completed: bool,
        accepted_episodes: int,
        target_episodes: int,
        skipped_grid_cells: list[dict[str, int]],
        hdf5_path: Path | None = None,
    ) -> None:
        by_phase = Counter(str(event.get("phase_name", "unknown")) for event in self.events)
        by_type = Counter(str(event.get("failure_type", "unknown")) for event in self.events)
        by_diagnostic_cause = Counter(
            str(event.get("diagnostic_cause", "unknown")) for event in self.events
        )
        by_reason = Counter(str(event.get("reason", "unknown")) for event in self.events)
        summary = {
            "schema_version": 1,
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "completed": bool(completed),
            "accepted_episodes": int(accepted_episodes),
            "target_episodes": int(target_episodes),
            "failed_attempts": len(self.events),
            "skipped_grid_cells": list(skipped_grid_cells),
            "failures_by_phase": dict(sorted(by_phase.items())),
            "failures_by_type": dict(sorted(by_type.items())),
            "failures_by_diagnostic_cause": dict(sorted(by_diagnostic_cause.items())),
            "failures_by_reason": dict(sorted(by_reason.items())),
            "failure_log": str(self.jsonl_path.resolve()),
            "hdf5_path": None if hdf5_path is None else str(Path(hdf5_path).resolve()),
        }
        temporary = self.summary_path.with_name(f".{self.summary_path.name}.tmp")
        temporary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.summary_path)
