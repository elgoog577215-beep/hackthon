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
from course_document import CourseBlock, CourseDocument, CourseSection, stable_hash
from course_evolution import (
    CourseEvolutionOperation,
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
        "title", "name", "content", "text", "markdown", "summary", "content_summary",
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
            "section_snapshot": item.model_dump(mode="json"),
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
            metadata={
                "kind": block.kind,
                # Kept inside the server-side disposable index so a reviewed
                # candidate can compile back into the existing canonical
                # command group. context_view deliberately strips this payload.
                "course_block": block.model_dump(mode="json"),
                "editable_fields": {
                    key: value
                    for key, value in block.payload.items()
                    if key in {"markdown", "text", "content", "title", "summary"}
                    and isinstance(value, str)
                },
            },
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
    payload["outline"] = [
        {
            key: value
            for key, value in item.items()
            if key != "section_snapshot"
        }
        for item in payload.get("outline") or []
    ]
    payload["units"] = [
        {
            **unit.model_dump(mode="json"),
            "text": _compact(unit.text, 320),
            "metadata": {
                key: value
                for key, value in unit.metadata.items()
                if key not in {"course_block", "editable_fields"}
            },
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
            "editable_fields": (
                {
                    key: _compact(value, 2400)
                    for key, value in (unit.metadata.get("editable_fields") or {}).items()
                    if isinstance(value, str)
                }
                if unit.asset_type == "course_content"
                else {}
            ),
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


_QUOTED_TERM_REPLACEMENT_RE = re.compile(
    r"(?:把|将)?\s*[“‘\"'](?P<before>[^”’\"']{1,120})[”’\"']"
    r"\s*(?:永远|统一|全部|全局)?\s*(?:替换成|替换为|改成|改为)\s*"
    r"[“‘\"'](?P<after>[^”’\"']{1,120})[”’\"']"
)
_PLAIN_TERM_REPLACEMENT_RE = re.compile(
    r"(?:把|将)\s*(?P<before>[^\s，,。；;\n]{1,80}?)\s*"
    r"(?:永远|统一|全部|全局)?\s*(?:替换成|替换为|改成|改为)\s*"
    r"(?P<after>[^\s，,。；;\n]{1,80})"
)


def _explicit_term_replacement_analysis(
    context: TeacherCourseChangeContext,
    instruction: str,
) -> dict[str, Any] | None:
    """Compile a literal A-to-B request into the existing operation group."""

    match = (
        _QUOTED_TERM_REPLACEMENT_RE.search(instruction)
        or _PLAIN_TERM_REPLACEMENT_RE.search(instruction)
    )
    if match is None:
        return None
    before = _compact(match.group("before"), 120)
    after = _compact(match.group("after"), 120)
    if not before or not after or before == after:
        return None

    affected_units: list[dict[str, Any]] = []
    for unit in context.units:
        if unit.asset_type != "course_content":
            continue
        patches = [
            {
                "field": field,
                "before": before,
                "after": after,
                "replace_all": True,
            }
            for field, value in (
                unit.metadata.get("editable_fields") or {}
            ).items()
            if isinstance(value, str) and before in value
        ]
        if not patches:
            continue
        affected_units.append({
            "unit_id": unit.unit_id,
            "disposition": "rewrite_partial",
            "reason": f"正式正文精确命中“{before}”",
            "confidence": 1.0,
            "content_patches": patches,
        })

    return {
        "analysis_mode": "deterministic_exact_replace",
        "interpreted_goal": (
            f"将正式课程正文中的“{before}”统一替换为“{after}”，"
            "不改变课程结构"
        ),
        "signal_kind": "semantic",
        "signal_confidence": 1.0,
        "hard_constraints": ["只修改逐字命中的正式正文", "不改变课程结构"],
        "soft_preferences": [],
        "protected_requirements": ["未命中内容保持不变"],
        "assumptions": [],
        "blocking_questions": (
            []
            if affected_units
            else [
                f"当前正式课程正文未找到“{before}”；"
                "请确认是否改为修改大纲、教案或讲稿范围。"
            ]
        ),
        "affected_units": affected_units,
        "structure": {
            "required": False,
            "affected_node_ids": [],
            "proposed_outline": [],
        },
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
    result["analysis_mode"] = (
        "deterministic_exact_replace"
        if result.get("analysis_mode")
        == "deterministic_exact_replace"
        else "ai_ranked"
    )
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
        content_patches: list[dict[str, Any]] = []
        for raw_patch in item.get("content_patches") or []:
            if not isinstance(raw_patch, dict):
                continue
            field = str(raw_patch.get("field") or "")
            before = str(raw_patch.get("before") or "")
            after = str(raw_patch.get("after") or "")
            if (
                field not in {"markdown", "text", "content", "title", "summary"}
                or not before
                or before == after
            ):
                continue
            content_patches.append({
                "field": field,
                "before": before,
                "after": after,
                "replace_all": bool(raw_patch.get("replace_all", True)),
            })
        affected.append({
            "unit_id": str(item["unit_id"]),
            "disposition": disposition,
            "reason": _compact(item.get("reason") or "AI 判断该单元会受到影响", 500),
            "confidence": confidence,
            "content_patches": content_patches[:40],
        })
    result["affected_units"] = affected
    structure = result.get("structure") if isinstance(result.get("structure"), dict) else {}
    structure["required"] = bool(structure.get("required") or result["signal_kind"] in {"structural", "mixed"})
    structure["affected_node_ids"] = [
        str(value) for value in structure.get("affected_node_ids") or [] if str(value)
    ][:200]
    structure["retire_node_ids"] = [
        str(value) for value in structure.get("retire_node_ids") or [] if str(value)
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
            candidate_status=(
                "ready"
                if unit.asset_type == "course_content" and item.get("content_patches")
                else "not_started"
            ),
            candidate_instruction=analysis.get("interpreted_goal") or "",
            metadata={
                "title": unit.title,
                "before_preview": _compact(unit.text, 360),
                "section_ids": unit.section_ids,
                "role": unit.role,
                "source_state": unit.source_state,
                "content_patches": deepcopy(item.get("content_patches") or []),
            },
        ))
    return result


def _content_operations(
    context: TeacherCourseChangeContext,
    analysis: dict[str, Any],
    migrations: list[CourseUnitMigration],
) -> list[CourseEvolutionOperation]:
    """Compile exact AI text patches into the existing canonical operation group."""
    units = {item.unit_id: item for item in context.units}
    analysis_by_id = {
        str(item.get("unit_id") or ""): item
        for item in analysis.get("affected_units") or []
        if isinstance(item, dict)
    }
    migration_by_unit = {
        item.source_unit_ids[0]: item
        for item in migrations
        if item.source_unit_ids
    }
    operations: list[CourseEvolutionOperation] = []
    for unit_id, item in analysis_by_id.items():
        unit = units.get(unit_id)
        migration = migration_by_unit.get(unit_id)
        raw_block = (unit.metadata.get("course_block") if unit is not None else None)
        if unit is None or migration is None or not isinstance(raw_block, dict):
            continue
        patches = item.get("content_patches") or []
        if not patches:
            continue
        before_block = CourseBlock.model_validate(raw_block)
        proposed = before_block.model_copy(deep=True)
        change_count = 0
        applied_patches: list[dict[str, Any]] = []
        for patch in patches:
            field = str(patch.get("field") or "")
            before = str(patch.get("before") or "")
            after = str(patch.get("after") or "")
            current = proposed.payload.get(field)
            if not isinstance(current, str) or not before or before not in current:
                continue
            occurrences = current.count(before)
            if bool(patch.get("replace_all", True)):
                proposed.payload[field] = current.replace(before, after)
                applied = occurrences
            else:
                proposed.payload[field] = current.replace(before, after, 1)
                applied = 1
            change_count += applied
            applied_patches.append({**patch, "occurrences": applied})
        if not change_count:
            migration.candidate_status = "failed"
            migration.metadata["candidate_error"] = "AI 修改片段未命中当前正式内容"
            continue
        operation_id = f"teacher-content-{uuid.uuid4().hex}"
        migration.candidate_status = "ready"
        migration.metadata.update({
            "operation_id": operation_id,
            "after_preview": _unit_text(proposed.payload, 360),
            "change_count": change_count,
            "applied_patches": applied_patches,
        })
        operations.append(CourseEvolutionOperation(
            operation_id=operation_id,
            operation_type="REPLACE_COURSE_BLOCK",
            target_block_id=before_block.block_id,
            target_section_id=before_block.section_id,
            scope="current",
            reason=migration.reason,
            payload={
                "expected_block_revision": before_block.internal_revision,
                "before_block": before_block.model_dump(mode="json"),
                "proposed_block": proposed.model_dump(mode="json"),
                "content_patches": applied_patches,
            },
        ))
    return operations


def _outline_rebuild_operation(
    context: TeacherCourseChangeContext,
    analysis: dict[str, Any],
    plan_id: str,
) -> list[CourseEvolutionOperation]:
    """Compile a reviewed full tree into one canonical outline operation."""
    proposed = list((analysis.get("structure") or {}).get("proposed_outline") or [])
    current = {
        str(item.get("node_id") or ""): item
        for item in context.outline
        if isinstance(item.get("section_snapshot"), dict)
    }
    if not proposed or not current:
        return []
    retire_ids = {
        str(value)
        for value in (analysis.get("structure") or {}).get("retire_node_ids") or []
        if str(value)
    }
    referenced_ids = {
        str(source_id)
        for item in proposed
        if isinstance(item, dict)
        for source_id in item.get("source_node_ids") or []
        if str(source_id)
    }
    if not referenced_ids.issubset(current) or not retire_ids.issubset(current):
        return []
    omitted_ids = set(current).difference(referenced_ids)
    # Omission alone is never interpreted as deletion. The model must name
    # every retired node explicitly so a truncated response cannot erase a tree.
    if omitted_ids != retire_ids:
        return []

    rows: list[dict[str, Any]] = []
    used_final_ids: set[str] = set()
    provisional_to_final: dict[str, str] = {}
    source_to_final: dict[str, str] = {}
    for index, item in enumerate(proposed):
        if not isinstance(item, dict):
            return []
        title = _compact(item.get("title") or item.get("node_name"), 200)
        if not title:
            return []
        source_ids = [
            str(value) for value in item.get("source_node_ids") or [] if str(value)
        ]
        stable_source = next(
            (value for value in source_ids if value not in used_final_ids),
            "",
        )
        provisional_id = str(item.get("provisional_id") or f"proposed-{index + 1}")
        final_id = stable_source or stable_hash(
            {
                "plan_id": plan_id,
                "provisional_id": provisional_id,
                "title": title,
            },
            prefix="section_",
        )
        if final_id in used_final_ids:
            return []
        used_final_ids.add(final_id)
        provisional_to_final[provisional_id] = final_id
        for source_id in source_ids:
            source_to_final.setdefault(source_id, final_id)
        rows.append({
            "item": item,
            "title": title,
            "source_ids": source_ids,
            "final_id": final_id,
            "provisional_id": provisional_id,
        })

    sections: list[CourseSection] = []
    levels: dict[str, int] = {}
    pending = list(rows)
    while pending:
        progressed = False
        for row in list(pending):
            item = row["item"]
            parent_ref = str(item.get("parent_ref") or item.get("parent_node_id") or "root")
            parent_id = (
                ""
                if parent_ref in {"", "root", "None"}
                else provisional_to_final.get(parent_ref)
                or source_to_final.get(parent_ref)
                or (parent_ref if parent_ref in used_final_ids else "")
            )
            if parent_ref not in {"", "root", "None"} and not parent_id:
                return []
            if parent_id and parent_id not in levels:
                continue
            source_ids = row["source_ids"]
            primary_snapshot = (
                current[source_ids[0]]["section_snapshot"]
                if source_ids
                else None
            )
            section = (
                CourseSection.model_validate(primary_snapshot)
                if isinstance(primary_snapshot, dict)
                else CourseSection(
                    section_id=row["final_id"],
                    title=row["title"],
                    position=len(sections),
                )
            )
            section.section_id = row["final_id"]
            section.parent_section_id = parent_id or None
            section.title = row["title"]
            section.position = len(sections)
            section.level = levels.get(parent_id, 0) + 1
            learning_focus = _compact(
                item.get("learning_focus") or item.get("learning_objective"),
                1000,
            )
            if learning_focus:
                section.learning_objective = learning_focus
            sections.append(section)
            levels[section.section_id] = section.level
            pending.remove(row)
            progressed = True
        if not progressed:
            return []

    operation_id = f"teacher-outline-{uuid.uuid4().hex}"
    return [CourseEvolutionOperation(
        operation_id=operation_id,
        operation_type="REBUILD_COURSE_OUTLINE",
        target_block_id="",
        target_section_id="",
        scope="current",
        reason=_compact(
            (analysis.get("structure") or {}).get("reason")
            or "按老师确认的新课程树重建结构并迁移稳定内容身份",
            500,
        ),
        payload={
            "outline_rebuild": {
                "sections": [item.model_dump(mode="json") for item in sections],
                "section_id_map": source_to_final,
                "retired_section_ids": sorted(retire_ids),
                "identity_mapping": [
                    {
                        "provisional_id": row["provisional_id"],
                        "final_section_id": row["final_id"],
                        "source_section_ids": row["source_ids"],
                    }
                    for row in rows
                ],
            },
        },
    )]


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
    raw_analysis = _explicit_term_replacement_analysis(
        context,
        normalized_instruction,
    )
    if raw_analysis is None and analyzer is not None:
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
    executable_operations = [
        *_content_operations(context, analysis, migrations),
        *_outline_rebuild_operation(context, analysis, change_set_id),
    ]
    planning = CourseChangePlan(
        plan_id=change_set_id,
        course_id=context.course_id,
        intent=intent,
        base_revision_vector=context.base_revision_vector,
        structural_operations=structure_operations,
        unit_migrations=migrations,
        status=(
            "needs_clarification"
            if questions
            else "candidate_ready"
            if executable_operations
            else "impact_ready"
        ),
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
            "operation_id": str(item.metadata.get("operation_id") or ""),
            "after_preview": str(item.metadata.get("after_preview") or ""),
            "change_count": int(item.metadata.get("change_count") or 0),
            "candidate_error": str(item.metadata.get("candidate_error") or ""),
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
        allowed_scopes=["current"] if executable_operations else [],
        operations=executable_operations,
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
            "current_outline": [
                {
                    key: value
                    for key, value in item.items()
                    if key != "section_snapshot"
                }
                for item in context.outline
            ],
            "proposed_outline": (analysis.get("structure") or {}).get("proposed_outline") or [],
            "candidate_bundle": {
                "operation_count": len(executable_operations),
                "operation_ids": [item.operation_id for item in executable_operations],
                "content_operation_count": sum(
                    item.operation_type == "REPLACE_COURSE_BLOCK"
                    for item in executable_operations
                ),
                "structure_operation_count": sum(
                    item.operation_type in {"RESEQUENCE_COURSE_PATH", "REBUILD_COURSE_OUTLINE"}
                    for item in executable_operations
                ),
            } if executable_operations else {},
            "application_capability": (
                "course_document_operation_group"
                if executable_operations
                else "impact_review"
            ),
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
        selected_operation_ids = [
            str(item.metadata.get("operation_id") or "")
            for item in plan.teacher_change_planning.unit_migrations
            if item.migration_id in selected and item.metadata.get("operation_id")
        ]
        structure_operation_ids = [
            item.operation_id
            for item in plan.operations
            if item.operation_type in {"RESEQUENCE_COURSE_PATH", "REBUILD_COURSE_OUTLINE"}
        ]
        if confirm_structure:
            selected_operation_ids.extend(structure_operation_ids)
        selected_operation_ids = list(dict.fromkeys(selected_operation_ids))
        plan.impact_summary["scope_review"] = {
            "selected_migration_ids": selected,
            "excluded_migration_ids": sorted(known.difference(selected)),
            "selected_operation_ids": selected_operation_ids,
            "reviewed_at": timestamp,
            "formal_content_changed": False,
        }
        plan.selected_operation_ids = selected_operation_ids
        plan.excluded_operation_ids = [
            item.operation_id
            for item in plan.operations
            if item.operation_id not in selected_operation_ids
        ]
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
