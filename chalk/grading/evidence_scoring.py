"""Calculate rubric scores from individual evidence evaluations."""

from decimal import Decimal


def calculate_evidence_score(subrequirements, evaluations):
    """Score explicitly weighted requirements using verified response structure."""
    if len(subrequirements) != len(evaluations):
        raise ValueError("Every subrequirement must have an evaluation.")

    earned = Decimal(0)
    details = []

    for requirement, evaluation in zip(subrequirements, evaluations):
        points = Decimal(str(requirement["possible"]))
        met = evaluation.get("met")
        evidence = evaluation.get("evidence", "")

        if points <= 0:
            raise ValueError("Subrequirement points must be positive.")

        if not isinstance(met, bool):
            raise ValueError("Each evaluation must have a true/false met value.")

        if not isinstance(evidence, str):
            raise ValueError("Evidence must be text.")

        if met and not evidence.strip():
            raise ValueError("Satisfied requirements need supporting evidence.")

        awarded = points if met else Decimal(0)
        earned += awarded

        details.append({
            "name": requirement["name"],
            "possible": float(points),
            "earned": float(awarded),
            "met": met,
            "evidence": evidence.strip(),
        })

    return {
        "earned": float(earned),
        "details": details,
    }
