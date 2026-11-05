"""PDF syllabi: read a PDF into a Word file the existing Word path handles.

A PDF syllabus is converted once, at upload, into "<name> (from PDF).docx".
Extraction, review, rollover, and export then all run on that Word file
exactly as they do for a syllabus uploaded as Word, and rollover writes
an editable .docx. The PDF itself is kept too, so rollover can also write
a copy of it with only the dates changed (chalk.rollover.pdf_rollover).

Two ways to read the PDF (the instructor picks one):
- "local": pdfplumber on this computer — free, offline, private.
- "ai": the configured LLM structures the text — handles unusual
  layouts, costs a few cents, and sends the text to the provider.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

PdfReadMethod = Literal["local", "ai"]
PDF_READ_METHODS: tuple[PdfReadMethod, ...] = ("local", "ai")

_CONVERTED_SUFFIX = " (from PDF).docx"


def converted_docx_name(pdf_path) -> str:
    """The Word file Chalk makes from a PDF: "<name> (from PDF).docx"."""
    return Path(pdf_path).stem + _CONVERTED_SUFFIX


def is_converted_from_pdf(filename: str) -> bool:
    return Path(filename).name.endswith(_CONVERTED_SUFFIX)


def original_pdf_name(converted_name: str) -> str:
    """The PDF a converted Word file was read from: "<name>.pdf"."""
    return Path(converted_name).name.removesuffix(_CONVERTED_SUFFIX) + ".pdf"
