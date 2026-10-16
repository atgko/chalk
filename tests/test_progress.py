"""chalk.progress: the helpers long operations use to report progress."""

import pytest

from chalk.progress import CHARS_PER_TOKEN, WRITING_STEP, report, within, writing_progress


def _recorder():
    reports: list = []
    return reports, lambda fraction, step: reports.append((fraction, step))


def test_report_without_a_callback_does_nothing():
    report(None, 0.5, "Halfway")  # the CLI and tests pass no callback


def test_report_passes_the_fraction_and_step_on():
    reports, on_progress = _recorder()
    report(on_progress, None, "Reading the PDF's pages")
    assert reports == [(None, "Reading the PDF's pages")]


def test_within_maps_a_part_onto_its_stretch_of_the_bar():
    reports, on_progress = _recorder()
    part = within(on_progress, 0.0, 0.9)

    part(0.5, "The AI is writing")
    part(None, "Waiting")

    assert reports == [(pytest.approx(0.45), "The AI is writing"), (None, "Waiting")]
    assert within(None, 0.0, 0.9) is None


def test_writing_progress_measures_the_reply_against_the_expected_length():
    reports, on_progress = _recorder()
    on_text = writing_progress(on_progress, expected_tokens=100)

    on_text(100 * CHARS_PER_TOKEN // 4)

    assert reports == [(pytest.approx(0.25), WRITING_STEP)]


def test_writing_progress_never_shows_an_unfinished_reply_as_done():
    reports, on_progress = _recorder()
    on_text = writing_progress(on_progress, expected_tokens=100)

    on_text(100 * CHARS_PER_TOKEN * 3)  # three times longer than expected

    assert reports[-1][0] < 1


def test_writing_progress_without_a_callback_asks_for_no_stream():
    assert writing_progress(None, expected_tokens=100) is None
