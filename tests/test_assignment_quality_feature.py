"""Regression tests for instructor-grounded assignment quality."""
from dataclasses import dataclass

from chalk.generation.assignment_quality import (
    assignment_quality_guidance,
    review_assignment_draft,
    revision_prompt,
    remove_unauthorized_submission_logistics,
)


@dataclass
class Request:
    content_type: str = "assignment"
    assignment_name: str = "Network Design Recommendation"
    assignment_goal: str = "Recommend and justify a network design."
    assignment_scenario: str = "A small business needs a reliable network."
    assignment_requirements: str = "Use course concepts."
    assignment_deliverables: str = ""
    assignment_format: str = ""
    assignment_evaluation: str = ""
    assignment_submission: str = ""
    assignment_description: str = ""
    learning_evidence: str = ""


def test_unauthorized_artifacts_flagged():
    req = Request()
    text = "# Network Design Recommendation\n\nSubmit a written report and include a detailed diagram."
    issues = review_assignment_draft(text, req)
    assert any("report" in issue for issue in issues)
    assert any("diagram" in issue for issue in issues)


def test_authorized_artifacts_preserved():
    req = Request(assignment_deliverables="A written report and a network diagram.")
    text = "# Network Design Recommendation\n\nSubmit a written report and include a network diagram."
    assert not review_assignment_draft(text, req)


def test_optional_examples_not_flagged():
    req = Request()
    text = "# Network Design Recommendation\n\nYou may include a diagram if useful."
    assert not review_assignment_draft(text, req)


def test_missing_existing_configuration_flagged():
    req = Request()
    text = "# Network Design Recommendation\n\nAnalyze the existing network configuration."
    assert any("existing configuration" in issue for issue in review_assignment_draft(text, req))


def test_guidance_and_revision_respect_instructor():
    req = Request()
    guidance = assignment_quality_guidance(req)
    assert "NO FORMAT SPECIFIED" in guidance
    prompt = revision_prompt("# Network Design Recommendation\nSubmit a report.", ["unauthorized report"], req)
    assert "[not specified]" in prompt
    assert "ORIGINAL DRAFT" in prompt


BAD_LIVE_DRAFT = """# Network Design Recommendation

## GOAL
Analyze the networking requirements.

## TASKS IN BRIEF
1. Recommend and justify a secure design.

## INSTRUCTIONS FOR SUBMISSION
Please submit your written explanation of your network design recommendation to the designated dropbox folder.

## EXPECTED DELIVERABLE
A network design recommendation with explanations and justifications.

## ASSIGNMENT SUBMISSION GUIDELINES
Submission will be accepted through [insert submission method, e.g., Dropbox, Google Classroom, etc.]. Please check the course website for specific submission details.
"""


def test_live_draft_detects_submission_logistics():
    issues = review_assignment_draft(BAD_LIVE_DRAFT, Request())
    assert any("platform or method" in issue for issue in issues)
    assert any("submission" in issue.lower() for issue in issues)


def test_live_draft_cleanup_preserves_real_deliverable():
    cleaned = remove_unauthorized_submission_logistics(BAD_LIVE_DRAFT, Request())
    assert "design recommendation with explanations" in cleaned
    assert "dropbox" not in cleaned.lower()
    assert "google classroom" not in cleaned.lower()
    assert "submission" not in cleaned.lower()
    assert not review_assignment_draft(cleaned, Request())


def test_authorized_submission_is_preserved():
    req = Request(assignment_submission="Submit a PDF to Canvas.")
    draft = "# Assignment\n\n## Submission\nSubmit a PDF to Canvas."
    assert remove_unauthorized_submission_logistics(draft, req) == draft
    assert not any("submission" in issue.lower() for issue in review_assignment_draft(draft, req))


def test_logistics_without_heading_removed():
    draft = "# Assignment\n\nRecommend a design.\n\nPlease upload to the designated Dropbox folder."
    cleaned = remove_unauthorized_submission_logistics(draft, Request())
    assert "Recommend a design" in cleaned
    assert "Dropbox" not in cleaned


def test_other_subject_not_affected():
    req = Request(assignment_name="History Analysis", assignment_goal="Analyze evidence")
    draft = "# History Analysis\n\n## Submission\nSubmit to Google Classroom."
    assert "Google Classroom" not in remove_unauthorized_submission_logistics(draft, req)


LIVE_2026_DRAFT = """# Network Design Recommendation

## GOAL
Analyze a small business network and justify a design.

## TASKS IN BRIEF
1. Recommend a secure design.

## DELIVERABLES
- A written analysis of the business's networking requirements and a justified network design recommendation.

## SUBMISSION
- All submissions must be in a clear and concise written format.

Note: The instructor has not provided specific requirements for the deliverables, format, or submission details.
"""


def test_latest_live_draft_has_warnings():
    issues = review_assignment_draft(LIVE_2026_DRAFT, Request(
        assignment_requirements="Do not require diagrams, written reports, or other specific submission formats unless explicitly requested.",
        assignment_deliverables="A network design recommendation with explanations and justifications. No specific document format or diagram is required.",
    ))
    assert any("written format" in i for i in issues), issues
    assert any("commentary" in i for i in issues), issues


def test_latest_live_draft_removes_submission_and_meta_notes():
    req = Request(assignment_requirements="Do not require written reports or submission formats.")
    cleaned = remove_unauthorized_submission_logistics(LIVE_2026_DRAFT, req)
    assert "## SUBMISSION" not in cleaned
    assert "All submissions" not in cleaned
    assert "instructor has not provided" not in cleaned
    assert "Recommend a secure design" in cleaned
    assert "A written analysis" in cleaned  # do not silently delete substantive work


def test_negative_requirement_is_not_authorization():
    req = Request(assignment_requirements="Do not require written reports or diagrams; no submission method was provided.")
    issues = review_assignment_draft("# Network Design Recommendation\n\nSubmit a written report and diagram.", req)
    assert any("report" in i for i in issues), issues
    assert any("diagram" in i for i in issues), issues


def test_explicit_written_report_and_submission_are_preserved():
    req = Request(assignment_deliverables="Submit a written report.", assignment_submission="Upload to Canvas.")
    draft = "# Network Design Recommendation\n\n## SUBMISSION\nSubmit a written report to Canvas."
    assert remove_unauthorized_submission_logistics(draft, req) == draft
    assert not review_assignment_draft(draft, req)


def test_unrelated_course_draft_still_detected():
    req = Request(assignment_name="History Essay", assignment_goal="Compare two primary sources")
    draft = "# History Essay\n\n## SUBMISSION\nAll submissions must be in a written format."
    assert "## SUBMISSION" not in remove_unauthorized_submission_logistics(draft, req)
    assert any("submission" in i.lower() for i in review_assignment_draft(draft, req))
