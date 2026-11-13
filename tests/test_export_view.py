"""The Export tab's file list (UAT, Nov 4: "Download outputs/canvas.html"
buttons in one long list read as a mess): files grouped by what they are,
each with a plain name."""

from ui.export_view import output_sections


def _make(paths, *relative_paths):
    files = []
    for relative in relative_paths:
        path = paths.outputs_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
        files.append(path)
    return files


def test_outputs_are_grouped_and_named_plainly(tmp_project):
    files = _make(
        tmp_project,
        "canvas.html",
        "course-brief.md",
        "quizzes/week-1-quiz.md",
        "rubrics/final-project-rubric.md",
        "syllabus.pdf",
        "syllabus.docx",
    )

    sections = output_sections(files, tmp_project)

    assert [(title, [label for label, _ in items]) for title, items in sections] == [
        ("Syllabus", ["Syllabus (Word)", "Syllabus (PDF)"]),
        ("Course materials", ["Week 1 quiz", "Final project rubric"]),
        ("Course brief", ["Course brief"]),
    ]


def test_the_canvas_page_has_no_download_button(tmp_project):
    # It goes on Canvas from the copy box; the file alone opens as code (Nov 12).
    files = _make(tmp_project, "canvas.html")

    assert output_sections(files, tmp_project) == []


def test_an_unfamiliar_file_is_still_listed(tmp_project):
    files = _make(tmp_project, "notes.txt")

    assert output_sections(files, tmp_project) == [("Other files", [("notes.txt", files[0])])]


def test_empty_sections_are_left_out(tmp_project):
    files = _make(tmp_project, "syllabus.md")

    assert output_sections(files, tmp_project) == [("Syllabus", [("Syllabus (Markdown)", files[0])])]
