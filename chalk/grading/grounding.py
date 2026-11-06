"""Grounding a grading in the submission (BACKLOG.md, "Make grading
consistent"; faculty meeting, Oct 23).

Two things make the same submission grade the same way twice. Grading
asks for the lowest temperature, so the model picks its most likely
answer rather than sampling a different one each time. And every score
must rest on a quote copied from the submission, which Chalk checks is
really there. A quote that isn't found, or credit with no quote, is
flagged for the instructor rather than changing the score: the model may
have copied the quote loosely, and the instructor makes the final call.
"""

from __future__ import annotations

import unicodedata

# The lowest temperature, for the most repeatable answer. A model that
# accepts only its default is asked again without one (chalk.llm_client).
GRADING_TEMPERATURE = 0.0

QUOTE_INSTRUCTION = (
    "Copy the quote word for word from the student submission: the shortest passage "
    "(under 40 words) that best supports the score. Use ... to join two separate parts. "
    "Never paraphrase, correct, or invent a quote."
)

_NOT_FOUND_NOTE = (
    "The quoted evidence wasn't found word for word in the submission. "
    "Check it before accepting the score."
)
_NO_QUOTE_NOTE = (
    "No quote from the submission supports this score. Check it before accepting the score."
)

# Curly quotes and dashes that a model may straighten (or curl) when copying.
_EQUIVALENT_CHARACTERS = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-",
})
# Quote marks and punctuation a model adds around a quote it copied.
_EDGE_CHARACTERS = " \"'.,;:!?"
_ELLIPSIS = "..."


def _normalize(text: str) -> str:
    """Case, spacing, and character differences a copy may have. NFKC also
    turns the ellipsis character into three full stops."""
    text = unicodedata.normalize("NFKC", text).translate(_EQUIVALENT_CHARACTERS).casefold()
    return " ".join(text.split())


def quote_in_submission(quote: str, submission: str) -> bool:
    """Whether `quote` appears in `submission`, allowing for differences in
    case, spacing, and quote and dash characters. Parts joined with "..."
    must each appear, in order."""
    fragments = [part.strip(_EDGE_CHARACTERS) for part in _normalize(quote).split(_ELLIPSIS)]
    fragments = [part for part in fragments if part]
    if not fragments:
        return False
    text = _normalize(submission)
    position = 0
    for fragment in fragments:
        found_at = text.find(fragment, position)
        if found_at < 0:
            return False
        position = found_at + len(fragment)
    return True


def check_quote(quote: object, submission: str, *, earned: float) -> tuple[str, str]:
    """The quote, and a note for the instructor when it doesn't support the
    score: "" when the quote was found, or when no credit needs one."""
    quote = quote.strip() if isinstance(quote, str) else ""
    if not quote:
        return "", _NO_QUOTE_NOTE if earned > 0 else ""
    return quote, "" if quote_in_submission(quote, submission) else _NOT_FOUND_NOTE
