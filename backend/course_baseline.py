"""Reviewable course-framing drafts and confirmed baseline commands."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from typing import Any

from course_document import stable_hash
from models import CourseGenerationRequest
from teaching_design import (
    COURSE_TEACHING_TYPES,
    LEARNING_PURPOSES,
    resolve_course_teaching_type,
    resolve_learning_purpose,
)


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

COURSE_PROFILE_FIELDS = (
    "english_name",
    "course_code",
    "course_goal",
    "default_location",
    "target_grade",
    "course_category",
    "target_major",
    "credits",
    "weekly_hours",
    "total_hours",
    "prerequisite_courses",
    "weekday",
    "periods",
    "assessment_method",
    "course_intro",
    "teaching_goals",
)


def _canonical_generation_request(value: dict[str, Any]) -> dict[str, Any]:
    """Keep new baseline writes on the three teacher-facing classifications."""
    request = deepcopy(value)
    legacy_course_type = str(request.get("course_type") or "").strip()
    learning_purpose = resolve_learning_purpose(
        request.get("learning_purpose"),
        legacy_course_type=legacy_course_type,
    )
    course_teaching_type, _ = resolve_course_teaching_type(
        request.get("course_teaching_type"),
        learning_purpose=learning_purpose,
        legacy_course_type=legacy_course_type,
        composition_style=request.get("composition_style"),
    )
    request["learning_purpose"] = learning_purpose
    request["course_teaching_type"] = course_teaching_type
    intent = request.get("course_intent")
    if isinstance(intent, dict) and str(intent.get("type") or "") == "inquiry":
        goal = "；".join(
            item
            for item in (
                str(intent.get("core_question") or "").strip(),
                str(intent.get("desired_output") or "").strip(),
            )
            if item
        )
        request["course_intent"] = {
            "schema_version": "course_intent_v1",
            "type": "systematic",
            "learning_goal": goal or str(request.get("subject") or "").strip(),
        }
    for legacy_field in ("course_type", "composition_style", "course_purpose"):
        request.pop(legacy_field, None)
    return request


def canonical_generation_request(value: dict[str, Any]) -> dict[str, Any]:
    """Return the current teacher-facing generation request for persistence.

    Runtime workers may still read the legacy fields while old jobs are being
    migrated, but every new formal write must pass through this boundary so a
    course never stores two competing classification systems.
    """
    return _canonical_generation_request(value)


def baseline_revision(course: dict[str, Any]) -> int:
    try:
        return max(0, int(course.get("generation_request_revision") or 0))
    except (TypeError, ValueError):
        return 0


def course_information_revision(course: dict[str, Any]) -> int:
    """Return the aggregate course-information revision.

    Existing courses only have ``generation_request_revision``. Reusing that
    value as the first aggregate revision preserves optimistic concurrency
    without silently migrating data on read.
    """
    try:
        value = course.get("course_information_revision")
        return max(0, int(value if value is not None else baseline_revision(course)))
    except (TypeError, ValueError):
        return baseline_revision(course)


def course_information_snapshot(course: dict[str, Any]) -> dict[str, Any]:
    profile = course.get("course_profile")
    if not isinstance(profile, dict):
        profile = {}
    request = course.get("generation_request")
    if not isinstance(request, dict):
        request = {}
    snapshot = {
        "course_name": str(course.get("course_name") or ""),
        "academic_year": str(course.get("academic_year") or ""),
        "term": str(course.get("term") or ""),
        "course_profile": {
            field: (
                deepcopy(profile.get(field))
                if field in {"credits", "weekly_hours", "total_hours"}
                else str(profile.get(field) or "")
            )
            for field in COURSE_PROFILE_FIELDS
        },
        "generation_request": deepcopy(request),
    }
    return normalize_course_information(course, snapshot)


def normalize_course_information(
    course: dict[str, Any],
    information: dict[str, Any],
) -> dict[str, Any]:
    """Synchronize duplicate creation/profile fields at the command boundary."""
    normalized = deepcopy(information)
    normalized["course_name"] = str(course.get("course_name") or "")
    normalized["academic_year"] = str(normalized.get("academic_year") or "").strip()
    normalized["term"] = str(normalized.get("term") or "").strip()

    profile = normalized.get("course_profile")
    if not isinstance(profile, dict):
        profile = {}
    profile = {
        field: deepcopy(profile.get(field))
        for field in COURSE_PROFILE_FIELDS
    }
    request = normalized.get("generation_request")
    if not isinstance(request, dict):
        request = {}
    request = _canonical_generation_request(request)
    brief = request.get("teacher_course_brief")
    if not isinstance(brief, dict):
        brief = {}
    brief = deepcopy(brief)

    brief.setdefault("schema_version", "teacher_course_brief_v1")
    brief.setdefault("total_class_hours", profile.get("total_hours") or 32)
    brief.setdefault("lesson_duration_minutes", 45)
    brief.setdefault("teaching_context", "classroom")

    total_hours = brief.get("total_class_hours")
    if total_hours is not None:
        profile["total_hours"] = total_hours

    audience = str(
        profile.get("target_grade")
        or brief.get("target_audience")
        or request.get("target_audience")
        or ""
    ).strip()
    if audience:
        profile["target_grade"] = audience
        brief["target_audience"] = audience
        request["target_audience"] = audience
    else:
        profile["target_grade"] = "大学生"
        brief["target_audience"] = "大学生"
        request["target_audience"] = "大学生"

    brief["academic_term"] = " ".join(
        item
        for item in (normalized["academic_year"], normalized["term"])
        if item
    )

    goal = _goal(request).strip()
    if goal:
        profile["course_goal"] = goal
        profile["teaching_goals"] = goal

    request["teacher_course_brief"] = brief
    normalized["course_profile"] = profile
    normalized["generation_request"] = request
    return normalized


def course_information_changed_fields(
    before: dict[str, Any],
    after: dict[str, Any],
) -> list[str]:
    changed: list[str] = []
    for field in ("academic_year", "term"):
        if before.get(field) != after.get(field):
            changed.append(field)
    before_profile = before.get("course_profile") or {}
    after_profile = after.get("course_profile") or {}
    for field in COURSE_PROFILE_FIELDS:
        if before_profile.get(field) != after_profile.get(field):
            changed.append(f"course_profile.{field}")
    changed.extend(
        field
        for field in baseline_changed_fields(
            before.get("generation_request") or {},
            after.get("generation_request") or {},
        )
        if field not in changed
    )
    before_request = before.get("generation_request") or {}
    after_request = after.get("generation_request") or {}
    for field in ("secondary_mode", "requirements", "grounding_strategy"):
        if before_request.get(field) != after_request.get(field):
            changed.append(field)
    before_brief = before_request.get("teacher_course_brief") or {}
    after_brief = after_request.get("teacher_course_brief") or {}
    for field in (
        "lesson_duration_minutes",
        "teaching_context",
        "class_size",
        "class_profile",
        "chapter_count",
        "section_count",
        "additional_requirements",
    ):
        if before_brief.get(field) != after_brief.get(field):
            changed.append(f"teacher_course_brief.{field}")
    return changed


def course_information_versions(course: dict[str, Any]) -> list[dict[str, Any]]:
    versions = [{
        "revision": course_information_revision(course),
        "current": True,
        "source": "current",
        "committed_at": str(course.get("updated_at") or ""),
        "changed_fields": [],
        "information": course_information_snapshot(course),
    }]
    history = course.get("course_information_history")
    if not isinstance(history, list):
        return versions
    seen = {versions[0]["revision"]}
    for entry in reversed(history):
        if not isinstance(entry, dict):
            continue
        revision = entry.get("previous_revision")
        information = entry.get("previous_information")
        if not isinstance(revision, int) or revision in seen or not isinstance(information, dict):
            continue
        seen.add(revision)
        versions.append({
            "revision": revision,
            "current": False,
            "source": str(entry.get("source") or "manual"),
            "committed_at": str(entry.get("committed_at") or ""),
            "changed_fields": list(entry.get("changed_fields") or []),
            "information": deepcopy(information),
        })
    return versions


def confirmed_generation_request(value: CourseGenerationRequest) -> dict[str, Any]:
    """Return the persisted baseline without per-run command identity fields."""
    return _canonical_generation_request(value.model_dump(
        mode="json",
        exclude={"request_id", "target_course_id"},
    ))


def baseline_changed_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    before = _canonical_generation_request(before)
    after = _canonical_generation_request(after)
    before_brief = before.get("teacher_course_brief") or {}
    after_brief = after.get("teacher_course_brief") or {}
    fields = {
        "learning_purpose": before.get("learning_purpose") != after.get("learning_purpose"),
        "course_teaching_type": before.get("course_teaching_type") != after.get("course_teaching_type"),
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


def build_course_information_mutation(
    *,
    expected_revision: int,
    information: dict[str, Any],
    source: str,
    restore_revision: int | None,
):
    """Build the aggregate profile + generation-request metadata command."""

    def mutate(raw: dict[str, Any]) -> None:
        current_revision = course_information_revision(raw)
        if current_revision != expected_revision:
            raise ValueError("course_information_revision_changed")
        previous = course_information_snapshot(raw)
        next_revision = current_revision + 1
        changed_fields = course_information_changed_fields(previous, information)
        now = datetime.now(timezone.utc).isoformat()

        history = list(raw.get("course_information_history") or [])
        history.append({
            "schema_version": "course_information_history_v1",
            "revision": next_revision,
            "previous_revision": current_revision,
            "source": source,
            "restore_revision": restore_revision,
            "changed_fields": changed_fields,
            "previous_information": previous,
            "committed_at": now,
        })

        generation_history = list(raw.get("generation_request_history") or [])
        generation_history.append({
            "schema_version": "generation_request_history_v1",
            "revision": next_revision,
            "previous_revision": current_revision,
            "source": source,
            "draft_id": "",
            "changed_fields": baseline_changed_fields(
                previous.get("generation_request") or {},
                information.get("generation_request") or {},
            ),
            "previous": deepcopy(previous.get("generation_request") or {}),
            "committed_at": now,
        })

        raw["academic_year"] = information.get("academic_year") or ""
        raw["term"] = information.get("term") or ""
        raw["course_profile"] = deepcopy(information.get("course_profile") or {})
        raw["generation_request"] = deepcopy(information.get("generation_request") or {})
        raw["course_information_revision"] = next_revision
        raw["generation_request_revision"] = next_revision
        raw["course_information_history"] = history[-20:]
        raw["generation_request_history"] = generation_history[-20:]
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
            "learning_purpose": "systematic | project | exam | null",
            "course_teaching_type": "theory | laboratory | practice | seminar | project | comprehensive | null",
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
        f"当前课程设置：{json.dumps(_canonical_generation_request(course.get('generation_request') or {}), ensure_ascii=False)}\n"
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
    current = _canonical_generation_request(course.get("generation_request") or {})
    candidate = deepcopy(current)
    updates = extracted.get("updates") if isinstance(extracted.get("updates"), dict) else {}

    learning_purpose = _enum(updates.get("learning_purpose"), set(LEARNING_PURPOSES))
    course_teaching_type = _enum(
        updates.get("course_teaching_type"),
        set(COURSE_TEACHING_TYPES),
    )

    # A model response produced by an older prompt may still return course_type.
    # Read it once for compatibility, then keep the draft on the current fields.
    legacy_course_type = _enum(updates.get("course_type"), COURSE_TYPES)
    if not learning_purpose and legacy_course_type:
        learning_purpose = resolve_learning_purpose(
            None,
            legacy_course_type=legacy_course_type,
        )
    if not course_teaching_type and legacy_course_type:
        course_teaching_type, _ = resolve_course_teaching_type(
            None,
            learning_purpose=learning_purpose,
            legacy_course_type=legacy_course_type,
        )
    if learning_purpose:
        candidate["learning_purpose"] = learning_purpose
    else:
        learning_purpose = str(candidate.get("learning_purpose") or "systematic")
    if course_teaching_type:
        candidate["course_teaching_type"] = course_teaching_type

    learning_goal = _text(updates.get("learning_goal"), limit=5000)
    if learning_goal:
        candidate["course_intent"] = _intent_with_goal(
            learning_purpose,
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

    candidate = _canonical_generation_request(candidate)
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
    learning_purpose: str,
    goal: str,
    existing: dict[str, Any],
    subject: str,
) -> dict[str, Any]:
    if learning_purpose == "project":
        return {
            "schema_version": "course_intent_v1",
            "type": "project",
            "project_goal": goal,
            "expected_deliverable": str(existing.get("expected_deliverable") or ""),
            "prior_experience": str(existing.get("prior_experience") or ""),
            "current_uncertainty": str(existing.get("current_uncertainty") or ""),
            "project_constraints": str(existing.get("project_constraints") or ""),
        }
    if learning_purpose == "exam":
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
    "build_course_information_mutation",
    "canonical_generation_request",
    "confirmed_generation_request",
    "course_information_changed_fields",
    "course_information_revision",
    "course_information_snapshot",
    "course_information_versions",
    "merge_ai_baseline_draft",
    "normalize_course_information",
]
