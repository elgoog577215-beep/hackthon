"""Versioned Lingzhi presentation style and layout registry."""

from __future__ import annotations

from dataclasses import dataclass

from presentation_models import LayoutId, TemplateId


TEMPLATE_VERSION = "1.0.0"
LAYOUT_REGISTRY_VERSION = "1.0.0"


@dataclass(frozen=True)
class TemplateSpec:
    template_id: TemplateId
    label: str
    surface: str
    ink: str
    muted: str
    accent: str
    soft_accent: str
    font_family: str
    code_font_family: str


@dataclass(frozen=True)
class LayoutSpec:
    layout_id: LayoutId
    label: str
    required_slots: tuple[str, ...]
    allowed_block_types: tuple[str, ...]
    max_blocks: int
    max_characters: int


TEMPLATES: dict[str, TemplateSpec] = {
    "lingzhi-classroom": TemplateSpec(
        "lingzhi-classroom", "灵知课堂", "#ffffff", "#172033", "#667085",
        "#6366f1", "#eef2ff", "Microsoft YaHei, PingFang SC, sans-serif",
        "Cascadia Code, Consolas, monospace",
    ),
    "lingzhi-engineering": TemplateSpec(
        "lingzhi-engineering", "理工推演", "#ffffff", "#182033", "#596579",
        "#5b5ce2", "#f3f4ff", "Microsoft YaHei, PingFang SC, sans-serif",
        "Cascadia Code, Consolas, monospace",
    ),
    "lingzhi-academic": TemplateSpec(
        "lingzhi-academic", "学术答辩", "#fffefa", "#202331", "#6b6f7d",
        "#5156c9", "#f1f1fb", "Microsoft YaHei, Noto Serif CJK SC, sans-serif",
        "Cascadia Code, Consolas, monospace",
    ),
}


LAYOUTS: dict[str, LayoutSpec] = {
    "L01": LayoutSpec("L01", "封面", ("title",), ("text", "callout"), 2, 500),
    "L02": LayoutSpec("L02", "课程路线", ("title", "blocks"), ("bullets", "text"), 3, 900),
    "L03": LayoutSpec("L03", "章节转场", ("title",), ("text", "callout"), 2, 550),
    "L04": LayoutSpec("L04", "核心概念", ("title", "blocks"), ("text", "bullets", "callout"), 4, 1300),
    "L05": LayoutSpec("L05", "双栏对比", ("title", "blocks"), ("comparison", "bullets", "text"), 4, 1400),
    "L06": LayoutSpec("L06", "流程算法", ("title", "blocks"), ("bullets", "text", "code"), 5, 1500),
    "L07": LayoutSpec("L07", "代码注解", ("title", "blocks"), ("code", "bullets", "callout"), 4, 1800),
    "L08": LayoutSpec("L08", "常见误区", ("title", "blocks"), ("comparison", "callout", "bullets"), 4, 1300),
    "L09": LayoutSpec("L09", "课堂练习", ("title", "blocks"), ("exercise", "text", "callout"), 4, 1200),
    "L10": LayoutSpec("L10", "小结学习路径", ("title", "blocks"), ("bullets", "text", "callout"), 4, 1100),
}


def get_template(template_id: str) -> TemplateSpec:
    try:
        return TEMPLATES[template_id]
    except KeyError as exc:
        raise ValueError(f"unknown_template:{template_id}") from exc


def get_layout(layout_id: str) -> LayoutSpec:
    try:
        return LAYOUTS[layout_id]
    except KeyError as exc:
        raise ValueError(f"unknown_layout:{layout_id}") from exc


def validate_slide_capacity(layout_id: str, blocks: list[dict], text: str) -> list[str]:
    spec = get_layout(layout_id)
    errors: list[str] = []
    if len(blocks) > spec.max_blocks:
        errors.append(f"layout {layout_id} allows at most {spec.max_blocks} blocks")
    if len(text) > spec.max_characters:
        errors.append(f"layout {layout_id} allows at most {spec.max_characters} characters")
    invalid = [str(block.get("type")) for block in blocks if block.get("type") not in spec.allowed_block_types]
    if invalid:
        errors.append(f"layout {layout_id} rejects block types: {', '.join(sorted(set(invalid)))}")
    return errors
