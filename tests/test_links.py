"""The links file (sponsor, Nov 9): every outside link in one place, with
this computer's changes saved apart from the bundled defaults."""

import json

import pytest

from chalk import links
from chalk.errors import ChalkError


@pytest.fixture
def files(tmp_path):
    defaults = tmp_path / "links.json"
    defaults.write_text(
        json.dumps(
            {
                "links": [
                    {"key": "calendars", "label": "Calendars", "url": "https://registrar.example.edu/", "used_for": "Terms"},
                    {"key": "schedule", "label": "Schedule", "url": "https://schedule.example.edu/", "used_for": "Rooms"},
                ]
            }
        ),
        encoding="utf-8",
    )
    return {"defaults": defaults, "overrides": tmp_path / "courses" / "Chalk links.json"}


def test_the_bundled_file_lists_every_link_chalk_uses():
    keys = {link.key for link in links.load_links(overrides=links.LINKS_FILE.parent / "missing.json")}

    assert {"academic_calendars", "class_schedule", "canvas_student_guides", "disability_center"} <= keys
    for link in links.load_links(overrides=links.LINKS_FILE.parent / "missing.json"):
        assert link.url.startswith("https://") and link.label and link.used_for


def test_links_come_from_the_bundled_file_until_changed(files):
    assert links.url_for("schedule", **files) == "https://schedule.example.edu/"
    assert not any(link.is_changed for link in links.load_links(**files))


def test_a_saved_change_wins_and_is_marked(files):
    changed = links.save_links(
        {"calendars": "https://registrar.example.edu/", "schedule": " https://new.example.edu/rooms "}, **files
    )

    assert changed == ["schedule"]
    assert links.url_for("schedule", **files) == "https://new.example.edu/rooms"
    assert [link.key for link in links.load_links(**files) if link.is_changed] == ["schedule"]
    # Only the changed link is stored, so a later fix to the bundled calendars link still applies.
    assert json.loads(files["overrides"].read_text(encoding="utf-8")) == {"schedule": "https://new.example.edu/rooms"}


def test_setting_every_link_back_removes_the_changes_file(files):
    links.save_links({"schedule": "https://new.example.edu/"}, **files)

    assert links.save_links({"schedule": "https://schedule.example.edu/"}, **files) == []
    assert not files["overrides"].exists()


@pytest.mark.parametrize("bad", ["", "schedule.example.edu", "javascript:alert(1)", "ftp://x.edu/"])
def test_a_bad_address_is_refused_and_nothing_is_saved(files, bad):
    with pytest.raises(ChalkError, match="isn't a web address"):
        links.save_links({"calendars": "https://ok.example.edu/", "schedule": bad}, **files)

    assert not files["overrides"].exists()


def test_a_damaged_changes_file_is_ignored(files):
    files["overrides"].parent.mkdir()
    files["overrides"].write_text("{not json", encoding="utf-8")

    assert links.url_for("calendars", **files) == "https://registrar.example.edu/"


def test_an_unknown_key_is_a_programming_error(files):
    with pytest.raises(KeyError):
        links.url_for("nope", **files)


def test_unknown_keys_are_not_saved(files):
    assert links.save_links({"nope": "https://x.example.edu/"}, **files) == []
