"""Optional educational frameworks for instructor-grounded assignments.

The instructor picks one main framework under Settings → More settings;
every assignment Chalk drafts or improves on this computer uses it. The
choice is saved next to the courses (Documents/Chalk Courses), like the
links in chalk/links.py.
"""

from __future__ import annotations

import json
from pathlib import Path

from chalk.errors import ChalkError, GenerationError
from chalk.locations import default_projects_dir

FRAMEWORK_LABELS = {
    "none": "None",
    "backward_design": "Backward Design (UbD)",
    "fink": "Fink's Taxonomy of Significant Learning",
    "constructive_alignment": "Constructive Alignment",
}
FRAMEWORKS = tuple(FRAMEWORK_LABELS)
DEFAULT_FRAMEWORK = "backward_design"
SETTINGS_FILE_NAME = "Chalk framework.json"


def settings_path() -> Path:
    return default_projects_dir() / SETTINGS_FILE_NAME


def load_main_framework(path: Path | None = None) -> str:
    """The framework chosen in Settings; a missing, damaged, or unknown
    choice means the default."""
    try:
        saved = json.loads((path or settings_path()).read_text(encoding="utf-8")).get("framework")
    except (OSError, ValueError, AttributeError):
        return DEFAULT_FRAMEWORK
    return saved if saved in FRAMEWORKS else DEFAULT_FRAMEWORK


def save_main_framework(framework: str, path: Path | None = None) -> None:
    """Save the main framework for every course on this computer."""
    if framework not in FRAMEWORKS:
        raise GenerationError("Choose a valid educational framework.")
    path = path or settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"framework": framework}, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise ChalkError(
            f"Chalk couldn't save the framework choice in {path.parent}. "
            "Check that the folder exists and isn't read-only, then try again."
        ) from exc


def framework_guidance(framework: str, evidence: str = "") -> str:
    """Provide educational design guidance without inventing requirements."""
    if framework not in FRAMEWORKS:
        raise GenerationError("Choose a valid educational framework.")

    if framework == "none":
        return ""

    shared = (
        "EDUCATIONAL DESIGN GUIDANCE (internal; do not print this heading):\n"
        "Instructor learning goals, requirements, and selected course materials "
        "remain the primary authority. Align the assignment with those inputs. "
        "Do not invent deliverables, grading criteria, deadlines, point values, "
        "or additional student requirements. Do not name the framework in the "
        "student-facing assignment unless requested. "
    )

    approaches = {
        "backward_design": (
            "Use Backward Design: first identify desired learning results; "
            "then identify acceptable evidence of learning; finally organize "
            "assignment tasks around those outcomes and evidence. "
            "Keep all three aligned with instructor instructions."
        ),
        "fink": (
            "Use Fink's Significant Learning framework where appropriate: "
            "foundational knowledge, application, integration, human dimension, "
            "caring, and learning how to learn. Select only categories supported "
            "by the instructor's goals. Do not force all six categories."
        ),
        "constructive_alignment": (
            "Use Constructive Alignment: connect intended learning outcomes, "
            "student learning activities, and assessment evidence. "
            "Ensure the tasks demonstrate the skills described in the "
            "instructor's learning outcomes."
        ),
    }

    result = shared + approaches[framework]

    if evidence.strip():
        result += (
            "\nINSTRUCTOR-PROVIDED EVIDENCE OF LEARNING: "
            + evidence.strip()
            + "\nUse this evidence to guide alignment without inventing "
            "submission formats, deadlines, or point values."
        )

    return result
