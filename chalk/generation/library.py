"""Saved drafts (the Drafts tab): the generated files under outputs/,
found by the names `engine.output_path_for` gives them, with each one's
archived earlier versions counted.

Only files named the way Chalk saves them are listed (`week-3-quiz.md`,
`lab-3-rubric.md`), so an instructor's own files in those folders aren't
mistaken for drafts.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

from chalk.generation.specs import SPECS, ContentSpec
from chalk.project import ProjectPaths

_ARCHIVE_SUFFIX = r"-\d{8}-\d{6}"


@dataclass(frozen=True)
class SavedDraft:
    spec: ContentSpec
    path: Path
    week_number: int | None
    name: str
    saved_at: dt.datetime
    archived_versions: int

    @property
    def title(self) -> str:
        if self.week_number is not None:
            subject = f"Week {self.week_number}"
        else:
            subject = self.name.replace("-", " ").capitalize()  # the file name's slug, e.g. "Lab 3"
        return f"{subject} — {self.spec.label}"


def list_saved_drafts(paths: ProjectPaths) -> list[SavedDraft]:
    """Every saved draft, in content-type order (as on the Generate tab),
    then by week number or name."""
    drafts: list[SavedDraft] = []
    for spec in SPECS.values():
        folder = paths.outputs_dir / spec.output_subdir
        if not folder.is_dir():
            continue
        found = [d for p in folder.glob("*.md") if (d := _draft_for(spec, p)) is not None]
        drafts += sorted(found, key=lambda d: (d.week_number or 0, d.name))
    return drafts


def _draft_for(spec: ContentSpec, path: Path) -> SavedDraft | None:
    if spec.per_week:
        match = re.fullmatch(rf"week-(\d+)-{re.escape(spec.key)}", path.stem)
        if match is None:
            return None
        week_number, name = int(match.group(1)), path.stem
    else:
        match = re.fullmatch(rf"(.+)-{re.escape(spec.key)}", path.stem)
        if match is None:
            return None
        week_number, name = None, match.group(1)
    return SavedDraft(
        spec=spec,
        path=path,
        week_number=week_number,
        name=name,
        saved_at=dt.datetime.fromtimestamp(path.stat().st_mtime, dt.UTC).astimezone(),
        archived_versions=_count_archived(path),
    )


def _count_archived(path: Path) -> int:
    archive = path.parent / ".archive"
    if not archive.is_dir():
        return 0
    pattern = re.compile(re.escape(path.stem) + _ARCHIVE_SUFFIX + re.escape(path.suffix))
    return sum(1 for p in archive.iterdir() if pattern.fullmatch(p.name))
