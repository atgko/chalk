"""Syllabus extraction (F-01): public entry point.

`extract_course()` dispatches to the Word or markdown extractor by file
extension and always runs the term/Week-1 consistency check on the result
(PRD section 6.1) — extraction and the consistency check are never
performed separately, so no caller can accidentally skip the check.
"""

from __future__ import annotations

from pathlib import Path

from chalk import metrics
from chalk.errors import ExtractionError
from chalk.extractors.consistency import ConsistencyResult, check_term_consistency
from chalk.extractors.docx_extractor import extract_course_data as _extract_docx
from chalk.extractors.markdown_extractor import extract_course_data as _extract_markdown
from chalk.models import CourseData

_EXTRACTORS_BY_SUFFIX = {
    ".docx": _extract_docx,
    ".md": _extract_markdown,
}


def extract_course(path, eval_log_path=None) -> tuple[CourseData, ConsistencyResult]:
    """Extract course.json from a syllabus file and run the consistency
    check.

    Dispatches on file extension (.docx -> Word path, .md -> markdown
    path) and raises ExtractionError for anything else.

    If `eval_log_path` is given, the consistency check's pass/fail result
    is logged automatically as a `consistency_check` event (PRD section
    6.7) — this happens unconditionally, every run, unlike the
    `consistency_check_override` event (see log_consistency_override),
    which only happens if the instructor proceeds past a failed check.
    """
    path = Path(path)
    extractor = _EXTRACTORS_BY_SUFFIX.get(path.suffix.lower())
    if extractor is None:
        raise ExtractionError(
            f"Unsupported file type '{path.suffix}'. Upload a .docx or .md syllabus."
        )

    course_data = extractor(path)
    consistency_result = check_term_consistency(course_data)

    if eval_log_path is not None:
        metrics.append_event(
            eval_log_path,
            "consistency_check",
            {
                "passed": consistency_result.passed,
                "term": consistency_result.term,
                "detail": consistency_result.detail,
            },
        )

    return course_data, consistency_result


def log_consistency_override(eval_log_path, consistency_result: ConsistencyResult) -> None:
    """Log that the instructor chose "Continue anyway" past a failed
    consistency check.

    Called by the CLI/UI layer (Milestone 5/6) — never automatically, and
    only for a check that actually failed. This is the flagship piece of
    evidence for the December presentation that the named test case
    (PRD section 6.1) fires correctly even when the instructor overrides it.
    """
    metrics.append_event(
        eval_log_path,
        "consistency_check_override",
        {
            "term": consistency_result.term,
            "detail": consistency_result.detail,
        },
    )
