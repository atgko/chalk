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

    if not criteria:
        raise ValueError(
            "No numbered rubric criteria were detected. "
            "Please review the rubric format."
        )

    return criteria
