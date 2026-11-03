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
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median
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
        "timestamp": dt.datetime.now(dt.UTC).isoformat(),
        **payload,
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def read_events(log_path: Path) -> list[dict[str, Any]]:
    """Read every event from the JSONL log, oldest first.

    Returns an empty list if the log doesn't exist yet — a fresh project
    has no eval-log.json until its first event, and that's not an error.
    A last line with no newline that doesn't parse is skipped: a
    background job (ui/background.py) may be partway through writing it.
    """
    if not log_path.exists():
        return []

    events: list[dict[str, Any]] = []
    with log_path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                if raw.endswith("\n"):
                    raise
    return events


def typical_output_tokens(log_path: Path, content_type: str, *, recent: int = 10) -> int | None:
    """The median reply length (output tokens) of this project's last
    `recent` generations of `content_type`, or None if there are none yet.
    The progress bar measures a streaming reply against it."""
    lengths = [
        event["output_tokens"]
        for event in read_events_by_type(log_path, "generation")
        if event.get("content_type") == content_type and event.get("output_tokens")
    ][-recent:]
    return int(median(lengths)) if lengths else None


def read_events_by_type(log_path: Path, event_type: EventType) -> list[dict[str, Any]]:
    """Convenience filter over read_events(), used by the Metrics tab and
    CLI `status` command to summarize one category at a time."""
    return [event for event in read_events(log_path) if event.get("event_type") == event_type]


@dataclass(frozen=True)
class MetricsSummary:
    """Aggregates over the whole log — what the Metrics tab, the UI footer,
    and CLI `status` report (PRD section 6.7)."""

    generation_counts: dict[str, int]
    total_cost_usd: float
    rollovers: list[dict[str, Any]]
    extraction_errors: list[dict[str, Any]]
    consistency_failures: int
    consistency_overrides: int


def summarize_events(events: list[dict[str, Any]]) -> MetricsSummary:
    """Totals over the eval log for the Metrics tab, the footer, and
    `toolkit.py status`."""
    def of_type(event_type: str) -> list[dict[str, Any]]:
        return [e for e in events if e.get("event_type") == event_type]

    generations = of_type("generation")
    return MetricsSummary(
        generation_counts=dict(Counter(e.get("content_type", "unknown") for e in generations)),
        total_cost_usd=sum(e.get("cost_usd") or 0.0 for e in generations),  # None = no known rate
        rollovers=of_type("rollover"),
        extraction_errors=of_type("extraction_error"),
        consistency_failures=sum(1 for e in of_type("consistency_check") if not e.get("passed", True)),
        consistency_overrides=len(of_type("consistency_check_override")),
    )


@dataclass(frozen=True)
class MonthlyCost:
    """One calendar month of generation spend — the Metrics tab's
    this-month figure and cost-by-month chart, and the report's monthly table."""

    month: str  # "YYYY-MM"
    generations: int
    cost_usd: float
    cost_by_type: dict[str, float]

    @property
    def avg_cost_usd(self) -> float:
        return self.cost_usd / self.generations if self.generations else 0.0


def month_key(when: dt.date) -> str:
    return f"{when.year:04d}-{when.month:02d}"


def previous_month_key(when: dt.date) -> str:
    return month_key(when.replace(day=1) - dt.timedelta(days=1))


def monthly_costs(events: list[dict[str, Any]], *, tz: dt.tzinfo | None = None) -> list[MonthlyCost]:
    """Generation cost per calendar month, oldest first, with quiet months
    in between included at $0 so the chart has no gaps.

    Months are in this computer's time zone (or `tz`), not the log's UTC,
    so a generation late on the 31st counts toward the month the user saw.
    """
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if event.get("event_type") == "generation" and event.get("timestamp"):
            local = dt.datetime.fromisoformat(event["timestamp"]).astimezone(tz)
            by_month[month_key(local)].append(event)
    if not by_month:
        return []
    return [_month_cost(month, by_month.get(month, [])) for month in _months_between(min(by_month), max(by_month))]


def _months_between(first: str, last: str) -> list[str]:
    year, month = map(int, first.split("-"))
    months = []
    while (key := f"{year:04d}-{month:02d}") <= last:
        months.append(key)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def _month_cost(month: str, generations: list[dict[str, Any]]) -> MonthlyCost:
    cost_by_type: dict[str, float] = defaultdict(float)
    for event in generations:
        cost_by_type[event.get("content_type", "unknown")] += event.get("cost_usd") or 0.0  # None = no known rate
    return MonthlyCost(month, len(generations), sum(cost_by_type.values()), dict(cost_by_type))
