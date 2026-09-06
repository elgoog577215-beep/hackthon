"""Measured, editable glyph projection for standalone source matrices."""
import re

from ppt_layout_execution import FONT_PATH, file_digest, _font


def project_formula(source):
    """Project supported notation before confirmation, keeping raw source intact."""
    matrix = project_matrix(source)
    if matrix is not None:
        return matrix
    from slide_deck_renderer import _format_formula_text
    source = re.sub(r"\\dots\b", lambda _: "…", source)
    text = _format_formula_text(source)
    if "\\" in text or "$" in text:
        raise ValueError("teaching_formula_not_supported")
    return text


_MATH_SPAN = re.compile(r"(?<!\\)\$\$(.+?)\$\$|\\\((.+?)\\\)|\\\[(.+?)\\\]|(?<![\\$])\$(?!\$)([^\n$]+?)(?<!\\)\$(?![\d$])", re.S)


def project_prose_math(source):
    """Convert only delimited math, including math inside an exact quotation.

    Ordinary prose, currency and braces stay literal; code never enters here.
    Unsupported notation is a draft error, not a final-render fallback.
    """
    def display(match):
        return project_formula(next(value for value in match.groups() if value is not None))
    return _MATH_SPAN.sub(display, source)


def project_matrix(source):
    """Align columns using the frozen font; return None for other formulas.

    The exact LaTeX remains in the teaching element and its source range. Hair
    spaces express measured column padding in both SVG and native text objects.
    This is a symbol-text projection, not an editable Office equation object.
    """
    match = re.fullmatch(r"\s*(?:\$\$?)?\s*\\begin\{(?P<kind>bmatrix|pmatrix|matrix)\}(?P<body>.*?)\\end\{(?P=kind)\}\s*(?:\$\$?)?\s*", source, re.S)
    if not match:
        return None
    from slide_deck_renderer import _format_formula_text
    rows = [[_format_formula_text(cell.strip()) for cell in row.split('&')]
            for row in re.split(r"\\\\", match['body']) if row.strip()]
    if not rows or any('\n' in cell or '\\' in cell for row in rows for cell in row):
        raise ValueError('teaching_matrix_structure_unsupported')
    # A teaching counterexample may intentionally omit an entry. Preserve the
    # ragged source, leaving empty visual space; never supply a missing zero.
    columns = max(map(len, rows))
    rows = [row + [''] * (columns - len(row)) for row in rows]
    font = _font(80, file_digest(FONT_PATH))
    gap = '\u2003'
    padding = '\u200a'
    step = font.getlength(padding)
    if step <= 0:
        raise ValueError('teaching_matrix_spacing_font_unsupported')
    widths = [max(font.getlength(row[c]) for row in rows) for c in range(columns)]
    left, right = ('⎛⎜⎝', '⎞⎟⎠') if match['kind'] == 'pmatrix' else ('⎡⎢⎣', '⎤⎥⎦')
    projected = []
    for index, row in enumerate(rows):
        cells = [padding * round((widths[c] - font.getlength(cell)) / step) + cell for c, cell in enumerate(row)]
        line = gap.join(cells)
        if match['kind'] != 'matrix':
            position = 0 if index == 0 else 2 if index == len(rows) - 1 else 1
            if len(rows) == 1:
                a, b = ('(', ')') if match['kind'] == 'pmatrix' else ('[', ']')
            else:
                a, b = left[position], right[position]
            line = a + gap + line + gap + b
        projected.append(line)
    return '\n'.join(projected)
