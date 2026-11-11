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
    assert len(tabs) == len(set(tabs)) == 10
    assert session.group_of("Generate") == "Build"
    assert session.group_of("Metrics") == "Settings"


def test_a_requested_tab_sets_both_rows_of_tabs(state):
    session.go_to_tab("Metrics")
    session.apply_tab_request()

    assert state[session.ACTIVE_TAB_KEY] == "Metrics"
    assert state[session.tabs_widget_key(session.GROUP_TAB_KEY)] == "Settings"
    assert state[session.tabs_widget_key(session.SUB_TAB_KEYS["Settings"])] == "Metrics"


def test_with_nothing_open_the_upload_tab_opens(state):
    session.apply_tab_request()

    assert (state[session.ACTIVE_TAB_KEY], state[session.tabs_widget_key(session.GROUP_TAB_KEY)]) == ("Upload", "Build")


def test_a_group_opens_its_first_tab_and_then_the_one_it_showed_last(state):
    state[session.tabs_widget_key(session.GROUP_TAB_KEY)] = "Settings"
    session.on_group_change()
    assert state[session.ACTIVE_TAB_KEY] == "AI Provider"

    state[session.tabs_widget_key(session.SUB_TAB_KEYS["Settings"])] = "Metrics"
    session.on_sub_tab_change(session.tabs_widget_key(session.SUB_TAB_KEYS["Settings"]))
    assert state[session.ACTIVE_TAB_KEY] == "Metrics"

    state[session.tabs_widget_key(session.GROUP_TAB_KEY)] = "Grading Assistant"
    session.on_group_change()
    assert state[session.ACTIVE_TAB_KEY] == "Grading Assistant"

    state[session.tabs_widget_key(session.GROUP_TAB_KEY)] = "Settings"
    session.on_group_change()
    assert state[session.ACTIVE_TAB_KEY] == "Metrics"


class _StrictState(dict):
    """Rejects an empty key, as Streamlit's session state does."""

    def get(self, key, default=None):
        if not isinstance(key, str) or not key:
            raise ValueError("Invalid `key` value. Supported values: a non-empty string.")
        return super().get(key, default)


def test_a_group_without_a_second_row_opens_without_an_empty_key_lookup(monkeypatch):
    state = _StrictState({session.tabs_widget_key(session.GROUP_TAB_KEY): "Grading Assistant"})
    monkeypatch.setattr(session.st, "session_state", state)

    session.on_group_change()

    assert state[session.ACTIVE_TAB_KEY] == "Grading Assistant"


def test_a_tab_click_during_an_interrupted_run_leaves_the_open_tab_alone(state):
    """A click while a slow run hasn't redrawn the tabs yet (UAT, Nov 4):
    Streamlit calls the callbacks with the tabs' keys missing."""
    state[session.ACTIVE_TAB_KEY] = "Rollover"

    session.on_group_change()
    session.on_sub_tab_change(session.tabs_widget_key(session.SUB_TAB_KEYS["Build"]))

    assert state[session.ACTIVE_TAB_KEY] == "Rollover"


def test_a_group_shows_the_most_pressing_mark_of_its_tabs():
    assert background._strongest(["done", None, "running"]) == "running"
    assert background._strongest(["done", "failed"]) == "failed"
    assert background._strongest([None]) is None


def test_group_tab_styles_skip_the_tabs_inside_them():
    css = background.tab_marks_css(
        ("Build", "Settings"), "group", {"Build": "running"}, nested_keys=("build", "settings")
    )
    assert '.st-key-group [data-testid="stTab"]:nth-of-type(1):not(.st-key-build *):not(.st-key-settings *)' in css


def test_a_tab_name_from_before_the_grouping_opens_upload(state):
    state[session.ACTIVE_TAB_KEY] = "Settings"  # the old Settings tab
    session.apply_tab_request()

    assert (state[session.ACTIVE_TAB_KEY], state[session.tabs_widget_key(session.GROUP_TAB_KEY)]) == ("Upload", "Build")


def test_a_tab_the_app_opens_gets_new_tabs_widgets(state):
    """Nov 11 UAT: Confirm and save opened Rollover, but the browser's tabs
    widget still held Review and sent it back with the Preview rollover
    click. The app's own switch now keys the tabs widgets anew, so a value
    the browser kept from before it can't reopen the old tab."""
    state[session.ACTIVE_TAB_KEY] = "Review"
    assert session.apply_tab_request() is False
    build_key = session.tabs_widget_key(session.SUB_TAB_KEYS["Build"])

    session.go_to_tab("Rollover")
    assert session.apply_tab_request() is True

    new_key = session.tabs_widget_key(session.SUB_TAB_KEYS["Build"])
    assert new_key != build_key
    assert state[new_key] == "Rollover"
    state[build_key] = "Review"  # what the browser's old widget still holds
    session.on_sub_tab_change(new_key)
    assert state[session.ACTIVE_TAB_KEY] == "Rollover"
