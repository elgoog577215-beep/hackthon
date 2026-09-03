"""Bounded, resumable planning primitives for large course outlines.

The product contract is one ordered ``CourseOutlineRevision``.  The execution
contract is intentionally smaller:

1. one light chapter skeleton freezes course-level progression;
2. independent chapters expand concurrently;
3. a chapter with many sections expands in bounded sequential batches;
4. local code assembles the only official outline.

No function in this module calls a model.  Total course size is not a product
limit; only the amount of work assigned to one model request is bounded.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from teaching_design import (
    COVERAGE_STATUS_COMPLETE,
    judge_course_coverage,
)
from course_versioning import stable_hash
from teacher_visible_language import has_unnatural_system_language


def course_coverage_verdict(
    *,
    subject: str,
    brief: dict[str, Any],
    skeleton: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Judge requested size against subject scope during outline planning.

    Called twice per course: once before the skeleton exists, so the size
    verdict can shape the skeleton prompt, and once after, so the verdict can
    name the topics the frozen skeleton actually left out. The verdict is a
    statement about scope only — it never supplies course content.
    """
    classroom = brief.get("teacher_course_brief") or {}
    shape = brief.get("course_shape_constraints") or {}
    planned_topics: list[str] | None = None
    if skeleton is not None:
        planned_topics = _skeleton_topic_text(skeleton)
    return judge_course_coverage(
        subject=subject,
        class_hours=classroom.get("total_class_hours"),
        # Only a real planned size counts. ``minimum_section_count`` is the
        # product floor for an unsized request, not evidence of capacity.
        section_count=(
            shape.get("section_count")
            or _skeleton_section_count(skeleton)
        ),
        planned_topics=planned_topics,
    )


def _skeleton_topic_text(skeleton: dict[str, Any]) -> list[str]:
    """Collect every chapter-level phrase a topic could be named in."""
    values: list[str] = [
        str(skeleton.get("course_title") or ""),
        str(skeleton.get("positioning") or ""),
    ]
    values.extend(
        str(item) for item in skeleton.get("learning_objectives") or []
    )
    for chapter in skeleton.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        values.append(str(chapter.get("title") or ""))
        values.append(str(chapter.get("learning_focus") or ""))
    return [item for item in values if item.strip()]


def _skeleton_section_count(skeleton: dict[str, Any] | None) -> int | None:
    if not isinstance(skeleton, dict):
        return None
    total = sum(
        int(item.get("section_count") or 0)
        for item in skeleton.get("chapters") or []
        if isinstance(item, dict)
    )
    return total or None


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _clip(value: Any, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max_chars:
        return text
    return text[: max(1, max_chars - 1)] + "…"


_VISIBLE_UNIT_PREFIX = re.compile(
    r"^(?:(?:第\s*)?\d+(?:\.\d+)?\s*[章节讲]\s*|\d+(?:\.\d+)+\s*)"
)


def _plain_unit_title(value: Any, fallback: str) -> str:
    title = _clip(value, 140)
    previous = ""
    while title and title != previous:
        previous = title
        title = _VISIBLE_UNIT_PREFIX.sub("", title, count=1).strip()
    return title or fallback


def _planning_stages(value: Any) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple)):
        values = value
    else:
        values = []
    result: list[str] = []
    for item in values:
        stage = _clip(item, 80)
        if stage and stage not in result:
            result.append(stage)
    return result


def _text_items(value: Any, *, max_chars: int, limit: int) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = []
    result: list[str] = []
    for item in values:
        text = _clip(item, max_chars)
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _non_negative_number(value: Any) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return round(max(0.0, number), 2)


def _normalize_hour_breakdown(value: Any) -> dict[str, float]:
    source = value if isinstance(value, dict) else {}
    return {
        "classroom_lecture": _non_negative_number(
            source.get("classroom_lecture") or source.get("lecture")
        ),
        "classroom_practice": _non_negative_number(
            source.get("classroom_practice") or source.get("practice")
        ),
        "online_instruction": _non_negative_number(
            source.get("online_instruction") or source.get("online")
        ),
    }


def _normalize_learning_tasks(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in value if isinstance(value, list) else []:
        if isinstance(raw, str):
            raw = {"task": raw}
        if not isinstance(raw, dict):
            continue
        task = _clip(raw.get("task") or raw.get("description"), 260)
        if not task:
            continue
        mode = str(raw.get("mode") or "offline").strip().lower()
        if mode not in {"online", "offline"}:
            mode = "offline"
        stage = str(raw.get("stage") or "after_class").strip().lower()
        if stage not in {"before_class", "after_class"}:
            stage = "after_class"
        result.append({
            "mode": mode,
            "stage": stage,
            "task": task,
            "evidence": _clip(raw.get("evidence"), 220),
            # 这是课外学习负担，不计入课程总学时。
            "estimated_hours": _non_negative_number(raw.get("estimated_hours")),
        })
        if len(result) >= 6:
            break
    return result


def _normalize_extension_resources(
    value: Any,
    *,
    confirmed_reference_labels: set[str],
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for raw in value if isinstance(value, list) else []:
        if isinstance(raw, str):
            raw = {"title": raw}
        if not isinstance(raw, dict):
            continue
        title = _clip(raw.get("title") or raw.get("name"), 240)
        if not title:
            continue
        resource_type = str(raw.get("resource_type") or raw.get("type") or "book").strip().lower()
        if resource_type not in {"book", "article", "standard", "regulation", "dataset", "video", "website", "other"}:
            resource_type = "other"
        source_ref = _clip(raw.get("source_ref"), 260)
        locator = _clip(
            raw.get("locator") or raw.get("chapter") or raw.get("section"),
            180,
        )
        edition = _clip(raw.get("edition"), 120)
        # 模型不能自行把书目宣布为已核验；只有与课程已确认来源精确匹配时才算。
        verification_status = (
            "verified"
            if source_ref and source_ref in confirmed_reference_labels
            else "pending"
        )
        result.append({
            "resource_type": resource_type,
            "title": title,
            "edition": edition,
            "locator": locator,
            "source_ref": source_ref,
            "verification_status": verification_status,
        })
        if len(result) >= 6:
            break
    return result


def _normalize_assessment_plan(
    value: Any,
    *,
    outcome_count: int,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in value if isinstance(value, list) else []:
        if not isinstance(raw, dict):
            continue
        item = _clip(raw.get("item") or raw.get("name"), 160)
        criteria = _clip(raw.get("criteria") or raw.get("scoring_criteria"), 360)
        if not item:
            continue
        category = str(raw.get("category") or raw.get("type") or "formative").strip().lower()
        if category not in {"formative", "summative"}:
            category = "formative"
        outcome_numbers = list(dict.fromkeys(
            number
            for raw_number in raw.get("outcome_numbers") or []
            if (number := _positive_int(raw_number)) and number <= outcome_count
        ))
        result.append({
            "item": item,
            "category": category,
            "weight_percent": _non_negative_number(
                raw.get("weight_percent") or raw.get("weight")
            ),
            "criteria": criteria,
            "outcome_numbers": outcome_numbers,
        })
        if len(result) >= 16:
            break
    return result


def _normalize_course_modules(value: Any, *, lecture_count: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(value if isinstance(value, list) else [], start=1):
        if not isinstance(raw, dict):
            continue
        title = _clip(raw.get("title") or raw.get("name"), 160)
        lecture_numbers = list(dict.fromkeys(
            number
            for raw_number in raw.get("lecture_numbers") or []
            if (number := _positive_int(raw_number)) and number <= lecture_count
        ))
        if not title or not lecture_numbers:
            continue
        result.append({
            "module_id": _clip(raw.get("module_id") or f"M{index}", 40),
            "title": title,
            "lecture_numbers": lecture_numbers,
        })
    return result


@dataclass(frozen=True)
class CourseOutlinePlanningBudget:
    """Per-unit outline execution settings, never a total-course ceiling."""

    batch_max_sections: int = 6
    # Legacy names retained for callers. There is no whole-outline deadline;
    # the per-unit value means continuous stream inactivity.
    batch_timeout_seconds: int = 90
    total_timeout_seconds: int = 0
    # Each formal teacher-outline request is bounded even while hidden
    # reasoning keeps emitting activity, otherwise an overloaded model can
    # occupy the job forever without producing teacher-visible text.
    teacher_lecture_request_timeout_seconds: int = 600
    # Sixteen formal lectures plus the course-level alignment fields exceed
    # the generic 8K outline ceiling in real provider runs. Start the teacher
    # request with enough room instead of predictably truncating once and
    # repeating the whole outline at double headroom.
    teacher_lecture_max_output_tokens: int = 16_384
    # Formal outlines use one compact framework request followed by a small
    # number of bounded detail batches. This avoids both one giant response and
    # sixteen independent requests competing for provider capacity.
    teacher_detail_batch_size: int = 4
    teacher_detail_concurrency: int = 2

    @classmethod
    def from_env(cls) -> CourseOutlinePlanningBudget:
        return cls(
            batch_max_sections=_env_int(
                "COURSE_OUTLINE_BATCH_MAX_SECTIONS",
                6,
                minimum=2,
                maximum=8,
            ),
            batch_timeout_seconds=_env_int(
                "COURSE_OUTLINE_INACTIVITY_TIMEOUT_SECONDS",
                90,
                minimum=30,
                maximum=600,
            ),
            total_timeout_seconds=0,
            teacher_lecture_request_timeout_seconds=_env_int(
                "COURSE_TEACHER_OUTLINE_REQUEST_TIMEOUT_SECONDS",
                600,
                minimum=120,
                maximum=1800,
            ),
            teacher_lecture_max_output_tokens=_env_int(
                "COURSE_TEACHER_OUTLINE_MAX_OUTPUT_TOKENS",
                16_384,
                minimum=8192,
                maximum=32_768,
            ),
            teacher_detail_batch_size=_env_int(
                "COURSE_TEACHER_OUTLINE_DETAIL_BATCH_SIZE",
                4,
                minimum=2,
                maximum=8,
            ),
            teacher_detail_concurrency=_env_int(
                "COURSE_TEACHER_OUTLINE_DETAIL_CONCURRENCY",
                2,
                minimum=1,
                maximum=4,
            ),
        )


def outline_request_fingerprint(
    *,
    topic: str,
    audience: str,
    brief: dict[str, Any],
    difficulty_profile: dict[str, Any],
) -> str:
    """Identify whether a persisted outline checkpoint still matches the request."""
    # ``brief_id`` identifies one compilation event and is intentionally
    # regenerated. It must not invalidate semantically identical outline
    # checkpoints during resume.
    stable_brief = {
        key: value
        for key, value in brief.items()
        if key != "brief_id"
    }
    return stable_hash(
        {
            "topic": topic,
            "audience": audience,
            "brief": stable_brief,
            "difficulty_profile": difficulty_profile,
        },
        prefix="outline_request_",
    )


def normalize_outline_skeleton(
    payload: dict[str, Any],
    *,
    topic: str,
    request_fingerprint: str,
) -> dict[str, Any]:
    lecture_payload = payload.get("lectures")
    lecture_mode = bool(
        isinstance(lecture_payload, list)
        or payload.get("authoring_structure_version") == "lecture_v1"
    )
    raw_units = (
        lecture_payload
        if isinstance(lecture_payload, list)
        else payload.get("chapters") or []
    )
    reference_books = _text_items(
        payload.get("reference_books"), max_chars=260, limit=30
    )
    reference_websites = _text_items(
        payload.get("reference_websites"), max_chars=260, limit=30
    )
    confirmed_reference_labels = set(reference_books + reference_websites)
    chapters: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_units, start=1):
        if not isinstance(raw, dict):
            continue
        section_count = 1 if lecture_mode else _positive_int(raw.get("section_count"))
        title = _plain_unit_title(
            raw.get("title"),
            f"第 {index} 讲" if lecture_mode else f"第 {index} 章",
        )
        hour_breakdown = _normalize_hour_breakdown(raw.get("hour_breakdown"))
        planned_hours = round(sum(hour_breakdown.values()), 2)
        external_mentor = (
            raw.get("external_mentor")
            if isinstance(raw.get("external_mentor"), dict)
            else {}
        )
        chapters.append({
            "chapter_number": index,
            "lecture_number": index if lecture_mode else None,
            "title": title,
            "planning_stages": _planning_stages(
                raw.get("planning_stages") or raw.get("planning_stage")
            ),
            "learning_focus": _clip(
                raw.get("learning_focus")
                or raw.get("learning_objective")
                or f"完成{topic}的第 {index} 阶段学习任务",
                220,
            ),
            "content_summary": _clip(
                raw.get("content_summary")
                or raw.get("content")
                or (raw.get("learning_focus") if not lecture_mode else ""),
                720,
            ),
            "learning_objective": _clip(
                raw.get("learning_objective") or raw.get("learning_focus"),
                260,
            ),
            "key_points": [
                _clip(item, 160)
                for item in raw.get("key_points") or []
                if str(item or "").strip()
            ][:6],
            "key_difficulties": [
                _clip(item, 160)
                for item in raw.get("key_difficulties") or []
                if str(item or "").strip()
            ][:6],
            "activities": [
                _clip(item, 180)
                for item in raw.get("activities") or []
                if str(item or "").strip()
            ][:6],
            "homework": [
                _clip(item, 180)
                for item in raw.get("homework") or []
                if str(item or "").strip()
            ][:6],
            "application_anchors": _text_items(
                raw.get("application_anchors") or raw.get("cases"),
                max_chars=240,
                limit=6,
            ),
            "extension_resources": _normalize_extension_resources(
                raw.get("extension_resources") or raw.get("readings"),
                confirmed_reference_labels=confirmed_reference_labels,
            ),
            "learning_tasks": _normalize_learning_tasks(
                raw.get("learning_tasks") or raw.get("online_learning")
            ),
            "education_objective_refs": _text_items(
                raw.get("education_objective_refs"),
                max_chars=160,
                limit=6,
            ),
            "ideology_implementation": _clip(
                raw.get("ideology_implementation"), 260
            ),
            "external_mentor": {
                key: _clip(external_mentor.get(key), 160)
                for key in ("name", "organization", "role")
                if _clip(external_mentor.get(key), 160)
            },
            "hour_breakdown": hour_breakdown,
            "planned_hours": planned_hours or None,
            "assessment": _text_items(
                raw.get("assessment"),
                max_chars=240,
                limit=8,
            ),
            "scope_boundary": _clip(raw.get("scope_boundary"), 320),
            "learning_path_role": _learning_path_role(
                raw.get("learning_path_role")
            ),
            "path_reason": _clip(
                raw.get("path_reason") or "课程主路径",
                240,
            ),
            "section_count": section_count or 0,
        })
    measurable_outcomes = [
        _clip(item, 220)
        for item in payload.get("measurable_outcomes") or []
        if str(item or "").strip()
    ][:12]
    outcome_alignment_by_number: dict[int, dict[str, Any]] = {}
    for raw in payload.get("outcome_alignment") or []:
        if not isinstance(raw, dict):
            continue
        outcome_number = _positive_int(
            raw.get("outcome_number") or raw.get("outcome_index")
        )
        if not outcome_number or outcome_number > len(measurable_outcomes):
            continue
        lecture_numbers = list(dict.fromkeys(
            number
            for item in raw.get("lecture_numbers") or []
            if (number := _positive_int(item)) and number <= len(chapters)
        ))
        candidate = {
            "outcome_number": outcome_number,
            "objective_refs": _text_items(
                raw.get("objective_refs"),
                max_chars=120,
                limit=8,
            ),
            "lecture_numbers": lecture_numbers,
            "assessment_evidence": _text_items(
                raw.get("assessment_evidence"),
                max_chars=180,
                limit=8,
            ),
            "coverage_scope": _clip(raw.get("coverage_scope"), 260),
        }
        existing = outcome_alignment_by_number.get(outcome_number)
        if existing is None:
            outcome_alignment_by_number[outcome_number] = candidate
            continue
        for key in ("objective_refs", "assessment_evidence"):
            existing[key] = list(dict.fromkeys(existing[key] + candidate[key]))[:8]
        existing["lecture_numbers"] = list(dict.fromkeys(
            existing["lecture_numbers"] + candidate["lecture_numbers"]
        ))
        if not existing["coverage_scope"]:
            existing["coverage_scope"] = candidate["coverage_scope"]
    outcome_alignment = list(outcome_alignment_by_number.values())
    assessment_plan = _normalize_assessment_plan(
        payload.get("assessment_plan"),
        outcome_count=len(measurable_outcomes),
    )
    skeleton = {
        "schema_version": "course_outline_skeleton_v2",
        "formal_syllabus_contract_version": (
            "formal_syllabus_v2" if lecture_mode else ""
        ),
        "authoring_structure_version": (
            "lecture_v1" if lecture_mode else "legacy_chapter_v1"
        ),
        "request_fingerprint": request_fingerprint,
        "course_title": _clip(payload.get("course_title") or topic, 160),
        "positioning": _clip(
            payload.get("positioning")
            or f"系统学习{topic}并完成可检查成果",
            280,
        ),
        "learning_objectives": [
            _clip(item, 220)
            for item in payload.get("learning_objectives") or []
            if str(item or "").strip()
        ][:16],
        "prerequisites": [
            _clip(item, 160)
            for item in payload.get("prerequisites") or []
            if str(item or "").strip()
        ][:16],
        "course_intro_zh": _clip(payload.get("course_intro_zh"), 1800),
        "course_intro_en": _clip(payload.get("course_intro_en"), 1800),
        "education_objectives": [
            _clip(item, 220)
            for item in payload.get("education_objectives") or []
            if str(item or "").strip()
        ][:12],
        "measurable_outcomes": measurable_outcomes,
        "outcome_alignment": outcome_alignment,
        "teaching_methods": [
            _clip(item, 220)
            for item in payload.get("teaching_methods") or []
            if str(item or "").strip()
        ][:12],
        "assessment_methods": [
            _clip(item, 220)
            for item in payload.get("assessment_methods") or []
            if str(item or "").strip()
        ][:12],
        "assessment_plan": assessment_plan,
        "course_modules": _normalize_course_modules(
            payload.get("course_modules"), lecture_count=len(chapters)
        ),
        "ideology_cases": deepcopy(payload.get("ideology_cases") or []),
        "reference_books": reference_books,
        "reference_websites": reference_websites,
        "course_website": _clip(payload.get("course_website"), 500),
        "chapters": chapters,
    }
    if not skeleton["learning_objectives"]:
        skeleton["learning_objectives"] = [
            f"能够解释并应用{topic}的核心方法",
        ]
    skeleton["revision_id"] = stable_hash(
        skeleton,
        prefix="outline_skeleton_",
    )
    return skeleton


def _completed_stream_array_items(
    content: str,
    *,
    field: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Decode only complete objects already received from a streamed JSON array."""
    match = re.search(rf'"{re.escape(field)}"\s*:\s*\[', content)
    if not match:
        return []
    decoder = json.JSONDecoder()
    cursor = match.end()
    items: list[dict[str, Any]] = []
    while cursor < len(content) and len(items) < limit:
        while cursor < len(content) and (
            content[cursor].isspace() or content[cursor] == ","
        ):
            cursor += 1
        if cursor >= len(content) or content[cursor] == "]":
            break
        try:
            value, cursor = decoder.raw_decode(content, cursor)
        except json.JSONDecodeError:
            break
        if isinstance(value, dict):
            items.append(value)
    return items


def project_streamed_teacher_outline_growth(
    content: str,
    *,
    topic: str,
    lecture_count: int,
) -> dict[str, Any]:
    """Project complete streamed lecture objects without accepting partial JSON.

    The projection is display-only. The formal outline is still accepted only
    after the provider response closes, parses and passes the full validator.
    """
    expected_count = max(1, int(lecture_count or 0))
    raw_lectures = _completed_stream_array_items(
        content,
        field="lectures",
        limit=expected_count,
    )
    partial = normalize_outline_skeleton(
        {
            "authoring_structure_version": "lecture_v1",
            "course_title": topic,
            "lectures": raw_lectures,
        },
        topic=topic,
        request_fingerprint="streaming_preview",
    )
    completed = min(expected_count, len(partial.get("chapters") or []))
    chapters: list[dict[str, Any]] = []
    for index in range(1, expected_count + 1):
        generated = (
            partial["chapters"][index - 1]
            if index <= completed
            else {}
        )
        chapters.append({
            "chapter_number": index,
            "title": str(generated.get("title") or "正在生成本讲主题…"),
            "learning_focus": str(
                generated.get("learning_focus")
                or generated.get("learning_objective")
                or ""
            ),
            "section_count": 1,
            "completed_section_count": 1 if index <= completed else 0,
            "status": (
                "completed"
                if index <= completed
                else "growing"
                if index == completed + 1
                else "waiting"
            ),
            "sections": [],
        })
    return {
        "schema_version": "course_outline_growth_v1",
        "authoring_structure_version": "lecture_v1",
        "state": "growing",
        "course_title": topic,
        "positioning": "",
        "active_batch_id": "",
        "active_chapter_number": (
            min(expected_count, completed + 1)
            if completed < expected_count
            else 0
        ),
        "completed_batches": completed,
        "total_batches": expected_count,
        "completed_sections": completed,
        "total_sections": expected_count,
        "streamed_content_chars": len(content),
        "chapters": chapters,
    }


def validate_outline_skeleton(
    skeleton: dict[str, Any],
    *,
    shape_constraints: dict[str, Any],
    request_fingerprint: str,
    course_type_contract: dict[str, Any] | None = None,
    coverage_verdict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    chapters = [
        item
        for item in skeleton.get("chapters") or []
        if isinstance(item, dict)
    ]
    if skeleton.get("request_fingerprint") != request_fingerprint:
        issues.append(_issue(
            "outline_skeleton:stale_request",
            "章节骨架不属于当前课程需求修订",
        ))
    if not chapters:
        issues.append(_issue(
            "outline_skeleton:missing_chapters",
            "章节骨架没有返回可扩展章节",
        ))
    invalid_counts = [
        int(item.get("chapter_number") or index)
        for index, item in enumerate(chapters, start=1)
        if not _positive_int(item.get("section_count"))
    ]
    if invalid_counts:
        issues.append(_issue(
            "outline_skeleton:invalid_section_counts",
            f"章节 {invalid_counts} 没有合法的小节数量",
        ))
    expected_chapters = _positive_int(shape_constraints.get("chapter_count"))
    expected_sections = _positive_int(shape_constraints.get("section_count"))
    minimum_chapters = _positive_int(
        shape_constraints.get("minimum_chapter_count")
    )
    minimum_sections = _positive_int(
        shape_constraints.get("minimum_section_count")
    )
    actual_sections = sum(
        int(item.get("section_count") or 0)
        for item in chapters
    )
    if expected_chapters is not None and len(chapters) != expected_chapters:
        issues.append(_issue(
            "outline_skeleton:chapter_count_mismatch",
            f"用户要求 {expected_chapters} 章，骨架实际为 {len(chapters)} 章",
        ))
    if expected_sections is not None and actual_sections != expected_sections:
        issues.append(_issue(
            "outline_skeleton:section_count_mismatch",
            f"用户要求 {expected_sections} 节，骨架实际分配 {actual_sections} 节",
        ))
    if shape_constraints.get("teacher_lecture_mode"):
        non_unitary = [
            int(item.get("chapter_number") or index)
            for index, item in enumerate(chapters, start=1)
            if int(item.get("section_count") or 0) != 1
        ]
        if non_unitary:
            issues.append(_issue(
                "outline_skeleton:teacher_lecture_adapter_mismatch",
                f"教师课程的每一讲只能有一个内部内容容器，异常讲次：{non_unitary}",
            ))
    if expected_chapters is None and minimum_chapters is not None and len(chapters) < minimum_chapters:
        issues.append(_issue(
            "outline_skeleton:below_complete_chapter_minimum",
            f"完整课程至少需要 {minimum_chapters} 章，骨架实际为 {len(chapters)} 章",
        ))
    if expected_sections is None and minimum_sections is not None and actual_sections < minimum_sections:
        issues.append(_issue(
            "outline_skeleton:below_complete_section_minimum",
            f"完整课程至少需要 {minimum_sections} 节，骨架实际分配 {actual_sections} 节",
        ))
    if (
        expected_chapters is not None
        and expected_sections is not None
        and expected_sections < expected_chapters
    ):
        issues.append(_issue(
            "outline_skeleton:inconsistent_shape",
            "小节总数少于章节数，无法保证每章至少包含一个可学习小节",
        ))
    required_stages = [
        str(item.get("id") or "").strip()
        for item in (course_type_contract or {}).get("required_planning_stages") or []
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    ]
    if required_stages and chapters:
        chapter_stages = [
            _planning_stages(
                item.get("planning_stages") or item.get("planning_stage")
            )
            for item in chapters
        ]
        actual_stages = [
            stage
            for stages in chapter_stages
            for stage in stages
        ]
        missing_stages = [
            stage for stage in required_stages if stage not in actual_stages
        ]
        unknown_stages = [
            stage for stage in actual_stages
            if stage and stage not in required_stages
        ]
        if any(not stages for stages in chapter_stages):
            issues.append(_issue(
                "outline_skeleton:missing_planning_stage",
                "专用课程规划器要求每章声明 planning_stages",
            ))
        if missing_stages:
            issues.append(_issue(
                "outline_skeleton:incomplete_planning_stages",
                f"课程骨架缺少必要规划阶段：{missing_stages}",
            ))
        if unknown_stages:
            issues.append(_issue(
                "outline_skeleton:unknown_planning_stage",
                f"课程骨架包含未知规划阶段：{unknown_stages}",
            ))
        known_positions = [
            required_stages.index(stage)
            for stage in actual_stages
            if stage in required_stages
        ]
        if known_positions != sorted(known_positions):
            issues.append(_issue(
                "outline_skeleton:planning_stage_order_mismatch",
                "课程骨架的规划阶段顺序不符合课程类型合同",
            ))
    issues.extend(_coverage_honesty_issues(skeleton, coverage_verdict))
    return {
        "schema_version": "course_outline_skeleton_validation_v2",
        "passed": not issues,
        "issues": issues,
        "actual": {
            "chapter_count": len(chapters),
            "section_count": actual_sections,
        },
    }


_COMPLETENESS_CLAIMS = (
    "完整课程",
    "完整覆盖",
    "全面覆盖",
    "完整的课程",
    "系统完整",
    "面面俱到",
)

_COMPLETENESS_NEGATION = re.compile(
    r"(?:并不|并非|不追求|不承担|不承诺|不要求|不能|无法|无需|无须|未|非|不).{0,8}$"
)


def _affirmative_completeness_claims(prose: str) -> list[str]:
    """Return completeness claims that are asserted rather than denied.

    The outline prompt explicitly asks a short course to state what it does not
    cover.  A plain substring check therefore treated honest wording such as
    ``不追求学科完整覆盖`` as the exact overclaim it was denying.  Inspect the
    local prefix of every occurrence so a negative scope boundary passes while
    a real promise like ``完整覆盖全部内容`` remains blocked.
    """
    claims: list[str] = []
    for claim in _COMPLETENESS_CLAIMS:
        for match in re.finditer(re.escape(claim), prose):
            prefix = prose[max(0, match.start() - 12):match.start()]
            if _COMPLETENESS_NEGATION.search(prefix):
                continue
            claims.append(claim)
            break
    return claims


def _coverage_honesty_issues(
    skeleton: dict[str, Any],
    coverage_verdict: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Reject a completeness claim the requested course size cannot support.

    This is the honesty gate: a course that cannot cover its subject may still
    be generated, but it may not describe itself as if it had.
    """
    if not coverage_verdict:
        return []
    if coverage_verdict.get("status") == COVERAGE_STATUS_COMPLETE:
        return []
    if coverage_verdict.get("may_claim_complete_subject"):
        return []
    prose = " ".join([
        str(skeleton.get("course_title") or ""),
        str(skeleton.get("positioning") or ""),
    ])
    claims = _affirmative_completeness_claims(prose)
    if not claims:
        return []
    return [_issue(
        "outline_skeleton:unsupported_completeness_claim",
        f"{coverage_verdict.get('scale_label') or '当前课程规格'}不足以完整覆盖"
        f"{coverage_verdict.get('subject') or '本学科'}，"
        f"课程名称或定位不得包含 {claims}；"
        f"应改为「{coverage_verdict.get('required_positioning') or '核心概览课'}」"
        "并显式列出本次不覆盖的知识点",
    )]


def build_outline_batch_specs(
    skeleton: dict[str, Any],
    budget: CourseOutlinePlanningBudget,
) -> list[dict[str, Any]]:
    """Split each chapter into ordered units while allowing chapters to run in parallel."""
    chapters = [
        item
        for item in skeleton.get("chapters") or []
        if isinstance(item, dict)
    ]
    specs: list[dict[str, Any]] = []
    for chapter_index, chapter in enumerate(chapters, start=1):
        count = max(0, int(chapter.get("section_count") or 0))
        batch_count = math.ceil(count / budget.batch_max_sections) if count else 0
        previous_chapter_count = (
            int(chapters[chapter_index - 2].get("section_count") or 0)
            if chapter_index > 1
            else 0
        )
        for batch_index, start in enumerate(
            range(1, count + 1, budget.batch_max_sections),
            start=1,
        ):
            end = min(count, start + budget.batch_max_sections - 1)
            specs.append({
                "batch_id": (
                    f"OUT-C{chapter_index:03d}-B{batch_index:03d}"
                ),
                "chapter_number": chapter_index,
                "chapter_batch_index": batch_index,
                "chapter_batch_count": batch_count,
                "start_section_index": start,
                "end_section_index": end,
                "section_count": end - start + 1,
                "chapter_section_count": count,
                "expected_node_ids": [
                    f"L2-{chapter_index}-{section_index}"
                    for section_index in range(start, end + 1)
                ],
                "previous_chapter_anchor_id": (
                    f"L2-{chapter_index - 1}-{previous_chapter_count}"
                    if previous_chapter_count
                    else None
                ),
            })
    return specs


_TEACHER_OUTLINE_DETAIL_FIELDS = (
    "content_summary",
    "key_points",
    "key_difficulties",
    "activities",
    "homework",
    "application_anchors",
    "extension_resources",
    "learning_tasks",
    "education_objective_refs",
    "ideology_implementation",
    "external_mentor",
    "assessment",
)


def build_teacher_outline_detail_batch_specs(
    skeleton: dict[str, Any],
    *,
    batch_size: int,
    pending_lecture_numbers: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Group lecture details without changing the frozen course framework."""
    valid_numbers = [
        int(item.get("lecture_number") or item.get("chapter_number") or index)
        for index, item in enumerate(skeleton.get("chapters") or [], start=1)
        if isinstance(item, dict)
    ]
    requested = (
        [int(item) for item in pending_lecture_numbers]
        if pending_lecture_numbers is not None
        else valid_numbers
    )
    numbers = [item for item in requested if item in set(valid_numbers)]
    size = max(1, int(batch_size or 1))
    revision_id = str(skeleton.get("revision_id") or "")
    specs: list[dict[str, Any]] = []
    for offset in range(0, len(numbers), size):
        group = numbers[offset:offset + size]
        if not group:
            continue
        specs.append({
            "batch_id": f"OUT-TD-{group[0]:03d}-{group[-1]:03d}",
            "skeleton_revision_id": revision_id,
            "lecture_numbers": group,
            "lecture_count": len(group),
        })
    return specs


def normalize_teacher_outline_detail_batch(
    payload: dict[str, Any],
    *,
    spec: dict[str, Any],
    skeleton: dict[str, Any],
) -> dict[str, Any]:
    """Normalize one detail response while keeping framework fields immutable."""
    raw_lectures = [
        item for item in payload.get("lectures") or []
        if isinstance(item, dict)
    ]
    raw_by_number = {
        number: item
        for item in raw_lectures
        if (number := _positive_int(item.get("lecture_number")))
    }
    confirmed_reference_labels = {
        str(item).strip()
        for item in [
            *(skeleton.get("reference_books") or []),
            *(skeleton.get("reference_websites") or []),
        ]
        if str(item).strip()
    }
    lectures: list[dict[str, Any]] = []
    for lecture_number in spec.get("lecture_numbers") or []:
        raw = raw_by_number.get(int(lecture_number))
        if raw is None:
            continue
        external_mentor = (
            raw.get("external_mentor")
            if isinstance(raw.get("external_mentor"), dict)
            else {}
        )
        lectures.append({
            "lecture_number": int(lecture_number),
            "content_summary": _clip(raw.get("content_summary"), 720),
            "key_points": _text_items(
                raw.get("key_points"), max_chars=160, limit=6
            ),
            "key_difficulties": _text_items(
                raw.get("key_difficulties"), max_chars=160, limit=6
            ),
            "activities": _text_items(
                raw.get("activities"), max_chars=180, limit=6
            ),
            "homework": _text_items(
                raw.get("homework"), max_chars=180, limit=6
            ),
            "application_anchors": _text_items(
                raw.get("application_anchors"), max_chars=240, limit=6
            ),
            "extension_resources": _normalize_extension_resources(
                raw.get("extension_resources"),
                confirmed_reference_labels=confirmed_reference_labels,
            ),
            "learning_tasks": _normalize_learning_tasks(
                raw.get("learning_tasks")
            ),
            "education_objective_refs": _text_items(
                raw.get("education_objective_refs"),
                max_chars=160,
                limit=6,
            ),
            "ideology_implementation": _clip(
                raw.get("ideology_implementation"), 260
            ),
            "external_mentor": {
                key: _clip(external_mentor.get(key), 160)
                for key in ("name", "organization", "role")
                if _clip(external_mentor.get(key), 160)
            },
            "assessment": _text_items(
                raw.get("assessment"), max_chars=240, limit=8
            ),
        })
    batch = {
        "schema_version": "teacher_outline_detail_batch_v1",
        "batch_id": str(payload.get("batch_id") or ""),
        "skeleton_revision_id": str(
            payload.get("skeleton_revision_id") or ""
        ),
        "lectures": lectures,
    }
    batch["revision_id"] = stable_hash(
        batch,
        prefix="teacher_outline_detail_",
    )
    return batch


def validate_teacher_outline_detail_batch(
    batch: dict[str, Any],
    *,
    spec: dict[str, Any],
    skeleton: dict[str, Any],
) -> dict[str, Any]:
    """Reject an incomplete detail batch without invalidating other batches."""
    issues: list[dict[str, str]] = []
    if batch.get("batch_id") != spec.get("batch_id"):
        issues.append(_issue(
            "teacher_outline_detail:batch_id_mismatch",
            "讲次详情批次标识与请求不一致",
        ))
    if batch.get("skeleton_revision_id") != skeleton.get("revision_id"):
        issues.append(_issue(
            "teacher_outline_detail:stale_framework",
            "讲次详情引用了旧课程框架",
        ))
    expected_numbers = [
        int(item) for item in spec.get("lecture_numbers") or []
    ]
    lectures = [
        item for item in batch.get("lectures") or []
        if isinstance(item, dict)
    ]
    actual_numbers = [
        int(item.get("lecture_number") or 0) for item in lectures
    ]
    if actual_numbers != expected_numbers:
        issues.append(_issue(
            "teacher_outline_detail:lecture_order_mismatch",
            f"讲次详情应返回 {expected_numbers}，实际为 {actual_numbers}",
        ))
    confirmed_references = {
        str(item).strip()
        for item in [
            *(skeleton.get("reference_books") or []),
            *(skeleton.get("reference_websites") or []),
        ]
        if str(item).strip()
    }
    required_list_fields = (
        ("key_points", "教学重点"),
        ("key_difficulties", "教学难点"),
        ("activities", "教学活动"),
        ("homework", "课后任务"),
        ("application_anchors", "应用情境"),
        ("learning_tasks", "学习任务"),
        ("assessment", "达成检验"),
    )
    for lecture in lectures:
        number = int(lecture.get("lecture_number") or 0)
        if not str(lecture.get("content_summary") or "").strip():
            issues.append(_issue(
                "teacher_outline_detail:missing_content_summary",
                f"第 {number} 讲缺少内容摘要",
            ))
        for field, label in required_list_fields:
            if not list(lecture.get(field) or []):
                issues.append(_issue(
                    f"teacher_outline_detail:missing_{field}",
                    f"第 {number} 讲缺少{label}",
                ))
        tasks = [
            item for item in lecture.get("learning_tasks") or []
            if isinstance(item, dict)
        ]
        if tasks and any(not str(item.get("evidence") or "").strip() for item in tasks):
            issues.append(_issue(
                "teacher_outline_detail:missing_task_evidence",
                f"第 {number} 讲的学习任务缺少可提交证据",
            ))
        if confirmed_references and not list(
            lecture.get("extension_resources") or []
        ):
            issues.append(_issue(
                "teacher_outline_detail:missing_extension_resources",
                f"第 {number} 讲未从已确认参考资料中选择拓展资源",
            ))
    return {
        "schema_version": "teacher_outline_detail_validation_v1",
        "passed": not issues,
        "issues": issues,
        "actual": {"lecture_count": len(lectures)},
    }


def merge_teacher_outline_detail(
    lecture: dict[str, Any],
    detail: dict[str, Any],
) -> dict[str, Any]:
    """Apply generated detail without letting it rename or reorder a lecture."""
    merged = deepcopy(lecture)
    for field in _TEACHER_OUTLINE_DETAIL_FIELDS:
        if field in detail:
            merged[field] = deepcopy(detail[field])
    return merged


def normalize_outline_batch(
    payload: dict[str, Any],
    *,
    spec: dict[str, Any],
    skeleton_revision_id: str,
) -> dict[str, Any]:
    chapter_number = int(spec.get("chapter_number") or 1)
    start_index = int(spec.get("start_section_index") or 1)
    sections: list[dict[str, Any]] = []
    for offset, raw in enumerate(payload.get("sections") or []):
        if not isinstance(raw, dict):
            continue
        section_index = start_index + offset
        sections.append({
            "node_id": f"L2-{chapter_number}-{section_index}",
            "section_number": f"{chapter_number}.{section_index}",
            "title": _clip(
                raw.get("title")
                or f"学习任务 {chapter_number}.{section_index}",
                140,
            ),
            "learning_objective": _clip(
                raw.get("learning_objective")
                or f"完成第 {chapter_number}.{section_index} 节的可检查任务",
                240,
            ),
            "prerequisite_node_ids": [
                str(item)
                for item in raw.get("prerequisite_node_ids") or []
                if str(item or "").strip()
            ][:8],
            "assessment": [
                _clip(item, 180)
                for item in raw.get("assessment") or []
                if str(item or "").strip()
            ][:8],
            "scope_boundary": _clip(
                raw.get("scope_boundary"),
                240,
            ),
            "learning_path_role": _learning_path_role(
                raw.get("learning_path_role")
            ),
            "path_reason": _clip(
                raw.get("path_reason") or "课程主路径",
                240,
            ),
        })
    batch = {
        "schema_version": "course_outline_batch_v2",
        "batch_id": str(spec.get("batch_id") or ""),
        "skeleton_revision_id": skeleton_revision_id,
        "chapter_number": chapter_number,
        "sections": sections,
    }
    batch["revision_id"] = stable_hash(batch, prefix="outline_batch_")
    return batch


def validate_outline_batch(
    batch: dict[str, Any],
    *,
    spec: dict[str, Any],
    skeleton_revision_id: str,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    sections = [
        item
        for item in batch.get("sections") or []
        if isinstance(item, dict)
    ]
    expected_ids = list(spec.get("expected_node_ids") or [])
    actual_ids = [str(item.get("node_id") or "") for item in sections]
    if batch.get("skeleton_revision_id") != skeleton_revision_id:
        issues.append(_issue(
            "outline_batch:stale_skeleton",
            "目录批次引用了旧章节骨架",
        ))
    if actual_ids != expected_ids:
        issues.append(_issue(
            "outline_batch:section_order_mismatch",
            f"目录批次应返回 {expected_ids}，实际为 {actual_ids}",
        ))
    position = {
        node_id: index
        for index, node_id in enumerate(expected_ids)
    }
    previous_anchor = str(
        spec.get("previous_chapter_anchor_id") or ""
    )
    for section in sections:
        node_id = str(section.get("node_id") or "")
        if not str(section.get("title") or "").strip():
            issues.append(_issue(
                "outline_batch:missing_title",
                f"{node_id} 缺少小节名称",
            ))
        if not str(section.get("learning_objective") or "").strip():
            issues.append(_issue(
                "outline_batch:missing_objective",
                f"{node_id} 缺少可观察学习目标",
            ))
        for dependency in section.get("prerequisite_node_ids") or []:
            dependency = str(dependency)
            local_is_earlier = (
                dependency in position
                and position[dependency] < position.get(node_id, -1)
            )
            prior_batch_pattern = (
                dependency.startswith(
                    f"L2-{int(spec.get('chapter_number') or 1)}-"
                )
                and _section_index(dependency)
                < _section_index(node_id)
            )
            if not (
                local_is_earlier
                or prior_batch_pattern
                or (previous_anchor and dependency == previous_anchor)
            ):
                issues.append(_issue(
                    "outline_batch:invalid_prerequisite",
                    f"{node_id} 引用了当前批次不可用的前置小节 {dependency}",
                ))
    return {
        "schema_version": "course_outline_batch_validation_v2",
        "passed": not issues,
        "issues": issues,
        "actual": {"section_count": len(sections)},
    }


def compile_fallback_outline_batch(
    *,
    spec: dict[str, Any],
    chapter: dict[str, Any],
    skeleton_revision_id: str,
) -> dict[str, Any]:
    start = int(spec.get("start_section_index") or 1)
    end = int(spec.get("end_section_index") or start)
    chapter_number = int(spec.get("chapter_number") or 1)
    title = str(chapter.get("title") or f"第 {chapter_number} 章")
    focus = str(chapter.get("learning_focus") or title)
    previous_anchor = str(spec.get("previous_chapter_anchor_id") or "")
    sections: list[dict[str, Any]] = []
    for section_index in range(start, end + 1):
        node_id = f"L2-{chapter_number}-{section_index}"
        dependency = ""
        if section_index > 1:
            dependency = f"L2-{chapter_number}-{section_index - 1}"
        elif previous_anchor:
            dependency = previous_anchor
        sections.append({
            "node_id": node_id,
            "section_number": f"{chapter_number}.{section_index}",
            "title": f"{title}：学习任务 {section_index}",
            "learning_objective": (
                f"围绕“{focus}”完成第 {section_index} 个可观察学习任务"
            ),
            "prerequisite_node_ids": [dependency] if dependency else [],
            "assessment": [
                f"提交并说明第 {chapter_number}.{section_index} 节的应用结果",
            ],
            "scope_boundary": (
                f"只完成“{focus}”在第 {section_index} 个任务中的责任，"
                "不提前替代后续小节"
            ),
            "learning_path_role": _learning_path_role(
                chapter.get("learning_path_role")
            ),
            "path_reason": str(
                chapter.get("path_reason") or "课程主路径"
            ),
        })
    return normalize_outline_batch(
        {"sections": sections},
        spec=spec,
        skeleton_revision_id=skeleton_revision_id,
    )


def compile_teacher_lecture_outline_batch(
    *,
    spec: dict[str, Any],
    lecture: dict[str, Any],
    skeleton_revision_id: str,
) -> dict[str, Any]:
    """Project one lecture-native model unit into the legacy inner container.

    The container keeps existing downstream generation code working, but it is
    not a second teacher-visible course level and therefore receives no visible
    1.1-style title.
    """
    lecture_number = int(spec.get("chapter_number") or 1)
    previous_anchor = str(spec.get("previous_chapter_anchor_id") or "")
    title = _plain_unit_title(lecture.get("title"), f"第 {lecture_number} 讲")
    objective = _clip(
        lecture.get("learning_objective")
        or lecture.get("learning_focus")
        or f"完成“{title}”的学习任务",
        260,
    )
    content_summary = _clip(
        lecture.get("content_summary")
        or lecture.get("learning_focus")
        or objective,
        720,
    )
    payload = {
        "sections": [{
            "node_id": f"L2-{lecture_number}-1",
            "title": title,
            "content_summary": content_summary,
            "learning_objective": objective,
            "prerequisite_node_ids": [previous_anchor] if previous_anchor else [],
            "assessment": [
                _clip(item, 180)
                for item in lecture.get("assessment") or []
                if str(item or "").strip()
            ],
            "scope_boundary": _clip(lecture.get("scope_boundary"), 240),
            "learning_path_role": _learning_path_role(
                lecture.get("learning_path_role")
            ),
            "path_reason": _clip(
                lecture.get("path_reason") or "本讲在整课中的推进作用",
                240,
            ),
        }],
    }
    batch = normalize_outline_batch(
        payload,
        spec=spec,
        skeleton_revision_id=skeleton_revision_id,
    )
    section = (batch.get("sections") or [{}])[0]
    section.update({
        "title": title,
        "content_summary": content_summary,
        "key_points": deepcopy(lecture.get("key_points") or []),
        "key_difficulties": deepcopy(lecture.get("key_difficulties") or []),
        "activities": deepcopy(lecture.get("activities") or []),
        "homework": deepcopy(lecture.get("homework") or []),
        "application_anchors": deepcopy(lecture.get("application_anchors") or []),
        "extension_resources": deepcopy(lecture.get("extension_resources") or []),
        "learning_tasks": deepcopy(lecture.get("learning_tasks") or []),
        "education_objective_refs": deepcopy(lecture.get("education_objective_refs") or []),
        "ideology_implementation": str(lecture.get("ideology_implementation") or ""),
        "external_mentor": deepcopy(lecture.get("external_mentor") or {}),
        "hour_breakdown": deepcopy(lecture.get("hour_breakdown") or {}),
        "planned_hours": lecture.get("planned_hours"),
        "week": lecture.get("week"),
    })
    batch["revision_id"] = stable_hash(batch, prefix="outline_batch_")
    return batch


def assemble_course_outline(
    *,
    skeleton: dict[str, Any],
    batch_specs: list[dict[str, Any]],
    batches: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    specs_by_chapter: dict[int, list[dict[str, Any]]] = {}
    for spec in batch_specs:
        specs_by_chapter.setdefault(
            int(spec.get("chapter_number") or 0),
            [],
        ).append(spec)
    chapters: list[dict[str, Any]] = []
    for chapter in skeleton.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        chapter_number = int(chapter.get("chapter_number") or len(chapters) + 1)
        sections: list[dict[str, Any]] = []
        for spec in sorted(
            specs_by_chapter.get(chapter_number, []),
            key=lambda item: int(item.get("start_section_index") or 0),
        ):
            batch = batches.get(str(spec.get("batch_id") or "")) or {}
            sections.extend(
                deepcopy(item)
                for item in batch.get("sections") or []
                if isinstance(item, dict)
            )
        chapters.append({
            "chapter_number": chapter_number,
            "lecture_number": (
                chapter_number
                if skeleton.get("authoring_structure_version") == "lecture_v1"
                else None
            ),
            "title": str(chapter.get("title") or f"第 {chapter_number} 章"),
            "planning_stages": _planning_stages(
                chapter.get("planning_stages") or chapter.get("planning_stage")
            ),
            "learning_focus": str(
                chapter.get("learning_focus") or chapter.get("title") or ""
            ),
            "learning_path_role": _learning_path_role(
                chapter.get("learning_path_role")
            ),
            "path_reason": str(
                chapter.get("path_reason") or "课程主路径"
            ),
            "content_summary": str(chapter.get("content_summary") or ""),
            "learning_objective": str(chapter.get("learning_objective") or ""),
            "key_points": deepcopy(chapter.get("key_points") or []),
            "key_difficulties": deepcopy(chapter.get("key_difficulties") or []),
            "activities": deepcopy(chapter.get("activities") or []),
            "homework": deepcopy(chapter.get("homework") or []),
            "application_anchors": deepcopy(chapter.get("application_anchors") or []),
            "extension_resources": deepcopy(chapter.get("extension_resources") or []),
            "learning_tasks": deepcopy(chapter.get("learning_tasks") or []),
            "education_objective_refs": deepcopy(chapter.get("education_objective_refs") or []),
            "ideology_implementation": str(chapter.get("ideology_implementation") or ""),
            "external_mentor": deepcopy(chapter.get("external_mentor") or {}),
            "hour_breakdown": deepcopy(chapter.get("hour_breakdown") or {}),
            "planned_hours": chapter.get("planned_hours"),
            "sections": sections,
        })
    return {
        "authoring_structure_version": str(
            skeleton.get("authoring_structure_version") or "legacy_chapter_v1"
        ),
        "formal_syllabus_contract_version": str(
            skeleton.get("formal_syllabus_contract_version") or ""
        ),
        "course_title": str(skeleton.get("course_title") or ""),
        "course_intro_zh": str(skeleton.get("course_intro_zh") or ""),
        "course_intro_en": str(skeleton.get("course_intro_en") or ""),
        "positioning": str(skeleton.get("positioning") or ""),
        "learning_objectives": list(
            skeleton.get("learning_objectives") or []
        ),
        "prerequisites": list(skeleton.get("prerequisites") or []),
        "education_objectives": list(
            skeleton.get("education_objectives") or []
        ),
        "measurable_outcomes": list(
            skeleton.get("measurable_outcomes") or []
        ),
        "outcome_alignment": deepcopy(
            skeleton.get("outcome_alignment") or []
        ),
        "teaching_methods": list(skeleton.get("teaching_methods") or []),
        "assessment_methods": list(
            skeleton.get("assessment_methods") or []
        ),
        "assessment_plan": deepcopy(skeleton.get("assessment_plan") or []),
        "course_modules": deepcopy(skeleton.get("course_modules") or []),
        "ideology_cases": deepcopy(skeleton.get("ideology_cases") or []),
        "reference_books": list(skeleton.get("reference_books") or []),
        "reference_websites": list(
            skeleton.get("reference_websites") or []
        ),
        "course_website": str(skeleton.get("course_website") or ""),
        "chapters": chapters,
    }


_QUALITY_RULE_VERSION = "course_outline_editorial_v6"
_QUOTED_TOPIC = re.compile(r"[“‘「『《][^”’」』》]{1,80}[”’」』》]")
_NUMBER_TOKEN = re.compile(r"(?:第\s*)?\d+(?:\.\d+)?(?:\s*[章节项个])?")
_QUALITY_PUNCTUATION = re.compile(r"[\s\W_]+", re.UNICODE)
_GENERIC_OBJECTIVE_PATTERNS = (
    re.compile(r"完成(?:第)?[^，。；]{0,24}(?:学习)?任务"),
    re.compile(r"围绕[^，。；]{0,30}完成[^，。；]{0,20}任务"),
    re.compile(r"掌握[^，。；]{0,30}(?:知识|内容|方法)$"),
)
_GENERIC_ASSESSMENT_PATTERNS = (
    re.compile(r"完成一项可检查的"),
    re.compile(r"提交并说明第?[^，。；]{0,20}(?:结果|任务)"),
    re.compile(r"能独立完成[^，。；]{0,40}(?:标准计算|条件判定|结果核验)"),
)
_SYSTEM_REGISTER_PATTERN = re.compile(
    r"全课知识地图|先修链定位|学习路径角色|可观察成果证据|证据闭环|"
    r"输入对象|输出对象|系统策略|课程主路径"
)


def _editorial_signature(value: Any, *, title: str = "") -> str:
    """Reduce a sentence to its reusable editorial template."""
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = _QUOTED_TOPIC.sub("主题", text)
    clean_title = re.sub(r"^\s*\d+(?:\.\d+)?\s*", "", title).strip().lower()
    if clean_title and len(clean_title) >= 2:
        text = text.replace(clean_title, "主题")
    text = _NUMBER_TOKEN.sub("序号", text)
    return _QUALITY_PUNCTUATION.sub("", text)


def _outline_assessment_items(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    item = str(value or "").strip()
    return [item] if item else []


def _editorial_issue(
    code: str,
    message: str,
    *,
    category: str,
    node_ids: list[str] | None = None,
    evidence: dict[str, Any] | None = None,
    repair_instruction: str = "",
    blocking: bool = False,
) -> dict[str, Any]:
    return {
        "code": code,
        "rule_version": _QUALITY_RULE_VERSION,
        "severity": "error" if blocking else "suggestion",
        "blocking": blocking,
        "category": category,
        "message": message,
        "node_ids": list(node_ids or []),
        "evidence": deepcopy(evidence or {}),
        "repair_instruction": repair_instruction,
    }


def _review_course_requirements(course_context: dict[str, Any] | None) -> dict[str, Any]:
    context = course_context if isinstance(course_context, dict) else {}
    request = context.get("generation_request") if isinstance(context.get("generation_request"), dict) else {}
    generation_brief = context.get("course_generation_brief") if isinstance(context.get("course_generation_brief"), dict) else {}
    profile = context.get("course_profile") if isinstance(context.get("course_profile"), dict) else {}
    if not profile:
        profile = generation_brief.get("formal_course_profile") if isinstance(generation_brief.get("formal_course_profile"), dict) else {}
    teacher = request.get("teacher_course_brief") if isinstance(request.get("teacher_course_brief"), dict) else {}
    if not teacher:
        teacher = context.get("teacher_course_brief") if isinstance(context.get("teacher_course_brief"), dict) else {}
    if not teacher:
        teacher = generation_brief.get("teacher_course_brief") if isinstance(generation_brief.get("teacher_course_brief"), dict) else {}
    total_hours = _non_negative_number(
        profile.get("total_hours") or teacher.get("total_class_hours")
    )
    template_constraints = teacher.get("syllabus_template_constraints")
    return {
        "total_hours": total_hours,
        "teaching_context": str(teacher.get("teaching_context") or "classroom"),
        "template_constraints": (
            template_constraints if isinstance(template_constraints, dict) else {}
        ),
    }


def review_course_outline_document(
    plan: dict[str, Any] | None,
    *,
    course_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Review a draft freely, but identify defects that block formal confirmation."""
    source = plan if isinstance(plan, dict) else {}
    formal_contract = (
        source.get("formal_syllabus_contract_version") == "formal_syllabus_v2"
    )
    requirements = _review_course_requirements(course_context)
    unit_label = (
        "讲"
        if source.get("authoring_structure_version") == "lecture_v1"
        else "小节"
    )
    chapters = [item for item in source.get("chapters") or [] if isinstance(item, dict)]
    sections = [
        section
        for chapter in chapters
        for section in chapter.get("sections") or []
        if isinstance(section, dict)
    ]
    issues: list[dict[str, Any]] = []
    if not str(source.get("positioning") or "").strip():
        issues.append(_editorial_issue(
            "outline_editorial:missing_positioning",
            "课程定位还没有说明这门课面向谁、解决什么问题以及最终形成什么能力。",
            category="document_identity",
            repair_instruction="补写课程定位：明确学习对象、课程边界与最终可观察成果，不改变章节结构。",
            blocking=formal_contract,
        ))
    if not [item for item in source.get("learning_objectives") or [] if str(item).strip()]:
        issues.append(_editorial_issue(
            "outline_editorial:missing_course_outcomes",
            "整门课程缺少可检查的学习成果，章节安排因此没有清晰的共同终点。",
            category="document_identity",
            repair_instruction="补充 3—5 条可观察、可评价的全课学习成果，不改变章节结构。",
            blocking=formal_contract,
        ))
    if formal_contract and not str(source.get("course_intro_zh") or "").strip():
        issues.append(_editorial_issue(
            "outline_editorial:missing_course_intro_zh",
            "正式大纲缺少中文课程简介。",
            category="document_identity",
            repair_instruction="根据现有课程定位、内容与教学方式补写中文课程简介，不新增课程事实。",
            blocking=True,
        ))
    if formal_contract and not str(source.get("course_intro_en") or "").strip():
        issues.append(_editorial_issue(
            "outline_editorial:missing_course_intro_en",
            "正式大纲缺少与中文内容对应的英文课程简介。",
            category="document_identity",
            repair_instruction="根据中文简介形成语义对应的英文简介，不增加中文版本没有的承诺。",
            blocking=True,
        ))
    education_objectives = [
        item for item in source.get("education_objectives") or []
        if str(item).strip()
    ]
    if formal_contract and not education_objectives:
        issues.append(_editorial_issue(
            "outline_editorial:missing_education_objectives",
            "课程整体还没有与真实教学内容相关的育人目标。",
            category="education",
            repair_instruction="从课程中的责任、规范、证据意识或社会影响提炼育人目标，不使用空泛口号。",
            blocking=True,
        ))
    measurable_outcomes = [
        item for item in source.get("measurable_outcomes") or []
        if str(item).strip()
    ]
    aligned_outcome_numbers = {
        _positive_int(item.get("outcome_number") or item.get("outcome_index"))
        for item in source.get("outcome_alignment") or []
        if isinstance(item, dict)
    }
    missing_outcome_numbers = [
        index for index in range(1, len(measurable_outcomes) + 1)
        if index not in aligned_outcome_numbers
    ]
    if missing_outcome_numbers:
        issues.append(_editorial_issue(
            "outline_editorial:missing_outcome_alignment",
            f"有 {len(missing_outcome_numbers)} 项可测量成果尚未关联课程目标、覆盖讲次和评价证据。",
            category="outcome_alignment",
            evidence={"outcome_numbers": missing_outcome_numbers},
            repair_instruction=(
                "只补充课程目标与预期成果关联：为每项可测量成果指明"
                "对应目标、覆盖讲次、评价证据和内容范围，不改变讲次结构。"
            ),
            blocking=formal_contract,
        ))
    if formal_contract and not measurable_outcomes:
        issues.append(_editorial_issue(
            "outline_editorial:missing_measurable_outcomes",
            "正式大纲缺少可验证的学习成果。",
            category="outcome_alignment",
            repair_instruction="补充可观察、可评价的成果，并建立目标、讲次与评价证据关联。",
            blocking=True,
        ))

    title_counts = Counter(
        signature
        for section in sections
        if (signature := _editorial_signature(section.get("title")))
    )
    duplicate_titles = {
        signature for signature, count in title_counts.items() if count > 1
    }
    duplicate_title_nodes = [
        str(section.get("node_id") or "")
        for section in sections
        if _editorial_signature(section.get("title")) in duplicate_titles
    ]
    if duplicate_title_nodes:
        issues.append(_editorial_issue(
            "outline_editorial:duplicate_section_titles",
            f"有 {len(duplicate_title_nodes)} {unit_label}使用了重复或近似重复的标题，课程推进层次不够清楚。",
            category="progression",
            node_ids=duplicate_title_nodes,
            evidence={"duplicate_template_count": len(duplicate_titles)},
            repair_instruction="重写这些小节标题与目标，使每节只承担一个不重复的学习责任；保留节点、章节归属和先后顺序。",
        ))

    overloaded_nodes: list[str] = []
    generic_objective_nodes: list[str] = []
    overlong_objective_nodes: list[str] = []
    system_register_nodes: list[str] = []
    generic_assessment_nodes: list[str] = []
    missing_assessment_nodes: list[str] = []
    missing_scope_nodes: list[str] = []
    objective_signatures: dict[str, list[str]] = {}
    assessment_signatures: dict[str, list[str]] = {}
    for section in sections:
        node_id = str(section.get("node_id") or "")
        title = str(section.get("title") or "")
        objective = str(section.get("learning_objective") or "").strip()
        assessments = _outline_assessment_items(section.get("assessment"))
        if len(title) > 32 and len(re.findall(r"[、/：]|(?:与|及|和|并)", title)) >= 2:
            overloaded_nodes.append(node_id)
        if not objective or any(pattern.search(objective) for pattern in _GENERIC_OBJECTIVE_PATTERNS):
            generic_objective_nodes.append(node_id)
        if len(objective) > 120 or len(re.findall(r"[；;]", objective)) >= 4:
            overlong_objective_nodes.append(node_id)
        if (
            _SYSTEM_REGISTER_PATTERN.search(" ".join((title, objective)))
            or has_unnatural_system_language(" ".join((title, objective)))
        ):
            system_register_nodes.append(node_id)
        objective_signature = _editorial_signature(objective, title=title)
        if objective_signature:
            objective_signatures.setdefault(objective_signature, []).append(node_id)
        if not assessments:
            missing_assessment_nodes.append(node_id)
        if not str(section.get("scope_boundary") or "").strip():
            missing_scope_nodes.append(node_id)
        for assessment in assessments:
            if any(pattern.search(assessment) for pattern in _GENERIC_ASSESSMENT_PATTERNS):
                generic_assessment_nodes.append(node_id)
            signature = _editorial_signature(assessment, title=title)
            if signature:
                assessment_signatures.setdefault(signature, []).append(node_id)

    if overloaded_nodes:
        issues.append(_editorial_issue(
            "outline_editorial:overloaded_section_titles",
            f"有 {len(overloaded_nodes)} {unit_label}的标题同时塞入多个主题，建议拆清主任务或收紧命名。",
            category="progression",
            node_ids=overloaded_nodes,
            repair_instruction="收紧这些小节的标题与学习目标，每节只保留一个主任务；不改变节点数量和顺序。",
        ))
    if generic_objective_nodes:
        unique_nodes = list(dict.fromkeys(generic_objective_nodes))
        issues.append(_editorial_issue(
            "outline_editorial:generic_objectives",
            f"有 {len(unique_nodes)} {unit_label}的目标仍是通用任务句，教师难以判断学生究竟要学会什么。",
            category="outcome_quality",
            node_ids=unique_nodes,
            repair_instruction="把这些小节目标改成“动作 + 对象 + 条件/标准”的可观察表达；保持节点、标题、章节归属和顺序不变。",
        ))
    if overlong_objective_nodes:
        unique_nodes = list(dict.fromkeys(overlong_objective_nodes))
        issues.append(_editorial_issue(
            "outline_editorial:overlong_objectives",
            f"有 {len(unique_nodes)} {unit_label}的目标塞入过多动作与判断条件，读起来不像课程大纲。",
            category="outcome_quality",
            node_ids=unique_nodes,
            repair_instruction=(
                "把目标收成一至两句，只保留本节最主要的学习结果；知识点、易错点和"
                "验收细则留给教案与评价，不在大纲目标中展开。"
            ),
        ))
    document_register_text = " ".join([
        str(source.get("positioning") or ""),
        *[
            str(chapter.get("learning_focus") or "")
            for chapter in chapters
        ],
    ])
    if (
        _SYSTEM_REGISTER_PATTERN.search(document_register_text)
        or has_unnatural_system_language(document_register_text)
        or system_register_nodes
    ):
        unique_nodes = list(dict.fromkeys(system_register_nodes))
        issues.append(_editorial_issue(
            "outline_editorial:system_register",
            "教师可见大纲混入了系统规划术语，表达不像真实课程标准或教学大纲。",
            category="teacher_register",
            node_ids=unique_nodes,
            repair_instruction=(
                "改用课程大纲常用表达，直接说明学习内容与学生要达到的结果；不要出现"
                "知识地图、先修链定位、路径角色、内部证据流程或系统策略等规划语言。"
            ),
        ))
    if missing_assessment_nodes:
        issues.append(_editorial_issue(
            "outline_editorial:missing_assessments",
            f"有 {len(missing_assessment_nodes)} {unit_label}没有达成检验，目标还不能被课堂验证。",
            category="assessment_quality",
            node_ids=missing_assessment_nodes,
            repair_instruction=f"为这些{unit_label}各补充一项与目标直接对应的达成检验，写清学生产出与判断标准；不改变结构。",
        ))
    if missing_scope_nodes:
        issues.append(_editorial_issue(
            "outline_editorial:missing_scope_boundaries",
            f"有 {len(missing_scope_nodes)} {unit_label}没有说清自己负责到哪里，与前后内容的边界还不明确。",
            category="progression",
            node_ids=missing_scope_nodes,
            repair_instruction=f"为这些{unit_label}补充范围说明：写清当前{unit_label}负责的内容，以及明确不提前展开什么；不改变结构。",
        ))

    minimum_repetition = max(3, math.ceil(max(1, len(sections)) * 0.35))
    repeated_objective_nodes = list(dict.fromkeys(
        node_id
        for nodes in objective_signatures.values()
        if len(nodes) >= minimum_repetition
        for node_id in nodes
    ))
    repeated_assessment_nodes = list(dict.fromkeys(
        node_id
        for nodes in assessment_signatures.values()
        if len(nodes) >= minimum_repetition
        for node_id in nodes
    ))
    if repeated_objective_nodes:
        issues.append(_editorial_issue(
            "outline_editorial:repeated_objective_template",
            f"有 {len(repeated_objective_nodes)} {unit_label}沿用同一种目标句式，只替换了主题名称。",
            category="outcome_quality",
            node_ids=repeated_objective_nodes,
            evidence={"threshold": minimum_repetition},
            repair_instruction="重写这些小节的学习目标，让动作、学习对象与完成标准随具体内容变化；保留节点、标题和顺序。",
        ))
    combined_assessment_nodes = list(dict.fromkeys([
        *generic_assessment_nodes,
        *repeated_assessment_nodes,
    ]))
    if combined_assessment_nodes:
        issues.append(_editorial_issue(
            "outline_editorial:repeated_assessment_template",
            f"有 {len(combined_assessment_nodes)} {unit_label}的达成检验过于模板化，无法体现不同{unit_label}的能力要求。",
            category="assessment_quality",
            node_ids=combined_assessment_nodes,
            evidence={"threshold": minimum_repetition},
            repair_instruction=(
                f"只重写这些{unit_label}的范围说明与达成检验：为每{unit_label}选择与目标相符的不同证据形态，"
                "如解释、推导、判错、比较、设计、实作或迁移；写清产出和判断标准，"
                "保留节点、标题、目标、章节归属与顺序。"
            ),
        ))

    if formal_contract:
        missing_anchor_nodes: list[str] = []
        missing_resource_nodes: list[str] = []
        unverified_resource_nodes: list[str] = []
        missing_task_nodes: list[str] = []
        missing_online_task_nodes: list[str] = []
        missing_hour_nodes: list[str] = []
        official_hours = 0.0
        online_hours = 0.0
        classroom_hours = 0.0
        teaching_context = requirements["teaching_context"]
        confirmed_reference_labels = {
            str(item).strip()
            for item in [
                *(source.get("reference_books") or []),
                *(source.get("reference_websites") or []),
            ]
            if str(item).strip()
        }
        for section in sections:
            node_id = str(section.get("node_id") or "")
            if not _text_items(section.get("application_anchors"), max_chars=240, limit=6):
                missing_anchor_nodes.append(node_id)
            resources = [
                item for item in section.get("extension_resources") or []
                if isinstance(item, dict)
            ]
            if not resources:
                missing_resource_nodes.append(node_id)
            elif any(
                item.get("verification_status") != "verified"
                or not str(item.get("source_ref") or "").strip()
                or str(item.get("source_ref") or "").strip() not in confirmed_reference_labels
                or (
                    item.get("resource_type") == "book"
                    and (
                        not str(item.get("edition") or "").strip()
                        or not str(item.get("locator") or "").strip()
                    )
                )
                for item in resources
            ):
                unverified_resource_nodes.append(node_id)
            tasks = [
                item for item in section.get("learning_tasks") or []
                if isinstance(item, dict) and str(item.get("task") or "").strip()
            ]
            if not tasks:
                missing_task_nodes.append(node_id)
            elif teaching_context in {"online", "blended"} and not any(
                item.get("mode") == "online" for item in tasks
            ):
                missing_online_task_nodes.append(node_id)
            breakdown = (
                section.get("hour_breakdown")
                if isinstance(section.get("hour_breakdown"), dict)
                else {}
            )
            lecture_hours = _non_negative_number(breakdown.get("classroom_lecture"))
            practice_hours = _non_negative_number(breakdown.get("classroom_practice"))
            lecture_online_hours = _non_negative_number(breakdown.get("online_instruction"))
            section_hours = lecture_hours + practice_hours + lecture_online_hours
            if section_hours <= 0:
                missing_hour_nodes.append(node_id)
            official_hours += section_hours
            classroom_hours += lecture_hours + practice_hours
            online_hours += lecture_online_hours

        for code, message, category, node_ids, instruction in (
            (
                "outline_editorial:missing_application_anchors",
                f"有 {len(missing_anchor_nodes)} 讲缺少案例、问题、例题、实验或项目情境。",
                "lecture_contract",
                missing_anchor_nodes,
                "为这些讲次各补充一个真正承载本讲内容的应用情境，不强行套用同一种案例形式。",
            ),
            (
                "outline_editorial:missing_extension_resources",
                f"有 {len(missing_resource_nodes)} 讲缺少拓展资源。",
                "reference_quality",
                missing_resource_nodes,
                "从教师已确认来源中为这些讲次选择相关资源；没有来源时标记缺口，不得编造。",
            ),
            (
                "outline_editorial:unverified_extension_resources",
                f"有 {len(unverified_resource_nodes)} 讲的拓展资源尚未核验来源、版次或定位信息。",
                "reference_quality",
                unverified_resource_nodes,
                "核对来源；书籍确认版次与章节后再填写页码，无法核验的内容继续标记待补充。",
            ),
            (
                "outline_editorial:missing_learning_tasks",
                f"有 {len(missing_task_nodes)} 讲缺少课前或课后学习任务。",
                "lecture_contract",
                missing_task_nodes,
                "为这些讲次补充学习任务、完成方式和学生留下的证据。",
            ),
            (
                "outline_editorial:missing_online_learning_tasks",
                f"有 {len(missing_online_task_nodes)} 讲不符合当前授课模式，缺少线上学习任务。",
                "lecture_contract",
                missing_online_task_nodes,
                "为这些讲次补充线上课前或课后任务；纯线下任务不能冒充线上学习。",
            ),
            (
                "outline_editorial:missing_hour_breakdown",
                f"有 {len(missing_hour_nodes)} 讲没有分配线下讲授、线下实践或在线教学学时。",
                "hours",
                missing_hour_nodes,
                "按实际授课方式补充分项学时；课外任务用预计学习负担记录，不计入总学时。",
            ),
        ):
            if node_ids:
                issues.append(_editorial_issue(
                    code,
                    message,
                    category=category,
                    node_ids=node_ids,
                    repair_instruction=instruction,
                    blocking=True,
                ))

        expected_hours = requirements["total_hours"]
        if expected_hours and abs(official_hours - expected_hours) > 0.01:
            issues.append(_editorial_issue(
                "outline_editorial:hour_total_mismatch",
                f"各讲计入总学时的合计为 {official_hours:g}，与课程总学时 {expected_hours:g} 不一致。",
                category="hours",
                evidence={"actual_hours": official_hours, "expected_hours": expected_hours},
                repair_instruction="调整各讲分项学时，使线下讲授、线下实践和在线教学合计等于课程总学时。",
                blocking=True,
            ))
        mode_invalid = (
            teaching_context == "classroom" and online_hours > 0
        ) or (
            teaching_context in {"online", "self_study"} and classroom_hours > 0
        ) or (
            teaching_context == "blended" and (classroom_hours <= 0 or online_hours <= 0)
        )
        if mode_invalid:
            issues.append(_editorial_issue(
                "outline_editorial:hour_mode_mismatch",
                "学时分配与已确认的授课模式不一致。",
                category="hours",
                evidence={
                    "teaching_context": teaching_context,
                    "classroom_hours": classroom_hours,
                    "online_hours": online_hours,
                },
                repair_instruction="按照已确认授课模式重新分配线下讲授、线下实践和在线教学学时。",
                blocking=True,
            ))

        assessment_plan = [
            item for item in source.get("assessment_plan") or []
            if isinstance(item, dict)
        ]
        if not assessment_plan:
            issues.append(_editorial_issue(
                "outline_editorial:missing_assessment_plan",
                "正式大纲缺少结构化考核权重与评分标准。",
                category="assessment_plan",
                repair_instruction="补充过程性与终结性评价，权重合计100%，并关联可测量成果。",
                blocking=True,
            ))
        else:
            assessment_weight = sum(
                _non_negative_number(item.get("weight_percent"))
                for item in assessment_plan
            )
            categories = {str(item.get("category") or "") for item in assessment_plan}
            if abs(assessment_weight - 100.0) > 0.01:
                issues.append(_editorial_issue(
                    "outline_editorial:assessment_weight_mismatch",
                    f"考核权重合计为 {assessment_weight:g}%，必须为100%。",
                    category="assessment_plan",
                    evidence={"weight_percent": assessment_weight},
                    repair_instruction="调整各考核项目权重，使合计恰好为100%。",
                    blocking=True,
                ))
            if not {"formative", "summative"}.issubset(categories):
                issues.append(_editorial_issue(
                    "outline_editorial:assessment_category_missing",
                    "考核方案必须同时包含过程性评价和终结性评价。",
                    category="assessment_plan",
                    repair_instruction="补齐过程性或终结性评价，并重新检查权重与成果关联。",
                    blocking=True,
                ))
            incomplete_assessments = [
                index for index, item in enumerate(assessment_plan, start=1)
                if not str(item.get("criteria") or "").strip()
                or not list(item.get("outcome_numbers") or [])
            ]
            if incomplete_assessments:
                issues.append(_editorial_issue(
                    "outline_editorial:assessment_evidence_missing",
                    f"有 {len(incomplete_assessments)} 项考核缺少评分标准或成果关联。",
                    category="assessment_plan",
                    evidence={"assessment_numbers": incomplete_assessments},
                    repair_instruction="为每项考核写清评分标准并关联至少一项可测量成果。",
                    blocking=True,
                ))

        modules = [
            item for item in source.get("course_modules") or []
            if isinstance(item, dict)
        ]
        module_lecture_numbers = [
            _positive_int(number)
            for item in modules
            for number in item.get("lecture_numbers") or []
            if _positive_int(number)
        ]
        expected_lecture_numbers = list(range(1, len(chapters) + 1))
        if not modules:
            issues.append(_editorial_issue(
                "outline_editorial:missing_course_modules",
                "讲次尚未归入知识模块。",
                category="module_grouping",
                repair_instruction="按内容关系给讲次分组；模块只保存讲次范围，不新增课程层级。",
                blocking=True,
            ))
        elif sorted(module_lecture_numbers) != expected_lecture_numbers:
            issues.append(_editorial_issue(
                "outline_editorial:module_lecture_coverage",
                "知识模块必须完整覆盖所有讲次，且每讲只能归入一个模块。",
                category="module_grouping",
                evidence={
                    "actual": module_lecture_numbers,
                    "expected": expected_lecture_numbers,
                },
                repair_instruction="调整模块包含的讲次，使每讲恰好出现一次；不要生成模块节点。",
                blocking=True,
            ))

        template = requirements["template_constraints"]
        checks = {
            "intro_zh_chars": len(str(source.get("course_intro_zh") or "").strip()),
            "learning_objective_count": len([item for item in source.get("learning_objectives") or [] if str(item).strip()]),
            "education_objective_count": len(education_objectives),
            "measurable_outcome_count": len(measurable_outcomes),
            "reference_count": len(source.get("reference_books") or []) + len(source.get("reference_websites") or []),
            "module_count": len(modules),
        }
        violations: list[str] = []
        for key, actual in checks.items():
            minimum = _positive_int(template.get(f"{key}_min"))
            maximum = _positive_int(template.get(f"{key}_max"))
            exact = _positive_int(template.get(key))
            if exact is not None and actual != exact:
                violations.append(f"{key} 应为 {exact}，实际为 {actual}")
            elif minimum is not None and actual < minimum:
                violations.append(f"{key} 至少为 {minimum}，实际为 {actual}")
            elif maximum is not None and actual > maximum:
                violations.append(f"{key} 至多为 {maximum}，实际为 {actual}")
        if violations:
            issues.append(_editorial_issue(
                "outline_editorial:template_constraint_mismatch",
                "大纲不符合教师或学校明确指定的模板数字要求。",
                category="template_constraints",
                evidence={"violations": violations},
                repair_instruction="只按已确认模板调整对应字数或条数，未指定的数字不设全局硬限制。",
                blocking=True,
            ))

    blocking_issues = [item for item in issues if item.get("blocking")]
    metrics = {
        "chapter_count": len(chapters),
        "section_count": len(sections),
        "issue_count": len(issues),
        "located_section_count": len({
            node_id
            for issue in issues
            for node_id in issue.get("node_ids") or []
            if node_id
        }),
    }
    report = {
        "schema_version": "course_outline_editorial_review_v5",
        "rule_version": _QUALITY_RULE_VERSION,
        "non_blocking": not blocking_issues,
        "passed": not blocking_issues,
        "can_confirm": not blocking_issues,
        "blocking_issues": blocking_issues,
        "status": "confirmation_blocked" if blocking_issues else ("review_suggested" if issues else "ready"),
        "summary": (
            f"大纲草稿已生成；仍有 {len(blocking_issues)} 类正式确认条件未满足。"
            if blocking_issues
            else f"大纲已生成，可继续编辑和确认；发现 {len(issues)} 类内容建议。"
            if issues
            else "整篇大纲未发现高频专业表达问题。"
        ),
        "metrics": metrics,
        "issues": issues,
    }
    report["revision_id"] = stable_hash(report, prefix="outline_editorial_")
    return report


def outline_neighbor_chapters(
    skeleton: dict[str, Any],
    chapter_number: int,
) -> list[dict[str, Any]]:
    """Expose only the adjacent chapter contracts, not the whole course payload."""
    return [
        deepcopy(item)
        for item in skeleton.get("chapters") or []
        if isinstance(item, dict)
        and abs(int(item.get("chapter_number") or 0) - chapter_number) <= 1
    ]


def select_chapter_evidence_hints(
    artifacts: dict[str, Any],
    chapter: dict[str, Any],
    *,
    max_items: int = 4,
) -> list[dict[str, str]]:
    """Select a tiny chapter-local evidence index without rebroadcasting files."""
    query = " ".join([
        str(chapter.get("title") or ""),
        str(chapter.get("learning_focus") or ""),
    ])
    query_tokens = set(_keywords(query))
    ranked: list[tuple[float, dict[str, Any]]] = []
    for item in artifacts.get("evidence_catalog") or []:
        if not isinstance(item, dict):
            continue
        item_tokens = {
            str(token).lower()
            for token in item.get("keywords") or []
        }
        overlap = len(query_tokens & item_tokens)
        score = float(overlap)
        if item.get("priority") == "core":
            score += 0.4
        if item.get("authority") == "primary":
            score += 0.2
        if score > 0:
            ranked.append((score, item))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {
            "evidence_id": str(item.get("evidence_id") or ""),
            "kind": str(item.get("kind") or ""),
            "summary": _clip(
                item.get("summary") or item.get("source_text") or "",
                180,
            ),
        }
        for _score, item in ranked[:max_items]
    ]


def _keywords(text: str) -> list[str]:
    english = re.findall(r"[A-Za-z][A-Za-z0-9_+-]{1,30}", text.lower())
    chinese_groups = re.findall(r"[\u4e00-\u9fff]{2,20}", text)
    chinese: list[str] = []
    for group in chinese_groups:
        chinese.append(group)
        for width in (2, 3, 4):
            chinese.extend(
                group[index:index + width]
                for index in range(max(0, len(group) - width + 1))
            )
    return list(dict.fromkeys([*english, *chinese]))[:32]


def _section_index(node_id: str) -> int:
    try:
        return int(str(node_id).rsplit("-", 1)[-1])
    except (TypeError, ValueError):
        return -1


def _learning_path_role(value: Any) -> str:
    role = str(value or "").strip()
    if role in {
        "focus",
        "standard",
        "compressed",
        "verify_in_project",
        "milestone",
    }:
        return role
    return "standard"


def _issue(code: str, message: str) -> dict[str, str]:
    return {
        "code": code,
        "severity": "critical",
        "message": message,
    }


__all__ = [
    "CourseOutlinePlanningBudget",
    "assemble_course_outline",
    "build_outline_batch_specs",
    "build_teacher_outline_detail_batch_specs",
    "compile_fallback_outline_batch",
    "compile_teacher_lecture_outline_batch",
    "course_coverage_verdict",
    "merge_teacher_outline_detail",
    "normalize_outline_batch",
    "normalize_outline_skeleton",
    "normalize_teacher_outline_detail_batch",
    "outline_neighbor_chapters",
    "outline_request_fingerprint",
    "project_streamed_teacher_outline_growth",
    "review_course_outline_document",
    "select_chapter_evidence_hints",
    "validate_outline_batch",
    "validate_outline_skeleton",
    "validate_teacher_outline_detail_batch",
]
