import datetime as dt

from chalk.archiving import archive_before_write
from chalk.metrics import read_events_by_type


def test_returns_none_when_there_is_nothing_to_archive(tmp_path):
    assert archive_before_write(tmp_path / "syllabus.docx") is None


def test_moves_the_existing_file_into_a_dot_archive_directory(tmp_path):
    path = tmp_path / "outputs" / "syllabus.docx"
    path.parent.mkdir(parents=True)
    path.write_text("original content", encoding="utf-8")

    archived_path = archive_before_write(path, now=dt.datetime(2026, 9, 23, 10, 30, 0))

    assert archived_path == tmp_path / "outputs" / ".archive" / "syllabus-20260923-103000.docx"
    assert archived_path.read_text(encoding="utf-8") == "original content"
    assert not path.exists()


def test_logs_an_archive_event_when_eval_log_path_given(tmp_path):
    path = tmp_path / "syllabus.docx"
    path.write_text("v1", encoding="utf-8")
    log_path = tmp_path / "eval-log.json"

    archive_before_write(path, eval_log_path=log_path, now=dt.datetime(2026, 9, 23, 10, 30, 0))

    events = read_events_by_type(log_path, "archive")
    assert len(events) == 1
    assert events[0]["original_path"] == str(path)


def test_no_event_logged_when_nothing_was_archived(tmp_path):
    log_path = tmp_path / "eval-log.json"
    archive_before_write(tmp_path / "does-not-exist.docx", eval_log_path=log_path)
    assert not log_path.exists()


def test_multiple_archives_of_the_same_filename_do_not_collide(tmp_path):
    path = tmp_path / "syllabus.docx"
    path.write_text("v1", encoding="utf-8")
    archive_before_write(path, now=dt.datetime(2026, 9, 23, 10, 0, 0))

    path.write_text("v2", encoding="utf-8")
    archive_before_write(path, now=dt.datetime(2026, 9, 23, 11, 0, 0))

    archive_dir = tmp_path / ".archive"
    archived_files = sorted(p.name for p in archive_dir.iterdir())
    assert archived_files == ["syllabus-20260923-100000.docx", "syllabus-20260923-110000.docx"]
