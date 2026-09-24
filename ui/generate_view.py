"""Generate tab (PRD section 7.2 / F-05): choose a content type and its
options, see the cost estimate, generate a draft, review it inline, then
Save (archiving any previous version), Regenerate (after confirming the
new paid call), or Discard."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from chalk.config import describe_provider
from chalk.costs import format_cost
from chalk.errors import ChalkError
from chalk.generation.engine import (
    GeneratedDraft,
    GenerationRequest,
    current_env,
    estimate_cost,
    generate,
    overwrite_warning,
    save_draft,
)
from chalk.generation.source_context import read_source_text
from chalk.generation.specs import (
    DEFAULT_PROMPT_COUNT,
    DEFAULT_QUESTION_COUNT,
    DEFAULT_RUBRIC_POINTS,
    QUIZ_FORMATS,
    SPECS,
    ContentSpec,
)
from chalk.models import CourseData
from chalk.project import ProjectPaths, list_source_files
from ui import common, session
from ui.upload_view import save_upload


def render(paths: ProjectPaths, course_data: CourseData) -> None:
    draft = session.get_draft()
    if draft is not None:
        _render_draft(paths, course_data, draft)
        return

    if describe_provider(current_env()) == "Not configured":
        st.info("Connect an AI provider in the Settings tab to generate content.")
        return

    spec = SPECS[st.selectbox("Content type", list(SPECS), format_func=lambda key: SPECS[key].label)]
    request = _request_form(paths, course_data, spec)

    try:
        estimate = estimate_cost(paths, course_data, request)
    except ChalkError as exc:
        st.caption(exc.user_message)
        return
    st.caption(f"Estimated cost: {format_cost(estimate, prefix='up to ~')}")

    warning = overwrite_warning(paths, request)
    confirmed = True
    if warning:
        st.warning(warning)
        confirmed = st.checkbox("Yes — archive the old version and generate a new one")

    if st.button("Generate", type="primary", disabled=not confirmed):
        _run(paths, course_data, request)


def _request_form(paths: ProjectPaths, course_data: CourseData, spec: ContentSpec) -> GenerationRequest:
    fields: dict = {"content_type": spec.key}
    if spec.per_week:
        weeks = {w.week_number: w for w in course_data.weeks if not w.is_break}
        fields["week_number"] = st.selectbox(
            "Week",
            list(weeks),
            format_func=lambda n: f"Week {n} — {'; '.join(weeks[n].topics) or 'no topics listed'}",
        )
    if spec.key == "quiz":
        fields["question_count"] = int(st.number_input("Questions", 1, 50, DEFAULT_QUESTION_COUNT))
        fields["quiz_format"] = st.selectbox("Format", QUIZ_FORMATS, index=QUIZ_FORMATS.index("mixed"))
    elif spec.key == "discussion":
        fields["prompt_count"] = int(st.number_input("Prompts", 1, 20, DEFAULT_PROMPT_COUNT))
    elif spec.key == "rubric":
        fields |= _rubric_fields()
    elif spec.key == "slides":
        fields["slide_notes"] = st.text_area("Bullet points or a reading excerpt (optional)")

    syllabus_name = Path(course_data.course.source_file).name
    materials = [name for name in list_source_files(paths) if name != syllabus_name]
    if materials:
        fields["source_files"] = tuple(st.multiselect("Source materials to use", materials))
    else:
        st.caption("No source materials added yet — generation will use course topics and objectives only.")
    return GenerationRequest(**fields)


def _rubric_fields() -> dict:
    name = st.text_input("Assignment name", placeholder="Lab 3: VLANs")
    description = st.text_area("Assignment description")
    uploaded = st.file_uploader(
        "…or upload the assignment description", type=["pdf", "docx", "md", "txt"], key="rubric-upload"
    )
    if uploaded is not None:
        description = read_source_text(save_upload(uploaded.name, uploaded.getvalue()))
    points = int(st.number_input("Total points", 1, 1000, DEFAULT_RUBRIC_POINTS))
    return {"assignment_name": name, "assignment_description": description, "total_points": points}


def _run(paths: ProjectPaths, course_data: CourseData, request: GenerationRequest) -> None:
    try:
        with st.spinner("Generating — this can take a minute…"):
            draft = generate(paths, course_data, request)
    except ChalkError as exc:
        st.error(exc.user_message)
        return
    session.set_draft(draft)
    st.rerun()


def _render_draft(paths: ProjectPaths, course_data: CourseData, draft: GeneratedDraft) -> None:
    st.subheader(f"Draft for review — {common.relative(draft.output_path, paths)}")
    st.caption(
        f"{draft.model} · {draft.input_tokens:,} tokens in / {draft.output_tokens:,} out · "
        f"Cost: {format_cost(draft.cost_usd)}"
    )
    if draft.request.content_type == "slides":
        st.code(draft.text, language="markdown")
    else:
        with st.container(border=True):
            st.markdown(draft.text)

    if session.regenerate_requested():
        st.warning("Generate a new version? This makes another paid call. The current draft will be discarded.")
        go_col, keep_col = st.columns(2)
        if go_col.button("Yes, regenerate", type="primary"):
            _run(paths, course_data, draft.request)
        if keep_col.button("Keep this draft"):
            session.request_regenerate(False)
            st.rerun()
        return

    save_col, regenerate_col, discard_col = st.columns(3)
    if save_col.button("Save", type="primary"):
        saved = save_draft(paths, draft)
        session.set_draft(None)
        session.flash(f"Saved {common.relative(saved, paths)}. Previous versions, if any, were archived.")
        st.rerun()
    if regenerate_col.button("Regenerate"):
        session.request_regenerate(True)
        st.rerun()
    if discard_col.button("Discard"):
        session.set_draft(None)
        st.rerun()
