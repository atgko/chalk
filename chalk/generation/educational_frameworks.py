"""Optional educational frameworks for instructor-grounded assignments."""

from chalk.errors import GenerationError

FRAMEWORKS = ("none", "backward_design", "fink", "constructive_alignment")


def framework_guidance(framework: str, evidence: str = "") -> str:
    """Provide educational design guidance without inventing requirements."""
    if framework not in FRAMEWORKS:
        raise GenerationError("Choose a valid educational framework.")

    if framework == "none":
        return ""

    shared = (
        "EDUCATIONAL DESIGN GUIDANCE (internal; do not print this heading):\n"
        "Instructor learning goals, requirements, and selected course materials "
        "remain the primary authority. Align the assignment with those inputs. "
        "Do not invent deliverables, grading criteria, deadlines, point values, "
        "or additional student requirements. Do not name the framework in the "
        "student-facing assignment unless requested. "
    )

    approaches = {
        "backward_design": (
            "Use Backward Design: first identify desired learning results; "
            "then identify acceptable evidence of learning; finally organize "
            "assignment tasks around those outcomes and evidence. "
            "Keep all three aligned with instructor instructions."
        ),
        "fink": (
            "Use Fink's Significant Learning framework where appropriate: "
            "foundational knowledge, application, integration, human dimension, "
            "caring, and learning how to learn. Select only categories supported "
            "by the instructor's goals. Do not force all six categories."
        ),
        "constructive_alignment": (
            "Use Constructive Alignment: connect intended learning outcomes, "
            "student learning activities, and assessment evidence. "
            "Ensure the tasks demonstrate the skills described in the "
            "instructor's learning outcomes."
        ),
    }

    result = shared + approaches[framework]

    if evidence.strip():
        result += (
            "\nINSTRUCTOR-PROVIDED EVIDENCE OF LEARNING: "
            + evidence.strip()
            + "\nUse this evidence to guide alignment without inventing "
            "submission formats, deadlines, or point values."
        )

    return result
