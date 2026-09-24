import json

import pytest

from chalk.calendar_data import find_term, load_calendars

SAMPLE_CALENDARS = {
    "institution": "University of Utah",
    "calendar_source": "https://registrar.utah.edu/academic-calendars/",
    "last_updated": "2026-09-17",
    "terms": [
        {
            "term": "Fall 2026",
            "start": "2026-08-24",
            "end": "2026-12-10",
            "verified_against": "https://registrar.utah.edu/academic-calendars/",
            "verified_date": "2026-09-17",
            "no_class_dates": [
                {"label": "Labor Day", "date": "2026-09-07"},
                {
                    "label": "Fall Break",
                    "date_start": "2026-10-10",
                    "date_end": "2026-10-18",
                },
            ],
        }
    ],
}


def test_load_calendars_reads_json_file(tmp_path):
    path = tmp_path / "calendars.json"
    path.write_text(json.dumps(SAMPLE_CALENDARS), encoding="utf-8")

    calendars = load_calendars(path)
    assert calendars["institution"] == "University of Utah"
    assert len(calendars["terms"]) == 1


def test_load_calendars_raises_on_missing_file(tmp_path):
    with pytest.raises(OSError):
        load_calendars(tmp_path / "does-not-exist.json")


def test_find_term_returns_matching_term():
    term = find_term(SAMPLE_CALENDARS, "Fall 2026")
    assert term is not None
    assert term["start"] == "2026-08-24"
    assert len(term["no_class_dates"]) == 2


def test_find_term_returns_none_for_unknown_term_graceful_degradation():
    # PRD section 5.3: a term missing from the file must not raise — the
    # tool prompts for a Week 1 date and proceeds normally.
    term = find_term(SAMPLE_CALENDARS, "Fall 2099")
    assert term is None
