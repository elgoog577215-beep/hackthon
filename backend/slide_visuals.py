"""Grounded teaching narrative and visual direction for source-first slide decks."""

from __future__ import annotations

import asyncio
import inspect
import re
from collections import Counter, defaultdict
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from course_document import CourseDocument, stable_hash

SLIDE_VISUAL_PLAN_SCHEMA = "slide_visual_plan_v1"
SLIDE_VISUAL_POLICY_VERSION = "visual_director_v1"

VisualKind = Literal[
    "source_image",
    "generated_illustration",
    "relational_diagram",
    "coordinate_plot",
    "chart",
    "table",
    "formula",
    "code",
    "none",
]
VisualPurpose = Literal[
    "structure",
    "process",
    "comparison",
    "evidence",
    "application",
    "context",
    "exercise",
]
SlideComposition = Literal[
    "statement",
    "figure-first",
    "split-visual",
    "diagram-full",
    "comparison",
    "process",
    "exercise",
    "appendix",
]

_VISUAL_KINDS = {
    "source_image",
    "generated_illustration",
    "relational_diagram",
    "coordinate_plot",
    "chart",
    "table",
    "formula",
    "code",
    "none",
}
_NAVIGATION_LAYOUTS = {"cover", "roadmap", "section-divider", "summary"}
_NUMBER_RE = re.compile(r"\d+")
_SPATIAL_MATH_RE = re.compile(
    r"(?:坐标|向量|平面|空间|基底|线性变换|线性映射|旋转|投影|特征向量|"
    r"coordinate|vector|plane|space|basis|rotation|projection)",
    re.IGNORECASE,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VisualNodeV1(_StrictModel):
    node_id: str
    label: str = Field(min_length=1, max_length=80)
    source_fragment_ids: list[str] = Field(default_factory=list, min_length=1)
    emphasis: Literal["primary", "secondary", "muted"] = "secondary"


class VisualEdgeV1(_StrictModel):
    source: str
    target: str
    label: str = Field(default="", max_length=40)
    relation: Literal[
        "sequence",
        "supports",
        "contrasts",
        "causes",
        "contains",
        "maps_to",
    ] = "sequence"


class VisualAnchorV1(_StrictModel):
    visual_id: str
    kind: VisualKind
    purpose: VisualPurpose
    source_fragment_ids: list[str] = Field(default_factory=list)
    alt_text: str = Field(default="", max_length=240)
    asset_id: str = ""
    nodes: list[VisualNodeV1] = Field(default_factory=list, max_length=8)
    edges: list[VisualEdgeV1] = Field(default_factory=list, max_length=12)
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_shape(self) -> "VisualAnchorV1":
        if self.kind not in _VISUAL_KINDS:
            raise ValueError("unknown visual type")
        if self.kind == "none":
            if self.nodes or self.edges or self.asset_id:
                raise ValueError("A none visual cannot contain rendered payload")
            return self
        if not self.source_fragment_ids:
            raise ValueError("A meaningful visual must bind source fragments")
        if not self.alt_text:
            raise ValueError("A meaningful visual must have alt text")
        if self.kind == "relational_diagram" and not self.nodes:
            raise ValueError("A relational diagram needs source-bound nodes")
        if self.kind in {"source_image", "generated_illustration"} and not (
            self.asset_id or self.parameters.get("asset_ref") or self.parameters.get("prompt")
        ):
            raise ValueError("An image visual needs an asset reference or prompt")
        return self


class SlideVisualPlanPageV1(_StrictModel):
    page_id: str
    teaching_job: str = Field(min_length=1, max_length=180)
    takeaway: str = Field(min_length=1, max_length=160)
    takeaway_source_fragment_ids: list[str] = Field(default_factory=list)
    transition_from: str = Field(default="", max_length=180)
    composition: SlideComposition
    visual_anchor: VisualAnchorV1
    role_layout_variant: Literal["primary", "alternate", "dense"] = "primary"
    chapter_id: str = ""
    appendix: bool = False


class SlideVisualPlanV1(_StrictModel):
    schema_version: Literal["slide_visual_plan_v1"] = SLIDE_VISUAL_PLAN_SCHEMA
    policy_version: str = SLIDE_VISUAL_POLICY_VERSION
    source_document_revision: str
    mode: Literal["full", "teaching", "concise"]
    theme: str
    variant_key: str
    deck_brief: dict[str, Any] = Field(default_factory=dict)
    pages: list[SlideVisualPlanPageV1]

    @model_validator(mode="after")
    def validate_pages(self) -> "SlideVisualPlanV1":
        page_ids = [page.page_id for page in self.pages]
        if len(page_ids) != len(set(page_ids)):
            raise ValueError("Visual plan page IDs must be unique")
        return self


def deterministic_visual_plan(
    document: CourseDocument,
    allocation_plan: Any,
    fragments: list[Any],
) -> SlideVisualPlanV1:
    """Build a source-grounded visual plan without requiring a model or image API."""
    catalog = {item.fragment_id: item for item in fragments}
    pages: list[SlideVisualPlanPageV1] = []
    prior_takeaway = ""
    content_index = 0
    for page in allocation_plan.pages:
        page_fragments = [
            catalog[fragment_id]
            for fragment_id in page.fragment_ids
            if fragment_id in catalog
        ]
        is_navigation = page.layout in _NAVIGATION_LAYOUTS and not page_fragments
        takeaway, takeaway_ids = _takeaway(page, page_fragments, document.title)
        teaching_job = _teaching_job(page, takeaway)
        transition = (
            ""
            if not pages
            else _transition_text(page, prior_takeaway, takeaway)
        )
        if page.appendix:
            anchor = _none_anchor(page.page_id, "evidence")
            composition: SlideComposition = "appendix"
        elif is_navigation:
            anchor = _none_anchor(page.page_id, "structure")
            composition = "statement"
        else:
            anchor = _visual_anchor(page, page_fragments, content_index)
            composition = _composition_for(page, anchor, content_index)
            content_index += 1
        pages.append(SlideVisualPlanPageV1(
            page_id=page.page_id,
            teaching_job=teaching_job,
            takeaway=takeaway,
            takeaway_source_fragment_ids=takeaway_ids,
            transition_from=transition,
            composition=composition,
            visual_anchor=anchor,
            role_layout_variant=("primary", "alternate", "dense")[content_index % 3],
            chapter_id=str(getattr(page, "chapter_id", "") or ""),
            appendix=bool(page.appendix),
        ))
        prior_takeaway = takeaway
    _rebalance_compositions(pages)
    plan = SlideVisualPlanV1(
        source_document_revision=document.document_revision,
        mode=allocation_plan.mode,
        theme=allocation_plan.theme,
        variant_key=allocation_plan.variant_key,
        deck_brief={
            "communication_job": (
                f"帮助学习者沿课程原文建立“{document.title}”的概念、方法与应用链条。"
            ),
            "audience": "课程学习者",
            "narrative_arc": [
                "导入",
                "概念",
                "原理",
                "方法",
                "案例",
                "检查",
                "回顾",
            ],
            "content_policy": "source_fragments_only",
        },
        pages=pages,
    )
    validate_visual_plan(plan, allocation_plan, fragments)
    return plan


def _rebalance_compositions(pages: list[SlideVisualPlanPageV1]) -> None:
    """Keep visual rhythm deterministic even across repeated exercises/formulas."""
    alternatives: list[SlideComposition] = [
        "figure-first",
        "split-visual",
        "diagram-full",
        "comparison",
        "process",
        "exercise",
        "statement",
    ]
    eligible = [
        page
        for page in pages
        if not page.appendix and page.visual_anchor.kind != "none"
    ]
    previous: SlideComposition | str = ""
    run = 0
    for index, page in enumerate(eligible):
        if page.composition == previous:
            run += 1
        else:
            previous = page.composition
            run = 1
        if run <= 2:
            continue
        replacement = next(
            candidate
            for candidate in alternatives
            if candidate != page.composition
            and (index == 0 or candidate != eligible[index - 1].composition)
        )
        page.composition = replacement
        previous = replacement
        run = 1

    chapters: dict[str, list[SlideVisualPlanPageV1]] = defaultdict(list)
    for page in eligible:
        if page.chapter_id:
            chapters[page.chapter_id].append(page)
    for chapter_pages in chapters.values():
        if len(chapter_pages) < 4:
            continue
        maximum = max(1, int(len(chapter_pages) * 0.35))
        while True:
            counts = Counter(page.composition for page in chapter_pages)
            overused = next(
                (
                    composition
                    for composition, count in counts.most_common()
                    if count > maximum
                ),
                None,
            )
            if overused is None:
                break
            changed = False
            for index in range(len(chapter_pages) - 1, -1, -1):
                page = chapter_pages[index]
                if page.composition != overused:
                    continue
                replacement = next(
                    (
                        candidate
                        for candidate in alternatives
                        if (
                            candidate != overused
                            and counts[candidate] < maximum
                            and (
                                index == 0
                                or chapter_pages[index - 1].composition != candidate
                            )
                            and (
                                index == len(chapter_pages) - 1
                                or chapter_pages[index + 1].composition != candidate
                            )
                        )
                    ),
                    None,
                )
                if replacement is None:
                    continue
                page.composition = replacement
                changed = True
                break
            if not changed:
                break


async def plan_slide_visuals(
    document: CourseDocument,
    allocation_plan: Any,
    fragments: list[Any],
    *,
    ai_planner: Callable[
        [dict[str, Any]],
        Awaitable[dict[str, Any]] | dict[str, Any],
    ] | None = None,
    timeout_seconds: float = 12.0,
) -> SlideVisualPlanV1:
    """Accept a strict source-bound AI plan or return the deterministic director."""
    fallback = deterministic_visual_plan(document, allocation_plan, fragments)
    if ai_planner is None:
        fallback.deck_brief["planner"] = "deterministic_fallback"
        fallback.deck_brief["fallback_reason"] = "no_ai_visual_planner"
        return fallback
    request = {
        "schema_version": "slide_visual_plan_request_v1",
        "source_document_revision": document.document_revision,
        "mode": allocation_plan.mode,
        "theme": allocation_plan.theme,
        "variant_key": allocation_plan.variant_key,
        "rules": {
            "body_text_forbidden": True,
            "unknown_fragment_ids_forbidden": True,
            "takeaway_must_be_source_grounded": True,
            "visual_labels_must_be_source_excerpts": True,
            "generated_images_may_not_contain_text_or_logos": True,
        },
        "allowed_visual_kinds": sorted(_VISUAL_KINDS),
        "pages": [
            {
                "page_id": page.page_id,
                "layout": page.layout,
                "narrative_role": page.narrative_role,
                "appendix": page.appendix,
                "chapter_id": page.chapter_id,
                "fragments": [
                    {
                        "fragment_id": fragment.fragment_id,
                        "kind": fragment.kind,
                        "text": fragment.text,
                    }
                    for fragment in fragments
                    if fragment.fragment_id in page.fragment_ids
                ],
            }
            for page in allocation_plan.pages
        ],
    }
    try:
        if inspect.iscoroutinefunction(ai_planner):
            raw = await asyncio.wait_for(ai_planner(request), timeout=timeout_seconds)
        else:
            result = await asyncio.wait_for(
                asyncio.to_thread(ai_planner, request),
                timeout=timeout_seconds,
            )
            raw = await result if inspect.isawaitable(result) else result
        candidate = SlideVisualPlanV1.model_validate(raw)
        validate_visual_plan(candidate, allocation_plan, fragments)
        candidate.deck_brief["planner"] = "ai"
        return candidate
    except Exception:
        fallback.deck_brief["planner"] = "deterministic_fallback"
        fallback.deck_brief["fallback_reason"] = "invalid_or_failed_ai_visual_plan"
        return fallback


def validate_visual_plan(
    visual_plan: SlideVisualPlanV1,
    allocation_plan: Any,
    fragments: list[Any],
) -> dict[str, Any]:
    """Reject unknown bindings, fabricated numbers, and invalid visual topology."""
    fragment_ids = {item.fragment_id for item in fragments}
    fragment_text = {item.fragment_id: str(item.text) for item in fragments}
    allocation_pages = {page.page_id: page for page in allocation_plan.pages}
    if visual_plan.source_document_revision != allocation_plan.source_document_revision:
        raise ValueError("Visual plan source revision is stale")
    if visual_plan.variant_key != allocation_plan.variant_key:
        raise ValueError("Visual plan variant does not match allocation")
    if set(page.page_id for page in visual_plan.pages) != set(allocation_pages):
        raise ValueError("Visual plan pages do not match allocation pages")

    for page in visual_plan.pages:
        allocated = set(allocation_pages[page.page_id].fragment_ids)
        referenced = set(page.takeaway_source_fragment_ids)
        referenced.update(page.visual_anchor.source_fragment_ids)
        for node in page.visual_anchor.nodes:
            referenced.update(node.source_fragment_ids)
        unknown = referenced - fragment_ids
        if unknown:
            raise ValueError(f"Visual plan references unknown fragment: {sorted(unknown)[0]}")
        escaped = referenced - allocated
        if escaped:
            raise ValueError(
                f"Visual plan references a fragment outside page allocation: {sorted(escaped)[0]}"
            )
        if page.takeaway_source_fragment_ids:
            grounded = "\n".join(
                fragment_text[item]
                for item in page.takeaway_source_fragment_ids
            )
            source_numbers = set(_NUMBER_RE.findall(grounded))
            invented = set(_NUMBER_RE.findall(page.takeaway)) - source_numbers
            if invented:
                raise ValueError(f"Visual plan contains ungrounded number: {sorted(invented)[0]}")
            normalized_takeaway = _normalized_grounding_text(page.takeaway).rstrip("…")
            normalized_grounded = _normalized_grounding_text(grounded)
            if normalized_takeaway and normalized_takeaway not in normalized_grounded:
                raise ValueError(
                    f"Visual plan takeaway is not a source excerpt: {page.page_id}"
                )
        node_ids = {node.node_id for node in page.visual_anchor.nodes}
        if len(node_ids) != len(page.visual_anchor.nodes):
            raise ValueError("Visual diagram node IDs must be unique")
        if any(edge.source not in node_ids or edge.target not in node_ids for edge in page.visual_anchor.edges):
            raise ValueError("Visual diagram edge references an unknown node")
        for node in page.visual_anchor.nodes:
            node_grounded = "\n".join(
                fragment_text[item]
                for item in node.source_fragment_ids
            )
            normalized_label = _normalized_grounding_text(node.label).rstrip("…")
            if normalized_label and normalized_label not in _normalized_grounding_text(node_grounded):
                raise ValueError("Visual diagram label is not a source excerpt")
        source_text = "\n".join(
            fragment_text[item]
            for item in page.visual_anchor.source_fragment_ids
        )
        if page.visual_anchor.kind == "table":
            for row in page.visual_anchor.parameters.get("rows") or []:
                excerpt = str(row[-1] if isinstance(row, list) and row else row).rstrip("…")
                if excerpt and _normalized_grounding_text(excerpt) not in _normalized_grounding_text(source_text):
                    raise ValueError("Visual table row is not a source excerpt")
        if page.visual_anchor.kind == "coordinate_plot":
            for label in page.visual_anchor.parameters.get("labels") or []:
                excerpt = str(
                    label.get("text") if isinstance(label, dict) else label
                ).rstrip("…")
                if excerpt and _normalized_grounding_text(excerpt) not in _normalized_grounding_text(source_text):
                    raise ValueError("Coordinate label is not a source excerpt")
    return {"passed": True, "page_count": len(visual_plan.pages)}


def apply_visual_plan_to_slides(
    slides: list[dict[str, Any]],
    visual_plan: SlideVisualPlanV1,
) -> list[dict[str, Any]]:
    by_page = {page.page_id: page for page in visual_plan.pages}
    result: list[dict[str, Any]] = []
    for slide in slides:
        page = by_page.get(str(slide.get("unit_id") or ""))
        if not page:
            result.append(slide)
            continue
        updated = dict(slide)
        updated["teaching_job"] = page.teaching_job
        updated["takeaway"] = page.takeaway
        updated["transition_from"] = page.transition_from
        updated["composition"] = page.composition
        updated["visuals"] = (
            []
            if page.visual_anchor.kind == "none"
            else [page.visual_anchor.model_dump(mode="json")]
        )
        quality = dict(updated.get("quality") or {})
        quality["visual_plan_page_id"] = page.page_id
        quality["visual_kind"] = page.visual_anchor.kind
        quality["composition"] = page.composition
        updated["quality"] = quality
        result.append(updated)
    return result


def visual_quality_report(
    visual_plan: SlideVisualPlanV1,
    allocation_plan: Any,
) -> dict[str, Any]:
    """Measure meaningful visual rhythm without counting decorative shapes."""
    allocation_by_id = {page.page_id: page for page in allocation_plan.pages}
    eligible = [
        page
        for page in visual_plan.pages
        if (
            not page.appendix
            and allocation_by_id[page.page_id].fragment_ids
            and allocation_by_id[page.page_id].layout not in {"section-divider"}
        )
    ]
    visual_pages = [
        page for page in eligible
        if page.visual_anchor.kind != "none"
    ]
    ratio = 1.0 if not eligible else len(visual_pages) / len(eligible)
    required = {"teaching": 0.70, "concise": 0.80, "full": 0.40}[visual_plan.mode]
    issues: list[dict[str, Any]] = []
    if ratio + 1e-9 < required:
        issues.append({
            "severity": "critical",
            "code": "visual_coverage_below_threshold",
            "message": f"Effective visual coverage {ratio:.1%} is below {required:.0%}.",
        })

    chapter_pages: dict[str, list[SlideVisualPlanPageV1]] = defaultdict(list)
    for page in eligible:
        if page.chapter_id:
            chapter_pages[page.chapter_id].append(page)
    for chapter_id, pages in chapter_pages.items():
        if not any(page.visual_anchor.kind != "none" for page in pages):
            issues.append({
                "severity": "critical",
                "code": "chapter_explanatory_visual_missing",
                "chapter_id": chapter_id,
            })
        compositions = Counter(page.composition for page in pages)
        if len(pages) >= 4 and any(count / len(pages) > 0.35 for count in compositions.values()):
            issues.append({
                "severity": "major",
                "code": "chapter_composition_overused",
                "chapter_id": chapter_id,
            })

    previous = ""
    run = 0
    for page in eligible:
        if page.composition == previous:
            run += 1
        else:
            previous = page.composition
            run = 1
        if run > 2:
            issues.append({
                "severity": "critical",
                "code": "composition_repeated_more_than_twice",
                "page_id": page.page_id,
            })
            break
    passed = not any(item["severity"] == "critical" for item in issues)
    return {
        "passed": passed,
        "effective_visual_coverage_ratio": round(ratio, 6),
        "required_visual_coverage_ratio": required,
        "eligible_page_count": len(eligible),
        "visual_page_count": len(visual_pages),
        "visual_kind_counts": dict(Counter(
            page.visual_anchor.kind for page in visual_pages
        )),
        "issues": issues,
        "blockers": [item for item in issues if item["severity"] == "critical"],
        "warnings": [item for item in issues if item["severity"] != "critical"],
        "render_contract": "shared_slide_spec_v1",
    }


def visual_integrity_issues(content: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate source bindings and immutable assets in a materialized deck."""
    fragments = {
        str(item.get("fragment_id") or ""): item
        for item in content.get("fragment_manifest") or []
    }
    assets = {
        str(item.get("asset_id") or ""): item
        for item in content.get("visual_asset_manifest") or []
    }
    issues: list[dict[str, Any]] = []
    for slide in content.get("slides") or []:
        slide_id = str(slide.get("unit_id") or "")
        allocated = set((slide.get("quality") or {}).get("fragment_ids") or [])
        for visual in slide.get("visuals") or []:
            kind = str(visual.get("kind") or "")
            source_ids = set(visual.get("source_fragment_ids") or [])
            if source_ids - allocated:
                issues.append({
                    "severity": "critical",
                    "code": "visual_source_binding_invalid",
                    "slide_id": slide_id,
                })
            if source_ids - set(fragments):
                issues.append({
                    "severity": "critical",
                    "code": "visual_unknown_fragment",
                    "slide_id": slide_id,
                })
            source_text = "\n".join(
                str(fragments[fragment_id].get("text") or "")
                for fragment_id in source_ids
                if fragment_id in fragments
            )
            for node in visual.get("nodes") or []:
                node_sources = node.get("source_fragment_ids") or []
                node_text = "\n".join(
                    str(fragments[fragment_id].get("text") or "")
                    for fragment_id in node_sources
                    if fragment_id in fragments
                )
                label = str(node.get("label") or "").rstrip("…")
                if label and _normalized_grounding_text(label) not in _normalized_grounding_text(node_text):
                    issues.append({
                        "severity": "critical",
                        "code": "diagram_label_not_source_bound",
                        "slide_id": slide_id,
                    })
            if kind in {"source_image", "generated_illustration"}:
                asset_id = str(visual.get("asset_id") or "")
                asset = assets.get(asset_id)
                if (
                    not asset
                    or not str(asset.get("sha256") or "")
                    or not str(asset.get("alt_text") or "")
                ):
                    issues.append({
                        "severity": "critical",
                        "code": "visual_asset_missing_or_unbound",
                        "slide_id": slide_id,
                        "asset_id": asset_id,
                    })
            if kind == "chart":
                parameters = visual.get("parameters") or {}
                values = [
                    value
                    for series in parameters.get("series") or []
                    for value in series.get("values") or []
                ]
                if not values or not all(isinstance(value, (int, float)) for value in values):
                    issues.append({
                        "severity": "critical",
                        "code": "chart_data_invalid",
                        "slide_id": slide_id,
                    })
                elif any(str(value) not in source_text for value in values):
                    issues.append({
                        "severity": "critical",
                        "code": "chart_data_not_source_bound",
                        "slide_id": slide_id,
                    })
    if content.get("visual_plan") and (
        (content.get("visual_quality_report") or {}).get("render_contract")
        != "shared_slide_spec_v1"
    ):
        issues.append({
            "severity": "critical",
            "code": "preview_export_render_contract_mismatch",
            "target": "deck",
        })
    return issues


def build_signature(
    *,
    source_document_revision: str,
    mode: str,
    theme: str,
    compiler_version: str,
    theme_version: str,
) -> dict[str, str]:
    payload = {
        "source_document_revision": source_document_revision,
        "mode": mode,
        "theme": theme,
        "compiler_version": compiler_version,
        "theme_version": theme_version,
        "visual_policy_version": SLIDE_VISUAL_POLICY_VERSION,
    }
    return {**payload, "signature": stable_hash(payload, prefix="sbs_")}


def _takeaway(page: Any, fragments: list[Any], deck_title: str) -> tuple[str, list[str]]:
    if fragments:
        candidates: list[tuple[int, int, Any, str]] = []
        kind_priority = {
            "paragraph": 4,
            "heading": 3,
            "list_item": 2,
            "table": 2,
            "formula": 1,
            "code": 1,
        }
        for source_index, source in enumerate(fragments):
            text = _clean_source_text(source.text)
            sentence = re.split(
                r"(?:[。！？!?]+|\.(?=\s|$))\s*",
                text,
                maxsplit=1,
            )[0].strip()
            if source.kind == "list_item":
                label, separator, _remainder = sentence.partition("：")
                if not separator:
                    label, separator, _remainder = sentence.partition(":")
                if separator and 2 <= len(label) <= 30:
                    sentence = label
            if not sentence:
                continue
            generic = _is_generic_source_label(sentence)
            meaningful = len(re.sub(r"[\W_]+", "", sentence)) >= 5
            score = kind_priority.get(source.kind, 0) - (6 if generic else 0)
            candidates.append((score, -source_index, source, sentence if meaningful else text))
        if candidates:
            _score, _source_index, source, sentence = max(candidates, key=lambda item: (item[0], item[1]))
            return _trim_takeaway(sentence), [source.fragment_id]
    derived = [
        str(item.text).strip()
        for item in getattr(page, "derived_text", [])
        if str(item.text).strip()
    ]
    if page.layout == "cover":
        return deck_title, []
    if page.layout == "roadmap":
        return "课程将沿章节问题逐步展开", []
    if page.page_id == "slide:summary":
        return "回到课程主问题，连接概念、方法与应用", []
    if page.page_id == "slide:appendix-divider":
        return "补充材料保留完整课程来源", []
    return _trim_takeaway(derived[0] if derived else deck_title), []


def _teaching_job(page: Any, takeaway: str) -> str:
    role = str(getattr(page, "narrative_role", "") or "concept")
    prefix = {
        "orientation": "建立本段学习方向",
        "concept": "解释核心概念",
        "reasoning": "说明结论为何成立",
        "method": "展示可复用的方法",
        "example": "用具体情境验证概念",
        "misconception": "识别并纠正常见误区",
        "checkpoint": "检查是否真正理解",
        "recap": "连接本章知识链",
        "appendix": "保留补充来源",
    }.get(role, "推进课程理解")
    return f"{prefix}：{takeaway}"


def _transition_text(page: Any, previous: str, current: str) -> str:
    role = str(getattr(page, "narrative_role", "") or "")
    connector = {
        "reasoning": "在上一结论基础上追问原因",
        "method": "把原理转化为可执行步骤",
        "example": "把抽象规则放入具体情境",
        "checkpoint": "暂停推进并检查理解",
        "recap": "收束前面的概念与方法",
        "appendix": "转入补充来源",
    }.get(role, "继续推进同一知识链")
    return f"{connector}：{_trim_takeaway(previous, 34)} → {_trim_takeaway(current, 34)}"


def _visual_anchor(page: Any, fragments: list[Any], index: int) -> VisualAnchorV1:
    ids = [item.fragment_id for item in fragments]
    kinds = {item.kind for item in fragments}
    role = str(getattr(page, "narrative_role", "") or "")
    visual_id = stable_hash(
        {"page_id": page.page_id, "fragment_ids": ids, "policy": SLIDE_VISUAL_POLICY_VERSION},
        prefix="sv_",
    )
    source_image = next(
        (
            item
            for item in fragments
            if item.source_kind == "image" and item.asset_refs
        ),
        None,
    )
    if source_image is not None:
        return VisualAnchorV1(
            visual_id=visual_id,
            kind="source_image",
            purpose="evidence",
            source_fragment_ids=ids,
            alt_text=_trim_takeaway(source_image.text, 120),
            parameters={"asset_ref": source_image.asset_refs[0]},
        )
    if "code" in kinds:
        return VisualAnchorV1(
            visual_id=visual_id,
            kind="code",
            purpose="evidence",
            source_fragment_ids=ids,
            alt_text="课程原始代码及其阅读重点",
            parameters={"language": "code"},
        )
    if "formula" in kinds:
        return VisualAnchorV1(
            visual_id=visual_id,
            kind="formula",
            purpose="evidence",
            source_fragment_ids=ids,
            alt_text="课程原始公式",
            parameters={"source_bound": True},
        )
    if "table" in kinds:
        return VisualAnchorV1(
            visual_id=visual_id,
            kind="table",
            purpose="comparison",
            source_fragment_ids=ids,
            alt_text="课程原始结构化表格",
            parameters={"text": "\n".join(item.text for item in fragments)},
        )

    clauses = _source_clauses(fragments)
    list_clauses = [
        (_trim_takeaway(_clean_source_text(item.text), 72), item.fragment_id)
        for item in fragments
        if item.kind == "list_item" and _clean_source_text(item.text)
    ]
    if (
        len(list_clauses) >= 3
        or (role == "misconception" and len(clauses) >= 2)
        or (str(getattr(page, "layout", "") or "") == "comparison" and len(clauses) >= 2)
    ):
        rows = [
            [str(row_index + 1).zfill(2), label]
            for row_index, (label, _fragment_id) in enumerate((list_clauses or clauses)[:6])
        ]
        return VisualAnchorV1(
            visual_id=visual_id,
            kind="table",
            purpose="comparison" if role == "misconception" else "structure",
            source_fragment_ids=ids,
            alt_text="按课程原文顺序整理的结构化要点",
            parameters={
                "headers": ["顺序", "课程原文要点"],
                "rows": rows,
                "source_bound": True,
            },
        )
    joined_source = " ".join(_clean_source_text(item.text) for item in fragments)
    if (
        clauses
        and _SPATIAL_MATH_RE.search(joined_source)
        and role in {"concept", "reasoning", "method", "example"}
        and (role == "example" or index % 4 == 1)
    ):
        return VisualAnchorV1(
            visual_id=visual_id,
            kind="coordinate_plot",
            purpose="application" if role == "example" else "structure",
            source_fragment_ids=ids,
            alt_text="以坐标空间承载课程原文概念的非比例示意",
            parameters={
                "labels": [
                    {"text": label, "source_fragment_id": fragment_id}
                    for label, fragment_id in clauses[:4]
                ],
                "source_bound": True,
                "not_to_scale": True,
            },
        )
    nodes = [
        VisualNodeV1(
            node_id=f"n{node_index + 1}",
            label=label,
            source_fragment_ids=[fragment_id],
            emphasis="primary" if node_index == 0 else "secondary",
        )
        for node_index, (label, fragment_id) in enumerate(clauses[:5])
    ]
    edges = [
        VisualEdgeV1(
            source=nodes[node_index].node_id,
            target=nodes[node_index + 1].node_id,
            relation=(
                "contrasts"
                if role == "misconception"
                else "supports"
                if role == "reasoning"
                else "sequence"
            ),
        )
        for node_index in range(max(0, len(nodes) - 1))
    ]
    if nodes:
        purpose: VisualPurpose = {
            "example": "application",
            "checkpoint": "exercise",
            "misconception": "comparison",
            "reasoning": "structure",
            "method": "process",
        }.get(role, "structure")  # type: ignore[assignment]
        return VisualAnchorV1(
            visual_id=visual_id,
            kind="relational_diagram",
            purpose=purpose,
            source_fragment_ids=ids,
            alt_text=f"以课程原文片段构成的{purpose}图解",
            nodes=nodes,
            edges=edges,
            parameters={
                "direction": "horizontal" if index % 2 == 0 else "vertical",
                "diagram_type": (
                    "process"
                    if role in {"method", "checkpoint"}
                    else "cause-effect"
                    if role == "reasoning"
                    else "relationship"
                ),
            },
        )
    return _none_anchor(page.page_id, "structure")


def _composition_for(
    page: Any,
    anchor: VisualAnchorV1,
    index: int,
) -> SlideComposition:
    role = str(getattr(page, "narrative_role", "") or "")
    if role == "checkpoint":
        return "exercise"
    if role == "misconception":
        return "comparison"
    if anchor.kind == "none":
        return "statement"
    if anchor.kind in {"formula", "code", "table", "chart"}:
        return ("split-visual", "figure-first", "diagram-full")[index % 3]
    # Rotate silhouettes so a deck cannot degrade into a repeated card grid.
    return ("figure-first", "split-visual", "diagram-full")[index % 3]


def _none_anchor(page_id: str, purpose: VisualPurpose) -> VisualAnchorV1:
    return VisualAnchorV1(
        visual_id=stable_hash({"page_id": page_id, "kind": "none"}, prefix="sv_"),
        kind="none",
        purpose=purpose,
    )


def _source_clauses(fragments: list[Any]) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for fragment in fragments:
        clean = _clean_source_text(fragment.text)
        for value in re.split(r"(?:[。！？；;]\s*|\n+)", clean):
            label = _trim_takeaway(value.strip(), 34)
            if label and label not in {item[0] for item in values}:
                values.append((label, fragment.fragment_id))
    return values


def _clean_source_text(value: str) -> str:
    clean = str(value or "")
    clean = re.sub(r"^#{1,6}\s*", "", clean)
    clean = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", clean)
    clean = re.sub(r"\*\*(.+?)\*\*", r"\1", clean)
    clean = re.sub(r"__(.+?)__", r"\1", clean)
    clean = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"\1", clean)
    clean = re.sub(r"`([^`\n]+)`", r"\1", clean)
    clean = clean.replace("$$", "")
    clean = re.sub(r"(?<!\\)\$", "", clean)
    clean = re.sub(r"\\(?:mathbf|mathrm|mathit|text)\{([^{}]+)\}", r"\1", clean)
    clean = re.sub(r"\\mathbb\{([A-Za-z])\}", r"\1", clean)
    clean = clean.replace(r"\subseteq", "⊆")
    clean = re.sub(r"\\in(?![A-Za-z])", "∈", clean)
    clean = clean.replace(r"\cdots", "…")
    clean = clean.replace(r"\times", "×")
    clean = re.sub(r"\\to(?![A-Za-z])", "→", clean)
    return re.sub(r"\s+", " ", clean).strip()


def _is_generic_source_label(value: str) -> bool:
    normalized = re.sub(r"[\W_]+", "", value).lower()
    return normalized in {
        "核心概念与背景",
        "深度原理底层机制",
        "技术实现方法论",
        "思考与挑战",
        "实战案例行业应用",
        "学习目标",
        "正文",
    }


def _normalized_grounding_text(value: str) -> str:
    return re.sub(r"\s+", "", _clean_source_text(value))


def _trim_takeaway(value: str, limit: int = 54) -> str:
    clean = _clean_source_text(value)
    return clean if len(clean) <= limit else clean[: limit - 1].rstrip("，,；;：: ") + "…"


__all__ = [
    "SLIDE_VISUAL_PLAN_SCHEMA",
    "SLIDE_VISUAL_POLICY_VERSION",
    "SlideVisualPlanPageV1",
    "SlideVisualPlanV1",
    "VisualAnchorV1",
    "VisualEdgeV1",
    "VisualNodeV1",
    "apply_visual_plan_to_slides",
    "build_signature",
    "deterministic_visual_plan",
    "plan_slide_visuals",
    "validate_visual_plan",
    "visual_quality_report",
    "visual_integrity_issues",
]
