#!/usr/bin/env python3
"""Run and audit one real, multi-section course-generation production chain.

The audit uses the same CourseService and TaskManager as the product path, but
stores the generated course in an isolated directory.  It records operational
metadata only: prompt sizes, timings, retries, fallbacks, stage transitions and
artifact counts.  Prompt text and full generated course content are excluded
from the report.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
import tempfile
import time
from collections import Counter, defaultdict
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for module_root in (ROOT, BACKEND):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

import task_manager as task_manager_module  # noqa: E402
from course_repository import CourseDocumentRepository  # noqa: E402
from course_service import CourseService  # noqa: E402
from course_versions import CourseVersionRepository  # noqa: E402
from generation_workspace import GenerationWorkspaceRepository  # noqa: E402
from learning_asset_storage import LearningAssetRepository  # noqa: E402
from material_storage import MaterialRepository  # noqa: E402
from question_bank import QuestionBankRepository  # noqa: E402
from storage import Storage  # noqa: E402
from task_manager import TaskManager  # noqa: E402

TERMINAL_STATUSES = {"completed", "completed_with_warnings", "failed", "conflict"}
STAGE_METRIC_KEYS = {
    "status",
    "schema_version",
    "strategy",
    "planning_mode",
    "initial_planning_mode",
    "model_call_count",
    "prompt_chars",
    "prompt_tokens",
    "max_prompt_tokens",
    "prompt_detail_levels",
    "adaptive_compaction_count",
    "duration_ms",
    "section_count",
    "chapter_count",
    "batch_count",
    "completed_batch_count",
    "completed_section_count",
    "failed_section_count",
    "completed_skeleton_chunk_count",
    "skeleton_chunk_count",
    "resumed_skeleton_chunk_count",
    "final_payload_split_count",
    "max_concurrency",
    "resume_available",
    "completion_policy",
    "generation_dependency",
    "degraded",
    "semantic_status",
    "semantic_retry_count",
    "ai_section_count",
    "needs_manual_review",
    "runtime_budget",
    "actual",
    "fallback_reason",
    "generation_source",
    "attempt_count",
    "section_ids",
    "batch_id",
    "chunk_id",
    "reason",
    "source_outline_revision_id",
    "knowledge_compilation_model_call_count",
    "graph_compilation_model_call_count",
    "total_prompt_tokens",
    "provider_capacity",
    "provider",
    "start_interval_seconds",
    "models",
    "limit",
    "in_flight",
    "started",
    "succeeded",
    "rate_limited",
    "quota_exhausted",
    "transient_failures",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_issue(issue: Any) -> dict[str, Any]:
    if not isinstance(issue, dict):
        return {"message": str(issue)[:240]}
    return {
        key: issue.get(key)
        for key in (
            "code",
            "severity",
            "issue_type",
            "node_id",
            "section_id",
            "message",
            "description",
        )
        if issue.get(key) not in (None, "", [], {})
    }


def _safe_stage_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 3:
        return None
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:240]
    if isinstance(value, list):
        if all(item is None or isinstance(item, (bool, int, float, str)) for item in value):
            return [item[:160] if isinstance(item, str) else item for item in value[:40]]
        summarized = []
        for item in value[:40]:
            if isinstance(item, dict):
                compact = {
                    key: _safe_stage_value(item.get(key), depth=depth + 1)
                    for key in STAGE_METRIC_KEYS
                    if key in item
                }
                summarized.append({key: value for key, value in compact.items() if value is not None})
        return summarized
    if isinstance(value, dict):
        compact = {
            key: _safe_stage_value(item, depth=depth + 1)
            for key, item in value.items()
            if key in STAGE_METRIC_KEYS
        }
        return {key: item for key, item in compact.items() if item is not None}
    return str(value)[:160]


def _summarize_stage(stage: Any) -> dict[str, Any]:
    if not isinstance(stage, dict):
        return {}
    result = {
        key: _safe_stage_value(stage.get(key))
        for key in STAGE_METRIC_KEYS
        if key in stage
    }
    batches = stage.get("batches")
    if isinstance(batches, dict):
        result["batches"] = {
            str(batch_id): _safe_stage_value(batch)
            for batch_id, batch in list(batches.items())[:80]
            if isinstance(batch, dict)
        }
    fallback_units = stage.get("fallback_units")
    if isinstance(fallback_units, list):
        result["fallback_units"] = _safe_stage_value(fallback_units)
    return {key: value for key, value in result.items() if value is not None}


def _error_category(message: str) -> str:
    lowered = message.lower()
    if "insufficient_quota" in lowered or "insufficient balance" in lowered or "额度" in lowered:
        return "quota_exhausted"
    if "429" in lowered or "rate limit" in lowered or "limit_burst_rate" in lowered:
        return "rate_limited"
    if "timeout" in lowered or "timed out" in lowered or "超时" in lowered:
        return "timeout"
    if "401" in lowered or "403" in lowered or "authentication" in lowered:
        return "authentication"
    if "truncated" in lowered or "max_tokens" in lowered:
        return "output_truncated"
    if "empty" in lowered:
        return "empty_response"
    if "connection" in lowered or "network" in lowered:
        return "connection"
    return "provider_error"


class ProviderAuditHandler(logging.Handler):
    """Capture sanitized provider outcomes from the real AIBase execution."""

    def __init__(self, started_at: float) -> None:
        super().__init__()
        self.started_at = started_at
        self.events: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        event = ""
        if "AI Response Complete" in message:
            event = "request_succeeded"
        elif "AI API Call Error" in message:
            event = "request_failed"
        elif "Stream Error" in message:
            event = "stream_attempt_failed"
        elif "AI response truncated" in message:
            event = "response_truncated"
        elif "Empty response from AI" in message:
            event = "empty_response"
        elif "AI model circuit opened" in message:
            event = "model_circuit_opened"
        elif "AI provider disabled" in message:
            event = "provider_disabled"
        if not event:
            return
        model_match = re.search(r"Model:\s*([^,)]+)", message)
        attempt_match = re.search(r"Attempt\s+(\d+)/(\d+)", message)
        status_match = re.search(r"(?<!\d)([45]\d\d)(?!\d)", message)
        item: dict[str, Any] = {
            "elapsed_seconds": round(time.monotonic() - self.started_at, 2),
            "event": event,
        }
        if model_match:
            item["model"] = model_match.group(1).strip()
        if attempt_match:
            item["attempt"] = int(attempt_match.group(1))
            item["attempt_limit"] = int(attempt_match.group(2))
        if status_match:
            item["http_status"] = int(status_match.group(1))
        if event not in {"request_succeeded", "model_circuit_opened"}:
            item["category"] = _error_category(message)
        self.events.append(item)


class AuditedCourseService(CourseService):
    """CourseService with non-content operational tracing around model units."""

    def __init__(self, *args: Any, audit_started_at: float, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._audit_started_at = audit_started_at
        self.model_units: list[dict[str, Any]] = []

    async def _call_llm_with_heartbeat(self, *args: Any, **kwargs: Any) -> str:
        user_prompt = str(args[0] if args else kwargs.get("user_prompt") or "")
        system_prompt = str(args[1] if len(args) > 1 else kwargs.get("system_prompt") or "")
        started = time.monotonic()
        item: dict[str, Any] = {
            "kind": "structured_generation",
            "phase": str(kwargs.get("phase") or "unknown"),
            "started_at_seconds": round(started - self._audit_started_at, 2),
            "prompt_chars": len(user_prompt) + len(system_prompt),
            "estimated_input_tokens": self.estimate_request_tokens(user_prompt, system_prompt),
            "max_output_tokens": kwargs.get("max_output_tokens"),
            "max_provider_attempts": kwargs.get("max_attempts"),
            "thinking_enabled": bool(kwargs.get("enable_thinking")),
        }
        try:
            result = await super()._call_llm_with_heartbeat(*args, **kwargs)
            item.update({
                "status": "succeeded",
                "output_chars": len(result or ""),
            })
            models = self._models_for(False)
            if models:
                item["selected_model"] = models[0]
            return result
        except BaseException as exc:
            item.update({
                "status": "cancelled" if isinstance(exc, asyncio.CancelledError) else "failed",
                "error_type": type(exc).__name__,
                "error_category": _error_category(str(exc)),
            })
            raise
        finally:
            item["duration_seconds"] = round(time.monotonic() - started, 2)
            self.model_units.append(item)

    async def _stream_llm(self, *args: Any, **kwargs: Any) -> AsyncIterator[str]:
        prompt = str(args[0] if args else kwargs.get("prompt") or "")
        system_prompt = str(args[1] if len(args) > 1 else kwargs.get("system_prompt") or "")
        started = time.monotonic()
        output_chars = 0
        item: dict[str, Any] = {
            "kind": "content_stream",
            "phase": "content_generation",
            "started_at_seconds": round(started - self._audit_started_at, 2),
            "prompt_chars": len(prompt) + len(system_prompt),
            "estimated_input_tokens": self.estimate_request_tokens(prompt, system_prompt),
            "max_output_tokens": kwargs.get("max_tokens"),
            "max_provider_attempts": kwargs.get("max_attempts"),
        }
        try:
            async for chunk in super()._stream_llm(*args, **kwargs):
                output_chars += len(chunk)
                yield chunk
            item.update({"status": "succeeded", "output_chars": output_chars})
            models = self._models_for(False)
            if models:
                item["selected_model"] = models[0]
        except BaseException as exc:
            item.update({
                "status": "cancelled" if isinstance(exc, asyncio.CancelledError) else "failed",
                "output_chars": output_chars,
                "error_type": type(exc).__name__,
                "error_category": _error_category(str(exc)),
            })
            raise
        finally:
            item["duration_seconds"] = round(time.monotonic() - started, 2)
            self.model_units.append(item)


def _phase_durations(timeline: list[dict[str, Any]], elapsed_seconds: float) -> dict[str, float]:
    totals: defaultdict[str, float] = defaultdict(float)
    for index, item in enumerate(timeline):
        start = float(item.get("elapsed_seconds") or 0)
        end = (
            float(timeline[index + 1].get("elapsed_seconds") or elapsed_seconds)
            if index + 1 < len(timeline)
            else elapsed_seconds
        )
        totals[str(item.get("phase") or "unknown")] += max(0.0, end - start)
    return {
        phase: round(duration, 2)
        for phase, duration in sorted(totals.items(), key=lambda pair: pair[1], reverse=True)
    }


def _course_shape(course_data: dict[str, Any]) -> dict[str, Any]:
    plan = course_data.get("course_outline") or course_data.get("course_plan") or {}
    chapters = []
    section_total = 0
    for chapter in plan.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        sections = [
            {
                "node_id": str(section.get("node_id") or ""),
                "title": str(section.get("title") or section.get("node_name") or ""),
            }
            for section in chapter.get("sections") or []
            if isinstance(section, dict)
        ]
        section_total += len(sections)
        chapters.append({
            "chapter_id": str(chapter.get("chapter_id") or ""),
            "title": str(chapter.get("title") or chapter.get("chapter_title") or ""),
            "section_count": len(sections),
            "sections": sections,
        })
    return {
        "course_title": str(plan.get("course_title") or course_data.get("course_name") or ""),
        "chapter_count": len(chapters),
        "section_count": section_total,
        "chapters": chapters,
    }


def _node_summaries(course_data: dict[str, Any]) -> list[dict[str, Any]]:
    summaries = []
    for node in course_data.get("nodes") or []:
        if not isinstance(node, dict) or int(node.get("node_level") or 1) != 2:
            continue
        runtime = node.get("generation_runtime") or {}
        quality = node.get("generation_quality") or {}
        summaries.append({
            "node_id": str(node.get("node_id") or ""),
            "name": str(node.get("node_name") or ""),
            "status": str(node.get("generation_status") or ""),
            "generated_chars": int(node.get("generated_chars") or len(str(node.get("node_content") or ""))),
            "block_count": len(node.get("content_blocks") or []),
            "needs_manual_review": bool(node.get("needs_manual_review")),
            "error_summary": str(node.get("error_summary") or "")[:240] or None,
            "quality_passed": quality.get("passed"),
            "quality_issue_count": len(quality.get("issues") or []),
            "generation_runtime": {
                key: runtime.get(key)
                for key in (
                    "prompt_chars",
                    "estimated_input_tokens",
                    "prompt_detail_level",
                    "adaptive_compaction",
                    "generation_source",
                    "fallback_reason",
                    "duration_ms",
                    "output_chars",
                    "continued_from_chars",
                    "timeout_policy",
                    "inactivity_timeout_seconds",
                )
                if runtime.get(key) is not None
            },
        })
    return summaries


def _collect_report(
    *,
    started_at: float,
    audit_root: Path,
    report_path: Path,
    request: dict[str, Any],
    manager: TaskManager | None,
    service: AuditedCourseService | None,
    provider_handler: ProviderAuditHandler,
    storage: Storage | None,
    workspaces: GenerationWorkspaceRepository | None,
    documents: CourseDocumentRepository | None,
    task_id: str,
    course_id: str,
    timeline: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    confirmed_steps: list[str],
    stop_reason: str | None,
    runtime_error: dict[str, str] | None,
) -> dict[str, Any]:
    elapsed_seconds = round(time.monotonic() - started_at, 2)
    task = dict((manager.tasks.get(task_id) or {}) if manager and task_id else {})
    workspace: dict[str, Any] = {}
    if workspaces and task_id:
        try:
            workspace = workspaces.load(task_id) or {}
        except Exception:
            workspace = {}
    course_data = workspace.get("course_data") or {}
    if not isinstance(course_data, dict):
        course_data = {}
    raw_course: dict[str, Any] = {}
    if storage and course_id:
        try:
            raw_course = storage.load_course(course_id) or {}
        except Exception:
            raw_course = {}
    document: dict[str, Any] = {}
    if documents and course_id:
        try:
            document = (documents.document_envelope(course_id) or {}).get("document") or {}
        except Exception:
            document = {}

    stage_artifacts = course_data.get("generation_stage_artifacts") or {}
    node_summaries = _node_summaries(course_data)
    model_units = list(service.model_units if service else [])
    unit_counts = Counter(
        f"{item.get('kind')}:{item.get('status')}" for item in model_units
    )
    model_counts = Counter(
        str(item.get("selected_model"))
        for item in model_units
        if item.get("selected_model")
    )
    provider_event_counts = Counter(
        str(item.get("event")) for item in provider_handler.events
    )
    knowledge_base = course_data.get("course_knowledge_base") or {}
    learning_assets = course_data.get("learning_assets") or {}
    quality_report = course_data.get("generation_quality_report") or {}
    asset_quality = course_data.get("asset_quality_report") or {}
    source_chain = course_data.get("generation_source_chain_report") or {}
    teaching_plan = course_data.get("course_teaching_plan") or {}
    question_review_queue = course_data.get("question_bank_review_queue") or {}
    question_review_items = (
        question_review_queue.get("items") or []
        if isinstance(question_review_queue, dict)
        else question_review_queue
    )
    task_logs = []
    if manager and task_id:
        for entry in manager._get_task_log(task_id):
            task_logs.append({
                "timestamp": entry.timestamp.isoformat(),
                "node_id": entry.node_id,
                "node_name": entry.node_name,
                "event": entry.event,
                "retry_count": entry.retry_count,
                "generated_chars": entry.generated_chars,
                "duration_ms": entry.duration_ms,
                "message": entry.message[:240],
            })

    return {
        "schema_version": "course_generation_chain_audit_v2",
        "started_at": datetime.fromtimestamp(
            time.time() - elapsed_seconds, tz=timezone.utc
        ).isoformat(),
        "completed_at": _utc_now(),
        "elapsed_seconds": elapsed_seconds,
        "audit_workspace": str(audit_root),
        "report_path": str(report_path),
        "request": {
            "subject": request.get("subject"),
            "target_audience": request.get("target_audience"),
            "difficulty": request.get("difficulty"),
            "pedagogy_mode": request.get("pedagogy_mode"),
            "course_purpose": request.get("course_purpose"),
            "requirements_chars": len(str(request.get("requirements") or "")),
            "requested_chapters": 6,
            "requested_sections": 12,
            "material_count": len(request.get("material_bindings") or []),
        },
        "identity": {"task_id": task_id, "course_id": course_id},
        "outcome": {
            "task_status": task.get("status"),
            "task_phase": task.get("phase"),
            "task_progress": task.get("progress"),
            "publication_allowed": quality_report.get(
                "publication_allowed",
                task.get("publication_allowed"),
            ),
            "workspace_status": workspace.get("status"),
            "generation_status": course_data.get("generation_status") or raw_course.get("generation_status"),
            "confirmed_steps": confirmed_steps,
            "stop_reason": stop_reason,
            "runtime_error": runtime_error,
        },
        "course_shape": _course_shape(course_data),
        "timeline": timeline,
        "phase_durations_seconds": _phase_durations(timeline, elapsed_seconds),
        "reviews": reviews,
        "runtime_budget": course_data.get("generation_runtime_budget") or {},
        "stage_artifacts": {
            str(name): _summarize_stage(stage)
            for name, stage in stage_artifacts.items()
            if isinstance(stage, dict)
        },
        "model_execution": {
            "business_unit_count": len(model_units),
            "business_unit_counts": dict(unit_counts),
            "selected_model_counts": dict(model_counts),
            "units": model_units,
            "provider_event_counts": dict(provider_event_counts),
            "provider_events": provider_handler.events,
            "provider_capacity": (
                service.provider_capacity_snapshot()
                if service
                else {}
            ),
            "provider_attempt_observability_note": (
                "非流式请求可从日志识别成功与失败尝试；流式成功只在业务单元层可见，"
                "若先失败后切换模型，则失败尝试另见 provider_events。"
            ),
        },
        "content_nodes": node_summaries,
        "content_summary": {
            "section_count": len(node_summaries),
            "completed_count": sum(item["status"] == "completed" for item in node_summaries),
            "manual_review_count": sum(item["needs_manual_review"] for item in node_summaries),
            "fallback_count": sum(
                (item.get("generation_runtime") or {}).get("generation_source") != "model"
                for item in node_summaries
            ),
            "total_generated_chars": sum(item["generated_chars"] for item in node_summaries),
            "max_prompt_chars": max(
                ((item.get("generation_runtime") or {}).get("prompt_chars") or 0 for item in node_summaries),
                default=0,
            ),
            "max_estimated_input_tokens": max(
                ((item.get("generation_runtime") or {}).get("estimated_input_tokens") or 0 for item in node_summaries),
                default=0,
            ),
        },
        "task_log": task_logs,
        "final_artifacts": {
            "teaching_plan_schema": teaching_plan.get("schema_version"),
            "teaching_plan_section_count": len(teaching_plan.get("sections") or []),
            "knowledge_point_count": len(knowledge_base.get("knowledge_points") or []),
            "knowledge_relation_count": len(knowledge_base.get("relations") or []),
            "learning_asset_counts": {
                str(name): len(values)
                for name, values in learning_assets.items()
                if isinstance(values, list)
            },
            "question_analysis_summary": course_data.get("question_analysis_summary") or {},
            "question_bank_coverage": course_data.get("question_bank_coverage") or {},
            "question_bank_review": {
                "blocking_count": (
                    question_review_queue.get("blocking_count")
                    if isinstance(question_review_queue, dict)
                    else len(question_review_items)
                ),
                "item_count": len(question_review_items),
                "tier_counts": (
                    question_review_queue.get("tier_counts") or {}
                    if isinstance(question_review_queue, dict)
                    else {}
                ),
            },
            "document_section_count": len(document.get("sections") or []),
            "document_block_count": len(document.get("blocks") or []),
        },
        "quality": {
            "final_status": quality_report.get("final_status"),
            "publication_allowed": quality_report.get("publication_allowed"),
            "blocking_issues": [_safe_issue(item) for item in (quality_report.get("blocking_issues") or [])[:40]],
            "warning_count": len(quality_report.get("warnings") or quality_report.get("quality_warnings") or []),
            "asset_quality_passed": asset_quality.get("passed"),
            "asset_blocking_issue_count": len(asset_quality.get("blocking_issues") or []),
            "asset_warning_count": len(asset_quality.get("warnings") or []),
            "asset_blocking_issues": [_safe_issue(item) for item in (asset_quality.get("blocking_issues") or [])[:40]],
            "source_chain_can_publish": source_chain.get("can_publish"),
            "source_chain_issues": [_safe_issue(item) for item in (source_chain.get("issues") or [])[:40]],
        },
    }


async def run_audit(
    *,
    subject: str,
    timeout_seconds: int,
    report_path: Path,
) -> dict[str, Any]:
    started_at = time.monotonic()
    audit_root = Path(tempfile.mkdtemp(prefix="lingzhi-generation-audit-"))
    data_root = audit_root / "data"
    timeline: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    confirmed_steps: list[str] = []
    stop_reason: str | None = None
    runtime_error: dict[str, str] | None = None
    task_id = ""
    course_id = ""
    manager: TaskManager | None = None
    service: AuditedCourseService | None = None
    storage: Storage | None = None
    workspaces: GenerationWorkspaceRepository | None = None
    documents: CourseDocumentRepository | None = None
    provider_handler = ProviderAuditHandler(started_at)
    ai_logger = logging.getLogger("ai_base")
    ai_logger.addHandler(provider_handler)

    request = {
        "subject": subject,
        "target_audience": "大学一年级学生",
        "difficulty": "intermediate",
        "style": "academic",
        "composition_style": "theory_driven",
        "requirements": (
            "请生成一门正式、完整、可发布的6章12节课程，每章严格2节。"
            "内容从随机事件与概率公理开始，依次覆盖条件概率与独立性、随机变量与分布、"
            "数字特征、常用极限定理，最后完成中心极限定理及一个综合建模应用。"
            "章节之间必须递进且不能重复；每节都要有明确学习目标、适用边界、关键定义或定理、"
            "至少一个推导或例题、一个常见误区、一个可验收任务，并为后续练习和知识关系提供稳定依据。"
            "数学符号使用LaTeX，不能为了凑字数重复目录或泛泛总结。"
        ),
        "materials": [],
        "material_bindings": [],
        "grounding_strategy": "general_assisted",
        "pedagogy_mode": "math_formal",
        "generation_mode": "review_blueprint",
        "course_purpose": "systematic",
        "current_readiness": "掌握高中代数与基础函数，尚未系统学习概率论",
        "adaptation_preference": "balanced",
        "asset_preferences": {},
        "web_question_enrichment": {"enabled": False},
    }

    try:
        storage = Storage(str(data_root))
        workspaces = GenerationWorkspaceRepository(data_root / "generation_workspaces")
        versions = CourseVersionRepository(data_root / "course_versions")
        assets = LearningAssetRepository(data_root / "learning_assets")
        documents = CourseDocumentRepository(storage)
        service = AuditedCourseService(
            materials=MaterialRepository(data_root / "materials"),
            audit_started_at=started_at,
        )
        task_manager_module.TASKS_FILE = data_root / "tasks.json"
        manager = TaskManager(
            storage,
            service,
            None,
            version_repository=versions,
            asset_repository=assets,
            workspace_repository=workspaces,
            document_repository=documents,
            question_bank_repository_override=QuestionBankRepository(
                data_root / "question_banks"
            ),
        )
        await manager.start()
        job = await manager.create_generation_job(request)
        task_id = str(job["job_id"])
        course_id = str(job["course_id"])
        print(json.dumps({
            "audit": "started",
            "task_id": task_id,
            "course_id": course_id,
            "audit_workspace": str(audit_root),
            "report_path": str(report_path),
        }, ensure_ascii=False), flush=True)

        last_key: tuple[Any, ...] | None = None
        while time.monotonic() - started_at < timeout_seconds:
            task = manager.tasks.get(task_id) or {}
            current_nodes = tuple(
                str(item.get("node_name") or "")
                for item in task.get("current_nodes") or []
            )
            key = (
                task.get("status"),
                task.get("phase"),
                task.get("progress"),
                task.get("phase_progress"),
                task.get("completed_nodes"),
                task.get("total_nodes"),
                current_nodes,
                task.get("message"),
            )
            if key != last_key:
                event = {
                    "elapsed_seconds": round(time.monotonic() - started_at, 2),
                    "status": task.get("status"),
                    "phase": task.get("phase"),
                    "progress": task.get("progress"),
                    "phase_progress": task.get("phase_progress"),
                    "completed_nodes": task.get("completed_nodes"),
                    "total_nodes": task.get("total_nodes"),
                    "current_nodes": list(current_nodes),
                    "message": str(task.get("message") or "")[:240],
                }
                timeline.append(event)
                print(json.dumps({"audit_event": event}, ensure_ascii=False), flush=True)
                last_key = key

            if task.get("status") == "waiting_for_review":
                review = manager.get_generation_review(course_id)
                if not review:
                    stop_reason = "waiting_for_review_without_artifact"
                    break
                step = str(review.get("step") or "unknown")
                artifact = review.get("artifact") or {}
                review_summary = {
                    "elapsed_seconds": round(time.monotonic() - started_at, 2),
                    "step": step,
                    "can_confirm": bool(review.get("can_confirm")),
                    "section_count": artifact.get("section_count"),
                    "completed_count": artifact.get("completed_count"),
                    "manual_review_count": artifact.get("manual_review_count"),
                    "quality_status": artifact.get("quality_status"),
                    "publication_allowed": artifact.get("publication_allowed"),
                    "blocking_issue_count": len(artifact.get("blocking_issues") or []),
                    "source_chain_can_publish": (artifact.get("source_chain") or {}).get("can_publish"),
                }
                if not reviews or reviews[-1] != review_summary:
                    reviews.append(review_summary)
                    print(json.dumps({"audit_review": review_summary}, ensure_ascii=False), flush=True)
                if step not in {"outline", "release"}:
                    stop_reason = f"unexpected_review_step:{step}"
                    break
                if not review.get("can_confirm"):
                    stop_reason = f"review_blocked:{step}"
                    break
                await manager.confirm_generation_step(course_id, step)
                confirmed_steps.append(step)
                continue

            if task.get("status") in TERMINAL_STATUSES:
                stop_reason = f"terminal:{task.get('status')}"
                break
            await asyncio.sleep(1)
        else:
            stop_reason = f"audit_timeout:{timeout_seconds}s"
    except BaseException as exc:
        runtime_error = {
            "type": type(exc).__name__,
            "message": str(exc)[:500],
        }
        stop_reason = stop_reason or f"exception:{type(exc).__name__}"
    finally:
        report = _collect_report(
            started_at=started_at,
            audit_root=audit_root,
            report_path=report_path,
            request=request,
            manager=manager,
            service=service,
            provider_handler=provider_handler,
            storage=storage,
            workspaces=workspaces,
            documents=documents,
            task_id=task_id,
            course_id=course_id,
            timeline=timeline,
            reviews=reviews,
            confirmed_steps=confirmed_steps,
            stop_reason=stop_reason,
            runtime_error=runtime_error,
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if manager:
            await manager.shutdown(timeout=10)
        ai_logger.removeHandler(provider_handler)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="真实运行并审计多章节课程生成主链")
    parser.add_argument(
        "--subject",
        default="概率论基础：从随机事件到中心极限定理",
    )
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("/tmp/lingzhi-course-generation-chain-audit.json"),
    )
    args = parser.parse_args()
    report = asyncio.run(run_audit(
        subject=args.subject,
        timeout_seconds=args.timeout,
        report_path=args.report.resolve(),
    ))
    print(json.dumps({
        "audit": "finished",
        "report_path": report.get("report_path"),
        "outcome": report.get("outcome"),
        "elapsed_seconds": report.get("elapsed_seconds"),
        "course_shape": {
            "chapter_count": (report.get("course_shape") or {}).get("chapter_count"),
            "section_count": (report.get("course_shape") or {}).get("section_count"),
        },
    }, ensure_ascii=False, indent=2), flush=True)
    return 0 if not (report.get("outcome") or {}).get("runtime_error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
