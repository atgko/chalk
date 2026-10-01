"""PDF syllabi through the whole workflow: pipeline, upload helpers, CLI,
metrics, and rollover of the converted Word file."""

import io
import json

import pytest

from chalk import metrics
from chalk.cli import main
from chalk.errors import ExtractionError
from chalk.extractors import extract_course
from chalk.pipeline import (
    PDF_READING_CONTENT_TYPE,
    confirm_rollover,
    convert_pdf_syllabus,
    estimate_ai_reading_cost_per_page,
    extract_syllabus,
    preview_rollover,
    save_reviewed_course,
)
from chalk.project import list_source_files
from chalk.report import render_evaluation_report
from tests.fixtures import pdf_layout_builder
from tests.test_pdf_import_readers import _reply
from ui.upload_view import extract_upload

_ENV_KEYS = ("LLM_PROVIDER", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")


@pytest.fixture
def pdf(tmp_path):
    return pdf_layout_builder.build_two_page_syllabus(tmp_path / "IS 6640 Fall 2026.pdf")


@pytest.fixture
def ai(monkeypatch):
    """A configured provider with a cost rate, and a mocked LLM whose
    reply the test can set."""
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    state = {"reply": _reply(), "calls": 0}

    def fake_complete(prompt, system="", max_tokens=2000):
        state["calls"] += 1
        return {"text": state["reply"], "input_tokens": 1000, "output_tokens": 2000}

    monkeypatch.setattr("chalk.pdf_import.ai_reader.complete", fake_complete)
    return state


# ---- Pipeline ------------------------------------------------------------------------


def test_extracting_a_pdf_stores_the_converted_word_file(tmp_project, pdf):
    course_data, consistency = extract_syllabus(tmp_project, pdf)

    assert course_data.course.source_file == "source/IS 6640 Fall 2026 (from PDF).docx"
    assert course_data.course.source_format == "word"
    assert list_source_files(tmp_project) == ["IS 6640 Fall 2026 (from PDF).docx"]
    assert consistency.passed
    [event] = metrics.read_events_by_type(tmp_project.eval_log, "extraction")
    assert (event["filename"], event["pdf_method"]) == ("IS 6640 Fall 2026.pdf", "local")


def test_a_local_read_costs_nothing_and_logs_no_generation(tmp_project, pdf):
    conversion = convert_pdf_syllabus(tmp_project, pdf)
    assert (conversion.method, conversion.cost_usd, conversion.pdf_name) == ("local", None, pdf.name)
    assert conversion.docx_path.name == "IS 6640 Fall 2026 (from PDF).docx"
    assert metrics.read_events_by_type(tmp_project.eval_log, "generation") == []


def test_an_ai_read_logs_its_tokens_and_cost(tmp_project, pdf, ai):
    conversion = convert_pdf_syllabus(tmp_project, pdf, method="ai")

    # gpt-4o in the bundled config: $0.0025 / 1K in, $0.01 / 1K out.
    assert conversion.cost_usd == pytest.approx(1000 / 1000 * 0.0025 + 2000 / 1000 * 0.01)
    [event] = metrics.read_events_by_type(tmp_project.eval_log, "generation")
    assert event["content_type"] == PDF_READING_CONTENT_TYPE
    assert (event["model"], event["input_tokens"], event["output_tokens"]) == ("gpt-4o", 1000, 2000)
    assert "Networking" not in json.dumps(event)  # metadata only, never content
    course_data, _ = extract_course(conversion.docx_path)
    assert [w.week_number for w in course_data.weeks] == [1, 2, None, 3]


def test_a_failed_pdf_read_is_logged_with_its_method(tmp_project, tmp_path, ai):
    ai["reply"] = "sorry, I can't"
    with pytest.raises(ExtractionError):
        convert_pdf_syllabus(tmp_project, pdf_layout_builder.build_two_page_syllabus(tmp_path / "x.pdf"), method="ai")
    [event] = metrics.read_events_by_type(tmp_project.eval_log, "extraction_error")
    assert (event["filename"], event["pdf_method"]) == ("x.pdf", "ai")


def test_an_extraction_failure_after_conversion_names_the_pdf(tmp_project, tmp_path, ai):
    ai["reply"] = _reply(course={"title": "No term anywhere"})
    with pytest.raises(ExtractionError, match="Could not find the term"):
        extract_syllabus(tmp_project, pdf_layout_builder.build_two_page_syllabus(tmp_path / "y.pdf"), pdf_method="ai")
    [event] = metrics.read_events_by_type(tmp_project.eval_log, "extraction_error")
    assert (event["filename"], event["pdf_method"]) == ("y.pdf", "ai")


def test_the_converted_syllabus_rolls_over_as_word(tmp_project, pdf):
    course_data, _ = extract_syllabus(tmp_project, pdf)
    save_reviewed_course(tmp_project, course_data)

    plan = preview_rollover(tmp_project, course_data, "Spring 2027", llm_generate_topics=False)
    written = confirm_rollover(tmp_project, plan)

    assert written[0].name == "syllabus.docx"
    rolled, consistency = extract_course(written[0])
    assert rolled.course.term == "Spring 2027"
    assert [w.week_number for w in rolled.weeks if not w.is_break] == [1, 2, 3, 4]
    assert consistency.passed


def test_cost_per_page_hint_uses_the_model_rate(tmp_project, ai, monkeypatch):
    assert estimate_ai_reading_cost_per_page(tmp_project) == pytest.approx(0.8 * 0.0025 + 1.2 * 0.01)
    monkeypatch.setenv("LLM_MODEL", "a-model-with-no-rate")
    assert estimate_ai_reading_cost_per_page(tmp_project) is None


def test_the_report_counts_pdf_extractions_separately(tmp_project, pdf):
    extract_syllabus(tmp_project, pdf)
    report = render_evaluation_report(
        metrics.read_events(tmp_project.eval_log), project_name="P", generated_on=__import__("datetime").date(2026, 10, 1)
    )
    assert "| pdf | 1 | 0 | 0% |" in report


# ---- Upload helpers ------------------------------------------------------------------


def test_upload_of_a_pdf_read_locally(tmp_project, pdf):
    outcome = extract_upload(tmp_project, pdf)
    assert outcome.pending is not None and outcome.notice is None
    assert outcome.pending.course_data.course.source_file.endswith("(from PDF).docx")


def test_upload_of_a_pdf_read_with_ai_reports_the_cost(tmp_project, pdf, ai):
    outcome = extract_upload(tmp_project, pdf, pdf_method="ai")
    assert outcome.pending is not None
    assert outcome.notice == f"Read {pdf.name} with AI. Cost: $0.0225."


def test_a_failed_local_pdf_read_suggests_the_other_options(tmp_project, tmp_path):
    scan = pdf_layout_builder.build_pdf_without_text(tmp_path / "scan.pdf")
    outcome = extract_upload(tmp_project, scan)
    assert "scanned" in outcome.error
    assert "Read it with AI" in outcome.error


def test_a_failed_ai_read_does_not_suggest_ai_again(tmp_project, pdf, ai):
    ai["reply"] = "not json"
    outcome = extract_upload(tmp_project, pdf, pdf_method="ai")
    assert "didn't come back in the expected form" in outcome.error
    assert "Read it with AI" not in outcome.error


def test_choosing_a_table_reuses_the_pdf_conversion(tmp_project, pdf, ai):
    schedule = {"type": "schedule", "rows": [{"week": 1, "date": "8/24", "topics": ["Intro"]}]}
    ai["reply"] = _reply(content=[schedule, {"type": "heading", "text": "AGAIN"}, schedule])

    outcome = extract_upload(tmp_project, pdf, pdf_method="ai")

    choice = outcome.table_choice
    assert choice is not None and choice.pdf_conversion is not None
    picked = extract_upload(tmp_project, choice.upload_path, 0, pdf_conversion=choice.pdf_conversion)
    assert picked.pending is not None
    assert ai["calls"] == 1  # the AI read wasn't repeated (or paid for twice)


# ---- CLI -----------------------------------------------------------------------------


def _run(*argv):
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), input_fn=lambda _prompt: "", out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def test_cli_extracts_a_pdf_locally(tmp_project, pdf):
    code, out, err = _run("extract", str(pdf), "--project", str(tmp_project.root))
    assert code == 0, err
    assert "Saved the PDF as a Word file for review and rollover: source/IS 6640 Fall 2026 (from PDF).docx" in out


def test_cli_ai_read_needs_a_provider(tmp_project, pdf, monkeypatch):
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    code, _, err = _run("extract", str(pdf), "--read-pdf-with", "ai", "--project", str(tmp_project.root))
    assert code == 1
    assert "No LLM provider is configured" in err


def test_cli_extracts_a_pdf_with_ai(tmp_project, pdf, ai):
    code, out, err = _run("extract", str(pdf), "--read-pdf-with", "ai", "--project", str(tmp_project.root))
    assert code == 0, err
    assert "IS 6640" in out
