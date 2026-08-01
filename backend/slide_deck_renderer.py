"""Editable PPTX renderer for the shared structured slide deck contract."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from slide_deck import SlideBlockSpec, SlideDeckContent, SlideSpec, validate_slide_deck
from slide_asset_repository import SlideAssetRepository, slide_asset_repository
from slide_theme import load_slide_theme_pack

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
    "qizhi-classroom": {
        "surface": "FFFDF7",
        "canvas": "FFF3D6",
        "chart_bg": "E6F2FF",
        "title": "17365D",
        "ink": "34465C",
        "muted": "6D7D91",
        "accent": "2F6FE4",
        "accent_soft": "DCE9FF",
        "green": "16856B",
        "green_soft": "E2F7F0",
        "amber": "F29D38",
        "amber_soft": "FFF0D9",
        "red": "C45443",
        "red_soft": "FCE7E3",
        "code": "14243B",
        "title_font": "Noto Sans SC",
        "title_east_asian_font": "Microsoft YaHei",
        "body_font": "Noto Sans SC",
        "body_east_asian_font": "Microsoft YaHei",
        "math_font": "Times New Roman",
    },
    "academic-editorial": {
        "surface": "FBFAF7",
        "canvas": "EFEEE9",
        "chart_bg": "E4E7E9",
        "title": "273340",
        "ink": "45515D",
        "muted": "727A82",
        "accent": "315E7D",
        "accent_soft": "DCE6EB",
        "green": "4F6D64",
        "green_soft": "E6EDEA",
        "amber": "8B6B3E",
        "amber_soft": "F2EBDD",
        "red": "824C45",
        "red_soft": "F3E4E1",
        "code": "252E35",
        "title_font": "Noto Serif SC",
        "title_east_asian_font": "SimSun",
        "body_font": "Noto Sans SC",
        "body_east_asian_font": "Microsoft YaHei",
        "math_font": "Times New Roman",
    },
    "grid-notebook": {
        "surface": "FAF8F0",
        "canvas": "F2EEDC",
        "chart_bg": "DFE8E3",
        "title": "283B36",
        "ink": "40524D",
        "muted": "73817C",
        "accent": "2D7464",
        "accent_soft": "D9EAE3",
        "green": "648B57",
        "green_soft": "E8F0E2",
        "amber": "D18A32",
        "amber_soft": "F8E9CF",
        "red": "B75A48",
        "red_soft": "F4DFDA",
        "code": "253D38",
        "title_font": "Noto Sans SC",
        "title_east_asian_font": "Microsoft YaHei",
        "body_font": "Noto Sans SC",
        "body_east_asian_font": "Microsoft YaHei",
        "math_font": "Times New Roman",
    },
    "modern-geometric": {
        "surface": "F6F3FF",
        "canvas": "E9E1FF",
        "chart_bg": "DAD2F2",
        "title": "231A4A",
        "ink": "463D62",
        "muted": "746C8B",
        "accent": "6548E8",
        "accent_soft": "DDD4FF",
        "green": "138D85",
        "green_soft": "DDF5F1",
        "amber": "F08B3E",
        "amber_soft": "FFE6D5",
        "red": "D45168",
        "red_soft": "FADCE3",
        "code": "211B3A",
        "title_font": "Noto Sans SC",
        "title_east_asian_font": "Microsoft YaHei",
        "body_font": "Noto Sans SC",
        "body_east_asian_font": "Microsoft YaHei",
        "math_font": "Times New Roman",
    },
    "dark-tech": {
        "surface": "0C1321",
        "canvas": "16243A",
        "chart_bg": "22334B",
        "title": "F3F8FF",
        "ink": "D7E3F2",
        "muted": "91A6BE",
        "accent": "4DB5FF",
        "accent_soft": "183C5A",
        "green": "40D6B1",
        "green_soft": "173D3A",
        "amber": "FFB35A",
        "amber_soft": "49351F",
        "red": "FF7385",
        "red_soft": "482631",
        "code": "070D16",
        "title_font": "Noto Sans SC",
        "title_east_asian_font": "Microsoft YaHei",
        "body_font": "Noto Sans SC",
        "body_east_asian_font": "Microsoft YaHei",
        "math_font": "Times New Roman",
    },
}

# The five v3 themes are authored once and consumed by both Vue and PPTX.
_SHARED_THEMES = load_slide_theme_pack()["themes"]
THEMES.update({name: dict(tokens) for name, tokens in _SHARED_THEMES.items()})

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
    asset_repository: SlideAssetRepository | None = None,
    course_data: dict[str, Any] | None = None,
) -> Path:
    """Render the same slide spec used by the browser preview into editable PPTX."""
    deck = SlideDeckContent.model_validate(content)
    payload = deck.model_dump(mode="json")
    if require_quality:
        if deck.schema_version == "slide_deck_v5":
            from slide_deck_v5 import (
                validate_slide_deck_v5,
                v5_contract_issues,
            )

            if course_data is not None:
                report = validate_slide_deck_v5(
                    payload,
                    course_data=course_data,
                )
            elif payload.get("quality_report"):
                embedded = dict(payload["quality_report"])
                composition_issues = v5_contract_issues(
                    list(payload.get("slides") or [])
                )
                blockers = [
                    *(embedded.get("blockers") or []),
                    *composition_issues,
                ]
                report = {
                    **embedded,
                    "passed": bool(embedded.get("passed")) and not blockers,
                    "blockers": blockers,
                }
            else:
                report = validate_slide_deck_v5(payload)
        else:
            report = validate_slide_deck(payload)
        if not report["passed"]:
            raise SlideDeckQualityError(report)

    from pptx import Presentation
    from pptx.util import Inches

    presentation = Presentation()
    presentation.slide_width = Inches(13.333)
    presentation.slide_height = Inches(7.5)
    theme_config = validate_theme(theme)
    resolved_asset_repository = asset_repository or slide_asset_repository

    for index, unit in enumerate(deck.slides):
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        _render_slide(
            slide,
            unit,
            index + 1,
            len(deck.slides),
            theme_config,
            resolved_asset_repository,
        )
        if unit.speaker_notes:
            slide.notes_slide.notes_text_frame.text = unit.speaker_notes

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    presentation.save(path)
    return path


def audit_exported_pptx(
    path: str | Path,
    *,
    expected_slide_count: int | None = None,
) -> dict[str, Any]:
    """Audit the actual PPTX object tree after export without external services."""
    from pptx import Presentation

    presentation = Presentation(path)
    issues: list[dict[str, Any]] = []
    if expected_slide_count is not None and len(presentation.slides) != expected_slide_count:
        issues.append({
            "severity": "critical",
            "code": "exported_slide_count_mismatch",
            "expected": expected_slide_count,
            "actual": len(presentation.slides),
        })
    if round(presentation.slide_width / presentation.slide_height, 3) != round(16 / 9, 3):
        issues.append({
            "severity": "critical",
            "code": "exported_aspect_ratio_invalid",
        })
    for slide_index, slide in enumerate(presentation.slides, start=1):
        visible_object_count = 0
        for shape in slide.shapes:
            left = int(shape.left)
            top = int(shape.top)
            right = left + int(shape.width)
            bottom = top + int(shape.height)
            if left < 0 or top < 0 or right > presentation.slide_width or bottom > presentation.slide_height:
                issues.append({
                    "severity": "critical",
                    "code": "exported_object_out_of_bounds",
                    "page": slide_index,
                    "shape_name": str(shape.name or ""),
                })
            if int(shape.width) > 0 and int(shape.height) > 0:
                visible_object_count += 1
        if visible_object_count == 0:
            issues.append({
                "severity": "critical",
                "code": "exported_page_has_no_objects",
                "page": slide_index,
            })
    blockers = [item for item in issues if item["severity"] == "critical"]
    return {
        "schema_version": "slide_render_review_v1",
        "reviewer": "post_export_pptx_object_audit",
        "passed": not blockers,
        "page_count": len(presentation.slides),
        "issues": issues,
        "blockers": blockers,
        "repair_attempts": 0,
    }


def validate_theme(theme: str) -> dict[str, str]:
    try:
        return THEMES[theme]
    except KeyError as exc:
        choices = ", ".join(sorted(THEMES))
        raise ValueError(f"Unknown slide theme '{theme}'. Expected one of: {choices}") from exc


V5_LAYOUT_RENDERER_NAMES = {
    "cover-minimal": "_render_cover_minimal",
    "cover-editorial": "_render_cover_editorial",
    "agenda-linear": "_render_agenda_linear",
    "chapter-entry": "_render_chapter",
    "hero-claim": "_render_claim_only",
    "editorial-body": "_render_editorial_body",
    "balanced-two-column": "_render_two_column",
    "classification-3": "_render_classification_three",
    "process-sequence": "_render_process",
    "formula-explanation": "_render_editorial_body",
    "figure-text": "_render_visual_directed",
    "diagram-full": "_render_visual_directed",
    "worked-example": "_render_worked_example",
    "parallel-examples": "_render_parallel_examples",
    "question-prompt": "_render_question_prompt",
    "practice-feedback": "_render_practice_feedback",
    "chapter-recap": "_render_chapter_recap",
    "course-synthesis": "_render_course_synthesis",
}


def _render_slide(
    slide: Any,
    unit: SlideSpec,
    page_number: int,
    page_count: int,
    theme: dict[str, str],
    asset_repository: SlideAssetRepository,
) -> None:
    _fill_background(slide, theme["surface"])
    resolved_layout = str(
        unit.quality.get("resolved_layout")
        or unit.quality.get("requested_layout")
        or unit.layout
    )
    if unit.visuals and resolved_layout not in {
        "cover",
        "cover-minimal",
        "cover-editorial",
        "roadmap",
        "agenda-linear",
        "chapter",
        "chapter-entry",
        "recap",
        "chapter-recap",
        "course-synthesis",
        "appendix",
    }:
        _render_visual_directed(slide, unit, theme, asset_repository)
        _footer(slide, unit, page_number, page_count, theme)
        return
    renderer_name = V5_LAYOUT_RENDERER_NAMES.get(resolved_layout)
    renderer = globals().get(renderer_name) if renderer_name else None
    renderer = renderer or {
        "cover": _render_cover,
        "roadmap": _render_roadmap,
        "chapter": _render_chapter,
        "objective": _render_objective,
        "concept": _render_concept,
        "comparison": _render_comparison,
        "comparison-matrix": _render_comparison,
        "process": _render_process,
        "code": _render_code,
        "misconception": _render_misconception,
        "practice": _render_practice,
        "recap": _render_recap,
        "appendix": _render_appendix,
        "hero-statement": _render_hero_statement,
        "two-column": _render_two_column,
        "case-study": _render_case_study,
        "question": _render_practice,
        "summary": _render_recap,
    }.get(resolved_layout) or {
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
        "appendix": _render_appendix,
    }.get(unit.layout, _render_concept)
    renderer(slide, unit, theme)
    if unit.layout != "cover":
        _footer(slide, unit, page_number, page_count, theme)


def _render_visual_directed(
    slide: Any,
    unit: SlideSpec,
    theme: dict[str, str],
    asset_repository: SlideAssetRepository,
) -> None:
    """Render one dominant visual and the complete source body on a flat canvas."""
    visual = dict(unit.visuals[0])
    kind = str(visual.get("kind") or "none")
    _heading(slide, unit, theme)
    if kind in {"source_image", "generated_illustration"}:
        if _render_image_visual(
            slide,
            unit,
            visual,
            theme,
            asset_repository,
        ):
            return
    if kind in {"relational_diagram", "rule_diagram"}:
        _render_relational_visual(slide, unit, visual, theme)
        return
    if kind == "coordinate_plot":
        _render_coordinate_visual(slide, unit, visual, theme)
        return
    if kind == "chart":
        _render_chart_visual(slide, unit, visual, theme)
        return
    if kind == "table":
        _render_table_visual(slide, unit, visual, theme)
        return
    if kind == "formula":
        _render_formula_visual(slide, unit, visual, theme)
        return
    if kind == "code":
        _render_code_visual(slide, unit, visual, theme)
        return
    if not _visible_source_text(unit):
        _render_navigation_statement(slide, unit, theme, heading_already_rendered=True)
        return
    _render_editorial_body(slide, unit, theme)


def _render_relational_visual(
    slide: Any,
    unit: SlideSpec,
    visual: dict[str, Any],
    theme: dict[str, str],
) -> None:
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_CONNECTOR
    from pptx.util import Inches

    nodes = list(visual.get("nodes") or [])[:5]
    edges = list(visual.get("edges") or [])[:10]
    composition = unit.composition or "split-visual"
    visual_left = composition in {"figure-first", "diagram-full"}
    diagram_x = 0.78 if visual_left else 7.0
    text_x = 7.22 if visual_left else 0.78
    diagram_w = 5.95
    text_w = 5.32
    _source_panel(slide, unit, text_x, 1.92, text_w, 4.62, theme)
    _shape(
        slide,
        diagram_x,
        1.92,
        diagram_w,
        4.62,
        theme["canvas"],
        radius=True,
        line=theme["chart_bg"],
    )
    _text(
        slide,
        _visual_caption(visual),
        diagram_x + 0.32,
        2.15,
        diagram_w - 0.64,
        0.34,
        11,
        theme["accent"],
        bold=True,
    )
    if not nodes:
        return
    vertical = str((visual.get("parameters") or {}).get("direction") or "") == "vertical"
    positions: dict[str, tuple[float, float, float, float]] = {}
    if vertical:
        gap = 0.07
        available_height = 3.62
        node_h = min(
            0.72,
            (available_height - gap * max(0, len(nodes) - 1)) / max(1, len(nodes)),
        )
        for index, node in enumerate(nodes):
            positions[str(node.get("node_id"))] = (
                diagram_x + 0.55,
                2.62 + index * (node_h + gap),
                diagram_w - 1.1,
                node_h,
            )
    else:
        columns = 2 if len(nodes) > 3 else 1
        if columns == 1:
            node_w = (diagram_w - 1.1 - max(0, len(nodes) - 1) * 0.18) / len(nodes)
            for index, node in enumerate(nodes):
                positions[str(node.get("node_id"))] = (
                    diagram_x + 0.55 + index * (node_w + 0.18),
                    3.25,
                    node_w,
                    1.28,
                )
        else:
            node_w = (diagram_w - 1.28) / 2
            for index, node in enumerate(nodes):
                row, column = divmod(index, 2)
                positions[str(node.get("node_id"))] = (
                    diagram_x + 0.46 + column * (node_w + 0.22),
                    2.78 + row * 1.52,
                    node_w,
                    1.12,
                )

    # Connectors are deliberately created first so they remain behind nodes.
    edge_labels: list[tuple[str, float, float]] = []
    for edge in edges:
        source = positions.get(str(edge.get("source") or ""))
        target = positions.get(str(edge.get("target") or ""))
        if not source or not target:
            continue
        x1 = source[0] + source[2] / 2
        y1 = source[1] + source[3] / 2
        x2 = target[0] + target[2] / 2
        y2 = target[1] + target[3] / 2
        connector = slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT,
            Inches(x1),
            Inches(y1),
            Inches(x2),
            Inches(y2),
        )
        connector.line.color.rgb = RGBColor.from_string(theme["muted"])
        connector.line.width = Inches(0.018)
        edge_label = str(edge.get("label") or "").strip()
        if edge_label:
            edge_labels.append((edge_label, (x1 + x2) / 2, (y1 + y2) / 2))

    for edge_label, x, y in edge_labels:
        _text(
            slide,
            _diagram_label(edge_label),
            x - 0.68,
            y - 0.22,
            1.36,
            0.4,
            9,
            theme["muted"],
            bold=True,
            align="center",
        )

    for node in nodes:
        node_id = str(node.get("node_id") or "")
        x, y, width, height = positions[node_id]
        primary = str(node.get("emphasis") or "") == "primary"
        full_label = str(node.get("label") or "")
        visible_label = _diagram_label(full_label, maximum=18)
        label_size = 16
        shape = _shape(
            slide,
            x,
            y,
            width,
            height,
            theme["accent_soft"] if primary else theme["surface"],
            radius=True,
            line=theme["accent"] if primary else theme["chart_bg"],
        )
        _set_alt_text(shape, full_label)
        _text(
            slide,
            visible_label,
            x + 0.15,
            y + 0.09,
            width - 0.3,
            height - 0.16,
            label_size,
            theme["title"] if primary else theme["ink"],
            bold=primary or len(visible_label) < 18,
            align="center",
        )


def _render_formula_visual(
    slide: Any,
    unit: SlideSpec,
    visual: dict[str, Any],
    theme: dict[str, str],
) -> None:
    formula = str((visual.get("parameters") or {}).get("formula") or "").strip()
    if not formula:
        formula = next(
            (
                block.content
                for block in unit.blocks
                if block.metadata.get("formula")
            ),
            "",
        )
    if not formula:
        _render_editorial_body(slide, unit, theme)
        return
    supporting_blocks = [
        block
        for block in unit.blocks
        if not block.metadata.get("formula")
    ]
    has_supporting_copy = bool(supporting_blocks)
    formula_width = 7.15 if has_supporting_copy else 11.78
    _shape(
        slide,
        0.78,
        1.92,
        formula_width,
        4.62,
        theme["canvas"],
        radius=True,
        line=theme["chart_bg"],
    )
    _text(slide, "关键公式", 1.15, 2.22, 1.4, 0.3, 11, theme["accent"], bold=True)
    display_formula = _format_formula_text(formula)
    _text(
        slide,
        display_formula,
        1.14,
        2.78 if "\n" in display_formula else 3.08,
        formula_width - 0.72,
        2.35 if "\n" in display_formula else 1.55,
        28 if len(display_formula) < 72 else 22,
        theme["title"],
        bold=False,
        align="center",
        font=theme["math_font"],
        east_asian_font=theme["body_east_asian_font"],
    )
    if has_supporting_copy:
        supporting = SlideSpec.model_validate({
            **unit.model_dump(mode="json"),
            "blocks": [block.model_dump(mode="json") for block in supporting_blocks],
        })
        _source_panel(slide, supporting, 8.2, 1.92, 4.36, 4.62, theme)


def _plain_formula(value: str) -> str:
    clean = str(value or "").strip()
    clean = re.sub(r"^\s*(?:\$\$|\\\[)", "", clean)
    clean = re.sub(r"(?:\$\$|\\\])\s*$", "", clean)
    return clean.strip()


_SUBSCRIPT = str.maketrans("0123456789+-=()aehijklmnoprstuvx", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ")
_SUPERSCRIPT = str.maketrans({
    **dict(zip("0123456789+-=()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾", strict=True)),
    **{
        "a": "ᵃ", "b": "ᵇ", "c": "ᶜ", "d": "ᵈ", "e": "ᵉ",
        "f": "ᶠ", "g": "ᵍ", "h": "ʰ", "i": "ⁱ", "j": "ʲ",
        "k": "ᵏ", "l": "ˡ", "m": "ᵐ", "n": "ⁿ", "o": "ᵒ",
        "p": "ᵖ", "r": "ʳ", "s": "ˢ", "t": "ᵗ", "u": "ᵘ",
        "v": "ᵛ", "w": "ʷ", "x": "ˣ", "y": "ʸ", "z": "ᶻ",
    },
})
_FORMULA_SYMBOLS = {
    r"\Longleftrightarrow": "⟺",
    r"\Leftrightarrow": "⇔",
    r"\longrightarrow": "⟶",
    r"\rightarrow": "→",
    r"\mapsto": "↦",
    r"\subseteq": "⊆",
    r"\supseteq": "⊇",
    r"\mathbf": "",
    r"\boldsymbol": "",
    r"\operatorname": "",
    r"\mathrm": "",
    r"\mathbb": "",
    r"\text": "",
    r"\rank": "rank",
    r"\dim": "dim",
    r"\min": "min",
    r"\max": "max",
    r"\ker": "ker",
    r"\det": "det",
    r"\cdots": "⋯",
    r"\vdots": "⋮",
    r"\times": "×",
    r"\approx": "≈",
    r"\neq": "≠",
    r"\leq": "≤",
    r"\geq": "≥",
    r"\subset": "⊂",
    r"\supset": "⊃",
    r"\forall": "∀",
    r"\exists": "∃",
    r"\lambda": "λ",
    r"\alpha": "α",
    r"\beta": "β",
    r"\gamma": "γ",
    r"\theta": "θ",
    r"\sigma": "σ",
    r"\sum": "∑",
    r"\Sigma": "Σ",
    r"\Delta": "Δ",
    r"\Omega": "Ω",
    r"\prod": "∏",
    r"\cap": "∩",
    r"\cup": "∪",
    r"\land": "∧",
    r"\lor": "∨",
    r"\in": "∈",
    r"\mid": "∣",
    r"\quad": "  ",
    r"\left": "",
    r"\right": "",
}


def _format_formula_text(value: str) -> str:
    """Compile common course LaTeX into portable, editable mathematical text."""
    expression = _plain_formula(value)
    expression = re.sub(
        r"\\sum_\{([^{}]+)\}\^\{([^{}]+)\}",
        lambda match: (
            "∑"
            + _script_text(match.group(1), _SUBSCRIPT, "_")
            + _script_text(match.group(2), _SUPERSCRIPT, "^")
        ),
        expression,
    )
    expression = re.sub(
        r"\\sum_\{([^{}]+)\}\^([A-Za-z0-9])",
        lambda match: (
            "∑"
            + _script_text(match.group(1), _SUBSCRIPT, "_")
            + _script_text(match.group(2), _SUPERSCRIPT, "^")
        ),
        expression,
    )
    matrix_pattern = re.compile(
        r"\\begin\{(?P<kind>[bp]?matrix)\}(?P<body>.*?)\\end\{(?P=kind)\}",
        re.DOTALL,
    )
    expression = matrix_pattern.sub(
        lambda match: _format_formula_matrix(match.group("body"), match.group("kind")),
        expression,
    )
    # Some imported course documents JSON-escape LaTeX commands twice. Matrix
    # row separators have already been consumed above, so the remaining paired
    # slashes can safely be normalized back to one command introducer.
    expression = re.sub(r"\\\\(?=[A-Za-z{}])", r"\\", expression)
    expression = re.sub(
        r"\\frac\{([^{}]+)\}\{([^{}]+)\}",
        lambda match: f"({match.group(1)})⁄({match.group(2)})",
        expression,
    )
    for command, symbol in sorted(_FORMULA_SYMBOLS.items(), key=lambda item: -len(item[0])):
        expression = expression.replace(command, symbol)
    expression = expression.replace(r"\{", "⦃").replace(r"\}", "⦄")
    expression = re.sub(
        r"([∑Σ])_([A-Za-z0-9]+)=([A-Za-z0-9]+)\^([A-Za-z0-9]+)",
        lambda match: (
            "∑"
            + _script_text(f"{match.group(2)}={match.group(3)}", _SUBSCRIPT, "_")
            + _script_text(match.group(4), _SUPERSCRIPT, "^")
        ),
        expression,
    )
    expression = re.sub(
        r"_\{([^{}]+)\}",
        lambda match: _script_text(match.group(1), _SUBSCRIPT, "_"),
        expression,
    )
    expression = re.sub(
        r"\^\{([^{}]+)\}",
        lambda match: _script_text(match.group(1), _SUPERSCRIPT, "^"),
        expression,
    )
    expression = re.sub(
        r"_([A-Za-z0-9+\-=()])",
        lambda match: _script_text(match.group(1), _SUBSCRIPT, "_"),
        expression,
    )
    expression = re.sub(
        r"\^([A-Za-z0-9+\-=()])",
        lambda match: _script_text(match.group(1), _SUPERSCRIPT, "^"),
        expression,
    )
    expression = (
        expression.replace("{", "")
        .replace("}", "")
        .replace("⦃", "{")
        .replace("⦄", "}")
    )
    expression = re.sub(r"[ \t]+", " ", expression)
    expression = re.sub(r" *\n *", "\n", expression)
    return expression.strip(" ,")


def _display_text(value: str) -> str:
    """Format math markup for display while retaining the source text in the model."""
    text = str(value or "")
    if "\\" not in text and "$" not in text:
        return text
    return _format_formula_text(text)


def _script_text(value: str, translation: dict[int, str], marker: str) -> str:
    rendered = str(value).translate(translation)
    return rendered if all(ord(character) in translation for character in str(value)) else f"{marker}{value}"


def _format_formula_matrix(body: str, kind: str) -> str:
    rows = [
        _format_formula_text(row.replace("&", "  "))
        for row in re.split(r"\\\\", body)
        if row.strip()
    ]
    if not rows:
        return ""
    brackets = ("(", ")") if kind == "pmatrix" else ("⎡", "⎤")
    if len(rows) == 1:
        return f"{brackets[0]} {rows[0]} {brackets[1]}"
    lines: list[str] = []
    for index, row in enumerate(rows):
        left = brackets[0] if index == 0 else ("⎣" if index == len(rows) - 1 else "⎢")
        right = brackets[1] if index == 0 else ("⎦" if index == len(rows) - 1 else "⎥")
        lines.append(f"{left} {row} {right}")
    return "\n".join(lines)


def _render_code_visual(
    slide: Any,
    unit: SlideSpec,
    visual: dict[str, Any],
    theme: dict[str, str],
) -> None:
    code = _find_block(unit, "code")
    _shape(slide, 0.78, 1.92, 7.65, 4.62, theme["code"], radius=True)
    _text(slide, "SOURCE", 1.12, 2.18, 1.2, 0.28, 11, "AEB6D0", bold=True, font=CODE_FONT)
    _text(
        slide,
        code.content if code else "",
        1.12,
        2.7,
        6.92,
        3.38,
        16,
        "F5F7FF",
        font=CODE_FONT,
        east_asian_font=theme["body_east_asian_font"],
    )
    supporting = SlideSpec.model_validate({
        **unit.model_dump(mode="json"),
        "blocks": [
            block.model_dump(mode="json")
            for block in unit.blocks
            if block is not code
        ],
    })
    _source_panel(slide, supporting, 8.7, 1.92, 3.86, 4.62, theme)


def _render_table_visual(
    slide: Any,
    unit: SlideSpec,
    visual: dict[str, Any],
    theme: dict[str, str],
) -> None:
    parameters = visual.get("parameters") or {}
    parameter_rows = parameters.get("rows") or []
    if parameter_rows:
        _table(
            slide,
            [str(value) for value in parameters.get("headers") or ["顺序", "课程原文要点"]],
            [[str(value) for value in row] for row in parameter_rows],
            0.78,
            1.92,
            7.18,
            4.62,
            theme,
        )
        _source_panel(slide, unit, 8.2, 1.92, 4.36, 4.62, theme)
        return
    block = next(
        (
            item for item in unit.blocks
            if item.metadata.get("rows")
        ),
        None,
    )
    if block is None:
        _source_panel(slide, unit, 0.78, 1.92, 11.78, 4.62, theme)
        return
    _table(
        slide,
        [str(value) for value in block.metadata.get("headers") or []],
        [[str(value) for value in row] for row in block.metadata.get("rows") or []],
        0.78,
        1.92,
        11.78,
        4.62,
        theme,
    )


def _render_coordinate_visual(
    slide: Any,
    unit: SlideSpec,
    visual: dict[str, Any],
    theme: dict[str, str],
) -> None:
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_CONNECTOR
    from pptx.util import Inches

    _source_panel(slide, unit, 0.78, 1.92, 4.65, 4.62, theme)
    _shape(slide, 5.72, 1.92, 6.84, 4.62, theme["canvas"], radius=True, line=theme["chart_bg"])
    origin_x, origin_y = 8.98, 4.38
    for x1, y1, x2, y2 in (
        (6.25, origin_y, 12.05, origin_y),
        (origin_x, 2.36, origin_x, 6.0),
    ):
        axis = slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT,
            Inches(x1),
            Inches(y1),
            Inches(x2),
            Inches(y2),
        )
        axis.line.color.rgb = RGBColor.from_string(theme["muted"])
    parameters = visual.get("parameters") or {}
    points = list(parameters.get("points") or [])
    labels = [str(item) for item in parameters.get("point_labels") or []]
    maximum = max(
        1.0,
        max(
            (abs(float(value)) for point in points[:10] for value in point[:2]),
            default=1.0,
        ),
    )
    x_scale = 2.25 / maximum
    y_scale = 1.52 / maximum
    rendered_points = [
        (
            origin_x + float(raw_x) * x_scale,
            origin_y - float(raw_y) * y_scale,
        )
        for raw_x, raw_y in points[:10]
    ]
    if parameters.get("connect_points") and len(rendered_points) >= 2:
        connector = slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT,
            Inches(rendered_points[0][0]),
            Inches(rendered_points[0][1]),
            Inches(rendered_points[1][0]),
            Inches(rendered_points[1][1]),
        )
        connector.line.color.rgb = RGBColor.from_string(theme["accent"])
        connector.line.width = Inches(0.025)
    for index, (x, y) in enumerate(rendered_points):
        shape = _shape(slide, x - 0.07, y - 0.07, 0.14, 0.14, theme["accent"], radius=True)
        label = labels[index] if index < len(labels) else ""
        _set_alt_text(shape, label or str(visual.get("alt_text") or "坐标数据点"))
        _text(
            slide,
            label,
            x + 0.12,
            y - 0.34,
            1.1,
            0.3,
            16,
            theme["ink"],
            bold=True,
        )
    axis_labels = [str(item) for item in parameters.get("axis_labels") or ["x", "y"]]
    _text(slide, axis_labels[0], 12.04, origin_y - 0.28, 0.22, 0.24, 12, theme["muted"], bold=True)
    _text(slide, axis_labels[1], origin_x + 0.12, 2.2, 0.22, 0.24, 12, theme["muted"], bold=True)


def _render_chart_visual(
    slide: Any,
    unit: SlideSpec,
    visual: dict[str, Any],
    theme: dict[str, str],
) -> None:
    from pptx.chart.data import ChartData
    from pptx.enum.chart import XL_CHART_TYPE
    from pptx.util import Inches

    parameters = visual.get("parameters") or {}
    categories = [str(item) for item in parameters.get("categories") or []]
    series = list(parameters.get("series") or [])
    if not categories or not series:
        _source_panel(slide, unit, 0.78, 1.92, 11.78, 4.62, theme)
        return
    data = ChartData()
    data.categories = categories
    for item in series[:4]:
        values = item.get("values") or []
        if len(values) != len(categories) or not all(isinstance(value, (int, float)) for value in values):
            continue
        data.add_series(str(item.get("name") or "Series"), values)
    if not data._series:
        _source_panel(slide, unit, 0.78, 1.92, 11.78, 4.62, theme)
        return
    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        Inches(0.78),
        Inches(1.92),
        Inches(7.4),
        Inches(4.62),
        data,
    ).chart
    chart.has_legend = len(series) > 1
    _source_panel(slide, unit, 8.48, 1.92, 4.08, 4.62, theme)


def _render_image_visual(
    slide: Any,
    unit: SlideSpec,
    visual: dict[str, Any],
    theme: dict[str, str],
    asset_repository: SlideAssetRepository,
) -> bool:
    from pptx.util import Inches

    asset_id = str(visual.get("asset_id") or "")
    if not asset_id:
        return False
    try:
        image_path = asset_repository.resolve(asset_id)
    except (FileNotFoundError, ValueError):
        return False
    picture = slide.shapes.add_picture(
        str(image_path),
        Inches(0.78),
        Inches(1.92),
        width=Inches(7.2),
        height=Inches(4.62),
    )
    _set_alt_text(picture, str(visual.get("alt_text") or "课程视觉素材"))
    _source_panel(slide, unit, 8.28, 1.92, 4.28, 4.62, theme)
    return True


def _source_panel(
    slide: Any,
    unit: SlideSpec,
    x: float,
    y: float,
    width: float,
    height: float,
    theme: dict[str, str],
) -> None:
    body = _visible_source_text(unit)
    _shape(slide, x, y, width, height, theme["surface"], radius=True, line=theme["chart_bg"])
    _text(slide, "课程正文", x + 0.28, y + 0.25, 1.1, 0.28, 10, theme["muted"], bold=True)
    _text(
        slide,
        body,
        x + 0.28,
        y + 0.72,
        width - 0.56,
        height - 1.05,
        18 if len(body) <= 170 else 16,
        theme["ink"],
        font=theme["body_font"],
        east_asian_font=theme["body_east_asian_font"],
    )


def _visible_source_text(unit: SlideSpec) -> str:
    values: list[str] = []
    for block in unit.blocks:
        if block.title:
            values.append(block.title)
        if block.items:
            values.extend(f"• {item}" for item in block.items if item)
        elif block.content:
            values.append(block.content)
    return "\n\n".join(value for value in values if value)


def _diagram_label(value: str, maximum: int = 32) -> str:
    """Keep diagram nodes glanceable while preserving the full source in alt text."""
    clean = " ".join(str(value or "").split())
    if len(clean) <= maximum:
        return clean
    boundary = max(
        clean.rfind("。", 0, maximum),
        clean.rfind("；", 0, maximum),
        clean.rfind("，", 0, maximum),
        clean.rfind("）", 0, maximum),
        clean.rfind(")", 0, maximum),
        clean.rfind(" ", 0, maximum),
    )
    if boundary < maximum // 2:
        boundary = maximum
    elif clean[boundary] in "）)":
        boundary += 1
    return clean[:boundary].rstrip("。；， ")


def _visual_caption(visual: dict[str, Any]) -> str:
    diagram_type = str((visual.get("parameters") or {}).get("diagram_type") or "")
    if diagram_type:
        return {
            "process": "步骤关系",
            "cause-effect": "因果关系",
            "comparison": "对比关系",
            "mapping": "映射关系",
            "hierarchy": "概念层级",
            "reasoning": "推理关系",
        }.get(diagram_type, "概念关系")
    alt_text = str(visual.get("alt_text") or "").strip()
    if alt_text.startswith(("由课程原文", "按课程原文", "课程原文")):
        return "概念关系"
    return alt_text or "概念关系"


def _set_alt_text(shape: Any, value: str) -> None:
    try:
        non_visual = shape._element.xpath(".//p:cNvPr")[0]
        non_visual.set("descr", str(value or ""))
    except (AttributeError, IndexError):
        return


def _render_cover(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    _shape(slide, 0.58, 0.55, 0.12, 5.92, theme["accent"], radius=False)
    _shape(slide, 10.82, 0.0, 2.513, 7.5, theme["accent_soft"], radius=False)
    _shape(slide, 11.35, 0.72, 1.04, 1.04, theme["green"], radius=True)
    _text(slide, "灵知", 11.35, 0.99, 1.04, 0.34, 15, "FFFFFF", bold=True, align="center")
    _text(slide, unit.eyebrow or "课程演示", 0.92, 0.72, 4.0, 0.38, 14, theme["accent"], bold=True)
    cover_title_size = 42 if len(unit.title) > 32 else 46 if len(unit.title) > 22 else 50
    _text(
        slide, unit.title, 0.92, 1.22, 9.15, 2.6, cover_title_size, theme["title"], bold=True,
        font=theme["title_font"], east_asian_font=theme["title_east_asian_font"],
    )
    if unit.subtitle:
        _text(slide, unit.subtitle, 0.94, 3.77, 7.8, 0.42, 16, theme["muted"])
    _shape(slide, 0.92, 4.23, 8.85, 1.14, theme["canvas"], radius=True, line=theme["accent_soft"])
    _text(slide, "学习主线", 1.18, 4.48, 1.2, 0.28, 11, theme["green"], bold=True)
    _text(slide, unit.key_message or _block_content(unit.blocks, 0), 2.42, 4.35, 7.0, 0.68, 18, theme["ink"], bold=True)
    _text(slide, "同一课程结构 · 知识与能力绑定 · 可继续编辑", 0.94, 6.45, 7.0, 0.32, 11, theme["muted"])


def _render_cover_minimal(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    """Render a restrained title page with one clear focal hierarchy."""
    _shape(slide, 0.82, 0.76, 0.12, 0.72, theme["accent"], radius=False)
    _text(
        slide,
        unit.eyebrow or "课程课件",
        1.12,
        0.86,
        3.6,
        0.34,
        13,
        theme["accent"],
        bold=True,
    )
    title_size = 38 if len(unit.title) > 34 else 44 if len(unit.title) > 22 else 50
    _text(
        slide,
        unit.title,
        0.86,
        2.02,
        10.9,
        2.05,
        title_size,
        theme["title"],
        bold=True,
        font=theme["title_font"],
        east_asian_font=theme["title_east_asian_font"],
    )
    _shape(slide, 0.88, 5.5, 3.25, 0.06, theme["accent"], radius=False)
    if unit.subtitle:
        _text(slide, unit.subtitle, 0.9, 5.78, 8.4, 0.45, 16, theme["muted"])


def _render_cover_editorial(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    """Render a concise editorial cover with a balanced visual field."""
    _shape(slide, 9.25, 0.0, 4.083, 7.5, theme["accent_soft"], radius=False)
    _shape(slide, 0.88, 0.78, 0.12, 0.74, theme["accent"], radius=False)
    _text(
        slide,
        unit.eyebrow or "课程课件",
        1.18,
        0.88,
        3.8,
        0.36,
        13,
        theme["accent"],
        bold=True,
    )
    _text(
        slide,
        unit.title,
        0.9,
        2.0,
        7.65,
        2.0,
        50 if len(unit.title) <= 14 else 44,
        theme["title"],
        bold=True,
        font=theme["title_font"],
        east_asian_font=theme["title_east_asian_font"],
    )
    if unit.subtitle:
        _shape(slide, 0.92, 4.72, 5.65, 0.05, theme["accent"], radius=False)
        _text(slide, unit.subtitle, 0.94, 5.04, 7.3, 0.7, 20, theme["ink"], bold=True)
    _text(slide, "COURSE", 9.72, 1.08, 2.4, 0.42, 14, theme["accent"], bold=True)
    _text(
        slide,
        "概念\n方法\n应用",
        9.72,
        2.05,
        2.25,
        2.45,
        30,
        theme["title"],
        bold=True,
        font=theme["title_font"],
        east_asian_font=theme["title_east_asian_font"],
    )


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
        _shape(slide, x, y, 5.55, card_h, theme["canvas"], radius=True, line=theme["chart_bg"])
        _shape(slide, x + 0.22, y + 0.22, 0.5, 0.5, theme["accent_soft"], radius=True)
        _text(slide, f"{index + 1:02d}", x + 0.22, y + 0.33, 0.5, 0.2, 10, theme["accent"], bold=True, align="center")
        _text(slide, item, x + 0.9, y + 0.24, 4.35, card_h - 0.25, 17, theme["ink"], bold=True)


def _render_agenda_linear(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    """Render the course route as an editorial sequence instead of a card grid."""
    _heading(slide, unit, theme)
    items = _all_items(unit)[:6]
    if not items:
        _render_navigation_statement(slide, unit, theme, heading_already_rendered=True)
        return
    row_h = min(0.76, 4.35 / max(1, len(items)))
    for index, item in enumerate(items):
        y = 1.9 + index * row_h
        _shape(
            slide,
            0.82,
            y + row_h - 0.04,
            11.55,
            0.018,
            theme["chart_bg"],
            radius=False,
        )
        _text(
            slide,
            f"{index + 1:02d}",
            0.88,
            y + 0.13,
            0.72,
            0.28,
            11,
            theme["accent"],
            bold=True,
            font="Aptos Mono",
        )
        _text(
            slide,
            item,
            1.78,
            y + 0.08,
            9.95,
            row_h - 0.12,
            18 if len(item) <= 24 else 16,
            theme["ink"],
            bold=True,
        )


def _render_chapter(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    _shape(slide, 0.0, 0.0, 4.05, 7.5, theme["accent_soft"], radius=False)
    chapter_number = _chapter_number(unit.title)
    _text(slide, chapter_number, 0.72, 1.15, 2.5, 1.35, 54, theme["accent"], bold=True)
    _text(slide, unit.eyebrow or "章节转场", 4.65, 1.08, 2.3, 0.32, 12, theme["green"], bold=True)
    _text(
        slide, unit.title, 4.65, 1.62, 7.55, 1.4, 35, theme["title"], bold=True,
        font=theme["title_font"], east_asian_font=theme["title_east_asian_font"],
    )
    _shape(slide, 4.65, 3.45, 6.95, 1.55, theme["canvas"], radius=True, line=theme["chart_bg"])
    _text(slide, "本章主线", 4.98, 3.78, 1.4, 0.3, 11, theme["accent"], bold=True)
    chapter_message = (
        unit.key_message
        or _block_content(unit.blocks, 0)
        or unit.teaching_job
        or unit.takeaway
    )
    _text(slide, chapter_message, 4.98, 4.12, 6.18, 0.62, 16, theme["ink"], bold=True)


def _render_objective(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    if not _visible_source_text(unit) and not unit.key_message:
        _render_navigation_statement(slide, unit, theme)
        return
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
        _shape(slide, x, 2.87, width, 3.52, theme["canvas"], radius=True, line=theme["chart_bg"])
        accent = [theme["accent"], theme["green"], theme["amber"]][index % 3]
        _shape(slide, x, 2.87, 0.08, 3.52, accent, radius=False)
        _text(
            slide,
            block.title or unit.eyebrow or f"要点 {index + 1}",
            x + 0.3,
            3.14,
            width - 0.55,
            0.46,
            15,
            accent,
            bold=True,
        )
        if block.items:
            item_size = 19 if len(blocks) == 1 and len(block.items) <= 3 else 16
            _bullets(slide, block.items, x + 0.3, 3.72, width - 0.58, 2.25, item_size, theme["ink"], accent)
        else:
            is_formula = bool(block.metadata.get("formula"))
            body_size = (
                26
                if len(blocks) == 1 and len(block.content) <= 70
                else 21
                if len(blocks) == 1 and len(block.content) <= 150
                else 16
            )
            _text(
                slide,
                block.content,
                x + 0.3,
                3.76,
                width - 0.58,
                2.18,
                body_size,
                theme["ink"],
                font=theme["math_font"] if is_formula else theme["body_font"],
                east_asian_font=theme["body_east_asian_font"],
            )


def _render_hero_statement(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    _heading(slide, unit, theme)
    body = " ".join(
        value
        for block in unit.blocks
        for value in (block.items or [block.content])
        if value
    )
    body = body or unit.takeaway or unit.teaching_job or unit.title
    _shape(slide, 0.82, 1.82, 11.68, 4.52, theme["accent_soft"], radius=True)
    _shape(slide, 1.16, 2.2, 0.12, 3.72, theme["accent"], radius=False)
    _text(slide, "核心判断", 1.58, 2.24, 2.0, 0.34, 12, theme["accent"], bold=True)
    _text(
        slide,
        body,
        1.58,
        2.92,
        9.9,
        2.42,
        27 if len(body) <= 90 else 21,
        theme["ink"],
        bold=len(body) <= 90,
        font=theme["title_font"],
        east_asian_font=theme["title_east_asian_font"],
    )


def _render_claim_only(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    """Render a promoted one-sentence claim once, without a duplicate body panel."""
    _heading(slide, unit, theme)
    _shape(slide, 0.9, 2.25, 0.12, 3.35, theme["accent"], radius=False)
    _text(
        slide,
        unit.teaching_job or unit.eyebrow or "核心判断",
        1.4,
        2.3,
        3.4,
        0.38,
        13,
        theme["accent"],
        bold=True,
    )
    _shape(slide, 1.4, 4.95, 4.25, 0.05, theme["chart_bg"], radius=False)


def _render_navigation_statement(
    slide: Any,
    unit: SlideSpec,
    theme: dict[str, str],
    *,
    heading_already_rendered: bool = False,
) -> None:
    """Render source-free navigation beats without empty UI-like containers."""
    if not heading_already_rendered:
        _heading(slide, unit, theme)
    topic = _heading_excerpt(unit.title, 42)
    if unit.layout in {"recap", "summary"}:
        prefix = "本章回顾"
        detail = unit.takeaway or unit.key_message or f"回到“{topic}”，串联本章的概念、方法与应用。"
    else:
        prefix = "本节学习问题"
        detail = unit.teaching_job or unit.takeaway or f"围绕“{topic}”，建立定义、判断方法与应用联系。"
    _shape(slide, 0.92, 2.18, 0.12, 3.5, theme["accent"], radius=False)
    _text(slide, prefix, 1.38, 2.22, 2.5, 0.36, 12, theme["accent"], bold=True)
    _text(
        slide,
        detail,
        1.38,
        2.92,
        10.3,
        1.72,
        27 if len(detail) <= 42 else 22,
        theme["ink"],
        bold=True,
        font=theme["title_font"],
        east_asian_font=theme["title_east_asian_font"],
    )
    _text(
        slide,
        "先明确问题，再连接概念、方法与检验。",
        1.38,
        5.18,
        8.8,
        0.42,
        14,
        theme["muted"],
    )


def _render_classification_three(
    slide: Any,
    unit: SlideSpec,
    theme: dict[str, str],
) -> None:
    """Render exactly three peer concepts as equal semantic columns."""
    _heading(slide, unit, theme)
    items = _all_items(unit)[:3]
    if len(items) != 3:
        _render_concept(slide, unit, theme)
        return
    accents = (theme["accent"], theme["green"], theme["amber"])
    for index, item in enumerate(items):
        x = 0.82 + index * 3.92
        _shape(slide, x, 2.02, 3.58, 0.08, accents[index], radius=False)
        _text(
            slide,
            f"{index + 1:02d}",
            x,
            2.35,
            0.72,
            0.3,
            11,
            accents[index],
            bold=True,
            font="Aptos Mono",
        )
        _text(
            slide,
            item,
            x,
            3.0,
            3.38,
            2.35,
            18 if len(item) <= 48 else 16,
            theme["ink"],
            bold=True,
        )
        if index < 2:
            _shape(
                slide,
                x + 3.72,
                2.02,
                0.018,
                3.95,
                theme["chart_bg"],
                radius=False,
            )


def _render_editorial_body(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    if not _visible_source_text(unit):
        _render_navigation_statement(slide, unit, theme)
        return
    _heading(slide, unit, theme)
    values = [
        value
        for block in unit.blocks
        for value in (block.items or [block.content])
        if value
    ]
    body = "\n\n".join(values)
    _shape(slide, 0.86, 1.92, 0.1, 4.32, theme["accent"], radius=False)
    _text(
        slide,
        body,
        1.34,
        2.3,
        10.75,
        3.55,
        26 if len(body) <= 90 else 22 if len(body) <= 180 else 17,
        theme["ink"],
    )
    _shape(slide, 1.34, 6.13, 4.35, 0.025, theme["chart_bg"], radius=False)


def _render_two_column(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    _heading(slide, unit, theme)
    values = [
        value
        for block in unit.blocks
        for value in (block.items or [block.content])
        if value
    ]
    if len(values) == 1:
        paragraphs = [item for item in values[0].split("\n\n") if item.strip()]
        if len(paragraphs) > 1:
            split_at = (len(paragraphs) + 1) // 2
            values = [
                "\n\n".join(paragraphs[:split_at]),
                "\n\n".join(paragraphs[split_at:]),
            ]
    if len(values) < 2:
        _render_editorial_body(slide, unit, theme)
        return
    labels = ("依据", "推论")
    colors = (
        (theme["accent_soft"], theme["accent"]),
        (theme["green_soft"], theme["green"]),
    )
    for index, value in enumerate(values[:2]):
        x = 0.82 + index * 5.92
        soft, accent = colors[index]
        _shape(slide, x, 1.9, 5.58, 4.38, soft, radius=True)
        _text(slide, labels[index], x + 0.34, 2.2, 1.2, 0.32, 12, accent, bold=True)
        _text(slide, value, x + 0.34, 2.82, 4.9, 2.85, 17, theme["ink"])


def _render_case_study(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    _heading(slide, unit, theme)
    values = [
        value
        for block in unit.blocks
        for value in (block.items or [block.content])
        if value
    ]
    body = "\n\n".join(values)
    _shape(slide, 0.82, 1.82, 3.0, 4.55, theme["green_soft"], radius=True)
    _text(slide, "CASE", 1.18, 2.2, 1.2, 0.36, 13, theme["green"], bold=True)
    _text(slide, "从具体情境\n检验抽象结构", 1.18, 3.0, 2.24, 1.35, 24, theme["ink"], bold=True)
    _shape(slide, 4.12, 1.82, 8.38, 4.55, theme["canvas"], radius=True, line=theme["chart_bg"])
    _text(slide, "案例观察", 4.48, 2.18, 1.6, 0.32, 12, theme["accent"], bold=True)
    _text(slide, body, 4.48, 2.82, 7.3, 2.95, 18 if len(body) <= 180 else 16, theme["ink"])


def _render_parallel_examples(
    slide: Any,
    unit: SlideSpec,
    theme: dict[str, str],
) -> None:
    """Render peer examples without implying causality or reasoning order."""
    _heading(slide, unit, theme)
    values = _all_items(unit)[:4]
    if len(values) < 2:
        _render_editorial_body(slide, unit, theme)
        return
    gap = 0.28
    width = (11.55 - gap * (len(values) - 1)) / len(values)
    for index, value in enumerate(values):
        x = 0.88 + index * (width + gap)
        _shape(slide, x, 2.08, width, 0.07, theme["accent"], radius=False)
        _text(slide, f"{index + 1:02d}", x, 2.42, 0.68, 0.28, 11, theme["accent"], bold=True)
        _text(
            slide,
            value,
            x,
            3.0,
            width - 0.12,
            2.35,
            19 if len(value) <= 48 else 16,
            theme["ink"],
            bold=True,
        )


def _render_question_prompt(
    slide: Any,
    unit: SlideSpec,
    theme: dict[str, str],
) -> None:
    """Render one practice prompt as a flat, presentation-first composition."""
    _heading(slide, unit, theme)
    prompt = _block_content(unit.blocks, 0) or unit.key_message or unit.takeaway
    _shape(slide, 0.92, 2.18, 0.11, 3.5, theme["accent"], radius=False)
    _text(slide, "先独立判断", 1.42, 2.24, 2.4, 0.34, 13, theme["accent"], bold=True)
    _text(
        slide,
        prompt,
        1.42,
        3.0,
        10.45,
        2.25,
        25 if len(prompt) <= 88 else 20,
        theme["ink"],
        bold=True,
        font=theme["title_font"],
        east_asian_font=theme["title_east_asian_font"],
    )


def _worked_example_labels(quality: dict[str, Any], count: int) -> tuple[str, ...]:
    explicit = tuple(
        str(item).strip()
        for item in quality.get("worked_step_labels") or []
        if str(item).strip()
    )
    if len(explicit) >= count:
        return explicit[:count]
    return tuple(f"步骤 {index + 1}" for index in range(count))


def _render_worked_example(
    slide: Any,
    unit: SlideSpec,
    theme: dict[str, str],
) -> None:
    """Render a worked example as a visible reasoning path."""
    _heading(slide, unit, theme)
    values = [
        value
        for block in unit.blocks
        for value in (block.items or [block.content])
        if value
    ]
    if not values:
        _render_navigation_statement(slide, unit, theme)
        return
    if len(values) == 1:
        values = [
            item.strip()
            for item in values[0].split("\n\n")
            if item.strip()
        ]
    if len(values) < 2:
        _render_case_study(slide, unit, theme)
        return
    labels = _worked_example_labels(unit.quality, min(3, len(values)))
    accents = (theme["accent"], theme["green"], theme["amber"])
    _shape(slide, 1.14, 2.17, 0.035, 3.72, theme["chart_bg"], radius=False)
    for index, (label, value) in enumerate(zip(labels, values[:3])):
        y = 1.92 + index * 1.38
        accent = accents[index]
        _shape(slide, 0.88, y + 0.17, 0.55, 0.55, accent, radius=True)
        _text(
            slide,
            str(index + 1),
            0.88,
            y + 0.34,
            0.55,
            0.18,
            11,
            "FFFFFF",
            bold=True,
            align="center",
        )
        _text(slide, label, 1.72, y + 0.1, 1.2, 0.3, 12, accent, bold=True)
        _text(
            slide,
            value,
            3.0,
            y,
            9.02,
            0.96,
            18 if len(value) <= 90 else 16,
            theme["ink"],
            bold=index == 2,
        )
        if index < len(labels) - 1:
            _shape(
                slide,
                1.72,
                y + 1.1,
                10.28,
                0.02,
                theme["chart_bg"],
                radius=False,
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
        _shape(slide, x, 2.08, width, 3.72, theme["canvas"], radius=True, line=theme["chart_bg"])
        _shape(slide, x + 0.22, 2.34, 0.58, 0.58, theme["accent"], radius=True)
        _text(slide, str(index + 1), x + 0.22, 2.52, 0.58, 0.2, 12, "FFFFFF", bold=True, align="center")
        _text(slide, item, x + 0.23, 3.25, width - 0.46, 1.95, 16, theme["ink"], bold=True)
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
    _shape(slide, 0.78, 1.82, 7.52, 4.64, theme["canvas"], radius=True, line=theme["chart_bg"])
    _text(slide, exercise.title if exercise and exercise.title else "先独立作答", 1.12, 2.13, 2.4, 0.35, 12, theme["accent"], bold=True)
    if exercise and exercise.items:
        _bullets(slide, exercise.items, 1.12, 2.75, 6.78, 2.95, 15, theme["ink"], theme["accent"])
    else:
        _text(slide, exercise.content if exercise else unit.key_message, 1.12, 2.75, 6.78, 2.95, 17, theme["ink"], bold=True)
    _shape(slide, 8.58, 1.82, 3.97, 4.64, theme["amber_soft"], radius=True)
    _text(slide, "检查标准", 8.91, 2.13, 1.7, 0.34, 12, theme["amber"], bold=True)
    checks = [item for block in unit.blocks if block is not exercise for item in (block.items or [block.content]) if item]
    _bullets(slide, checks[:4] or ["能说明理由", "能处理边界", "能独立完成"], 8.91, 2.82, 3.30, 2.82, 13, theme["ink"], theme["amber"])


def _render_practice_feedback(
    slide: Any,
    unit: SlideSpec,
    theme: dict[str, str],
) -> None:
    """Align every task with its answer instead of creating imbalanced columns."""
    _heading(slide, unit, theme)
    exercise = _find_block(unit, "exercise") or (
        unit.blocks[0] if unit.blocks else None
    )
    feedback_blocks = [
        block
        for block in unit.blocks
        if block is not exercise
    ]
    prompts = []
    if exercise:
        prompts = list(exercise.items) if exercise.items else [exercise.content]
    prompts = [value for value in prompts if value][:3]
    checks = [
        value
        for block in feedback_blocks
        for value in (block.items or [block.content])
        if value
    ]
    checks = checks[:3]
    if not prompts:
        prompts = [unit.key_message or unit.takeaway]
    prompts = [value for value in prompts if value]
    row_count = max(len(prompts), 1)
    row_height = 4.48 / row_count
    for index, prompt in enumerate(prompts):
        y = 1.9 + index * row_height
        answer = checks[index] if index < len(checks) else ""
        _shape(
            slide,
            0.82,
            y,
            11.72,
            0.018,
            theme["chart_bg"],
            radius=False,
        )
        _text(
            slide,
            f"问题 {index + 1:02d}",
            1.05,
            y + 0.22,
            1.45,
            0.28,
            11,
            theme["accent"],
            bold=True,
        )
        _text(
            slide,
            "回答与判断依据",
            7.25,
            y + 0.22,
            2.0,
            0.28,
            11,
            theme["green"],
            bold=True,
        )
        text_top = y + 0.72
        _text(
            slide,
            prompt,
            1.05,
            text_top,
            5.55,
            max(0.7, row_height - 1.0),
            17 if len(prompt) <= 80 else 15,
            theme["ink"],
            bold=True,
        )
        if answer:
            _text(
                slide,
                answer,
                7.25,
                text_top,
                4.85,
                max(0.7, row_height - 1.0),
                16 if len(answer) <= 80 else 14,
                theme["ink"],
            )


def _render_recap(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    visible_text = _visible_source_text(unit)
    if (
        (not visible_text and not unit.key_message)
        or (
            len(unit.blocks) <= 1
            and len(visible_text.strip()) < 40
            and len(unit.key_message.strip()) < 40
        )
    ):
        _render_navigation_statement(slide, unit, theme)
        return
    _heading(slide, unit, theme)
    blocks = unit.blocks[:3]
    if len(blocks) == 1 and len(blocks[0].items) > 1:
        for index, value in enumerate(blocks[0].items[:6]):
            column = index % 2
            row = index // 2
            x = 0.82 + column * 5.92
            y = 1.82 + row * 1.43
            accent = [theme["accent"], theme["green"], theme["amber"]][row % 3]
            soft = [theme["accent_soft"], theme["green_soft"], theme["amber_soft"]][row % 3]
            _shape(slide, x, y, 5.66, 1.18, soft, radius=True)
            _text(slide, f"{index + 1:02d}", x + 0.26, y + 0.44, 0.52, 0.22, 12, accent, bold=True, align="center")
            _text(slide, value, x + 0.92, y + 0.28, 4.38, 0.62, 17, theme["ink"], bold=True)
        return
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


def _render_chapter_recap(
    slide: Any,
    unit: SlideSpec,
    theme: dict[str, str],
) -> None:
    """Render a compact memory path instead of generic recap cards."""
    _heading(slide, unit, theme)
    items = _all_items(unit)
    if not items:
        items = [
            block.content
            for block in unit.blocks
            if block.content
        ]
    items = items[:5]
    if not items:
        _render_navigation_statement(slide, unit, theme)
        return
    _shape(slide, 1.0, 3.1, 11.1, 0.035, theme["chart_bg"], radius=False)
    count = len(items)
    width = 10.9 / max(count, 1)
    accents = (theme["accent"], theme["green"], theme["amber"])
    for index, item in enumerate(items):
        x = 1.0 + index * width
        accent = accents[index % len(accents)]
        _shape(slide, x, 2.83, 0.56, 0.56, accent, radius=True)
        _text(
            slide,
            str(index + 1),
            x,
            3.0,
            0.56,
            0.18,
            11,
            "FFFFFF",
            bold=True,
            align="center",
        )
        _text(
            slide,
            item,
            x - 0.02,
            3.68,
            max(1.65, width - 0.22),
            1.25,
            16,
            theme["ink"],
            bold=True,
        )
    takeaway = unit.key_message or unit.takeaway
    if takeaway:
        _shape(slide, 0.98, 5.5, 0.08, 0.72, theme["accent"], radius=False)
        _text(
            slide,
            takeaway,
            1.32,
            5.58,
            10.65,
            0.52,
            16,
            theme["muted"],
            bold=True,
        )


def _render_course_synthesis(
    slide: Any,
    unit: SlideSpec,
    theme: dict[str, str],
) -> None:
    """Render the whole-course route as one connected synthesis."""
    _heading(slide, unit, theme)
    items = _all_items(unit)
    if not items:
        items = [
            block.content
            for block in unit.blocks
            if block.content
        ]
    items = items[:6]
    if not items:
        _render_navigation_statement(slide, unit, theme)
        return
    core = unit.key_message or unit.takeaway or unit.title
    _text(slide, "课程主线", 0.92, 1.92, 1.4, 0.3, 12, theme["accent"], bold=True)
    _text(
        slide,
        core,
        0.92,
        2.46,
        3.08,
        2.2,
        23 if len(core) <= 36 else 18,
        theme["ink"],
        bold=True,
    )
    _shape(slide, 4.3, 1.86, 0.035, 4.5, theme["chart_bg"], radius=False)
    row_height = 3.95 / max(len(items), 1)
    for index, item in enumerate(items):
        y = 1.94 + index * row_height
        accent = (theme["accent"], theme["green"], theme["amber"])[index % 3]
        _text(
            slide,
            f"{index + 1:02d}",
            4.72,
            y + 0.08,
            0.52,
            0.24,
            11,
            accent,
            bold=True,
            align="center",
        )
        _text(
            slide,
            item,
            5.52,
            y,
            6.34,
            max(0.45, row_height - 0.08),
            16,
            theme["ink"],
            bold=True,
        )


def _render_appendix(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    _heading(slide, unit, theme)
    _shape(
        slide,
        0.78,
        1.82,
        11.78,
        4.93,
        theme["canvas"],
        radius=True,
        line=theme["chart_bg"],
    )
    _shape(slide, 0.78, 1.82, 0.09, 4.93, theme["accent"], radius=False)
    values: list[str] = []
    for block in unit.blocks:
        if block.title:
            values.append(block.title)
        if block.items:
            values.extend(f"• {item}" for item in block.items if item)
        elif block.content:
            values.append(block.content)
    body = "\n\n".join(values)
    if len(body) > 380:
        left, right = _balanced_text_columns(body)
        _text(
            slide,
            left,
            1.13,
            2.12,
            5.22,
            4.3,
            16,
            theme["ink"],
            font=theme["body_font"],
            east_asian_font=theme["body_east_asian_font"],
        )
        _shape(slide, 6.55, 2.13, 0.02, 4.25, theme["chart_bg"], radius=False)
        _text(
            slide,
            right,
            6.83,
            2.12,
            5.18,
            4.3,
            16,
            theme["ink"],
            font=theme["body_font"],
            east_asian_font=theme["body_east_asian_font"],
        )
    else:
        _text(
            slide,
            body,
            1.13,
            2.12,
            11.02,
            4.3,
            16,
            theme["ink"],
            font=theme["body_font"],
            east_asian_font=theme["body_east_asian_font"],
        )


def _balanced_text_columns(value: str) -> tuple[str, str]:
    paragraphs = [item.strip() for item in value.split("\n\n") if item.strip()]
    if len(paragraphs) < 2:
        midpoint = max(1, len(value) // 2)
        split_at = value.rfind("。", 0, midpoint)
        if split_at < 1:
            split_at = value.rfind("；", 0, midpoint)
        if split_at < 1:
            split_at = midpoint
        return value[: split_at + 1].strip(), value[split_at + 1 :].strip()
    target = len(value) / 2
    left: list[str] = []
    right: list[str] = []
    left_size = 0
    for paragraph in paragraphs:
        if left and left_size + len(paragraph) > target:
            right.append(paragraph)
        elif right:
            right.append(paragraph)
        else:
            left.append(paragraph)
            left_size += len(paragraph) + 2
    return "\n\n".join(left), "\n\n".join(right)


def _heading(slide: Any, unit: SlideSpec, theme: dict[str, str]) -> None:
    heading_mode = str(unit.quality.get("heading_mode") or "full")
    if heading_mode == "hidden":
        section_label = str(
            unit.quality.get("section_label")
            or unit.eyebrow
            or unit.slide_purpose
        )
        _text(
            slide,
            section_label,
            0.78,
            0.55,
            8.8,
            0.38,
            13,
            theme["accent"],
            bold=True,
        )
        _shape(slide, 0.78, 1.12, 0.72, 0.04, theme["accent"], radius=False)
        _shape(slide, 1.58, 1.12, 0.08, 0.04, theme["green"], radius=False)
        return
    heading = _display_heading(unit)
    heading_size = 35
    _text(slide, unit.eyebrow or unit.slide_purpose, 0.78, 0.42, 2.7, 0.3, 11, theme["accent"], bold=True)
    _text(
        slide, heading, 0.78, 0.68, 11.72, 1.18, heading_size, theme["title"], bold=True,
        font=theme["title_font"], east_asian_font=theme["title_east_asian_font"],
    )
    _shape(slide, 0.78, 1.86, 0.72, 0.04, theme["accent"], radius=False)
    _shape(slide, 1.58, 1.86, 0.08, 0.04, theme["green"], radius=False)


def _footer(slide: Any, unit: SlideSpec, page: int, total: int, theme: dict[str, str]) -> None:
    section = unit.section_id or "COURSE"
    _text(slide, section, 0.78, 7.1, 2.4, 0.2, 8, theme["muted"], font="Aptos Mono")
    _text(slide, f"{page:02d} / {total:02d}", 11.48, 7.1, 1.02, 0.2, 8, theme["muted"], align="right", font="Aptos Mono")


def _fill_background(slide: Any, color: str) -> None:
    from pptx.dml.color import RGBColor

    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor.from_string(color)
    # Keep the legacy editable background shape as the first object while
    # staying a fraction inside the canvas to avoid false overflow at full bleed.
    _shape(slide, 0.01, 0.01, 13.30, 7.47, color, radius=False)


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
    paragraph.text = _display_text(str(value or ""))
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
    for index, value in enumerate([_display_text(str(item)) for item in items if str(item).strip()]):
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
            cell.text = (
                _display_text(values[row_index][column_index])
                if row_index < len(values) and column_index < len(values[row_index])
                else ""
            )
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor.from_string(
                theme["accent_soft"]
                if row_index == 0
                else (theme["surface"] if row_index % 2 else theme["canvas"])
            )
            cell.margin_left = cell.margin_right = Inches(0.1)
            cell.margin_top = cell.margin_bottom = Inches(0.07)
            paragraph = cell.text_frame.paragraphs[0]
            _configure_font(paragraph.font, BODY_FONT)
            paragraph.font.size = Pt(16)
            paragraph.font.bold = row_index == 0
            paragraph.font.color.rgb = RGBColor.from_string(theme["accent"] if row_index == 0 else theme["ink"])
            paragraph.alignment = PP_ALIGN.LEFT


def _display_heading(unit: SlideSpec) -> str:
    title = _format_formula_text(str(unit.title or "").strip())
    takeaway = str(unit.takeaway or "").strip()
    visual_kind = str(unit.visuals[0].get("kind") or "") if unit.visuals else ""
    if title and not _is_generic_heading(title):
        return _heading_excerpt(title)
    if not takeaway:
        return _heading_excerpt(title)
    if (
        visual_kind == "formula"
        or takeaway.startswith(("$", "\\[", "\\("))
        or re.search(r"\\[A-Za-z]+", takeaway)
        or re.fullmatch(r"[\d\s.、:：()（）-]+", takeaway)
    ):
        return _heading_excerpt(title, limit=46)
    return _heading_excerpt(_format_formula_text(takeaway))


def _is_generic_heading(value: str) -> bool:
    normalized = re.sub(r"[\s:：|/\\_-]+", "", str(value or "")).lower()
    return normalized in {
        "课程正文",
        "课程内容",
        "正文",
        "内容",
        "未命名",
        "body",
        "content",
    }


def _heading_excerpt(value: str, limit: int | None = None) -> str:
    """Choose a complete audience-facing title phrase without an ellipsis."""
    clean = " ".join(str(value or "").split()).strip("，,；;：:。… ")
    if limit is None:
        limit = 18 if re.search(r"[\u3400-\u9fff]", clean) else 42
    if len(clean) <= limit:
        return clean
    excerpt = clean[:limit]
    opening = max(excerpt.rfind("（"), excerpt.rfind("("))
    closing = max(excerpt.rfind("）"), excerpt.rfind(")"))
    if opening > closing and opening >= max(8, limit // 3):
        excerpt = excerpt[:opening]
    else:
        punctuation = max(
            excerpt.rfind("。"),
            excerpt.rfind("；"),
            excerpt.rfind("，"),
            excerpt.rfind("："),
            excerpt.rfind("）"),
            excerpt.rfind(")"),
        )
        if punctuation >= max(10, limit // 2):
            excerpt = excerpt[: punctuation + (1 if excerpt[punctuation] in "）)" else 0)]
        else:
            space = excerpt.rfind(" ")
            if space >= max(10, limit // 2):
                excerpt = excerpt[:space]
    return excerpt.rstrip("，,；;：:。 ")


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
