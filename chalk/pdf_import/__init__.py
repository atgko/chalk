"""PDF syllabi: read a PDF into a Word file the existing Word path handles.

Chalk can't edit a PDF in place, so a PDF syllabus is converted once, at
upload, into "<name> (from PDF).docx". Extraction, review, rollover, and
export then all run on that Word file exactly as they do for a syllabus
uploaded as Word — and rollover writes an editable .docx.

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
    return Path(pdf_path).stem + _CONVERTED_SUFFIX


def is_converted_from_pdf(filename: str) -> bool:
    return Path(filename).name.endswith(_CONVERTED_SUFFIX)
