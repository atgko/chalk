import json

from freezegun import freeze_time

from chalk.metrics import append_event, read_events, read_events_by_type


def test_append_event_creates_file_and_parent_dir(tmp_path):
    log_path = tmp_path / "nested" / "eval-log.json"
    append_event(log_path, "extraction", {"filename": "syllabus.docx"})
    assert log_path.exists()


def test_append_event_writes_one_json_object_per_line(tmp_path):
    log_path = tmp_path / "eval-log.json"
    append_event(log_path, "extraction", {"filename": "a.docx"})
    append_event(log_path, "rollover", {"from_term": "Fall 2026", "to_term": "Fall 2027"})

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["event_type"] == "extraction"
    assert first["filename"] == "a.docx"


@freeze_time("2026-09-23T12:00:00+00:00")
def test_append_event_stamps_a_utc_timestamp(tmp_path):
    log_path = tmp_path / "eval-log.json"
    append_event(log_path, "extraction", {"filename": "a.docx"})
    events = read_events(log_path)
    assert events[0]["timestamp"] == "2026-09-23T12:00:00+00:00"


def test_append_event_preserves_earlier_lines_on_later_appends(tmp_path):
    log_path = tmp_path / "eval-log.json"
    for i in range(5):
        append_event(log_path, "generation", {"i": i})
    events = read_events(log_path)
    assert [e["i"] for e in events] == [0, 1, 2, 3, 4]


def test_read_events_returns_empty_list_for_missing_file(tmp_path):
    log_path = tmp_path / "does-not-exist.json"
    assert read_events(log_path) == []


def test_read_events_by_type_filters_to_the_requested_event_type(tmp_path):
    log_path = tmp_path / "eval-log.json"
    append_event(log_path, "extraction", {"filename": "a.docx"})
    append_event(log_path, "consistency_check", {"passed": False})
    append_event(log_path, "consistency_check_override", {"passed": False})

    checks = read_events_by_type(log_path, "consistency_check")
    assert len(checks) == 1
    assert checks[0]["passed"] is False
