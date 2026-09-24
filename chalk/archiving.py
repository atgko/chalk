"""Archive-before-overwrite (F-06, extended by DECISIONS.md to cover
course.json in addition to outputs/*).

Before any file write that would overwrite an existing file, the existing
version is moved into a sibling `.archive/` directory with a timestamp
suffix. This is the one shared mechanism every output-writing feature
(rollover, generation, course.json re-save) calls into, rather than each
one growing its own archiving code path (PLAN.md Risk #5).

Pulled forward from Milestone 5 (chalk.project) because rollover's
"write only after Confirm" flow needs it now.
"""

from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

from chalk import metrics


def archive_before_write(
    path: Path, *, eval_log_path: Path | None = None, now: dt.datetime | None = None
) -> Path | None:
    """If `path` already exists, move it into `path.parent/.archive/` with
    a timestamp suffix before the caller overwrites it.

    Returns the archived file's new path, or None if there was nothing to
    archive (a brand-new file — not an error). If `eval_log_path` is given
    and a file was actually archived, logs an `archive` event
    (PRD section 6.7).
    """
    if not path.exists():
        return None

    timestamp = (now or dt.datetime.now()).strftime("%Y%m%d-%H%M%S")
    archive_dir = path.parent / ".archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archived_path = archive_dir / f"{path.stem}-{timestamp}{path.suffix}"
    shutil.move(str(path), str(archived_path))

    if eval_log_path is not None:
        metrics.append_event(
            eval_log_path,
            "archive",
            {"original_path": str(path), "archived_path": str(archived_path)},
        )

    return archived_path
