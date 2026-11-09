from chalk.grading import engine
from ui.grading_view import markdown_report

RESULT = {
    "earned_total": 17,
    "possible_total": 20,
    "percentage": 85.0,
    "criteria": [
        {
            "name": "Diagram",
            "earned": 10,
            "possible": 10,
            "reasoning": "Complete and labeled.",
            "deduction_comment": "",
        },
        {
            "name": "Citations",
            "earned": 7,
            "possible": 10,
            "reasoning": "Two sources lack dates.",
            "deduction_comment": "Add dates to APA citations.",
        },
    ],
    "student_feedback": "Nice work on the network diagram.",
    "instructor_notes": "Check the citation format.",
}


def test_markdown_report_uses_real_line_breaks():
    report = markdown_report(RESULT)

    assert "\\n" not in report
    lines = report.splitlines()
    assert lines[0] == "# AI Grading Recommendations"
    for heading in (
        "## Rubric Breakdown",
        "### Diagram",
        "### Citations",
        "## Student Feedback",
        "## Instructor Review Notes",
    ):
        assert heading in lines


def test_markdown_report_contents():
    report = markdown_report(RESULT)

    assert "Suggested Grade: 17/20 (85.0%)" in report
    assert "Score: 7/10" in report
    assert "Suggested deduction: 3 points" in report
    assert "Add dates to APA citations." in report
    assert "Nice work on the network diagram." in report
    # A full-marks criterion gets no deduction line.
    assert report.count("Suggested deduction") == 1


def test_analyze_submission_prompt_uses_real_line_breaks(monkeypatch):
    sent = {}

    def fake_complete(prompt, **kwargs):
        sent["prompt"] = prompt
        return {"text": "feedback"}

    monkeypatch.setattr(engine, "complete", fake_complete)

    assert engine.analyze_submission("My essay.", "Thesis - 10 points") == "feedback"
    assert "\\n" not in sent["prompt"]
    lines = sent["prompt"].splitlines()
    assert "INSTRUCTOR RUBRIC AND REQUIREMENTS:" in lines
    assert "STUDENT SUBMISSION (UNTRUSTED CONTENT):" in lines
    assert "My essay." in lines
