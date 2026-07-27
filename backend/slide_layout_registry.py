"""Deterministic semantic layout registry for course-logic slide decks."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


SlideSceneKind = Literal[
    "chapter_entry",
    "prerequisite_activation",
    "concept",
    "reasoning",
    "method",
    "worked_example",
    "practice_feedback",
    "misconception",
    "application",
    "chapter_recap",
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LayoutSlotV2(_StrictModel):
    slot_id: str
    accepts: list[str]
    required: bool = False


class LayoutDefinitionV2(_StrictModel):
    layout_id: str
    renderer_layout: str
    template_use: str
    layout_family: str
    scene_kinds: list[SlideSceneKind]
    slots: list[LayoutSlotV2]
    density_budget: int = Field(ge=80)
    item_budget: int = Field(ge=0)
    typography_budget: dict[str, int]
    asset_slots: int = Field(ge=0)
    evidence_kinds: list[str] = Field(default_factory=list)
    theme_compatibility: list[str] = Field(default_factory=list)
    disabled_when: list[str] = Field(default_factory=list)
    max_consecutive: int = Field(default=2, ge=1)


class LayoutSelectionV2(_StrictModel):
    layout_id: str
    renderer_layout: str
    layout_family: str
    score: float
    scene_match_score: float
    slot_match_score: float
    density_score: float
    rhythm_score: float
    theme_score: float
    capacity_passed: bool
    reason: str


_ALL_THEMES = [
    "qizhi-classroom",
    "academic-editorial",
    "grid-notebook",
    "modern-geometric",
    "dark-tech",
]


def _layout(
    layout_id: str,
    renderer_layout: str,
    template_use: str,
    family: str,
    scenes: list[SlideSceneKind],
    *,
    slots: list[tuple[str, list[str], bool]],
    density: int,
    items: int = 6,
    assets: int = 0,
    evidence: list[str] | None = None,
) -> LayoutDefinitionV2:
    return LayoutDefinitionV2(
        layout_id=layout_id,
        renderer_layout=renderer_layout,
        template_use=template_use,
        layout_family=family,
        scene_kinds=scenes,
        slots=[
            LayoutSlotV2(slot_id=slot_id, accepts=accepts, required=required)
            for slot_id, accepts, required in slots
        ],
        density_budget=density,
        item_budget=items,
        typography_budget={"title_min_pt": 35, "body_min_pt": 16},
        asset_slots=assets,
        evidence_kinds=evidence or [],
        theme_compatibility=_ALL_THEMES,
    )


SLIDE_LAYOUT_REGISTRY_V2: tuple[LayoutDefinitionV2, ...] = (
    _layout(
        "chapter-question",
        "section-divider",
        "章节驱动问题",
        "hero",
        ["chapter_entry"],
        slots=[("claim", ["text"], True), ("route", ["list"], False)],
        density=360,
    ),
    _layout(
        "prerequisite-recall",
        "objective-cards",
        "先修唤醒",
        "cards",
        ["prerequisite_activation"],
        slots=[("prompt", ["text"], True), ("recall", ["list"], False)],
        density=520,
        items=5,
    ),
    _layout(
        "definition-focus",
        "hero-statement",
        "定义与正式陈述",
        "statement",
        ["concept"],
        slots=[("definition", ["text", "formula"], True)],
        density=430,
        evidence=["formula"],
    ),
    _layout(
        "definition-boundary",
        "two-column",
        "定义与条件边界",
        "split",
        ["concept", "misconception"],
        slots=[
            ("definition", ["text", "formula"], True),
            ("boundary", ["text", "list"], True),
        ],
        density=720,
        items=8,
        evidence=["formula", "table"],
    ),
    _layout(
        "positive-negative",
        "comparison",
        "正反例对照",
        "comparison",
        ["concept", "misconception"],
        slots=[("positive", ["text"], True), ("negative", ["text"], True)],
        density=760,
        items=8,
    ),
    _layout(
        "reasoning-route",
        "process",
        "证明或推导路线",
        "process",
        ["reasoning"],
        slots=[("claim", ["text", "formula"], True), ("steps", ["list"], True)],
        density=650,
        items=7,
        evidence=["formula", "diagram"],
        assets=1,
    ),
    _layout(
        "derivation-steps",
        "formula",
        "分步推导",
        "derivation",
        ["reasoning", "worked_example"],
        slots=[("formula", ["formula"], True), ("explanation", ["text"], False)],
        density=820,
        items=8,
        evidence=["formula"],
    ),
    _layout(
        "method-flow",
        "process",
        "方法流程",
        "process",
        ["method"],
        slots=[("task", ["text"], True), ("steps", ["list"], True)],
        density=620,
        items=7,
        evidence=["diagram", "code"],
        assets=1,
    ),
    _layout(
        "decision-branch",
        "cause-effect",
        "条件分支",
        "diagram",
        ["method", "misconception"],
        slots=[("conditions", ["list"], True), ("result", ["text"], True)],
        density=560,
        items=6,
        evidence=["diagram"],
        assets=1,
    ),
    _layout(
        "example-prompt",
        "question",
        "例题题目",
        "question",
        ["worked_example"],
        slots=[("prompt", ["text", "formula", "code"], True)],
        density=620,
        evidence=["formula", "code", "table"],
    ),
    _layout(
        "example-strategy",
        "two-column",
        "已知目标与策略",
        "split",
        ["worked_example"],
        slots=[("given", ["text", "formula"], True), ("strategy", ["text", "list"], True)],
        density=700,
        items=7,
        evidence=["formula", "diagram"],
        assets=1,
    ),
    _layout(
        "example-reveal",
        "answer",
        "解答揭示",
        "answer",
        ["worked_example", "practice_feedback"],
        slots=[("solution", ["text", "formula", "code"], True)],
        density=850,
        items=8,
        evidence=["formula", "code"],
    ),
    _layout(
        "result-validation",
        "data-highlight",
        "结果验证",
        "validation",
        ["worked_example", "method"],
        slots=[("result", ["text", "formula"], True), ("check", ["text", "list"], False)],
        density=560,
        items=5,
        evidence=["formula", "chart"],
        assets=1,
    ),
    _layout(
        "practice-prompt",
        "practice",
        "练习题目与思考",
        "question",
        ["practice_feedback"],
        slots=[("prompt", ["text", "formula", "code"], True)],
        density=650,
        evidence=["formula", "code", "table"],
    ),
    _layout(
        "feedback-mastery",
        "answer",
        "反馈与掌握判断",
        "feedback",
        ["practice_feedback"],
        slots=[("answer", ["text", "formula", "code"], True), ("criterion", ["text", "list"], False)],
        density=720,
        items=7,
        evidence=["formula", "code"],
    ),
    _layout(
        "misconception-repair",
        "misconception",
        "误区定位与修复",
        "comparison",
        ["misconception"],
        slots=[("wrong", ["text", "formula"], True), ("repair", ["text", "formula"], True)],
        density=700,
        items=6,
        evidence=["formula"],
    ),
    _layout(
        "application-mapping",
        "case-study",
        "情境到学科结构的映射",
        "case",
        ["application"],
        slots=[("situation", ["text", "image"], True), ("mapping", ["text", "diagram"], True)],
        density=700,
        items=6,
        evidence=["image", "diagram", "chart", "table"],
        assets=1,
    ),
    _layout(
        "chapter-knowledge-map",
        "knowledge-map",
        "章节知识关系",
        "diagram",
        ["chapter_recap"],
        slots=[("relations", ["diagram", "list"], True), ("closure", ["text"], True)],
        density=620,
        items=7,
        evidence=["diagram"],
        assets=1,
    ),
    _layout(
        "chapter-closure",
        "summary",
        "目标闭环与下一章承接",
        "summary",
        ["chapter_recap"],
        slots=[("closure", ["text", "list"], True), ("next", ["text"], False)],
        density=680,
        items=8,
    ),
    _layout(
        "formula-focus",
        "formula",
        "公式证据",
        "formula",
        ["concept", "reasoning", "method", "worked_example", "practice_feedback"],
        slots=[("formula", ["formula"], True), ("explanation", ["text"], False)],
        density=760,
        items=7,
        evidence=["formula"],
    ),
    _layout(
        "code-focus",
        "code",
        "代码证据",
        "code",
        ["method", "worked_example", "practice_feedback", "application"],
        slots=[("code", ["code"], True), ("explanation", ["text"], False)],
        density=1100,
        items=8,
        evidence=["code"],
    ),
    _layout(
        "table-evidence",
        "data-highlight",
        "表格证据",
        "table",
        ["concept", "method", "worked_example", "application"],
        slots=[("table", ["table"], True), ("interpretation", ["text"], False)],
        density=820,
        items=10,
        evidence=["table", "chart"],
        assets=1,
    ),
    _layout(
        "figure-text",
        "two-column",
        "图文解释",
        "split",
        ["concept", "reasoning", "method", "application"],
        slots=[("visual", ["image", "diagram", "chart"], True), ("text", ["text"], True)],
        density=620,
        items=6,
        evidence=["image", "diagram", "chart"],
        assets=1,
    ),
)


def registry_summary_v2() -> list[dict[str, Any]]:
    return [
        {
            "layout_id": item.layout_id,
            "renderer_layout": item.renderer_layout,
            "template_use": item.template_use,
            "layout_family": item.layout_family,
            "scene_kinds": item.scene_kinds,
            "slots": [slot.model_dump(mode="json") for slot in item.slots],
            "density_budget": item.density_budget,
            "item_budget": item.item_budget,
            "asset_slots": item.asset_slots,
            "evidence_kinds": item.evidence_kinds,
        }
        for item in SLIDE_LAYOUT_REGISTRY_V2
    ]


def select_layout_v2(
    *,
    scene_kind: SlideSceneKind,
    evidence_kinds: list[str],
    character_count: int,
    item_count: int,
    theme: str,
    recent_layout_families: list[str] | None = None,
) -> LayoutSelectionV2:
    """Hard-filter incompatible layouts, then apply the documented stable score."""
    evidence = {str(item) for item in evidence_kinds if str(item)}
    recent = list(recent_layout_families or [])
    candidates: list[tuple[float, LayoutDefinitionV2, dict[str, float]]] = []
    for layout in SLIDE_LAYOUT_REGISTRY_V2:
        if scene_kind not in layout.scene_kinds:
            continue
        if theme not in layout.theme_compatibility:
            continue
        if character_count > layout.density_budget or item_count > layout.item_budget:
            continue
        required_evidence = {
            accepted
            for slot in layout.slots
            if slot.required and not ({"text", "list"} & set(slot.accepts))
            for accepted in slot.accepts
        }
        if required_evidence and not (required_evidence & evidence):
            continue
        scene_score = 1.0
        slot_score = 1.0 if not evidence else (
            len(evidence & set(layout.evidence_kinds)) / len(evidence)
            if layout.evidence_kinds
            else 0.35
        )
        density_score = max(0.0, 1.0 - character_count / max(layout.density_budget, 1))
        consecutive = 0
        for family in reversed(recent):
            if family != layout.layout_family:
                break
            consecutive += 1
        if consecutive >= layout.max_consecutive:
            continue
        rhythm_score = 1.0 if not recent or recent[-1] != layout.layout_family else 0.45
        theme_score = 1.0
        score = (
            scene_score * 0.35
            + slot_score * 0.25
            + density_score * 0.20
            + rhythm_score * 0.10
            + theme_score * 0.10
        )
        candidates.append((
            score,
            layout,
            {
                "scene": scene_score,
                "slot": slot_score,
                "density": density_score,
                "rhythm": rhythm_score,
                "theme": theme_score,
            },
        ))
    if not candidates:
        raise ValueError(
            f"No capacity-safe layout for scene={scene_kind}, "
            f"characters={character_count}, items={item_count}, evidence={sorted(evidence)}"
        )
    score, selected, parts = sorted(
        candidates,
        key=lambda item: (-item[0], item[1].layout_id),
    )[0]
    return LayoutSelectionV2(
        layout_id=selected.layout_id,
        renderer_layout=selected.renderer_layout,
        layout_family=selected.layout_family,
        score=round(score, 6),
        scene_match_score=parts["scene"],
        slot_match_score=round(parts["slot"], 6),
        density_score=round(parts["density"], 6),
        rhythm_score=parts["rhythm"],
        theme_score=parts["theme"],
        capacity_passed=True,
        reason=(
            f"scene={scene_kind}; evidence={','.join(sorted(evidence)) or 'text'}; "
            f"capacity={character_count}/{selected.density_budget}; family={selected.layout_family}"
        ),
    )
