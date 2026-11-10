"""Instructor-grounded assignment guidance and conservative advisory checks.

Checks flag potentially unsupported requirements; they do not silently rewrite
faculty-facing material. A single bounded LLM revision may address issues.
"""
from __future__ import annotations

import re


def _instructor_text(request) -> str:
    return "\n".join(str(getattr(request, field, "") or "") for field in (
        "assignment_description", "assignment_requirements", "assignment_scenario",
        "assignment_deliverables", "assignment_format", "assignment_evaluation",
        "assignment_submission", "learning_evidence",
    ))


def assignment_quality_guidance(request) -> str:
    if request.content_type != "assignment":
        return ""
    rules = [
        "FINAL INSTRUCTOR-GROUNDED ASSIGNMENT CONTRACT:",
        "Write directions to students, NOT an example solution or model answer.",
        ("Instructor inputs are authoritative. Course sources support subject matter, "
        "but examples in sources are not automatically mandatory deliverables."),
        ("Preserve the instructor's exact goal, scenario, constraints, assessment "
        "expectations and explicitly requested deliverables."),
        ("Do not invent facts about an existing system, employee count, equipment, "
        "problems, budgets, deadlines or assessment criteria."),
        ("If no existing configuration is supplied, ask students to identify "
        "requirements or needed information; do not claim one exists."),
        ("Do not invent mandatory reports, diagrams, PDFs, presentations, "
        "screenshots, length, or submission formats."),
        ("A network design recommendation is NOT inherently a written report "
        "or a mandatory diagram. Do not assume a medium."),
        "Do not solve the assignment for students or prescribe one specific design.",
        "Align the tasks and evidence with the stated learning goal.",
        "Do not introduce a student-facing educational framework label unless asked.",
        "Avoid duplicated task descriptions and generic filler.",
        "Never expose instructor-facing metadata or notes about missing fields in the student draft.",
        ("Use [Faculty decision needed] only where an essential detail cannot "
        "be omitted; do not invent it."),
        ("Before answering, check each MUST/REQUIRED/SUBMIT instruction against "
        "the instructor's explicit instructions. Remove unauthorized mandates."),
    ]
    if not (request.assignment_deliverables or "").strip():
        rules.append("NO DELIVERABLE TYPE SPECIFIED: describe the work, not a submission artifact.")
    if not (request.assignment_format or "").strip():
        rules.append("NO FORMAT SPECIFIED: do not require a report, diagram or file type.")
    if not (request.assignment_submission or "").strip():
        rules.append("NO SUBMISSION DETAILS: omit submission instructions and heading; do not add written submission mandates.")
    if not (request.assignment_evaluation or "").strip():
        rules.append("NO EVALUATION DETAILS: do not invent a rubric or grading criteria.")
    return "\n".join(rules)


_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
_MANDATE = re.compile(r"\b(?:submit|prepare|write|produce|turn in|provide|include|create|attach|upload|must|require(?:d|s)?)\b", re.IGNORECASE)
_ARTIFACTS = {
    "report": r"\b(?:written\s+)?reports?\b",
    "diagram": r"\bdiagrams?\b",
    "presentation": r"\bpresentations?\b|\bslides?\b",
    "pdf": r"\bpdfs?\b",
    "screenshot": r"\bscreenshots?\b",
}


# Only remove explicit submission logistics when the instructor did not supply any.
# Never remove the substantive deliverables or rewrite the student's task.
_SUBMISSION_HEADING = re.compile(
    r"^#{1,6}\s+(?:assignment\s+)?(?:instructions\s+for\s+submission|"
    r"submission(?:\s+(?:guidelines|instructions|details|information|method))?)\s*$",
    re.IGNORECASE,
)
_SUBMISSION_LOGISTICS = re.compile(
    r"\b(?:submit|upload|turn\s+in|hand\s+in|submission(?:s)?\s+(?:will|must|should|is|are))\b"
    r".{0,180}\b(?:dropbox|canvas|google\s+classroom|blackboard|moodle|"
    r"course\s+(?:website|site|portal)|designated\s+(?:folder|dropbox)|"
    r"submission\s+(?:method|location|platform)|\[insert\s+submission)\b",
    re.IGNORECASE | re.DOTALL,
)
_PLACEHOLDER = re.compile(
    r"\[(?:insert|specify|add|enter)\s+[^\]\n]*(?:submission|dropbox|canvas|classroom)[^\]\n]*\]",
    re.IGNORECASE,
)


def _has_submission_authority(request) -> bool:
    """Only affirmative submission instructions grant submission authority.

    Negative constraints (e.g. 'do not require written reports') are not
    permission to require a written report or submission method.
    """
    positive = "\n".join(str(getattr(request, field, "") or "") for field in (
        "assignment_submission", "assignment_description", "assignment_requirements",
        "assignment_deliverables", "assignment_format",
    ))
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", positive):
        if re.search(r"\b(?:do not|don't|without|no specific|not required|unless explicitly|avoid)\b", sentence, re.IGNORECASE):
            continue
        if re.search(r"\b(?:submit|submission|upload|turn in|hand in|dropbox|canvas|classroom|blackboard|moodle)\b", sentence, re.IGNORECASE):
            return True
    return False


def _positive_authorization(request, kind: str) -> bool:
    """Recognize an explicitly requested artifact, not a prohibition of it."""
    fields = ("assignment_description", "assignment_requirements", "assignment_deliverables", "assignment_format")
    pattern = _ARTIFACTS[kind]
    for field in fields:
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", str(getattr(request, field, "") or "")):
            if re.search(pattern, sentence, re.IGNORECASE) and not re.search(
                r"\b(?:do not|don't|without|no specific|not required|unless explicitly|avoid)\b", sentence, re.IGNORECASE
            ):
                return True
    return False


_UNSPECIFIED_NOTE = re.compile(
    r"\b(?:the instructor|instructor)\s+(?:has\s+)?(?:not|n't)\s+(?:provided|specified)\b|"
    r"\b(?:no specific|not provided|not specified|unspecified)\b.{0,110}"
    r"\b(?:submission|format|deliverable|requirements?)\b|"
    r"\b(?:submission|format|deliverable|requirements?)\b.{0,100}"
    r"\b(?:not provided|not specified|unspecified)\b", re.IGNORECASE,
)
_FORMAT_MANDATE = re.compile(
    r"\b(?:all\s+submissions?\s+must|submissions?\s+(?:must|should|are required)|"
    r"(?:must|should|required to|please)\s+(?:be\s+)?(?:submit|write|provide|prepare|produce)|"
    r"(?:submit|write|provide|prepare|produce)\s+(?:a|an|the|your)?)\b", re.IGNORECASE,
)
_WRITTEN_FORMAT = re.compile(r"\b(?:written\s+(?:format|form|analysis|explanation|response|submission)|"
                             r"in\s+writing|write\s+(?:a|an|the|your)\s+(?:analysis|explanation|response))\b", re.IGNORECASE)


def _is_unauthorized_submission_line(line: str, request) -> bool:
    if _has_submission_authority(request) or (
        _positive_authorization(request, "report") and re.search(r"\bwritten\s+report\b", line, re.IGNORECASE)
    ):
        return False
    return bool(_SUBMISSION_LOGISTICS.search(line) or _PLACEHOLDER.search(line)
                or re.search(r"\b(?:submit|upload|turn\s+in|submission)\b", line, re.IGNORECASE)
                and re.search(r"\b(?:written|format|file|folder|platform|method|location|portal)\b", line, re.IGNORECASE))


def _unauthorized_submission_lines(text: str, request) -> list[str]:
    return [line for line in text.splitlines() if _is_unauthorized_submission_line(line, request)]


def remove_unauthorized_submission_logistics(text: str, request) -> str:
    """Remove independently recognizable invented logistics and meta-notes.

    Do not silently rewrite substantive tasks or deliverables. Remaining
    questionable requirements are flagged for faculty review.
    """
    if request.content_type != "assignment":
        return text
    lines = text.splitlines()
    cleaned = []
    in_submission_section = False
    for line in lines:
        heading = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if heading:
            in_submission_section = False
            if not _has_submission_authority(request) and _SUBMISSION_HEADING.match(line):
                in_submission_section = True
                continue
        if in_submission_section:
            continue
        if _UNSPECIFIED_NOTE.search(line) and re.search(r"\b(?:instructor|submission|format|deliverable)\b", line, re.IGNORECASE):
            continue
        if _is_unauthorized_submission_line(line, request):  # noqa: SIM102
            if re.match(r"^\s*(?:[-*]\s+|\d+[.)]\s+)?(?:please\s+)?"
                        r"(?:submit|upload|turn\s+in|hand\s+in|submission\b|"
                        r"all\s+submissions?\b|check\s+the\s+course\s+(?:website|site))", line, re.IGNORECASE):
                continue
        cleaned.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned)).strip()


def review_assignment_draft(text: str, request) -> list[str]:
    if request.content_type != "assignment":
        return []
    issues: list[str] = []
    supplied = _instructor_text(request)
    if _unauthorized_submission_lines(text, request):
        issues.append("Submission platform or method invented without instructor authorization.")
    if not _has_submission_authority(request) and any(
        _SUBMISSION_HEADING.match(line) for line in text.splitlines()
    ):
        issues.append("Unauthorized submission instructions section.")
    headings = {m.group(1).strip().casefold() for m in _HEADING.finditer(text)}
    if not _has_submission_authority(request) and any(
        h.startswith("submission") for h in headings
    ):
        issues.append("Submission section added without instructor instructions.")
    if not (request.assignment_evaluation or "").strip() and any(
        h.startswith(("evaluation", "grading", "scoring", "rubric")) for h in headings
    ):
        issues.append("Evaluation section added without instructor instructions.")

    # Check mandates sentence-by-sentence. Mere mentions of reports and diagrams
    # are not violations; they can be legitimate examples or optional tools.
    for artifact, pattern in _ARTIFACTS.items():
        if _positive_authorization(request, artifact):
            continue
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
            if not re.search(pattern, sentence, re.IGNORECASE):
                continue
            if re.search(r"\b(?:optional|optionally|may|could|if useful|for example|e\.g\.)\b", sentence, re.IGNORECASE):
                continue
            if _MANDATE.search(sentence) and re.search(
                rf"\b(?:submit|prepare|write|produce|turn in|provide|include|create|attach|upload|must|required?)\b"
                rf".{{0,90}}{pattern}|{pattern}.{{0,50}}\b(?:must|required)\b",
                sentence, re.IGNORECASE,
            ):
                issues.append(f"Potentially required {artifact} not explicitly authorized by instructor.")
                break

    if re.search(r"\b(?:RAID\s*[0156]|hub.and.spoke|block all incoming traffic)\b", text, re.IGNORECASE):
        issues.append("Possible model answer or unsupported technical solution.")
    if _UNSPECIFIED_NOTE.search(text):
        issues.append("Internal instructor missing-information commentary leaked into student draft.")
    if not _positive_authorization(request, "report") and not _has_submission_authority(request):  # noqa: SIM102
        if any(_WRITTEN_FORMAT.search(line) and (
                   _FORMAT_MANDATE.search(line) or re.search(r"^\s*[-*]\s+", line)
               ) for line in text.splitlines()):
            issues.append("Potentially required written format not explicitly authorized by instructor.")
    if re.search(
        r"\b(?:describe|document|analyze|evaluate|assess)\s+(?:the |an? )?"
        r"(?:current|existing)\s+(?:network|system|infrastructure)\s+"
        r"(?:configuration|topology|architecture|setup)\b", text, re.IGNORECASE,
    ) and not re.search(
        r"\b(?:current|existing)\s+(?:network|system|infrastructure)\s+"
        r"(?:configuration|topology|architecture|setup)\b", supplied, re.IGNORECASE,
    ):
        issues.append("Draft assumes an existing configuration; verify it is in the selected sources.")
    return list(dict.fromkeys(issues))


def revision_prompt(original: str, issues: list[str], request) -> str:
    """One narrowly scoped revision; the original draft remains the fallback."""
    return (
        "Revise the STUDENT-FACING ASSIGNMENT below. Correct ONLY the listed "
        "quality issues. Preserve all valid instructions, educational goals, "
        "structure, and explicitly instructor-authorized requirements. "
        "Do not invent deliverables, facts, solutions, deadlines, or formats. "
        "When submission details are unspecified, remove submission platform "
        "instructions, invented written-format mandates, and placeholder submission sections entirely. "
        "Never expose notes about missing instructor inputs to students. "
        "Do not introduce new requirements. Return ONLY the complete revised "
        "assignment in Markdown.\n\n"
        "INSTRUCTOR GOAL:\n" + (request.assignment_goal or "") + "\n\n"
        "INSTRUCTOR INSTRUCTIONS (BLANK MEANS NOT SPECIFIED):\n" +
        "\n".join(f"{field}: {getattr(request, field, '') or '[not specified]'}" for field in (
            "assignment_scenario", "assignment_requirements", "assignment_deliverables",
            "assignment_format", "assignment_evaluation", "assignment_submission",
        )) + "\n\nQUALITY ISSUES:\n" +
        "\n".join("- " + issue for issue in issues) +
        "\n\nORIGINAL DRAFT:\n" + original
    )
