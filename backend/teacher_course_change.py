"""Teacher whole-course impact analysis over the existing authoring truths.

This module deliberately owns no course content.  It builds a disposable,
read-only index from the canonical course document and the teacher authoring
repositories, then stores only an explainable CourseChangePlan inside the
existing CourseEvolutionPlan envelope.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Iterable, Literal

from pydantic import BaseModel, Field

from course_change_planning import (
    CourseChangeIntent,
    CourseChangePlan,
    CourseChangeSignal,
    CourseStructureOperation,
    CourseUnitMigration,
    ProposedOutlineNode,
    summarize_course_change_plan,
)
from course_document import CourseDocument, stable_hash
from course_evolution import (
    CourseEvolutionPlan,
    CourseEvolutionRepository,
    CourseEvolutionState,
)
from course_revisions import revision_vector_for_document

COURSE_CHANGE_CONTEXT_SCHEMA = "teacher_course_change_context_v1"
COURSE_CHANGE_INDEX_SCHEMA = "teacher_course_change_index_v1"

AssetState = Literal["available", "partial", "missing", "stale"]
SourceMode = Literal["formal_course", "authoring_workspace", "mixed", "unavailable"]


class TeacherCourseChangeSourceUnavailable(ValueError):
    """No course or authoring truth exists for impact analysis."""


class TeacherCourseChangeUnit(BaseModel):
    unit_id: str
    asset_type: str
    unit_type: str
    title: str
    text: str = ""
    section_ids: list[str] = Field(default_factory=list)
    parent_id: str = ""
    role: str = ""
    source_revision: str = ""
    source_state: str = "current"
    metadata: dict[str, Any] = Field(default_factory=dict)


class TeacherCourseAssetSummary(BaseModel):
    asset_type: str
    label: str
    state: AssetState
    count: int = 0
    source: str
    revision: str = ""


class TeacherCourseChangeContext(BaseModel):
    schema_version: Literal["teacher_course_change_context_v1"] = (
        COURSE_CHANGE_CONTEXT_SCHEMA
    )
    index_schema_version: Literal["teacher_course_change_index_v1"] = (
        COURSE_CHANGE_INDEX_SCHEMA
    )
    course_id: str
    course_title: str
    source_mode: SourceMode
    ready: bool
    readiness_message: str
    base_revision_vector: dict[str, str] = Field(default_factory=dict)
    assets: list[TeacherCourseAssetSummary] = Field(default_factory=list)
    outline: list[dict[str, Any]] = Field(default_factory=list)
    units: list[TeacherCourseChangeUnit] = Field(default_factory=list)
    updated_at: str


AnalysisCallable = Callable[
    [dict[str, Any], list[dict[str, Any]], str],
    Awaitable[dict[str, Any] | None],
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compact(value: Any, limit: int = 420) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= limit else f"{text[: limit - 1].rstrip()}…"


def _find_revision(values: Iterable[Any], revision_id: str) -> dict[str, Any]:
    items = [item for item in values if isinstance(item, dict)]
    selected = next(
        (item for item in items if str(item.get("revision_id") or "") == revision_id),
        None,
    )
    return deepcopy(selected or (items[-1] if items else {}))


def _text_fragments(value: Any, *, depth: int = 0) -> list[str]:
    if depth > 5:
        return []
    if isinstance(value, str):
        normalized = _compact(value, 1200)
        return [normalized] if normalized else []
    if isinstance(value, (int, float, bool)):
        return []
    if isinstance(value, list):
        result: list[str] = []
        for item in value[:80]:
            result.extend(_text_fragments(item, depth=depth + 1))
        return result
    if not isinstance(value, dict):
        return []
    preferred = (
        "title", "name", "content", "text", "summary", "content_summary",
        "teacher_activity", "student_activity", "expected_output", "purpose",
        "learning_objective", "key_message", "subtitle", "question", "prompt",
        "stem", "answer", "explanation", "speaker_notes",
    )
    result: list[str] = []
    for key in preferred:
        if key in value:
            result.extend(_text_fragments(value.get(key), depth=depth + 1))
    if result:
        return result
    for item in list(value.values())[:40]:
        result.extend(_text_fragments(item, depth=depth + 1))
    return result


def _unit_text(value: Any, limit: int = 1200) -> str:
    unique = list(dict.fromkeys(_text_fragments(value)))
    return _compact(" · ".join(unique), limit)


def _outline_from_document(document: CourseDocument) -> list[dict[str, Any]]:
    return [
        {
            "node_id": item.section_id,
            "parent_node_id": item.parent_section_id or "root",
            "node_name": item.title,
            "node_level": item.level,
            "learning_objective": item.learning_objective,
            "source": "course_document",
        }
        for item in sorted(document.sections, key=lambda value: (value.position, value.section_id))
    ]


def _outline_from_preview(preview: dict[str, Any] | None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in (preview or {}).get("nodes") or []:
        if not isinstance(raw, dict) or not raw.get("node_id"):
            continue
        result.append({
            "node_id": str(raw.get("node_id") or ""),
            "parent_node_id": str(raw.get("parent_node_id") or "root"),
            "node_name": str(raw.get("node_name") or "未命名章节"),
            "node_level": int(raw.get("node_level") or 1),
            "learning_objective": str(raw.get("learning_objective") or ""),
            "source": "teacher_generation_workspace",
        })
    return result


def _outline_units(outline: list[dict[str, Any]]) -> list[TeacherCourseChangeUnit]:
    return [
        TeacherCourseChangeUnit(
            unit_id=f"outline:{item['node_id']}",
            asset_type="outline",
            unit_type="outline_node",
            title=str(item.get("node_name") or "未命名章节"),
            text=_compact(item.get("learning_objective") or ""),
            section_ids=[str(item["node_id"])],
            parent_id=str(item.get("parent_node_id") or "root"),
            source_revision=str(item.get("source_revision") or ""),
            metadata={"level": int(item.get("node_level") or 1)},
        )
        for item in outline
    ]


def _document_units(document: CourseDocument) -> list[TeacherCourseChangeUnit]:
    sections = {item.section_id: item for item in document.sections}
    result: list[TeacherCourseChangeUnit] = []
    for block in document.blocks:
        section = sections.get(block.section_id)
        result.append(TeacherCourseChangeUnit(
            unit_id=f"course_content:{block.block_id}",
            asset_type="course_content",
            unit_type="course_block",
            title=(section.title if section else block.block_id),
            text=_unit_text(block.payload),
            section_ids=[block.section_id],
            parent_id=block.section_id,
            role=block.role,
            source_revision=block.internal_revision,
            source_state=block.status,
            metadata={"kind": block.kind},
        ))
    return result


def _authoring_units(authoring: dict[str, Any]) -> list[TeacherCourseChangeUnit]:
    result: list[TeacherCourseChangeUnit] = []
    for lesson_id, lesson in (authoring.get("lessons") or {}).items():
        if not isinstance(lesson, dict):
            continue
        plan_revision = _find_revision(
            lesson.get("revisions") or [],
            str(lesson.get("working_revision_id") or ""),
        )
        plan = plan_revision.get("plan") or {}
        for index, section in enumerate(plan.get("sections") or []):
            if not isinstance(section, dict):
                continue
            section_id = str(
                section.get("section_node_id")
                or section.get("section_id")
                or lesson_id
            )
            unit_id = str(section.get("section_id") or section_id or index)
            result.append(TeacherCourseChangeUnit(
                unit_id=f"lesson_plan:{lesson_id}:{unit_id}",
                asset_type="lesson_plan",
                unit_type="lesson_plan_section",
                title=str(section.get("title") or section.get("name") or f"教案段落 {index + 1}"),
                text=_unit_text(section),
                section_ids=[section_id] if section_id else [str(lesson_id)],
                parent_id=str(lesson_id),
                role=str(section.get("role") or ""),
                source_revision=str(plan_revision.get("revision_id") or ""),
                source_state=str(lesson.get("source_state") or "current"),
            ))

        script_revision = _find_revision(
            lesson.get("script_revisions") or [],
            str(lesson.get("working_script_revision_id") or ""),
        )
        script_state = str(
            (lesson.get("script_confirmation") or {}).get("source_state")
            or "current"
        )
        for section_index, section in enumerate(script_revision.get("sections") or []):
            if not isinstance(section, dict):
                continue
            section_id = str(section.get("section_node_id") or lesson_id)
            for block_index, block in enumerate(section.get("blocks") or []):
                if not isinstance(block, dict):
                    continue
                block_id = str(block.get("block_id") or f"{section_index}-{block_index}")
                result.append(TeacherCourseChangeUnit(
                    unit_id=f"script:{lesson_id}:{block_id}",
                    asset_type="script",
                    unit_type="script_block",
                    title=str(block.get("title") or block.get("name") or section.get("title") or "讲稿段落"),
                    text=_unit_text(block),
                    section_ids=[section_id],
                    parent_id=str(lesson_id),
                    role=str(block.get("role") or ""),
                    source_revision=str(script_revision.get("revision_id") or ""),
                    source_state=script_state,
                    metadata={"module_id": str(block.get("module_id") or "")},
                ))

        for asset in lesson.get("ppt_assets") or []:
            if not isinstance(asset, dict):
                continue
            revision = _find_revision(
                asset.get("v6_revisions") or asset.get("revisions") or [],
                str(asset.get("working_v6_revision_id") or asset.get("working_revision_id") or ""),
            )
            pages = revision.get("pages") or (revision.get("representation") or {}).get("pages") or []
            for page_index, page in enumerate(pages):
                if not isinstance(page, dict):
                    continue
                page_id = str(page.get("page_id") or page.get("slide_id") or page_index + 1)
                section_ids = [
                    str(value) for value in (
                        page.get("section_node_ids")
                        or ([page.get("section_node_id")] if page.get("section_node_id") else [])
                    ) if value
                ] or [str(lesson_id)]
                result.append(TeacherCourseChangeUnit(
                    unit_id=f"ppt:{lesson_id}:{page_id}",
                    asset_type="ppt",
                    unit_type="slide",
                    title=str(page.get("title") or f"第 {page_index + 1} 页"),
                    text=_unit_text(page),
                    section_ids=section_ids,
                    parent_id=str(lesson_id),
                    source_revision=str(revision.get("revision_id") or ""),
                    source_state=str(asset.get("source_state") or "current"),
                ))
    return result


def _ppt_units(
    authoring: dict[str, Any],
    registries: list[dict[str, Any]],
) -> list[TeacherCourseChangeUnit]:
    registry_by_course = {
        str(item.get("course_id") or ""): item
        for item in registries
        if isinstance(item, dict) and item.get("course_id")
    }
    result: list[TeacherCourseChangeUnit] = []
    for lesson_id, lesson in (authoring.get("lessons") or {}).items():
        if not isinstance(lesson, dict):
            continue
        for asset in lesson.get("ppt_assets") or []:
            if not isinstance(asset, dict):
                continue
            synthetic_course_id = str(asset.get("synthetic_course_id") or "")
            registry = registry_by_course.get(synthetic_course_id) or {}
            spec_id = ""
            binding = _find_revision(
                asset.get("v6_revisions") or [],
                str(asset.get("working_v6_revision_id") or ""),
            )
            spec_id = str(binding.get("spec_id") or "")
            spec = next(
                (
                    item for item in registry.get("specs") or []
                    if isinstance(item, dict) and str(item.get("spec_id") or "") == spec_id
                ),
                {},
            )
            content = ((spec.get("payload") or {}).get("content") or {})
            for page_index, page in enumerate(content.get("pages") or []):
                if not isinstance(page, dict):
                    continue
                page_id = str(page.get("page_id") or page_index + 1)
                section_ids = [
                    str(value) for value in page.get("source_section_ids") or [] if value
                ] or [str(lesson_id)]
                result.append(TeacherCourseChangeUnit(
                    unit_id=f"ppt:{lesson_id}:{page_id}",
                    asset_type="ppt",
                    unit_type="slide",
                    title=str(page.get("title") or f"第 {page_index + 1} 页"),
                    text=_unit_text(page),
                    section_ids=section_ids,
                    parent_id=str(lesson_id),
                    source_revision=str(spec.get("revision") or binding.get("revision_id") or ""),
                    source_state=str(asset.get("source_state") or "current"),
                    metadata={
                        "representation_id": str(asset.get("working_representation_id") or ""),
                        "spec_id": spec_id,
                    },
                ))
    return result


def _question_units(bundle: dict[str, Any] | None) -> list[TeacherCourseChangeUnit]:
    if not bundle:
        return []
    values = bundle.get("items") or bundle.get("questions") or []
    result: list[TeacherCourseChangeUnit] = []
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("item_id") or item.get("question_id") or index + 1)
        section_ids = [
            str(value) for value in (
                item.get("section_ids")
                or item.get("section_node_ids")
                or ([item.get("section_id")] if item.get("section_id") else [])
            ) if value
        ]
        result.append(TeacherCourseChangeUnit(
            unit_id=f"question_bank:{item_id}",
            asset_type="question_bank",
            unit_type="question",
            title=str(item.get("title") or item.get("stem") or f"题目 {index + 1}"),
            text=_unit_text(item),
            section_ids=section_ids,
            role=str(item.get("role") or item.get("question_type") or "checkpoint"),
            source_revision=str(bundle.get("bundle_revision_id") or ""),
            source_state=str(item.get("status") or "current"),
        ))
    return result


def build_teacher_course_change_context(
    *,
    course_id: str,
    document: CourseDocument,
    preview: dict[str, Any] | None,
    authoring: dict[str, Any] | None,
    question_bank: dict[str, Any] | None,
    representation_registries: list[dict[str, Any]] | None = None,
) -> TeacherCourseChangeContext:
    formal_outline = _outline_from_document(document)
    preview_outline = _outline_from_preview(preview)
    outline = formal_outline or preview_outline
    indexed_units = [
        *_outline_units(outline),
        *_document_units(document),
        *_authoring_units(authoring or {}),
        *_ppt_units(authoring or {}, representation_registries or []),
        *_question_units(question_bank),
    ]
    # A slide may be projected both from an authoring revision and from the
    # representation registry. The registry entry is appended later and is
    # richer, so keep it without exposing duplicate IDs to ranking/review.
    units = list({item.unit_id: item for item in indexed_units}.values())
    counts = Counter(item.asset_type for item in units)
    labels = {
        "outline": "课程大纲",
        "course_content": "课程正文",
        "lesson_plan": "教案",
        "script": "讲稿",
        "ppt": "PPT",
        "question_bank": "题库",
    }
    sources = {
        "outline": "course_document" if formal_outline else "teacher_generation_workspace",
        "course_content": "course_document",
        "lesson_plan": "teacher_lesson_authoring",
        "script": "teacher_lesson_authoring",
        "ppt": "teacher_lesson_authoring",
        "question_bank": "question_bank",
    }
    authoring_revision = str((authoring or {}).get("revision") or "")
    revisions = {
        **revision_vector_for_document(document).revisions,
        "teacher_outline": str((authoring or {}).get("outline_revision_id") or ""),
        "teacher_lesson_authoring": authoring_revision,
        "question_bank": str((question_bank or {}).get("bundle_revision_id") or ""),
    }
    assets: list[TeacherCourseAssetSummary] = []
    for asset_type in labels:
        count = counts.get(asset_type, 0)
        state: AssetState = "available" if count else "missing"
        if asset_type in {"lesson_plan", "script", "ppt"} and count and len((authoring or {}).get("lessons") or {}) < max(1, len([item for item in outline if int(item.get("node_level") or 1) == 1])):
            state = "partial"
        if any(item.asset_type == asset_type and item.source_state == "stale" for item in units):
            state = "stale"
        assets.append(TeacherCourseAssetSummary(
            asset_type=asset_type,
            label=labels[asset_type],
            state=state,
            count=count,
            source=sources[asset_type],
            revision=(
                document.document_revision
                if asset_type == "course_content"
                else str((authoring or {}).get("outline_revision_id") or "")
                if asset_type == "outline"
                else str((question_bank or {}).get("bundle_revision_id") or "")
                if asset_type == "question_bank"
                else authoring_revision
            ),
        ))
    formal_available = bool(document.sections or document.blocks)
    authoring_available = bool(preview_outline or (authoring or {}).get("lessons"))
    source_mode: SourceMode = (
        "mixed" if formal_available and authoring_available
        else "formal_course" if formal_available
        else "authoring_workspace" if authoring_available
        else "unavailable"
    )
    ready = bool(outline or units)
    return TeacherCourseChangeContext(
        course_id=course_id,
        course_title=document.title or str((preview or {}).get("course_name") or "未命名课程"),
        source_mode=source_mode,
        ready=ready,
        readiness_message=(
            "已连接课程结构与现有教学资产"
            if ready else "当前课程还没有可分析的结构或教学资产"
        ),
        base_revision_vector={key: value for key, value in revisions.items() if value},
        assets=assets,
        outline=outline,
        units=units,
        updated_at=_now(),
    )


def context_view(context: TeacherCourseChangeContext) -> dict[str, Any]:
    payload = context.model_dump(mode="json")
    payload["units"] = [
        {
            **unit.model_dump(mode="json"),
            "text": _compact(unit.text, 320),
        }
        for unit in context.units
    ]
    payload["summary"] = {
        "available_assets": sum(item.state in {"available", "partial", "stale"} for item in context.assets),
        "missing_assets": sum(item.state == "missing" for item in context.assets),
        "indexed_units": len(context.units),
        "outline_nodes": len(context.outline),
    }
    return payload


def _tokens(value: str) -> set[str]:
    normalized = str(value or "").lower()
    latin = re.findall(r"[a-z0-9][a-z0-9_.+-]{1,}", normalized)
    cjk = re.findall(r"[\u4e00-\u9fff]", normalized)
    grams = ["".join(cjk[index:index + 2]) for index in range(max(0, len(cjk) - 1))]
    return set(latin + grams)


def rank_change_units(
    context: TeacherCourseChangeContext,
    instruction: str,
    *,
    limit: int = 80,
) -> list[dict[str, Any]]:
    request_tokens = _tokens(instruction)
    broad_request = any(value in instruction for value in ("所有", "全部", "整个课程", "全课", "每个"))
    scored: list[tuple[float, TeacherCourseChangeUnit]] = []
    for unit in context.units:
        body_tokens = _tokens(f"{unit.title} {unit.text} {unit.role}")
        overlap = len(request_tokens.intersection(body_tokens))
        role_bonus = 0.0
        if any(value in instruction for value in ("例子", "案例", "示例")) and unit.role in {"example", "application", "counterexample"}:
            role_bonus = 5.0
        if any(value in instruction for value in ("题", "练习", "考核")) and unit.asset_type == "question_bank":
            role_bonus = 4.0
        if any(value in instruction.lower() for value in ("ppt", "课件", "幻灯片")) and unit.asset_type == "ppt":
            role_bonus = 4.0
        if broad_request:
            role_bonus += 0.8
        source_bonus = 0.4 if unit.asset_type == "outline" else 0.0
        scored.append((overlap * 2.0 + role_bonus + source_bonus, unit))

    # Expand strong semantic hits through explicit section relationships. This
    # is a recall accelerator only; the model (or teacher in fallback mode)
    # remains responsible for the impact verdict.
    anchor_section_ids = {
        section_id
        for score, unit in scored
        if score >= 2.0
        for section_id in unit.section_ids
    }
    if anchor_section_ids:
        scored = [
            (
                score + (1.5 if anchor_section_ids.intersection(unit.section_ids) else 0.0),
                unit,
            )
            for score, unit in scored
        ]
    scored.sort(key=lambda value: (-value[0], value[1].asset_type, value[1].unit_id))
    selected: list[tuple[float, TeacherCourseChangeUnit]] = []
    selected_ids: set[str] = set()
    # Reserve capacity before filling by global score. Otherwise a broad
    # request makes every unit positive and the top-N can be exhausted by one
    # large asset, hiding scripts or slides from the model entirely.
    asset_types = sorted({item.asset_type for item in context.units})
    reserve_per_asset = max(1, min(4, limit // max(1, len(asset_types) * 2)))
    for asset_type in asset_types:
        candidates = [item for item in scored if item[1].asset_type == asset_type]
        for candidate in candidates[:reserve_per_asset]:
            if len(selected) >= limit:
                break
            selected.append(candidate)
            selected_ids.add(candidate[1].unit_id)
    for candidate in scored:
        if len(selected) >= limit:
            break
        if candidate[0] <= 0 or candidate[1].unit_id in selected_ids:
            continue
        selected.append(candidate)
        selected_ids.add(candidate[1].unit_id)
    selected.sort(key=lambda value: (-value[0], value[1].asset_type, value[1].unit_id))
    return [
        {
            "unit_id": unit.unit_id,
            "asset_type": unit.asset_type,
            "unit_type": unit.unit_type,
            "title": unit.title,
            "summary": _compact(unit.text, 260),
            "section_ids": unit.section_ids,
            "role": unit.role,
            "source_state": unit.source_state,
            "rank_score": round(score, 2),
        }
        for score, unit in selected
    ]


def _fallback_analysis(
    context: TeacherCourseChangeContext,
    instruction: str,
    ranked: list[dict[str, Any]],
) -> dict[str, Any]:
    structural_terms = ("章节", "大纲", "重构", "合并", "拆分", "删除", "移动", "顺序", "新增一章")
    structural = any(term in instruction for term in structural_terms)
    positive = [item for item in ranked if float(item.get("rank_score") or 0) > 0]
    pool = positive or ranked
    affected: list[dict[str, Any]] = []
    affected_ids: set[str] = set()
    # Fallback remains visibly provisional, but it must not silently collapse
    # a whole-course request into whichever document happened to rank first.
    for asset_type in sorted({str(item.get("asset_type") or "") for item in pool}):
        candidate = next(
            (item for item in pool if str(item.get("asset_type") or "") == asset_type),
            None,
        )
        if candidate is not None:
            affected.append(candidate)
            affected_ids.add(str(candidate.get("unit_id") or ""))
    for item in pool:
        if len(affected) >= 24:
            break
        unit_id = str(item.get("unit_id") or "")
        if unit_id in affected_ids:
            continue
        affected.append(item)
        affected_ids.add(unit_id)
    return {
        "analysis_mode": "index_fallback",
        "interpreted_goal": instruction,
        "signal_kind": "structural" if structural else "uncertain",
        "signal_confidence": 0.45 if structural else 0.35,
        "hard_constraints": [],
        "soft_preferences": [],
        "protected_requirements": [],
        "assumptions": ["AI 深度判断暂不可用，当前影响范围由索引给出，需老师复核。"],
        "blocking_questions": [],
        "affected_units": [
            {
                "unit_id": item["unit_id"],
                "disposition": "regenerate" if structural and item["asset_type"] in {"script", "ppt"} else "rewrite_partial",
                "reason": "与老师要求在主题、角色或结构关系上相关",
                "confidence": 0.45,
            }
            for item in affected
        ],
        "structure": {"required": structural, "affected_node_ids": [], "proposed_outline": []},
    }


def _normalize_analysis(
    raw: dict[str, Any] | None,
    context: TeacherCourseChangeContext,
    instruction: str,
    ranked: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return _fallback_analysis(context, instruction, ranked)
    result = deepcopy(raw)
    result["analysis_mode"] = "ai_ranked"
    result["interpreted_goal"] = _compact(result.get("interpreted_goal") or instruction, 1000)
    if result.get("signal_kind") not in {"semantic", "structural", "mixed", "uncertain"}:
        result["signal_kind"] = "uncertain"
    try:
        result["signal_confidence"] = max(0.0, min(1.0, float(result.get("signal_confidence") or 0.5)))
    except (TypeError, ValueError):
        result["signal_confidence"] = 0.5
    for key in ("hard_constraints", "soft_preferences", "protected_requirements", "assumptions", "blocking_questions"):
        result[key] = [
            _compact(item, 400) for item in result.get(key) or [] if _compact(item, 400)
        ][:30]
    known_ids = {item.unit_id for item in context.units}
    affected: list[dict[str, Any]] = []
    for item in result.get("affected_units") or []:
        if not isinstance(item, dict) or str(item.get("unit_id") or "") not in known_ids:
            continue
        disposition = str(item.get("disposition") or "rewrite_partial")
        if disposition not in {"reuse_exact", "reuse_rebind", "rewrite_partial", "regenerate", "retire", "blocked"}:
            disposition = "rewrite_partial"
        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence") or 0.6)))
        except (TypeError, ValueError):
            confidence = 0.6
        affected.append({
            "unit_id": str(item["unit_id"]),
            "disposition": disposition,
            "reason": _compact(item.get("reason") or "AI 判断该单元会受到影响", 500),
            "confidence": confidence,
        })
    result["affected_units"] = affected
    structure = result.get("structure") if isinstance(result.get("structure"), dict) else {}
    structure["required"] = bool(structure.get("required") or result["signal_kind"] in {"structural", "mixed"})
    structure["affected_node_ids"] = [
        str(value) for value in structure.get("affected_node_ids") or [] if str(value)
    ][:200]
    structure["proposed_outline"] = [
        item for item in structure.get("proposed_outline") or [] if isinstance(item, dict)
    ][:200]
    result["structure"] = structure
    if not affected and not result["blocking_questions"]:
        fallback = _fallback_analysis(context, instruction, ranked)
        result["affected_units"] = fallback["affected_units"]
        result["assumptions"] = [
            *result["assumptions"],
            "AI 没有返回可定位单元，已保留索引候选供老师复核。",
        ]
    return result


def _structure_operations(
    context: TeacherCourseChangeContext,
    analysis: dict[str, Any],
    plan_id: str,
) -> list[CourseStructureOperation]:
    structure = analysis.get("structure") or {}
    proposed = structure.get("proposed_outline") or []
    if not structure.get("required") or not proposed:
        return []
    proposed_nodes: list[ProposedOutlineNode] = []
    for index, item in enumerate(proposed):
        title = _compact(item.get("title") or item.get("node_name"), 200)
        if not title:
            continue
        proposed_nodes.append(ProposedOutlineNode(
            provisional_id=str(item.get("provisional_id") or f"proposed-{index + 1}"),
            title=title,
            parent_ref=str(item.get("parent_ref") or item.get("parent_node_id") or "root"),
            position=index,
            learning_focus=_compact(item.get("learning_focus") or item.get("learning_objective"), 500),
            source_node_ids=[str(value) for value in item.get("source_node_ids") or [] if str(value)],
        ))
    if not proposed_nodes:
        return []
    revision = context.base_revision_vector.get("teacher_outline") or context.base_revision_vector.get("course_document") or "unknown"
    return [CourseStructureOperation(
        operation_id=f"structure-{uuid.uuid4().hex}",
        operation_type="REBUILD_OUTLINE",
        base_blueprint_revision_id=revision,
        idempotency_key=stable_hash({"plan": plan_id, "outline": proposed}, prefix="idem_"),
        source_node_ids=[str(item.get("node_id") or "") for item in context.outline if item.get("node_id")],
        proposed_nodes=proposed_nodes,
        reason=_compact(structure.get("reason") or "课程结构需要先调整，再迁移和重建下游资产", 500),
        assumptions=[_compact(item, 300) for item in analysis.get("assumptions") or []],
        confidence=float(analysis.get("signal_confidence") or 0.5),
    )]


def _unit_migrations(
    context: TeacherCourseChangeContext,
    analysis: dict[str, Any],
) -> list[CourseUnitMigration]:
    by_id = {item.unit_id: item for item in context.units}
    result: list[CourseUnitMigration] = []
    for item in analysis.get("affected_units") or []:
        unit = by_id.get(str(item.get("unit_id") or ""))
        if unit is None:
            continue
        disposition = str(item.get("disposition") or "rewrite_partial")
        target_ids = [] if disposition == "retire" else [unit.unit_id]
        result.append(CourseUnitMigration(
            migration_id=f"migration-{uuid.uuid4().hex}",
            asset_type=unit.asset_type,
            unit_type=unit.unit_type,
            source_unit_ids=[unit.unit_id],
            target_unit_ids=target_ids,
            disposition=disposition,
            reason=str(item.get("reason") or "AI 判断该单元会受到影响"),
            confidence=float(item.get("confidence") or 0.6),
            dependency_ids=list(unit.section_ids),
            base_revisions={unit.unit_id: unit.source_revision} if unit.source_revision else {},
            requires_review=True,
            candidate_instruction=analysis.get("interpreted_goal") or "",
            metadata={
                "title": unit.title,
                "before_preview": _compact(unit.text, 360),
                "section_ids": unit.section_ids,
                "role": unit.role,
                "source_state": unit.source_state,
            },
        ))
    return result


async def create_teacher_course_change_plan(
    *,
    context: TeacherCourseChangeContext,
    user_id: str,
    request_id: str,
    instruction: str,
    repository: CourseEvolutionRepository,
    analyzer: AnalysisCallable | None = None,
) -> CourseEvolutionState:
    if not context.ready:
        raise TeacherCourseChangeSourceUnavailable("当前课程尚未形成可分析的大纲或教学资产")
    normalized_instruction = _compact(instruction, 5000)
    if not normalized_instruction:
        raise ValueError("课程修改要求不能为空")
    current = repository.load(user_id, context.course_id)
    existing = next(
        (
            item for item in current.change_sets
            if str(item.impact_summary.get("request_id") or "") == request_id
        ),
        None,
    )
    if existing is not None:
        return current

    ranked = rank_change_units(context, normalized_instruction)
    overview = {
        "course_id": context.course_id,
        "course_title": context.course_title,
        "source_mode": context.source_mode,
        "assets": [item.model_dump(mode="json") for item in context.assets],
        "outline": context.outline[:200],
        "indexed_unit_count": len(context.units),
    }
    raw_analysis: dict[str, Any] | None = None
    if analyzer is not None:
        try:
            raw_analysis = await analyzer(overview, ranked, normalized_instruction)
        except Exception:
            raw_analysis = None
    analysis = _normalize_analysis(raw_analysis, context, normalized_instruction, ranked)

    timestamp = _now()
    change_set_id = f"course-change-{uuid.uuid4().hex}"
    intent_id = f"intent-{uuid.uuid4().hex}"
    questions = analysis.get("blocking_questions") or []
    signal_kind = str(analysis.get("signal_kind") or "uncertain")
    intent = CourseChangeIntent(
        intent_id=intent_id,
        course_id=context.course_id,
        raw_request=normalized_instruction,
        interpreted_goal=str(analysis.get("interpreted_goal") or normalized_instruction),
        scope_hint={
            "requested_scope": "whole_course",
            "analysis_mode": analysis.get("analysis_mode"),
            "ranked_candidate_count": len(ranked),
        },
        hard_constraints=analysis.get("hard_constraints") or [],
        soft_preferences=analysis.get("soft_preferences") or [],
        protected_requirements=analysis.get("protected_requirements") or [],
        source_refs=[item.source for item in context.assets if item.state != "missing"],
        signals=[CourseChangeSignal(
            signal_id=f"signal-{uuid.uuid4().hex}",
            kind=signal_kind,
            evidence="AI 结合课程索引、资产关系与老师原话判断",
            confidence=float(analysis.get("signal_confidence") or 0.5),
            source=str(analysis.get("analysis_mode") or "index_fallback"),
        )],
        assumptions=analysis.get("assumptions") or [],
        blocking_questions=questions,
        can_proceed_without_clarification=not questions,
    )
    structure_operations = _structure_operations(context, analysis, change_set_id)
    migrations = _unit_migrations(context, analysis)
    planning = CourseChangePlan(
        plan_id=change_set_id,
        course_id=context.course_id,
        intent=intent,
        base_revision_vector=context.base_revision_vector,
        structural_operations=structure_operations,
        unit_migrations=migrations,
        status="needs_clarification" if questions else "impact_ready",
        created_at=timestamp,
        updated_at=timestamp,
    )
    summary = summarize_course_change_plan(planning).model_dump(mode="json")
    affected_units = [
        {
            "migration_id": item.migration_id,
            "unit_id": item.source_unit_ids[0] if item.source_unit_ids else "",
            "asset_type": item.asset_type,
            "unit_type": item.unit_type,
            "title": str(item.metadata.get("title") or item.unit_type),
            "before_preview": str(item.metadata.get("before_preview") or ""),
            "section_ids": item.metadata.get("section_ids") or [],
            "source_state": str(item.metadata.get("source_state") or "current"),
            "disposition": item.disposition,
            "reason": item.reason,
            "confidence": item.confidence,
            "candidate_status": item.candidate_status,
        }
        for item in migrations
    ]
    plan = CourseEvolutionPlan(
        change_set_id=change_set_id,
        user_id=user_id,
        course_id=context.course_id,
        hypothesis_id="",
        source_kind="manual_request",
        target_section_id="",
        request_text=normalized_instruction,
        growth_direction="author_directed",
        generation_status="ready",
        base_revision_vector=context.base_revision_vector,
        teacher_change_planning=planning,
        scope_selection="whole_course",
        allowed_scopes=[],
        impact_summary={
            "request_id": request_id,
            "analysis_mode": analysis.get("analysis_mode"),
            "source_mode": context.source_mode,
            "asset_inventory": [item.model_dump(mode="json") for item in context.assets],
            "coverage": {
                "indexed_units": len(context.units),
                "ranked_candidates": len(ranked),
                "affected_units": len(affected_units),
            },
            "planning_summary": summary,
            "affected_units": affected_units,
            "current_outline": context.outline,
            "proposed_outline": (analysis.get("structure") or {}).get("proposed_outline") or [],
            "application_capability": "impact_review",
            "formal_content_changed": False,
        },
        expected_effect=str(analysis.get("interpreted_goal") or normalized_instruction),
        status="pending",
        created_at=timestamp,
        updated_at=timestamp,
    )
    def append_if_absent(latest: CourseEvolutionState) -> CourseEvolutionState:
        if any(
            str(item.impact_summary.get("request_id") or "") == request_id
            for item in latest.change_sets
        ):
            return latest
        latest.change_sets.append(plan)
        latest.updated_at = timestamp
        return latest

    return repository.update(user_id, context.course_id, append_if_absent)


def review_teacher_course_change_scope(
    *,
    repository: CourseEvolutionRepository,
    user_id: str,
    course_id: str,
    change_set_id: str,
    selected_migration_ids: list[str],
    confirm_structure: bool = False,
) -> CourseEvolutionState:
    """Persist teacher scope review without pretending content was applied."""
    selected = list(dict.fromkeys(str(value) for value in selected_migration_ids if str(value)))

    def update(state: CourseEvolutionState) -> CourseEvolutionState:
        plan = next(
            (item for item in state.change_sets if item.change_set_id == change_set_id),
            None,
        )
        if plan is None or plan.teacher_change_planning is None:
            raise KeyError(change_set_id)
        known = {
            item.migration_id
            for item in plan.teacher_change_planning.unit_migrations
        }
        unknown = set(selected).difference(known)
        if unknown:
            raise ValueError("影响范围包含不属于本方案的课程单元")
        if confirm_structure:
            proposed_outline = plan.impact_summary.get("proposed_outline") or []
            if not plan.teacher_change_planning.structural_operations:
                raise ValueError("当前方案不包含需要确认的课程结构变化")
            if not proposed_outline:
                raise ValueError("新的课程结构尚未形成，不能确认迁移")
        timestamp = _now()
        plan.impact_summary["scope_review"] = {
            "selected_migration_ids": selected,
            "excluded_migration_ids": sorted(known.difference(selected)),
            "reviewed_at": timestamp,
            "formal_content_changed": False,
        }
        if confirm_structure:
            plan.teacher_change_planning.structure_review_status = "confirmed"
            plan.impact_summary["structure_review"] = {
                "status": "confirmed",
                "confirmed_at": timestamp,
                "formal_content_changed": False,
            }
        plan.teacher_change_planning.updated_at = timestamp
        plan.updated_at = timestamp
        state.updated_at = timestamp
        return state

    return repository.update(user_id, course_id, update)


__all__ = [
    "TeacherCourseChangeContext",
    "TeacherCourseChangeSourceUnavailable",
    "TeacherCourseChangeUnit",
    "build_teacher_course_change_context",
    "context_view",
    "create_teacher_course_change_plan",
    "rank_change_units",
    "review_teacher_course_change_scope",
]
