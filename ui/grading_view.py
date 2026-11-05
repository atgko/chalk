from chalk.grading.export import export_pdf, export_word

"""AI Grading Assistant interface."""

from io import BytesIO

import streamlit as st

from chalk.config import (
    LOCAL_CHOICE,
    NOT_APPROVED_FOR_STUDENT_DATA,
    choice_for_env,
    describe_provider,
    effective_env,
)
from chalk.grading.eval_log import grade_and_log
from chalk.grading.strictness import STANDARD, STRICTNESS_LABELS, STRICTNESS_LEVELS
from chalk.llm_client import LLMProviderError


def extract_submission(uploaded_file):
    """Extract text from PDF, Word, or TXT submissions."""
    data = uploaded_file.getvalue()
    filename = uploaded_file.name.lower()

    if filename.endswith(".txt"):
        return data.decode("utf-8-sig")

    if filename.endswith(".docx"):
        from docx import Document

        document = Document(BytesIO(data))
        paragraphs = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                paragraphs.append(" | ".join(cell.text for cell in row.cells))
        return "\n".join(paragraphs)

    if filename.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    raise ValueError("Unsupported file type.")


def _provider_allows_grading(paths) -> bool:
    """Say where student work goes before any is uploaded, and stop when
    no provider is connected or the one in use isn't approved for student
    data. The rest of the app takes course materials only (FERPA), so
    this is the one tab where student work leaves the instructor's hands."""
    env = effective_env(paths.env)
    if describe_provider(env) == "Not configured":
        st.info("Connect an AI provider under Settings → AI Provider to use the Grading Assistant.")
        return False
    choice = choice_for_env(env)
    if choice in NOT_APPROVED_FOR_STUDENT_DATA:
        st.error(
            f"{choice} isn't approved by the university for student data, so the Grading Assistant "
            "is off while it's your AI provider. Switch to another provider under "
            "Settings → AI Provider to grade student work."
        )
        return False
    where = (
        "Student work you upload here stays on this computer: your local model reads it."
        if choice == LOCAL_CHOICE
        else f"Student work you upload here is sent to {choice} to be analyzed. Remove names, "
        "student IDs, and other identifying details first."
    )
    st.info(f"{where} Chalk only suggests grades: you review and approve every final grade.")
    return True


def render(paths):
    """Render the grading assistant workflow."""
    st.header("AI Grading Assistant")
    st.caption(
        "Upload student work and generate rubric-based grading "
        "recommendations for instructor review."
    )

    if not _provider_allows_grading(paths):
        return

    uploaded_file = st.file_uploader(
        "Upload student submission",
        type=["pdf", "docx", "txt"],
        key="grading_submission",
    )

    rubric = st.text_area(
        "Assignment instructions and grading rubric",
        height=200,
        placeholder="Paste the assignment requirements and rubric here...",
        key="grading_rubric",
    )

    instructions = st.text_area(
        "Additional grading instructions (optional)",
        height=100,
        placeholder="Enter any specific grading expectations...",
        key="grading_instructions",
    )

    strictness = st.segmented_control(
        "Grading strictness",
        STRICTNESS_LEVELS,
        default=STANDARD,
        format_func=STRICTNESS_LABELS.get,
        key="grading_strictness",
        help="Lenient gives the benefit of the doubt and encouraging feedback; Strict gives credit "
        "only for what the submission clearly shows, with direct feedback. Both grade only against "
        "the rubric. Standard grades as before.",
    ) or STANDARD

    ready = uploaded_file is not None and bool(rubric.strip())

    if st.button(
        "Analyze Submission",
        disabled=not ready,
        type="primary",
    ):
        try:
            with st.spinner("Analyzing student submission..."):
                submission = extract_submission(uploaded_file)

                if not submission.strip():
                    st.error(
                        "No readable text was found in the submission. "
                        "Scanned PDFs may require OCR."
                    )
                    return

                feedback = grade_and_log(
                    paths,
                    submission=submission,
                    rubric=rubric,
                    instructions=instructions,
                    strictness=strictness,
                )

            st.session_state["grading_feedback"] = feedback

        except (ValueError, UnicodeError) as exc:
            st.error(str(exc))
        except LLMProviderError as exc:
            st.error(str(exc))
        except Exception as exc:  # noqa: BLE001 - Keep the grading UI from crashing.
            st.error(f"Grading error: {type(exc).__name__}: {exc}")
            st.error(
                "The submission could not be processed. "
                "Check the file format and try again."
            )

    if st.session_state.get("grading_feedback"):
        result = st.session_state["grading_feedback"]

        st.divider()
        st.subheader("AI Grading Recommendations")
        st.warning(
            "These are preliminary AI recommendations. "
            "The instructor must review and approve all final grades."
        )

        earned = result["earned_total"]
        possible = result["possible_total"]
        percentage = result["percentage"]

        st.metric(
            "Suggested Overall Grade",
            f"{earned:g} / {possible:g}",
            f"{percentage:.1f}%",
            delta_color="off",
        )

        st.subheader("Rubric Breakdown")

        for criterion in result["criteria"]:
            name = criterion["name"]
            score = criterion["earned"]
            maximum = criterion["possible"]

            st.markdown(
                f"**{name}: {score:g} / {maximum:g} points**"
            )
            st.progress(min(1.0, score / maximum))
            st.write(criterion["reasoning"])

            deduction = maximum - score
            comment = criterion.get("deduction_comment", "")

            if deduction > 0:
                st.markdown(
                    f"**Suggested deduction: -{deduction:g} points**"
                )
                if comment:
                    st.info(comment)
                else:
                    st.warning(
                        "Deduction explanation unavailable. "
                        "Instructor review required."
                    )

        st.divider()
        st.subheader("Student Feedback")

        student_feedback = result["student_feedback"]
        st.text_area(
            "Copy this comment into Canvas",
            value=student_feedback,
            height=150,
            key="student_feedback_display",
        )

        st.divider()
        st.subheader("Instructor Review Notes")
        st.write(result["instructor_notes"] or "No additional notes provided.")

        report = (
            f"# AI Grading Recommendations\\n\\n"
            f"Suggested Grade: {earned:g}/{possible:g} "
            f"({percentage:.1f}%)\\n\\n"
            "## Rubric Breakdown\\n\\n"
        )

        for criterion in result["criteria"]:
            report += (
                f"### {criterion['name']}\\n"
                f"Score: {criterion['earned']:g}/"
                f"{criterion['possible']:g}\\n\\n"
                f"{criterion['reasoning']}\\n\\n"
                + (
                    f"Suggested deduction: "
                    f"{criterion['possible'] - criterion['earned']:g} points\\n\\n"
                    f"{criterion['deduction_comment']}\\n\\n"
                    if criterion['possible'] > criterion['earned']
                    else ""
                )
            )

        report += (
            f"## Student Feedback\\n\\n{student_feedback}\\n\\n"
            f"## Instructor Review Notes\\n\\n"
            f"{result['instructor_notes']}\\n\\n"
            "All grades are preliminary recommendations "
            "requiring instructor approval.\\n"
        )

        st.subheader("Download Grading Report")

        word_data = export_word(result)
        pdf_data = export_pdf(result)

        col1, col2, col3 = st.columns(3)

        with col1:
            st.download_button(
                "Download Word",
                data=word_data,
                file_name="grading_feedback.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        with col2:
            st.download_button(
                "Download PDF",
                data=pdf_data,
                file_name="grading_feedback.pdf",
                mime="application/pdf",
            )

        with col3:
            st.download_button(
                "Download Markdown",
                data=report,
                file_name="grading_feedback.md",
                mime="text/markdown",
            )
