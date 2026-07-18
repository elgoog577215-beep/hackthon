"""Editable PPTX renderer for the shared structured slide deck contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from slide_deck import SlideBlockSpec, SlideDeckContent, SlideSpec, validate_slide_deck

THEMES: dict[str, dict[str, str]] = {
    "qingfeng-classroom": {
        "surface": "F7FAFC",
        "canvas": "EBF4FF",
        "chart_bg": "E2E8F0",
        "title": "1A365D",
        "ink": "4A5568",
        "muted": "718096",
        "accent": "2B6CB0",
        "accent_soft": "BEE3F8",
        "green": "2F855A",
        "green_soft": "F0FFF4",
        "amber": "ED8936",
        "amber_soft": "FFFAF0",
        "red": "B54735",
        "red_soft": "FFF1EE",
        "code": "1A365D",
        "title_font": "Noto Sans SC",
        "title_east_asian_font": "Microsoft YaHei",
        "body_font": "Noto Sans SC",
        "body_east_asian_font": "Microsoft YaHei",
        "math_font": "Times New Roman",
    },
    "academic-bluegray": {
        "surface": "FCFCFD",
        "canvas": "E8EBEE",
        "chart_bg": "E8EBEE",
        "title": "2C3E50",
        "ink": "5D6D7E",
        "muted": "7F8C8D",
        "accent": "2E86C1",
        "accent_soft": "D6EAF8",
        "green": "2874A6",
        "green_soft": "EAF2F8",
        "amber": "B9770E",
        "amber_soft": "FDF2E9",
        "red": "922B21",
        "red_soft": "FDEDEC",
        "code": "2C3E50",
        "title_font": "Noto Serif SC",
        "title_east_asian_font": "SimSun",
        "body_font": "Noto Sans SC",
        "body_east_asian_font": "Microsoft YaHei",
        "math_font": "Times New Roman",
    },
}

BODY_FONT = "Noto Sans SC"
BODY_EAST_ASIAN_FONT = "Microsoft YaHei"
CODE_FONT = "Aptos Mono"


class SlideDeckQualityError(ValueError):
    def __init__(self, report: dict[str, Any]) -> None:
        self.report = report
        codes = ", ".join(item["code"] for item in report["blockers"])
        super().__init__(f"Slide deck quality gate blocked export: {codes}")


def export_structured_slide_deck(
    content: dict[str, Any],
    output_path: str | Path,
    *,
    require_quality: bool = True,
    theme: str = "qingfeng-classroom",
) -> Path:
    """Render the same slide spec used by the browser preview into editable PPTX."""
    deck = SlideDeckContent.model_validate(content)
    report = validate_slide_deck(deck.model_dump(mode="json"))
    if require_quality and not report["passed"]:
        raise SlideDeckQualityError(report)

    from pptx import Presentation
    from pptx.util import Inches

    presentation = Presentation()
    presentation.slide_width = Inches(13.333)
    presentation.slide_height = Inches(7.5)
    theme_config = validate_theme(theme)

    for index, unit in enumerate(deck.slides):
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        _render_slide(slide, unit, index + 1, len(deck.slides), theme_config)
        if unit.speaker_notes:
            slide.notes_slide.notes_text_frame.text = unit.speaker_notes

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    presentation.save(path)
    return path


def validate_theme(theme: str) -> dict[str, str]:
    try:
        return THEMES[theme]
    except KeyError as exc:
        choices = ", ".join(sorted(THEMES))
        raise ValueError(f"Unknown slide theme '{theme}'. Expected one of: {choices}") from exc


def _render_slide(
    slide: Any,
    unit: SlideSpec,
    page_number: int,
    page_count: int,
    theme: dict[str, str],
) -> None:
    _fill_background(slide, theme["surface"])
    renderer = {
        "cover": _render_cover,
        "roadmap": _render_roadmap,
        "chapter": _render_chapter,
        "objective": _render_objective,
        "concept": _render_concept,
        "comparison": _render_comparison,
        "process": _render_process,
        "code": _render_code,
        "misconception": _render_misconception,
        "practice": _render_practice,
        "recap": _render_recap,
    }.get(unit.layout, _render_concept)
    renderer(slide, unit, theme)
    if unit.layout != "cover":
        _footer(slide, unit, page_number, page_count, theme)


def _render_cover(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    _shape(slide, 0.58, 0.55, 0.12, 5.92, theme["accent"], radius=False)
    _shape(slide, 10.82, 0.0, 2.52, 7.5, theme["accent_soft"], radius=False)
    _shape(slide, 11.35, 0.72, 1.04, 1.04, theme["green"], radius=True)
    _text(slide, "灵知", 11.35, 0.99, 1.04, 0.34, 15, "FFFFFF", bold=True, align="center")
    _text(slide, unit.eyebrow or "课程演示", 0.92, 0.72, 4.0, 0.38, 14, theme["accent"], bold=True)
    _text(
        slide, unit.title, 0.92, 1.42, 9.15, 1.65, 34, theme["title"], bold=True,
        font=theme["title_font"], east_asian_font=theme["title_east_asian_font"],
    )
    if unit.subtitle:
        _text(slide, unit.subtitle, 0.94, 3.12, 7.8, 0.48, 15, theme["muted"])
    _shape(slide, 0.92, 4.23, 8.85, 1.14, theme["canvas"], radius=True, line=theme["accent_soft"])
    _text(slide, "学习主线", 1.18, 4.48, 1.2, 0.28, 11, theme["green"], bold=True)
    _text(slide, unit.key_message or _block_content(unit.blocks, 0), 2.42, 4.39, 7.0, 0.58, 15, theme["ink"], bold=True)
    _text(slide, "同一课程结构 · 知识与能力绑定 · 可继续编辑", 0.94, 6.45, 7.0, 0.32, 11, theme["muted"])


def _render_roadmap(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    _heading(slide, unit, theme)
    items = _all_items(unit)[:8]
    columns = 2
    rows = max(1, (len(items) + 1) // columns)
    card_h = min(1.04, 4.35 / rows)
    for index, item in enumerate(items):
        row, column = divmod(index, columns)
        x = 0.78 + column * 6.0
        y = 2.05 + row * (card_h + 0.16)
        _shape(slide, x, y, 5.55, card_h, "FFFFFF", radius=True, line="DFE3EE")
        _shape(slide, x + 0.22, y + 0.22, 0.5, 0.5, theme["accent_soft"], radius=True)
        _text(slide, f"{index + 1:02d}", x + 0.22, y + 0.33, 0.5, 0.2, 10, theme["accent"], bold=True, align="center")
        _text(slide, item, x + 0.9, y + 0.24, 4.35, card_h - 0.25, 14, theme["ink"], bold=True)


def _render_chapter(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    _shape(slide, 0.0, 0.0, 4.05, 7.5, theme["accent_soft"], radius=False)
    chapter_number = _chapter_number(unit.title)
    _text(slide, chapter_number, 0.72, 1.15, 2.5, 1.35, 54, theme["accent"], bold=True)
    _text(slide, unit.eyebrow or "章节转场", 4.65, 1.08, 2.3, 0.32, 12, theme["green"], bold=True)
    _text(
        slide, unit.title, 4.65, 1.62, 7.55, 1.4, 31, theme["title"], bold=True,
        font=theme["title_font"], east_asian_font=theme["title_east_asian_font"],
    )
    _shape(slide, 4.65, 3.45, 6.95, 1.55, "FFFFFF", radius=True, line="DFE3EE")
    _text(slide, "本章主线", 4.98, 3.78, 1.4, 0.3, 11, theme["accent"], bold=True)
    _text(slide, unit.key_message or _block_content(unit.blocks, 0), 4.98, 4.12, 6.18, 0.62, 15, theme["ink"], bold=True)


def _render_objective(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    _heading(slide, unit, theme)
    question = _find_block(unit, "callout") or (unit.blocks[0] if unit.blocks else None)
    _shape(slide, 0.76, 1.83, 5.0, 4.67, theme["accent_soft"], radius=True)
    _text(slide, "要解决的问题", 1.08, 2.14, 2.0, 0.32, 12, theme["accent"], bold=True)
    _text(slide, question.content if question else unit.key_message, 1.08, 2.72, 4.28, 2.1, 22, theme["ink"], bold=True)
    right_blocks = [block for block in unit.blocks if block is not question]
    if not right_blocks:
        right_blocks = [SlideBlockSpec(block_id="objective", type="bullets", items=[unit.key_message])]
    for index, block in enumerate(right_blocks[:2]):
        y = 1.83 + index * 2.35
        color = theme["green_soft"] if index == 0 else theme["amber_soft"]
        accent = theme["green"] if index == 0 else theme["amber"]
        _shape(slide, 6.05, y, 6.48, 2.12, color, radius=True)
        _text(slide, block.title or ("知识坐标" if index == 0 else "完成后能够"), 6.38, y + 0.27, 2.3, 0.3, 11, accent, bold=True)
        _bullets(slide, block.items or [block.content], 6.38, y + 0.72, 5.72, 1.12, 14, theme["ink"], accent)


def _render_concept(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    _heading(slide, unit, theme)
    if unit.key_message:
        _shape(slide, 0.76, 1.72, 11.82, 0.86, theme["accent_soft"], radius=True)
        _text(slide, unit.key_message, 1.05, 1.94, 11.22, 0.4, 16, theme["ink"], bold=True)
    blocks = unit.blocks
    width = 11.82 / max(1, len(blocks)) - 0.18
    for index, block in enumerate(blocks):
        x = 0.76 + index * (width + 0.27)
        _shape(slide, x, 2.87, width, 3.52, "FFFFFF", radius=True, line="DFE3EE")
        accent = [theme["accent"], theme["green"], theme["amber"]][index % 3]
        _shape(slide, x, 2.87, 0.08, 3.52, accent, radius=False)
        _text(slide, block.title or f"要点 {index + 1}", x + 0.3, 3.17, width - 0.55, 0.42, 13, accent, bold=True)
        if block.items:
            _bullets(slide, block.items, x + 0.3, 3.76, width - 0.58, 2.18, 13, theme["ink"], accent)
        else:
            is_formula = bool(block.metadata.get("formula"))
            _text(
                slide,
                block.content,
                x + 0.3,
                3.76,
                width - 0.58,
                2.18,
                14,
                theme["ink"],
                font=theme["math_font"] if is_formula else theme["body_font"],
                east_asian_font=theme["body_east_asian_font"],
            )


def _render_comparison(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    _heading(slide, unit, theme)
    block = _find_block(unit, "comparison")
    if block and block.metadata.get("rows"):
        headers = [str(value) for value in block.metadata.get("headers") or []]
        rows = [[str(value) for value in row] for row in block.metadata.get("rows") or []]
        _table(slide, headers, rows, 0.78, 1.85, 11.78, 4.45, theme)
    else:
        _render_concept(slide, unit, theme)
        return
    if unit.key_message:
        _shape(slide, 0.78, 6.37, 11.78, 0.48, theme["amber_soft"], radius=True)
        _text(slide, unit.key_message, 1.02, 6.48, 11.25, 0.23, 11, theme["amber"], bold=True)


def _render_process(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    _heading(slide, unit, theme)
    items = _all_items(unit)[:5] or [block.content for block in unit.blocks if block.content][:5]
    width = (11.7 - max(0, len(items) - 1) * 0.24) / max(1, len(items))
    for index, item in enumerate(items):
        x = 0.82 + index * (width + 0.24)
        _shape(slide, x, 2.08, width, 3.72, "FFFFFF", radius=True, line="DFE3EE")
        _shape(slide, x + 0.22, 2.34, 0.58, 0.58, theme["accent"], radius=True)
        _text(slide, str(index + 1), x + 0.22, 2.52, 0.58, 0.2, 12, "FFFFFF", bold=True, align="center")
        _text(slide, item, x + 0.23, 3.25, width - 0.46, 1.95, 15, theme["ink"], bold=True)
        if index < len(items) - 1:
            _text(slide, "→", x + width + 0.01, 3.68, 0.22, 0.35, 17, theme["muted"], bold=True, align="center")


def _render_code(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    _heading(slide, unit, theme)
    code = _find_block(unit, "code")
    _shape(slide, 0.76, 1.75, 7.48, 4.72, theme["code"], radius=True)
    language = str(code.metadata.get("language") or "code") if code else "code"
    _text(slide, language.upper(), 1.05, 2.02, 1.4, 0.28, 10, "AEB6D0", bold=True, font="Aptos Mono")
    _text(slide, code.content if code else "", 1.05, 2.48, 6.9, 3.6, 13, "F5F7FF", font="Aptos Mono")
    insight_blocks = [block for block in unit.blocks if block is not code]
    _shape(slide, 8.52, 1.75, 4.04, 4.72, theme["canvas"], radius=True)
    _text(slide, "阅读线索", 8.86, 2.08, 1.7, 0.32, 12, theme["green"], bold=True)
    items = [item for block in insight_blocks for item in (block.items or [block.content]) if item][:5]
    _bullets(slide, items or [unit.key_message], 8.86, 2.65, 3.32, 3.1, 11, theme["ink"], theme["green"])


def _render_misconception(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    _heading(slide, unit, theme)
    mistakes = [
        item for block in unit.blocks if block.type == "misconception"
        for item in (block.items or [block.content]) if item
    ]
    correction = unit.key_message or "回到定义、条件和可验证证据进行判断。"
    _shape(slide, 0.78, 1.93, 5.65, 4.28, theme["red_soft"], radius=True)
    _text(slide, "容易这样想", 1.13, 2.25, 2.0, 0.34, 12, theme["red"], bold=True)
    _bullets(slide, mistakes[:4] or ["忽略条件，只记结论"], 1.13, 2.88, 4.92, 2.62, 16, theme["ink"], theme["red"])
    _shape(slide, 6.71, 1.93, 5.84, 4.28, theme["green_soft"], radius=True)
    _text(slide, "应当这样判断", 7.06, 2.25, 2.2, 0.34, 12, theme["green"], bold=True)
    _text(slide, correction, 7.06, 2.96, 5.08, 1.62, 21, theme["ink"], bold=True)
    _text(slide, "用反例、边界或独立作答确认理解。", 7.06, 5.08, 4.9, 0.38, 12, theme["muted"])


def _render_practice(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    _heading(slide, unit, theme)
    exercise = _find_block(unit, "exercise") or (unit.blocks[0] if unit.blocks else None)
    _shape(slide, 0.78, 1.82, 7.52, 4.64, "FFFFFF", radius=True, line="DADFEB")
    _text(slide, exercise.title if exercise and exercise.title else "先独立作答", 1.12, 2.13, 2.4, 0.35, 12, theme["accent"], bold=True)
    if exercise and exercise.items:
        _bullets(slide, exercise.items, 1.12, 2.75, 6.78, 2.95, 15, theme["ink"], theme["accent"])
    else:
        _text(slide, exercise.content if exercise else unit.key_message, 1.12, 2.75, 6.78, 2.95, 17, theme["ink"], bold=True)
    _shape(slide, 8.58, 1.82, 3.97, 4.64, theme["amber_soft"], radius=True)
    _text(slide, "检查标准", 8.91, 2.13, 1.7, 0.34, 12, theme["amber"], bold=True)
    checks = [item for block in unit.blocks if block is not exercise for item in (block.items or [block.content]) if item]
    _bullets(slide, checks[:4] or ["能说明理由", "能处理边界", "能独立完成"], 8.91, 2.82, 3.30, 2.82, 13, theme["ink"], theme["amber"])


def _render_recap(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    _heading(slide, unit, theme)
    blocks = unit.blocks[:3]
    for index, block in enumerate(blocks):
        y = 1.8 + index * 1.58
        accent = [theme["accent"], theme["green"], theme["amber"]][index % 3]
        soft = [theme["accent_soft"], theme["green_soft"], theme["amber_soft"]][index % 3]
        _shape(slide, 0.82, y, 11.72, 1.36, soft, radius=True)
        _text(slide, block.title or f"带走 {index + 1}", 1.14, y + 0.24, 2.0, 0.31, 12, accent, bold=True)
        values = block.items or [block.content]
        _text(slide, " · ".join(value for value in values if value), 3.22, y + 0.18, 8.83, 0.94, 14, theme["ink"], bold=True)
    if unit.key_message:
        _text(slide, unit.key_message, 0.86, 6.27, 11.4, 0.38, 13, theme["muted"], bold=True, align="center")


def _heading(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    _text(slide, unit.eyebrow or unit.slide_purpose, 0.78, 0.5, 2.7, 0.3, 11, theme["accent"], bold=True)
    _text(
        slide, unit.title, 0.78, 0.88, 11.72, 0.7, 25, theme["title"], bold=True,
        font=theme["title_font"], east_asian_font=theme["title_east_asian_font"],
    )
    _shape(slide, 0.78, 1.58, 0.72, 0.05, theme["accent"], radius=False)
    _shape(slide, 1.58, 1.58, 0.08, 0.05, theme["green"], radius=False)


def _footer(slide: Any, unit: SlideSpec, page: int, total: int, theme: dict[str, str]) -> None:
    section = unit.section_id or "COURSE"
    _text(slide, section, 0.78, 7.1, 2.4, 0.2, 8, theme["muted"], font="Aptos Mono")
    _text(slide, f"{page:02d} / {total:02d}", 11.48, 7.1, 1.02, 0.2, 8, theme["muted"], align="right", font="Aptos Mono")


def _fill_background(slide: Any, color: str) -> None:
    _shape(slide, 0, 0, 13.333, 7.5, color, radius=False)


def _shape(
    slide: Any,
    x: float,
    y: float,
    width: float,
    height: float,
    fill: str,
    *,
    radius: bool,
    line: str | None = None,
) -> Any:
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Inches

    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(width), Inches(height))
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor.from_string(fill)
    if line:
        shape.line.color.rgb = RGBColor.from_string(line)
        shape.line.width = Inches(0.008)
    else:
        shape.line.fill.background()
    if radius and hasattr(shape, "adjustments") and len(shape.adjustments):
        shape.adjustments[0] = 0.08
    return shape


def _text(
    slide: Any,
    value: str,
    x: float,
    y: float,
    width: float,
    height: float,
    size: int,
    color: str,
    *,
    bold: bool = False,
    align: str = "left",
    font: str = BODY_FONT,
    east_asian_font: str = BODY_EAST_ASIAN_FONT,
) -> Any:
    from pptx.dml.color import RGBColor
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.util import Inches, Pt

    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(width), Inches(height))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = Inches(0.01)
    frame.margin_top = frame.margin_bottom = Inches(0.01)
    frame.vertical_anchor = MSO_ANCHOR.TOP
    paragraph = frame.paragraphs[0]
    paragraph.text = str(value or "")
    _configure_font(paragraph.font, font, east_asian_font)
    paragraph.font.size = Pt(size)
    paragraph.font.bold = bold
    paragraph.font.color.rgb = RGBColor.from_string(color)
    paragraph.alignment = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}[align]
    paragraph.space_after = Pt(0)
    return box


def _bullets(
    slide: Any,
    items: list[str],
    x: float,
    y: float,
    width: float,
    height: float,
    size: int,
    color: str,
    bullet_color: str,
) -> Any:
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt

    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(width), Inches(height))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = Inches(0.01)
    for index, value in enumerate([str(item) for item in items if str(item).strip()]):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.text = f"•  {value}"
        _configure_font(paragraph.font, BODY_FONT)
        paragraph.font.size = Pt(size)
        paragraph.font.color.rgb = RGBColor.from_string(color)
        paragraph.space_after = Pt(max(5, size * 0.55))
        if paragraph.runs:
            paragraph.runs[0].font.color.rgb = RGBColor.from_string(bullet_color if len(value) < 1 else color)
    return box


def _table(
    slide: Any,
    headers: list[str],
    rows: list[list[str]],
    x: float,
    y: float,
    width: float,
    height: float,
    theme: dict[str, str],
) -> None:
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches, Pt

    column_count = max(1, len(headers), max((len(row) for row in rows), default=0))
    row_count = 1 + max(1, len(rows))
    table = slide.shapes.add_table(
        row_count,
        column_count,
        Inches(x),
        Inches(y),
        Inches(width),
        Inches(height),
    ).table
    for column in table.columns:
        column.width = Inches(width / column_count)
    values = [headers or ["比较项"], *rows]
    for row_index in range(row_count):
        for column_index in range(column_count):
            cell = table.cell(row_index, column_index)
            cell.text = values[row_index][column_index] if row_index < len(values) and column_index < len(values[row_index]) else ""
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor.from_string(theme["accent_soft"] if row_index == 0 else ("FFFFFF" if row_index % 2 else theme["canvas"]))
            cell.margin_left = cell.margin_right = Inches(0.1)
            cell.margin_top = cell.margin_bottom = Inches(0.07)
            paragraph = cell.text_frame.paragraphs[0]
            _configure_font(paragraph.font, BODY_FONT)
            paragraph.font.size = Pt(12 if column_count >= 4 else 14)
            paragraph.font.bold = row_index == 0
            paragraph.font.color.rgb = RGBColor.from_string(theme["accent"] if row_index == 0 else theme["ink"])
            paragraph.alignment = PP_ALIGN.LEFT


def _configure_font(font: Any, latin_font: str, east_asian_font: str = BODY_EAST_ASIAN_FONT) -> None:
    """Write both Latin and East Asian typefaces into DrawingML.

    python-pptx only writes ``a:latin`` through ``Font.name``. Explicit
    ``a:ea`` prevents Chinese text from disappearing in renderers that do not
    inherit a usable theme font.
    """
    from pptx.oxml.ns import qn

    font.name = latin_font
    properties = font._element
    east_asian = properties.find(qn("a:ea"))
    if east_asian is None:
        east_asian = properties.makeelement(qn("a:ea"))
        properties.append(east_asian)
    east_asian.set("typeface", east_asian_font)


def _find_block(unit: SlideSpec, block_type: str) -> SlideBlockSpec | None:
    return next((block for block in unit.blocks if block.type == block_type), None)


def _all_items(unit: SlideSpec) -> list[str]:
    return [item for block in unit.blocks for item in block.items if item]


def _block_content(blocks: list[SlideBlockSpec], index: int) -> str:
    return blocks[index].content if len(blocks) > index else ""


def _chapter_number(title: str) -> str:
    import re

    match = re.search(r"(\d+)", title)
    return f"{int(match.group(1)):02d}" if match else "•"


__all__ = ["SlideDeckQualityError", "THEMES", "export_structured_slide_deck", "validate_theme"]
