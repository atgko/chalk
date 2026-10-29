"""Find, remove, and redraw glyphs in a PDF page's content stream.

The PDF rollover (chalk.rollover.pdf_rollover) changes a few dates in the
original PDF and leaves everything else alone. A PDF has no "text" to
edit, only text-showing operators (Tj, TJ) that draw glyph codes in a
font at a position. So this module walks a page's content stream the way
a PDF reader does, tracking the text and graphics state well enough to
know where each glyph lands. pdfplumber (pdfminer) computes the same
positions for the characters it reads, which is how a character found by
pdfplumber is matched to the glyph code that drew it.

A replacement removes the old glyphs, leaving a gap so the rest of the
line stays where it was, and draws the new text at the end of the page,
at the old text's position and in the same font, size, and color. It's
drawn at the end, outside every clipping path, because some PDF printers
clip each glyph to its own narrow box, which would hide a longer date
written in its place. The text layer (copy and paste, screen readers,
Chalk's own PDF reader next term) then has only the new text.

Only fonts whose codes Chalk can split and measure are handled: simple
fonts (one byte per code, /Widths, or a standard font) and Type0 fonts
with Identity-H (two bytes per code, /W). Text in any other font, or
inside a form XObject, simply isn't found, and the caller skips the PDF
rather than guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from pypdf.generic import (
    ArrayObject,
    ByteStringObject,
    ContentStream,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    TextStringObject,
)
from reportlab.pdfbase.pdfmetrics import stringWidth

Matrix = tuple[float, float, float, float, float, float]
Operation = tuple[list, bytes]
_IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
_STANDARD_FONTS = {
    "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique",
    "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic",
    "Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique",
}  # fmt: skip
# A glyph's computed origin and pdfplumber's must agree this closely (points).
_POSITION_TOLERANCE = 0.05


class UnsupportedFont(Exception):
    """A font whose codes Chalk can't split or measure."""


@dataclass(frozen=True)
class Font:
    """What Chalk needs to know about a font to walk and write its codes."""

    key: str  # stable across pages: the font object's id, else its name
    code_bytes: int  # 1 for a simple font, 2 for Identity-H
    widths: dict[int, float]  # code -> width in thousandths of text space
    default_width: float

    def codes(self, data: bytes) -> list[int]:
        step = self.code_bytes
        return [
            int.from_bytes(data[i : i + step], "big") for i in range(0, len(data) - step + 1, step)
        ]

    def encode(self, codes: list[int]) -> bytes:
        return b"".join(code.to_bytes(self.code_bytes, "big") for code in codes)

    def width(self, code: int) -> float:
        return self.widths.get(code, self.default_width)


@dataclass(frozen=True)
class Glyph:
    """One drawn glyph: which operator drew it, where in that operator,
    its code and font, where it landed, and the text state it was drawn
    in (to measure and draw a replacement the same way)."""

    op_index: int
    element: int  # index in the TJ array (0 for Tj)
    code_index: int  # index of the code within that string
    code: int
    font: Font
    font_name: str  # the page's resource name for the font, e.g. "/R10"
    font_size: float
    char_spacing: float
    word_spacing: float
    h_scale: float
    to_page: Matrix  # text space at this glyph -> page space (pdfminer's)
    render_mode: int  # Tr: 0 fill, 3 invisible (an OCR text layer), ...
    flow: int  # glyphs with the same flow follow on from each other

    @property
    def origin(self) -> tuple[float, float]:
        return self.to_page[4], self.to_page[5]

    def moved(self, distance: float) -> Glyph:
        """This glyph as if `distance` further along its line (text space)."""
        return replace(self, to_page=_multiply((1.0, 0.0, 0.0, 1.0, distance, 0.0), self.to_page))


@dataclass(frozen=True)
class Removal:
    """How a run of glyphs is removed: the gap left in each operator, and
    how far that moves the text after the run in the same flow."""

    gaps: dict[int, float]  # operator index -> gap width (text space)
    shift: float


@dataclass
class _State:
    ctm: Matrix = _IDENTITY
    font: Font | None = None
    font_name: str = ""
    font_size: float = 0.0
    char_spacing: float = 0.0
    word_spacing: float = 0.0
    h_scale: float = 1.0
    leading: float = 0.0
    render_mode: int = 0


@dataclass
class PageGlyphs:
    """A page's parsed content stream and every glyph it draws."""

    content: ContentStream
    glyphs: list[Glyph]
    offset: tuple[float, float]  # the mediabox's lower-left corner
    open_states: int  # q without a matching Q at the end of the stream
    _by_cell: dict[tuple[int, int], list[Glyph]] = field(default_factory=dict, repr=False)

    def at(self, x: float, y: float) -> Glyph | None:
        """The glyph whose origin is at (x, y), as pdfplumber reports a
        character's position (its matrix's e and f)."""
        if not self._by_cell:
            for glyph in self.glyphs:
                self._by_cell.setdefault(_cell(*glyph.origin), []).append(glyph)
        cx, cy = _cell(x, y)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for glyph in self._by_cell.get((cx + dx, cy + dy), []):
                    if (
                        abs(glyph.origin[0] - x) <= _POSITION_TOLERANCE
                        and abs(glyph.origin[1] - y) <= _POSITION_TOLERANCE
                    ):
                        return glyph
        return None


def _cell(x: float, y: float) -> tuple[int, int]:
    return round(x), round(y)


def read_page_glyphs(page, reader) -> PageGlyphs:
    """Walk the page's content stream and record every glyph a Tj, TJ, '
    or " draws. The starting CTM matches pdfminer's for an unrotated page,
    so positions compare directly with pdfplumber's."""
    content = ContentStream(page.get_contents(), reader)
    x0, y0 = float(page.mediabox.left), float(page.mediabox.bottom)
    walker = _Walker(_page_fonts(page), (1.0, 0.0, 0.0, 1.0, -x0, -y0))
    for index, (operands, operator) in enumerate(content.operations):
        walker.step(index, operands, operator)
    return PageGlyphs(content, walker.glyphs, (x0, y0), len(walker.stack))


def advance(glyph: Glyph, code: int) -> float:
    """The horizontal advance of `code` in `glyph`'s font and text state,
    in text space before the text matrix (PDF 32000-1 section 9.4.4)."""
    word = glyph.word_spacing if glyph.font.code_bytes == 1 and code == 32 else 0.0
    return (
        glyph.font.width(code) / 1000 * glyph.font_size + glyph.char_spacing + word
    ) * glyph.h_scale


def plan_removal(page_glyphs: PageGlyphs, run: list[Glyph], new_width: float) -> Removal:
    """Plan removing a run of glyphs (in drawing order) to make room for
    new text `new_width` wide. The first glyph's operator gets a gap that
    wide, so the text after it flows on as in a word processor. A later
    operator in the same flow loses its glyphs without a gap (the room is
    already made); one positioned on its own gets a gap as wide as what it
    lost, so the rest of it stays put."""
    first = run[0]
    gaps: dict[int, float] = {}
    removed_from_flow = 0.0
    for op_index, glyphs in _by_operator(run).items():
        removed = _removed_width(page_glyphs.content, op_index, glyphs)
        if op_index == first.op_index or glyphs[0].flow == first.flow:
            gaps[op_index] = new_width if op_index == first.op_index else 0.0
            removed_from_flow += removed
        else:
            gaps[op_index] = removed
    return Removal(gaps, new_width - removed_from_flow)


def remove_glyph_run(page_glyphs: PageGlyphs, run: list[Glyph], removal: Removal) -> None:
    """Remove the run as planned (plan_removal)."""
    for op_index, glyphs in _by_operator(run).items():
        _remove_from_operator(page_glyphs.content, op_index, glyphs, removal.gaps[op_index])


def _by_operator(run: list[Glyph]) -> dict[int, list[Glyph]]:
    by_op: dict[int, list[Glyph]] = {}
    for glyph in run:
        by_op.setdefault(glyph.op_index, []).append(glyph)
    return by_op


def text_operations(
    glyph: Glyph, elements: list, font_name: str, color: tuple, offset: tuple[float, float]
) -> list[Operation]:
    """Operators that draw a TJ array of `elements` (strings and kerns) at
    `glyph`'s position, size, and text state, in the font the page calls
    `font_name`, in `color` (gray, RGB, or CMYK values)."""
    a, b, c, d, e, f = glyph.to_page
    x0, y0 = offset
    fill = [FloatObject(value) for value in color] or [FloatObject(0)]
    fill_operator = {1: b"g", 3: b"rg", 4: b"k"}.get(len(fill), b"g")
    if fill_operator == b"g" and len(fill) != 1:
        fill = [FloatObject(0)]
    return [
        ([], b"BT"),
        (fill, fill_operator),
        ([NameObject(font_name), FloatObject(glyph.font_size)], b"Tf"),
        ([FloatObject(glyph.char_spacing)], b"Tc"),
        ([FloatObject(glyph.word_spacing)], b"Tw"),
        ([FloatObject(glyph.h_scale * 100)], b"Tz"),
        ([NumberObject(glyph.render_mode)], b"Tr"),
        ([FloatObject(round(value, 6)) for value in (a, b, c, d, e + x0, f + y0)], b"Tm"),
        ([ArrayObject(elements)], b"TJ"),
        ([], b"ET"),
    ]


def finish_page(page_glyphs: PageGlyphs, drawing: list[Operation]) -> None:
    """Append `drawing` to the page's content, after closing every
    graphics state the original content left open, so no clipping path or
    transformation of the original applies to it."""
    content = page_glyphs.content
    closing = [([], b"Q")] * (page_glyphs.open_states + 1)
    content.operations = [([], b"q"), *content.operations, *closing, *drawing]


def add_standard_font(page, base_font: str) -> str:
    """Add a standard PDF font to the page's resources (it needs no
    embedding) and return its resource name."""
    resources = page["/Resources"].get_object()
    if "/Font" not in resources:
        resources[NameObject("/Font")] = DictionaryObject()
    fonts = resources["/Font"].get_object()
    name = f"/Chalk{base_font.replace('-', '')}"
    if name not in fonts:
        fonts[NameObject(name)] = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject(f"/{base_font}"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        })  # fmt: skip
    return name


def standard_font_width(text: str, base_font: str, glyph: Glyph) -> float:
    """`text`'s width in `base_font` at `glyph`'s size, in text space."""
    return stringWidth(text, base_font, glyph.font_size) * glyph.h_scale


def kern(width: float, glyph: Glyph) -> FloatObject:
    """A TJ number that moves the pen right by `width` text-space units."""
    return FloatObject(round(-width * 1000 / (glyph.font_size * glyph.h_scale), 4))


# ---- Walking the content stream ------------------------------------------------------


class _Walker:
    """A minimal PDF text interpreter: just enough state to place glyphs."""

    def __init__(self, fonts: dict, ctm: Matrix):
        self.fonts = fonts
        self.state = _State(ctm=ctm)
        self.stack: list[_State] = []
        self.text_matrix: Matrix = _IDENTITY
        self.line_matrix: Matrix = _IDENTITY
        self.glyphs: list[Glyph] = []
        self.flow = 0

    def step(self, index: int, operands: list, operator: bytes) -> None:
        handler = _HANDLERS.get(operator)
        if handler is not None:
            handler(self, index, operands)

    def push(self, _index, _operands) -> None:
        self.stack.append(replace(self.state))

    def pop(self, _index, _operands) -> None:
        if self.stack:
            self.state = self.stack.pop()

    def concat(self, _index, operands) -> None:
        self.state.ctm = _multiply(_matrix(operands), self.state.ctm)

    def begin_text(self, _index, _operands) -> None:
        self.text_matrix = self.line_matrix = _IDENTITY
        self.flow += 1

    def set_font(self, _index, operands) -> None:
        self.state.font_name = str(operands[0])
        self.state.font = self.fonts.get(self.state.font_name)
        self.state.font_size = float(operands[1])

    def set_char_spacing(self, _index, operands) -> None:
        self.state.char_spacing = float(operands[0])

    def set_word_spacing(self, _index, operands) -> None:
        self.state.word_spacing = float(operands[0])

    def set_leading(self, _index, operands) -> None:
        self.state.leading = float(operands[0])

    def set_render_mode(self, _index, operands) -> None:
        self.state.render_mode = int(operands[0])

    def set_h_scale(self, _index, operands) -> None:
        self.state.h_scale = float(operands[0]) / 100

    def move(self, tx: float, ty: float) -> None:
        self.line_matrix = _multiply((1.0, 0.0, 0.0, 1.0, tx, ty), self.line_matrix)
        self.text_matrix = self.line_matrix
        self.flow += 1

    def td(self, _index, operands) -> None:
        self.move(float(operands[0]), float(operands[1]))

    def td_leading(self, _index, operands) -> None:
        self.state.leading = -float(operands[1])
        self.move(float(operands[0]), float(operands[1]))

    def tm(self, _index, operands) -> None:
        self.text_matrix = self.line_matrix = _matrix(operands)
        self.flow += 1

    def next_line(self, _index=None, _operands=None) -> None:
        self.move(0.0, -self.state.leading)

    def show(self, index, operands) -> None:
        self.show_elements(index, [operands[0]])

    def show_array(self, index, operands) -> None:
        self.show_elements(index, list(operands[0]))

    def next_line_show(self, index, operands) -> None:
        self.next_line()
        self.show_elements(index, [operands[0]])

    def spacing_next_line_show(self, index, operands) -> None:
        self.state.word_spacing = float(operands[0])
        self.state.char_spacing = float(operands[1])
        self.next_line()
        self.show_elements(index, [operands[2]])

    def show_elements(self, index: int, elements: list) -> None:
        state = self.state
        if state.font is None:
            return
        for element_index, element in enumerate(elements):
            if not isinstance(element, (bytes, str)):
                shift = -float(element) / 1000 * state.font_size * state.h_scale
                self.text_matrix = _multiply((1.0, 0.0, 0.0, 1.0, shift, 0.0), self.text_matrix)
                continue
            for code_index, code in enumerate(state.font.codes(raw_bytes(element))):
                glyph = Glyph(
                    index, element_index, code_index, code, state.font, state.font_name, state.font_size,
                    state.char_spacing, state.word_spacing, state.h_scale, _multiply(self.text_matrix, state.ctm),
                    state.render_mode, self.flow,
                )  # fmt: skip
                self.glyphs.append(glyph)
                self.text_matrix = _multiply(
                    (1.0, 0.0, 0.0, 1.0, advance(glyph, code), 0.0), self.text_matrix
                )


_HANDLERS = {
    b"q": _Walker.push,
    b"Q": _Walker.pop,
    b"cm": _Walker.concat,
    b"BT": _Walker.begin_text,
    b"Tf": _Walker.set_font,
    b"Tc": _Walker.set_char_spacing,
    b"Tw": _Walker.set_word_spacing,
    b"TL": _Walker.set_leading,
    b"Tz": _Walker.set_h_scale,
    b"Tr": _Walker.set_render_mode,
    b"Td": _Walker.td,
    b"TD": _Walker.td_leading,
    b"Tm": _Walker.tm,
    b"T*": _Walker.next_line,
    b"Tj": _Walker.show,
    b"TJ": _Walker.show_array,
    b"'": _Walker.next_line_show,
    b'"': _Walker.spacing_next_line_show,
}


# ---- Removing glyphs from an operator ---------------------------------------------------


def _elements(content: ContentStream, op_index: int) -> list:
    operands, operator = content.operations[op_index]
    if operator == b"TJ":
        return list(operands[0])
    if operator == b"Tj":
        return [operands[0]]
    raise UnsupportedFont("Only Tj and TJ operators are rewritten")


def _remove_from_operator(
    content: ContentStream, op_index: int, removed: list[Glyph], gap: float
) -> None:
    """Rebuild one text-showing operator as a TJ without the `removed`
    glyphs (and anything between them), leaving a gap `gap` wide."""
    elements = _elements(content, op_index)
    first, last = removed[0], removed[-1]
    start, end = (first.element, first.code_index), (last.element, last.code_index)

    rebuilt: list = []
    for element_index, element in enumerate(elements):
        if not isinstance(element, (bytes, str)):
            if not start < (element_index, -1) < end:
                rebuilt.append(element)
            continue
        kept: list[int] = []
        for code_index, code in enumerate(first.font.codes(raw_bytes(element))):
            position = (element_index, code_index)
            if position == start:
                _flush(rebuilt, kept, first.font)
                if gap:
                    rebuilt.append(kern(gap, first))
            if not start <= position <= end:
                kept.append(code)
        _flush(rebuilt, kept, first.font)
    content.operations[op_index] = ([ArrayObject(rebuilt)], b"TJ")


def _removed_width(content: ContentStream, op_index: int, removed: list[Glyph]) -> float:
    """How wide the removed glyphs (and anything between them) are."""
    elements = _elements(content, op_index)
    glyph, last = removed[0], removed[-1]
    start, end = (glyph.element, glyph.code_index), (last.element, last.code_index)
    width = 0.0
    for element_index, element in enumerate(elements):
        if not isinstance(element, (bytes, str)):
            if start < (element_index, -1) < end:
                width -= float(element) / 1000 * glyph.font_size * glyph.h_scale
            continue
        for code_index, code in enumerate(glyph.font.codes(raw_bytes(element))):
            if start <= (element_index, code_index) <= end:
                width += advance(glyph, code)
    return width


def _flush(rebuilt: list, codes: list[int], font: Font) -> None:
    if codes:
        rebuilt.append(ByteStringObject(font.encode(codes)))
        codes.clear()


# ---- Fonts --------------------------------------------------------------------------


def _page_fonts(page) -> dict[str, Font]:
    resources = page.get("/Resources")
    font_dict = resources.get_object().get("/Font") if resources is not None else None
    fonts: dict[str, Font] = {}
    for name, reference in font_dict.get_object().items() if font_dict is not None else []:
        try:
            fonts[str(name)] = _font(reference)
        except UnsupportedFont:
            continue  # its glyphs aren't recorded, so nothing in it can be replaced
    return fonts


def _font(reference) -> Font:
    font = reference.get_object()
    key = f"obj{reference.idnum}" if hasattr(reference, "idnum") else str(font.get("/BaseFont"))
    subtype = font.get("/Subtype")
    if subtype == "/Type0":
        return _type0_font(font, key)
    if subtype in ("/Type1", "/TrueType", "/MMType1"):
        return _simple_font(font, key)
    raise UnsupportedFont(f"Font subtype {subtype}")


def _simple_font(font, key: str) -> Font:
    widths = font.get("/Widths")
    if widths is not None:
        first_char = int(font.get("/FirstChar", 0))
        descriptor = font.get("/FontDescriptor")
        missing = float(descriptor.get_object().get("/MissingWidth", 0)) if descriptor else 0.0
        table = {first_char + i: float(w) for i, w in enumerate(widths.get_object())}
        return Font(key, 1, table, missing)
    base = str(font.get("/BaseFont", "")).lstrip("/")
    if base not in _STANDARD_FONTS:
        raise UnsupportedFont(f"No widths for {base}")
    table = {
        code: stringWidth(bytes([code]).decode("cp1252", "replace"), base, 1000)
        for code in range(32, 256)
    }
    return Font(key, 1, table, stringWidth(" ", base, 1000))


def _type0_font(font, key: str) -> Font:
    if font.get("/Encoding") != "/Identity-H":
        raise UnsupportedFont(f"CMap {font.get('/Encoding')}")
    descendant = font["/DescendantFonts"][0].get_object()
    return Font(key, 2, _cid_widths(descendant.get("/W")), float(descendant.get("/DW", 1000)))


def _cid_widths(w_array) -> dict[int, float]:
    """Parse a CIDFont /W array: `c [w1 w2 ...]` or `c_first c_last w`."""
    widths: dict[int, float] = {}
    items = list(w_array.get_object()) if w_array is not None else []
    i = 0
    while i < len(items):
        start = int(items[i])
        following = items[i + 1].get_object()
        if isinstance(following, list):
            for offset, width in enumerate(following):
                widths[start + offset] = float(width)
            i += 2
        else:
            for code in range(start, int(following) + 1):
                widths[code] = float(items[i + 2])
            i += 3
    return widths


# ---- Small helpers --------------------------------------------------------------------


def raw_bytes(element) -> bytes:
    if isinstance(element, TextStringObject):
        # original_bytes, not get_original_bytes(): the latter can add a
        # UTF-16 byte-order mark to a string pypdf decoded as UTF-16.
        return element.original_bytes
    if isinstance(element, bytes):
        return bytes(element)
    return str(element).encode(
        "latin-1", "replace"
    )  # pragma: no cover - pypdf gives one of the two above


def _matrix(operands) -> Matrix:
    a, b, c, d, e, f = (float(value) for value in operands)
    return (a, b, c, d, e, f)


def _multiply(m: Matrix, n: Matrix) -> Matrix:
    """m × n, PDF's row-vector convention (apply m, then n)."""
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return (
        a * a2 + b * c2, a * b2 + b * d2,
        c * a2 + d * c2, c * b2 + d * d2,
        e * a2 + f * c2 + e2, e * b2 + f * d2 + f2,
    )  # fmt: skip
