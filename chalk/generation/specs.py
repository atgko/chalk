"""The content types Chalk can generate (F-05a-e), as data.

Each ContentSpec says which prompt template to use, which `{variables}`
that template must contain, where output is saved, and the max_tokens
ceiling (also the output-token assumption in the pre-generation cost
estimate — DECISIONS.md). Adding a content type means adding a spec, a
template in resources/prompts/, and nothing else in the engine.
"""

from __future__ import annotations

from dataclasses import dataclass

COMMON_VARIABLES = ("course_title", "learning_objectives", "source_material_context")


@dataclass(frozen=True)
class ContentSpec:
    key: str
    label: str
    output_subdir: str
    required_variables: tuple[str, ...]
    max_tokens: int
    per_week: bool = True

    @property
    def template_name(self) -> str:
        return f"{self.key}.txt"


SPECS: dict[str, ContentSpec] = {
    spec.key: spec
    for spec in (
        ContentSpec(
            key="quiz",
            label="Quiz",
            output_subdir="quizzes",
            required_variables=(*COMMON_VARIABLES, "week_number", "topics", "question_count", "format"),
            max_tokens=2000,
        ),
        ContentSpec(
            key="discussion",
            label="Discussion prompts",
            output_subdir="discussions",
            required_variables=(*COMMON_VARIABLES, "week_number", "topics", "prompt_count"),
            max_tokens=1200,
        ),
        ContentSpec(
            key="rubric",
            label="Rubric",
            output_subdir="rubrics",
            required_variables=(*COMMON_VARIABLES, "assignment_name", "assignment_description", "total_points"),
            max_tokens=1500,
            per_week=False,
        ),
        ContentSpec(
            key="summary",
            label="Module summary",
            output_subdir="summaries",
            required_variables=(*COMMON_VARIABLES, "week_number", "topics"),
            max_tokens=1500,
        ),
        ContentSpec(
            key="slides",
            label="Slides",
            output_subdir="slides",
            required_variables=(*COMMON_VARIABLES, "week_number", "topics", "slide_notes"),
            max_tokens=2500,
        ),
    )
}

QUIZ_FORMATS = ("multiple choice", "short answer", "mixed")
DEFAULT_QUESTION_COUNT = 5
DEFAULT_PROMPT_COUNT = 3
DEFAULT_RUBRIC_POINTS = 100
