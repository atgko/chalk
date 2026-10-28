import json

import pytest
from freezegun import freeze_time

from chalk.metrics import append_event, read_events, read_events_by_type, typical_output_tokens


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


def test_read_events_skips_a_last_line_still_being_written(tmp_path):
    log_path = tmp_path / "eval-log.json"
    append_event(log_path, "generation", {"content_type": "quiz"})
    with log_path.open("a", encoding="utf-8") as f:
        f.write('{"event_type": "gener')  # a background job partway through its write

    assert [e["content_type"] for e in read_events(log_path)] == ["quiz"]


def test_read_events_still_rejects_a_corrupt_complete_line(tmp_path):
    log_path = tmp_path / "eval-log.json"
    log_path.write_text('{"event_type": "gener\n', encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        read_events(log_path)


def test_read_events_by_type_filters_to_the_requested_event_type(tmp_path):
    log_path = tmp_path / "eval-log.json"
    append_event(log_path, "extraction", {"filename": "a.docx"})
    append_event(log_path, "consistency_check", {"passed": False})
    append_event(log_path, "consistency_check_override", {"passed": False})

    checks = read_events_by_type(log_path, "consistency_check")
    assert len(checks) == 1
    assert checks[0]["passed"] is False


def test_summarize_events_aggregates_every_reported_metric():
    from chalk.metrics import summarize_events

    events = [
        {"event_type": "generation", "content_type": "quiz", "cost_usd": 0.01},
        {"event_type": "generation", "content_type": "quiz", "cost_usd": 0.02},
        {"event_type": "generation", "cost_usd": 0.005},
        {"event_type": "rollover", "target_term": "Fall 2027"},
        {"event_type": "extraction_error", "filename": "x.docx"},
        {"event_type": "consistency_check", "passed": False},
        {"event_type": "consistency_check", "passed": True},
        {"event_type": "consistency_check_override"},
    ]

    summary = summarize_events(events)

    assert summary.generation_counts == {"quiz": 2, "unknown": 1}
    assert round(summary.total_cost_usd, 3) == 0.035
    assert summary.rollovers == [events[3]]
    assert summary.extraction_errors == [events[4]]
    assert summary.consistency_failures == 1
    assert summary.consistency_overrides == 1


def test_summarize_events_of_an_empty_log():
    from chalk.metrics import summarize_events

    summary = summarize_events([])
    assert summary.generation_counts == {}
    assert summary.total_cost_usd == 0


def _generation(timestamp, cost_usd, content_type="quiz"):
    return {"event_type": "generation", "timestamp": timestamp, "content_type": content_type, "cost_usd": cost_usd}


def test_monthly_costs_groups_generation_cost_by_month_and_type():
    import datetime as dt

    from chalk.metrics import monthly_costs

    events = [
        _generation("2026-09-10T12:00:00+00:00", 0.01),
        _generation("2026-09-20T12:00:00+00:00", 0.02, "rubric"),
        _generation("2026-09-25T12:00:00+00:00", None),  # no known rate counts as $0
        {"event_type": "rollover", "timestamp": "2026-09-26T12:00:00+00:00"},
        _generation("2026-10-01T12:00:00+00:00", 0.04),
    ]

    [september, october] = monthly_costs(events, tz=dt.UTC)

    assert september.month == "2026-09"
    assert september.generations == 3
    assert round(september.cost_usd, 4) == 0.03
    assert september.cost_by_type == {"quiz": 0.01, "rubric": 0.02}
    assert round(september.avg_cost_usd, 4) == 0.01
    assert (october.month, october.generations, october.cost_usd) == ("2026-10", 1, 0.04)


def test_monthly_costs_fills_quiet_months_with_zero_across_a_year_end():
    import datetime as dt

    from chalk.metrics import monthly_costs

    events = [_generation("2026-11-15T12:00:00+00:00", 0.01), _generation("2027-02-15T12:00:00+00:00", 0.02)]

    months = monthly_costs(events, tz=dt.UTC)

    assert [m.month for m in months] == ["2026-11", "2026-12", "2027-01", "2027-02"]
    assert (months[1].generations, months[1].cost_usd, months[1].avg_cost_usd) == (0, 0.0, 0.0)


def test_monthly_costs_buckets_by_local_time_not_utc():
    import datetime as dt

    from chalk.metrics import monthly_costs

    # 9 pm on Oct 31 in UTC-5 is already Nov 1 in UTC.
    events = [_generation("2026-11-01T02:00:00+00:00", 0.01)]
    eastern = dt.timezone(dt.timedelta(hours=-5))

    assert [m.month for m in monthly_costs(events, tz=eastern)] == ["2026-10"]


def test_monthly_costs_of_a_log_without_generations():
    from chalk.metrics import monthly_costs

    assert monthly_costs([{"event_type": "rollover", "timestamp": "2026-09-26T12:00:00+00:00"}]) == []


def test_month_keys_for_this_and_last_month():
    import datetime as dt

    from chalk.metrics import month_key, previous_month_key

    assert month_key(dt.date(2026, 10, 28)) == "2026-10"
    assert previous_month_key(dt.date(2026, 10, 28)) == "2026-09"
    assert previous_month_key(dt.date(2027, 1, 5)) == "2026-12"


def test_typical_output_tokens_is_the_median_of_recent_replies_of_that_type(tmp_path):
    log_path = tmp_path / "eval-log.json"
    for tokens in (400, 900, 500):
        append_event(log_path, "generation", {"content_type": "quiz", "output_tokens": tokens})
    append_event(log_path, "generation", {"content_type": "rubric", "output_tokens": 3000})

    assert typical_output_tokens(log_path, "quiz") == 500
    assert typical_output_tokens(log_path, "quiz", recent=2) == 700  # the last two: 900 and 500
    assert typical_output_tokens(log_path, "summary") is None
