"""Teacher-only lesson plan assets and jobs.

This module deliberately does not write ``CourseDocument``.  It is the
authoring boundary for a teacher lesson (one L1 node plus all direct L2
sections) while the existing learner course-generation pipeline remains
unchanged.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import threading
import uuid
import hashlib
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from course_document import document_from_generation_draft
from course_pedagogy import module_block_role


SCHEMA_VERSION = "teacher_lesson_authoring_v1"
LESSON_PLAN_PIPELINE_VERSION = "standard_lesson_plan_v1"
JOB_TYPES = {
    "teacher_lesson_plan_generation",
}


class TeacherLessonAuthoringError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.splitlines() if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if isinstance(item, str) and item.strip()]
    return []


def _unique_text(values: list[str]) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in values if item.strip()))


def teacher_lesson_section_content(section: dict[str, Any]) -> dict[str, Any]:
    """Project plan-v3 knowledge/modules into concrete teacher-editable fields.

    Real provider fallbacks keep useful knowledge facts but often omit the old
    ``learning_objective`` / ``teacher_activities`` convenience fields.  This
    projection is the compatibility boundary shared by preview, editing and
    PPT source compilation; it never serializes module dictionaries as prose.
    """
    points = [
        point
        for group in section.get("knowledge_structure") or []
        if isinstance(group, dict)
        for point in group.get("knowledge_points") or []
        if isinstance(point, dict)
    ]
    modules = [
        item for item in section.get("teaching_modules") or []
        if isinstance(item, dict)
    ]
    capability_objectives = [
        str(capability.get("observable_behavior") or capability.get("name") or "").strip()
        for point in points
        for capability in point.get("capability_points") or []
        if isinstance(capability, dict)
        and str(capability.get("observable_behavior") or capability.get("name") or "").strip()
    ]
    statements = [
        str(point.get("statement") or point.get("description") or "").strip()
        for point in points
        if str(point.get("statement") or point.get("description") or "").strip()
    ]
    boundaries = [
        item for point in points for item in _text_list(point.get("boundaries"))
    ]
    misconceptions = [
        str(item.get("discrimination") or item.get("name") or "").strip()
        for point in points
        for item in point.get("misconceptions") or []
        if isinstance(item, dict)
        and str(item.get("discrimination") or item.get("name") or "").strip()
    ]

    def module_line(module: dict[str, Any]) -> str:
        labels = {
            "lesson_goal": "本节目标",
            "core_explanation": "核心讲解",
            "math_problem_strategy": "策略选择",
            "math_worked_example": "例题推演",
            "math_intuition": "直觉导入",
            "math_representation": "多重表征",
            "math_formalization": "正式定义",
            "math_variation": "变式练习",
            "learner_action": "学习者行动",
            "feedback_check": "检查与反馈",
        }
        module_id = str(module.get("module_id") or "")
        label = str(module.get("label") or labels.get(module_id) or "教学活动")
        knowledge = _text_list(module.get("knowledge_names"))
        guidance = str(module.get("teaching_guidance") or "").strip()
        if guidance.startswith("按模板完成"):
            guidance = ""
        details = [f"围绕{'、'.join(knowledge)}" if knowledge else "", guidance]
        suffix = "；".join(item for item in details if item)
        return f"{label}：{suffix}" if suffix else label

    explicit_objective = str(
        section.get("learning_objective") or section.get("objective") or ""
    ).strip()
    learning_objective = (
        explicit_objective
        or "；".join(capability_objectives)
        or "；".join(statements)
        or "；".join(_text_list(section.get("key_points")))
    )
    key_difficulties = _text_list(section.get("key_difficulties")) or _unique_text([
        *_text_list(section.get("key_points")),
        *boundaries,
        *misconceptions,
    ])
    module_teacher_activities = _unique_text([
        str(module.get("teacher_activity") or "").strip()
        for module in modules
        if str(module.get("teacher_activity") or "").strip()
    ])
    module_student_activities = _unique_text([
        str(module.get("student_activity") or "").strip()
        for module in modules
        if str(module.get("student_activity") or "").strip()
    ])
    teacher_activities = module_teacher_activities or _text_list(
        section.get("teacher_activities")
    ) or _unique_text([
        module_line(module)
        for module in modules
        if str(module.get("module_id") or "") not in {
            "learner_action", "math_variation", "feedback_check",
        }
    ])
    student_activities = module_student_activities or _text_list(
        section.get("student_activities")
    ) or _unique_text([
        module_line(module)
        for module in modules
        if str(module.get("module_id") or "") in {"learner_action", "math_variation"}
    ])
    homework = _text_list(section.get("homework")) or _unique_text([
        module_line(module)
        for module in modules
        if str(module.get("module_id") or "") == "feedback_check"
    ])
    return {
        "learning_objective": learning_objective,
        "key_difficulties": key_difficulties,
        "teacher_activities": teacher_activities,
        "student_activities": student_activities,
        "homework": homework,
        "knowledge_statements": statements,
        "knowledge_boundaries": boundaries,
        "misconceptions": misconceptions,
    }


def normalize_teacher_lesson_plan(plan: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(plan)
    normalized["sections"] = []
    for section in plan.get("sections") or []:
        if not isinstance(section, dict):
            continue
        next_section = deepcopy(section)
        for key, value in teacher_lesson_section_content(next_section).items():
            if key.startswith("knowledge_") or key == "misconceptions":
                continue
            if key in {"teacher_activities", "student_activities"} and next_section.get("teaching_modules"):
                next_section[key] = deepcopy(value)
            elif not next_section.get(key):
                next_section[key] = deepcopy(value)
        normalized["sections"].append(next_section)
    return normalized


def validate_teacher_lesson_plan(
    plan: dict[str, Any],
    *,
    expected_section_ids: list[str] | None = None,
    expected_outline_revision_id: str = "",
    source_outline_revision_id: str = "",
) -> dict[str, Any]:
    """Validate the one teacher-facing standard lesson-plan contract.

    The V3 planner remains responsible for grounded knowledge and pedagogy.
    This gate owns the final classroom document: complete section coverage,
    observable objectives, executable activities, checks, timing and homework.
    Drafts may be saved with blockers, but only a passing revision can become
    the confirmed source for question-bank and PPT production.
    """
    normalized = normalize_teacher_lesson_plan(plan)
    sections = [
        item for item in normalized.get("sections") or []
        if isinstance(item, dict)
    ]
    actual_ids = [str(item.get("node_id") or "") for item in sections]
    blocking: list[dict[str, str]] = []
    review: list[dict[str, str]] = []

    def issue(
        target: list[dict[str, str]],
        code: str,
        message: str,
        section_id: str = "",
    ) -> None:
        payload = {"code": code, "message": message}
        if section_id:
            payload["section_id"] = section_id
        target.append(payload)

    if str(normalized.get("schema_version") or "") != "course_teaching_plan_v3":
        issue(blocking, "lesson_plan:schema", "教案必须使用统一的 CourseTeachingPlanV3 结构。")
    if not sections:
        issue(blocking, "lesson_plan:sections_empty", "教案没有可用的教学小节。")
    if any(not section_id for section_id in actual_ids):
        issue(blocking, "lesson_plan:section_identity", "教案小节缺少稳定标识。")
    if len(actual_ids) != len(set(actual_ids)):
        issue(blocking, "lesson_plan:duplicate_section", "教案包含重复小节。")
    if expected_section_ids is not None and actual_ids != expected_section_ids:
        issue(blocking, "lesson_plan:section_scope", "教案必须按大纲顺序完整覆盖当前讲次的所有小节。")
    if (
        expected_outline_revision_id
        and source_outline_revision_id
        and expected_outline_revision_id != source_outline_revision_id
    ):
        issue(blocking, "lesson_plan:stale_outline", "教案对应的大纲版本已经过期。")

    total_modules = 0
    total_minutes = 0
    knowledge_point_count = 0
    for section in sections:
        section_id = str(section.get("node_id") or "")
        objective = str(section.get("learning_objective") or "").strip()
        key_points = _text_list(section.get("key_points"))
        difficulties = _text_list(section.get("key_difficulties"))
        checks = _text_list(section.get("in_class_checks"))
        homework = _text_list(section.get("homework"))
        modules = [
            item for item in section.get("teaching_modules") or []
            if isinstance(item, dict)
        ]
        total_modules += len(modules)
        section_minutes = sum(
            max(0, int(item.get("planned_minutes") or 0))
            for item in modules
            if str(item.get("planned_minutes") or "").isdigit()
        )
        total_minutes += section_minutes

        if not objective:
            issue(blocking, "lesson_plan:objective", "小节缺少可观察的教学目标。", section_id)
        if not key_points:
            issue(blocking, "lesson_plan:key_points", "小节缺少教学重点。", section_id)
        if not difficulties:
            issue(blocking, "lesson_plan:difficulties", "小节缺少教学难点。", section_id)
        if not modules:
            issue(blocking, "lesson_plan:modules", "小节缺少可执行的教学流程。", section_id)
        if modules and not any(str(item.get("teacher_activity") or "").strip() for item in modules):
            issue(blocking, "lesson_plan:teacher_activity", "小节缺少具体的教师活动。", section_id)
        if modules and not any(str(item.get("student_activity") or "").strip() for item in modules):
            issue(blocking, "lesson_plan:student_activity", "小节缺少具体的学生活动。", section_id)
        if modules and section_minutes <= 0:
            issue(blocking, "lesson_plan:timing", "小节缺少有效的时间分配。", section_id)
        elif any(item.get("planned_minutes") in (None, "") for item in modules):
            issue(review, "lesson_plan:module_timing", "部分教学环节未单独标注时长。", section_id)
        if not checks:
            issue(blocking, "lesson_plan:checks", "小节缺少课堂检查或可观察产出。", section_id)
        if not homework:
            issue(blocking, "lesson_plan:homework", "小节缺少课后巩固或迁移任务。", section_id)

        points = [
            point
            for group in section.get("knowledge_structure") or []
            if isinstance(group, dict)
            for point in group.get("knowledge_points") or []
            if isinstance(point, dict)
        ]
        knowledge_point_count += len(points)
        for point in points:
            name = str(point.get("name") or "").strip()
            statement = str(point.get("statement") or point.get("description") or "").strip()
            if name and not statement:
                issue(blocking, "lesson_plan:knowledge_statement", f"知识点「{name}」缺少准确陈述。", section_id)
            if point.get("conflict") or point.get("needs_manual_review"):
                issue(blocking, "lesson_plan:knowledge_conflict", f"知识点「{name or '未命名'}」存在待核实冲突。", section_id)

    return {
        "schema_version": "teacher_lesson_plan_quality_v1",
        "pipeline_version": LESSON_PLAN_PIPELINE_VERSION,
        "passed": not blocking,
        "blocking_issues": blocking,
        "review_issues": review,
        "metrics": {
            "section_count": len(sections),
            "teaching_module_count": total_modules,
            "knowledge_point_count": knowledge_point_count,
            "planned_minutes": total_minutes,
        },
    }


def extract_uploaded_pptx_evidence(
    path: Path,
    *,
    asset_id: str,
) -> list[dict[str, Any]]:
    """Extract visible slide text without mutating the teacher's source deck."""
    if path.suffix.lower() != ".pptx":
        raise TeacherLessonAuthoringError(
            "uploaded_ppt_format_unsupported",
            "旧课件同源解析目前仅支持 PPTX 文件。",
        )
    try:
        from pptx import Presentation

        presentation = Presentation(path)
    except Exception as exc:
        raise TeacherLessonAuthoringError(
            "uploaded_ppt_parse_failed",
            "旧课件无法解析，请确认文件未损坏。",
        ) from exc

    evidence: list[dict[str, Any]] = []
    for slide_number, slide in enumerate(presentation.slides, start=1):
        parts: list[str] = []
        for shape in slide.shapes:
            text = ""
            if getattr(shape, "has_text_frame", False):
                text = str(getattr(shape, "text", "") or "")
            elif getattr(shape, "has_table", False):
                text = "\n".join(
                    str(cell.text or "")
                    for row in shape.table.rows
                    for cell in row.cells
                )
            normalized = " ".join(text.split()).strip()
            if normalized and normalized not in parts:
                parts.append(normalized)
        source_text = "\n".join(parts).strip()
        if not source_text:
            continue
        evidence.append({
            "evidence_id": f"uploaded-ppt-{asset_id}-slide-{slide_number}",
            "kind": "uploaded_ppt_slide",
            "summary": source_text[:1200],
            "source_text": source_text[:2400],
            "slide": slide_number,
            "asset_id": asset_id,
        })
    if not evidence:
        raise TeacherLessonAuthoringError(
            "uploaded_ppt_empty",
            "旧课件中没有可用于生成教案的文字内容。",
        )
    return evidence


def _default_root() -> Path:
    configured = os.getenv("TEACHER_LESSON_AUTHORING_DIR", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent / "data" / "teacher_lesson_authoring"


def lesson_scope(course_data: dict[str, Any], lesson_unit_id: str) -> dict[str, Any]:
    """Resolve one stable teacher lesson and its direct ordered sections."""
    nodes = [item for item in course_data.get("nodes") or [] if isinstance(item, dict)]
    lesson = next(
        (
            item for item in nodes
            if str(item.get("node_id") or "") == lesson_unit_id
            and int(item.get("node_level") or 0) == 1
        ),
        None,
    )
    if not lesson:
        raise TeacherLessonAuthoringError(
            "lesson_unit_not_found",
            "当前课程中不存在该讲次。",
            details={"lesson_unit_id": lesson_unit_id},
        )
    sections = [
        deepcopy(item) for item in nodes
        if str(item.get("parent_node_id") or "") == lesson_unit_id
    ]
    if not sections:
        raise TeacherLessonAuthoringError(
            "lesson_sections_empty",
            "当前讲次没有可生成教案的小节。",
            details={"lesson_unit_id": lesson_unit_id},
        )
    plan = course_data.get("course_plan") or course_data.get("course_outline") or {}
    chapters = [item for item in plan.get("chapters") or [] if isinstance(item, dict)]
    chapter = next(
        (
            item for item in chapters
            if str(item.get("node_id") or item.get("chapter_id") or "") == lesson_unit_id
        ),
        None,
    )
    if chapter is None:
        section_ids = {str(item.get("node_id") or "") for item in sections}
        chapter = next(
            (
                item for item in chapters
                if section_ids
                and section_ids.issubset({
                    str(section.get("node_id") or "")
                    for section in item.get("sections") or []
                    if isinstance(section, dict)
                })
            ),
            None,
        )
    return {
        "lesson": deepcopy(lesson),
        "sections": sections,
        "chapter": deepcopy(chapter) if isinstance(chapter, dict) else None,
    }


def teacher_lesson_script_revision(
    course_data: dict[str, Any],
    lesson_unit_id: str,
) -> str:
    """Fingerprint the saved course body used as this lesson's single script source."""
    scope = lesson_scope(course_data, lesson_unit_id)
    payload = [
        {
            "section_node_id": str(section.get("node_id") or ""),
            "title": str(section.get("node_name") or ""),
            "content": str(section.get("node_content") or ""),
        }
        for section in scope["sections"]
    ]
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:24]
    return f"tlsr-{digest}"


def teacher_lesson_script_sections_revision(
    sections: list[dict[str, Any]],
) -> str:
    """Fingerprint one teacher-script asset without depending on course storage."""
    payload = [
        {
            "section_node_id": str(section.get("section_node_id") or ""),
            "title": str(section.get("title") or ""),
            "content": str(section.get("content") or ""),
        }
        for section in sections
        if isinstance(section, dict)
    ]
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:24]
    return f"tlsr-{digest}"


def lesson_plan_ppt_source(
    plan: dict[str, Any],
    *,
    lesson_unit_id: str,
    source_revision_id: str,
) -> dict[str, Any]:
    """Compile the teacher-only source contract for one lesson deck."""
    normalized_plan = normalize_teacher_lesson_plan(plan)
    sections = [
        deepcopy(item)
        for item in normalized_plan.get("sections") or []
        if isinstance(item, dict) and item.get("node_id")
    ]
    if not sections:
        raise TeacherLessonAuthoringError(
            "lesson_plan_empty",
            "本讲教案没有可用于生成 PPT 的小节。",
        )
    return {
        "schema_version": "teacher_lesson_ppt_source_v1",
        "lesson_unit_id": lesson_unit_id,
        "source_lesson_plan_revision_id": source_revision_id,
        "title": str(plan.get("lesson_title") or plan.get("course_title") or "本讲课件"),
        "sections": sections,
    }


def teacher_lesson_deck_to_structured_slide_deck(
    deck: dict[str, Any],
    *,
    source_revision_id: str,
) -> dict[str, Any]:
    """Adapt the lightweight teacher deck to the shared editable PPTX renderer."""
    raw_slides = [item for item in deck.get("slides") or [] if isinstance(item, dict)]
    if not raw_slides:
        raise TeacherLessonAuthoringError("lesson_ppt_empty", "本讲 PPT 没有可导出的页面。")
    slides = []
    for index, slide in enumerate(raw_slides):
        body = slide.get("body") or []
        if isinstance(body, str):
            body = [body]
        layout = "cover" if index == 0 else "recap" if index == len(raw_slides) - 1 else "concept"
        slides.append({
            "unit_id": str(slide.get("slide_id") or f"slide-{index + 1}"),
            "position": index,
            "layout": layout,
            "slide_purpose": "teacher_lesson_presentation",
            "title": str(slide.get("title") or f"第 {index + 1} 页"),
            "key_message": str(body[0] if body else slide.get("title") or ""),
            "takeaway": str(body[-1] if body else ""),
            "blocks": [{
                "block_id": f"{slide.get('slide_id') or index}-bullets",
                "type": "bullets",
                "items": [str(item) for item in body if str(item).strip()][:8],
            }],
            "speaker_notes": str(slide.get("speaker_notes") or ""),
        })
    return {
        "schema_version": "slide_deck_v2",
        "title": str(deck.get("title") or "本讲课件"),
        "theme": "qingfeng-classroom",
        "source_document_revision": source_revision_id,
        "slides": slides,
    }


def teacher_lesson_v6_source(
    course_data: dict[str, Any],
    *,
    lesson_unit_id: str,
    plan_revision: dict[str, Any],
    script_revision: dict[str, Any] | None = None,
) -> tuple[Any, dict[str, Any], str]:
    """Adapt one teacher plan revision to the existing V6 source contracts.

    The returned synthetic course id is stable for one real course + lesson,
    while the CourseDocument revision changes with the teacher plan. Nothing is
    persisted to the learner CourseDocument repository.
    """
    scope = lesson_scope(course_data, lesson_unit_id)
    plan = normalize_teacher_lesson_plan(plan_revision.get("plan") or {})
    plan_sections = {
        str(item.get("node_id") or ""): deepcopy(item)
        for item in plan.get("sections") or []
        if isinstance(item, dict) and item.get("node_id")
    }
    digest = hashlib.sha256(
        f"{course_data.get('course_id')}:{lesson_unit_id}".encode("utf-8")
    ).hexdigest()[:20]
    synthetic_course_id = f"teacher-lesson-{digest}"
    lesson_title = str(scope["lesson"].get("node_name") or "本讲课件")
    script_sections = {
        str(item.get("section_node_id") or ""): deepcopy(item)
        for item in (script_revision or {}).get("sections") or []
        if isinstance(item, dict) and item.get("section_node_id")
    }
    script_revision_id = str((script_revision or {}).get("revision_id") or "")
    if not script_revision_id:
        script_revision_id = teacher_lesson_script_revision(course_data, lesson_unit_id)
    lesson_node = deepcopy(scope["lesson"])
    lesson_node.update({
        "node_id": lesson_unit_id,
        "parent_node_id": "root",
        "node_level": 1,
        "node_name": lesson_title,
        "node_content": "",
        "content_blocks": [],
    })
    nodes = [lesson_node]
    for section_index, outline_section in enumerate(scope["sections"], start=1):
        section_id = str(outline_section.get("node_id") or "")
        planned = plan_sections.get(section_id) or {}
        section_content = teacher_lesson_section_content(planned)
        modules = [
            item for item in planned.get("teaching_modules") or []
            if isinstance(item, dict)
        ]
        blocks: list[dict[str, Any]] = []
        script_content = str(
            (script_sections.get(section_id) or {}).get("content")
            or outline_section.get("node_content")
            or ""
        ).strip()
        if script_content:
            blocks.append({
                "block_id": f"{section_id}-teacher-script",
                "type": "concept",
                "title": "讲稿正文",
                "content": script_content,
                "metadata": {
                    "role": "concept",
                    "source_kind": "confirmed_teacher_script",
                },
            })
        for module_index, module in enumerate(modules, start=1):
            module_id = str(module.get("module_id") or "core_explanation")
            role = module_block_role(module_id)
            if role not in {
                "orientation", "prerequisite", "objective", "concept", "reasoning",
                "example", "counterexample", "application", "activity", "feedback",
                "misconception", "checkpoint", "remediation", "summary", "transfer",
            }:
                role = "concept"
            knowledge_names = [
                str(item) for item in module.get("knowledge_names") or []
                if str(item).strip()
            ]
            labels = {
                "lesson_goal": "本节目标",
                "core_explanation": "核心讲解",
                "math_problem_strategy": "策略选择",
                "math_worked_example": "例题推演",
                "math_intuition": "直觉导入",
                "math_representation": "多重表征",
                "math_formalization": "正式定义",
                "math_variation": "变式练习",
                "learner_action": "学习者行动",
                "feedback_check": "检查与反馈",
            }
            purpose = str(module.get("teaching_purpose") or "").strip()
            if purpose.startswith("按模板完成"):
                purpose = ""
            guidance = str(module.get("teaching_guidance") or "").strip()
            if guidance.startswith("按模板完成"):
                guidance = ""
            if module_id == "lesson_goal":
                concrete = [section_content["learning_objective"]]
            elif module_id in {"learner_action", "math_variation"}:
                concrete = section_content["student_activities"]
            elif module_id == "feedback_check":
                concrete = [
                    *section_content["homework"],
                    *section_content["misconceptions"],
                ]
            else:
                concrete = [
                    *section_content["knowledge_statements"],
                    *section_content["key_difficulties"],
                ]
            paragraphs = _unique_text([
                *[str(item) for item in concrete if str(item).strip()],
                purpose,
                guidance,
                f"教师活动：{module.get('teacher_activity')}" if module.get("teacher_activity") else "",
                f"学生活动：{module.get('student_activity')}" if module.get("student_activity") else "",
                f"知识要点：{'、'.join(knowledge_names)}" if knowledge_names else "",
            ])
            blocks.append({
                "block_id": f"{section_id}-teacher-{module_index}",
                "type": role,
                "title": str(module.get("label") or labels.get(module_id) or module_id),
                "content": "\n\n".join(item for item in paragraphs if item),
                "metadata": {
                    "role": role,
                    "module_id": module_id,
                    "module_instance_id": f"{section_id}:{module_id}:{module_index}",
                    "concept_refs": knowledge_names,
                },
            })
        if not blocks:
            key_points = [str(item) for item in planned.get("key_points") or [] if str(item).strip()]
            blocks = [{
                "block_id": f"{section_id}-teacher-concept",
                "type": "concept",
                "title": str(outline_section.get("node_name") or "核心教学"),
                "content": "\n\n".join(filter(None, [
                    str(section_content.get("learning_objective") or outline_section.get("learning_objective") or ""),
                    f"知识要点：{'、'.join(key_points)}" if key_points else "",
                ])),
                "metadata": {"role": "concept", "concept_refs": key_points},
            }]
        node = deepcopy(outline_section)
        node.update({
            "node_id": section_id,
            "parent_node_id": lesson_unit_id,
            "node_level": 2,
            "node_name": str(outline_section.get("node_name") or f"第{section_index}节"),
            "learning_objective": str(
                section_content.get("learning_objective")
                or outline_section.get("learning_objective")
                or ""
            ),
            "knowledge_structure": deepcopy(
                planned.get("knowledge_structure")
                or outline_section.get("knowledge_structure")
                or []
            ),
            "key_points": deepcopy(planned.get("key_points") or []),
            "content_blocks": blocks,
            "node_content": "\n\n".join(
                f"## {block['title']}\n\n{block['content']}" for block in blocks
            ),
        })
        nodes.append(node)
    synthetic = {
        "course_id": synthetic_course_id,
        "course_name": lesson_title,
        "language": str(course_data.get("language") or "zh-CN"),
        "nodes": nodes,
        "course_teaching_plan": plan,
        "course_knowledge_base": deepcopy(course_data.get("course_knowledge_base") or {}),
        "course_coherence_contract": deepcopy(course_data.get("course_coherence_contract") or {}),
        "generation_request": deepcopy(course_data.get("generation_request") or {}),
        "teacher_lesson_source": {
            "real_course_id": str(course_data.get("course_id") or ""),
            "lesson_unit_id": lesson_unit_id,
            "lesson_plan_revision_id": str(plan_revision.get("revision_id") or ""),
            "script_revision_id": script_revision_id,
        },
    }
    document = document_from_generation_draft(synthetic)
    return document, synthetic, synthetic_course_id


class TeacherLessonAuthoringRepository:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root is not None else _default_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, course_id: str) -> Path:
        safe = "".join(char for char in course_id if char.isalnum() or char in {"-", "_"})
        if not safe or safe != course_id:
            raise TeacherLessonAuthoringError("invalid_course_id", "课程标识无效。")
        return self.root / f"{safe}.json"

    def _empty(self, course_id: str) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "course_id": course_id,
            "revision": 0,
            "outline_revision_id": "",
            "lessons": {},
            "jobs": {},
            "updated_at": _now(),
        }

    def load(self, course_id: str) -> dict[str, Any]:
        with self._lock:
            path = self._path(course_id)
            if not path.exists():
                return self._empty(course_id)
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise TeacherLessonAuthoringError(
                    "authoring_repository_corrupt",
                    "教师讲次资产读取失败。",
                ) from exc
            return data if isinstance(data, dict) else self._empty(course_id)

    def _save(self, value: dict[str, Any]) -> dict[str, Any]:
        course_id = str(value.get("course_id") or "")
        path = self._path(course_id)
        payload = deepcopy(value)
        payload["schema_version"] = SCHEMA_VERSION
        payload["revision"] = int(payload.get("revision") or 0) + 1
        payload["updated_at"] = _now()
        fd, temp_name = tempfile.mkstemp(prefix=f".{course_id}.", suffix=".tmp", dir=str(self.root))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return deepcopy(payload)

    def set_outline(self, course_id: str, outline_revision_id: str) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            value["outline_revision_id"] = outline_revision_id
            for lesson in (value.get("lessons") or {}).values():
                if not isinstance(lesson, dict) or not lesson.get("working_revision_id"):
                    continue
                working = next(
                    (
                        item for item in lesson.get("revisions") or []
                        if isinstance(item, dict)
                        and item.get("revision_id") == lesson.get("working_revision_id")
                    ),
                    None,
                )
                lesson["source_state"] = (
                    "current"
                    if isinstance(working, dict)
                    and str(working.get("source_outline_revision_id") or "") == outline_revision_id
                    else "stale"
                )
            return self._save(value)

    def create_job(
        self,
        course_id: str,
        lesson_unit_id: str,
        *,
        job_type: str = "teacher_lesson_plan_generation",
        request_id: str = "",
        source_outline_revision_id: str = "",
    ) -> dict[str, Any]:
        if job_type not in JOB_TYPES:
            raise TeacherLessonAuthoringError("unsupported_teacher_job", "不支持的教师讲次任务。")
        with self._lock:
            value = self.load(course_id)
            if request_id:
                existing = next(
                    (
                        job for job in (value.get("jobs") or {}).values()
                        if isinstance(job, dict)
                        and job.get("request_id") == request_id
                        and job.get("lesson_unit_id") == lesson_unit_id
                        and job.get("type") == job_type
                    ),
                    None,
                )
                if existing:
                    return deepcopy(existing)
            job_id = f"tlj-{uuid.uuid4().hex}"
            job = {
                "id": job_id,
                "course_id": course_id,
                "lesson_unit_id": lesson_unit_id,
                "type": job_type,
                "request_id": request_id,
                "source_outline_revision_id": source_outline_revision_id,
                "status": "pending",
                "progress": 0,
                "phase": "queued",
                "message": "等待生成本讲教案",
                "stream_sequence": 0,
                "stream_batches": {},
                "stream_complete": False,
                "warnings": [],
                "error": None,
                "created_at": _now(),
                "updated_at": _now(),
            }
            value.setdefault("jobs", {})[job_id] = job
            self._save(value)
            return deepcopy(job)

    def update_job(self, course_id: str, job_id: str, **changes: Any) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            job = (value.get("jobs") or {}).get(job_id)
            if not isinstance(job, dict):
                raise TeacherLessonAuthoringError("teacher_job_not_found", "教师讲次任务不存在。")
            job.update(deepcopy(changes))
            job["updated_at"] = _now()
            value["jobs"][job_id] = job
            self._save(value)
            return deepcopy(job)

    def update_job_stream(
        self,
        course_id: str,
        job_id: str,
        *,
        phase: str,
        progress: int,
        message: str,
        batch_id: str,
        event: str,
        delta: str = "",
    ) -> dict[str, Any]:
        """Persist one model-stream checkpoint without losing concurrent batches."""
        with self._lock:
            value = self.load(course_id)
            job = (value.get("jobs") or {}).get(job_id)
            if not isinstance(job, dict):
                raise TeacherLessonAuthoringError("teacher_job_not_found", "教师讲次任务不存在。")
            batches = deepcopy(job.get("stream_batches") or {})
            if event == "reset":
                batches[batch_id] = ""
            elif event == "delta":
                batches[batch_id] = (
                    str(batches.get(batch_id) or "") + str(delta or "")
                )[-200_000:]
            job.update({
                "phase": phase,
                "progress": progress,
                "message": message,
                "stream_sequence": int(job.get("stream_sequence") or 0) + 1,
                "stream_batches": batches,
                "stream_complete": False,
                "updated_at": _now(),
            })
            value["jobs"][job_id] = job
            self._save(value)
            return deepcopy(job)

    def save_plan_revision(
        self,
        course_id: str,
        lesson_unit_id: str,
        plan: dict[str, Any],
        *,
        source_outline_revision_id: str,
        generation_source: str = "model",
        warnings: list[dict[str, Any]] | None = None,
        source_refs: list[dict[str, Any]] | None = None,
        quality_report: dict[str, Any] | None = None,
        actor: str = "teacher",
    ) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            normalized_plan = normalize_teacher_lesson_plan(plan)
            effective_quality = deepcopy(
                quality_report or validate_teacher_lesson_plan(normalized_plan)
            )
            lesson = value.setdefault("lessons", {}).setdefault(lesson_unit_id, {
                "lesson_unit_id": lesson_unit_id,
                "working_revision_id": "",
                "confirmed_revision_id": "",
                "source_state": "current",
                "revisions": [],
                "ai_candidates": [],
                "working_script_revision_id": "",
                "script_revisions": [],
                "script_confirmation": {},
                "ppt_assets": [],
            })
            revision_id = f"tlpr-{uuid.uuid4().hex}"
            revision = {
                "revision_id": revision_id,
                "lesson_unit_id": lesson_unit_id,
                "source_outline_revision_id": source_outline_revision_id,
                "generation_source": generation_source,
                "status": (
                    "needs_ai_review"
                    if warnings or not effective_quality.get("passed")
                    else "draft"
                ),
                "warnings": deepcopy(warnings or []),
                "source_refs": deepcopy(source_refs or []),
                "pipeline_version": LESSON_PLAN_PIPELINE_VERSION,
                "quality_report": effective_quality,
                "plan": normalized_plan,
                "actor": actor,
                "created_at": _now(),
            }
            lesson.setdefault("revisions", []).append(revision)
            lesson["working_revision_id"] = revision_id
            lesson["source_state"] = (
                "current"
                if not value.get("outline_revision_id")
                or str(value.get("outline_revision_id") or "") == source_outline_revision_id
                else "stale"
            )
            for asset in lesson.get("ppt_assets") or []:
                if not isinstance(asset, dict):
                    continue
                source_revision = str(asset.get("source_lesson_plan_revision_id") or "")
                if source_revision and source_revision != revision_id:
                    asset["source_state"] = "stale"
            if source_outline_revision_id and not value.get("outline_revision_id"):
                value["outline_revision_id"] = source_outline_revision_id
            saved = self._save(value)
            return deepcopy(saved["lessons"][lesson_unit_id])

    def save_ppt_revision(
        self,
        course_id: str,
        lesson_unit_id: str,
        deck: dict[str, Any],
        *,
        source_lesson_plan_revision_id: str,
        generation_source: str = "model",
        warnings: list[dict[str, Any]] | None = None,
        actor: str = "teacher",
        asset_role: str = "primary",
    ) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            if not isinstance(lesson, dict):
                raise TeacherLessonAuthoringError("lesson_plan_not_found", "请先生成本讲教案。")
            if lesson.get("working_revision_id") != source_lesson_plan_revision_id:
                raise TeacherLessonAuthoringError(
                    "lesson_plan_revision_conflict",
                    "教案草稿已经变化，请基于最新版本生成 PPT。",
                )
            assets = lesson.setdefault("ppt_assets", [])
            asset = next(
                (
                    item for item in assets
                    if isinstance(item, dict) and item.get("role") == asset_role
                ),
                None,
            )
            if asset is None:
                asset = {
                    "asset_id": f"tlpa-{uuid.uuid4().hex}",
                    "lesson_unit_id": lesson_unit_id,
                    "role": asset_role,
                    "working_revision_id": "",
                    "source_lesson_plan_revision_id": source_lesson_plan_revision_id,
                    "source_state": "current",
                    "revisions": [],
                    "ai_candidates": [],
                }
                assets.append(asset)
            revision_id = f"tlpv-{uuid.uuid4().hex}"
            revision = {
                "revision_id": revision_id,
                "lesson_unit_id": lesson_unit_id,
                "source_lesson_plan_revision_id": source_lesson_plan_revision_id,
                "generation_source": generation_source,
                "status": "needs_ai_review" if warnings else "draft",
                "warnings": deepcopy(warnings or []),
                "deck": deepcopy(deck),
                "actor": actor,
                "created_at": _now(),
            }
            asset.setdefault("revisions", []).append(revision)
            asset["working_revision_id"] = revision_id
            asset["source_lesson_plan_revision_id"] = source_lesson_plan_revision_id
            asset["source_state"] = "current"
            saved = self._save(value)
            saved_lesson = saved["lessons"][lesson_unit_id]
            return deepcopy(next(item for item in saved_lesson["ppt_assets"] if item["asset_id"] == asset["asset_id"]))

    def bind_v6_ppt_revision(
        self,
        course_id: str,
        lesson_unit_id: str,
        *,
        source_lesson_plan_revision_id: str,
        source_script_revision_id: str,
        synthetic_course_id: str,
        representation_id: str,
        spec_id: str,
        candidate_status: str,
    ) -> dict[str, Any]:
        """Register one real V6 representation without copying it into student data."""
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            if not isinstance(lesson, dict):
                raise TeacherLessonAuthoringError("lesson_plan_not_found", "请先生成本讲教案。")
            if lesson.get("confirmed_revision_id") != source_lesson_plan_revision_id:
                raise TeacherLessonAuthoringError(
                    "lesson_plan_revision_conflict",
                    "已确认教案已经变化，V6 结果未登记。",
                )
            assets = lesson.setdefault("ppt_assets", [])
            asset = next(
                (item for item in assets if isinstance(item, dict) and item.get("role") == "primary"),
                None,
            )
            if asset is None:
                asset = {
                    "asset_id": f"tlpa-{uuid.uuid4().hex}",
                    "lesson_unit_id": lesson_unit_id,
                    "role": "primary",
                    "working_revision_id": "",
                    "source_lesson_plan_revision_id": source_lesson_plan_revision_id,
                    "source_state": "current",
                    "revisions": [],
                    "ai_candidates": [],
                }
                assets.append(asset)
            binding = {
                "revision_id": f"tlv6r-{uuid.uuid4().hex}",
                "engine": "slide_deck_v6",
                "synthetic_course_id": synthetic_course_id,
                "representation_id": representation_id,
                "spec_id": spec_id,
                "source_lesson_plan_revision_id": source_lesson_plan_revision_id,
                "source_script_revision_id": source_script_revision_id,
                "candidate_status": candidate_status,
                "created_at": _now(),
            }
            asset.setdefault("v6_revisions", []).append(binding)
            asset["engine"] = "slide_deck_v6"
            asset["working_v6_revision_id"] = binding["revision_id"]
            asset["working_representation_id"] = representation_id
            asset["synthetic_course_id"] = synthetic_course_id
            asset["source_lesson_plan_revision_id"] = source_lesson_plan_revision_id
            asset["source_script_revision_id"] = source_script_revision_id
            asset["source_state"] = "current"
            saved = self._save(value)
            return deepcopy(next(item for item in saved["lessons"][lesson_unit_id]["ppt_assets"] if item["asset_id"] == asset["asset_id"]))

    def save_ppt_ai_candidate(
        self,
        course_id: str,
        lesson_unit_id: str,
        *,
        asset_id: str,
        base_revision_id: str,
        instruction: str,
        deck: dict[str, Any],
        slide_indexes: list[int] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            asset = next(
                (
                    item for item in (lesson or {}).get("ppt_assets") or []
                    if isinstance(item, dict) and item.get("asset_id") == asset_id
                ),
                None,
            )
            if not isinstance(asset, dict):
                raise TeacherLessonAuthoringError("lesson_ppt_not_found", "本讲还没有可优化的 PPT。")
            if asset.get("working_revision_id") != base_revision_id:
                raise TeacherLessonAuthoringError("lesson_ppt_revision_conflict", "PPT 草稿已经变化，请重新优化。")
            candidate = {
                "candidate_id": f"tlpac-{uuid.uuid4().hex}",
                "asset_id": asset_id,
                "base_revision_id": base_revision_id,
                "instruction": instruction,
                "slide_indexes": list(slide_indexes or []),
                "deck": deepcopy(deck),
                "status": "pending",
                "created_at": _now(),
            }
            asset.setdefault("ai_candidates", []).append(candidate)
            self._save(value)
            return deepcopy(candidate)

    def resolve_ppt_ai_candidate(
        self,
        course_id: str,
        lesson_unit_id: str,
        candidate_id: str,
        *,
        accept: bool,
        actor: str = "teacher",
    ) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            assets = (lesson or {}).get("ppt_assets") or []
            asset = next(
                (
                    item for item in assets
                    if isinstance(item, dict)
                    and any(
                        isinstance(candidate, dict) and candidate.get("candidate_id") == candidate_id
                        for candidate in item.get("ai_candidates") or []
                    )
                ),
                None,
            )
            if not isinstance(asset, dict):
                raise TeacherLessonAuthoringError("lesson_ppt_candidate_not_found", "AI PPT 候选不存在。")
            candidate = next(item for item in asset["ai_candidates"] if item.get("candidate_id") == candidate_id)
            if candidate.get("status") != "pending":
                return deepcopy(asset)
            if asset.get("working_revision_id") != candidate.get("base_revision_id"):
                raise TeacherLessonAuthoringError("lesson_ppt_revision_conflict", "PPT 草稿已经变化，不能覆盖新修改。")
            candidate["status"] = "accepted" if accept else "rejected"
            candidate["resolved_at"] = _now()
            if not accept:
                saved = self._save(value)
                return deepcopy(next(item for item in saved["lessons"][lesson_unit_id]["ppt_assets"] if item["asset_id"] == asset["asset_id"]))
            deck = deepcopy(candidate.get("deck") or {})
            source_revision = str(asset.get("source_lesson_plan_revision_id") or "")
            asset_role = str(asset.get("role") or "primary")
            self._save(value)
        return self.save_ppt_revision(
            course_id,
            lesson_unit_id,
            deck,
            source_lesson_plan_revision_id=source_revision,
            generation_source="ai_optimization",
            actor=actor,
            asset_role=asset_role,
        )

    def get_job(self, course_id: str, job_id: str) -> dict[str, Any]:
        value = self.load(course_id)
        job = (value.get("jobs") or {}).get(job_id)
        if not isinstance(job, dict):
            raise TeacherLessonAuthoringError("teacher_job_not_found", "教师讲次任务不存在。")
        return deepcopy(job)

    def lesson(self, course_id: str, lesson_unit_id: str) -> dict[str, Any]:
        value = self.load(course_id)
        lesson = (value.get("lessons") or {}).get(lesson_unit_id)
        if not isinstance(lesson, dict):
            return {
                "lesson_unit_id": lesson_unit_id,
                "working_revision_id": "",
                "confirmed_revision_id": "",
                "source_state": "current",
                "revisions": [],
                "ai_candidates": [],
                "working_script_revision_id": "",
                "script_revisions": [],
                "script_confirmation": {},
                "ppt_assets": [],
            }
        return deepcopy(lesson)

    def confirm_plan_revision(
        self,
        course_id: str,
        lesson_unit_id: str,
        revision_id: str,
        *,
        quality_report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            if not isinstance(lesson, dict):
                raise TeacherLessonAuthoringError("lesson_plan_not_found", "本讲还没有可确认的教案。")
            revision = next(
                (
                    item for item in lesson.get("revisions") or []
                    if isinstance(item, dict) and item.get("revision_id") == revision_id
                ),
                None,
            )
            if revision is None:
                raise TeacherLessonAuthoringError("lesson_plan_revision_not_found", "教案修订不存在。")
            if lesson.get("working_revision_id") != revision_id:
                raise TeacherLessonAuthoringError(
                    "lesson_plan_revision_conflict",
                    "只能确认当前教案工作稿。",
                )
            effective_quality = deepcopy(
                quality_report
                or revision.get("quality_report")
                or validate_teacher_lesson_plan(revision.get("plan") or {})
            )
            revision["pipeline_version"] = LESSON_PLAN_PIPELINE_VERSION
            revision["quality_report"] = effective_quality
            if not effective_quality.get("passed"):
                raise TeacherLessonAuthoringError(
                    "lesson_plan_quality_blocked",
                    "教案尚未通过专业性与完整性检查。",
                    details={
                        "quality_report": deepcopy(effective_quality),
                        "blocking_issues": deepcopy(
                            effective_quality.get("blocking_issues") or []
                        ),
                    },
                )
            if lesson.get("source_state") != "current":
                raise TeacherLessonAuthoringError(
                    "lesson_plan_outline_conflict",
                    "教案对应的大纲已经变化，请先更新教案。",
                )
            lesson["confirmed_revision_id"] = revision_id
            revision["status"] = "confirmed"
            revision["confirmed_at"] = _now()
            script_confirmation = lesson.get("script_confirmation")
            if isinstance(script_confirmation, dict) and script_confirmation.get("confirmed_revision_id"):
                if script_confirmation.get("source_lesson_plan_revision_id") != revision_id:
                    script_confirmation["source_state"] = "stale"
            saved = self._save(value)
            return deepcopy(saved["lessons"][lesson_unit_id])

    def save_script_revision(
        self,
        course_id: str,
        lesson_unit_id: str,
        sections: list[dict[str, Any]],
        *,
        source_lesson_plan_revision_id: str,
        generation_source: str = "model",
        requirements: str = "",
        material_asset_ids: list[str] | None = None,
        actor: str = "teacher",
    ) -> dict[str, Any]:
        normalized_sections = [
            {
                "section_node_id": str(item.get("section_node_id") or "").strip(),
                "title": str(item.get("title") or "").strip(),
                "content": str(item.get("content") or "").strip(),
            }
            for item in sections
            if isinstance(item, dict)
        ]
        if not normalized_sections or any(
            not item["section_node_id"] or not item["content"]
            for item in normalized_sections
        ):
            raise TeacherLessonAuthoringError(
                "lesson_script_incomplete",
                "本讲仍有小节没有讲稿内容，暂时不能保存。",
            )
        revision_id = teacher_lesson_script_sections_revision(normalized_sections)
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            if not isinstance(lesson, dict):
                raise TeacherLessonAuthoringError(
                    "lesson_plan_not_found",
                    "请先生成并确认本讲教案。",
                )
            if lesson.get("confirmed_revision_id") != source_lesson_plan_revision_id:
                raise TeacherLessonAuthoringError(
                    "lesson_plan_revision_conflict",
                    "已确认教案已经变化，请基于最新教案生成讲稿。",
                )
            revisions = lesson.setdefault("script_revisions", [])
            existing = next(
                (
                    item for item in revisions
                    if isinstance(item, dict) and item.get("revision_id") == revision_id
                ),
                None,
            )
            if existing is None:
                revisions.append({
                    "revision_id": revision_id,
                    "lesson_unit_id": lesson_unit_id,
                    "source_lesson_plan_revision_id": source_lesson_plan_revision_id,
                    "generation_source": generation_source,
                    "requirements": requirements,
                    "material_asset_ids": list(dict.fromkeys(
                        str(value or "").strip()
                        for value in material_asset_ids or []
                        if str(value or "").strip()
                    )),
                    "sections": normalized_sections,
                    "actor": actor,
                    "created_at": _now(),
                })
            lesson["working_script_revision_id"] = revision_id
            confirmation = lesson.get("script_confirmation")
            if isinstance(confirmation, dict) and confirmation.get("confirmed_revision_id") != revision_id:
                confirmation["source_state"] = "stale"
            for asset in lesson.get("ppt_assets") or []:
                if not isinstance(asset, dict) or asset.get("engine") != "slide_deck_v6":
                    continue
                if asset.get("source_script_revision_id") != revision_id:
                    asset["source_state"] = "stale"
            saved = self._save(value)
            return deepcopy(saved["lessons"][lesson_unit_id])

    def confirm_script_revision(
        self,
        course_id: str,
        lesson_unit_id: str,
        revision_id: str,
    ) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            if not isinstance(lesson, dict):
                raise TeacherLessonAuthoringError(
                    "lesson_plan_not_found",
                    "请先生成并确认本讲教案。",
                )
            source_plan_revision = str(lesson.get("confirmed_revision_id") or "")
            if not source_plan_revision:
                raise TeacherLessonAuthoringError(
                    "lesson_plan_not_confirmed",
                    "请先确认本讲教案，再确认讲稿。",
                )
            if lesson.get("working_script_revision_id") != revision_id:
                raise TeacherLessonAuthoringError(
                    "lesson_script_revision_conflict",
                    "只能确认当前讲稿工作稿。",
                )
            revision = next(
                (
                    item for item in lesson.get("script_revisions") or []
                    if isinstance(item, dict) and item.get("revision_id") == revision_id
                ),
                None,
            )
            if not isinstance(revision, dict):
                raise TeacherLessonAuthoringError(
                    "lesson_script_revision_not_found",
                    "讲稿修订不存在。",
                )
            if revision.get("source_lesson_plan_revision_id") != source_plan_revision:
                raise TeacherLessonAuthoringError(
                    "lesson_plan_revision_conflict",
                    "讲稿对应的教案已经变化，请重新生成讲稿。",
                )
            lesson["script_confirmation"] = {
                "confirmed_revision_id": revision_id,
                "source_lesson_plan_revision_id": source_plan_revision,
                "source_state": "current",
                "confirmed_at": _now(),
            }
            for asset in lesson.get("ppt_assets") or []:
                if not isinstance(asset, dict):
                    continue
                source_revision = str(asset.get("source_script_revision_id") or "")
                if asset.get("engine") == "slide_deck_v6" and source_revision != revision_id:
                    asset["source_state"] = "stale"
            saved = self._save(value)
            return deepcopy(saved["lessons"][lesson_unit_id])

    def save_ai_candidate(
        self,
        course_id: str,
        lesson_unit_id: str,
        *,
        base_revision_id: str,
        instruction: str,
        plan: dict[str, Any],
        section_node_id: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            if not isinstance(lesson, dict):
                raise TeacherLessonAuthoringError("lesson_plan_not_found", "本讲还没有可优化的教案。")
            if lesson.get("working_revision_id") != base_revision_id:
                raise TeacherLessonAuthoringError("lesson_plan_revision_conflict", "教案草稿已经变化，请重新生成 AI 候选。")
            candidate = {
                "candidate_id": f"tlpc-{uuid.uuid4().hex}",
                "lesson_unit_id": lesson_unit_id,
                "base_revision_id": base_revision_id,
                "instruction": instruction,
                "section_node_id": section_node_id,
                "plan": deepcopy(plan),
                "status": "pending",
                "created_at": _now(),
            }
            lesson.setdefault("ai_candidates", []).append(candidate)
            self._save(value)
            return deepcopy(candidate)

    def resolve_ai_candidate(
        self,
        course_id: str,
        lesson_unit_id: str,
        candidate_id: str,
        *,
        accept: bool,
        quality_report: dict[str, Any] | None = None,
        actor: str = "teacher",
    ) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            if not isinstance(lesson, dict):
                raise TeacherLessonAuthoringError("lesson_plan_not_found", "本讲还没有可优化的教案。")
            candidate = next(
                (
                    item for item in lesson.get("ai_candidates") or []
                    if isinstance(item, dict) and item.get("candidate_id") == candidate_id
                ),
                None,
            )
            if candidate is None:
                raise TeacherLessonAuthoringError("lesson_plan_candidate_not_found", "AI 教案候选不存在。")
            if candidate.get("status") != "pending":
                return deepcopy(lesson)
            if lesson.get("working_revision_id") != candidate.get("base_revision_id"):
                raise TeacherLessonAuthoringError("lesson_plan_revision_conflict", "教案草稿已经变化，不能覆盖新修改。")
            candidate["status"] = "accepted" if accept else "rejected"
            candidate["resolved_at"] = _now()
            if not accept:
                saved = self._save(value)
                return deepcopy(saved["lessons"][lesson_unit_id])
            source_outline_revision_id = str(value.get("outline_revision_id") or "")
            plan = deepcopy(candidate.get("plan") or {})
            self._save(value)
        return self.save_plan_revision(
            course_id,
            lesson_unit_id,
            plan,
            source_outline_revision_id=source_outline_revision_id,
            generation_source="ai_optimization",
            quality_report=quality_report,
            actor=actor,
        )

    def view(self, course_id: str) -> dict[str, Any]:
        return self.load(course_id)


Planner = Callable[[dict[str, Any], str, Callable[..., Awaitable[None]]], Awaitable[dict[str, Any]]]


class TeacherLessonAuthoringService:
    def __init__(self, repository: TeacherLessonAuthoringRepository):
        self.repository = repository

    @staticmethod
    def _quality_report(
        course_data: dict[str, Any],
        lesson_unit_id: str,
        plan: dict[str, Any],
        *,
        expected_outline_revision_id: str,
        source_outline_revision_id: str,
    ) -> dict[str, Any]:
        scope = lesson_scope(course_data, lesson_unit_id)
        return validate_teacher_lesson_plan(
            plan,
            expected_section_ids=[
                str(item.get("node_id") or "")
                for item in scope["sections"]
            ],
            expected_outline_revision_id=expected_outline_revision_id,
            source_outline_revision_id=source_outline_revision_id,
        )

    def save_plan_draft(
        self,
        *,
        course_id: str,
        lesson_unit_id: str,
        course_data: dict[str, Any],
        plan: dict[str, Any],
        source_outline_revision_id: str,
        actor: str,
    ) -> dict[str, Any]:
        canonical_outline_revision = str(
            self.repository.view(course_id).get("outline_revision_id") or ""
        )
        effective_source_revision = (
            source_outline_revision_id or canonical_outline_revision
        )
        quality_report = self._quality_report(
            course_data,
            lesson_unit_id,
            plan,
            expected_outline_revision_id=canonical_outline_revision,
            source_outline_revision_id=effective_source_revision,
        )
        return self.repository.save_plan_revision(
            course_id,
            lesson_unit_id,
            plan,
            source_outline_revision_id=effective_source_revision,
            generation_source="teacher_edit",
            quality_report=quality_report,
            actor=actor,
        )

    def confirm_plan(
        self,
        *,
        course_id: str,
        lesson_unit_id: str,
        course_data: dict[str, Any],
        revision_id: str,
    ) -> dict[str, Any]:
        lesson = self.repository.lesson(course_id, lesson_unit_id)
        revision = next(
            (
                item for item in lesson.get("revisions") or []
                if isinstance(item, dict) and item.get("revision_id") == revision_id
            ),
            None,
        )
        if not isinstance(revision, dict):
            raise TeacherLessonAuthoringError(
                "lesson_plan_revision_not_found",
                "教案修订不存在。",
            )
        canonical_outline_revision = str(
            self.repository.view(course_id).get("outline_revision_id") or ""
        )
        quality_report = self._quality_report(
            course_data,
            lesson_unit_id,
            revision.get("plan") or {},
            expected_outline_revision_id=canonical_outline_revision,
            source_outline_revision_id=str(
                revision.get("source_outline_revision_id") or ""
            ),
        )
        return self.repository.confirm_plan_revision(
            course_id,
            lesson_unit_id,
            revision_id,
            quality_report=quality_report,
        )

    def resolve_ai_candidate(
        self,
        *,
        course_id: str,
        lesson_unit_id: str,
        course_data: dict[str, Any],
        candidate_id: str,
        accept: bool,
        actor: str,
    ) -> dict[str, Any]:
        lesson = self.repository.lesson(course_id, lesson_unit_id)
        candidate = next(
            (
                item for item in lesson.get("ai_candidates") or []
                if isinstance(item, dict)
                and item.get("candidate_id") == candidate_id
            ),
            None,
        )
        if not isinstance(candidate, dict) or not accept:
            return self.repository.resolve_ai_candidate(
                course_id,
                lesson_unit_id,
                candidate_id,
                accept=accept,
                actor=actor,
            )
        canonical_outline_revision = str(
            self.repository.view(course_id).get("outline_revision_id") or ""
        )
        quality_report = self._quality_report(
            course_data,
            lesson_unit_id,
            candidate.get("plan") or {},
            expected_outline_revision_id=canonical_outline_revision,
            source_outline_revision_id=canonical_outline_revision,
        )
        return self.repository.resolve_ai_candidate(
            course_id,
            lesson_unit_id,
            candidate_id,
            accept=True,
            quality_report=quality_report,
            actor=actor,
        )

    async def run_plan_job(
        self,
        *,
        course_id: str,
        lesson_unit_id: str,
        job_id: str,
        course_data: dict[str, Any],
        planner: Planner,
    ) -> dict[str, Any]:
        self.repository.update_job(
            course_id,
            job_id,
            status="running",
            phase="lesson_plan_generation",
            progress=5,
            message="正在生成本讲全部小节教案",
        )

        async def on_progress(
            phase: str,
            progress: int,
            message: str,
            _phase_progress: int = 0,
            phase_detail: dict[str, Any] | None = None,
        ) -> None:
            changes: dict[str, Any] = {
                "phase": phase,
                "progress": max(5, min(95, int(progress))),
                "message": message,
            }
            detail = phase_detail or {}
            stream_event = str(detail.get("stream_event") or "")
            batch_id = str(detail.get("stream_batch_id") or "")
            if stream_event in {"reset", "delta"} and batch_id:
                self.repository.update_job_stream(
                    course_id,
                    job_id,
                    phase=phase,
                    progress=changes["progress"],
                    message=message,
                    batch_id=batch_id,
                    event=stream_event,
                    delta=str(detail.get("stream_delta") or ""),
                )
                return
            self.repository.update_job(
                course_id,
                job_id,
                **changes,
            )

        try:
            result = await planner(course_data, lesson_unit_id, on_progress)
            plan = result.get("plan") if isinstance(result, dict) else None
            if not isinstance(plan, dict) or not plan.get("sections"):
                raise TeacherLessonAuthoringError(
                    "lesson_plan_empty",
                    "本讲教案生成结果为空。",
                )
            plan = normalize_teacher_lesson_plan(plan)
            warnings = list(result.get("warnings") or [])
            generation_source = str(result.get("generation_source") or ("deterministic_local_fallback" if warnings else "model"))
            source_refs = [
                deepcopy(item)
                for item in result.get("source_refs") or []
                if isinstance(item, dict)
            ]
            outline_revision = str(
                result.get("source_outline_revision_id")
                or self.repository.get_job(course_id, job_id).get("source_outline_revision_id")
                or ""
            )
            quality_report = self._quality_report(
                course_data,
                lesson_unit_id,
                plan,
                expected_outline_revision_id=str(
                    self.repository.view(course_id).get("outline_revision_id")
                    or outline_revision
                ),
                source_outline_revision_id=outline_revision,
            )
            if not quality_report.get("passed"):
                warnings.extend({
                    **deepcopy(item),
                    "severity": "blocking",
                    "source": "standard_lesson_plan_quality",
                } for item in quality_report.get("blocking_issues") or [])
            lesson = self.repository.save_plan_revision(
                course_id,
                lesson_unit_id,
                plan,
                source_outline_revision_id=outline_revision,
                generation_source=generation_source,
                warnings=warnings,
                source_refs=source_refs,
                quality_report=quality_report,
            )
            status = "completed_with_warnings" if warnings else "completed"
            current_job = self.repository.get_job(course_id, job_id)
            return self.repository.update_job(
                course_id,
                job_id,
                status=status,
                phase="lesson_plan_ready",
                progress=100,
                message=(
                    "本讲教案已生成"
                    if not warnings
                    else "模型内容校验未通过；已保留可编辑基础稿，请审核或 AI 优化后再确认"
                ),
                warnings=warnings,
                result_revision_id=lesson.get("working_revision_id"),
                stream_sequence=int(current_job.get("stream_sequence") or 0) + 1,
                stream_complete=True,
                error=None,
            )
        except Exception as exc:
            if isinstance(exc, asyncio.CancelledError):
                raise
            code = exc.code if isinstance(exc, TeacherLessonAuthoringError) else "lesson_plan_generation_failed"
            current_job = self.repository.get_job(course_id, job_id)
            return self.repository.update_job(
                course_id,
                job_id,
                status="failed",
                phase="lesson_plan_failed",
                message="本讲教案生成失败",
                stream_sequence=int(current_job.get("stream_sequence") or 0) + 1,
                stream_complete=True,
                error={"code": code, "message": str(exc), "retryable": True},
            )

    async def run_ppt_job(
        self,
        *,
        course_id: str,
        lesson_unit_id: str,
        job_id: str,
        source_revision_id: str,
        source: dict[str, Any],
        generator: Callable[[dict[str, Any], Callable[..., Awaitable[None]]], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        self.repository.update_job(
            course_id,
            job_id,
            status="running",
            phase="lesson_ppt_generation",
            progress=5,
            message="正在生成本讲 PPT",
        )

        async def on_progress(phase: str, progress: int, message: str) -> None:
            self.repository.update_job(
                course_id,
                job_id,
                phase=phase,
                progress=max(5, min(95, int(progress))),
                message=message,
            )

        try:
            result = await generator(source, on_progress)
            deck = result.get("deck") if isinstance(result, dict) else None
            if not isinstance(deck, dict) or not deck.get("slides"):
                raise TeacherLessonAuthoringError("lesson_ppt_empty", "本讲 PPT 生成结果为空。")
            warnings = list(result.get("warnings") or [])
            asset = self.repository.save_ppt_revision(
                course_id,
                lesson_unit_id,
                deck,
                source_lesson_plan_revision_id=source_revision_id,
                generation_source=str(result.get("generation_source") or "model"),
                warnings=warnings,
            )
            status = "completed_with_warnings" if warnings else "completed"
            return self.repository.update_job(
                course_id,
                job_id,
                status=status,
                phase="lesson_ppt_ready",
                progress=100,
                message="本讲 PPT 已生成" if not warnings else "本讲基础 PPT 已生成，建议继续 AI 优化",
                warnings=warnings,
                result_revision_id=asset.get("working_revision_id"),
                result_asset_id=asset.get("asset_id"),
                error=None,
            )
        except Exception as exc:
            if isinstance(exc, asyncio.CancelledError):
                raise
            code = exc.code if isinstance(exc, TeacherLessonAuthoringError) else "lesson_ppt_generation_failed"
            return self.repository.update_job(
                course_id,
                job_id,
                status="failed",
                phase="lesson_ppt_failed",
                message="本讲 PPT 生成失败",
                error={"code": code, "message": str(exc), "retryable": True},
            )
