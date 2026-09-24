"""Course project workspace (F-06): directory layout, `init`, `add`,
course.json load/save, and `status`.

A course project is a plain directory (PRD section 5.1). `ProjectPaths`
is the one place that knows where each file in it lives, so neither the
CLI nor the Streamlit UI ever builds a project path by hand.

Feature workflows that span several of these pieces (extract -> review ->
save, rollover preview -> confirm) live in chalk.pipeline.
"""

from __future__ import annotations

import datetime as dt
import shutil
from dataclasses import dataclass
from pathlib import Path

from chalk import branding, metrics
from chalk.archiving import archive_before_write
from chalk.errors import ProjectError
from chalk.models import CourseData, SourceMaterialRef

RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"

SOURCE_SUFFIXES = (".pdf", ".docx", ".md", ".txt")
OUTPUT_SUBDIRS = ("quizzes", "discussions", "rubrics", "summaries", "slides")

_PROJECT_GITIGNORE = ".env\n"


@dataclass(frozen=True)
class ProjectPaths:
    root: Path

    @property
    def course_json(self) -> Path:
        return self.root / "course.json"

    @property
    def config_json(self) -> Path:
        return self.root / "config.json"

    @property
    def env(self) -> Path:
        return self.root / ".env"

    @property
    def source_dir(self) -> Path:
        return self.root / "source"

    @property
    def outputs_dir(self) -> Path:
        return self.root / "outputs"

    @property
    def prompts_dir(self) -> Path:
        return self.root / "prompts"

    @property
    def calendars_json(self) -> Path:
        return self.root / "data" / "calendars.json"

    @property
    def eval_log(self) -> Path:
        return self.root / "eval-log.json"

    @property
    def readme(self) -> Path:
        return self.root / "README.md"

    @property
    def canvas_html(self) -> Path:
        return self.outputs_dir / "canvas.html"

    @property
    def course_brief(self) -> Path:
        return self.outputs_dir / "course-brief.md"

    def syllabus_output(self, source_format: str) -> Path:
        suffix = ".docx" if source_format == "word" else ".md"
        return self.outputs_dir / f"syllabus{suffix}"


@dataclass(frozen=True)
class ProjectStatus:
    name: str
    course: CourseData | None
    source_files: list[str]
    output_counts: dict[str, int]
    total_cost_usd: float
    rollover_count: int
    extraction_error_count: int
    consistency_failures: int


# ---- init / open ---------------------------------------------------------


def init_project(parent_dir, name: str, *, resources_dir: Path = RESOURCES_DIR) -> ProjectPaths:
    """Create a fresh course project at `parent_dir/name` with the full
    section 5.1 layout, seeded from the toolkit's bundled resources."""
    name = name.strip()
    if not name or any(sep in name for sep in ("/", "\\")) or name in (".", ".."):
        raise ProjectError(f"'{name}' isn't a usable project name. Use something like IS-6640-Fall-2027.")

    paths = ProjectPaths(Path(parent_dir) / name)
    if paths.root.exists() and any(paths.root.iterdir()):
        raise ProjectError(f"A folder named '{name}' already exists here and isn't empty. Pick another name.")

    for directory in (paths.source_dir, paths.prompts_dir, paths.calendars_json.parent):
        directory.mkdir(parents=True, exist_ok=True)
    for subdir in OUTPUT_SUBDIRS:
        (paths.outputs_dir / subdir).mkdir(parents=True, exist_ok=True)

    shutil.copyfile(resources_dir / "config.json", paths.config_json)
    shutil.copyfile(resources_dir / "data" / "calendars.json", paths.calendars_json)
    for prompt in sorted((resources_dir / "prompts").glob("*.txt")):
        shutil.copyfile(prompt, paths.prompts_dir / prompt.name)

    (paths.root / ".gitignore").write_text(_PROJECT_GITIGNORE, encoding="utf-8")
    paths.readme.write_text(_project_readme(name), encoding="utf-8")
    return paths


def open_project(root) -> ProjectPaths:
    """Return ProjectPaths for an existing project, or raise ProjectError
    if `root` doesn't look like one (no config.json)."""
    paths = ProjectPaths(Path(root))
    if not paths.config_json.is_file():
        raise ProjectError(
            f"'{paths.root}' isn't a {branding.PROJECT_NAME} course project (no config.json). "
            "Create one with `python toolkit.py init --name <course>`, or point at an existing project folder."
        )
    return paths


# ---- course.json -----------------------------------------------------------


def load_course(paths: ProjectPaths) -> CourseData | None:
    """Load course.json, or None if nothing has been extracted yet."""
    if not paths.course_json.exists():
        return None
    return CourseData.model_validate_json(paths.course_json.read_text(encoding="utf-8"))


def require_course(paths: ProjectPaths) -> CourseData:
    course_data = load_course(paths)
    if course_data is None:
        raise ProjectError("Upload and extract a syllabus first — this project has no course.json yet.")
    return course_data


def save_course(paths: ProjectPaths, course_data: CourseData) -> Path:
    """Write course.json, archiving the previous version first (DECISIONS:
    course.json re-saves are archived just like outputs/)."""
    archive_before_write(paths.course_json, eval_log_path=paths.eval_log)
    paths.course_json.write_text(course_data.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return paths.course_json


# ---- add -------------------------------------------------------------------


def add_source(paths: ProjectPaths, file_path, *, now: dt.datetime | None = None) -> Path:
    """Copy a source-material file into source/ and index it (PRD `add`).

    Re-adding a file with the same name archives the old copy. If
    course.json exists, its source_materials list is updated too.
    """
    file_path = Path(file_path)
    if file_path.suffix.lower() not in SOURCE_SUFFIXES:
        raise ProjectError(
            f"'{file_path.name}' can't be added. Supported source files: "
            + ", ".join(SOURCE_SUFFIXES)
            + "."
        )
    if not file_path.is_file():
        raise ProjectError(f"Couldn't find '{file_path}'. Check the path and try again.")

    destination = copy_into_source(paths, file_path)

    course_data = load_course(paths)
    if course_data is not None:
        ref = SourceMaterialRef(filename=destination.name, added_at=now or dt.datetime.now(dt.timezone.utc))
        kept = [m for m in course_data.source_materials if m.filename != destination.name]
        save_course(paths, course_data.model_copy(update={"source_materials": [*kept, ref]}))

    metrics.append_event(
        paths.eval_log,
        "source_indexed",
        {"filename": destination.name, "source_count": len(list_source_files(paths))},
    )
    return destination


def copy_into_source(paths: ProjectPaths, file_path: Path) -> Path:
    """Copy `file_path` into source/ (archiving a same-named older copy).
    A file already inside source/ is left where it is."""
    destination = paths.source_dir / file_path.name
    if file_path.resolve() == destination.resolve():
        return destination
    paths.source_dir.mkdir(parents=True, exist_ok=True)
    archive_before_write(destination, eval_log_path=paths.eval_log)
    shutil.copyfile(file_path, destination)
    return destination


def list_source_files(paths: ProjectPaths) -> list[str]:
    if not paths.source_dir.exists():
        return []
    return sorted(p.name for p in paths.source_dir.iterdir() if p.is_file())


# ---- status ----------------------------------------------------------------


def project_status(paths: ProjectPaths) -> ProjectStatus:
    """Summarize project state for `toolkit.py status` and the UI footer."""
    events = metrics.read_events(paths.eval_log)
    return ProjectStatus(
        name=paths.root.name,
        course=load_course(paths),
        source_files=list_source_files(paths),
        output_counts=_count_outputs(paths),
        total_cost_usd=sum(e.get("cost_usd", 0.0) for e in events if e["event_type"] == "generation"),
        rollover_count=sum(1 for e in events if e["event_type"] == "rollover"),
        extraction_error_count=sum(1 for e in events if e["event_type"] == "extraction_error"),
        consistency_failures=sum(
            1 for e in events if e["event_type"] == "consistency_check" and not e.get("passed", True)
        ),
    )


def _count_outputs(paths: ProjectPaths) -> dict[str, int]:
    counts = {"top-level": 0, **{subdir: 0 for subdir in OUTPUT_SUBDIRS}}
    if not paths.outputs_dir.exists():
        return counts
    for entry in paths.outputs_dir.iterdir():
        if entry.is_file():
            counts["top-level"] += 1
        elif entry.name in OUTPUT_SUBDIRS:
            counts[entry.name] = sum(1 for p in entry.iterdir() if p.is_file())
    return counts


def _project_readme(name: str) -> str:
    return (
        f"# {name}\n\n"
        f"A {branding.PROJECT_NAME} course project.\n\n"
        "- `course.json` — the structured course; every output is built from it\n"
        "- `source/` — your syllabus and any source materials you've added\n"
        "- `outputs/` — updated syllabus, Canvas HTML, course brief, generated content "
        "(previous versions are kept in `outputs/.archive/`)\n"
        "- `prompts/` — editable prompt templates\n"
        "- `data/calendars.json` — academic calendar data\n"
        "- `eval-log.json` — local metrics log (never leaves this machine)\n"
        "- `.env` — your LLM provider credentials (never commit this file)\n"
    )
