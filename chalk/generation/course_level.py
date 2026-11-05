"""Course level and AI-use components for generated content (sponsor
meeting, Oct 15: "make it undergrad to grad difficulty, include AI
components for learning").

The level shapes how demanding a draft is. It defaults to what the
course number says under the University of Utah's numbering (1000-2999
lower-division, 3000-5999 upper-division, 6000 and up graduate), and the
instructor can change it on the Generate tab or with `--level`.

Both reach the prompt through optional template variables,
`{course_level_guidance}` and `{ai_component_guidance}`. A project whose
templates predate them still gets the guidance: build_prompt adds it at
the end of the prompt instead, since an instructor's template is never
silently replaced (chalk/generation/prompts.py).
"""

from __future__ import annotations

import re

from chalk.errors import GenerationError

LOWER_DIVISION = "lower-division"
UPPER_DIVISION = "upper-division"
GRADUATE = "graduate"
COURSE_LEVELS = (LOWER_DIVISION, UPPER_DIVISION, GRADUATE)

LEVEL_LABELS = {
    LOWER_DIVISION: "Undergraduate, lower-division (1000–2000 level)",
    UPPER_DIVISION: "Undergraduate, upper-division (3000–5000 level)",
    GRADUATE: "Graduate (6000 level and up)",
}

_GUIDANCE = {
    LOWER_DIVISION: (
        "COURSE LEVEL: lower-division undergraduate. Write for students meeting this subject "
        "for the first time: define key terms, break multi-step work into smaller guided steps, "
        "and focus on understanding and applying core concepts with clear examples."
    ),
    UPPER_DIVISION: (
        "COURSE LEVEL: upper-division undergraduate. Assume students know the field's "
        "foundations: focus on applying and analyzing concepts in realistic situations, and ask "
        "them to solve problems with some independence while giving clear direction."
    ),
    GRADUATE: (
        "COURSE LEVEL: graduate. Assume professional or disciplinary background: focus on "
        "analysis, evaluation, and synthesis, ask students to justify their decisions and weigh "
        "trade-offs, engage with real-world complexity, and keep scaffolding to a minimum."
    ),
}

# The AI-use task gets a section of its own with this heading, so students
# and the instructor can find it (sponsor meeting, Oct 28: it wasn't clear
# where the task had ended up). Exports highlight it.
AI_TASK_HEADING = "AI-USE TASK"

AI_COMPONENT_GUIDANCE = (
    "AI-USE COMPONENT: include one task in which students use a generative AI tool as part of "
    "their learning, for example to brainstorm options, get feedback on a draft, or critique an "
    "AI-generated answer. Ask students to document how they used it (what they asked, what they "
    "kept or changed, and why) and to reflect on where the tool was wrong or limited. The "
    "assignment's learning goal must still be shown through the student's own work. Do not name "
    "a specific AI product unless the instructor did. "
    f"Give this task its own section, headed exactly `## {AI_TASK_HEADING}`, after MORE DETAILS "
    "and before DELIVERABLES, and start the section with the line "
    "`> This task asks you to use a generative AI tool.` Put all of the AI-use instructions "
    "there, not inside another section. In TASKS IN BRIEF, end that task's line with "
    "\"(AI-use task)\"."
)
_AI_TASK_HEADING_RE = re.compile(r"^#{1,3}\s*AI[- ]USE TASK\b", re.IGNORECASE | re.MULTILINE)

_COURSE_NUMBER_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")  # "IS 6640" or "OSC6660"


def has_ai_task_section(text: str) -> bool:
    """True when a draft has the AI-use task's own section."""
    return bool(_AI_TASK_HEADING_RE.search(text))


def level_from_course_number(course_number: str) -> str | None:
    """The level a U of U course number implies ("IS 6640" → graduate),
    or None when there's no four-digit number to go by."""
    match = _COURSE_NUMBER_RE.search(course_number or "")
    if match is None:
        return None
    number = int(match.group(1))
    if number >= 6000:
        return GRADUATE
    return UPPER_DIVISION if number >= 3000 else LOWER_DIVISION


def level_guidance(level: str | None) -> str:
    """The prompt text for `level`; empty when no level was chosen."""
    if level is None:
        return ""
    if level not in _GUIDANCE:
        raise GenerationError(f"Course level must be one of: {', '.join(COURSE_LEVELS)}.")
    return _GUIDANCE[level]
