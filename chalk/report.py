"""Evaluation report — the December evidence artifact (PRD sections 6.7
and 15): files processed, consistency-check catches, error rate by
format, rollovers, and cost per content type, all computed from
eval-log.json. Metadata only; the log never holds course or student
content, so neither does this report.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from pathlib import Path
from typing import Any

from chalk.archiving import archive_before_write
from chalk.metrics import read_events
from chalk.project import ProjectPaths

_FORMAT_BY_SUFFIX = {".docx": "word", ".md": "markdown"}


def render_evaluation_report(events: list[dict[str, Any]], *, project_name: str, generated_on: dt.date) -> str:
    sections = [
        f"# Evaluation report — {project_name}\n\n"
        f"Generated {generated_on.isoformat()} from eval-log.json ({len(events)} events). "
        "Metadata only — no course or student content is logged.",
        _files_section(events),
        _consistency_section(events),
        _rollover_section(events),
        _generation_section(events),
    ]
    return "\n\n".join(sections) + "\n"


def write_evaluation_report(paths: ProjectPaths, *, generated_on: dt.date | None = None) -> Path:
    output_path = paths.outputs_dir / "evaluation-report.md"
    text = render_evaluation_report(
        read_events(paths.eval_log), project_name=paths.root.name, generated_on=generated_on or dt.date.today()
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    archive_before_write(output_path, eval_log_path=paths.eval_log)
    output_path.write_text(text, encoding="utf-8")
    return output_path


def _of_type(events: list[dict[str, Any]], event_type: str) -> list[dict[str, Any]]:
    return [e for e in events if e.get("event_type") == event_type]


def _when(event: dict[str, Any]) -> str:
    return event.get("timestamp", "")[:16].replace("T", " ")


def _files_section(events: list[dict[str, Any]]) -> str:
    extracted: dict[str, int] = defaultdict(int)
    failed: dict[str, int] = defaultdict(int)
    for event in _of_type(events, "extraction"):
        extracted[event.get("source_format", "unknown")] += 1
    for event in _of_type(events, "extraction_error"):
        failed[_FORMAT_BY_SUFFIX.get(Path(event.get("filename", "")).suffix.lower(), "other")] += 1

    lines = ["## Files processed", ""]
    formats = sorted(set(extracted) | set(failed))
    if not formats:
        return "\n".join([*lines, "_No extractions yet._"])
    lines += ["| Format | Extracted | Errors | Error rate |", "| --- | --- | --- | --- |"]
    for fmt in formats:
        attempts = extracted[fmt] + failed[fmt]
        lines.append(f"| {fmt} | {extracted[fmt]} | {failed[fmt]} | {failed[fmt] / attempts:.0%} |")
    errors = _of_type(events, "extraction_error")
    if errors:
        lines += ["", "Errors:", *(f"- {_when(e)} — {e.get('filename', '?')}: {e.get('error_type', '?')}" for e in errors)]
    return "\n".join(lines)


def _consistency_section(events: list[dict[str, Any]]) -> str:
    checks = _of_type(events, "consistency_check")
    caught = [e for e in checks if not e.get("passed", True)]
    overrides = _of_type(events, "consistency_check_override")
    lines = [
        "## Term / Week-1 consistency check",
        "",
        f"- Checks run: {len(checks)}",
        f"- Mismatches caught: {len(caught)}",
        f"- Continued anyway (override logged): {len(overrides)}",
    ]
    lines += [f"- {_when(e)} — caught on term “{e.get('term', '?')}”" for e in caught]
    return "\n".join(lines)


def _rollover_section(events: list[dict[str, Any]]) -> str:
    rollovers = _of_type(events, "rollover")
    lines = ["## Rollovers", ""]
    if not rollovers:
        return "\n".join([*lines, "_No rollovers yet._"])
    lines += ["| When | From | To | Weeks | Flags for review |", "| --- | --- | --- | --- | --- |"]
    lines += [
        f"| {_when(e)} | {e.get('source_term', '')} | {e.get('target_term', '')} | "
        f"{e.get('source_duration_weeks')} → {e.get('target_duration_weeks')} | {e.get('flag_count', 0)} |"
        for e in rollovers
    ]
    return "\n".join(lines)


def _generation_section(events: list[dict[str, Any]]) -> str:
    generations = _of_type(events, "generation")
    lines = ["## Generation cost by content type", ""]
    if not generations:
        return "\n".join([*lines, "_No content generated yet._"])

    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in generations:
        by_type[event.get("content_type", "unknown")].append(event)
    lines += [
        "| Content type | Calls | Input tokens | Output tokens | Total cost | Avg cost / call |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for content_type, calls in sorted(by_type.items()):
        total = sum(e.get("cost_usd") or 0.0 for e in calls)
        lines.append(
            f"| {content_type} | {len(calls)} | {sum(e.get('input_tokens', 0) for e in calls):,} | "
            f"{sum(e.get('output_tokens', 0) for e in calls):,} | ${total:.4f} | ${total / len(calls):.4f} |"
        )
    grand_total = sum(e.get("cost_usd") or 0.0 for e in generations)
    lines += ["", f"**Total: {len(generations)} calls, ${grand_total:.4f}.**"]
    unpriced = sum(1 for e in generations if e.get("cost_usd") is None)
    if unpriced:
        lines.append(f"{unpriced} call(s) used a model with no cost rate in config.json and are counted as $0.")
    models = sorted({e.get("model", "?") for e in generations})
    lines.append(f"Models used: {', '.join(models)}.")
    return "\n".join(lines)
