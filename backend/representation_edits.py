"""Classify representation edits and keep semantic ownership in the course."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re
from typing import Any, Literal

from course_document import stable_hash
from slide_deck import validate_slide_deck
from teaching_representations import (
    TeachingRepresentation,
    TeachingRepresentationRegistry,
    TeachingRepresentationRepository,
    TeachingRepresentationSpec,
)

EditClassification = Literal["presentation", "equivalent_semantic", "semantic", "ambiguous"]
COURSE_TEXT_PATCH_SCHEMA = "course_text_patch_v1"

_TEACHING_DIMENSIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "conceptual_understanding",
        "概念理解",
        ("理解", "解释", "为什么", "含义", "原理", "关系", "本质", "explain", "why", "meaning"),
    ),
    (
        "procedural_fluency",
        "计算技能",
        ("计算", "规则", "步骤", "求解", "操作", "套用", "calculate", "procedure", "compute"),
    ),
    (
        "transfer_application",
        "迁移应用",
        ("应用", "迁移", "建模", "解决实际", "新情境", "apply", "transfer", "model"),
    ),
    (
        "evaluation_creation",
        "评价创造",
        ("评价", "比较方案", "设计", "证明", "创造", "evaluate", "design", "prove"),
    ),
)


def classify_representation_edit(
    *,
    field: str,
    before: Any,
    after: Any,
    semantic_intent: bool | None = None,
) -> dict[str, Any]:
    before_text = str(before or "").strip()
    after_text = str(after or "").strip()
    semantic_change = _teaching_dimension_change(before_text, after_text)
    if before_text == after_text:
        return {"classification": "equivalent_semantic", "reason": "内容没有发生语义变化"}
    if field in {"theme", "layout", "color", "font_size", "animation_speed", "position"}:
        return {"classification": "presentation", "reason": "修改只涉及视觉或播放表现"}
    if semantic_intent is True:
        return {
            "classification": "semantic",
            "reason": (
                semantic_change["summary"]
                if semantic_change
                else "用户明确要求改变课程含义"
            ),
            **({"semantic_change": semantic_change} if semantic_change else {}),
        }
    if semantic_intent is False:
        return {"classification": "equivalent_semantic", "reason": "用户明确要求只调整当前表达"}
    normalized_before = _normalize(before_text)
    normalized_after = _normalize(after_text)
    if normalized_before == normalized_after:
        return {"classification": "equivalent_semantic", "reason": "仅标点、空白或格式发生变化"}
    if field == "title" and _token_overlap(normalized_before, normalized_after) >= 0.72:
        return {"classification": "equivalent_semantic", "reason": "标题保持同一核心概念"}
    if semantic_change:
        return {
            "classification": "semantic",
            "reason": semantic_change["summary"],
            "semantic_change": semantic_change,
        }
    if field in {"bullets", "speaker_notes", "body", "example", "prompt", "title", "key_message", "subtitle"}:
        return {"classification": "ambiguous", "reason": "该字段承载教学含义，需要用户决定是否联动课程"}
    return {"classification": "ambiguous", "reason": "无法仅靠确定性规则确认语义边界"}


def representation_edit_impact(
    registry: TeachingRepresentationRegistry,
    spec: TeachingRepresentationSpec,
    *,
    unit_id: str,
    field: str | None = None,
) -> dict[str, Any]:
    bindings = spec.unit_bindings.get(unit_id) or []
    all_source_keys = {key for binding in bindings for key in binding.source_revisions}
    preferred_prefixes = {
        "body": ("block:",),
        "markdown": ("block:",),
        "example": ("block:",),
        "prompt": ("practice:",),
        "learning_objective": ("objective:",),
        "key_message": ("objective:",),
    }.get(str(field or ""))
    preferred_source_keys = (
        {
            key
            for key in all_source_keys
            if preferred_prefixes and key.startswith(preferred_prefixes)
        }
        if preferred_prefixes
        else set()
    )
    # A paragraph edit follows the paragraph's block revision, while an
    # objective edit follows the objective revision.  Falling back to all
    # bindings preserves compatibility for fields without a narrower semantic
    # owner.
    source_keys = sorted(preferred_source_keys or all_source_keys)
    block_ids = sorted({binding.block_id for binding in bindings if binding.block_id})
    section_ids = sorted({binding.section_id for binding in bindings if binding.section_id})
    affected: list[dict[str, Any]] = []
    change_items: list[dict[str, Any]] = []
    protected_items: list[dict[str, Any]] = []
    total_unit_count = 0
    for representation in registry.representations:
        representation_spec = next((
            item for item in registry.specs if item.spec_id == representation.spec_id
        ), None)
        if representation_spec is None:
            continue
        units = _representation_units(representation_spec)
        units_by_id = {
            str(item.get("unit_id") or ""): item
            for item in units
            if item.get("unit_id")
        }
        all_unit_ids = sorted(representation_spec.unit_bindings)
        total_unit_count += len(all_unit_ids)
        unit_ids = sorted({
            candidate_unit_id
            for candidate_unit_id, candidate_bindings in representation_spec.unit_bindings.items()
            if any(
                set(binding.source_revisions).intersection(source_keys)
                for binding in candidate_bindings
            )
        })
        if unit_ids:
            unit_summaries = [
                _impact_unit_summary(
                    representation.representation_type,
                    units_by_id.get(candidate_unit_id) or {},
                    candidate_unit_id,
                    origin=(
                        representation.representation_id
                        == next((
                            item.representation_id
                            for item in registry.representations
                            if item.spec_id == spec.spec_id
                        ), "")
                        and candidate_unit_id == unit_id
                    ),
                )
                for candidate_unit_id in unit_ids
            ]
            change_items.extend(unit_summaries)
            affected.append({
                "representation_id": representation.representation_id,
                "representation_type": representation.representation_type,
                "unit_ids": unit_ids,
                "units": unit_summaries,
                "unaffected_unit_ids": [
                    candidate_unit_id
                    for candidate_unit_id in all_unit_ids
                    if candidate_unit_id not in unit_ids
                ],
            })
        for candidate_unit_id in all_unit_ids:
            if candidate_unit_id in unit_ids or len(protected_items) >= 6:
                continue
            candidate = units_by_id.get(candidate_unit_id) or {}
            protected_items.append({
                "representation_type": representation.representation_type,
                "unit_id": candidate_unit_id,
                "label": _unit_label(representation.representation_type, candidate, candidate_unit_id),
                "reason": "与本次修改没有共同来源依赖，保持当前版本",
            })
    affected_unit_count = sum(len(item["unit_ids"]) for item in affected)
    return {
        "source_keys": source_keys,
        "block_ids": block_ids,
        "section_ids": section_ids,
        "affected_representations": affected,
        "change_items": change_items,
        "protected_items": protected_items,
        "affected_unit_count": affected_unit_count,
        "unaffected_unit_count": max(0, total_unit_count - affected_unit_count),
        "total_unit_count": total_unit_count,
        "protected": ["无来源关系的课程块", "其他课程", "历史作答", "个人笔记原文"],
    }


def build_course_text_patch(
    block_payload: dict[str, Any],
    *,
    before: str,
    after: str,
) -> dict[str, Any]:
    """把派生材料中的小改动定位为唯一、可冲突检测的课程文本补丁。"""
    before_text = str(before or "")
    after_text = str(after or "")
    if not before_text:
        raise ValueError("Semantic edit requires non-empty source text")

    selected_field = ""
    selected_content = ""
    selected_start = -1
    for field_group in (
        ("markdown", "text", "content"),
        ("title", "summary"),
    ):
        matches: list[tuple[str, str, int]] = []
        for field in field_group:
            content = block_payload.get(field)
            if not isinstance(content, str):
                continue
            start = content.find(before_text)
            if start >= 0:
                matches.append((field, content, start))
        if matches:
            if len(matches) != 1:
                raise ValueError("Semantic edit matches multiple course fields")
            selected_field, selected_content, selected_start = matches[0]
            break
    if not selected_field:
        raise ValueError("Semantic edit source text is not present in the course block")
    if selected_content.find(before_text, selected_start + 1) >= 0:
        raise ValueError("Semantic edit source text occurs more than once in the course block")

    selected_end = selected_start + len(before_text)
    prefix_context = selected_content[max(0, selected_start - 48):selected_start]
    suffix_context = selected_content[selected_end:selected_end + 48]
    return {
        "schema_version": COURSE_TEXT_PATCH_SCHEMA,
        "field": selected_field,
        "start": selected_start,
        "end": selected_end,
        "before": before_text,
        "after": after_text,
        "prefix_context": prefix_context,
        "suffix_context": suffix_context,
        "line_start": selected_content.count("\n", 0, selected_start) + 1,
        "line_end": selected_content.count("\n", 0, selected_end) + 1,
    }


def apply_course_text_patch_preview(
    block_payload: dict[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any]:
    """在不写入课程的情况下生成补丁后的块 payload，供审阅差异使用。"""
    field = str(patch.get("field") or "")
    current = block_payload.get(field)
    start = patch.get("start")
    end = patch.get("end")
    before = str(patch.get("before") or "")
    if (
        not isinstance(current, str)
        or not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
        or start < 0
        or end < start
        or end > len(current)
        or current[start:end] != before
    ):
        raise ValueError("Course text patch no longer matches its preview source")
    updated = deepcopy(block_payload)
    updated[field] = f"{current[:start]}{str(patch.get('after') or '')}{current[end:]}"
    return updated


def _representation_units(spec: TeachingRepresentationSpec) -> list[dict[str, Any]]:
    content = spec.payload.get("content") or {}
    value = content.get("units") or content.get("slides") or content.get("sections") or []
    return [item for item in value if isinstance(item, dict)]


def _impact_unit_summary(
    representation_type: str,
    unit: dict[str, Any],
    unit_id: str,
    *,
    origin: bool,
) -> dict[str, Any]:
    purpose = str(unit.get("slide_purpose") or "")
    layout = str(unit.get("layout") or "")
    role, reason = _impact_role(representation_type, purpose=purpose, layout=layout)
    return {
        "representation_type": representation_type,
        "unit_id": unit_id,
        "label": _unit_label(representation_type, unit, unit_id),
        "role": role,
        "reason": reason,
        "section_id": str(unit.get("section_id") or ""),
        "origin": origin,
    }


def _impact_role(
    representation_type: str,
    *,
    purpose: str,
    layout: str,
) -> tuple[str, str]:
    if representation_type == "outline":
        return "目标定位", "课程大纲中的本节目标需要更新"
    if representation_type == "lesson_plan":
        return "教案重点", "课堂重点、建构活动与检查方式需要对齐新目标"
    if representation_type == "handout":
        return "讲义解释", "学习引导需要从完成步骤转向说明概念与依据"
    if representation_type == "practice_sheet":
        return "理解检查", "检查任务需要验证是否能解释，而不只判断答案"
    if representation_type == "slide_deck":
        if purpose == "learning_objective" or layout == "objective":
            return "PPT 学习目标", "当前目标页是本次语义修改的起点"
        if purpose in {"example", "application", "transfer"}:
            return "例题与迁移", "例题需要补充为什么这样做以及如何迁移"
        if purpose in {"mastery_check", "activity", "checkpoint"} or layout == "practice":
            return "课堂理解检查", "课堂检查需要观察解释与推理，而不只计算结果"
        if purpose in {"reasoning", "concept_and_reasoning"} or layout in {"process", "comparison"}:
            return "推理与图解", "推理过程需要突出关系、依据和运算顺序"
        if purpose in {"misconception", "counterexample"} or layout == "misconception":
            return "易错辨析", "错误分析需要指向概念混淆及其纠正依据"
        return "概念讲解", "核心页面需要增加与新教学目标的对齐提示"
    return "相关内容", "该内容与本次修改共享同一课程来源"


def _unit_label(
    representation_type: str,
    unit: dict[str, Any],
    unit_id: str,
) -> str:
    title = str(
        unit.get("title")
        or unit.get("section_title")
        or unit.get("learning_objective")
        or unit.get("prompt")
        or ""
    ).strip()
    prefix = {
        "outline": "大纲",
        "lesson_plan": "教案",
        "handout": "讲义",
        "practice_sheet": "检查",
        "slide_deck": "PPT",
    }.get(representation_type, representation_type)
    return f"{prefix} · {title[:34]}" if title else f"{prefix} · {unit_id}"


def apply_representation_only_edit(
    repository: TeachingRepresentationRepository,
    registry: TeachingRepresentationRegistry,
    representation: TeachingRepresentation,
    spec: TeachingRepresentationSpec,
    *,
    unit_id: str,
    field: str,
    after: Any,
) -> TeachingRepresentationRegistry:
    payload = deepcopy(spec.payload)
    content = payload.get("content") or {}
    units_key = next((key for key in ("units", "slides", "sections") if isinstance(content.get(key), list)), "")
    if not units_key:
        raise ValueError("Teaching representation does not contain editable units")
    unit = next((item for item in content[units_key] if str(item.get("unit_id") or "") == unit_id), None)
    if unit is None:
        raise KeyError(unit_id)
    before = deepcopy(unit.get(field))
    unit[field] = deepcopy(after)
    if spec.representation_type == "slide_deck":
        overrides = content.setdefault("presentation_overrides", {})
        unit_overrides = overrides.setdefault(unit_id, {})
        existing = unit_overrides.get(field) if isinstance(unit_overrides.get(field), dict) else {}
        base_value = existing.get("base_value", before)
        if after == base_value:
            unit_overrides.pop(field, None)
            if not unit_overrides:
                overrides.pop(unit_id, None)
        else:
            unit_overrides[field] = {
                "value": deepcopy(after),
                "base_value": deepcopy(base_value),
                "source_revision_vector": {
                    source_key: revision
                    for binding in spec.unit_bindings.get(unit_id) or []
                    for source_key, revision in binding.source_revisions.items()
                },
            }
        quality = validate_slide_deck(content)
        if not quality["passed"]:
            codes = ", ".join(
                issue["code"] for issue in quality["issues"]
                if issue["severity"] == "critical"
            )
            raise ValueError(f"Slide edit violates the quality gate: {codes}")
        content["quality_summary"] = {
            "passed": quality["passed"],
            "score": quality["score"],
            "semantic_issue_count": len(quality["semantic"]["issues"]),
            "visual_issue_count": len(quality["visual"]["issues"]),
        }
    now = datetime.now(timezone.utc).isoformat()
    spec_revision = stable_hash(payload, prefix="tsr_")
    edited_spec = TeachingRepresentationSpec(
        spec_id=stable_hash({
            "course_id": spec.course_id,
            "representation_type": spec.representation_type,
            "source_bindings": [item.model_dump(mode="json") for item in spec.source_bindings],
            "payload": payload,
        }, prefix="trs_"),
        course_id=spec.course_id,
        representation_type=spec.representation_type,
        source_bindings=spec.source_bindings,
        unit_bindings=spec.unit_bindings,
        payload=payload,
        revision=spec_revision,
        created_at=now,
        updated_at=now,
    )
    repository.register_spec(edited_spec)
    edited_representation = representation.model_copy(deep=True)
    edited_representation.spec_id = edited_spec.spec_id
    edited_representation.semantic_fingerprint = stable_hash(content, prefix="sem_")
    edited_representation.render_fingerprint = stable_hash({
        "spec_revision": spec_revision,
        "renderer": "structured_json_v2",
    }, prefix="rnd_")
    edited_representation.revision = stable_hash({
        "spec_revision": spec_revision,
        "source_revision_vector": edited_representation.source_revision_vector,
    }, prefix="rpr_")
    edited_representation.updated_at = now
    return repository.register_representation(edited_representation)


def _normalize(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", value).lower()


def _teaching_dimension_change(before: str, after: str) -> dict[str, Any] | None:
    before_dimension = _teaching_dimension(before)
    after_dimension = _teaching_dimension(after)
    if before_dimension is None or after_dimension is None:
        return None
    if before_dimension[0] == after_dimension[0]:
        return None
    implications = {
        "conceptual_understanding": [
            "讲解增加概念含义、关系与成立依据",
            "例题不仅给步骤，还要解释为什么这样做",
            "理解检查加入说明、辨析与运算顺序",
        ],
        "procedural_fluency": [
            "讲解明确规则、步骤与关键检查点",
            "例题突出稳定执行方法",
            "理解检查加入独立计算与过程校验",
        ],
        "transfer_application": [
            "讲解补充适用条件与情境判断",
            "例题加入新情境迁移",
            "理解检查要求选择并解释方法",
        ],
        "evaluation_creation": [
            "讲解呈现多种方案与判断标准",
            "例题加入比较、证明或设计",
            "理解检查要求形成并捍卫自己的方案",
        ],
    }.get(after_dimension[0], [])
    interpretation = (
        "这不只是措辞调整：课堂重心从正确执行步骤，升级为解释概念关系、"
        "成立依据与运算顺序。"
        if before_dimension[0] == "procedural_fluency"
        and after_dimension[0] == "conceptual_understanding"
        else f"这次修改改变了教学证据：课堂需要证明学生已经达到「{after_dimension[1]}」，"
        f"而不再只满足「{before_dimension[1]}」。"
    )
    return {
        "from_dimension": before_dimension[0],
        "from_label": before_dimension[1],
        "to_dimension": after_dimension[0],
        "to_label": after_dimension[1],
        "summary": f"教学目标从「{before_dimension[1]}」转向「{after_dimension[1]}」",
        "interpretation": interpretation,
        "instructional_implications": implications,
    }


def _teaching_dimension(value: str) -> tuple[str, str] | None:
    normalized = value.lower()
    scored = [
        (sum(marker in normalized for marker in markers), key, label)
        for key, label, markers in _TEACHING_DIMENSIONS
    ]
    score, key, label = max(scored, default=(0, "", ""))
    return (key, label) if score else None


def _token_overlap(before: str, after: str) -> float:
    before_tokens = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]+", before))
    after_tokens = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]+", after))
    if not before_tokens or not after_tokens:
        return 0.0
    return len(before_tokens & after_tokens) / len(before_tokens | after_tokens)


__all__ = [
    "COURSE_TEXT_PATCH_SCHEMA",
    "apply_representation_only_edit",
    "apply_course_text_patch_preview",
    "build_course_text_patch",
    "classify_representation_edit",
    "representation_edit_impact",
]
