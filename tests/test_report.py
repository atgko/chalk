"""Tests for chalk.report — the December evidence artifact."""

import datetime as dt

from chalk import metrics
from chalk.report import render_evaluation_report, write_evaluation_report

ON = dt.date(2026, 12, 1)


def _event(event_type, **payload):
    return {"event_type": event_type, "timestamp": "2026-11-02T15:30:00+00:00", **payload}


def test_empty_log_renders_every_section_with_placeholders():
    report = render_evaluation_report([], project_name="IS-6640", generated_on=ON)
    assert report.startswith("# Evaluation report — IS-6640\n\nGenerated 2026-12-01 from eval-log.json (0 events).")
    for placeholder in ("_No extractions yet._", "_No rollovers yet._", "_No content generated yet._"):
        assert placeholder in report
    assert "- Checks run: 0" in report


def test_files_processed_with_error_rate_by_format():
    events = [
        _event("extraction", source_format="word"),
        _event("extraction", source_format="word"),
        _event("extraction", source_format="markdown"),
        _event("extraction_error", filename="locked.docx", error_type="ProtectedFileError"),
        _event("extraction_error", filename="notes.pdf", error_type="ExtractionError"),
    ]
    report = render_evaluation_report(events, project_name="P", generated_on=ON)
    assert "| word | 2 | 1 | 33% |" in report
    assert "| markdown | 1 | 0 | 0% |" in report
    assert "| other | 0 | 1 | 100% |" in report
    assert "- 2026-11-02 15:30 — locked.docx: ProtectedFileError" in report


def test_consistency_catches_and_overrides():
    events = [
        _event("consistency_check", passed=True, term="Fall 2026"),
        _event("consistency_check", passed=False, term="Spring 2026"),
        _event("consistency_check_override", term="Spring 2026"),
    ]
    report = render_evaluation_report(events, project_name="P", generated_on=ON)
    assert "- Checks run: 2" in report
    assert "- Mismatches caught: 1" in report
    assert "- Continued anyway (override logged): 1" in report
    assert "caught on term “Spring 2026”" in report


def test_rollovers_table():
    events = [
        _event("rollover", source_term="Fall 2026", target_term="Fall 2027",
               source_duration_weeks=10, target_duration_weeks=12, flag_count=2)
    ]
    report = render_evaluation_report(events, project_name="P", generated_on=ON)
    assert "| 2026-11-02 15:30 | Fall 2026 | Fall 2027 | 10 → 12 | 2 |" in report


def test_generation_cost_by_content_type_including_unpriced_calls():
    events = [
        _event("generation", content_type="quiz", input_tokens=1000, output_tokens=500, cost_usd=0.0075, model="gpt-4o"),
        _event("generation", content_type="quiz", input_tokens=1000, output_tokens=500, cost_usd=0.0025, model="gpt-4o"),
        _event("generation", content_type="rubric", input_tokens=2000, output_tokens=800, cost_usd=None, model="custom"),
    ]
    report = render_evaluation_report(events, project_name="P", generated_on=ON)
    assert "| quiz | 2 | 2,000 | 1,000 | $0.0100 | $0.0050 |" in report
    assert "| rubric | 1 | 2,000 | 800 | $0.0000 | $0.0000 |" in report
    assert "**Total: 3 calls, $0.0100.**" in report
    assert "1 call(s) used a model with no cost rate" in report
    assert "Models used: custom, gpt-4o." in report


def test_write_saves_under_outputs_and_archives(tmp_project):
    metrics.append_event(tmp_project.eval_log, "extraction", {"source_format": "word"})
    first = write_evaluation_report(tmp_project, generated_on=ON)
    write_evaluation_report(tmp_project, generated_on=ON)

    assert first == tmp_project.outputs_dir / "evaluation-report.md"
    assert "| word | 1 | 0 | 0% |" in first.read_text(encoding="utf-8")
    assert len(list((tmp_project.outputs_dir / ".archive").glob("evaluation-report-*.md"))) == 1


def test_write_uses_today_by_default(tmp_project):
    path = write_evaluation_report(tmp_project)
    assert f"Generated {dt.date.today().isoformat()}" in path.read_text(encoding="utf-8")
