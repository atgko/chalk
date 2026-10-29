"""The tabs grouped by purpose (sponsor meeting, Oct 28): Build, Grading
Assistant, and Settings, with a second row of tabs for a group that has
several (ui/session.py, ui/background.py)."""

import pytest

from ui import background, session


@pytest.fixture
def state(monkeypatch):
    """Session state as a plain dict, which is all these functions use."""
    fake: dict = {}
    monkeypatch.setattr(session.st, "session_state", fake)
    return fake


def test_every_tab_is_in_exactly_one_group():
    tabs = [tab for group in session.TAB_GROUPS.values() for tab in group]
    assert len(tabs) == len(set(tabs)) == 9
    assert session.group_of("Generate") == "Build"
    assert session.group_of("Metrics") == "Settings"


def test_a_requested_tab_sets_both_rows_of_tabs(state):
    session.go_to_tab("Metrics")
    session.apply_tab_request()

    assert state[session.ACTIVE_TAB_KEY] == "Metrics"
    assert state[session.GROUP_TAB_KEY] == "Settings"
    assert state[session.SUB_TAB_KEYS["Settings"]] == "Metrics"


def test_with_nothing_open_the_upload_tab_opens(state):
    session.apply_tab_request()

    assert (state[session.ACTIVE_TAB_KEY], state[session.GROUP_TAB_KEY]) == ("Upload", "Build")


def test_a_group_opens_its_first_tab_and_then_the_one_it_showed_last(state):
    state[session.GROUP_TAB_KEY] = "Settings"
    session.on_group_change()
    assert state[session.ACTIVE_TAB_KEY] == "AI Provider"

    state[session.SUB_TAB_KEYS["Settings"]] = "Metrics"
    session.on_sub_tab_change(session.SUB_TAB_KEYS["Settings"])
    assert state[session.ACTIVE_TAB_KEY] == "Metrics"

    state[session.GROUP_TAB_KEY] = "Grading Assistant"
    session.on_group_change()
    assert state[session.ACTIVE_TAB_KEY] == "Grading Assistant"

    state[session.GROUP_TAB_KEY] = "Settings"
    session.on_group_change()
    assert state[session.ACTIVE_TAB_KEY] == "Metrics"


def test_a_group_shows_the_most_pressing_mark_of_its_tabs():
    assert background._strongest(["done", None, "running"]) == "running"
    assert background._strongest(["done", "failed"]) == "failed"
    assert background._strongest([None]) is None


def test_group_tab_styles_skip_the_tabs_inside_them():
    css = background.tab_marks_css(
        ("Build", "Settings"), "group", {"Build": "running"}, nested_keys=("build", "settings")
    )
    assert '.st-key-group [data-testid="stTab"]:nth-of-type(1):not(.st-key-build *):not(.st-key-settings *)' in css
