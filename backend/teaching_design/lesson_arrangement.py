"""教师可见的本讲课型与教学块编排合同。

内部学科画像和细课型只负责给出建议；本模块把它们投影为教师能直接调整的
七类课型和有序教学块，并把确认结果重新编译给成熟的 V3 教案引擎。
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any

from course_pedagogy import (
    MODULES,
    attach_module_plans_to_plan,
    coerce_persisted_profile,
    module_block_role,
)
from lesson_identity import lesson_chapter_index, resolve_lesson_chapter
from .compiler import (
    LESSON_TYPE_CONTRACTS,
    compile_lesson_semantics,
    compile_teaching_block_contract,
    lesson_phase,
    order_teaching_blocks,
    recommend_lesson_type,
    resolve_course_teaching_type,
)


SCHEMA_VERSION = "teacher_lesson_arrangement_v1"
# 保留现有外部结构版本；类型内容由统一语义库投影，避免第二套课型注册表。
LESSON_TYPES: dict[str, dict[str, str]] = {
    key: {"label": value["label"], "purpose": value["purpose"]}
    for key, value in LESSON_TYPE_CONTRACTS.items()
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _stable_id(*parts: str, prefix: str) -> str:
    digest = hashlib.sha256("\u241f".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _course_plan(course_data: dict[str, Any]) -> dict[str, Any]:
    existing = course_data.get("course_plan") or course_data.get("course_outline")
    if isinstance(existing, dict) and existing.get("chapters"):
        return deepcopy(existing)

    nodes = [item for item in course_data.get("nodes") or [] if isinstance(item, dict)]
    chapters = []
    for node in nodes:
        node_id = _text(node.get("node_id"))
        if not node_id or not (
            int(node.get("node_level") or 0) == 1
            or _text(node.get("parent_node_id")) == "root"
        ):
            continue
        sections = []
        for child in nodes:
            if _text(child.get("parent_node_id")) != node_id:
                continue
            sections.append({
                "node_id": _text(child.get("node_id")),
                "title": _text(child.get("node_name")),
                "learning_objective": _text(
                    child.get("learning_objective")
                    or child.get("learning_goal")
                    or child.get("node_goal")
                ),
                "key_points": deepcopy(child.get("key_points") or []),
            })
        if sections:
            chapters.append({
                "node_id": node_id,
                "title": _text(node.get("node_name")),
                "sections": sections,
            })
    return {"chapters": chapters}


def _lesson_chapter(plan: dict[str, Any], lesson_unit_id: str) -> dict[str, Any] | None:
    return resolve_lesson_chapter(plan, lesson_unit_id)


def _lesson_type(archetype_ids: list[str], module_ids: list[str]) -> str:
    archetype_tokens = {
        token
        for value in archetype_ids
        for token in re.split(r"[^a-z0-9]+", value.lower())
        if token
    }
    module_tokens = {
        token
        for value in module_ids
        for token in re.split(r"[^a-z0-9]+", value.lower())
        if token
    }
    tokens = {
        token
        for value in [*archetype_ids, *module_ids]
        for token in re.split(r"[^a-z0-9]+", value.lower())
        if token
    }
    if tokens & {"project", "workshop", "studio"}:
        return "project_workshop"
    if archetype_tokens & {"experiment", "inquiry", "investigation"}:
        return "experiment_inquiry"
    if archetype_tokens & {"review", "assessment", "retrieval", "exam", "diagnosis", "diagnostic"}:
        return "review_assessment"
    if archetype_tokens & {"case", "discussion", "debate", "decision"}:
        return "case_discussion"
    practical = bool(tokens & {
        "practice", "procedure", "operation", "coding", "debug", "debugging", "simulation",
        "roleplay", "task", "build", "runnable", "testing", "refactoring", "modification",
    })
    theoretical = bool(tokens & {
        "concept", "principle", "theory", "reason", "reasoning", "proof", "model",
        "explanation", "mechanism", "architecture",
    })
    if module_tokens & {"retrieval", "assessment"} and not practical:
        return "review_assessment"
    if practical and theoretical:
        return "theory_practice"
    if practical:
        return "practice"
    return "theory"


def _course_teaching_type(course_data: dict[str, Any]) -> str:
    brief = course_data.get("course_generation_brief") or {}
    request = course_data.get("generation_request") or {}
    value = (
        brief.get("course_teaching_type")
        or request.get("course_teaching_type")
        or course_data.get("course_teaching_type")
    )
    resolved, _ = resolve_course_teaching_type(
        value,
        learning_purpose=(brief.get("learning_purpose") or request.get("learning_purpose")),
        legacy_course_type=(brief.get("course_type") or request.get("course_type")),
        composition_style=(
            (course_data.get("course_composition_profile") or {}).get("style")
            or request.get("composition_style")
        ),
    )
    return resolved


def _course_semantic_inputs(course_data: dict[str, Any]) -> dict[str, str]:
    brief = course_data.get("course_generation_brief") or {}
    request = course_data.get("generation_request") or {}
    return {
        "learning_purpose": _text(
            brief.get("learning_purpose")
            or request.get("learning_purpose")
            or course_data.get("learning_purpose")
        ),
        "subject_type": _text(
            brief.get("subject_type")
            or request.get("subject_type")
            or request.get("pedagogy_mode")
            or course_data.get("subject_type")
            or "auto"
        ),
        "discipline_hint": _text(
            brief.get("subject")
            or request.get("subject")
            or request.get("topic")
            or course_data.get("course_name")
        ),
    }


def _classroom_constraints(course_data: dict[str, Any], duration: int) -> dict[str, Any]:
    brief = course_data.get("teacher_course_brief") or {}
    request = course_data.get("generation_request") or {}
    raw = {
        **(request.get("classroom_constraints") or {}),
        **(brief.get("classroom_constraints") or {}),
    }
    raw["lesson_duration_minutes"] = duration
    for key in (
        "class_size", "delivery_mode", "grouping", "equipment",
        "safety_and_access", "assessment_pressure",
    ):
        if key not in raw:
            value = brief.get(key) or request.get(key)
            if value not in (None, "", [], {}):
                raw[key] = value
    return raw


def _allocate_minutes(total: int, count: int) -> list[int]:
    if count <= 0:
        return []
    safe_total = max(count, int(total or 45))
    base, remainder = divmod(safe_total, count)
    return [base + (1 if index < remainder else 0) for index in range(count)]


def _compact_large_legacy_lesson(
    blocks: list[dict[str, Any]],
    sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep historical chapter-shaped lessons editable instead of rendering dozens of rows.

    Current historical courses may expose a whole chapter with many second-level nodes as
    one LessonUnit. Until the hierarchy migration is complete, each such node becomes one
    visible block whose summary retains the internal module sequence.
    """
    if len(sections) <= 4:
        return blocks
    grouped: dict[str, list[dict[str, Any]]] = {}
    for block in blocks:
        grouped.setdefault(_text(block.get("section_node_id")), []).append(block)
    compacted = []
    for section in sections:
        section_id = _text(section.get("node_id"))
        items = grouped.get(section_id) or []
        if not items:
            continue
        first = items[0]
        names = [_text(item.get("name")) for item in items if _text(item.get("name"))]
        outputs = list(dict.fromkeys(
            _text(item.get("expected_output") or item.get("purpose"))
            for item in items
            if _text(item.get("expected_output") or item.get("purpose"))
        ))
        compacted.append({
            **first,
            "block_id": _stable_id(section_id, "section_sequence", prefix="lab"),
            "module_id": "teacher_section_sequence",
            "name": "本节完整教学",
            "role": "instruction",
            "purpose": "在当前小节内完成讲解、活动与检查。",
            "content_summary": f"按“{' → '.join(names)}”的顺序组织本节教学。",
            "expected_output": "；".join(outputs),
        })
    return compacted


def recommend_lesson_arrangement(
    course_data: dict[str, Any],
    lesson_unit_id: str,
    *,
    source_outline_revision_id: str = "",
) -> dict[str, Any]:
    plan = _course_plan(course_data)
    chapter = _lesson_chapter(plan, lesson_unit_id)
    if not isinstance(chapter, dict):
        return {
            "schema_version": SCHEMA_VERSION,
            "revision_id": "",
            "lesson_unit_id": lesson_unit_id,
            "source_outline_revision_id": source_outline_revision_id,
            "lesson_type": "theory",
            "lesson_type_label": LESSON_TYPES["theory"]["label"],
            "blocks": [],
            "status": "suggested",
            "confirmed": False,
            "source_state": "current",
        }

    scoped = deepcopy(plan)
    scoped["chapters"] = [deepcopy(chapter)]
    compiled = attach_module_plans_to_plan(scoped, coerce_persisted_profile(course_data))
    compiled_chapter = _lesson_chapter(compiled, lesson_unit_id) or {"sections": []}
    sections = [item for item in compiled_chapter.get("sections") or [] if isinstance(item, dict)]
    nodes_by_id = {
        _text(item.get("node_id")): item
        for item in course_data.get("nodes") or []
        if isinstance(item, dict) and _text(item.get("node_id"))
    }
    raw_blocks: list[dict[str, Any]] = []
    archetype_ids: list[str] = []
    module_ids: list[str] = []
    for section in sections:
        section_id = _text(section.get("node_id"))
        archetype = section.get("lesson_archetype") or {}
        archetype_ids.append(_text(archetype.get("archetype_id")))
        for index, module in enumerate(section.get("module_plan") or [], start=1):
            if not isinstance(module, dict) or not _text(module.get("module_id")):
                continue
            module_id = _text(module.get("module_id"))
            module_ids.append(module_id)
            raw_blocks.append({
                "block_id": _stable_id(section_id, module_id, str(index), prefix="lab"),
                "module_id": module_id,
                "section_node_id": section_id,
                "section_title": _text(
                    (nodes_by_id.get(section_id) or {}).get("node_name")
                    or section.get("title")
                    or section_id
                ),
                "name": _text(module.get("label") or module_id),
                "role": _text(module.get("block_role") or module_block_role(module_id)),
                "purpose": _text(module.get("output_contract")),
                "content_summary": _text(module.get("prompt_instruction") or module.get("output_contract")),
                "teacher_activity": "",
                "student_activity": "",
                "expected_output": _text(module.get("output_contract")),
                "required": bool(module.get("required", True)),
            })
    duration = int(
        (next((item for item in course_data.get("nodes") or [] if _text(item.get("node_id")) == lesson_unit_id), {}) or {}).get("duration_minutes")
        or (course_data.get("teacher_course_brief") or {}).get("lesson_duration_minutes")
        or 45
    )
    raw_blocks = _compact_large_legacy_lesson(raw_blocks, sections)
    for block, minutes in zip(raw_blocks, _allocate_minutes(duration, len(raw_blocks))):
        block["planned_minutes"] = minutes
    legacy_lesson_type = _lesson_type(archetype_ids, module_ids)
    chapters = [item for item in plan.get("chapters") or [] if isinstance(item, dict)]
    chapter_index = lesson_chapter_index(plan, lesson_unit_id) or 0
    course_teaching_type = _course_teaching_type(course_data)
    phase = lesson_phase(chapter_index, len(chapters))
    lesson_type = recommend_lesson_type(
        course_teaching_type,
        phase=phase,
        legacy_candidate=legacy_lesson_type,
    )
    raw_blocks = order_teaching_blocks(raw_blocks, lesson_type)
    semantic_inputs = _course_semantic_inputs(course_data)
    lesson_goal = _text(
        chapter.get("learning_objective")
        or chapter.get("learning_goal")
        or chapter.get("title")
    )
    lesson_semantics = compile_lesson_semantics(
        learning_purpose=semantic_inputs["learning_purpose"],
        subject_type=semantic_inputs["subject_type"],
        course_teaching_type=course_teaching_type,
        lesson_type=lesson_type,
        phase=phase,
        lesson_goal=lesson_goal,
        classroom_constraints=_classroom_constraints(course_data, duration),
        legacy_candidate=legacy_lesson_type,
        discipline_hint=semantic_inputs["discipline_hint"],
    )
    raw_blocks = [
        compile_teaching_block_contract(
            block,
            lesson_type=lesson_type,
            subject_standard_pack=(lesson_semantics.get("course_semantics") or {}).get(
                "subject_standard_pack"
            ),
        )
        for block in raw_blocks
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "teaching_semantics_version": lesson_semantics["teaching_semantics_version"],
        "revision_id": "",
        "lesson_unit_id": lesson_unit_id,
        "source_outline_revision_id": source_outline_revision_id,
        "lesson_type": lesson_type,
        "lesson_type_label": LESSON_TYPES[lesson_type]["label"],
        "lesson_type_recommendation_reason": lesson_semantics["lesson_type_recommendation_reason"],
        "lesson_type_contract": lesson_semantics["lesson_type_contract"],
        "required_learning_cycle": lesson_semantics["required_learning_cycle"],
        "classroom_constraints": lesson_semantics["classroom_constraints"],
        "quality_rules": lesson_semantics["quality_rules"],
        "subject_standard_pack": lesson_semantics["course_semantics"]["subject_standard_pack"],
        "course_teaching_type": course_teaching_type,
        "lesson_phase": phase,
        "blocks": raw_blocks,
        "status": "suggested",
        "confirmed": False,
        "source_state": "current",
    }


def normalize_lesson_arrangement(
    value: dict[str, Any],
    *,
    lesson_unit_id: str,
    source_outline_revision_id: str,
) -> dict[str, Any]:
    lesson_type = _text(value.get("lesson_type"))
    if lesson_type not in LESSON_TYPES:
        lesson_type = "theory"
    blocks = []
    for index, raw in enumerate(value.get("blocks") or [], start=1):
        if not isinstance(raw, dict):
            continue
        name = _text(raw.get("name") or raw.get("title"))
        section_id = _text(raw.get("section_node_id"))
        module_id = _text(raw.get("module_id")) or _stable_id(name, section_id, prefix="teacher-custom")
        try:
            planned_minutes = max(1, min(240, int(raw.get("planned_minutes") or 1)))
        except (TypeError, ValueError):
            planned_minutes = 1
        blocks.append(compile_teaching_block_contract({
            "block_id": _text(raw.get("block_id")) or _stable_id(section_id, module_id, str(index), prefix="lab"),
            "module_id": module_id,
            "section_node_id": section_id,
            "section_title": _text(raw.get("section_title")),
            "name": name,
            "role": _text(raw.get("role")) or module_block_role(module_id),
            "purpose": _text(raw.get("purpose")),
            "content_summary": _text(raw.get("content_summary")),
            "planned_minutes": planned_minutes,
            "teacher_activity": _text(raw.get("teacher_activity")),
            "student_activity": _text(raw.get("student_activity")),
            "expected_output": _text(raw.get("expected_output")),
            "check_method": _text(raw.get("check_method")),
            "feedback_strategy": _text(raw.get("feedback_strategy")),
            "adaptation_options": deepcopy(raw.get("adaptation_options") or []),
            "resource_refs": deepcopy(raw.get("resource_refs") or []),
            "tools": deepcopy(raw.get("tools") or []),
            "engagement_mode": _text(raw.get("engagement_mode")),
            "access_support": _text(raw.get("access_support")),
            "grouping": _text(raw.get("grouping")),
            "transition": _text(raw.get("transition")),
            "safety_boundary": _text(raw.get("safety_boundary")),
            "required": bool(raw.get("required", True)),
        }, lesson_type=lesson_type))
    return {
        "schema_version": SCHEMA_VERSION,
        "teaching_semantics_version": _text(value.get("teaching_semantics_version")),
        "revision_id": _text(value.get("revision_id")),
        "lesson_unit_id": lesson_unit_id,
        "source_outline_revision_id": source_outline_revision_id,
        "lesson_type": lesson_type,
        "lesson_type_label": LESSON_TYPES[lesson_type]["label"],
        "lesson_type_recommendation_reason": _text(value.get("lesson_type_recommendation_reason")),
        "lesson_type_contract": deepcopy(
            value.get("lesson_type_contract") or LESSON_TYPE_CONTRACTS[lesson_type]
        ),
        "required_learning_cycle": deepcopy(
            value.get("required_learning_cycle")
            or LESSON_TYPE_CONTRACTS[lesson_type]["learning_cycle"]
        ),
        "classroom_constraints": deepcopy(value.get("classroom_constraints") or {}),
        "quality_rules": deepcopy(value.get("quality_rules") or []),
        "blocks": order_teaching_blocks(blocks, lesson_type),
    }


def validate_lesson_arrangement(
    value: dict[str, Any],
    *,
    expected_section_ids: list[str],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if _text(value.get("lesson_type")) not in LESSON_TYPES:
        issues.append({"code": "lesson_arrangement:lesson_type", "message": "请选择有效的本讲课型。"})
    blocks = [item for item in value.get("blocks") or [] if isinstance(item, dict)]
    if not blocks:
        issues.append({"code": "lesson_arrangement:blocks_empty", "message": "本讲至少需要一个教学块。"})
    ids = [_text(item.get("block_id")) for item in blocks]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        issues.append({"code": "lesson_arrangement:block_identity", "message": "教学块标识缺失或重复。"})
    expected = set(expected_section_ids)
    actual_sections = {_text(item.get("section_node_id")) for item in blocks}
    if actual_sections - expected:
        issues.append({"code": "lesson_arrangement:section_scope", "message": "教学块引用了本讲以外的小节。"})
    missing_sections = [section_id for section_id in expected_section_ids if section_id not in actual_sections]
    if missing_sections:
        issues.append({"code": "lesson_arrangement:section_coverage", "message": "本讲每个小节至少需要一个教学块。"})
    if any(not _text(item.get("name")) for item in blocks):
        issues.append({"code": "lesson_arrangement:block_name", "message": "教学块名称不能为空。"})
    if any(int(item.get("planned_minutes") or 0) <= 0 for item in blocks):
        issues.append({"code": "lesson_arrangement:block_minutes", "message": "每个教学块都需要有效时长。"})
    if any(_text(item.get("engagement_mode")) not in {"passive", "active", "constructive", "interactive"} for item in blocks):
        issues.append({"code": "lesson_arrangement:engagement_mode", "message": "每个教学块都需要明确可观察的认知投入方式。"})
    if any(not _text(item.get("check_method")) for item in blocks):
        issues.append({"code": "lesson_arrangement:check_method", "message": "每个教学块都需要说明怎样取得学习证据。"})
    if any(not _text(item.get("feedback_strategy")) for item in blocks):
        issues.append({"code": "lesson_arrangement:feedback_strategy", "message": "每个教学块都需要说明教师怎样依据证据作出下一步调整。"})
    if any(not list(item.get("adaptation_options") or []) for item in blocks):
        issues.append({"code": "lesson_arrangement:adaptation_options", "message": "每个教学块都需要保留达到、部分达到和未达到时的处理路径。"})
    return issues


def apply_lesson_arrangement_to_plan(
    plan: dict[str, Any],
    arrangement: dict[str, Any],
) -> dict[str, Any]:
    result = deepcopy(plan)
    lesson_unit_id = _text(arrangement.get("lesson_unit_id"))
    chapter = _lesson_chapter(result, lesson_unit_id)
    if not isinstance(chapter, dict):
        return result
    lesson_type = _text(arrangement.get("lesson_type"))
    type_contract = LESSON_TYPES.get(lesson_type, LESSON_TYPES["theory"])
    blocks_by_section: dict[str, list[dict[str, Any]]] = {}
    for block in arrangement.get("blocks") or []:
        if isinstance(block, dict):
            blocks_by_section.setdefault(_text(block.get("section_node_id")), []).append(block)
    for section in chapter.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = _text(section.get("node_id"))
        modules = []
        for block in blocks_by_section.get(section_id, []):
            module_id = _text(block.get("module_id"))
            registry = MODULES.get(module_id)
            modules.append({
                "module_id": module_id,
                "label": _text(block.get("name")),
                "block_role": _text(block.get("role")) or module_block_role(module_id),
                "scope": "lesson",
                "frequency": "lesson_required",
                "source_mode": "teacher_current",
                "required": bool(block.get("required", True)),
                "output_contract": _text(block.get("expected_output") or block.get("purpose") or (registry.output_contract if registry else "")),
                "prompt_instruction": _text(block.get("content_summary") or (registry.prompt_instruction if registry else "")),
                "arrangement_block_id": _text(block.get("block_id")),
                "planned_minutes": int(block.get("planned_minutes") or 1),
                "teacher_activity": _text(block.get("teacher_activity")),
                "student_activity": _text(block.get("student_activity")),
                "expected_output": _text(block.get("expected_output")),
                "check_method": _text(block.get("check_method")),
                "feedback_strategy": _text(block.get("feedback_strategy")),
                "adaptation_options": deepcopy(block.get("adaptation_options") or []),
                "resource_refs": deepcopy(block.get("resource_refs") or []),
                "tools": deepcopy(block.get("tools") or []),
                "engagement_mode": _text(block.get("engagement_mode")),
                "access_support": _text(block.get("access_support")),
                "grouping": _text(block.get("grouping")),
                "transition": _text(block.get("transition")),
                "safety_boundary": _text(block.get("safety_boundary")),
                "lesson_archetype_id": f"teacher_{lesson_type}",
                "lesson_archetype_label": type_contract["label"],
            })
        section["module_plan"] = modules
        section["lesson_archetype"] = {
            "archetype_id": f"teacher_{lesson_type}",
            "label": type_contract["label"],
            "purpose": type_contract["purpose"],
            "source": "teacher_current_arrangement",
        }
    result["teacher_lesson_arrangement"] = json.loads(json.dumps(arrangement, ensure_ascii=False))
    result["teacher_lesson_semantics"] = {
        "teaching_semantics_version": _text(arrangement.get("teaching_semantics_version")),
        "lesson_type": lesson_type,
        "lesson_type_contract": deepcopy(
            arrangement.get("lesson_type_contract") or LESSON_TYPE_CONTRACTS[lesson_type]
        ),
        "required_learning_cycle": deepcopy(arrangement.get("required_learning_cycle") or []),
        "classroom_constraints": deepcopy(arrangement.get("classroom_constraints") or {}),
        "quality_rules": deepcopy(arrangement.get("quality_rules") or []),
    }
    return result


__all__ = [
    "LESSON_TYPES",
    "SCHEMA_VERSION",
    "apply_lesson_arrangement_to_plan",
    "normalize_lesson_arrangement",
    "recommend_lesson_arrangement",
    "validate_lesson_arrangement",
]
