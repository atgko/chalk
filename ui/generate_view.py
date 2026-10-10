"""Generate tab (PRD section 7.2 / F-05): choose a content type and its
options, see the cost estimate, generate a draft, review it inline, then
Save (archiving any previous version), Regenerate (after confirming the
new paid call), or Discard."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
from chalk.generation.assignment_export import export_assignment

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
    DEFAULT_MIXED_SPLIT,
    DEFAULT_PROMPT_COUNT,
    DEFAULT_QUESTION_COUNT,
    DEFAULT_RUBRIC_POINTS,
    QUIZ_FORMATS,
    SPECS,
    ContentSpec,
)
from chalk.models import CourseData
from chalk.project import SOURCE_SUFFIXES, ProjectPaths, add_source, list_source_files
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
        fields |= _quiz_fields()
    elif spec.key == "discussion":
        fields["prompt_count"] = int(st.number_input("Prompts", 1, 20, DEFAULT_PROMPT_COUNT))
    elif spec.key == "assignment":
        fields |= _assignment_fields()
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
    _render_source_uploader(paths)
    return GenerationRequest(**fields)


def _quiz_fields() -> dict:
    quiz_format = st.selectbox("Format", QUIZ_FORMATS, index=QUIZ_FORMATS.index("mixed"))
    if quiz_format != "mixed":
        count = int(st.number_input("Questions", 1, 50, DEFAULT_QUESTION_COUNT))
        return {"quiz_format": quiz_format, "question_count": count}

    mc_col, sa_col = st.columns(2)
    multiple_choice = int(mc_col.number_input("Multiple choice", 1, 49, DEFAULT_MIXED_SPLIT[0]))
    short_answer = int(sa_col.number_input("Short answer", 1, 49, DEFAULT_MIXED_SPLIT[1]))
    st.caption(f"{multiple_choice + short_answer} questions in total.")
    return {
        "quiz_format": quiz_format,
        "question_count": multiple_choice + short_answer,
        "multiple_choice_count": multiple_choice,
        "short_answer_count": short_answer,
    }


def _render_source_uploader(paths: ProjectPaths) -> None:
    with st.expander("Add source materials"):
        files = st.file_uploader(
            "Your summaries, notes, or excerpts (PDF, DOCX, MD, TXT)",
            type=[suffix.lstrip(".") for suffix in SOURCE_SUFFIXES],
            accept_multiple_files=True,
            key="source-upload",
        )
        st.caption(common.FERPA_NOTICE)
        if st.button("Add to project", disabled=not files):
            try:
                added = [add_source(paths, save_upload(f.name, f.getvalue())).name for f in files]
            except ChalkError as exc:
                st.error(exc.user_message)
                return
            session.flash(f"Added to source/: {', '.join(added)}.")
            st.rerun()


def _assignment_fields() -> dict:
    st.markdown("### Assignment Creator / Enhancer")
    mode_label = st.radio(
        "What would you like to do?",
        ("Create a new assignment", "Improve an existing assignment"),
        horizontal=True,
    )
    mode = "create" if mode_label.startswith("Create") else "enhance"
    name = st.text_input("Assignment name", placeholder="Network Design Recommendation")
    goal = st.text_area(
        "What should students learn or demonstrate?",
        placeholder="Students should apply course concepts to a realistic business problem and defend their recommendation.",
    )
    description = ""
    if mode == "enhance":
        description = st.text_area("Paste the existing assignment", height=180)
        uploaded = st.file_uploader(
            "...or upload the existing assignment",
            type=["pdf", "docx", "md", "txt"],
            key="assignment-upload",
        )
        if uploaded is not None:
            description = read_source_text(save_upload(uploaded.name, uploaded.getvalue()))
    requirements = st.text_area(
        "Requirements or constraints (optional)",
        placeholder="Length, format, deliverables, allowed AI use, grading expectations, or anything Chalk should preserve.",
    )
    with st.expander("Additional assignment details (optional)"):
        st.caption(
            "Add details you want Chalk to treat as requirements. "
            "Leave a field blank when you want Chalk to avoid making that decision."
        )

        scenario = st.text_area(
            "Scenario / context",
            placeholder="Business situation, case context, student role, or other setup",
            key="assignment-scenario",
        )

        deliverables = st.text_area(
            "Required deliverables",
            placeholder="Report, presentation, diagram, analysis, reflection, or other required work",
            key="assignment-deliverables",
        )

        assignment_format = st.text_input(
            "Format / length",
            placeholder="Example: 2–3 pages, PDF, 10 slides",
            key="assignment-format",
        )

        evaluation = st.text_area(
            "Evaluation expectations",
            placeholder="What a successful submission should demonstrate",
            key="assignment-evaluation",
        )

        submission = st.text_input(
            "Submission details",
            placeholder="Due date, submission location, filename convention, if applicable",
            key="assignment-submission",
        )

    st.caption(
        "Chalk will use the saved course objectives and any source materials you select below. "
        "The result is a faculty-reviewed draft, not an automatic course change."
    )
    return {
        "assignment_mode": mode,
        "assignment_name": name,
        "assignment_goal": goal,
        "assignment_description": description,
        "assignment_requirements": requirements,
        "assignment_scenario": scenario,
        "assignment_deliverables": deliverables,
        "assignment_format": assignment_format,
        "assignment_evaluation": evaluation,
        "assignment_submission": submission,
    }


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

    if draft.request.content_type == "assignment":
        st.markdown("### Export assignment")

        export_format = st.selectbox(
            "File type",
            ("Word (.docx)", "PDF (.pdf)", "Markdown (.md)"),
            key="assignment-export-format",
        )

        file_data, extension, mime_type = export_assignment(
            draft.text,
            export_format,
        )

        base_name = draft.output_path.stem
        st.download_button(
            f"Download {export_format}",
            data=file_data,
            file_name=f"{base_name}.{extension}",
            mime=mime_type,
            key="assignment-download",
        )

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
