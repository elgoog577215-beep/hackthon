"""Reviewable course-framing drafts and confirmed baseline commands."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from typing import Any

from course_document import stable_hash
from models import CourseGenerationRequest


COURSE_TYPES = {"systematic", "project", "inquiry", "exam"}
DIFFICULTIES = {"beginner", "intermediate", "advanced"}
PEDAGOGY_MODES = {
    "auto",
    "general",
    "math_formal",
    "programming_engineering",
    "natural_science",
    "life_medical",
    "humanities_social",
    "language_learning",
    "business_career",
}
PRODUCTION_MODES = {"manual", "automatic"}


def baseline_revision(course: dict[str, Any]) -> int:
    try:
        return max(0, int(course.get("generation_request_revision") or 0))
    except (TypeError, ValueError):
        return 0


def confirmed_generation_request(value: CourseGenerationRequest) -> dict[str, Any]:
    """Return the persisted baseline without per-run command identity fields."""
    return value.model_dump(
        mode="json",
        exclude={"request_id", "target_course_id"},
    )


def baseline_changed_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    before_brief = before.get("teacher_course_brief") or {}
    after_brief = after.get("teacher_course_brief") or {}
    fields = {
        "course_type": before.get("course_type") != after.get("course_type"),
        "learning_goal": _goal(before) != _goal(after),
        "difficulty": before.get("difficulty") != after.get("difficulty"),
        "pedagogy_mode": before.get("pedagogy_mode") != after.get("pedagogy_mode"),
        "course_scale": (
            before_brief.get("total_class_hours"),
            before_brief.get("section_count"),
        ) != (
            after_brief.get("total_class_hours"),
            after_brief.get("section_count"),
        ),
        "production_mode": before.get("production_mode") != after.get("production_mode"),
    }
    return [key for key, changed in fields.items() if changed]


def build_baseline_mutation(
    *,
    expected_revision: int,
    generation_request: dict[str, Any],
    source: str,
    draft_id: str,
):
    """Build the metadata mutation used by the canonical course command boundary."""

    def mutate(raw: dict[str, Any]) -> None:
        current_revision = baseline_revision(raw)
        if current_revision != expected_revision:
            raise ValueError("course_baseline_revision_changed")
        previous = deepcopy(raw.get("generation_request") or {})
        next_revision = current_revision + 1
        changed_fields = baseline_changed_fields(previous, generation_request)
        now = datetime.now(timezone.utc).isoformat()
        history = list(raw.get("generation_request_history") or [])
        history.append({
            "schema_version": "generation_request_history_v1",
            "revision": next_revision,
            "previous_revision": current_revision,
            "source": source,
            "draft_id": draft_id,
            "changed_fields": changed_fields,
            "previous": previous,
            "committed_at": now,
        })
        raw["generation_request"] = deepcopy(generation_request)
        raw["generation_request_revision"] = next_revision
        raw["generation_request_history"] = history[-20:]
        raw["updated_at"] = now

    return mutate


def build_ai_baseline_prompt(
    course: dict[str, Any],
    conversation: dict[str, Any],
    *,
    through_message_id: str = "",
) -> str:
    messages: list[dict[str, str]] = []
    for item in conversation.get("messages") or []:
        role = str(item.get("role") or "")
        if role not in {"user", "assistant"}:
            continue
        if role == "assistant" and item.get("status") == "failed":
            continue
        content = str(item.get("content") or "").strip()
        if content:
            messages.append({"role": role, "content": content[:3000]})
        if through_message_id and str(item.get("message_id") or "") == through_message_id:
            break
    transcript = messages[-12:]
    schema = {
        "updates": {
            "course_type": "systematic | project | inquiry | exam | null",
            "learning_goal": "string | null",
            "difficulty": "beginner | intermediate | advanced | null",
            "pedagogy_mode": "auto | general | math_formal | programming_engineering | natural_science | life_medical | humanities_social | language_learning | business_career | null",
            "total_class_hours": "integer 1..1000 | null",
            "section_count": "integer 1..1000 | null",
            "production_mode": "manual | automatic | null",
        },
        "evidence": ["brief reason grounded in the transcript"],
    }
    return (
        "请把教师与 AI 的课程定调讨论提取为一份待审阅表单草稿。\n"
        "只提取对话明确支持的字段；没有依据的字段必须为 null，不能自行补造。\n"
        "learning_goal 表示完成课程后学习者应达到的结果，不是课程名称。\n"
        "只输出 JSON，不要输出 Markdown。\n"
        f"输出结构：{json.dumps(schema, ensure_ascii=False)}\n"
        f"当前课程：{course.get('course_name') or ''}\n"
        f"当前基线：{json.dumps(course.get('generation_request') or {}, ensure_ascii=False)}\n"
        f"本次对话：{json.dumps(transcript, ensure_ascii=False)}"
    )


def merge_ai_baseline_draft(
    course: dict[str, Any],
    extracted: dict[str, Any],
    *,
    conversation_id: str,
    source_message_ids: list[str],
) -> dict[str, Any]:
    """Merge a bounded model extraction into the current baseline.

    Unknown keys and invalid values are discarded. Missing values preserve the
    current baseline, so an AI draft cannot erase settings the conversation did
    not cover.
    """
    current = deepcopy(course.get("generation_request") or {})
    candidate = deepcopy(current)
    updates = extracted.get("updates") if isinstance(extracted.get("updates"), dict) else {}

    course_type = _enum(updates.get("course_type"), COURSE_TYPES)
    if course_type:
        candidate["course_type"] = course_type
        candidate["course_purpose"] = "exam_sprint" if course_type == "exam" else "systematic"
        candidate["composition_style"] = {
            "systematic": "balanced",
            "project": "project_driven",
            "inquiry": "inquiry_driven",
            "exam": "example_driven",
        }[course_type]
    else:
        course_type = str(candidate.get("course_type") or "systematic")

    learning_goal = _text(updates.get("learning_goal"), limit=5000)
    if learning_goal:
        candidate["course_intent"] = _intent_with_goal(
            course_type,
            learning_goal,
            candidate.get("course_intent") or {},
            str(candidate.get("subject") or course.get("course_name") or ""),
        )

    difficulty = _enum(updates.get("difficulty"), DIFFICULTIES)
    if difficulty:
        candidate["difficulty"] = difficulty
    pedagogy_mode = _enum(updates.get("pedagogy_mode"), PEDAGOGY_MODES)
    if pedagogy_mode:
        candidate["pedagogy_mode"] = pedagogy_mode
    production_mode = _enum(updates.get("production_mode"), PRODUCTION_MODES)
    if production_mode:
        candidate["production_mode"] = production_mode

    brief = deepcopy(candidate.get("teacher_course_brief") or {})
    hours = _integer(updates.get("total_class_hours"), 1, 1000)
    sections = _integer(updates.get("section_count"), 1, 1000)
    if hours is not None or sections is not None:
        brief.setdefault("schema_version", "teacher_course_brief_v1")
        brief.setdefault("target_audience", candidate.get("target_audience") or "大学生")
        brief.setdefault("total_class_hours", 16)
        brief.setdefault("lesson_duration_minutes", 45)
        brief.setdefault("teaching_context", "classroom")
        if hours is not None:
            brief["total_class_hours"] = hours
        if sections is not None:
            brief["section_count"] = sections
        candidate["teacher_course_brief"] = brief

    changed_fields = baseline_changed_fields(current, candidate)
    payload = {
        "course_id": str(course.get("course_id") or ""),
        "conversation_id": conversation_id,
        "based_on_revision": baseline_revision(course),
        "generation_request": candidate,
        "changed_fields": changed_fields,
        "source_message_ids": source_message_ids,
        "evidence": [
            _text(item, limit=300)
            for item in (extracted.get("evidence") or [])[:6]
            if _text(item, limit=300)
        ],
    }
    payload["draft_id"] = stable_hash(payload, prefix="cbd_")
    return payload


def _goal(request: dict[str, Any]) -> str:
    intent = request.get("course_intent") or {}
    intent_type = str(intent.get("type") or request.get("course_type") or "systematic")
    if intent_type == "project":
        return str(intent.get("project_goal") or "")
    if intent_type == "inquiry":
        return str(intent.get("desired_output") or intent.get("core_question") or "")
    if intent_type == "exam":
        return str(intent.get("exam_scope") or intent.get("exam_name") or "")
    return str(intent.get("learning_goal") or intent.get("desired_outcome") or "")


def _intent_with_goal(
    course_type: str,
    goal: str,
    existing: dict[str, Any],
    subject: str,
) -> dict[str, Any]:
    if course_type == "project":
        return {
            "schema_version": "course_intent_v1",
            "type": "project",
            "project_goal": goal,
            "expected_deliverable": str(existing.get("expected_deliverable") or ""),
            "prior_experience": str(existing.get("prior_experience") or ""),
            "current_uncertainty": str(existing.get("current_uncertainty") or ""),
            "project_constraints": str(existing.get("project_constraints") or ""),
        }
    if course_type == "inquiry":
        return {
            "schema_version": "course_intent_v1",
            "type": "inquiry",
            "core_question": str(existing.get("core_question") or subject),
            "desired_output": goal,
            "existing_understanding": str(existing.get("existing_understanding") or ""),
            "evidence_scope": str(existing.get("evidence_scope") or ""),
        }
    if course_type == "exam":
        return {
            "schema_version": "course_intent_v1",
            "type": "exam",
            "exam_name": str(existing.get("exam_name") or subject),
            "exam_date": str(existing.get("exam_date") or ""),
            "exam_scope": goal,
            "current_preparation": str(existing.get("current_preparation") or ""),
        }
    return {
        "schema_version": "course_intent_v1",
        "type": "systematic",
        "learning_goal": goal,
        "desired_outcome": str(existing.get("desired_outcome") or ""),
        "existing_foundation": str(existing.get("existing_foundation") or ""),
    }


def _enum(value: Any, allowed: set[str]) -> str:
    normalized = str(value or "").strip()
    return normalized if normalized in allowed else ""


def _text(value: Any, *, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _integer(value: Any, minimum: int, maximum: int) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if minimum <= parsed <= maximum else None


__all__ = [
    "baseline_changed_fields",
    "baseline_revision",
    "build_ai_baseline_prompt",
    "build_baseline_mutation",
    "confirmed_generation_request",
    "merge_ai_baseline_draft",
]
