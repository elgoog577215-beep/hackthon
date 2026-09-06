"""The small, explicit vocabulary shared by PPT content, layouts and themes.

A primitive owns appearance and capacity. A composition owns placement and the
allowed semantic shape. The model only selects a composition; it never returns
coordinates or styling instructions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PrimitiveSpec:
    kind: str
    role: str
    capacity: str


@dataclass(frozen=True)
class CompositionSpec:
    slug: str
    label: str
    expression_kind: str
    max_items: int
    max_chars: int
    family: str
    primitives: tuple[str, ...]
    status: str = "implemented"


PRIMITIVES: dict[str, PrimitiveSpec] = {
    "page-shell": PrimitiveSpec("page-shell", "页面背景、标题、页码和页眉", "one title, one page marker"),
    "card": PrimitiveSpec("card", "成组信息和独立状态", "one title plus short body"),
    "step-node": PrimitiveSpec("step-node", "顺序中的一个节点", "one short label"),
    "arrow": PrimitiveSpec("arrow", "有方向的顺序关系", "one source and one target"),
    "connector": PrimitiveSpec("connector", "非顺序关系", "one source and one target"),
    "center-node": PrimitiveSpec("center-node", "中心概念", "one short claim"),
    "bar": PrimitiveSpec("bar", "单一单位下的数值", "one non-negative source-exact value"),
    "icon": PrimitiveSpec("icon", "语义标记", "one registered icon"),
    "title-band": PrimitiveSpec("title-band", "卡片或分区的标题层", "one short title"),
    "conclusion-band": PrimitiveSpec("conclusion-band", "页面结论", "one short conclusion"),
    "page-number": PrimitiveSpec("page-number", "阅读位置", "one ordinal"),
    "rule": PrimitiveSpec("rule", "分组和视觉节奏", "one line"),
    "tag": PrimitiveSpec("tag", "分类或阶段标记", "one short label"),
}


COMPOSITIONS: dict[str, CompositionSpec] = {
    "cover": CompositionSpec("cover", "封面", "cover", 1, 60, "single", ("page-shell", "icon", "rule")),
    "agenda": CompositionSpec("agenda", "提纲", "agenda", 5, 36, "list", ("page-shell", "tag", "card")),
    "section": CompositionSpec("section", "章节引入", "cover", 1, 60, "single", ("page-shell", "icon", "rule")),
    "bullets": CompositionSpec("bullets", "要点", "evidence", 5, 52, "list", ("page-shell", "title-band", "card", "page-number")),
    "summary": CompositionSpec("summary", "小结", "recap", 4, 52, "list", ("page-shell", "title-band", "conclusion-band", "page-number")),
    "question": CompositionSpec("question", "问题与答案", "exercise", 2, 140, "question", ("page-shell", "card", "conclusion-band")),
    "comparison": CompositionSpec("comparison", "双对象对比", "comparison", 3, 48, "comparison", ("page-shell", "card", "rule", "conclusion-band")),
    "flow": CompositionSpec("flow", "三至四步流程", "process", 4, 38, "flow", ("page-shell", "step-node", "arrow", "page-number")),
    "flow6": CompositionSpec("flow6", "六步流程", "process", 6, 28, "flow", ("page-shell", "step-node", "arrow", "tag", "page-number")),
    "formula": CompositionSpec("formula", "公式与解释", "derivation", 2, 160, "single", ("page-shell", "card", "conclusion-band")),
    "figure": CompositionSpec("figure", "图片与说明", "evidence", 3, 52, "figure", ("page-shell", "card", "rule")),
    "chart": CompositionSpec("chart", "数据比较", "chart", 6, 24, "chart", ("page-shell", "bar", "rule", "page-number")),
    "chart_explanation": CompositionSpec("chart_explanation", "图表与解释", "chart", 6, 24, "chart", ("page-shell", "bar", "conclusion-band", "rule")),
    "code": CompositionSpec("code", "代码与解释", "evidence", 2, 140, "single", ("page-shell", "card", "conclusion-band")),
    "four_stage": CompositionSpec("four_stage", "四阶段卡片", "evidence", 4, 44, "four_stage", ("page-shell", "card", "arrow", "tag")),
    "triad": CompositionSpec("triad", "三场景卡片", "evidence", 3, 44, "triad", ("page-shell", "card", "title-band", "tag")),
    "mechanism_stack": CompositionSpec("mechanism_stack", "三机制组合", "evidence", 3, 44, "triad", ("page-shell", "card", "title-band", "conclusion-band")),
    "radial": CompositionSpec("radial", "中心辐射关系", "concept", 4, 36, "radial", ("page-shell", "center-node", "connector", "card")),
}

# The old names are kept as compatibility projections for legacy v1 manifests.
LEGACY_LAYOUTS = ("cover", "agenda", "section", "bullets", "summary", "question", "comparison", "flow", "formula", "figure")


def layout_tuple(slug: str) -> tuple[str, str, int, int]:
    spec = COMPOSITIONS[slug]
    return spec.expression_kind, spec.label, spec.max_items, spec.max_chars


def composition_capability(slug: str) -> dict[str, Any]:
    spec = COMPOSITIONS[slug]
    return {"composition": spec.family, "primitives": list(spec.primitives), "status": spec.status}


def composition_manifest() -> dict[str, Any]:
    return {
        "primitives": {key: asdict(value) for key, value in PRIMITIVES.items()},
        "compositions": {key: {**asdict(value), "primitives": list(value.primitives)} for key, value in COMPOSITIONS.items()},
    }
