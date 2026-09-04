"""Deterministic read-only projection for teacher course production state.

Tasks own execution, authoring repositories own assets, and this module only
explains those facts for product surfaces.  It must never persist or repair
state while compiling a response.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from copy import deepcopy
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from teacher_asset_readiness import (
    teacher_lesson_plan_readiness,
    teacher_lesson_plan_revision_has_content,
    teacher_lesson_ppt_asset_readiness,
    teacher_lesson_script_readiness,
    teacher_lesson_script_revision_has_content,
)

SCHEMA_VERSION = "course_production_state_v1"
STAGE_KEYS = ("outline", "lesson_plan", "script", "ppt")


class DisplayState(StrEnum):
    NOT_GENERATED = "not_generated"
    GENERATING = "generating"
    AVAILABLE = "available"
    FAILED = "failed"


class ProductionStage(StrEnum):
    OUTLINE = "outline"
    LESSON_PLAN = "lesson_plan"
    SCRIPT = "script"
    PPT = "ppt"


class PreparationState(StrEnum):
    PREPARING = "preparing"
    PREPARED = "prepared"


class TaskState(StrEnum):
    IDLE = "idle"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    FAILED = "failed"
    COMPLETED = "completed"


class Availability(StrEnum):
    MISSING = "missing"
    USABLE = "usable"
    STALE = "stale"


class SourceState(StrEnum):
    MISSING = "missing"
    CURRENT = "current"
    STALE = "stale"
    MIXED = "mixed"


class SourceRequirement(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"


class SourceReviewState(StrEnum):
    VERIFIED = "verified"
    PENDING_REVIEW = "pending_review"
    BLOCKED = "blocked"


class ProductionCounts(BaseModel):
    total: int = Field(ge=0)
    available: int = Field(ge=0)
    generating: int = Field(ge=0)
    failed: int = Field(ge=0)
    stale: int = Field(ge=0)


class RecoveryInfo(BaseModel):
    action: str
    automatic: bool = False
    requires_confirmation: bool = True


class ProductionIssue(BaseModel):
    issue_id: str
    stage: ProductionStage
    lesson_unit_id: str = ""
    block_id: str | None = None
    task_id: str | None = None
    source_id: str | None = None
    code: str
    summary: str
    blocking: bool = False
    category: str = ""
    recovery: RecoveryInfo


class ProductionSource(BaseModel):
    source_id: str
    label: str = ""
    requirement: SourceRequirement
    state: SourceReviewState
    code: str = ""
    summary: str = ""


class SourceReviewSummary(BaseModel):
    pending_review_count: int = Field(ge=0)
    required_blocked_count: int = Field(ge=0)
    sources: list[ProductionSource] = Field(default_factory=list)


class LatestAttempt(BaseModel):
    attempt_id: str
    task_ids: list[str]
    task_state: TaskState
    target_count: int = Field(ge=0)
    completed: int = Field(ge=0)
    failed: int = Field(ge=0)
    progress: int = Field(ge=0, le=100)
    lesson_unit_ids: list[str]
    message: str = ""
    updated_at: str = ""


class AssetProductionState(BaseModel):
    display_state: DisplayState
    task_state: TaskState
    availability: Availability
    source_state: SourceState
    latest_attempt_failed: bool = False
    update_required: bool = False
    issues: list[ProductionIssue] = Field(default_factory=list)


class StageProductionState(AssetProductionState):
    counts: ProductionCounts
    latest_attempt: LatestAttempt | None = None
    blocking_issues: list[ProductionIssue] = Field(default_factory=list)
    review_issues: list[ProductionIssue] = Field(default_factory=list)


class LessonProductionState(BaseModel):
    lesson_unit_id: str
    title: str = ""
    stages: dict[ProductionStage, AssetProductionState]


class CourseProductionState(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: str = SCHEMA_VERSION
    course_id: str
    preparation_state: PreparationState
    stages: dict[ProductionStage, StageProductionState]
    lessons: list[LessonProductionState]
    issues: list[ProductionIssue]
    source_summary: SourceReviewSummary


_TASK_STATE_MAP = {
    "pending": TaskState.QUEUED,
    "queued": TaskState.QUEUED,
    "running": TaskState.RUNNING,
    "paused": TaskState.PAUSED,
    "waiting_for_input": TaskState.PAUSED,
    "waiting_for_review": TaskState.PAUSED,
    "failed": TaskState.FAILED,
    "cancelled": TaskState.FAILED,
    "completed": TaskState.COMPLETED,
    "completed_with_warnings": TaskState.COMPLETED,
}

_TASK_PRIORITY = {
    TaskState.RUNNING: 0,
    TaskState.QUEUED: 1,
    TaskState.PAUSED: 2,
    TaskState.FAILED: 3,
    TaskState.COMPLETED: 4,
    TaskState.IDLE: 5,
}

_TASK_STAGE_MAP = {
    "teacher_outline_generation": "outline",
    "teacher_lesson_plan_generation": "lesson_plan",
    "teacher_lesson_script_generation": "script",
    "teaching_representation_build": "ppt",
    "slide_deck_variant_build": "ppt",
}

_NON_BLOCKING_OUTLINE_CODE_SUFFIXES = {
    ":missing_hour_breakdown",
    ":hour_total_mismatch",
    ":hour_mode_mismatch",
}

_SOURCE_PARSE_FAILED_STATES = {
    "corrupt",
    "damaged",
    "failed",
    "parse_failed",
    "unavailable",
}
_SOURCE_CONFLICT_STATES = {"binding_conflict", "conflict", "source_conflict"}
_SOURCE_STALE_STATES = {"expired", "outdated", "stale"}
_SOURCE_PENDING_STATES = {
    "legacy_unverified",
    "metadata_only",
    "needs_review",
    "pending",
    "pending_review",
    "unverified",
    "unknown",
    "uploaded",
    "parsing",
}


def _task_state(task: dict[str, Any] | None) -> TaskState:
    if not isinstance(task, dict):
        return TaskState.IDLE
    return _TASK_STATE_MAP.get(str(task.get("status") or ""), TaskState.IDLE)


def _latest(items: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    values = [item for item in items if isinstance(item, dict)]
    return max(
        values,
        key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
        default=None,
    )


def _flatten_nodes(nodes: object) -> list[dict[str, Any]]:
    pending = list(nodes or []) if isinstance(nodes, list) else []
    result: list[dict[str, Any]] = []
    while pending:
        item = pending.pop(0)
        if not isinstance(item, dict):
            continue
        result.append(item)
        children = item.get("children")
        if isinstance(children, list):
            pending[0:0] = children
    return result


def _formal_lesson_units(
    course: dict[str, Any],
    authoring_state: dict[str, Any],
) -> tuple[list[dict[str, str]], int]:
    nodes = _flatten_nodes(course.get("nodes"))
    units = [
        node for node in nodes
        if int(node.get("node_level") or 0) == 1
        and str(node.get("parent_node_id") or "root") in {"", "root"}
    ]
    if not units:
        parent_ids = {
            str(node.get("parent_node_id") or "")
            for node in nodes
            if str(node.get("parent_node_id") or "")
        }
        leaves = [
            node for node in nodes
            if str(node.get("node_id") or "") not in parent_ids
            and not node.get("children")
        ]
        units = leaves
    lessons = authoring_state.get("lessons")
    lessons = lessons if isinstance(lessons, dict) else {}
    projected = [
        {
            "lesson_unit_id": str(node.get("node_id") or ""),
            "title": str(node.get("node_name") or node.get("title") or ""),
        }
        for node in units
        if str(node.get("node_id") or "")
    ]
    if not projected:
        projected = [
            {
                "lesson_unit_id": str(lesson_id),
                "title": str((lesson or {}).get("node_name") or (lesson or {}).get("title") or ""),
            }
            for lesson_id, lesson in lessons.items()
            if str(lesson_id)
        ]
    profile = course.get("course_profile")
    profile = profile if isinstance(profile, dict) else {}
    brief = (course.get("generation_request") or {}).get("teacher_course_brief") or {}
    try:
        planned = int(
            profile.get("planned_lecture_count")
            or brief.get("lecture_count")
            or brief.get("section_count")
            or 0
        )
    except (TypeError, ValueError):
        planned = 0
    return projected, max(len(projected), planned)


def _lesson_id(task: dict[str, Any]) -> str:
    request = task.get("request_snapshot")
    request = request if isinstance(request, dict) else {}
    return str(
        task.get("lesson_unit_id")
        or task.get("lesson_id")
        or request.get("lesson_unit_id")
        or request.get("chapter_id")
        or ""
    )


def _attempt_groups(tasks: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        task_id = str(task.get("id") or task.get("task_id") or "")
        group_id = str(task.get("parent_job_id") or task.get("attempt_id") or task_id)
        if group_id:
            groups.setdefault(group_id, []).append(task)
    return list(groups.values())


def _latest_attempt(tasks: list[dict[str, Any]]) -> LatestAttempt | None:
    groups = _attempt_groups(tasks)
    latest_group = max(
        groups,
        key=lambda group: max(
            str(item.get("updated_at") or item.get("created_at") or "")
            for item in group
        ),
        default=None,
    )
    if not latest_group:
        return None
    task_states = [_task_state(item) for item in latest_group]
    aggregate_state = min(task_states, key=lambda item: _TASK_PRIORITY[item])
    completed = sum(state == TaskState.COMPLETED for state in task_states)
    failed = sum(state == TaskState.FAILED for state in task_states)
    target_count = max(
        [int(item.get("batch_size") or 0) for item in latest_group] + [len(latest_group)]
    )
    progress_total = sum(
        100 if state == TaskState.COMPLETED
        else max(0, min(100, int(item.get("progress") or 0)))
        for item, state in zip(latest_group, task_states)
    )
    current = min(
        latest_group,
        key=lambda item: (
            _TASK_PRIORITY[_task_state(item)],
            -int(item.get("batch_position") or 0),
        ),
    )
    task_ids = [
        str(item.get("id") or item.get("task_id") or "")
        for item in latest_group
        if str(item.get("id") or item.get("task_id") or "")
    ]
    return LatestAttempt(
        attempt_id=str(current.get("parent_job_id") or current.get("attempt_id") or task_ids[0]),
        task_ids=task_ids,
        task_state=aggregate_state,
        target_count=target_count,
        completed=completed,
        failed=failed,
        progress=round(progress_total / max(1, target_count)),
        lesson_unit_ids=list(dict.fromkeys(
            lesson_id for lesson_id in (_lesson_id(item) for item in latest_group) if lesson_id
        )),
        message=str(current.get("message") or ""),
        updated_at=max(
            str(item.get("updated_at") or item.get("created_at") or "")
            for item in latest_group
        ),
    )


def _safe_failure(task: dict[str, Any]) -> tuple[str, str]:
    error = task.get("error")
    detail = task.get("error_detail")
    error = error if isinstance(error, dict) else {}
    detail = detail if isinstance(detail, dict) else {}
    code = str(
        error.get("code")
        or detail.get("code")
        or task.get("error_code")
        or ("generation_cancelled" if task.get("status") == "cancelled" else "generation_failed")
    )
    summary = str(
        error.get("message")
        or detail.get("message")
        or task.get("error_user_message")
        or task.get("message")
        or "生成失败，可保留现有内容后重试。"
    )
    return code, summary


def _issue(
    *,
    stage: str,
    code: str,
    summary: str,
    lesson_unit_id: str = "",
    block_id: str = "",
    task_id: str = "",
    source_id: str = "",
    action: str = "retry_generation",
    blocking: bool = False,
    category: str = "",
) -> ProductionIssue:
    identity = json.dumps(
        [stage, lesson_unit_id, block_id, task_id, source_id, code],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    issue_id = "cpi-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return ProductionIssue(
        issue_id=issue_id,
        stage=stage,
        lesson_unit_id=lesson_unit_id,
        block_id=block_id or None,
        task_id=task_id or None,
        source_id=source_id or None,
        code=code,
        summary=summary,
        blocking=blocking,
        category=category,
        recovery=RecoveryInfo(action=action),
    )


def _task_issue(stage: str, task: dict[str, Any]) -> ProductionIssue:
    code, summary = _safe_failure(task)
    checkpoint = task.get("checkpoint")
    checkpoint = checkpoint if isinstance(checkpoint, dict) else {}
    return _issue(
        stage=stage,
        lesson_unit_id=_lesson_id(task),
        block_id=str(task.get("block_id") or checkpoint.get("current_block_id") or ""),
        task_id=str(task.get("id") or task.get("task_id") or ""),
        code=code,
        summary=summary,
        action=("resume_generation" if _task_state(task) == TaskState.PAUSED else "retry_generation"),
    )


def _outline_quality_issues(
    course: dict[str, Any],
    authoring: dict[str, Any],
) -> tuple[list[ProductionIssue], list[ProductionIssue]]:
    report = course.get("course_outline_quality_report")
    if not isinstance(report, dict):
        report = authoring.get("course_outline_quality_report")
    if not isinstance(report, dict):
        return [], []

    classified: dict[tuple[str, str], tuple[bool, ProductionIssue]] = {}
    collections = (
        (report.get("issues"), None),
        (report.get("review_issues"), False),
        (report.get("blocking_issues"), True),
        (report.get("blockers"), True),
    )
    for raw_items, forced_blocking in collections:
        if not isinstance(raw_items, list):
            continue
        for raw in raw_items:
            item = raw if isinstance(raw, dict) else {"code": str(raw or "")}
            code = str(item.get("code") or "outline_review_suggested")
            blocking = (
                bool(item.get("blocking"))
                if forced_blocking is None
                else forced_blocking
            )
            if any(
                code.endswith(suffix)
                for suffix in _NON_BLOCKING_OUTLINE_CODE_SUFFIXES
            ):
                blocking = False
            raw_locations = (
                item.get("node_ids")
                or item.get("lesson_unit_ids")
                or item.get("section_ids")
                or item.get("lesson_unit_id")
                or item.get("section_node_id")
                or []
            )
            if isinstance(raw_locations, (str, int)):
                raw_locations = [raw_locations]
            locations = [str(value) for value in raw_locations if str(value)] or [""]
            summary = str(
                item.get("message")
                or item.get("summary")
                or item.get("repair_instruction")
                or ("大纲结构校验未通过。" if blocking else "大纲有内容待修正。")
            )
            category = str(
                item.get("category")
                or ("outline_structure" if blocking else "outline_review")
            )
            for lesson_unit_id in locations:
                issue = _issue(
                    stage="outline",
                    lesson_unit_id=lesson_unit_id,
                    code=code,
                    summary=summary,
                    action="repair_outline_structure" if blocking else "review_outline",
                    blocking=blocking,
                    category=category,
                )
                key = (code, lesson_unit_id)
                existing = classified.get(key)
                # A hard-gate collection wins duplicate legacy entries, except
                # for codes that are contractually always editorial suggestions.
                if existing is None or (blocking and not existing[0]):
                    classified[key] = (blocking, issue)

    blocking_issues = [issue for blocking, issue in classified.values() if blocking]
    review_issues = [issue for blocking, issue in classified.values() if not blocking]
    return blocking_issues, review_issues


def _course_source_summary(
    course: dict[str, Any],
) -> tuple[SourceReviewSummary, list[ProductionIssue], list[ProductionIssue]]:
    generation_request = course.get("generation_request")
    generation_request = generation_request if isinstance(generation_request, dict) else {}
    bindings = course.get("material_bindings")
    if not isinstance(bindings, list):
        bindings = generation_request.get("material_bindings")
    bindings = bindings if isinstance(bindings, list) else []

    def indexed(items: object, *keys: str) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for raw in items if isinstance(items, list) else []:
            if not isinstance(raw, dict):
                continue
            identity = next((str(raw.get(key) or "") for key in keys if raw.get(key)), "")
            if identity:
                result[identity] = raw
        return result

    assets = indexed(course.get("material_assets"), "asset_id", "material_id")
    cards = indexed(course.get("material_cards"), "asset_id", "material_id")
    documents = indexed(course.get("parsed_documents"), "asset_id", "material_id")
    sources: list[ProductionSource] = []
    blocking_issues: list[ProductionIssue] = []
    review_issues: list[ProductionIssue] = []

    for raw_binding in bindings:
        if not isinstance(raw_binding, dict):
            continue
        source_id = str(raw_binding.get("asset_id") or raw_binding.get("material_id") or "")
        if not source_id:
            continue
        asset = assets.get(source_id, {})
        card = cards.get(source_id, {})
        document = documents.get(source_id, {})
        metadata = raw_binding.get("source_metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        required = (
            str(raw_binding.get("usage_policy") or "") == "must_use"
            or str(raw_binding.get("authority") or "") == "primary"
        )
        state_values = {
            str(value).strip().lower()
            for owner in (raw_binding, metadata, asset, card, document)
            for key in (
                "status",
                "parse_status",
                "evidence_state",
                "review_state",
                "binding_state",
                "source_state",
                "validity_state",
            )
            if (value := owner.get(key)) is not None and str(value).strip()
        }
        if any(bool(owner.get("binding_conflict")) for owner in (raw_binding, metadata)):
            state_values.add("binding_conflict")
        origin = str(
            metadata.get("origin")
            or metadata.get("recommendation_source")
            or raw_binding.get("recommendation_source")
            or ""
        ).lower()
        teacher_confirmed = metadata.get(
            "teacher_confirmed",
            raw_binding.get("teacher_confirmed"),
        )
        ai_pending = (
            origin in {"ai", "ai_recommendation", "model", "model_recommendation"}
            and teacher_confirmed is not True
        )

        blocked_code = ""
        recovery_action = ""
        blocked_summary = ""
        if state_values & _SOURCE_CONFLICT_STATES:
            blocked_code = "required_source_binding_conflict"
            recovery_action = "resolve_source_binding"
            blocked_summary = "必需来源的绑定关系存在冲突，请确认正确来源后继续。"
        elif state_values & _SOURCE_PARSE_FAILED_STATES:
            blocked_code = "required_source_parse_failed"
            recovery_action = "replace_or_reupload_source"
            blocked_summary = "必需来源无法读取，请重新上传或更换可用文件。"
        elif state_values & _SOURCE_STALE_STATES:
            blocked_code = "required_source_stale"
            recovery_action = "refresh_required_source"
            blocked_summary = "必需来源已经过期，请更新来源后继续。"

        label = str(
            raw_binding.get("source_label")
            or asset.get("filename")
            or card.get("filename")
            or source_id
        )
        if required and blocked_code:
            source_state = SourceReviewState.BLOCKED
            code = blocked_code
            summary = blocked_summary
            blocking_issues.append(_issue(
                stage="lesson_plan",
                source_id=source_id,
                code=code,
                summary=summary,
                action=recovery_action,
                blocking=True,
                category="required_source",
            ))
        elif blocked_code or state_values & _SOURCE_PENDING_STATES or ai_pending:
            source_state = SourceReviewState.PENDING_REVIEW
            code = (
                "required_source_pending_review"
                if required
                else "optional_source_pending_review"
            )
            summary = (
                "必需来源仍在处理或等待核对，现有可用内容不会被覆盖。"
                if required
                else "可选来源尚待核对，不影响现有内容使用。"
            )
            review_issues.append(_issue(
                stage="lesson_plan",
                source_id=source_id,
                code=code,
                summary=summary,
                action="review_source",
                category="source_review",
            ))
        else:
            source_state = SourceReviewState.VERIFIED
            code = ""
            summary = ""
        sources.append(ProductionSource(
            source_id=source_id,
            label=label,
            requirement=(
                SourceRequirement.REQUIRED if required else SourceRequirement.OPTIONAL
            ),
            state=source_state,
            code=code,
            summary=summary,
        ))

    return SourceReviewSummary(
        pending_review_count=sum(
            item.state == SourceReviewState.PENDING_REVIEW for item in sources
        ),
        required_blocked_count=sum(
            item.requirement == SourceRequirement.REQUIRED
            and item.state == SourceReviewState.BLOCKED
            for item in sources
        ),
        sources=sources,
    ), blocking_issues, review_issues


def _attach_stage_issues(
    stage: StageProductionState,
    *,
    blocking_issues: list[ProductionIssue],
    review_issues: list[ProductionIssue],
) -> None:
    stage.blocking_issues = list({
        issue.issue_id: issue
        for issue in [*stage.blocking_issues, *blocking_issues]
    }.values())
    stage.review_issues = list({
        issue.issue_id: issue
        for issue in [*stage.review_issues, *review_issues]
    }.values())
    stage.issues = list({
        issue.issue_id: issue
        for issue in [*stage.issues, *blocking_issues, *review_issues]
    }.values())
    if blocking_issues or review_issues:
        stage.update_required = True
    if blocking_issues:
        if stage.source_state == SourceState.CURRENT:
            stage.source_state = SourceState.MIXED
        elif stage.source_state == SourceState.MISSING:
            stage.source_state = SourceState.STALE
        if (
            stage.availability == Availability.MISSING
            and stage.task_state not in {TaskState.QUEUED, TaskState.RUNNING, TaskState.PAUSED}
        ):
            stage.display_state = DisplayState.FAILED


def _working_revision(items: object, revision_id: str) -> dict[str, Any] | None:
    return next(
        (
            item for item in items or []
            if isinstance(item, dict) and str(item.get("revision_id") or "") == revision_id
        ),
        None,
    )


def _plan_facts(lesson: dict[str, Any]) -> tuple[bool, Availability, SourceState, bool]:
    revision_id = str(lesson.get("working_revision_id") or "")
    revision = _working_revision(lesson.get("revisions"), revision_id)
    last_good = teacher_lesson_plan_revision_has_content(revision)
    readiness = teacher_lesson_plan_readiness(lesson)
    stale = last_good and str(lesson.get("source_state") or "current") != "current"
    availability = Availability.USABLE if readiness["ready"] else Availability.STALE if stale else Availability.MISSING
    source = SourceState.STALE if stale else SourceState.CURRENT if last_good else SourceState.MISSING
    return last_good, availability, source, stale


def _script_facts(lesson: dict[str, Any]) -> tuple[bool, Availability, SourceState, bool]:
    revision_id = str(lesson.get("working_script_revision_id") or "")
    revision = _working_revision(lesson.get("script_revisions"), revision_id)
    last_good = teacher_lesson_script_revision_has_content(revision)
    plan_readiness = teacher_lesson_plan_readiness(lesson)
    readiness = teacher_lesson_script_readiness(lesson, plan_readiness=plan_readiness)
    stale = last_good and not readiness["ready"]
    availability = Availability.USABLE if readiness["ready"] else Availability.STALE if stale else Availability.MISSING
    source = SourceState.STALE if stale else SourceState.CURRENT if last_good else SourceState.MISSING
    return last_good, availability, source, stale


def _ppt_facts(lesson: dict[str, Any]) -> tuple[bool, Availability, SourceState, bool]:
    plan_readiness = teacher_lesson_plan_readiness(lesson)
    script_readiness = teacher_lesson_script_readiness(lesson, plan_readiness=plan_readiness)
    assets = [item for item in lesson.get("ppt_assets") or [] if isinstance(item, dict)]
    last_good_assets = [
        asset for asset in assets
        if any(str(asset.get(field) or "") for field in (
            "working_representation_id", "working_v6_revision_id", "working_revision_id"
        ))
    ]
    usable = any(
        teacher_lesson_ppt_asset_readiness(
            lesson,
            asset,
            plan_readiness=plan_readiness,
            script_readiness=script_readiness,
        )["ready"]
        for asset in last_good_assets
    )
    last_good = bool(last_good_assets)
    stale = last_good and not usable
    availability = Availability.USABLE if usable else Availability.STALE if stale else Availability.MISSING
    source = SourceState.STALE if stale else SourceState.CURRENT if last_good else SourceState.MISSING
    return last_good, availability, source, stale


def _asset_state(
    *,
    stage: str,
    last_good: bool,
    availability: Availability,
    source_state: SourceState,
    stale: bool,
    task: dict[str, Any] | None,
) -> AssetProductionState:
    task_state = _task_state(task)
    latest_failed = task_state == TaskState.FAILED
    issues: list[ProductionIssue] = []
    if latest_failed and isinstance(task, dict):
        issues.append(_task_issue(stage, task))
    if stale:
        issues.append(_issue(
            stage=stage,
            lesson_unit_id=_lesson_id(task or {}),
            code=f"{stage}_source_stale",
            summary="上游内容已经变化，当前版本仍保留，可按最新来源重新生成。",
            action="regenerate_from_latest_source",
        ))
    if last_good:
        display = DisplayState.AVAILABLE
    elif task_state in {TaskState.QUEUED, TaskState.RUNNING, TaskState.PAUSED}:
        display = DisplayState.GENERATING
    elif latest_failed:
        display = DisplayState.FAILED
    else:
        display = DisplayState.NOT_GENERATED
    return AssetProductionState(
        display_state=display,
        task_state=task_state,
        availability=availability,
        source_state=source_state,
        latest_attempt_failed=latest_failed,
        update_required=stale,
        issues=issues,
    )


def _aggregate_stage(
    stage: str,
    states: list[AssetProductionState],
    tasks: list[dict[str, Any]],
    *,
    total: int,
) -> StageProductionState:
    latest_attempt = _latest_attempt(tasks)
    task_state = latest_attempt.task_state if latest_attempt else TaskState.IDLE
    usable = sum(item.availability == Availability.USABLE for item in states)
    stale = sum(item.availability == Availability.STALE for item in states)
    generating = sum(
        item.display_state == DisplayState.GENERATING for item in states
    )
    failed = sum(
        item.display_state == DisplayState.FAILED for item in states
    )
    last_good_count = usable + stale
    if total > 0 and last_good_count >= total:
        display = DisplayState.AVAILABLE
    elif task_state in {TaskState.QUEUED, TaskState.RUNNING, TaskState.PAUSED}:
        display = DisplayState.GENERATING
    elif failed:
        display = DisplayState.FAILED
    elif last_good_count:
        display = DisplayState.AVAILABLE
    else:
        display = DisplayState.NOT_GENERATED
    availability = (
        Availability.USABLE if total > 0 and usable >= total
        else Availability.STALE if last_good_count else Availability.MISSING
    )
    if stale and usable:
        source_state = SourceState.MIXED
    elif stale:
        source_state = SourceState.STALE
    elif last_good_count:
        source_state = SourceState.CURRENT
    else:
        source_state = SourceState.MISSING
    issues = [issue for item in states for issue in item.issues]
    if stage == "outline" and latest_attempt and latest_attempt.task_state == TaskState.FAILED:
        latest_group = next(
            (group for group in _attempt_groups(tasks) if latest_attempt.attempt_id in {
                str(item.get("parent_job_id") or item.get("attempt_id") or item.get("id") or item.get("task_id") or "")
                for item in group
            }),
            [],
        )
        issues.extend(_task_issue(stage, item) for item in latest_group if _task_state(item) == TaskState.FAILED)
    unique_issues = {item.issue_id: item for item in issues}
    return StageProductionState(
        display_state=display,
        task_state=task_state,
        availability=availability,
        source_state=source_state,
        latest_attempt_failed=bool(latest_attempt and latest_attempt.failed > 0),
        update_required=stale > 0,
        counts=ProductionCounts(
            total=total,
            available=usable,
            generating=generating,
            failed=failed,
            stale=stale,
        ),
        latest_attempt=latest_attempt,
        issues=list(unique_issues.values()),
        blocking_issues=[],
        review_issues=[],
    )


def compile_course_production_state(
    course: dict[str, Any],
    *,
    authoring_state: dict[str, Any] | None = None,
    tasks: Iterable[dict[str, Any]] | None = None,
    ppt_checkpoints: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compile the versioned state without mutating any supplied snapshot."""

    authoring = deepcopy(authoring_state or {})
    task_values = [deepcopy(item) for item in tasks or [] if isinstance(item, dict)]
    for checkpoint in ppt_checkpoints or []:
        if not isinstance(checkpoint, dict):
            continue
        task_values.append({
            **deepcopy(checkpoint),
            "type": str(checkpoint.get("type") or "slide_deck_variant_build"),
        })
    tasks_by_stage: dict[str, list[dict[str, Any]]] = {key: [] for key in STAGE_KEYS}
    for task in task_values:
        stage = _TASK_STAGE_MAP.get(str(task.get("type") or task.get("asset_type") or ""))
        if not stage and str(task.get("asset_type") or "") in {"lesson_plan", "script", "ppt"}:
            stage = str(task.get("asset_type"))
        if stage:
            tasks_by_stage[stage].append(task)

    units, formal_total = _formal_lesson_units(course, authoring)
    lessons = authoring.get("lessons")
    lessons = lessons if isinstance(lessons, dict) else {}
    unit_states: list[LessonProductionState] = []
    stage_items: dict[str, list[AssetProductionState]] = {
        "lesson_plan": [], "script": [], "ppt": []
    }
    for unit in units:
        lesson_id = unit["lesson_unit_id"]
        lesson = lessons.get(lesson_id)
        lesson = lesson if isinstance(lesson, dict) else {}
        stages: dict[str, AssetProductionState] = {}
        for stage, facts in (
            ("lesson_plan", _plan_facts(lesson)),
            ("script", _script_facts(lesson)),
            ("ppt", _ppt_facts(lesson)),
        ):
            lesson_task = _latest(
                item for item in tasks_by_stage[stage]
                if _lesson_id(item) == lesson_id
            )
            state = _asset_state(
                stage=stage,
                last_good=facts[0],
                availability=facts[1],
                source_state=facts[2],
                stale=facts[3],
                task=lesson_task,
            )
            # Stale issues need the formal lesson identity even without a task.
            for issue in state.issues:
                if not issue.lesson_unit_id:
                    issue.lesson_unit_id = lesson_id
                    issue.issue_id = _issue(
                        stage=issue.stage,
                        lesson_unit_id=lesson_id,
                        block_id=issue.block_id or "",
                        task_id=issue.task_id or "",
                        code=issue.code,
                        summary=issue.summary,
                        action=issue.recovery.action,
                    ).issue_id
            stages[stage] = state
            stage_items[stage].append(state)
        unit_states.append(LessonProductionState(
            lesson_unit_id=lesson_id,
            title=unit["title"],
            stages=stages,
        ))

    # A revision identity alone does not prove that a readable outline exists.
    outline_last_good = bool(units)
    outline_task = _latest(tasks_by_stage["outline"])
    outline_state = _asset_state(
        stage="outline",
        last_good=outline_last_good,
        availability=Availability.USABLE if outline_last_good else Availability.MISSING,
        source_state=SourceState.CURRENT if outline_last_good else SourceState.MISSING,
        stale=False,
        task=outline_task,
    )
    stages: dict[str, StageProductionState] = {
        "outline": _aggregate_stage("outline", [outline_state], tasks_by_stage["outline"], total=1),
    }
    for stage in ("lesson_plan", "script", "ppt"):
        stages[stage] = _aggregate_stage(
            stage,
            stage_items[stage],
            tasks_by_stage[stage],
            total=formal_total,
        )

    outline_blocking, outline_review = _outline_quality_issues(course, authoring)
    _attach_stage_issues(
        stages["outline"],
        blocking_issues=outline_blocking,
        review_issues=outline_review,
    )
    source_summary, source_blocking, source_review = _course_source_summary(course)
    _attach_stage_issues(
        stages["lesson_plan"],
        blocking_issues=source_blocking,
        review_issues=source_review,
    )

    prepared = bool(
        stages["outline"].availability == Availability.USABLE
        and formal_total > 0
        and all(
            stages[stage].counts.available >= formal_total
            for stage in ("lesson_plan", "script", "ppt")
        )
        and all(not stage.blocking_issues for stage in stages.values())
    )
    all_issues = {issue.issue_id: issue for stage in stages.values() for issue in stage.issues}
    result = CourseProductionState(
        course_id=str(course.get("course_id") or authoring.get("course_id") or ""),
        preparation_state="prepared" if prepared else "preparing",
        stages=stages,
        lessons=unit_states,
        issues=list(all_issues.values()),
        source_summary=source_summary,
    )
    return result.model_dump(mode="json", exclude_none=True)


def read_course_production_state(
    course: dict[str, Any],
    authoring_repository: Any,
    task_manager: Any | None = None,
) -> dict[str, Any]:
    """Read current owners once and delegate all interpretation to the compiler."""

    course_id = str(course.get("course_id") or "")
    try:
        authoring = authoring_repository.view(course_id)
    except Exception:
        authoring = {}
    tasks: list[dict[str, Any]] = []
    if task_manager is not None:
        try:
            tasks = list(task_manager.get_tasks_by_course(course_id))
        except Exception:
            tasks = []
    return compile_course_production_state(
        course,
        authoring_state=authoring,
        tasks=tasks,
    )
