"""Parse instructor-defined rubric categories and point values."""

import re
from decimal import Decimal


def parse_rubric(rubric: str) -> list[dict]:
    """Extract numbered rubric criteria without AI assistance."""
    criteria = []

    pattern = re.compile(
        r"^\s*\d+[.)]\s*\**(.+?)\**\s*"
        r"[\u2014\u2013-]\s*(\d+(?:\.\d+)?)\s*points?\b",
        re.IGNORECASE,
    )

    for line in rubric.splitlines():
        # Remove Markdown bold markers.
        clean_line = line.replace("**", "").strip()
        match = pattern.search(clean_line)

        if match:
            name = match.group(1).strip()
            maximum = Decimal(match.group(2))

            if maximum <= 0:
                raise ValueError("Rubric points must be positive.")

            criteria.append({
                "name": name,
                "possible": float(maximum),
            })

    # Optional indented subrequirements with explicit point values.
    sub_pattern = re.compile(
        r"^\s*[-–]\s+(.+?)\s*[-–:]\s*(\d+(?:\.\d+)?)\s*points?\s*$",
        re.IGNORECASE,
    )

    criterion_index = -1
    for line in rubric.splitlines():
        clean_line = line.replace("**", "").rstrip()
        if pattern.search(clean_line.strip()):
            criterion_index += 1
            continue

        match = sub_pattern.match(clean_line)
        if match and criterion_index >= 0:
            criteria[criterion_index].setdefault("subrequirements", []).append({
                "name": match.group(1).strip(),
                "possible": float(Decimal(match.group(2))),
            })

    for criterion in criteria:
        parts = criterion.get("subrequirements", [])
        if parts:
            allocated = sum(Decimal(str(p["possible"])) for p in parts)
            maximum = Decimal(str(criterion["possible"]))
            if allocated != maximum:
                raise ValueError(
                    f"Subrequirements for {criterion['name']} total "
                    f"{allocated} points, but the criterion is worth {maximum}."
                )

    if not criteria:
        raise ValueError(
            "No numbered rubric criteria were detected. "
            "Please review the rubric format."
        )

    return criteria
