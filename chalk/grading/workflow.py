"""Coordinate rubric-based grading recommendations."""

from chalk.grading.criterion import grade_criterion
from chalk.grading.evidence_evaluator import evaluate_weighted_criterion
from chalk.grading.rubric import parse_rubric
from chalk.grading.scoring import calculate_scores


def analyze_by_criterion(
    submission: str,
    rubric: str,
    instructions: str = "",
) -> dict:
    """Grade each rubric criterion and assemble preliminary feedback."""
    if not submission.strip():
        raise ValueError("Student submission cannot be empty.")

    if not rubric.strip():
        raise ValueError("A grading rubric is required.")

    criteria = parse_rubric(rubric)
    recommendations = []

    for criterion in criteria:
        if criterion.get("subrequirements"):
            recommendation = evaluate_weighted_criterion(
                submission=submission,
                criterion=criterion,
                instructions=instructions,
            )
            missing = [
                item["name"]
                for item in recommendation["details"]
                if not item["met"]
            ]
            recommendation["reasoning"] = (
                "Evidence-based evaluation of explicitly weighted requirements. "
                + "; ".join(
                    f'{item["name"]}: {"met" if item["met"] else "not met"} '
                    f'({item["earned"]:g}/{item["possible"]:g} points). '
                    f'{item["evidence"]}'
                    for item in recommendation["details"]
                )
            )
            recommendation["deduction_comment"] = (
                "Review the following requirements: " + ", ".join(missing) + "."
                if missing else ""
            )
        else:
            recommendation = grade_criterion(
                submission=submission,
                rubric=rubric,
                criterion=criterion,
                instructions=instructions,
            )
        recommendations.append(recommendation)

    if len(recommendations) != len(criteria):
        raise ValueError(
            "Not all rubric criteria were evaluated. "
            "Instructor review is required."
        )

    scores = calculate_scores(recommendations)

    criteria = scores["criteria"]

    strengths = [
        item["name"]
        for item in criteria
        if item["possible"] > 0 and item["earned"] / item["possible"] >= 0.75
    ]

    improvements = [
        item["name"]
        for item in criteria
        if item["earned"] < item["possible"]
    ]

    comment_parts = []

    if strengths:
        comment_parts.append(
            "You demonstrated a good understanding of "
            + ", ".join(strengths).lower()
            + "."
        )

    if improvements:
        comment_parts.append(
            "For future assignments, focus on fully addressing "
            + ", ".join(improvements).lower()
            + "."
        )

    comment_parts.append(
        "Review the rubric breakdown for specific feedback "
        "and opportunities to improve."
    )

    student_comment = " ".join(comment_parts)

    feedback_lines = [
        f"{item['name']}: {item['reasoning']}"
        for item in criteria
    ]

    return {
        **scores,
        "student_feedback": student_comment,
        "instructor_notes": (
            "These are preliminary AI recommendations. "
            "Review each criterion and its supporting evidence "
            "before assigning a final grade.\n\n"
            + "\n".join(feedback_lines)
        ),
    }
