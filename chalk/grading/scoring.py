"""Validate and calculate preliminary rubric-based scores."""

from decimal import Decimal, InvalidOperation


class GradingValidationError(ValueError):
    """Raised when AI-generated grading data is invalid."""


def calculate_scores(criteria):
    """Validate criterion scores and calculate a suggested total."""
    if not isinstance(criteria, list) or not criteria:
        raise GradingValidationError("At least one rubric criterion is required.")

    results = []
    earned_total = Decimal("0")
    possible_total = Decimal("0")

    for criterion in criteria:
        if not isinstance(criterion, dict):
            raise GradingValidationError("Each criterion must be an object.")

        name = criterion.get("name")
        if not isinstance(name, str) or not name.strip():
            raise GradingValidationError("Each criterion needs a name.")

        try:
            earned = Decimal(str(criterion["earned"]))
            possible = Decimal(str(criterion["possible"]))
        except (KeyError, InvalidOperation, TypeError, ValueError):
            raise GradingValidationError(
                f"Invalid score for criterion: {name}"
            ) from None

        if not earned.is_finite() or not possible.is_finite():
            raise GradingValidationError("Scores must be finite numbers.")

        if possible <= 0 or earned < 0 or earned > possible:
            raise GradingValidationError(
                f"Score is outside the allowed range for: {name}"
            )

        allowed = criterion.get("allowed_scores")
        if allowed is not None:
            if not isinstance(allowed, list) or not allowed:
                raise GradingValidationError(
                    f"Invalid allowed scores for: {name}"
                )
            try:
                valid_scores = {Decimal(str(value)) for value in allowed}
            except (InvalidOperation, TypeError, ValueError):
                raise GradingValidationError(
                    f"Invalid allowed scores for: {name}"
                ) from None

            if not all(value.is_finite() for value in valid_scores):
                raise GradingValidationError(
                    f"Invalid allowed scores for: {name}"
                )

            if earned not in valid_scores:
                raise GradingValidationError(
                    f"Score is not an allowed rubric value for: {name}"
                )

        reasoning = criterion.get("reasoning", "")
        deduction_comment = criterion.get("deduction_comment", "")

        if not isinstance(reasoning, str):
            raise GradingValidationError(
                f"Invalid reasoning for: {name}"
            )

        if not isinstance(deduction_comment, str):
            raise GradingValidationError(
                f"Invalid deduction comment for: {name}"
            )

        if earned < possible and not deduction_comment.strip():
            deduction_comment = (
                "The AI did not provide a justification for this "
                "deduction. Instructor review is required before "
                "accepting the suggested score."
            )

        # Flag explicit score contradictions in AI explanations.
        import re

        stated_scores = re.findall(
            '(?<!\\d)(\\d+(?:\\.\\d+)?)\\s*/\\s*(\\d+(?:\\.\\d+)?)(?!\\d)',
            reasoning,
        )

        contradictions = [
            (float(stated_earned), float(stated_possible))
            for stated_earned, stated_possible in stated_scores
            if (
                float(stated_possible) == float(possible)
                and float(stated_earned) != float(earned)
            )
        ]

        if contradictions:
            warning = (
                "The AI explanation contains a score that contradicts "
                "the suggested grade. Instructor review is required."
            )
            deduction_comment = (
                f"{deduction_comment.strip()} {warning}".strip()
            )

        results.append({
            "name": name.strip(),
            "earned": float(earned),
            "possible": float(possible),
            "reasoning": reasoning,
            "deduction_comment": (
                deduction_comment.strip() if earned < possible else ""
            ),
        })

        earned_total += earned
        possible_total += possible

    percentage = earned_total / possible_total * 100

    return {
        "criteria": results,
        "earned_total": float(earned_total),
        "possible_total": float(possible_total),
        "percentage": float(percentage),
    }
