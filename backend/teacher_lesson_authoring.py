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
import re
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
from lesson_arrangement import normalize_lesson_arrangement
from teacher_script import (
    SCRIPT_PIPELINE_VERSION,
    SCRIPT_QUALITY_VERSION,
    compile_teacher_script_module_contract,
    normalize_teacher_script_section,
    validate_teacher_script_section,
)


SCHEMA_VERSION = "teacher_lesson_authoring_v1"
LESSON_PLAN_PIPELINE_VERSION = "standard_lesson_plan_v1"
TEACHER_ASSET_JOB_SCHEMA_VERSION = "teacher_asset_job_v1"
LESSON_JOB_STALE_SECONDS = 300
JOB_TYPES = {
    "teacher_lesson_plan_generation",
    "teacher_lesson_script_generation",
}


class TeacherLessonAuthoringError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_lesson_asset(lesson_unit_id: str) -> dict[str, Any]:
    return {
        "lesson_unit_id": lesson_unit_id,
        "arrangement": {
            "working_revision_id": "",
            "confirmed_revision_id": "",
            "source_state": "current",
            "revisions": [],
        },
        "working_revision_id": "",
        "confirmed_revision_id": "",
        "source_state": "current",
        "revisions": [],
        "ai_candidates": [],
        "working_script_revision_id": "",
        "script_revisions": [],
        "script_confirmation": {},
        "ppt_manuscript": {},
        "ppt_assets": [],
        "imported_ppt_reviews": [],
    }


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


def extract_uploaded_pptx_review(
    path: Path,
    *,
    asset_id: str,
    filename: str = "",
) -> dict[str, Any]:
    """Build an editable text index while keeping the uploaded PPTX immutable."""
    if path.suffix.lower() != ".pptx":
        raise TeacherLessonAuthoringError(
            "uploaded_ppt_format_unsupported",
            "PPT 审阅目前仅支持 PPTX 文件。",
        )
    try:
        from pptx import Presentation

        presentation = Presentation(path)
    except Exception as exc:
        raise TeacherLessonAuthoringError(
            "uploaded_ppt_parse_failed",
            "PPT 无法解析，请确认文件未损坏。",
        ) from exc

    slides: list[dict[str, Any]] = []
    for slide_number, slide in enumerate(presentation.slides, start=1):
        blocks: list[dict[str, Any]] = []
        for shape_index, shape in enumerate(slide.shapes):
            raw_text = ""
            kind = "text"
            editable = False
            if getattr(shape, "has_text_frame", False):
                raw_text = str(getattr(shape, "text", "") or "")
                editable = True
                shape_name = str(getattr(shape, "name", "") or "").lower()
                if "title" in shape_name or "标题" in shape_name:
                    kind = "title"
            elif getattr(shape, "has_table", False):
                raw_text = "\n".join(
                    str(cell.text or "")
                    for row in shape.table.rows
                    for cell in row.cells
                )
                kind = "table"
            text = "\n".join(line.strip() for line in raw_text.splitlines() if line.strip())
            if not text:
                continue
            blocks.append({
                "block_id": f"uploaded-ppt-{asset_id}-s{slide_number}-b{shape_index}",
                "shape_index": shape_index,
                "kind": kind,
                "text": text,
                "original_text": text,
                "editable": editable,
            })
        if blocks and not any(item.get("kind") == "title" for item in blocks):
            blocks[0]["kind"] = "title"
        title_block = next(
            (item for item in blocks if item.get("kind") == "title"),
            None,
        )
        content_hash = hashlib.sha256(
            json.dumps(blocks, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:24]
        slides.append({
            "slide_id": f"uploaded-ppt-{asset_id}-slide-{slide_number}",
            "slide_number": slide_number,
            "title": str((title_block or {}).get("text") or ""),
            "blocks": blocks,
            "content_hash": content_hash,
        })
    if not slides:
        raise TeacherLessonAuthoringError(
            "uploaded_ppt_empty",
            "PPT 中没有可审阅的页面。",
        )
    return {
        "source_asset_id": asset_id,
        "source_filename": filename or path.name,
        "slides": slides,
    }


def _review_terms(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9_]{3,}|[\u4e00-\u9fff]{2,}", text.lower())
    terms: set[str] = set()
    for word in words:
        terms.add(word)
        if re.fullmatch(r"[\u4e00-\u9fff]{2,}", word):
            terms.update(word[index:index + 2] for index in range(len(word) - 1))
    return terms


def build_uploaded_ppt_review_report(
    slides: list[dict[str, Any]],
    *,
    sources: list[dict[str, Any]],
    reference_units: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return explainable review findings; indexes assist but never publish edits."""
    findings: list[dict[str, Any]] = []
    confirmed_sources = [item for item in sources if item.get("status") == "confirmed"]
    confidence = "high" if len(confirmed_sources) >= 2 else "medium" if sources else "low"

    def add_finding(
        code: str,
        title: str,
        detail: str,
        *,
        slide_id: str = "",
        slide_number: int | None = None,
        severity: str = "suggestion",
        evidence: list[dict[str, Any]] | None = None,
    ) -> None:
        target = slide_id or "deck"
        digest = hashlib.sha256(f"{code}:{target}".encode("utf-8")).hexdigest()[:12]
        findings.append({
            "finding_id": f"ppt-review-{digest}",
            "code": code,
            "title": title,
            "detail": detail,
            "severity": severity,
            "confidence": confidence,
            "slide_id": slide_id,
            "slide_number": slide_number,
            "status": "open",
            "evidence": deepcopy(evidence or []),
        })

    reference_terms = set().union(*(
        _review_terms(str(item.get("text") or "")) for item in reference_units
    )) if reference_units else set()
    slide_terms: dict[str, set[str]] = {}
    for slide in slides:
        slide_id = str(slide.get("slide_id") or "")
        blocks = [item for item in slide.get("blocks") or [] if isinstance(item, dict)]
        text = "\n".join(str(item.get("text") or "") for item in blocks).strip()
        terms = _review_terms(text)
        slide_terms[slide_id] = terms
        slide_number = int(slide.get("slide_number") or 0)
        title = str(slide.get("title") or "").strip()
        if not blocks:
            add_finding(
                "visual_only_slide",
                "该页未识别到可审阅文字",
                "当前只检查到视觉内容，请确认该页是否需要讲解文字或备注。",
                slide_id=slide_id,
                slide_number=slide_number,
            )
        elif not title:
            add_finding(
                "slide_title_missing",
                "该页缺少明确标题",
                "补充页面标题可以让教学进度和学习目标更容易被识别。",
                slide_id=slide_id,
                slide_number=slide_number,
            )
        if len(text) > 260 or len(blocks) > 8:
            add_finding(
                "slide_content_dense",
                "该页文字较密",
                f"已识别 {len(text)} 个字符、{len(blocks)} 个文字块，建议拆分或保留一个主结论。",
                slide_id=slide_id,
                slide_number=slide_number,
            )
        if reference_terms and terms and len(reference_terms & terms) < 2:
            add_finding(
                "slide_alignment_unresolved",
                "与已确认教学内容的对应关系不明确",
                "索引未找到该页与当前教案或讲稿的明确对应，请确认是补充材料还是需要调整。",
                slide_id=slide_id,
                slide_number=slide_number,
                evidence=[{"kind": item.get("kind"), "label": item.get("label"), "revision_id": item.get("revision_id")} for item in confirmed_sources],
            )

    for unit in reference_units:
        unit_terms = _review_terms(str(unit.get("text") or ""))
        if not unit_terms or any(len(unit_terms & terms) >= 2 for terms in slide_terms.values()):
            continue
        label = str(unit.get("label") or "教学内容")
        add_finding(
            "source_unit_not_covered",
            f"未找到“{label}”的明确对应页",
            "已确认的教案或讲稿中包含该内容，但 PPT 索引未找到足够相关的页面。",
            evidence=[{
                "kind": unit.get("kind"),
                "label": label,
                "revision_id": unit.get("revision_id"),
            }],
        )

    return {
        "schema_version": "uploaded_ppt_review_report_v1",
        "generated_at": _now(),
        "sources": deepcopy(sources),
        "findings": findings,
        "summary": {
            "slide_count": len(slides),
            "finding_count": len(findings),
            "high_confidence_count": sum(item.get("confidence") == "high" for item in findings),
        },
    }


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
    payload = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        blocks = [
            block for block in section.get("blocks") or [] if isinstance(block, dict)
        ]
        # Preserve the historic content fingerprint for one-way migrated v1
        # scripts so existing confirmation links remain valid.
        legacy_only = bool(blocks) and all(
            str(block.get("module_id") or "") == "legacy_script" for block in blocks
        )
        item = {
            "section_node_id": str(section.get("section_node_id") or ""),
            "title": str(section.get("title") or ""),
        }
        if blocks and not legacy_only:
            item["blocks"] = [
                {
                    "block_id": str(block.get("block_id") or ""),
                    "module_id": str(block.get("module_id") or ""),
                    "role": str(block.get("role") or ""),
                    "title": str(block.get("title") or ""),
                    "content": str(block.get("content") or ""),
                    "knowledge_names": list(block.get("knowledge_names") or []),
                    "planned_minutes": block.get("planned_minutes"),
                }
                for block in blocks
            ]
        else:
            item["content"] = str(
                (blocks[0].get("content") if legacy_only else section.get("content"))
                or ""
            )
        payload.append(item)
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:24]
    return f"tlsr-{digest}"


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
    script_revision: dict[str, Any],
) -> tuple[Any, dict[str, Any], str]:
    """Adapt one confirmed teacher script revision to the V6 source contracts.

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
    script_revision_id = str(script_revision.get("revision_id") or "")
    if not script_revision_id:
        raise TeacherLessonAuthoringError(
            "lesson_script_source_missing",
            "PPT 必须使用已确认讲稿，当前讲稿修订标识缺失。",
        )
    script_sections = {
        str(item.get("section_node_id") or ""): normalize_teacher_script_section(item)
        for item in script_revision.get("sections") or []
        if isinstance(item, dict) and item.get("section_node_id")
    }
    required_section_ids = [
        str(item.get("node_id") or "") for item in scope["sections"]
    ]
    missing_sections = [
        section_id
        for section_id in required_section_ids
        if section_id not in script_sections
    ]
    if missing_sections:
        raise TeacherLessonAuthoringError(
            "lesson_script_source_incomplete",
            "已确认讲稿没有完整覆盖本讲全部小节，不能生成 PPT。",
            details={"missing_section_node_ids": missing_sections},
        )
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
        blocks: list[dict[str, Any]] = []
        script_section = script_sections.get(section_id) or {}
        all_script_blocks = [
            item for item in script_section.get("blocks") or []
            if isinstance(item, dict) and str(item.get("content") or "").strip()
        ]
        if not all_script_blocks:
            raise TeacherLessonAuthoringError(
                "lesson_script_source_incomplete",
                "已确认讲稿仍有空白小节，不能生成 PPT。",
                details={"section_node_id": section_id},
            )
        for script_block in all_script_blocks:
            module_id = str(script_block.get("module_id") or "core_explanation")
            role = str(script_block.get("role") or module_block_role(module_id))
            if role not in {
                "orientation", "prerequisite", "objective", "concept", "reasoning",
                "example", "counterexample", "application", "activity", "feedback",
                "misconception", "checkpoint", "remediation", "summary", "transfer",
            }:
                role = "concept"
            knowledge_names = [
                str(item) for item in script_block.get("knowledge_names") or []
                if str(item).strip()
            ]
            blocks.append({
                "block_id": str(script_block.get("block_id") or f"{section_id}-{module_id}"),
                "type": role,
                "title": str(script_block.get("title") or module_id),
                "content": str(script_block.get("content") or "").strip(),
                "metadata": {
                    "role": role,
                    "module_id": module_id,
                    "module_instance_id": str(
                        script_block.get("block_id") or f"{section_id}:{module_id}"
                    ),
                    "concept_refs": knowledge_names,
                    "planned_minutes": script_block.get("planned_minutes"),
                    "content_perspective": "neutral",
                    "source_kind": "confirmed_teacher_script_block",
                    "legacy_adapter": module_id == "legacy_script",
                },
            })
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
            "script_content_perspective": "neutral",
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
                if not isinstance(lesson, dict):
                    continue
                arrangement = lesson.get("arrangement") or {}
                arrangement_revision = next(
                    (
                        item for item in arrangement.get("revisions") or []
                        if isinstance(item, dict)
                        and item.get("revision_id") == arrangement.get("working_revision_id")
                    ),
                    None,
                )
                arrangement["source_state"] = (
                    "current"
                    if not arrangement_revision
                    or str(arrangement_revision.get("source_outline_revision_id") or "") == outline_revision_id
                    else "stale"
                )
                lesson["arrangement"] = arrangement
                if not lesson.get("working_revision_id"):
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
                for review in lesson.get("imported_ppt_reviews") or []:
                    if not isinstance(review, dict):
                        continue
                    source_revision = str(review.get("source_outline_revision_id") or "")
                    if source_revision and source_revision != outline_revision_id:
                        review["source_state"] = "stale"
            return self._save(value)

    def save_arrangement_revision(
        self,
        course_id: str,
        lesson_unit_id: str,
        arrangement: dict[str, Any],
        *,
        source_outline_revision_id: str,
        actor: str = "teacher",
        confirm: bool = True,
    ) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            lesson = value.setdefault("lessons", {}).setdefault(
                lesson_unit_id,
                _empty_lesson_asset(lesson_unit_id),
            )
            state = lesson.setdefault("arrangement", {
                "working_revision_id": "",
                "confirmed_revision_id": "",
                "source_state": "current",
                "revisions": [],
            })
            normalized = normalize_lesson_arrangement(
                arrangement,
                lesson_unit_id=lesson_unit_id,
                source_outline_revision_id=source_outline_revision_id,
            )
            revision_id = f"tlar-{uuid.uuid4().hex}"
            revision = {
                **normalized,
                "revision_id": revision_id,
                "status": "confirmed" if confirm else "draft",
                "actor": actor,
                "created_at": _now(),
                **({"confirmed_at": _now()} if confirm else {}),
            }
            state.setdefault("revisions", []).append(revision)
            state["working_revision_id"] = revision_id
            state["source_state"] = (
                "current"
                if not value.get("outline_revision_id")
                or str(value.get("outline_revision_id") or "") == source_outline_revision_id
                else "stale"
            )
            if confirm:
                state["confirmed_revision_id"] = revision_id
            lesson["arrangement"] = state
            if source_outline_revision_id and not value.get("outline_revision_id"):
                value["outline_revision_id"] = source_outline_revision_id
            saved = self._save(value)
            return deepcopy(saved["lessons"][lesson_unit_id])

    def confirmed_arrangement(
        self,
        course_id: str,
        lesson_unit_id: str,
    ) -> dict[str, Any] | None:
        lesson = self.lesson(course_id, lesson_unit_id)
        state = lesson.get("arrangement") or {}
        revision_id = str(state.get("confirmed_revision_id") or "")
        if not revision_id or state.get("source_state", "current") != "current":
            return None
        return deepcopy(next(
            (
                item for item in state.get("revisions") or []
                if isinstance(item, dict) and item.get("revision_id") == revision_id
            ),
            None,
        ))

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
            initial_message = (
                "等待生成本讲讲稿"
                if job_type == "teacher_lesson_script_generation"
                else "等待生成本讲教案"
            )
            job = {
                "schema_version": TEACHER_ASSET_JOB_SCHEMA_VERSION,
                "id": job_id,
                "course_id": course_id,
                "lesson_unit_id": lesson_unit_id,
                "type": job_type,
                "asset_type": (
                    "script"
                    if job_type == "teacher_lesson_script_generation"
                    else "lesson_plan"
                ),
                "state_owner": "teacher_lesson_authoring",
                "request_id": request_id,
                "idempotency_key": request_id,
                "source_outline_revision_id": source_outline_revision_id,
                "status": "pending",
                "progress": 0,
                "phase": "queued",
                "message": initial_message,
                "stream_sequence": 0,
                "stream_batches": {},
                "stream_complete": False,
                "checkpoint": {},
                "cancel_requested": False,
                "retryable": True,
                "warnings": [],
                "error": None,
                "created_at": _now(),
                "heartbeat_at": _now(),
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
            timestamp = _now()
            job["updated_at"] = timestamp
            if str(job.get("status") or "") in {"pending", "running"}:
                job["heartbeat_at"] = timestamp
            if "result_sections" in changes:
                job["checkpoint"] = {
                    "result_sections": deepcopy(changes.get("result_sections") or []),
                    "completed_blocks": int(changes.get("completed_blocks") or 0),
                    "current_block_id": str(changes.get("current_block_id") or ""),
                    "saved_at": timestamp,
                }
            if str(job.get("status") or "") in {
                "completed", "completed_with_warnings", "failed", "cancelled"
            }:
                job["completed_at"] = timestamp
                job["retryable"] = bool(
                    (job.get("error") or {}).get("retryable")
                    if isinstance(job.get("error"), dict)
                    else False
                )
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
                "heartbeat_at": _now(),
                "updated_at": _now(),
            })
            value["jobs"][job_id] = job
            self._save(value)
            return deepcopy(job)

    def cancel_job(self, course_id: str, job_id: str) -> dict[str, Any]:
        """Cancel one durable teacher job while preserving its last checkpoint."""
        with self._lock:
            value = self.load(course_id)
            job = (value.get("jobs") or {}).get(job_id)
            if not isinstance(job, dict):
                raise TeacherLessonAuthoringError(
                    "teacher_job_not_found",
                    "教师讲次任务不存在。",
                )
            if str(job.get("status") or "") in {
                "completed", "completed_with_warnings", "failed", "cancelled"
            }:
                return deepcopy(job)
            timestamp = _now()
            job.update({
                "status": "cancelled",
                "phase": "teacher_asset_job_cancelled",
                "message": "已停止生成，已完成的内容仍然保留",
                "cancel_requested": True,
                "stream_sequence": int(job.get("stream_sequence") or 0) + 1,
                "stream_complete": True,
                "retryable": True,
                "error": {
                    "code": "teacher_asset_job_cancelled",
                    "message": "生成已由教师停止，可以从已保存进度继续。",
                    "retryable": True,
                },
                "completed_at": timestamp,
                "updated_at": timestamp,
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
        source_knowledge_scope_revision_id: str = "",
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
            lesson = value.setdefault("lessons", {}).setdefault(
                lesson_unit_id,
                _empty_lesson_asset(lesson_unit_id),
            )
            revision_id = f"tlpr-{uuid.uuid4().hex}"
            revision = {
                "revision_id": revision_id,
                "lesson_unit_id": lesson_unit_id,
                "source_outline_revision_id": source_outline_revision_id,
                "source_knowledge_scope_revision_id": source_knowledge_scope_revision_id,
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
            manuscript = lesson.get("ppt_manuscript")
            if (
                isinstance(manuscript, dict)
                and manuscript.get("source_lesson_plan_revision_id")
                != revision_id
            ):
                manuscript["source_state"] = "stale"
            for review in lesson.get("imported_ppt_reviews") or []:
                if not isinstance(review, dict):
                    continue
                source_revision = str(review.get("source_lesson_plan_revision_id") or "")
                if source_revision and source_revision != revision_id:
                    review["source_state"] = "stale"
            if source_outline_revision_id and not value.get("outline_revision_id"):
                value["outline_revision_id"] = source_outline_revision_id
            saved = self._save(value)
            return deepcopy(saved["lessons"][lesson_unit_id])

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
        ppt_manuscript_revision: str = "",
        ppt_manuscript_status: str = "draft",
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
                "ppt_manuscript_revision": ppt_manuscript_revision,
                "ppt_manuscript_status": ppt_manuscript_status,
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
            if ppt_manuscript_revision:
                asset["ppt_manuscript_revision"] = ppt_manuscript_revision
                asset["ppt_manuscript_status"] = ppt_manuscript_status
            asset["source_state"] = "current"
            saved = self._save(value)
            return deepcopy(next(item for item in saved["lessons"][lesson_unit_id]["ppt_assets"] if item["asset_id"] == asset["asset_id"]))

    def save_v6_ppt_manuscript(
        self,
        course_id: str,
        lesson_unit_id: str,
        *,
        source_lesson_plan_revision_id: str,
        source_script_revision_id: str,
        source_material_revision: str,
        task_id: str,
        mode: str,
        theme: str,
        manuscript: dict[str, Any],
    ) -> dict[str, Any]:
        """保存无原版 PPT 分支的独立文书工作稿，不提前创建 PPT 资产。"""
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            if not isinstance(lesson, dict):
                raise TeacherLessonAuthoringError(
                    "lesson_plan_not_found", "请先生成并确认本讲教案。"
                )
            confirmation = lesson.get("script_confirmation") or {}
            if (
                lesson.get("confirmed_revision_id")
                != source_lesson_plan_revision_id
                or lesson.get("working_script_revision_id")
                != source_script_revision_id
                or confirmation.get("confirmed_revision_id")
                != source_script_revision_id
                or confirmation.get("source_state", "current") != "current"
            ):
                raise TeacherLessonAuthoringError(
                    "lesson_ppt_source_stale",
                    "教案或讲稿已经变化，请基于已确认的最新内容重新生成 PPT 文书。",
                )
            state = {
                "revision": str(manuscript.get("manuscript_revision") or ""),
                "status": "draft",
                "source_state": "current",
                "source_lesson_plan_revision_id": source_lesson_plan_revision_id,
                "source_script_revision_id": source_script_revision_id,
                "source_material_revision": source_material_revision,
                "task_id": task_id,
                "mode": mode,
                "theme": theme,
                "manuscript": deepcopy(manuscript),
                "created_at": _now(),
                "confirmed_at": "",
                "generated_representation_id": "",
            }
            lesson["ppt_manuscript"] = state
            saved = self._save(value)
            return deepcopy(
                saved["lessons"][lesson_unit_id]["ppt_manuscript"]
            )

    def current_v6_ppt_manuscript(
        self, course_id: str, lesson_unit_id: str
    ) -> dict[str, Any] | None:
        lesson = self.lesson(course_id, lesson_unit_id)
        state = lesson.get("ppt_manuscript")
        return deepcopy(state) if isinstance(state, dict) and state else None

    def confirm_v6_ppt_manuscript_draft(
        self,
        course_id: str,
        lesson_unit_id: str,
        *,
        manuscript_revision: str,
    ) -> dict[str, Any]:
        """确认独立 PPT 文书；确认后才可进入 PPT 编译。"""
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            state = (lesson or {}).get("ppt_manuscript")
            if not isinstance(state, dict) or not state:
                raise TeacherLessonAuthoringError(
                    "lesson_ppt_manuscript_not_found", "请先生成 PPT 文书。"
                )
            if state.get("source_state") != "current":
                raise TeacherLessonAuthoringError(
                    "lesson_ppt_source_stale",
                    "教案或讲稿已经变化，请重新生成 PPT 文书。",
                )
            if str(state.get("revision") or "") != manuscript_revision:
                raise TeacherLessonAuthoringError(
                    "lesson_ppt_manuscript_revision_conflict",
                    "PPT 文书已更新，请刷新后再确认。",
                )
            state["status"] = "confirmed"
            state["confirmed_at"] = _now()
            saved = self._save(value)
            return deepcopy(
                saved["lessons"][lesson_unit_id]["ppt_manuscript"]
            )

    def bind_v6_ppt_manuscript_result(
        self,
        course_id: str,
        lesson_unit_id: str,
        *,
        manuscript_revision: str,
        representation_id: str,
    ) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            state = (lesson or {}).get("ppt_manuscript")
            if (
                not isinstance(state, dict)
                or state.get("status") != "confirmed"
                or state.get("source_state") != "current"
                or state.get("revision") != manuscript_revision
            ):
                raise TeacherLessonAuthoringError(
                    "lesson_ppt_manuscript_not_confirmed",
                    "PPT 文书尚未确认，不能登记生成结果。",
                )
            state["generated_representation_id"] = representation_id
            state["generated_at"] = _now()
            saved = self._save(value)
            return deepcopy(
                saved["lessons"][lesson_unit_id]["ppt_manuscript"]
            )

    def confirm_v6_ppt_manuscript(
        self,
        course_id: str,
        lesson_unit_id: str,
        *,
        representation_id: str,
        manuscript_revision: str,
    ) -> dict[str, Any]:
        """确认逐页 PPT 文书，作为正式导出的显式门。"""
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            if not isinstance(lesson, dict):
                raise TeacherLessonAuthoringError(
                    "lesson_plan_not_found", "请先生成本讲教案。"
                )
            asset = next(
                (
                    item
                    for item in lesson.get("ppt_assets") or []
                    if isinstance(item, dict)
                    and item.get("working_representation_id") == representation_id
                ),
                None,
            )
            if not isinstance(asset, dict):
                raise TeacherLessonAuthoringError(
                    "lesson_ppt_not_found", "本讲 PPT 文书不存在。"
                )
            if asset.get("source_state") != "current":
                raise TeacherLessonAuthoringError(
                    "lesson_ppt_source_stale", "讲稿或教案已更新，请先重新生成 PPT 文书。"
                )
            if str(asset.get("ppt_manuscript_revision") or "") != manuscript_revision:
                raise TeacherLessonAuthoringError(
                    "lesson_ppt_manuscript_revision_conflict",
                    "PPT 文书已更新，请刷新后再确认。",
                )
            asset["ppt_manuscript_status"] = "confirmed"
            for revision in asset.get("v6_revisions") or []:
                if (
                    isinstance(revision, dict)
                    and revision.get("representation_id") == representation_id
                    and revision.get("ppt_manuscript_revision") == manuscript_revision
                ):
                    revision["ppt_manuscript_status"] = "confirmed"
                    revision["ppt_manuscript_confirmed_at"] = _now()
            saved = self._save(value)
            return deepcopy(next(
                item
                for item in saved["lessons"][lesson_unit_id]["ppt_assets"]
                if item["asset_id"] == asset["asset_id"]
            ))

    def save_imported_ppt_review(
        self,
        course_id: str,
        lesson_unit_id: str,
        *,
        package_id: str,
        source_asset_id: str,
        source_filename: str,
        slides: list[dict[str, Any]],
        report: dict[str, Any],
        source_outline_revision_id: str,
        source_lesson_plan_revision_id: str,
        source_script_revision_id: str,
        actor: str,
    ) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            lesson = value.setdefault("lessons", {}).setdefault(
                lesson_unit_id, _empty_lesson_asset(lesson_unit_id)
            )
            for item in lesson.setdefault("imported_ppt_reviews", []):
                if isinstance(item, dict) and item.get("status") == "reviewing":
                    item["status"] = "superseded"
            review_id = f"tlpir-{uuid.uuid4().hex}"
            revision_id = f"tlpivr-{uuid.uuid4().hex}"
            review = {
                "review_id": review_id,
                "lesson_unit_id": lesson_unit_id,
                "package_id": package_id,
                "source_asset_id": source_asset_id,
                "source_filename": source_filename,
                "status": "reviewing",
                "source_state": "current",
                "revision_id": revision_id,
                "source_outline_revision_id": source_outline_revision_id,
                "source_lesson_plan_revision_id": source_lesson_plan_revision_id,
                "source_script_revision_id": source_script_revision_id,
                "slides": deepcopy(slides),
                "report": deepcopy(report),
                "ai_candidates": [],
                "revision_history": [{
                    "revision_id": revision_id,
                    "slides": deepcopy(slides),
                    "actor": actor,
                    "created_at": _now(),
                }],
                "created_at": _now(),
                "updated_at": _now(),
            }
            lesson["imported_ppt_reviews"].append(review)
            saved = self._save(value)
            return deepcopy(saved["lessons"][lesson_unit_id]["imported_ppt_reviews"][-1])

    def current_imported_ppt_review(
        self, course_id: str, lesson_unit_id: str
    ) -> dict[str, Any] | None:
        lesson = self.lesson(course_id, lesson_unit_id)
        reviews = [
            item for item in lesson.get("imported_ppt_reviews") or []
            if isinstance(item, dict) and item.get("status") in {"reviewing", "confirmed"}
        ]
        return deepcopy(reviews[-1]) if reviews else None

    def replace_imported_ppt_review(
        self,
        course_id: str,
        lesson_unit_id: str,
        *,
        review_id: str,
        base_revision_id: str,
        slides: list[dict[str, Any]],
        report: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            review = next(
                (item for item in (lesson or {}).get("imported_ppt_reviews") or []
                 if isinstance(item, dict) and item.get("review_id") == review_id),
                None,
            )
            if not isinstance(review, dict):
                raise TeacherLessonAuthoringError("uploaded_ppt_review_not_found", "PPT 审阅记录不存在。")
            if review.get("revision_id") != base_revision_id:
                raise TeacherLessonAuthoringError("uploaded_ppt_revision_conflict", "PPT 工作稿已更新，请刷新后再修改。")
            revision_id = f"tlpivr-{uuid.uuid4().hex}"
            review["slides"] = deepcopy(slides)
            review["report"] = deepcopy(report)
            review["revision_id"] = revision_id
            review["status"] = "reviewing"
            review["updated_at"] = _now()
            review.setdefault("revision_history", []).append({
                "revision_id": revision_id,
                "slides": deepcopy(slides),
                "actor": actor,
                "created_at": _now(),
            })
            saved = self._save(value)
            return deepcopy(next(
                item for item in saved["lessons"][lesson_unit_id]["imported_ppt_reviews"]
                if item.get("review_id") == review_id
            ))

    def save_imported_ppt_ai_candidate(
        self,
        course_id: str,
        lesson_unit_id: str,
        *,
        review_id: str,
        base_revision_id: str,
        slide_id: str,
        instruction: str,
        proposed_blocks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            review = next((item for item in (lesson or {}).get("imported_ppt_reviews") or [] if isinstance(item, dict) and item.get("review_id") == review_id), None)
            if not isinstance(review, dict):
                raise TeacherLessonAuthoringError("uploaded_ppt_review_not_found", "PPT 审阅记录不存在。")
            if review.get("revision_id") != base_revision_id:
                raise TeacherLessonAuthoringError("uploaded_ppt_revision_conflict", "PPT 工作稿已更新，请重新生成 AI 候选。")
            for item in review.get("ai_candidates") or []:
                if isinstance(item, dict) and item.get("status") == "pending":
                    item["status"] = "superseded"
            candidate = {
                "candidate_id": f"tlpiac-{uuid.uuid4().hex}",
                "base_revision_id": base_revision_id,
                "slide_id": slide_id,
                "instruction": instruction,
                "proposed_blocks": deepcopy(proposed_blocks),
                "status": "pending",
                "created_at": _now(),
            }
            review.setdefault("ai_candidates", []).append(candidate)
            self._save(value)
            return deepcopy(candidate)

    def mark_imported_ppt_ai_candidate(
        self,
        course_id: str,
        lesson_unit_id: str,
        *,
        review_id: str,
        candidate_id: str,
        status: str,
    ) -> dict[str, Any]:
        if status not in {"accepted", "rejected", "superseded"}:
            raise ValueError("unsupported imported PPT candidate status")
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            review = next((item for item in (lesson or {}).get("imported_ppt_reviews") or [] if isinstance(item, dict) and item.get("review_id") == review_id), None)
            candidate = next((item for item in (review or {}).get("ai_candidates") or [] if isinstance(item, dict) and item.get("candidate_id") == candidate_id), None)
            if not isinstance(candidate, dict):
                raise TeacherLessonAuthoringError("uploaded_ppt_candidate_not_found", "AI PPT 修改候选不存在。")
            if candidate.get("status") == "pending":
                candidate["status"] = status
                candidate["resolved_at"] = _now()
                self._save(value)
            return deepcopy(candidate)

    def confirm_imported_ppt_review(
        self,
        course_id: str,
        lesson_unit_id: str,
        *,
        review_id: str,
        revision_id: str,
    ) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            review = next((item for item in (lesson or {}).get("imported_ppt_reviews") or [] if isinstance(item, dict) and item.get("review_id") == review_id), None)
            if not isinstance(review, dict):
                raise TeacherLessonAuthoringError("uploaded_ppt_review_not_found", "PPT 审阅记录不存在。")
            if review.get("revision_id") != revision_id:
                raise TeacherLessonAuthoringError("uploaded_ppt_revision_conflict", "PPT 工作稿已更新，请刷新后再确认。")
            if review.get("source_state") != "current":
                raise TeacherLessonAuthoringError("uploaded_ppt_source_stale", "上游教学内容已更新，请先重新审阅。")
            review["status"] = "confirmed"
            review["confirmed_revision_id"] = revision_id
            review["confirmed_at"] = _now()
            assets = lesson.setdefault("ppt_assets", [])
            for asset in assets:
                if isinstance(asset, dict) and asset.get("role") == "primary":
                    asset["role"] = "supplemental"
            assets.append({
                "asset_id": f"tlpa-{uuid.uuid4().hex}",
                "lesson_unit_id": lesson_unit_id,
                "role": "primary",
                "engine": "uploaded_pptx",
                "working_revision_id": revision_id,
                "source_lesson_plan_revision_id": str(review.get("source_lesson_plan_revision_id") or ""),
                "source_script_revision_id": str(review.get("source_script_revision_id") or ""),
                "source_state": "current",
                "package_id": str(review.get("package_id") or ""),
                "source_asset_id": str(review.get("source_asset_id") or ""),
                "review_id": review_id,
                "confirmed_at": review["confirmed_at"],
                "revisions": [],
                "ai_candidates": [],
            })
            saved = self._save(value)
            return deepcopy(next(item for item in saved["lessons"][lesson_unit_id]["imported_ppt_reviews"] if item.get("review_id") == review_id))

    def save_v6_ppt_ai_candidate(
        self,
        course_id: str,
        lesson_unit_id: str,
        *,
        representation_id: str,
        base_spec_id: str,
        base_spec_revision: str,
        page_id: str,
        instruction: str,
        candidate_page: dict[str, Any],
        changed_fields: list[str],
    ) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            asset = next(
                (
                    item for item in (lesson or {}).get("ppt_assets") or []
                    if isinstance(item, dict)
                    and item.get("role") == "primary"
                    and item.get("engine") == "slide_deck_v6"
                ),
                None,
            )
            if not isinstance(asset, dict):
                raise TeacherLessonAuthoringError(
                    "lesson_ppt_not_found", "本讲还没有可优化的 V6 PPT。"
                )
            if (
                asset.get("working_representation_id") != representation_id
                or not any(
                    isinstance(item, dict)
                    and item.get("spec_id") == base_spec_id
                    and item.get("representation_id") == representation_id
                    for item in asset.get("v6_revisions") or []
                )
            ):
                raise TeacherLessonAuthoringError(
                    "lesson_ppt_revision_conflict",
                    "PPT 工作稿已经变化，请重新生成 AI 候选。",
                )
            for item in asset.get("v6_ai_candidates") or []:
                if isinstance(item, dict) and item.get("status") == "pending":
                    item["status"] = "superseded"
                    item["resolved_at"] = _now()
            candidate = {
                "candidate_id": f"tlv6ac-{uuid.uuid4().hex}",
                "representation_id": representation_id,
                "base_spec_id": base_spec_id,
                "base_spec_revision": base_spec_revision,
                "page_id": page_id,
                "instruction": instruction,
                "candidate_page": deepcopy(candidate_page),
                "changed_fields": list(changed_fields),
                "status": "pending",
                "created_at": _now(),
            }
            asset.setdefault("v6_ai_candidates", []).append(candidate)
            self._save(value)
            return deepcopy(candidate)

    def pending_v6_ppt_ai_candidate(
        self,
        course_id: str,
        lesson_unit_id: str,
        *,
        representation_id: str,
        spec_id: str,
        spec_revision: str,
    ) -> dict[str, Any] | None:
        lesson = self.lesson(course_id, lesson_unit_id)
        for asset in lesson.get("ppt_assets") or []:
            if not isinstance(asset, dict) or asset.get("role") != "primary":
                continue
            for candidate in reversed(asset.get("v6_ai_candidates") or []):
                if (
                    isinstance(candidate, dict)
                    and candidate.get("status") == "pending"
                    and candidate.get("representation_id") == representation_id
                    and candidate.get("base_spec_id") == spec_id
                    and candidate.get("base_spec_revision") == spec_revision
                ):
                    return deepcopy(candidate)
        return None

    def mark_v6_ppt_ai_candidate(
        self,
        course_id: str,
        lesson_unit_id: str,
        candidate_id: str,
        *,
        status: str,
        result_spec_id: str = "",
    ) -> dict[str, Any]:
        if status not in {"accepted", "rejected", "superseded"}:
            raise ValueError("unsupported V6 candidate status")
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            candidate = next(
                (
                    candidate
                    for asset in (lesson or {}).get("ppt_assets") or []
                    if isinstance(asset, dict)
                    for candidate in asset.get("v6_ai_candidates") or []
                    if isinstance(candidate, dict)
                    and candidate.get("candidate_id") == candidate_id
                ),
                None,
            )
            if not isinstance(candidate, dict):
                raise TeacherLessonAuthoringError(
                    "lesson_ppt_candidate_not_found", "AI PPT 候选不存在。"
                )
            if candidate.get("status") == "pending":
                candidate["status"] = status
                candidate["resolved_at"] = _now()
                if result_spec_id:
                    candidate["result_spec_id"] = result_spec_id
                self._save(value)
            return deepcopy(candidate)

    def get_job(self, course_id: str, job_id: str) -> dict[str, Any]:
        value = self.load(course_id)
        job = (value.get("jobs") or {}).get(job_id)
        if not isinstance(job, dict):
            raise TeacherLessonAuthoringError("teacher_job_not_found", "教师讲次任务不存在。")
        return deepcopy(job)

    def expire_stale_job(
        self,
        course_id: str,
        job_id: str,
        *,
        stale_after_seconds: int = LESSON_JOB_STALE_SECONDS,
    ) -> dict[str, Any]:
        """Close an orphaned generation job left behind by a process reload."""
        with self._lock:
            value = self.load(course_id)
            job = (value.get("jobs") or {}).get(job_id)
            if not isinstance(job, dict):
                raise TeacherLessonAuthoringError("teacher_job_not_found", "教师讲次任务不存在。")
            if str(job.get("status") or "") not in {"pending", "running"}:
                return deepcopy(job)
            try:
                updated_at = datetime.fromisoformat(
                    str(job.get("updated_at") or "").replace("Z", "+00:00")
                )
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
            except ValueError:
                updated_at = datetime.fromtimestamp(0, tz=timezone.utc)
            age_seconds = (datetime.now(timezone.utc) - updated_at).total_seconds()
            if age_seconds < max(1, int(stale_after_seconds)):
                return deepcopy(job)
            script_job = str(job.get("type") or "") == "teacher_lesson_script_generation"
            job.update({
                "status": "failed",
                "phase": (
                    "lesson_script_interrupted"
                    if script_job
                    else "lesson_plan_interrupted"
                ),
                "message": (
                    "讲稿生成进程已中断"
                    if script_job
                    else "教案生成进程已中断"
                ),
                "stream_sequence": int(job.get("stream_sequence") or 0) + 1,
                "stream_complete": True,
                "error": {
                    "code": (
                        "lesson_script_generation_interrupted"
                        if script_job
                        else "lesson_plan_generation_interrupted"
                    ),
                    "message": (
                        "生成进程已中断，已完成的讲稿块仍然保留，可以继续生成。"
                        if script_job
                        else "生成进程已中断，请重新生成本讲教案。"
                    ),
                    "retryable": True,
                },
                "updated_at": _now(),
            })
            value["jobs"][job_id] = job
            saved = self._save(value)
            return deepcopy(saved["jobs"][job_id])

    def lesson(self, course_id: str, lesson_unit_id: str) -> dict[str, Any]:
        value = self.load(course_id)
        lesson = (value.get("lessons") or {}).get(lesson_unit_id)
        if not isinstance(lesson, dict):
            return _empty_lesson_asset(lesson_unit_id)
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
        expected_working_revision_id: str | None = None,
    ) -> dict[str, Any]:
        normalized_sections = []
        for item in sections:
            if not isinstance(item, dict):
                continue
            normalized = normalize_teacher_script_section(item)
            quality_report = deepcopy(item.get("quality_report") or {})
            if not quality_report:
                quality_report = {
                    "schema_version": SCRIPT_QUALITY_VERSION,
                    "pipeline_version": "legacy_script_adapter_v1",
                    "passed": True,
                    "blocking_issues": [],
                    "review_issues": [{
                        "code": "teacher_script:legacy_adapter",
                        "message": "该讲稿由旧正文兼容迁移，建议教师确认教学块边界。",
                    }],
                    "metrics": {"block_count": len(normalized.get("blocks") or [])},
                }
            normalized["quality_report"] = quality_report
            normalized["pipeline_version"] = str(
                item.get("pipeline_version")
                or quality_report.get("pipeline_version")
                or SCRIPT_PIPELINE_VERSION
            )
            normalized_sections.append(normalized)
        if not normalized_sections or any(
            not item["section_node_id"]
            or not item["content"]
            or not item.get("blocks")
            for item in normalized_sections
        ):
            raise TeacherLessonAuthoringError(
                "lesson_script_incomplete",
                "本讲仍有小节没有讲稿内容，暂时不能保存。",
            )
        blocking_issues = [
            {
                **deepcopy(issue),
                "section_node_id": str(section.get("section_node_id") or ""),
            }
            for section in normalized_sections
            for issue in (section.get("quality_report") or {}).get("blocking_issues") or []
            if isinstance(issue, dict)
        ]
        review_issues = [
            {
                **deepcopy(issue),
                "section_node_id": str(section.get("section_node_id") or ""),
            }
            for section in normalized_sections
            for issue in (section.get("quality_report") or {}).get("review_issues") or []
            if isinstance(issue, dict)
        ]
        revision_quality = {
            "schema_version": SCRIPT_QUALITY_VERSION,
            "pipeline_version": SCRIPT_PIPELINE_VERSION,
            "passed": not blocking_issues,
            "blocking_issues": blocking_issues,
            "review_issues": review_issues,
            "metrics": {
                "section_count": len(normalized_sections),
                "block_count": sum(
                    len(section.get("blocks") or []) for section in normalized_sections
                ),
            },
        }
        revision_id = teacher_lesson_script_sections_revision(normalized_sections)
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            if not isinstance(lesson, dict):
                raise TeacherLessonAuthoringError(
                    "lesson_plan_not_found",
                    "请先生成并确认本讲教案。",
                )
            if (
                expected_working_revision_id is not None
                and lesson.get("working_script_revision_id")
                != expected_working_revision_id
            ):
                raise TeacherLessonAuthoringError(
                    "lesson_script_revision_conflict",
                    "讲稿工作稿已经变化，请基于当前版本重新修改。",
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
                    "quality_report": revision_quality,
                    "pipeline_version": SCRIPT_PIPELINE_VERSION,
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
            manuscript = lesson.get("ppt_manuscript")
            if (
                isinstance(manuscript, dict)
                and manuscript.get("source_script_revision_id") != revision_id
            ):
                manuscript["source_state"] = "stale"
            for review in lesson.get("imported_ppt_reviews") or []:
                if not isinstance(review, dict):
                    continue
                source_revision = str(review.get("source_script_revision_id") or "")
                if source_revision and source_revision != revision_id:
                    review["source_state"] = "stale"
            saved = self._save(value)
            return deepcopy(saved["lessons"][lesson_unit_id])

    def save_script_ai_candidate(
        self,
        course_id: str,
        lesson_unit_id: str,
        *,
        base_revision_id: str,
        section_node_id: str,
        instruction: str,
        replacement_text: str,
        source_lesson_plan_revision_id: str,
        material_asset_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            if not isinstance(lesson, dict):
                raise TeacherLessonAuthoringError(
                    "lesson_plan_not_found",
                    "请先生成并确认本讲教案。",
                )
            if lesson.get("working_script_revision_id") != base_revision_id:
                raise TeacherLessonAuthoringError(
                    "lesson_script_revision_conflict",
                    "讲稿工作稿已经变化，请重新生成 AI 候选。",
                )
            for item in lesson.get("script_ai_candidates") or []:
                if isinstance(item, dict) and item.get("status") == "pending":
                    item["status"] = "superseded"
                    item["resolved_at"] = _now()
            candidate = {
                "candidate_id": f"tlsac-{uuid.uuid4().hex}",
                "lesson_unit_id": lesson_unit_id,
                "base_revision_id": base_revision_id,
                "source_lesson_plan_revision_id": source_lesson_plan_revision_id,
                "section_node_id": section_node_id,
                "instruction": instruction,
                "replacement_text": replacement_text,
                "material_asset_ids": list(dict.fromkeys(
                    str(item).strip()
                    for item in material_asset_ids or []
                    if str(item).strip()
                )),
                "status": "pending",
                "created_at": _now(),
            }
            lesson.setdefault("script_ai_candidates", []).append(candidate)
            self._save(value)
            return deepcopy(candidate)

    def script_ai_candidate(
        self,
        course_id: str,
        lesson_unit_id: str,
        candidate_id: str,
    ) -> dict[str, Any]:
        lesson = self.lesson(course_id, lesson_unit_id)
        candidate = next(
            (
                item for item in lesson.get("script_ai_candidates") or []
                if isinstance(item, dict) and item.get("candidate_id") == candidate_id
            ),
            None,
        )
        if not isinstance(candidate, dict):
            raise TeacherLessonAuthoringError(
                "lesson_script_candidate_not_found",
                "AI 讲稿候选不存在。",
            )
        return deepcopy(candidate)

    def mark_script_ai_candidate(
        self,
        course_id: str,
        lesson_unit_id: str,
        candidate_id: str,
        *,
        status: str,
        result_revision_id: str = "",
    ) -> dict[str, Any]:
        if status not in {"accepted", "rejected", "superseded"}:
            raise ValueError("unsupported script candidate status")
        with self._lock:
            value = self.load(course_id)
            lesson = (value.get("lessons") or {}).get(lesson_unit_id)
            candidate = next(
                (
                    item for item in (lesson or {}).get("script_ai_candidates") or []
                    if isinstance(item, dict) and item.get("candidate_id") == candidate_id
                ),
                None,
            )
            if not isinstance(candidate, dict):
                raise TeacherLessonAuthoringError(
                    "lesson_script_candidate_not_found",
                    "AI 讲稿候选不存在。",
                )
            if candidate.get("status") == "pending":
                candidate["status"] = status
                candidate["resolved_at"] = _now()
                if result_revision_id:
                    candidate["result_revision_id"] = result_revision_id
                self._save(value)
            return deepcopy(candidate)

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
            quality_report = revision.get("quality_report") or {}
            if quality_report and not quality_report.get("passed"):
                raise TeacherLessonAuthoringError(
                    "lesson_script_quality_blocked",
                    "讲稿仍有未通过的教学结构检查，请修正后再确认。",
                    details={
                        "quality_report": deepcopy(quality_report),
                    },
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
            manuscript = lesson.get("ppt_manuscript")
            if (
                isinstance(manuscript, dict)
                and manuscript.get("source_script_revision_id") != revision_id
            ):
                manuscript["source_state"] = "stale"
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
        material_asset_ids: list[str] | None = None,
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
                "material_asset_ids": sorted({
                    str(value).strip()
                    for value in (material_asset_ids or [])
                    if str(value).strip()
                }),
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
            if self.repository.get_job(course_id, job_id).get("cancel_requested"):
                raise asyncio.CancelledError
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
            if self.repository.get_job(course_id, job_id).get("cancel_requested"):
                raise asyncio.CancelledError
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
            job_source_revision = str(
                self.repository.get_job(course_id, job_id).get("source_outline_revision_id")
                or ""
            )
            knowledge_scope_revision = str(
                result.get("source_outline_revision_id") or ""
            )
            outline_revision = job_source_revision or knowledge_scope_revision
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
                source_knowledge_scope_revision_id=knowledge_scope_revision,
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

    async def run_script_job(
        self,
        *,
        course_id: str,
        lesson_unit_id: str,
        job_id: str,
        source_plan_revision_id: str,
        outline_sections: list[dict[str, Any]],
        plan_sections: dict[str, dict[str, Any]],
        generator: Callable[
            [dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]],
            Awaitable[str],
        ],
        seed_sections: list[dict[str, Any]] | None = None,
        requirements: str = "",
        material_asset_ids: list[str] | None = None,
        actor: str = "teacher",
    ) -> dict[str, Any]:
        """Generate and persist one teacher script block at a time.

        Partial blocks live in the durable job until every confirmed-plan block is
        complete. A retry can seed a new job from that checkpoint without turning
        an incomplete script into a formal revision.
        """
        contracts: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
        for outline_section in outline_sections:
            section_id = str(outline_section.get("node_id") or "")
            plan_section = plan_sections.get(section_id) or {}
            contract = compile_teacher_script_module_contract(
                outline_section,
                plan_section,
            )
            if not contract.get("modules"):
                raise TeacherLessonAuthoringError(
                    "lesson_script_contract_empty",
                    f"{contract.get('title') or section_id} 没有可生成的教学块。",
                )
            contracts.append((outline_section, plan_section, contract))

        total_blocks = sum(
            len(contract.get("modules") or [])
            for _outline, _plan, contract in contracts
        )
        seed_by_section = {
            str(item.get("section_node_id") or ""): item
            for item in seed_sections or []
            if isinstance(item, dict) and item.get("section_node_id")
        }
        completed_by_section: dict[str, list[dict[str, Any]]] = {}
        block_states: dict[str, str] = {}
        for _outline, _plan, contract in contracts:
            section_id = str(contract.get("section_node_id") or "")
            expected = [
                item for item in contract.get("modules") or [] if isinstance(item, dict)
            ]
            existing = {
                str(item.get("block_id") or ""): item
                for item in (seed_by_section.get(section_id) or {}).get("blocks") or []
                if isinstance(item, dict)
                and item.get("block_id")
                and str(item.get("content") or "").strip()
            }
            completed: list[dict[str, Any]] = []
            for module in expected:
                block_id = str(module.get("block_id") or "")
                previous = existing.get(block_id)
                if previous:
                    candidate = {
                        **deepcopy(module),
                        "content": str(previous.get("content") or "").strip(),
                    }
                    single_contract = {
                        **deepcopy(contract),
                        "modules": [deepcopy(module)],
                    }
                    seed_report = validate_teacher_script_section(
                        {
                            "section_node_id": section_id,
                            "title": contract.get("title"),
                            "blocks": [candidate],
                        },
                        single_contract,
                    )
                    if seed_report.get("passed"):
                        completed.append(candidate)
                        block_states[block_id] = "completed"
                    else:
                        # Checkpoints are reusable evidence, not trusted final
                        # output. A truncated formula or newly tightened
                        # quality rule must regenerate only the affected block.
                        block_states[block_id] = "pending"
                else:
                    block_states[block_id] = "pending"
            completed_by_section[section_id] = completed

        def checkpoint_sections() -> list[dict[str, Any]]:
            result: list[dict[str, Any]] = []
            for _outline, _plan, contract in contracts:
                section_id = str(contract.get("section_node_id") or "")
                blocks = completed_by_section.get(section_id) or []
                if not blocks:
                    continue
                result.append(normalize_teacher_script_section({
                    "section_node_id": section_id,
                    "title": contract.get("title"),
                    "blocks": blocks,
                }, contract))
            return result

        completed_count = sum(
            1 for state in block_states.values() if state == "completed"
        )
        self.repository.update_job(
            course_id,
            job_id,
            status="running",
            phase="lesson_script_generation",
            progress=max(5, int(90 * completed_count / max(1, total_blocks))),
            message=(
                f"继续生成本讲讲稿，已保留 {completed_count}/{total_blocks} 个教学块"
                if completed_count
                else "正在按已确认教案生成本讲讲稿"
            ),
            total_blocks=total_blocks,
            completed_blocks=completed_count,
            block_states=block_states,
            result_sections=checkpoint_sections(),
            stream_complete=False,
            error=None,
        )

        current_block_id = ""
        current_block_title = ""
        try:
            for outline_section, plan_section, contract in contracts:
                section_id = str(contract.get("section_node_id") or "")
                completed = completed_by_section[section_id]
                completed_ids = {
                    str(item.get("block_id") or "") for item in completed
                }
                for module in contract.get("modules") or []:
                    if not isinstance(module, dict):
                        continue
                    current_block_id = str(module.get("block_id") or "")
                    current_block_title = str(module.get("title") or "教学块")
                    if current_block_id in completed_ids:
                        continue
                    if self.repository.get_job(course_id, job_id).get("cancel_requested"):
                        raise asyncio.CancelledError
                    block_states[current_block_id] = "running"
                    current_job = self.repository.get_job(course_id, job_id)
                    self.repository.update_job(
                        course_id,
                        job_id,
                        phase="lesson_script_block_generation",
                        message=f"正在生成：{current_block_title}",
                        current_block_id=current_block_id,
                        current_block_title=current_block_title,
                        block_states=block_states,
                        stream_sequence=int(current_job.get("stream_sequence") or 0) + 1,
                    )
                    content = str(await generator(
                        outline_section,
                        plan_section,
                        module,
                        deepcopy(completed),
                    ) or "").strip()
                    current_after_generation = self.repository.get_job(
                        course_id,
                        job_id,
                    )
                    if current_after_generation.get("cancel_requested"):
                        raise asyncio.CancelledError
                    if str(current_after_generation.get("status") or "") not in {
                        "pending",
                        "running",
                    }:
                        # A process-recovery watcher may have expired this job
                        # while an uncooperative provider request was still in
                        # flight. Never let the orphaned coroutine overwrite
                        # that terminal state or publish a late revision.
                        return current_after_generation
                    if not content:
                        raise TeacherLessonAuthoringError(
                            "lesson_script_block_empty",
                            f"{current_block_title} 没有生成有效内容。",
                        )
                    completed.append({**deepcopy(module), "content": content})
                    completed_ids.add(current_block_id)
                    block_states[current_block_id] = "completed"
                    completed_count += 1
                    current_job = self.repository.get_job(course_id, job_id)
                    self.repository.update_job(
                        course_id,
                        job_id,
                        phase="lesson_script_block_saved",
                        progress=max(5, min(95, int(95 * completed_count / max(1, total_blocks)))),
                        message=f"已生成 {completed_count}/{total_blocks} 个教学块",
                        completed_blocks=completed_count,
                        current_block_id="",
                        current_block_title="",
                        block_states=block_states,
                        result_sections=checkpoint_sections(),
                        stream_sequence=int(current_job.get("stream_sequence") or 0) + 1,
                    )

            final_sections: list[dict[str, Any]] = []
            for _outline, _plan, contract in contracts:
                section_id = str(contract.get("section_node_id") or "")
                section = normalize_teacher_script_section({
                    "section_node_id": section_id,
                    "title": contract.get("title"),
                    "blocks": completed_by_section.get(section_id) or [],
                }, contract)
                section["quality_report"] = validate_teacher_script_section(
                    section,
                    contract,
                )
                section["pipeline_version"] = SCRIPT_PIPELINE_VERSION
                if not section["quality_report"].get("passed"):
                    issues = "；".join(
                        str(item.get("message") or "")
                        for item in section["quality_report"].get("blocking_issues") or []
                        if isinstance(item, dict)
                    )
                    raise TeacherLessonAuthoringError(
                        "lesson_script_quality_blocked",
                        issues or "讲稿没有完整覆盖已确认教学块。",
                    )
                final_sections.append(section)

            lesson = self.repository.save_script_revision(
                course_id,
                lesson_unit_id,
                final_sections,
                source_lesson_plan_revision_id=source_plan_revision_id,
                generation_source="model_block_pipeline",
                requirements=requirements,
                material_asset_ids=material_asset_ids or [],
                actor=actor,
            )
            current_job = self.repository.get_job(course_id, job_id)
            return self.repository.update_job(
                course_id,
                job_id,
                status="completed",
                phase="lesson_script_ready",
                progress=100,
                message="本讲讲稿已生成，等待确认",
                completed_blocks=total_blocks,
                result_sections=final_sections,
                result_revision_id=str(lesson.get("working_script_revision_id") or ""),
                current_block_id="",
                current_block_title="",
                stream_sequence=int(current_job.get("stream_sequence") or 0) + 1,
                stream_complete=True,
                error=None,
            )
        except Exception as exc:
            if isinstance(exc, asyncio.CancelledError):
                raise
            if current_block_id:
                block_states[current_block_id] = "failed"
            code = (
                exc.code
                if isinstance(exc, TeacherLessonAuthoringError)
                else "lesson_script_generation_failed"
            )
            current_job = self.repository.get_job(course_id, job_id)
            return self.repository.update_job(
                course_id,
                job_id,
                status="failed",
                phase="lesson_script_failed",
                progress=max(5, int(95 * completed_count / max(1, total_blocks))),
                message=f"讲稿生成暂停，已保留 {completed_count}/{total_blocks} 个教学块",
                completed_blocks=completed_count,
                current_block_id=current_block_id,
                current_block_title=current_block_title,
                block_states=block_states,
                result_sections=checkpoint_sections(),
                stream_sequence=int(current_job.get("stream_sequence") or 0) + 1,
                stream_complete=True,
                error={
                    "code": code,
                    "message": str(exc),
                    "retryable": True,
                },
            )
