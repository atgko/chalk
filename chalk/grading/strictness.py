"""How strict a grading is (sponsor meeting, Oct 28: "let the grader
choose how strict the grading and feedback are").

Strictness changes both the suggested scores and the feedback's tone,
since a stricter reading of the rubric that kept a gentle tone (or the
reverse) would read as inconsistent. It never changes what the rubric
asks for or what a criterion is worth, and never lets a deduction rest
on a requirement the rubric doesn't state. Standard adds nothing, so a
standard grading is exactly what it was before this setting existed,
and the consistency test (BACKLOG.md) measures each level separately.
"""

from __future__ import annotations

LENIENT = "lenient"
STANDARD = "standard"
STRICT = "strict"
STRICTNESS_LEVELS = (LENIENT, STANDARD, STRICT)

STRICTNESS_LABELS = {
    LENIENT: "Lenient",
    STANDARD: "Standard",
    STRICT: "Strict",
}

_SHARED = (
    "Grade only against the rubric: never deduct points for requirements the rubric doesn't state, "
    "and never change what a criterion is worth."
)
_INSTRUCTIONS = {
    STANDARD: "",
    LENIENT: (
        "GRADING STRICTNESS: lenient. Give the student the benefit of the doubt: award partial credit "
        "for a reasonable attempt at a requirement, and full credit when the requirement is met in "
        "substance even if it's brief or imperfectly worded. Write the feedback in an encouraging "
        f"tone, leading with what went well. {_SHARED}"
    ),
    STRICT: (
        "GRADING STRICTNESS: strict. Award credit only for what the submission clearly shows: give "
        "partial credit only for parts of a requirement that are fully demonstrated, and full credit "
        "only when every part is met with specific supporting detail. Write the feedback in a direct, "
        f"professional tone that names each gap precisely. {_SHARED}"
    ),
}


def strictness_instructions(level: str) -> str:
    """The instruction sent with a grading at `level`; empty for Standard."""
    if level not in _INSTRUCTIONS:
        raise ValueError(f"Unknown grading strictness '{level}'. Use one of: {', '.join(STRICTNESS_LEVELS)}.")
    return _INSTRUCTIONS[level]


def with_strictness(instructions: str, level: str) -> str:
    """The grader's instructions with the strictness instruction first."""
    return "\n\n".join(part for part in (strictness_instructions(level), instructions.strip()) if part)
