"""Tests for chalk.generation.engine (F-05a-e) with a mocked LLM: prompt
assembly, the AI-draft banner, output paths, cost + metrics logging,
save-with-archive, and the overwrite warning."""

import datetime as dt

import pytest

from chalk import metrics
from chalk.errors import GenerationError, LLMProviderError
from chalk.generation.engine import (
    SYSTEM_PROMPT,
    GenerationRequest,
    build_prompt,
    estimate_cost,
    generate,
    output_path_for,
    overwrite_warning,
    save_draft,
    spec_for,
)
from tests.sample_course import build_sample_course_data

TODAY = dt.date(2026, 9, 24)


@pytest.fixture
def llm(monkeypatch):
    """Mocked chalk.generation.engine.complete; `llm.reply` sets the text,
    `llm.calls` records (prompt, system, max_tokens)."""

    class _Llm:
        reply = "## Questions\nQ1. What is a subnet?\n\n## Answer Key\nA1. A network slice."
        calls: list = []

        def __call__(self, prompt, system="", max_tokens=2000):
            self.calls.append((prompt, system, max_tokens))
            return {"text": self.reply, "input_tokens": 1200, "output_tokens": 400}

    fake = _Llm()
    fake.calls = []
    monkeypatch.setattr("chalk.generation.engine.complete", fake)
    for key, value in {"LLM_PROVIDER": "openai", "LLM_API_KEY": "sk", "LLM_MODEL": "gpt-4o"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    return fake


@pytest.fixture
def course():
    return build_sample_course_data()


# ---- Prompt assembly ----------------------------------------------------------------------


def test_quiz_prompt_carries_week_topics_objectives_and_options(tmp_project, course):
    prompt = build_prompt(
        tmp_project, course, GenerationRequest("quiz", week_number=3, question_count=7, quiz_format="short answer")
    )
    assert "IS 6640 Networking and Servers" in prompt
    assert "Week 3 covers: Topic 3A; Topic 3B" in prompt
    assert "- Configure and secure Linux servers" in prompt
    assert "Generate 7 questions in short answer format." in prompt
    assert "No source materials were provided" in prompt
    assert "{" not in prompt


def test_prompt_includes_selected_source_material(tmp_project, course):
    (tmp_project.source_dir / "ch3.txt").write_text("CIDR notation explained", encoding="utf-8")
    prompt = build_prompt(tmp_project, course, GenerationRequest("summary", week_number=3, source_files=("ch3.txt",)))
    assert "CIDR notation explained" in prompt


def test_course_without_objectives_says_so(tmp_project, course):
    prompt = build_prompt(
        tmp_project, course.model_copy(update={"learning_objectives": []}), GenerationRequest("summary", week_number=1)
    )
    assert "(none listed in the syllabus)" in prompt


def test_week_without_topics_says_so(tmp_project, course):
    weeks = [w.model_copy(update={"topics": []}) if w.week_number == 2 else w for w in course.weeks]
    prompt = build_prompt(tmp_project, course.model_copy(update={"weeks": weeks}), GenerationRequest("summary", week_number=2))
    assert "(no topics listed for this week)" in prompt


def test_discussion_prompt_asks_for_leveled_prompts(tmp_project, course):
    prompt = build_prompt(tmp_project, course, GenerationRequest("discussion", week_number=2, prompt_count=4))
    assert "Write 4 discussion prompts" in prompt
    for level in ("Recall", "Application", "Analysis"):
        assert level in prompt


def test_rubric_prompt_forbids_grading(tmp_project, course):
    prompt = build_prompt(
        tmp_project,
        course,
        GenerationRequest("rubric", assignment_name="Lab 3", assignment_description="Build a VLAN", total_points=50),
    )
    assert "Assignment: Lab 3" in prompt and "Build a VLAN" in prompt and "worth 50 points" in prompt
    assert "Do not grade, score, or evaluate any student work" in prompt
    assert "Never grade, score, or evaluate student work." in SYSTEM_PROMPT


def test_slides_prompt_uses_notes_or_a_fallback(tmp_project, course):
    with_notes = build_prompt(tmp_project, course, GenerationRequest("slides", week_number=1, slide_notes="OSI layers"))
    without = build_prompt(tmp_project, course, GenerationRequest("slides", week_number=1))
    assert "OSI layers" in with_notes
    assert "(none — use the week's topics)" in without
    assert ":::: {.columns}" in without


@pytest.mark.parametrize(
    ("request_", "message"),
    [
        (GenerationRequest("quiz", week_number=42), "Week 42 isn't in this course's schedule"),
        (GenerationRequest("quiz", week_number=1, question_count=0), "Question count must be at least 1"),
        (GenerationRequest("quiz", week_number=1, quiz_format="essay"), "Quiz format must be one of"),
        (GenerationRequest("discussion", week_number=1, prompt_count=0), "Prompt count must be at least 1"),
        (GenerationRequest("rubric", assignment_name="Lab"), "needs an assignment name and a description"),
        (
            GenerationRequest("rubric", assignment_name="Lab", assignment_description="x", total_points=0),
            "Total points must be at least 1",
        ),
        (GenerationRequest("poem", week_number=1), "Unknown content type 'poem'"),
    ],
)
def test_invalid_requests_are_plain_errors(tmp_project, course, request_, message):
    with pytest.raises(GenerationError, match=message):
        build_prompt(tmp_project, course, request_)


# ---- Output paths / overwrite -------------------------------------------------------------


@pytest.mark.parametrize(
    ("request_", "relative"),
    [
        (GenerationRequest("quiz", week_number=3), "outputs/quizzes/week-3-quiz.md"),
        (GenerationRequest("discussion", week_number=3), "outputs/discussions/week-3-discussion.md"),
        (GenerationRequest("summary", week_number=3), "outputs/summaries/week-3-summary.md"),
        (GenerationRequest("slides", week_number=3), "outputs/slides/week-3-slides.md"),
        (GenerationRequest("rubric", assignment_name="Lab 3: VLANs & Trunks!"), "outputs/rubrics/lab-3-vlans-trunks-rubric.md"),
        (GenerationRequest("rubric", assignment_name="???"), "outputs/rubrics/assignment-rubric.md"),
    ],
)
def test_output_paths_follow_the_prd(tmp_project, request_, relative):
    assert output_path_for(tmp_project, request_) == tmp_project.root / relative


def test_overwrite_warning_uses_the_prd_wording(tmp_project):
    request_ = GenerationRequest("quiz", week_number=3)
    assert overwrite_warning(tmp_project, request_) is None

    output_path_for(tmp_project, request_).write_text("old", encoding="utf-8")

    assert overwrite_warning(tmp_project, request_) == (
        "A quiz already exists for Week 3. Generating a new one will archive the old version. Continue?"
    )


def test_overwrite_warning_for_a_rubric_names_the_assignment(tmp_project):
    request_ = GenerationRequest("rubric", assignment_name="Lab 3")
    output_path_for(tmp_project, request_).write_text("old", encoding="utf-8")
    assert overwrite_warning(tmp_project, request_).startswith("A rubric already exists for “Lab 3”.")


# ---- Generate / save ----------------------------------------------------------------------


def test_generate_returns_a_bannered_draft_without_writing_it(tmp_project, course, llm):
    draft = generate(tmp_project, course, GenerationRequest("quiz", week_number=3), today=TODAY)

    assert draft.text.startswith(
        "> **AI-generated draft** — review and edit before use. Generated 2026-09-24 using gpt-4o.\n\n## Questions"
    )
    assert draft.output_path == tmp_project.outputs_dir / "quizzes" / "week-3-quiz.md"
    assert not draft.output_path.exists()
    prompt, system, max_tokens = llm.calls[0]
    assert system == SYSTEM_PROMPT
    assert max_tokens == spec_for("quiz").max_tokens


def test_generate_logs_tokens_and_cost_but_never_content(tmp_project, course, llm):
    draft = generate(tmp_project, course, GenerationRequest("quiz", week_number=3, source_files=()), today=TODAY)

    event = metrics.read_events_by_type(tmp_project.eval_log, "generation")[-1]
    assert event["content_type"] == "quiz"
    assert event["week_number"] == 3
    assert event["output_file"] == "outputs/quizzes/week-3-quiz.md"
    assert (event["input_tokens"], event["output_tokens"]) == (1200, 400)
    assert event["cost_usd"] == pytest.approx(1.2 * 0.0025 + 0.4 * 0.010)
    assert draft.cost_usd == event["cost_usd"]
    assert "subnet" not in tmp_project.eval_log.read_text(encoding="utf-8")


def test_generate_with_an_unpriced_model_logs_unknown_cost(tmp_project, course, llm, monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "gpt-unlisted")
    draft = generate(tmp_project, course, GenerationRequest("summary", week_number=1), today=TODAY)
    assert draft.cost_usd is None
    assert metrics.read_events_by_type(tmp_project.eval_log, "generation")[-1]["cost_usd"] is None


def test_rubric_events_have_no_week_number(tmp_project, course, llm):
    generate(tmp_project, course, GenerationRequest("rubric", assignment_name="Lab", assignment_description="x"))
    assert metrics.read_events_by_type(tmp_project.eval_log, "generation")[-1]["week_number"] is None


def test_generate_strips_a_wrapping_code_fence(tmp_project, course, llm):
    llm.reply = "```markdown\n## Key concepts\n- one\n```"
    draft = generate(tmp_project, course, GenerationRequest("summary", week_number=1), today=TODAY)
    assert "```" not in draft.text
    assert draft.text.endswith("## Key concepts\n- one\n")


def test_generated_slides_follow_the_pipeline_conventions(tmp_project, course, llm):
    llm.reply = "# Networking\n- intro\n## Layers\n- OSI"
    draft = generate(tmp_project, course, GenerationRequest("slides", week_number=1), today=TODAY)

    assert draft.text.startswith('---\ntitle: "Week 1: Topic 1A; Topic 1B"\nauthor: "Dave Norwood"\n---\n')
    assert "<!-- AI-generated draft — review and edit before use. Generated 2026-09-24 using gpt-4o. -->" in draft.text
    assert "<!-- Slide 2 -->\n## Layers" in draft.text
    assert "\n# " not in draft.text


def test_llm_failure_propagates_and_logs_nothing(tmp_project, course, monkeypatch):
    def _down(prompt, system="", max_tokens=2000):
        raise LLMProviderError("Could not reach the LLM provider.")

    monkeypatch.setattr("chalk.generation.engine.complete", _down)
    with pytest.raises(LLMProviderError):
        generate(tmp_project, course, GenerationRequest("quiz", week_number=1))
    assert metrics.read_events_by_type(tmp_project.eval_log, "generation") == []


def test_save_draft_writes_and_archives_the_previous_version(tmp_project, course, llm):
    request_ = GenerationRequest("quiz", week_number=3)
    first = generate(tmp_project, course, request_, today=TODAY)
    save_draft(tmp_project, first)
    llm.reply = "## Questions\nQ1. Second version"
    second = generate(tmp_project, course, request_, today=TODAY)

    path = save_draft(tmp_project, second)

    assert "Second version" in path.read_text(encoding="utf-8")
    archived = list((path.parent / ".archive").iterdir())
    assert len(archived) == 1 and "What is a subnet?" in archived[0].read_text(encoding="utf-8")
    assert metrics.read_events_by_type(tmp_project.eval_log, "archive")


def test_unknown_model_name_in_the_banner_when_env_is_missing(tmp_project, course, llm, monkeypatch):
    monkeypatch.delenv("LLM_MODEL")
    draft = generate(tmp_project, course, GenerationRequest("summary", week_number=1), today=TODAY)
    assert "using unknown model." in draft.text


# ---- Estimate ------------------------------------------------------------------------------


def test_estimate_is_an_upper_bound_from_prompt_length_and_max_tokens(tmp_project, course, llm):
    request_ = GenerationRequest("quiz", week_number=3)
    prompt_tokens = len(SYSTEM_PROMPT + build_prompt(tmp_project, course, request_)) // 4
    expected = prompt_tokens / 1000 * 0.0025 + 2000 / 1000 * 0.010
    assert estimate_cost(tmp_project, course, request_) == pytest.approx(expected)
    assert llm.calls == []  # estimating never calls the LLM
