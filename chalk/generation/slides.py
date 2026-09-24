"""Slide-deck post-processing (F-05e): enforce the IS 4490 pptx pipeline
conventions on whatever the model returned, so the file drops straight
into `scripts/convert-slides-to-pptx.sh`:

- a YAML title block first, with no `subtitle:` field
- `##` slide titles, each preceded by `<!-- Slide N -->`, numbered in order
- no bare `#` headings

The AI-draft banner (PRD section 6.5) can't be the first line here without
breaking the YAML-first rule, so it goes directly after the YAML block as
an HTML comment, which the converter ignores (DECISIONS.md).
"""

from __future__ import annotations

import re

_SLIDE_COMMENT_RE = re.compile(r"^\s*<!--\s*Slide\s+\d+\s*-->\s*$", re.IGNORECASE)
_H1_RE = re.compile(r"^#(?!#)\s*")


def normalize_slides(text: str, *, default_title: str, author: str, banner: str) -> str:
    front_matter, body = _split_front_matter(text.strip())
    front_matter = [line for line in front_matter if not line.lower().startswith("subtitle:")]
    if not any(line.lower().startswith("title:") for line in front_matter):
        front_matter.insert(0, f'title: "{default_title}"')
    if not any(line.lower().startswith("author:") for line in front_matter):
        front_matter.append(f'author: "{author}"')

    slides_out: list[str] = []
    slide_number = 0
    for line in body:
        if _SLIDE_COMMENT_RE.match(line):
            continue
        if _H1_RE.match(line) and line.strip() != "#":
            line = "## " + _H1_RE.sub("", line, count=1)
        if line.startswith("## "):
            slide_number += 1
            if slides_out and slides_out[-1].strip():
                slides_out.append("")
            slides_out.append(f"<!-- Slide {slide_number} -->")
        slides_out.append(line)

    deck = ["---", *front_matter, "---", "", f"<!-- {banner} -->", "", *_trim_blank(slides_out)]
    return "\n".join(deck) + "\n"


def _split_front_matter(text: str) -> tuple[list[str], list[str]]:
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for end in range(1, len(lines)):
            if lines[end].strip() == "---":
                return [line for line in lines[1:end] if line.strip()], lines[end + 1 :]
    return [], lines


def _trim_blank(lines: list[str]) -> list[str]:
    while lines and not lines[0].strip():
        lines = lines[1:]
    return lines
