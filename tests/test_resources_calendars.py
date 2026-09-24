"""Structural checks on the bundled resources/data/calendars.json.

This is the real data shipped with the toolkit (PRD section 5.3: "a
committed file that ships with the repo"), sourced from the University of
Utah registrar's published PDF calendars. We check structure and internal
consistency here rather than hand-asserting every date — the values
themselves are only as good as the source PDFs, and the registrar
explicitly reserves the right to change them ("Calendar subject to change
without notice").
"""

import datetime as dt
from pathlib import Path

import pytest

from chalk.calendar_data import find_term, load_calendars

CALENDARS_PATH = Path(__file__).resolve().parent.parent / "resources" / "data" / "calendars.json"

REQUIRED_TERM_KEYS = {"term", "start", "end", "verified_against", "verified_date", "no_class_dates"}


@pytest.fixture(scope="module")
def calendars():
    return load_calendars(CALENDARS_PATH)


def test_institution_is_university_of_utah(calendars):
    assert calendars["institution"] == "University of Utah"


def test_covers_at_least_through_the_2029_2030_academic_year(calendars):
    term_names = {t["term"] for t in calendars["terms"]}
    for expected in ("Fall 2026", "Spring 2027", "Fall 2029", "Spring 2030"):
        assert expected in term_names


def test_every_term_has_the_required_keys(calendars):
    for term in calendars["terms"]:
        missing = REQUIRED_TERM_KEYS - term.keys()
        assert not missing, f"{term.get('term')} is missing keys: {missing}"


def test_every_term_start_is_before_its_end(calendars):
    for term in calendars["terms"]:
        start = dt.date.fromisoformat(term["start"])
        end = dt.date.fromisoformat(term["end"])
        assert start < end, f"{term['term']}: start {start} is not before end {end}"


def test_terms_are_in_chronological_order(calendars):
    starts = [dt.date.fromisoformat(t["start"]) for t in calendars["terms"]]
    assert starts == sorted(starts)


def test_every_no_class_date_has_a_date_or_a_range(calendars):
    for term in calendars["terms"]:
        for entry in term["no_class_dates"]:
            has_single = "date" in entry
            has_range = "date_start" in entry and "date_end" in entry
            assert has_single or has_range, (
                f"{term['term']} no_class_date {entry.get('label')} has neither "
                "'date' nor a 'date_start'/'date_end' pair"
            )


def test_no_class_dates_fall_within_the_term_window(calendars):
    for term in calendars["terms"]:
        start = dt.date.fromisoformat(term["start"])
        end = dt.date.fromisoformat(term["end"])
        for entry in term["no_class_dates"]:
            if "date" in entry:
                event_date = dt.date.fromisoformat(entry["date"])
                assert start <= event_date <= end
            else:
                event_start = dt.date.fromisoformat(entry["date_start"])
                event_end = dt.date.fromisoformat(entry["date_end"])
                assert start <= event_start <= end
                assert start <= event_end <= end


def test_find_term_locates_a_known_term_in_the_real_data(calendars):
    fall_2026 = find_term(calendars, "Fall 2026")
    assert fall_2026 is not None
    assert fall_2026["start"] == "2026-08-24"
    assert fall_2026["end"] == "2026-12-10"


def test_find_term_gracefully_degrades_for_a_term_beyond_the_bundled_range(calendars):
    assert find_term(calendars, "Fall 2099") is None
