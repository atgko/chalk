from ui.workflow_search import search_workflows


def test_empty_search_returns_popular_starting_points():
    assert [workflow.key for workflow in search_workflows("")] == [
        "upload-syllabus",
        "review-course",
        "rollover-course",
        "generate-quiz",
    ]


def test_quiz_search_returns_the_quiz_generation_workflow():
    matches = search_workflows("Quiz")
    assert matches[0].key == "generate-quiz"
    assert matches[0].label == "Quiz generation"
    assert matches[0].tab == "Generate"
    assert matches[0].generation_type == "quiz"


def test_search_uses_plain_language_synonyms_and_all_words():
    assert [workflow.key for workflow in search_workflows("new semester dates")] == [
        "rollover-course"
    ]
    assert [workflow.key for workflow in search_workflows("PowerPoint outline")] == [
        "generate-slides"
    ]
    assert search_workflows("quiz canvas") == []


def test_every_workflow_opens_a_real_tab():
    from ui.shell import TAB_NAMES
    from ui.workflow_search import WORKFLOWS

    assert {workflow.tab for workflow in WORKFLOWS} <= set(TAB_NAMES)


def test_grading_search_finds_the_grading_assistant():
    matches = search_workflows("grade a submission")
    assert [workflow.key for workflow in matches] == ["grade-submission"]
    assert matches[0].tab == "Grading Assistant"


def test_drafts_search_finds_saved_generated_files():
    assert [workflow.key for workflow in search_workflows("saved drafts")] == ["view-drafts"]


def test_session_search_finds_the_rollover():
    assert [workflow.key for workflow in search_workflows("5-week session")] == [
        "rollover-course"
    ]
