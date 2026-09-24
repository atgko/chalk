"""Append-only metrics log (eval-log.json) — one JSON object per line
(JSON Lines), per DECISIONS.md ("append-only" taken literally: a true
JSON array can't be appended to without a read-modify-write of the whole
file on every event).

Every operation Chalk performs logs an event here. The *content* of
generated files is never logged — only metadata (counts, costs, filenames,
timestamps) — per PRD section 6.7: "No usage data leaves the machine."
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Literal

EventType = Literal[
    "extraction",
    "extraction_error",
    "consistency_check",
    "consistency_check_override",
    "rollover",
    "generation",
    "archive",
    "source_indexed",
]


def append_event(log_path: Path, event_type: EventType, payload: dict[str, Any]) -> None:
    """Append one event to the JSONL log at `log_path`.

    Creates the file (and its parent directory) if this is the first
    event for a fresh project. `payload` is merged into the event
    alongside `event_type` and a UTC `timestamp` — it should hold only
    metadata, never generated-file content.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "event_type": event_type,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        **payload,
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def read_events(log_path: Path) -> list[dict[str, Any]]:
    """Read every event from the JSONL log, oldest first.

    Returns an empty list if the log doesn't exist yet — a fresh project
    has no eval-log.json until its first event, and that's not an error.
    """
    if not log_path.exists():
        return []

    events: list[dict[str, Any]] = []
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def read_events_by_type(log_path: Path, event_type: EventType) -> list[dict[str, Any]]:
    """Convenience filter over read_events(), used by the Metrics tab and
    CLI `status` command to summarize one category at a time."""
    return [event for event in read_events(log_path) if event.get("event_type") == event_type]
