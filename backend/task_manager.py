# =============================================================================
# Task Manager - 课程生成任务管理器（纯 asyncio 架构）
# =============================================================================
#
# 架构说明：
# 本模块负责管理课程生成的异步任务队列，采用纯 asyncio 生产者-消费者模式。
# 使用 asyncio.Queue 调度任务，asyncio.Semaphore 控制并发上限。
#
# 生成流程：
# 1. 创建唯一 GenerationJob → 2. 生成并确认课程目录
# 3. 一次生成全课小节教案并本地编译知识库 → 4. 并行生成正文
# 5. 编译学习资产并执行确定性结构校验 → 6. 保存并推送进度
#
# Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 10.1, 10.2, 10.3, 10.4,
#               6.5, 7.1, 7.2, 7.5, 13.1, 13.2, 13.4, 13.5
# =============================================================================

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import re
import time
import uuid
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from content_blocks import set_node_content_blocks
from course_coherence import (
    compile_course_coherence_contract,
    evaluate_course_coherence,
)
from course_composition import compile_composition_profile
from course_document import document_from_generation_draft
from course_generation_workflow import PIPELINE_VERSION
from course_knowledge_base import (
    bind_course_knowledge_base_to_map,
    compile_course_knowledge_base,
)
from course_knowledge_map import compile_course_knowledge_map
from course_quality import build_final_course_quality_report, evaluate_node_content
from course_repository import (
    CourseDocumentConflict,
    CourseDocumentNotFound,
    CourseDocumentRepository,
)
from course_teaching_plan_projection import project_course_teaching_plan
from course_versioning import (
    analyze_blueprint_impact,
    build_blueprint_draft,
    merge_blueprint_draft,
)
from course_versions import (
    CourseVersionConflict,
    CourseVersionRepository,
    course_version_repository,
)
from generation_workspace import (
    GenerationWorkspaceNotFound,
    GenerationWorkspaceRepository,
    generation_workspace_repository,
)
from guided_generation import (
    GUIDED_STEP_KEYS,
    artifact_revision as guided_artifact_revision,
    build_source_chain_report,
    confirm_waiting_step,
    create_guided_workflow,
    expected_input_revisions as guided_expected_input_revisions,
    invalidate_after as invalidate_guided_steps_after,
    is_confirmed as guided_step_confirmed,
    mark_running as mark_guided_step_running,
    mark_waiting as mark_guided_step_waiting,
    migrate_guided_workflow,
    step_state as guided_step_state,
)
from learning_asset_storage import LearningAssetRepository, learning_asset_repository
from learning_assets import (
    assessment_assets,
    compile_learning_asset_plan,
    compile_learning_assets,
    evaluate_learning_asset_quality,
)
from question_bank import (
    QuestionBankRepository,
    question_bank_repository,
    reconcile_question_bank,
)
from question_search import enrich_question_bank_with_web
from material_pipeline import ingest_legacy_material_inputs
from material_storage import material_repository
from models import (
    NodeGenerationConfig,
    NodeStatus,
    TaskLogEntry,
)
from representation_compiler import compile_core_representations
from teaching_representations import teaching_representation_repository
from storage import DATA_DIR

logger = logging.getLogger(__name__)

DEFAULT_TASKS_FILE = Path(DATA_DIR) / "generation_jobs.json"
TASKS_FILE = DEFAULT_TASKS_FILE
LEGACY_TASKS_FILE = Path(__file__).with_name("tasks.json")

DEFAULT_MAX_CONCURRENCY = 2
DEFAULT_MAX_COURSE_CONCURRENCY = 2

# 内容完整性阈值（字符数）
CONTENT_COMPLETE_THRESHOLD = 600

STREAM_PROGRESS_INTERVAL_SECONDS = 1.5
DRAFT_CHECKPOINT_INTERVAL_SECONDS = 8.0
ACTIVE_NODE_PROGRESS_CREDIT = 0.35

# 重试上限
MAX_RETRIES = 2

# 指数退避参数
BACKOFF_BASE = 2
BACKOFF_MAX = 60


class TaskRecoveryConflict(RuntimeError):
    def __init__(self, message: str, *, recovery: dict[str, Any]) -> None:
        super().__init__(message)
        self.recovery = deepcopy(recovery)


class TaskStateConflict(RuntimeError):
    def __init__(self, message: str, *, status: str) -> None:
        super().__init__(message)
        self.status = status


def _remap_assessment_revision_references(
    assets: dict[str, Any],
    revision_remap: dict[str, str],
) -> None:
    """Keep mastery and final-assessment links aligned after a prompt repair."""
    for asset_type in ("mastery_criteria", "misconceptions"):
        for item in assets.get(asset_type) or []:
            if not isinstance(item, dict):
                continue
            item["assessment_bindings"] = [
                revision_remap.get(str(value), str(value))
                for value in item.get("assessment_bindings") or []
            ]
    for item in assets.get("final_assessment") or []:
        if not isinstance(item, dict):
            continue
        item["question_revision_ids"] = [
            revision_remap.get(str(value), str(value))
            for value in item.get("question_revision_ids") or []
        ]


def fix_latex_content(content: str) -> str:
    """修复 LaTeX 公式格式问题"""
    if not content:
        return content
    
    def fix_aligned_env(match):
        env_name = match.group(1)
        inner = match.group(2) if match.lastindex and match.lastindex >= 2 else ''
        
        inner = re.sub(r'\$\s*$', '', inner)
        inner = re.sub(r'^\s*\$', '', inner)
        inner = re.sub(r'\$\$', '', inner)
        inner = re.sub(r'\\\$', r'\\', inner)
        inner = re.sub(r'\\\s*$', r'\\', inner, flags=re.MULTILINE)
        inner = re.sub(r'\\\s*\n', r'\\\n', inner)
        
        return f'$$\n\\begin{{{env_name}}}\n{inner}\n\\end{{{env_name}}}\n$$'
    
    content = re.sub(
        r'\\begin\{(aligned|matrix|pmatrix|bmatrix|vmatrix|cases|eqnarray|gather|split)\}(.*?)(?:\\end\{\1\}|$)',
        fix_aligned_env,
        content,
        flags=re.DOTALL
    )
    
    content = re.sub(r'\\\[(.+?)\\\]', r'\n$$\n\1\n$$\n', content, flags=re.DOTALL)
    content = re.sub(r'\\\((.+?)\\\)', r'$\1$', content, flags=re.DOTALL)
    
    content = re.sub(
        r'(?<!\$)\$([^\n$]+?)\$(?!\$)',
        lambda match: f'${match.group(1).strip()}$',
        content,
    )
    
    return content


class TaskManager:
    """异步任务管理器，使用 asyncio 原生调度。

    通过 asyncio.Queue 实现生产者-消费者模式，asyncio.Semaphore 控制并发上限。
    集成 WebSocketService 进行实时推送，集成 CourseService 的流式生成方法。

    Attributes:
        storage: 存储层实例
        course_service: 课程生成服务实例
        ws_service: WebSocket 服务实例
        max_concurrency: 最大并发数
    """

    def __init__(
        self,
        storage: Any,
        course_service: Any,
        ws_service: Any,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
        max_course_concurrency: int = DEFAULT_MAX_COURSE_CONCURRENCY,
        version_repository: CourseVersionRepository | None = None,
        asset_repository: LearningAssetRepository | None = None,
        workspace_repository: GenerationWorkspaceRepository | None = None,
        document_repository: CourseDocumentRepository | None = None,
        question_bank_repository_override: QuestionBankRepository | None = None,
    ) -> None:
        self.storage = storage
        self.course_service = course_service
        self.ws_service = ws_service
        self._material_repository = getattr(course_service, "_material_repository", material_repository)
        self._version_repository = version_repository or course_version_repository
        self._learning_asset_repository = asset_repository or learning_asset_repository
        self._question_bank_repository = (
            question_bank_repository_override or question_bank_repository
        )
        self._generation_workspace_repository = workspace_repository or generation_workspace_repository
        self._course_document_repository = document_repository or CourseDocumentRepository(storage)
        self.max_concurrency = max_concurrency
        self.max_course_concurrency = max_course_concurrency

        # Task state
        self.tasks: dict[str, dict[str, Any]] = {}
        self._lock: asyncio.Lock = asyncio.Lock()
        self._creation_lock: asyncio.Lock = asyncio.Lock()

        # asyncio.Queue for producer-consumer pattern
        self._task_queue: asyncio.Queue[str] = asyncio.Queue()

        # Semaphore for concurrency control
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(max_concurrency)
        self._course_semaphore: asyncio.Semaphore = asyncio.Semaphore(max_course_concurrency)

        # Consumer loop task
        self._consumer_task: asyncio.Task[None] | None = None
        self._running: bool = False

        # Track running node tasks for cancellation
        # task_id -> {node_id -> asyncio.Task}
        self._running_node_tasks: dict[str, dict[str, asyncio.Task[Any]]] = {}
        self._running_job_tasks: dict[str, asyncio.Task[Any]] = {}

        # Task execution logs: task_id -> list[TaskLogEntry]
        self._task_logs: dict[str, list[TaskLogEntry]] = {}

        # Node retry counts: task_id -> {node_id -> count}
        self._node_retries: dict[str, dict[str, int]] = {}

        self.load_tasks()

    # -------------------------------------------------------------------------
    # Lifecycle: start / shutdown
    # -------------------------------------------------------------------------

    async def start(self) -> None:
        """通过 FastAPI lifespan 启动，创建消费者协程。

        **Validates: Requirements 10.1, 10.3**
        """
        if self._running:
            return
        self._running = True
        self._consumer_task = asyncio.create_task(self._consumer_loop())
        for task_id in list(self.tasks):
            if await self._reconcile_task_after_restart(task_id):
                await self._task_queue.put(task_id)
        self.save_tasks()
        logger.info("TaskManager started (max_concurrency=%d)", self.max_concurrency)

    async def shutdown(self, timeout: float = 30.0) -> None:
        """优雅关闭，等待正在执行的任务完成（最长 timeout 秒）。

        **Validates: Requirements 10.4**

        Args:
            timeout: 最长等待时间（秒），默认 30。
        """
        logger.info("TaskManager shutting down (timeout=%.1fs)...", timeout)
        self._running = False

        # Cancel the consumer loop
        if self._consumer_task and not self._consumer_task.done():
            self._consumer_task.cancel()
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._consumer_task), timeout=2.0
                )
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        # Gather all running jobs and node tasks
        all_node_tasks: list[asyncio.Task[Any]] = []
        all_node_tasks.extend(self._running_job_tasks.values())
        for node_tasks in self._running_node_tasks.values():
            all_node_tasks.extend(node_tasks.values())

        if all_node_tasks:
            logger.info("Waiting for %d running node tasks...", len(all_node_tasks))
            done, pending = await asyncio.wait(
                all_node_tasks, timeout=timeout
            )
            if pending:
                logger.warning(
                    "Force-cancelling %d tasks after %.1fs timeout",
                    len(pending), timeout,
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

        self.save_tasks()
        logger.info("TaskManager shutdown complete")

    # -------------------------------------------------------------------------
    # Task Lifecycle Management
    # -------------------------------------------------------------------------

    async def create_task(
        self,
        course_id: str,
        task_type: str = "course_generation",
        *,
        course_name: str = "",
        request_snapshot: dict[str, Any] | None = None,
        task_id: str | None = None,
        workspace_id: str | None = None,
        base_document_revision: str | None = None,
        enqueue: bool = True,
    ) -> str:
        """创建任务并放入 asyncio.Queue。

        **Validates: Requirements 10.2**

        Args:
            course_id: 课程 ID
            task_type: 任务类型

        Returns:
            新创建的 task_id
        """
        task_id = task_id or str(uuid.uuid4())
        now = datetime.now().isoformat()
        task: dict[str, Any] = {
            "id": task_id,
            "course_id": course_id,
            "type": task_type,
            "course_name": course_name,
            "status": "pending",
            "phase": "queued",
            "progress": 0,
            "total": 0,
            "completed_nodes": 0,
            "total_nodes": 0,
            "current_node_name": "",
            "current_phase": "",
            "phase_progress": 0,
            "phase_detail": {},
            "current_nodes": [],
            "message": "等待开始...",
            "created_at": now,
            "updated_at": now,
            "error": None,
            "retry_count": 0,
            "logs": [],
            "request_snapshot": request_snapshot or {},
            "node_drafts": {},
            "operation": str((request_snapshot or {}).get("operation") or "generate"),
            "candidate_id": (request_snapshot or {}).get("candidate_id"),
            "base_version_id": (request_snapshot or {}).get("base_version_id"),
            "blueprint_confirmed": bool((request_snapshot or {}).get("blueprint_confirmed", False)),
            "blueprint_revision_id": (request_snapshot or {}).get("blueprint_revision_id"),
            "workspace_id": workspace_id,
            "base_document_revision": base_document_revision,
        }
        if (
            task_type == "course_generation"
            and workspace_id
            and task["operation"] == "generate"
        ):
            task["guided_workflow"] = create_guided_workflow(task["request_snapshot"])
        async with self._lock:
            self.tasks[task_id] = task
            self._task_logs[task_id] = []
            self._node_retries[task_id] = {}
            try:
                self.save_tasks(strict=True)
            except Exception:
                self.tasks.pop(task_id, None)
                self._task_logs.pop(task_id, None)
                self._node_retries.pop(task_id, None)
                raise

        if enqueue:
            try:
                await self._task_queue.put(task_id)
            except BaseException:
                async with self._lock:
                    self.tasks.pop(task_id, None)
                    self._task_logs.pop(task_id, None)
                    self._node_retries.pop(task_id, None)
                    self.save_tasks(strict=True)
                raise
        logger.info("Created task %s for course %s", task_id, course_id)
        return task_id

    async def create_generation_job(
        self, request_snapshot: dict[str, Any]
    ) -> dict[str, Any]:
        """Create one durable job, a canonical shell, and an isolated generation workspace."""
        request_snapshot = dict(request_snapshot)
        async with self._creation_lock:
            request_id = str(request_snapshot.get("request_id") or "").strip()
            if request_id:
                existing = next(
                    (
                        task for task in self.tasks.values()
                        if str((task.get("request_snapshot") or {}).get("request_id") or "") == request_id
                    ),
                    None,
                )
                if existing:
                    return {
                        "job_id": str(existing["id"]),
                        "task_id": str(existing["id"]),
                        "course_id": str(existing["course_id"]),
                        "course_name": str(existing.get("course_name") or ""),
                        "status": str(existing.get("status") or "pending"),
                        "phase": str(existing.get("phase") or "queued"),
                        "deduplicated": True,
                    }
            return await self._create_generation_job(request_snapshot)

    async def _create_generation_job(
        self, request_snapshot: dict[str, Any]
    ) -> dict[str, Any]:
        subject = str(request_snapshot.get("subject") or "").strip()
        if not subject:
            raise ValueError("Course subject cannot be blank")
        request_snapshot["subject"] = subject
        composition_profile = compile_composition_profile(
            request_snapshot.get("composition_style"),
            legacy_style=request_snapshot.get("style"),
        )
        request_snapshot["composition_style"] = composition_profile["style"]
        # First-time generation has one product path. Requirements and outline
        # are followed by automatic teaching-plan/content production, then one
        # content review and one release confirmation.
        request_snapshot["generation_mode"] = "review_blueprint"
        legacy_bindings, metadata_only = await ingest_legacy_material_inputs(
            request_snapshot.get("materials") or [],
            repository=self._material_repository,
        )
        existing_bindings = list(request_snapshot.get("material_bindings") or [])
        request_snapshot["material_bindings"] = existing_bindings + legacy_bindings
        request_snapshot["materials"] = metadata_only
        course_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        course_data = {
            "course_id": course_id,
            "course_name": subject,
            "generation_schema_version": PIPELINE_VERSION,
            "generation_status": "queued",
            "nodes": [],
            "generation_request": request_snapshot,
            "generation_quality_report": None,
            "course_purpose": request_snapshot.get("course_purpose") or "systematic",
            "generation_mode": "review_blueprint",
            "asset_preferences": deepcopy(request_snapshot.get("asset_preferences") or {}),
            "web_question_enrichment": deepcopy(
                request_snapshot.get("web_question_enrichment") or {"enabled": False}
            ),
        }
        workspace_created = False
        try:
            self._generation_workspace_repository.create(
                task_id,
                course_id=course_id,
                course_data=course_data,
            )
            workspace_created = True
            shell = await self._course_document_repository.create_generation_shell(
                course_id,
                title=subject,
                job_id=task_id,
                metadata=course_data,
            )
            task_id = await self.create_task(
                course_id,
                "course_generation",
                course_name=subject,
                request_snapshot=request_snapshot,
                task_id=task_id,
                workspace_id=task_id,
                base_document_revision=str(shell["document"]["document_revision"]),
            )
        except BaseException:
            raw = self.storage.load_course(course_id) if self.storage else None
            if isinstance(raw, dict) and raw.get("generation_job_id") == task_id:
                await self._delete_stored_course(course_id)
            if workspace_created:
                self._generation_workspace_repository.delete(task_id)
            self._version_repository.delete_course(course_id)
            self._learning_asset_repository.delete_course(course_id)
            self._question_bank_repository.delete_course(course_id)
            self._reset_course_service_runtime(course_id, preserve_course=False)
            raise
        return {
            "job_id": task_id,
            "task_id": task_id,
            "course_id": course_id,
            "course_name": subject,
            "status": "pending",
            "phase": "queued",
        }

    @staticmethod
    def _sync_outline_plan_from_nodes(
        plan: dict[str, Any],
        nodes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Make the editable outline nodes the canonical outline input."""
        synced = deepcopy(plan)
        by_id = {
            str(node.get("node_id") or ""): node
            for node in nodes
            if isinstance(node, dict)
        }
        for chapter in synced.get("chapters") or []:
            chapter_number = str(chapter.get("chapter_number") or "")
            chapter_node = by_id.get(f"L1-{chapter_number}")
            if chapter_node:
                chapter_name = str(chapter_node.get("node_name") or "").strip()
                prefix = f"第{chapter_number}章 "
                chapter["title"] = (
                    chapter_name[len(prefix):].strip()
                    if chapter_name.startswith(prefix)
                    else chapter_name or chapter.get("title")
                )
            for section in chapter.get("sections") or []:
                section_number = str(section.get("section_number") or "")
                node = by_id.get(f"L2-{section_number.replace('.', '-')}")
                if not node:
                    continue
                node_name = str(node.get("node_name") or "").strip()
                prefix = f"{section_number} "
                section["title"] = (
                    node_name[len(prefix):].strip()
                    if node_name.startswith(prefix)
                    else node_name or section.get("title")
                )
                for field in (
                    "learning_objective",
                    "scope_boundary",
                    "assessment",
                    "prerequisite_node_ids",
                ):
                    if field in node:
                        section[field] = deepcopy(node[field])
        return synced

    @staticmethod
    def _strip_plan_after_outline(plan: dict[str, Any]) -> dict[str, Any]:
        """Keep only what the user approved at the outline boundary."""
        outline = deepcopy(plan)
        for field in (
            "knowledge_relations",
            "course_module_plan",
            "course_block_distribution",
            "course_difficulty_curve",
            "difficulty_profile",
        ):
            outline.pop(field, None)
        for chapter in outline.get("chapters") or []:
            for section in chapter.get("sections") or []:
                for field in (
                    "key_points",
                    "knowledge_structure",
                    "reused_knowledge_names",
                    "knowledge_relations",
                    "knowledge_package_status",
                    "module_plan",
                    "difficulty_contract",
                    "examples_plan",
                    "exercise_plan",
                ):
                    section.pop(field, None)
        return outline

    @classmethod
    def _discard_generation_artifacts_after(
        cls,
        course_data: dict[str, Any],
        step: str,
    ) -> dict[str, Any]:
        """Discard stale downstream data when an approved upstream step changes."""
        working = deepcopy(course_data)
        if step != "outline":
            return working

        plan = cls._strip_plan_after_outline(
            working.get("course_plan") or working.get("course_outline") or {}
        )
        working["course_plan"] = plan
        working["course_outline"] = deepcopy(plan)
        for field in (
            "course_knowledge_scope_contract",
            "course_teaching_plan",
            "course_knowledge_index",
            "course_knowledge_base",
            "course_knowledge_map",
            "course_knowledge_quality_report",
            "knowledge_relations",
            "knowledge_relation_decisions",
            "knowledge_relation_schema_version",
            "course_plan_constraint_report",
            "course_module_plan",
            "course_block_distribution",
            "course_difficulty_curve",
            "learning_asset_plan",
            "learning_assets",
            "learning_asset_bundle_revision_id",
            "asset_quality_report",
            "course_coherence_contract",
            "course_coherence_quality_report",
            "generation_quality_report",
            "generation_source_chain_report",
            "generation_completed_at",
        ):
            working.pop(field, None)

        downstream_node_fields = (
            "key_points",
            "knowledge_structure",
            "reused_knowledge_names",
            "module_plan",
            "difficulty_contract",
            "examples_plan",
            "exercise_plan",
            "node_content",
            "node_content_draft",
            "content_blocks",
            "course_blocks",
            "grounding_annotations",
            "grounding_invalid_refs",
            "generation_quality",
            "generated_chars",
            "needs_manual_review",
            "error_summary",
            "objective_id",
            "objective_revision_id",
        )
        for node in working.get("nodes") or []:
            for field in downstream_node_fields:
                node.pop(field, None)
            node["generation_status"] = "pending"

        blueprint = deepcopy(working.get("course_blueprint") or {})
        for field in (
            "knowledge_relations",
            "course_module_plan",
            "course_block_distribution",
            "course_difficulty_curve",
            "course_plan_constraint_report",
            "course_knowledge_base_revision_id",
            "course_coherence_revision_id",
            "learning_asset_plan",
        ):
            blueprint.pop(field, None)
        blueprint["sections"] = deepcopy(plan.get("chapters") or [])
        blueprint["nodes"] = [
            {
                key: deepcopy(node.get(key))
                for key in (
                    "node_id",
                    "parent_node_id",
                    "node_name",
                    "node_level",
                    "learning_objective",
                    "scope_boundary",
                    "assessment",
                    "prerequisite_node_ids",
                )
                if key in node
            }
            for node in working.get("nodes") or []
        ]
        working["course_blueprint"] = blueprint
        working["generation_stage_artifacts"] = {
            key: deepcopy(value)
            for key, value in (
                working.get("generation_stage_artifacts") or {}
            ).items()
            if key == "outline"
        }
        return working

    async def confirm_generation_step(
        self,
        course_id: str,
        step: str,
    ) -> dict[str, Any]:
        """Confirm the current user-facing artifact and resume the same job."""
        waiting = [
            task for task in self.tasks.values()
            if task.get("course_id") == course_id
            and task.get("status") == "waiting_for_review"
            and task.get("type") == "course_generation"
        ]
        if not waiting:
            related = [
                task for task in self.tasks.values()
                if task.get("course_id") == course_id
                and task.get("type") == "course_generation"
                and isinstance(task.get("guided_workflow"), dict)
            ]
            related.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
            if related:
                latest = related[0]
                confirmed_state = next(
                    (
                        item for item in latest["guided_workflow"].get("steps") or []
                        if item.get("key") == step
                    ),
                    None,
                )
                if confirmed_state and confirmed_state.get("status") == "confirmed":
                    return {
                        "status": "already_confirmed",
                        "job_id": str(latest["id"]),
                        "course_id": course_id,
                        "confirmed_step": step,
                        "artifact_revision": confirmed_state.get("artifact_revision"),
                        "guided_workflow": deepcopy(latest["guided_workflow"]),
                    }
            raise ValueError("No course generation job is waiting for review")
        waiting.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        task = waiting[0]
        task_id = str(task["id"])
        workflow = task.get("guided_workflow")
        if not isinstance(workflow, dict):
            raise ValueError("This generation job does not use the guided workflow")
        review_step = str(workflow.get("review_step") or "")
        if review_step != step:
            raise ValueError(
                f"Current review step is {review_step or 'none'}, not {step}"
            )
        course_data = self._load_task_course(task_id)
        if not course_data:
            raise ValueError("Course not found")

        impact: dict[str, Any] | None = None
        if step == "outline":
            outline_state = guided_step_state(workflow, "outline")
            reopened_revision = str(
                outline_state.get("previous_confirmed_revision") or ""
            )
            draft = self._version_repository.load_draft(course_id) or build_blueprint_draft(course_data)
            impact = analyze_blueprint_impact(course_data, draft)
            if not impact.get("can_confirm", False):
                raise CourseVersionConflict("Blueprint contains locked conflicts")
            confirmed = merge_blueprint_draft(course_data, draft)
            plan = deepcopy(confirmed.get("course_plan") or confirmed.get("course_outline") or {})
            if isinstance(plan, dict):
                plan["course_title"] = str(confirmed.get("course_name") or plan.get("course_title") or "")
                plan = self._sync_outline_plan_from_nodes(
                    plan,
                    confirmed.get("nodes") or [],
                )
                confirmed["course_plan"] = self._strip_plan_after_outline(plan)
                confirmed["course_outline"] = deepcopy(confirmed["course_plan"])
            if reopened_revision:
                confirmed = self._discard_generation_artifacts_after(
                    confirmed,
                    "outline",
                )
            confirmed["generation_status"] = "outline_confirmed"
            confirmed["blueprint_revision_id"] = impact.get("draft_blueprint_revision_id")
            frozen = self._version_repository.freeze_blueprint(course_id, confirmed)
            confirmed["blueprint_revision_id"] = frozen["blueprint_revision_id"]
            confirmed["course_outline_revision_id"] = frozen["blueprint_revision_id"]
            course_data = confirmed
            await self._save_task_course(task_id, course_data)
            self._version_repository.delete_draft(course_id)
            revision = guided_artifact_revision(
                "outline",
                course_data,
                request=task.get("request_snapshot") or {},
            )
            # 目录审阅页允许用户在确认前编辑；最终确认的是保存后的最新版，
            # 而不是刚进入审阅页时的旧修订。
            for item in workflow.get("steps") or []:
                if item.get("key") == "outline":
                    item["artifact_revision"] = revision
                    item.pop("previous_confirmed_revision", None)
                    break
            task["blueprint_confirmed"] = True
            task["blueprint_revision_id"] = revision
        else:
            if step == "release":
                # The publish gate is a decision made NOW: recompute the
                # source-chain report at confirm time instead of trusting a
                # snapshot stored by an earlier (possibly older) run.
                source_report = build_source_chain_report(
                    workflow,
                    course_data,
                    request=task.get("request_snapshot") or {},
                )
                quality_report = dict(
                    course_data.get("generation_quality_report") or {}
                )
                if not source_report.get("can_publish"):
                    raise CourseVersionConflict(
                        "The course no longer matches the confirmed source chain"
                    )
                quality_report["source_chain_passed"] = True
                if quality_report and not quality_report.get(
                    "publication_allowed"
                ) and quality_report.get("final_status") in {
                    "completed",
                    "completed_with_warnings",
                }:
                    # publication_allowed may have been stamped false purely
                    # because the stale stored source-chain report failed.
                    quality_report["publication_allowed"] = (
                        self._quality_allows_publication(
                            course_data,
                            quality_report,
                        )
                    )
                if not quality_report.get("publication_allowed"):
                    raise CourseVersionConflict(
                        "The course has blocking quality issues and cannot be published"
                    )
                course_data["generation_source_chain_report"] = source_report
                course_data["generation_quality_report"] = quality_report
                await self._save_task_course(task_id, course_data)
                # Like the outline step, the release review confirms the
                # saved state as of NOW (the recomputed gate reports above are
                # part of the reviewed artifact), so re-stamp its revision.
                refreshed_revision = guided_artifact_revision(
                    "release",
                    course_data,
                    request=task.get("request_snapshot") or {},
                )
                for item in workflow.get("steps") or []:
                    if item.get("key") == "release":
                        item["artifact_revision"] = refreshed_revision
                        break
            revision = guided_artifact_revision(
                step,
                course_data,
                request=task.get("request_snapshot") or {},
            )

        confirm_waiting_step(workflow, step, revision=revision)
        async with self._lock:
            task["status"] = "pending"
            task["phase"] = f"{step}_confirmed"
            task["phase_progress"] = 100
            task["message"] = {
                "outline": "课程目录已确认，开始冻结全课知识职责并按预算生成详细教案与正文",
                "content": "课程内容已确认，开始执行结构与发布预检",
                "release": "确认发布已完成，正在发布课程",
            }.get(step, "当前步骤已确认，继续生成")
            task["updated_at"] = datetime.now().isoformat()
            self.save_tasks()
        await self._task_queue.put(task_id)
        await self._push_progress(task_id)
        return {
            "status": "resumed",
            "job_id": task_id,
            "course_id": course_id,
            "confirmed_step": step,
            "artifact_revision": revision,
            "blueprint_revision_id": course_data.get("blueprint_revision_id"),
            "impact_report": impact,
            "guided_workflow": deepcopy(workflow),
        }

    async def reopen_generation_step(
        self,
        course_id: str,
        step: str,
    ) -> dict[str, Any]:
        """Return to a confirmed upstream review and invalidate every later step."""
        if step != "outline":
            raise ValueError(
                "Only the course outline can currently be edited after confirmation"
            )
        waiting = [
            task
            for task in self.tasks.values()
            if task.get("course_id") == course_id
            and task.get("type") == "course_generation"
            and task.get("status") == "waiting_for_review"
            and isinstance(task.get("guided_workflow"), dict)
        ]
        waiting.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        if not waiting:
            raise ValueError(
                "The generation job must be waiting for review before returning upstream"
            )
        task = waiting[0]
        task_id = str(task["id"])
        workflow = task["guided_workflow"]
        current_review = str(workflow.get("review_step") or "")
        if not current_review:
            raise ValueError("No generation step is currently waiting for review")
        if GUIDED_STEP_KEYS.index(current_review) <= GUIDED_STEP_KEYS.index(step):
            raise ValueError("The requested step is not upstream of the current review")
        state = guided_step_state(workflow, step)
        if state.get("status") != "confirmed":
            raise ValueError("The requested upstream step has not been confirmed")

        previous_revision = str(state.get("artifact_revision") or "")
        invalidated_steps = invalidate_guided_steps_after(workflow, step)
        state["status"] = "waiting_for_confirmation"
        state["confirmed_at"] = None
        state["previous_confirmed_revision"] = previous_revision
        state["input_revisions"] = guided_expected_input_revisions(workflow, step)
        workflow["current_step"] = step
        workflow["review_step"] = step
        workflow["updated_at"] = datetime.now().isoformat()

        course_data = self._load_task_course(task_id)
        if not course_data:
            raise ValueError("Course not found")
        draft = build_blueprint_draft(course_data)
        draft["impact_report"] = analyze_blueprint_impact(course_data, draft)
        self._version_repository.save_draft(course_id, draft)

        async with self._lock:
            task["status"] = "waiting_for_review"
            task["phase"] = "outline_reopened"
            task["phase_progress"] = 100
            task["message"] = "已返回课程目录；重新确认后，下游内容会按新目录重建"
            task["updated_at"] = datetime.now().isoformat()
            self.save_tasks()
        await self._push_progress(task_id)
        return {
            "status": "reopened",
            "job_id": task_id,
            "course_id": course_id,
            "review_step": step,
            "previous_artifact_revision": previous_revision,
            "invalidated_steps": invalidated_steps,
            "guided_workflow": deepcopy(workflow),
        }

    async def confirm_blueprint(self, course_id: str) -> dict[str, Any]:
        """Compatibility alias for the former outline-only review endpoint."""
        return await self.confirm_generation_step(course_id, "outline")
    async def create_regeneration_job(
        self,
        course_id: str,
        *,
        reason: str = "更新受影响内容",
        regenerate_all: bool = False,
    ) -> dict[str, Any]:
        """Create a candidate workspace and schedule only affected nodes."""
        active_task_id = self._find_active_task(course_id)
        if active_task_id:
            active = self.tasks[active_task_id]
            raise TaskStateConflict(
                "Course already has an active generation task",
                status=str(active.get("status") or "running"),
            )
        course_data = self.storage.load_course(course_id)
        if not course_data:
            raise ValueError("Course not found")
        current_entry = self._version_repository.ensure_initial_version(course_id, course_data)
        draft = self._version_repository.load_draft(course_id)
        if not draft:
            draft = build_blueprint_draft(course_data)
        impact = analyze_blueprint_impact(course_data, draft)
        if not impact.get("can_confirm", False):
            raise CourseVersionConflict("Blueprint contains locked conflicts")
        candidate_course = merge_blueprint_draft(course_data, draft)
        frozen = self._version_repository.freeze_blueprint(course_id, candidate_course)
        candidate_course["blueprint_revision_id"] = frozen["blueprint_revision_id"]
        affected = {
            str(node.get("node_id") or "")
            for node in candidate_course.get("nodes") or []
            if regenerate_all and int(node.get("node_level") or 1) == 2
        } or set(impact.get("affected_node_ids") or [])
        if not affected:
            affected = {
                str(node.get("node_id") or "")
                for node in candidate_course.get("nodes") or []
                if int(node.get("node_level") or 1) == 2
                and not self._is_content_complete(node)
            }
        for node in candidate_course.get("nodes") or []:
            node_id = str(node.get("node_id") or "")
            if node_id in affected and int(node.get("node_level") or 1) == 2:
                node["previous_content_revision_id"] = (
                    current_entry.get("content_revision_ids") or {}
                ).get(node_id)
                node["node_content"] = ""
                node.pop("node_content_draft", None)
                node["generation_status"] = NodeStatus.PENDING.value
                node["asset_status"] = "stale"
        if regenerate_all:
            impact["affected_node_ids"] = sorted(affected)
            impact["regenerate_all"] = True
        candidate = self._version_repository.create_candidate(
            course_id,
            candidate_course,
            base_version_id=current_entry.get("version_id"),
            impact_report=impact,
        )
        if not affected and not impact.get("asset_impacts"):
            promoted, version_entry = self._version_repository.promote_candidate(
                course_id,
                candidate["candidate_id"],
                reason=reason,
                operation="blueprint_metadata_update",
            )
            await self._save_course(course_id, promoted)
            self._version_repository.delete_draft(course_id)
            return {
                "status": "completed",
                "course_id": course_id,
                "candidate_id": candidate["candidate_id"],
                "course_version_id": version_entry["version_id"],
                "impact_report": impact,
            }
        request_snapshot = {
            "operation": "regenerate",
            "candidate_id": candidate["candidate_id"],
            "base_version_id": current_entry.get("version_id"),
            "blueprint_confirmed": True,
            "blueprint_revision_id": frozen["blueprint_revision_id"],
            "affected_node_ids": sorted(affected),
            "reason": reason,
        }
        task_id: str | None = None
        try:
            task_id = await self.create_task(
                course_id,
                "course_generation",
                course_name=str(course_data.get("course_name") or ""),
                request_snapshot=request_snapshot,
                enqueue=False,
            )
            candidate["job_id"] = task_id
            candidate["status"] = "queued"
            self._version_repository.save_candidate(course_id, candidate["candidate_id"], candidate)
            self._version_repository.delete_draft(course_id)
            await self._task_queue.put(task_id)
        except BaseException:
            if task_id and task_id in self.tasks:
                async with self._lock:
                    self.tasks.pop(task_id, None)
                    self._task_logs.pop(task_id, None)
                    self._node_retries.pop(task_id, None)
                    self.save_tasks(strict=True)
            self._version_repository.delete_candidate(course_id, candidate["candidate_id"])
            raise
        return {
            "status": "pending",
            "job_id": task_id,
            "task_id": task_id,
            "course_id": course_id,
            "candidate_id": candidate["candidate_id"],
            "base_version_id": current_entry.get("version_id"),
            "impact_report": impact,
        }

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        """获取任务信息。"""
        task = self.tasks.get(task_id)
        return self._task_view(task) if task else None

    def get_all_tasks(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取所有任务，按状态优先级和时间排序。"""
        status_priority = {
            "running": 0,
            "pending": 1,
            "waiting_for_review": 2,
            "paused": 3,
            "failed": 4,
            "completed": 5,
        }
        tasks_list = [self._task_view(task) for task in self.tasks.values()]
        tasks_list.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        tasks_list.sort(
            key=lambda x: status_priority.get(x.get("status", ""), 5)
        )
        return tasks_list[:limit]

    def get_tasks_by_course(self, course_id: str) -> list[dict[str, Any]]:
        """获取指定课程的所有任务。"""
        return [self._task_view(task) for task in self.tasks.values() if task["course_id"] == course_id]

    def get_generation_workspace_course(self, course_id: str) -> dict[str, Any] | None:
        candidates = [
            task for task in self.tasks.values()
            if task.get("course_id") == course_id and task.get("workspace_id")
        ]
        candidates.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        for task in candidates:
            try:
                workspace_id = str(task["workspace_id"])
                workspace = self._generation_workspace_repository.load(workspace_id)
                if workspace.get("status") == "published":
                    continue
                return self._generation_workspace_repository.load_course(workspace_id)
            except GenerationWorkspaceNotFound:
                continue
        return None

    def get_generation_preview(self, course_id: str) -> dict[str, Any] | None:
        """Project one active generation workspace into a user-safe read model."""
        candidates = [
            task for task in self.tasks.values()
            if task.get("course_id") == course_id and task.get("workspace_id")
        ]
        candidates.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        if not candidates:
            return None
        task = candidates[0]
        workspace_id = str(task.get("workspace_id") or "")
        if not workspace_id:
            return None
        try:
            workspace = self._generation_workspace_repository.load(workspace_id)
            if workspace.get("status") == "published":
                return None
            course_data = self._generation_workspace_repository.load_course(workspace_id)
        except GenerationWorkspaceNotFound:
            return None

        task_view = self._task_view(task)
        active_node_ids = {
            str(item.get("node_id") or "")
            for item in task_view.get("current_nodes") or []
            if item.get("node_id")
        }
        nodes: list[dict[str, Any]] = []
        for raw in course_data.get("nodes") or []:
            status = str(raw.get("generation_status") or NodeStatus.PENDING.value)
            node_id = str(raw.get("node_id") or "")
            if node_id in active_node_ids and status == NodeStatus.PENDING.value:
                status = NodeStatus.GENERATING.value
            final_content = str(raw.get("node_content") or "")
            draft_content = str(raw.get("node_content_draft") or "")
            visible_content = final_content or draft_content
            if status == NodeStatus.COMPLETED.value:
                content_state = "finalized"
            elif visible_content:
                content_state = "draft"
            elif status == NodeStatus.ERROR.value:
                content_state = "failed"
            else:
                content_state = status
            node = {
                "node_id": node_id,
                "parent_node_id": str(raw.get("parent_node_id") or "root"),
                "node_name": str(raw.get("node_name") or "未命名章节"),
                "node_level": int(raw.get("node_level") or 1),
                "node_type": str(raw.get("node_type") or "original"),
                "node_content": visible_content,
                "learning_objective": str(raw.get("learning_objective") or ""),
                "generation_status": status,
                "content_state": content_state,
                "generated_chars": int(raw.get("generated_chars") or len(visible_content)),
                "error_summary": raw.get("error_summary"),
                "difficulty_contract": deepcopy(raw.get("difficulty_contract") or {}),
                "content_blocks": (
                    deepcopy(raw.get("content_blocks") or [])
                    if status == NodeStatus.COMPLETED.value
                    else []
                ),
            }
            nodes.append(node)

        return {
            "schema_version": "generation_preview_v2",
            "projection": "generation_workspace",
            "course_id": str(course_data.get("course_id") or course_id),
            "course_name": str(course_data.get("course_name") or task.get("course_name") or ""),
            "workspace_id": workspace_id,
            "workspace_status": str(workspace.get("status") or "active"),
            "updated_at": workspace.get("updated_at") or task.get("updated_at"),
            "task": {
                key: deepcopy(task_view.get(key))
                for key in (
                    "id",
                    "course_id",
                    "course_name",
                    "status",
                    "phase",
                    "current_phase",
                    "progress",
                    "phase_progress",
                    "phase_detail",
                    "guided_workflow",
                    "message",
                    "error",
                    "completed_nodes",
                    "total_nodes",
                    "current_node_name",
                    "current_nodes",
                    "updated_at",
                    "operation",
                    "recovery",
                )
            },
            "teaching_plan": project_course_teaching_plan(course_data),
            "nodes": nodes,
        }

    def get_generation_review(self, course_id: str) -> dict[str, Any] | None:
        """Return the safe, product-facing artifact for the current review step."""
        candidates = [
            task
            for task in self.tasks.values()
            if task.get("course_id") == course_id
            and isinstance(task.get("guided_workflow"), dict)
        ]
        candidates.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        if not candidates:
            return None
        task = candidates[0]
        workflow = deepcopy(task["guided_workflow"])
        workspace_id = str(task.get("workspace_id") or "")
        try:
            course_data = (
                self._generation_workspace_repository.load_course(workspace_id)
                if workspace_id
                else self._load_task_course(str(task["id"]))
            )
        except GenerationWorkspaceNotFound:
            return None
        if not isinstance(course_data, dict):
            return None

        step = str(workflow.get("review_step") or workflow.get("current_step") or "outline")
        artifact: dict[str, Any] = {}
        if step == "outline":
            plan = course_data.get("course_plan") or course_data.get("course_outline") or {}
            artifact = {
                "course_name": str(course_data.get("course_name") or ""),
                "course_positioning": str(
                    plan.get("course_positioning")
                    or plan.get("positioning")
                    or plan.get("course_description")
                    or ""
                ),
                "learning_objectives": deepcopy(
                    plan.get("learning_objectives")
                    or course_data.get("learning_objectives")
                    or []
                ),
                "sections": [
                    {
                        "node_id": str(node.get("node_id") or ""),
                        "parent_node_id": str(node.get("parent_node_id") or "root"),
                        "name": str(node.get("node_name") or ""),
                        "level": int(node.get("node_level") or 1),
                        "learning_objective": str(node.get("learning_objective") or ""),
                        "scope_boundary": str(node.get("scope_boundary") or ""),
                    }
                    for node in course_data.get("nodes") or []
                ],
            }
        elif step == "content":
            content_nodes = [
                node
                for node in course_data.get("nodes") or []
                if int(node.get("node_level") or 1) == 2
            ]
            learning_assets = course_data.get("learning_assets") or {}
            quality_report = course_data.get("generation_quality_report") or {}
            asset_quality = course_data.get("asset_quality_report") or {}
            blocking_issues = [
                *deepcopy(quality_report.get("blocking_issues") or []),
                *deepcopy(asset_quality.get("blocking_issues") or []),
            ]
            assessment_items = assessment_assets(learning_assets)
            questions = [item for _, item in assessment_items]
            question_samples = []
            for asset_type, question in assessment_items[:8]:
                analysis = question.get("question_analysis") or {}
                understanding = analysis.get("question_understanding") or {}
                mapping = analysis.get("mapping") or {}
                intent = question.get("assessment_intent") or {}
                question_samples.append({
                    "question_id": str(question.get("question_id") or ""),
                    "asset_type": asset_type,
                    "practice_level": str(question.get("practice_level") or ""),
                    "prompt": str(question.get("prompt") or ""),
                    "status": str(analysis.get("status") or "pending"),
                    "task_goal": str(understanding.get("task_goal") or ""),
                    "why_this_question": str(intent.get("why_this_question") or ""),
                    "library_fit": str(mapping.get("library_fit") or ""),
                    "target_skills": deepcopy(intent.get("target_skills") or []),
                    "target_misconceptions": deepcopy(
                        intent.get("target_misconceptions") or []
                    ),
                    "issues": deepcopy((analysis.get("quality") or {}).get("issues") or []),
                })
            artifact = {
                "section_count": len(content_nodes),
                "completed_count": sum(self._is_content_complete(node) for node in content_nodes),
                "manual_review_count": sum(
                    bool(node.get("needs_manual_review"))
                    for node in content_nodes
                ),
                "quality_status": quality_report.get("final_status"),
                "quality_score": quality_report.get("score"),
                "asset_quality_passed": bool(asset_quality.get("passed")),
                "asset_counts": {
                    str(asset_type): len(values)
                    for asset_type, values in learning_assets.items()
                    if isinstance(values, list) and values
                },
                "question_review": {
                    "total": len(questions),
                    "passed": sum(
                        (item.get("question_analysis") or {}).get("status") == "passed"
                        for item in questions
                    ),
                    "blocked": sum(
                        (item.get("question_analysis") or {}).get("status") == "blocked"
                        for item in questions
                    ),
                    "samples": question_samples,
                },
                "blocking_issues": blocking_issues,
                "asset_blocking_issues": deepcopy(
                    asset_quality.get("blocking_issues") or []
                ),
                "warnings": deepcopy(
                    quality_report.get("warnings")
                    or quality_report.get("quality_warnings")
                    or []
                ),
                "sections": [
                    {
                        "node_id": str(node.get("node_id") or ""),
                        "name": str(node.get("node_name") or ""),
                        "status": str(node.get("generation_status") or ""),
                        "character_count": len(str(node.get("node_content") or "")),
                        "block_count": len(node.get("content_blocks") or []),
                        "needs_manual_review": bool(node.get("needs_manual_review")),
                    }
                    for node in content_nodes
                ],
            }
        elif step == "release":
            source_report = deepcopy(course_data.get("generation_source_chain_report") or {})
            quality_report = deepcopy(course_data.get("generation_quality_report") or {})
            artifact = {
                "quality_status": quality_report.get("final_status"),
                "publication_allowed": bool(quality_report.get("publication_allowed")),
                "blocking_issues": deepcopy(quality_report.get("blocking_issues") or []),
                "warnings": deepcopy(
                    quality_report.get("warnings")
                    or quality_report.get("quality_warnings")
                    or []
                ),
                "source_chain": source_report,
            }

        return {
            "schema_version": "guided_generation_review_v1",
            "course_id": course_id,
            "job_id": str(task.get("id") or ""),
            "status": str(task.get("status") or ""),
            "step": step,
            "can_confirm": (
                task.get("status") == "waiting_for_review"
                and workflow.get("review_step") == step
                and (
                    (
                        step != "content"
                        or (
                            artifact.get("completed_count")
                            == artifact.get("section_count")
                            and not artifact.get("blocking_issues")
                            and not (artifact.get("question_review") or {}).get(
                                "blocked"
                            )
                        )
                    )
                    and (
                        step != "release"
                        or (
                            artifact.get("publication_allowed")
                            and (artifact.get("source_chain") or {}).get("can_publish")
                        )
                    )
                )
            ),
            "guided_workflow": workflow,
            "artifact": artifact,
        }

    def describe_task_recovery(self, task_id: str) -> dict[str, Any]:
        task = self.tasks.get(task_id)
        if not task:
            raise KeyError(task_id)

        status = str(task.get("status") or "")
        base = {
            "state": "none",
            "can_resume": False,
            "reason_code": "not_needed",
            "reason": "当前任务不需要恢复",
            "checkpoint": {
                "phase": str(task.get("phase") or task.get("current_phase") or ""),
                "completed_nodes": int(task.get("completed_nodes") or 0),
                "total_nodes": int(task.get("total_nodes") or 0),
                "draft_node_ids": [],
                "failed_node_ids": [],
                "interrupted_node_ids": [],
                "requirements_ready": False,
                "outline_ready": False,
                "teaching_plan_ready": False,
                "completed_knowledge_packages": 0,
                "total_knowledge_packages": 0,
                "workspace_status": None,
                "updated_at": task.get("updated_at"),
            },
        }
        if status == "completed" or self._publication_receipt(task):
            return {
                **base,
                "state": "completed",
                "reason_code": "already_published",
                "reason": "课程已经发布完成，不需要再次执行",
            }
        if status == "conflict":
            return {
                **base,
                "state": "conflict",
                "reason_code": "revision_conflict",
                "reason": "当前课程已经变化，需要先处理内容冲突",
            }

        workspace_id = str(task.get("workspace_id") or "")
        candidate_id = str(task.get("candidate_id") or "")
        workspace: dict[str, Any] = {}
        if workspace_id:
            try:
                workspace = self._generation_workspace_repository.load(workspace_id)
                course_data = self._generation_workspace_repository.load_course(workspace_id)
            except GenerationWorkspaceNotFound:
                return {
                    **base,
                    "state": "unavailable",
                    "reason_code": "workspace_missing",
                    "reason": "生成工作区已丢失，无法安全继续原任务",
                }
        elif candidate_id:
            try:
                candidate = self._version_repository.load_candidate(
                    str(task["course_id"]), candidate_id
                )
            except KeyError:
                return {
                    **base,
                    "state": "unavailable",
                    "reason_code": "candidate_missing",
                    "reason": "课程候选版本已丢失，无法安全继续原任务",
                }
            course_data = candidate.get("course_data")
            if not isinstance(course_data, dict):
                return {
                    **base,
                    "state": "unavailable",
                    "reason_code": "candidate_invalid",
                    "reason": "课程候选版本不完整，无法安全继续原任务",
                }
            workspace = {
                "status": candidate.get("status"),
                "updated_at": candidate.get("updated_at"),
            }
        else:
            return {
                **base,
                "state": "unavailable",
                "reason_code": "checkpoint_not_supported",
                "reason": "该旧任务没有独立检查点，无法安全继续",
            }

        nodes = [
            node for node in course_data.get("nodes") or []
            if int(node.get("node_level") or 1) == 2
        ]
        draft_node_ids = [
            str(node.get("node_id") or "") for node in nodes
            if str(node.get("node_content_draft") or "").strip()
            and not self._is_content_complete(node)
        ]
        failed_node_ids = [
            str(node.get("node_id") or "") for node in nodes
            if node.get("generation_status") == NodeStatus.ERROR.value
            and not self._is_content_complete(node)
        ]
        interrupted_node_ids = [
            str(node.get("node_id") or "") for node in nodes
            if node.get("generation_status") == NodeStatus.GENERATING.value
            and not self._is_content_complete(node)
        ]
        completed_nodes = sum(1 for node in nodes if self._is_content_complete(node))
        stage_artifacts = course_data.get("generation_stage_artifacts") or {}
        package_states = stage_artifacts.get("section_knowledge") or {}
        course_teaching_stage = (
            stage_artifacts.get("course_teaching_plan") or {}
        )
        teaching_plan_batches = (
            course_teaching_stage.get("batches") or {}
            if isinstance(course_teaching_stage, dict)
            else {}
        )
        completed_teaching_plan_batches = sum(
            1
            for item in teaching_plan_batches.values()
            if isinstance(item, dict) and item.get("status") == "completed"
        )
        total_teaching_plan_batches = int(
            course_teaching_stage.get("batch_count") or 0
        )
        completed_teaching_plan_sections = int(
            course_teaching_stage.get("completed_section_count") or 0
        )
        total_teaching_plan_sections = int(
            course_teaching_stage.get("section_count") or len(nodes)
        )
        failed_teaching_plan_batch_id = str(
            course_teaching_stage.get("failed_batch_id") or ""
        )
        next_teaching_plan_batch_index = next(
            (
                index
                for index in range(1, total_teaching_plan_batches + 1)
                if not isinstance(
                    teaching_plan_batches.get(f"TP-B{index:02d}"), dict
                )
                or teaching_plan_batches[f"TP-B{index:02d}"].get("status")
                != "completed"
            ),
            0,
        )
        knowledge_index_stage = (
            stage_artifacts.get("course_knowledge_index") or {}
        )
        completed_knowledge_packages = (
            len(nodes)
            if (
                course_teaching_stage.get("status") == "completed"
                or knowledge_index_stage.get("status") == "completed"
            )
            else sum(
                1 for item in package_states.values()
                if isinstance(item, dict)
                and item.get("status") == "completed"
            )
        )
        relation_stage = stage_artifacts.get("course_relations") or {}
        relation_batches = relation_stage.get("batches") or {}
        course_graph_stage = stage_artifacts.get("course_graph") or {}
        completed_relation_batches = (
            1
            if course_graph_stage.get("status") == "completed"
            else sum(
                1
                for item in relation_batches.values()
                if isinstance(item, dict)
                and item.get("status") == "completed"
            )
        )
        requirements_ready = bool(
            course_data.get("course_generation_brief")
            and course_data.get("subject_pedagogy_profile")
        )
        checkpoint = {
            "phase": str(task.get("phase") or task.get("current_phase") or ""),
            "completed_nodes": completed_nodes,
            "total_nodes": len(nodes),
            "draft_node_ids": draft_node_ids,
            "failed_node_ids": failed_node_ids,
            "interrupted_node_ids": interrupted_node_ids,
            "requirements_ready": requirements_ready,
            "outline_ready": bool(course_data.get("course_outline")),
            "teaching_plan_ready": bool(
                course_teaching_stage.get("status") == "completed"
            ),
            "teaching_plan_mode": course_teaching_stage.get("planning_mode"),
            "completed_teaching_plan_batches": completed_teaching_plan_batches,
            "total_teaching_plan_batches": total_teaching_plan_batches,
            "completed_teaching_plan_sections": completed_teaching_plan_sections,
            "total_teaching_plan_sections": total_teaching_plan_sections,
            "failed_teaching_plan_batch_id": (
                failed_teaching_plan_batch_id or None
            ),
            "next_teaching_plan_batch_index": next_teaching_plan_batch_index,
            "completed_knowledge_packages": completed_knowledge_packages,
            "total_knowledge_packages": len(nodes),
            "completed_relation_batches": completed_relation_batches,
            "total_relation_batches": (
                0
                if course_teaching_stage.get("status") == "completed"
                else 1
                if knowledge_index_stage
                else len(nodes)
            ),
            "knowledge_registry_revision_id": (
                course_graph_stage.get(
                    "knowledge_identity_revision_id"
                )
                or relation_stage.get(
                    "knowledge_registry_revision_id"
                )
            ),
            "workspace_status": workspace.get("status"),
            "updated_at": workspace.get("updated_at") or task.get("updated_at"),
        }
        if workspace.get("status") == "published":
            return {
                **base,
                "state": "completed",
                "reason_code": "already_published",
                "reason": "课程已经发布完成，不需要再次执行",
                "checkpoint": checkpoint,
            }
        if status in {"pending", "running"} and task.get("last_recovery_reason") in {
            "service_restart",
            "manual_resume",
        }:
            return {
                **base,
                "state": "auto_resuming",
                "reason_code": "job_recovering",
                "reason": "任务正在从最近保存点继续",
                "checkpoint": checkpoint,
            }
        if status in {"pending", "running"}:
            return {**base, "checkpoint": checkpoint}
        if status == "completed_with_warnings" and (
            task.get("phase") == "quality_failed"
            or workspace.get("status") == "quality_failed"
        ):
            return {
                **base,
                "state": "quality_blocked",
                "reason_code": "quality_gate_failed",
                "reason": "内容已经生成，但结构或引用检查未通过；重复运行不会绕过同一错误",
                "checkpoint": checkpoint,
            }
        if status in {"paused", "failed", "completed_with_warnings"}:
            if completed_nodes or draft_node_ids:
                reason = "已保留完成内容和中断草稿，可以从保存点继续"
            elif course_teaching_stage.get("status") == "completed":
                reason = (
                    "全课小节教案、知识库与图谱已经保留，"
                    "可以从未完成正文继续"
                )
            elif completed_teaching_plan_batches:
                reason = (
                    f"已保留 {completed_teaching_plan_sections}/"
                    f"{total_teaching_plan_sections} 个小节教案，可以从第 "
                    f"{next_teaching_plan_batch_index or completed_teaching_plan_batches + 1} "
                    "批教案继续；正文尚未开始"
                )
            elif completed_relation_batches:
                if course_graph_stage.get("status") == "completed":
                    reason = "整课知识关系图已保留，可以从未完成正文继续"
                else:
                    reason = (
                        "已冻结全部知识节点，并保留 "
                        f"{completed_relation_batches}/{len(nodes)} 个旧版关系检查点，"
                        "可以从下一个未完成检查点继续"
                    )
            elif completed_knowledge_packages:
                if knowledge_index_stage.get("status") == "completed":
                    reason = (
                        "课程目录与旧版整课知识索引已保留，"
                        "继续后将迁移为同源小节教案与课程知识库"
                    )
                else:
                    reason = (
                        f"已保留课程目录和 {completed_knowledge_packages}/{len(nodes)} "
                        "个旧版知识检查点，可以从下一个未完成检查点继续"
                    )
            elif course_data.get("course_outline"):
                reason = "已保留课程目录，可以从全课小节教案阶段继续"
            elif requirements_ready:
                reason = "已保留课程需求与资料处理结果；继续后将重新生成课程目录"
            else:
                reason = "尚未生成课程内容；继续后将重试当前阶段"
            return {
                **base,
                "state": "manual_resume",
                "can_resume": True,
                "reason_code": (
                    "checkpoint_available"
                    if course_data.get("course_outline") or nodes
                    else "stage_restart_available"
                ),
                "reason": reason,
                "checkpoint": checkpoint,
            }
        return {**base, "checkpoint": checkpoint}

    def _task_view(self, task: dict[str, Any]) -> dict[str, Any]:
        view = deepcopy(task)
        view["recovery"] = self.describe_task_recovery(str(task["id"]))
        return view

    def _publication_receipt(self, task: dict[str, Any]) -> dict[str, Any] | None:
        if not task.get("workspace_id"):
            return None
        try:
            return self._course_document_repository.receipt_for_command(
                str(task["course_id"]),
                f"publish-generation:{task['id']}",
            )
        except (CourseDocumentNotFound, CourseDocumentConflict):
            return None

    async def _reset_interrupted_task_nodes(
        self,
        task_id: str,
        *,
        include_errors: bool,
    ) -> list[str]:
        recovered: list[str] = []

        def update(course_data: dict[str, Any]) -> dict[str, Any]:
            for node in course_data.get("nodes") or []:
                if int(node.get("node_level") or 1) != 2 or self._is_content_complete(node):
                    continue
                status = node.get("generation_status")
                if status == NodeStatus.GENERATING.value or (
                    include_errors and status == NodeStatus.ERROR.value
                ):
                    node_id = str(node.get("node_id") or "")
                    if node.get("error_summary"):
                        node["recovery_error_summary"] = node["error_summary"]
                    node["generation_status"] = NodeStatus.PENDING.value
                    node.pop("error_summary", None)
                    recovered.append(node_id)
            return course_data

        task = self.tasks.get(task_id) or {}
        workspace_id = str(task.get("workspace_id") or "")
        if workspace_id:
            self._generation_workspace_repository.update_course(workspace_id, update)
        else:
            course_data = self._load_task_course(task_id)
            if course_data is None:
                return []
            await self._save_task_course(task_id, update(course_data))
        return recovered

    async def _reconcile_task_after_restart(self, task_id: str) -> bool:
        task = self.tasks.get(task_id)
        if not task:
            return False
        if task.get("type") != "course_generation":
            return False
        if (
            task.get("status") == "completed_with_warnings"
            and task.get("phase") == "quality_failed"
        ):
            course_data = self._load_task_course(task_id) or {}
            quality_report = build_final_course_quality_report(course_data, job_id=task_id)
            if self._quality_allows_publication(course_data, quality_report):
                logger.info("Re-evaluating publishable quality warning task %s", task_id)
                await self._complete_task(task_id, course_data)
            return False
        if task.get("status") not in {"pending", "running"}:
            return False

        recovery = self.describe_task_recovery(task_id)
        if recovery.get("state") == "completed":
            receipt = self._publication_receipt(task) or {}
            task["status"] = "completed"
            task["phase"] = "completed"
            task["current_phase"] = "completed"
            task["progress"] = 100
            task["phase_progress"] = 100
            task["message"] = "课程已发布，任务状态已恢复"
            task["current_nodes"] = []
            task["current_node_name"] = ""
            task["course_version_id"] = receipt.get("document_revision") or task.get("course_version_id")
            task["updated_at"] = datetime.now().isoformat()
            return False
        if recovery.get("state") == "unavailable":
            task["status"] = "failed"
            task["phase"] = "recovery_unavailable"
            task["current_phase"] = "recovery_unavailable"
            task["message"] = str(recovery.get("reason") or "任务无法恢复")
            task["error"] = task["message"]
            task["current_nodes"] = []
            task["current_node_name"] = ""
            task["updated_at"] = datetime.now().isoformat()
            return False

        workspace_id = str(task.get("workspace_id") or "")
        if workspace_id:
            try:
                await self._course_document_repository.update_generation_state(
                    str(task["course_id"]),
                    job_id=task_id,
                    status="resuming",
                )
            except (CourseDocumentNotFound, CourseDocumentConflict):
                task["status"] = "failed"
                task["phase"] = "recovery_unavailable"
                task["current_phase"] = "recovery_unavailable"
                task["message"] = "课程生成外壳不可用，无法安全恢复"
                task["error"] = task["message"]
                task["updated_at"] = datetime.now().isoformat()
                return False

        await self._reset_interrupted_task_nodes(task_id, include_errors=False)
        if workspace_id:
            self._generation_workspace_repository.record_recovery(
                workspace_id,
                reason="service_restart",
                automatic=True,
            )

        task["status"] = "pending"
        task["message"] = "服务重启后正从最近保存点恢复"
        task["current_nodes"] = []
        task["current_node_name"] = ""
        task["restart_recovery_count"] = int(task.get("restart_recovery_count") or 0) + 1
        task["last_recovery_reason"] = "service_restart"
        task["updated_at"] = datetime.now().isoformat()
        self._node_retries[task_id] = {}
        return True

    async def pause_task(self, task_id: str) -> None:
        """Pause a job and cancel its active model calls after saving drafts."""
        task = self.tasks.get(task_id)
        if not task:
            raise KeyError(task_id)
        if task.get("status") not in {"pending", "running"}:
            raise TaskStateConflict(
                "Task cannot be paused in its current state",
                status=str(task.get("status") or "unknown"),
            )
        async with self._lock:
            current = self.tasks.get(task_id)
            if not current:
                raise KeyError(task_id)
            if current.get("status") not in {"pending", "running"}:
                raise TaskStateConflict(
                    "Task cannot be paused in its current state",
                    status=str(current.get("status") or "unknown"),
                )
            current["status"] = "paused"
            current["message"] = "已暂停"
            current["updated_at"] = datetime.now().isoformat()
            self.save_tasks()
        await self._cancel_runtime_tasks(task_id)
        await self._push_progress(task_id)

    async def resume_task(self, task_id: str) -> dict[str, Any]:
        """Resume one durable generation job from its existing checkpoint."""
        task = self.tasks.get(task_id)
        if not task:
            raise KeyError(task_id)

        recovery = self.describe_task_recovery(task_id)
        if task.get("status") in {"pending", "running"}:
            return {"status": "already_active", "task": self._task_view(task)}
        if recovery.get("state") == "completed":
            return {"status": "completed", "task": self._task_view(task)}
        if not recovery.get("can_resume"):
            raise TaskRecoveryConflict(
                str(recovery.get("reason") or "当前任务无法从原检查点继续"),
                recovery=recovery,
            )

        async with self._lock:
            if task.get("status") in {"pending", "running"}:
                return {"status": "already_active", "task": self._task_view(task)}
            task["status"] = "pending"
            task["phase"] = "resuming"
            task["current_phase"] = "resuming"
            task["message"] = "正在确认保存点并恢复任务"
            task["updated_at"] = datetime.now().isoformat()
            self.save_tasks()

        workspace_id = str(task.get("workspace_id") or "")
        try:
            if workspace_id:
                await self._course_document_repository.update_generation_state(
                    str(task["course_id"]),
                    job_id=task_id,
                    status="resuming",
                )
            await self._reset_interrupted_task_nodes(task_id, include_errors=True)
            if workspace_id:
                self._generation_workspace_repository.record_recovery(
                    workspace_id,
                    reason="manual_resume",
                    automatic=False,
                )
        except (CourseDocumentNotFound, CourseDocumentConflict) as exc:
            unavailable = {
                **recovery,
                "state": "unavailable",
                "can_resume": False,
                "reason_code": "generation_shell_unavailable",
                "reason": "课程生成外壳不可用，无法安全继续原任务",
            }
            async with self._lock:
                task["status"] = "failed"
                task["phase"] = "recovery_unavailable"
                task["current_phase"] = "recovery_unavailable"
                task["message"] = unavailable["reason"]
                task["error"] = unavailable["reason"]
                task["updated_at"] = datetime.now().isoformat()
                self.save_tasks()
            raise TaskRecoveryConflict(str(unavailable["reason"]), recovery=unavailable) from exc
        except Exception:
            async with self._lock:
                task["status"] = "failed"
                task["phase"] = "recovery_failed"
                task["current_phase"] = "recovery_failed"
                task["message"] = "恢复检查点时发生错误，原内容未被重新生成"
                task["error"] = task["message"]
                task["updated_at"] = datetime.now().isoformat()
                self.save_tasks()
            raise

        course_data = self._load_task_course(task_id) or {}
        knowledge_ready = (
            course_data.get("course_knowledge_base") or {}
        ).get("lifecycle_status") == "active"
        has_outline = bool(course_data.get("course_outline"))
        recovery_checkpoint = recovery.get("checkpoint") or {}
        has_content_checkpoint = bool(
            recovery_checkpoint.get("completed_nodes")
            or recovery_checkpoint.get("draft_node_ids")
        )
        phase = (
            "content_generation"
            if knowledge_ready or has_content_checkpoint
            else "course_teaching_plan"
            if has_outline
            else "requirement_analysis"
        )
        progress_cap = 50 if knowledge_ready or has_content_checkpoint else 35 if has_outline else 0
        async with self._lock:
            task["status"] = "pending"
            task["phase"] = phase
            task["current_phase"] = phase
            task["progress"] = min(int(task.get("progress") or 0), progress_cap)
            task["phase_progress"] = 0
            task["message"] = "已从保存点恢复，等待继续"
            task["error"] = None
            task["current_nodes"] = []
            task["current_node_name"] = ""
            task["recovery_count"] = int(task.get("recovery_count") or 0) + 1
            task["last_recovery_reason"] = "manual_resume"
            task["updated_at"] = datetime.now().isoformat()
            self._node_retries[task_id] = {}
            self.save_tasks()
        await self._task_queue.put(task_id)
        await self._push_progress(task_id)
        return {"status": "resumed", "task": self._task_view(task)}

    async def delete_task(self, task_id: str) -> None:
        """Cancel one job, wait for writes to stop, then remove task-owned artifacts."""
        task = self.tasks.get(task_id)
        if not task:
            raise KeyError(task_id)
        task_snapshot = deepcopy(task)
        async with self._lock:
            current = self.tasks.get(task_id)
            if not current:
                raise KeyError(task_id)
            if current.get("status") in {
                "pending", "running", "paused", "waiting_for_review",
            }:
                current["status"] = "cancelled"
                current["phase"] = "cancelled"
                current["current_phase"] = "cancelled"
                current["message"] = "任务已取消，正在清理生成状态"
                current["updated_at"] = datetime.now().isoformat()
                self.save_tasks(strict=True)
        await self._cancel_runtime_tasks(task_id)
        await self._cleanup_task_artifacts(task_snapshot)
        async with self._lock:
            self.tasks.pop(task_id, None)
            self._task_logs.pop(task_id, None)
            self._node_retries.pop(task_id, None)
            self._running_node_tasks.pop(task_id, None)
            self._running_job_tasks.pop(task_id, None)
            self.save_tasks(strict=True)

    async def clear_failed_tasks(self) -> int:
        """清理失败任务，返回清理数量。"""
        failed_ids = [
            task_id for task_id, task in self.tasks.items()
            if task.get("status") == "failed"
        ]
        removed = 0
        for task_id in failed_ids:
            try:
                await self.delete_task(task_id)
                removed += 1
            except KeyError:
                continue
        return removed

    async def delete_tasks_for_course(self, course_id: str) -> int:
        task_ids = [
            task_id for task_id, task in self.tasks.items()
            if task.get("course_id") == course_id
        ]
        removed = 0
        for task_id in task_ids:
            try:
                await self.delete_task(task_id)
                removed += 1
            except KeyError:
                continue
        return removed

    async def delete_course(self, course_id: str) -> int:
        """Stop every related job before deleting the formal course and sidecars."""
        removed = await self.delete_tasks_for_course(course_id)
        await self._delete_stored_course(course_id)
        self._version_repository.delete_course(course_id)
        self._learning_asset_repository.delete_course(course_id)
        self._question_bank_repository.delete_course(course_id)
        self._reset_course_service_runtime(course_id, preserve_course=False)
        return removed

    async def _cancel_runtime_tasks(self, task_id: str) -> None:
        current = asyncio.current_task()
        running_tasks: list[asyncio.Task[Any]] = []
        running_tasks.extend(self._running_node_tasks.get(task_id, {}).values())
        job = self._running_job_tasks.get(task_id)
        if job:
            running_tasks.append(job)
        unique = [
            item for index, item in enumerate(running_tasks)
            if item is not current and item not in running_tasks[:index]
        ]
        for item in unique:
            if not item.done():
                item.cancel()
        if unique:
            await asyncio.gather(*unique, return_exceptions=True)

    async def _cleanup_task_artifacts(self, task: dict[str, Any]) -> None:
        task_id = str(task.get("id") or "")
        course_id = str(task.get("course_id") or "")
        candidate_id = str(task.get("candidate_id") or "")
        candidate_bundle_id = ""
        if candidate_id:
            try:
                candidate = self._version_repository.load_candidate(course_id, candidate_id)
                candidate_bundle_id = str(
                    (candidate.get("course_data") or {}).get("learning_asset_bundle_revision_id") or ""
                )
            except KeyError:
                pass
            self._version_repository.delete_candidate(course_id, candidate_id)
            if candidate_bundle_id:
                self._learning_asset_repository.delete_bundle(course_id, candidate_bundle_id)

        workspace_id = str(task.get("workspace_id") or "")
        if workspace_id:
            self._generation_workspace_repository.delete(workspace_id)

        raw = self.storage.load_course(course_id) if self.storage and course_id else None
        publication = (raw or {}).get("course_document_publication") if isinstance(raw, dict) else None
        owns_unpublished_shell = bool(
            isinstance(raw, dict)
            and task.get("type") == "course_generation"
            and str(task.get("operation") or "generate") == "generate"
            and raw.get("generation_job_id") == task_id
            and not publication
            and raw.get("generation_status") != "passed"
        )
        if owns_unpublished_shell:
            await self._delete_stored_course(course_id)
            self._version_repository.delete_course(course_id)
            self._learning_asset_repository.delete_course(course_id)
            self._question_bank_repository.delete_course(course_id)
            self._reset_course_service_runtime(course_id, preserve_course=False)
        else:
            self._reset_course_service_runtime(course_id, preserve_course=True)

    async def _delete_stored_course(self, course_id: str) -> None:
        delete = getattr(self.storage, "delete_course", None)
        if not callable(delete):
            return
        if inspect.iscoroutinefunction(delete):
            await delete(course_id)
            return
        result = await asyncio.to_thread(delete, course_id)
        if inspect.isawaitable(result):
            await result

    def _reset_course_service_runtime(self, course_id: str, *, preserve_course: bool) -> None:
        if not self.course_service or not course_id:
            return
        clear = getattr(self.course_service, "clear_generation_state", None)
        if callable(clear):
            clear(course_id)
        if preserve_course:
            raw = self.storage.load_course(course_id) if self.storage else None
            register = getattr(self.course_service, "register_course_generation_metadata", None)
            if isinstance(raw, dict) and raw and callable(register):
                register(course_id, raw)

    # -------------------------------------------------------------------------
    # Single-node control: skip, retry, stop, retry_all_failed
    # -------------------------------------------------------------------------

    async def skip_node(self, task_id: str, node_id: str) -> None:
        """跳过指定节点，将其标记为 skipped 状态。

        **Validates: Requirements 7.1**

        Args:
            task_id: 任务 ID
            node_id: 节点 ID
        """
        task = self.tasks.get(task_id)
        if not task:
            logger.warning("skip_node: task %s not found", task_id)
            return

        course_data = self._load_task_course(task_id)
        if not course_data:
            return

        for node in course_data.get("nodes", []):
            if node.get("node_id") == node_id:
                node["generation_status"] = NodeStatus.SKIPPED.value
                break

        await self._save_task_course(task_id, course_data)

        # Cancel running task for this node if any
        node_tasks = self._running_node_tasks.get(task_id, {})
        running = node_tasks.pop(node_id, None)
        if running and not running.done():
            running.cancel()

        self._add_log_entry(
            task_id, node_id,
            node_name=self._find_node_name(course_data, node_id),
            event="skip", message=f"Node {node_id} skipped by user",
        )
        await self._update_progress(task_id, course_data)
        logger.info("Skipped node %s in task %s", node_id, task_id)

    async def retry_node(self, task_id: str, node_id: str) -> None:
        """重试指定节点（error 或 completed 状态）。

        **Validates: Requirements 7.2**

        若任务当前处于终态（completed/completed_with_warnings/failed），会将
        任务状态转回 running，并在重试节点处理完毕后重新执行质检/发布流程
        （复用 ``_complete_task``），确保 generation_quality_report、
        publication_allowed 以及已发布文档与重试后的实际内容保持一致。

        若任务当前正处于 running 状态（已有其它生成/重试在进行），拒绝本次
        重试请求，避免并发重试同一任务。

        Args:
            task_id: 任务 ID
            node_id: 节点 ID
        """
        task = self.tasks.get(task_id)
        if not task:
            logger.warning("retry_node: task %s not found", task_id)
            return

        if task.get("status") == "running":
            raise TaskStateConflict(
                "Task is already being processed; cannot start a new retry",
                status=str(task.get("status") or "running"),
            )

        course_data = self._load_task_course(task_id)
        if not course_data:
            return

        target_node: dict[str, Any] | None = None
        for node in course_data.get("nodes", []):
            if node.get("node_id") == node_id:
                node["generation_status"] = NodeStatus.PENDING.value
                node["error_summary"] = None
                target_node = node
                break

        if not target_node:
            logger.warning("retry_node: node %s not found", node_id)
            return

        await self._save_task_course(task_id, course_data)

        # Reset retry count for this node
        retries = self._node_retries.setdefault(task_id, {})
        retries[node_id] = 0

        self._add_log_entry(
            task_id, node_id,
            node_name=target_node.get("node_name", ""),
            event="retry", message=f"Node {node_id} retry requested by user",
        )

        # The task may already be in a terminal state (completed / completed_with_warnings
        # / failed). Transition it back to running so the task status reflects that content
        # is being silently rewritten in the background, instead of staying on a stale value.
        await self._update_task_status(
            task_id, "running", message=f"正在重试节点 {node_id}..."
        )

        async def _run_and_finalize() -> None:
            try:
                await self._process_node(task_id, target_node)
            finally:
                self._running_node_tasks.get(task_id, {}).pop(node_id, None)
            # Recompute quality/publication and settle the task's final status
            # against the actually-retried content, reusing the same logic used
            # for the initial generation run.
            fresh_course = self._load_task_course(task_id)
            if fresh_course is not None:
                await self._complete_task(task_id, fresh_course)

        node_task = asyncio.create_task(_run_and_finalize())
        self._running_node_tasks.setdefault(task_id, {})[node_id] = node_task
        logger.info("Retry scheduled for node %s in task %s", node_id, task_id)

    async def stop_node(self, task_id: str, node_id: str) -> None:
        """停止正在生成的节点，保留已生成内容。

        **Validates: Requirements 7.5**

        Args:
            task_id: 任务 ID
            node_id: 节点 ID
        """
        node_tasks = self._running_node_tasks.get(task_id, {})
        running = node_tasks.pop(node_id, None)
        if running and not running.done():
            running.cancel()
            logger.info("Stopped generation for node %s in task %s", node_id, task_id)

        # Mark node as completed with partial content
        task = self.tasks.get(task_id)
        if task:
            course_data = self._load_task_course(task_id)
            if course_data:
                for node in course_data.get("nodes", []):
                    if node.get("node_id") == node_id:
                        # Keep whatever content was generated
                        if node.get("generation_status") == NodeStatus.GENERATING.value:
                            node["generation_status"] = NodeStatus.COMPLETED.value
                        break
                await self._save_task_course(task_id, course_data)

        self._add_log_entry(
            task_id, node_id,
            node_name="",
            event="complete",
            message=f"Node {node_id} stopped by user, partial content retained",
        )

    async def retry_all_failed(self, task_id: str) -> None:
        """批量重试所有失败节点。

        **Validates: Requirements 13.3**

        与 ``retry_node`` 一致：若任务处于终态会先转回 running；若任务正在
        running（已有其它生成/重试在进行）则拒绝本次请求；重试完成后复用
        ``_complete_task`` 重新执行质检/发布，确保质量报告与已发布文档与
        重试后的实际内容保持一致。

        Args:
            task_id: 任务 ID
        """
        task = self.tasks.get(task_id)
        if not task:
            logger.warning("retry_all_failed: task %s not found", task_id)
            return

        if task.get("status") == "running":
            raise TaskStateConflict(
                "Task is already being processed; cannot start a new retry",
                status=str(task.get("status") or "running"),
            )

        course_data = self._load_task_course(task_id)
        if not course_data:
            return

        failed_nodes: list[dict[str, Any]] = []
        for node in course_data.get("nodes", []):
            if node.get("generation_status") == NodeStatus.ERROR.value:
                node["generation_status"] = NodeStatus.PENDING.value
                node["error_summary"] = None
                failed_nodes.append(node)

        if not failed_nodes:
            logger.info("retry_all_failed: no failed nodes in task %s", task_id)
            return

        await self._save_task_course(task_id, course_data)

        # Reset retry counts
        retries = self._node_retries.setdefault(task_id, {})
        for node in failed_nodes:
            retries[node["node_id"]] = 0

        logger.info(
            "Retrying %d failed nodes in task %s", len(failed_nodes), task_id
        )

        # The task may already be in a terminal state (completed / completed_with_warnings
        # / failed). Transition it back to running so the task status reflects that content
        # is being silently rewritten in the background, instead of staying on a stale value.
        await self._update_task_status(
            task_id, "running", message="正在重试失败节点..."
        )

        # Schedule all failed nodes and wait for them to finish.
        await self._schedule_nodes(task_id, failed_nodes)

        # Recompute quality/publication and settle the task's final status against
        # the actually-retried content, reusing the same logic used for the initial
        # generation run.
        fresh_course = self._load_task_course(task_id)
        if fresh_course is not None:
            await self._complete_task(task_id, fresh_course)
    # Consumer loop & scheduling
    # -------------------------------------------------------------------------

    async def _consumer_loop(self) -> None:
        """消费者循环，从 asyncio.Queue 取任务执行。

        **Validates: Requirements 3.1, 10.1, 10.2**
        """
        logger.info("Consumer loop started")
        try:
            while self._running:
                try:
                    task_id = await asyncio.wait_for(
                        self._task_queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                task = self.tasks.get(task_id)
                if not task or task["status"] not in ("pending", "running"):
                    continue

                running = self._running_job_tasks.get(task_id)
                if running and not running.done():
                    continue
                job = asyncio.create_task(self._run_job(task_id))
                self._running_job_tasks[task_id] = job
        except asyncio.CancelledError:
            logger.info("Consumer loop cancelled")

    async def _run_job(self, task_id: str) -> None:
        try:
            async with self._course_semaphore:
                await self._process_task(task_id)
        except asyncio.CancelledError:
            task = self.tasks.get(task_id)
            if task and task.get("status") not in ("paused", "cancelled"):
                await self._update_task_status(task_id, "pending", message="任务中断，等待恢复")
            raise
        except Exception as exc:
            logger.error("Error processing task %s: %s", task_id, exc, exc_info=True)
            await self._update_task_status(task_id, "failed", error=str(exc))
            await self._record_workspace_failure(task_id, str(exc))
        finally:
            self._running_job_tasks.pop(task_id, None)

    async def _schedule_nodes(
        self, task_id: str, nodes: list[dict]
    ) -> None:
        """按依赖波次调度节点生成。

        有前置依赖的节点等待依赖完成；无依赖或依赖已满足的节点保持并发。

        **Validates: Requirements 3.3, 3.4**

        Args:
            task_id: 任务 ID
            nodes: 待调度的节点列表
        """
        sorted_nodes = sorted(
            nodes, key=lambda n: (n.get("node_level", 1), nodes.index(n))
        )

        pending = list(sorted_nodes)
        completed = {
            n.get("node_id", "")
            for n in sorted_nodes
            if self._is_content_complete(n)
        }
        # Nodes that failed (or were skipped because a prerequisite failed) —
        # tracked separately from `completed` so downstream nodes can tell the
        # difference between "dependency satisfied" and "dependency gave up".
        unusable: set[str] = set()
        known_ids = {n.get("node_id", "") for n in sorted_nodes}

        task = self.tasks.get(task_id)
        course_id = task.get("course_id", "") if task else ""

        while pending:
            ready = [
                node for node in pending
                if self._node_dependencies(node, known_ids).issubset(completed | unusable)
            ]
            if not ready:
                # Invalid model-produced dependency graph: preserve progress in original order.
                ready = [pending[0]]

            # A node whose prerequisites include a failed/skipped node is blocked:
            # generating it would silently proceed with missing prerequisite content.
            # Mark it as errored instead of generating.
            blocked = [
                node for node in ready
                if self._node_dependencies(node, known_ids) & unusable
            ]
            runnable = [node for node in ready if node not in blocked]

            for node in blocked:
                node_id = node.get("node_id", "")
                await self._set_node_status(
                    task_id, course_id, node_id, NodeStatus.ERROR,
                    error_summary="前置节点生成失败或被跳过，已阻断本节点生成",
                )
                self._add_log_entry(
                    task_id, node_id,
                    node_name=node.get("node_name", ""),
                    event="error",
                    message=f"Node {node_id} blocked: prerequisite node(s) failed",
                )

            tasks: list[asyncio.Task[Any]] = []
            for node in runnable:
                node_id = node.get("node_id", "")
                task_obj = asyncio.create_task(self._process_node(task_id, node))
                self._running_node_tasks.setdefault(task_id, {})[node_id] = task_obj
                tasks.append(task_obj)

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            fresh_course = self._load_task_course(task_id)
            fresh_by_id = {
                n.get("node_id", ""): n
                for n in (fresh_course.get("nodes", []) if fresh_course else [])
            }
            for node in ready:
                node_id = node.get("node_id", "")
                if node in blocked:
                    unusable.add(node_id)
                else:
                    fresh_node = fresh_by_id.get(node_id, node)
                    status = fresh_node.get("generation_status")
                    if status in (NodeStatus.COMPLETED.value, NodeStatus.SKIPPED.value):
                        completed.add(node_id)
                    else:
                        unusable.add(node_id)
                pending.remove(node)

    def _node_dependencies(self, node: dict, known_ids: set[str]) -> set[str]:
        """返回当前待生成集合里的有效前置依赖"""
        raw = node.get("prerequisite_node_ids") or []
        if not isinstance(raw, list):
            return set()
        return {dep for dep in raw if isinstance(dep, str) and dep in known_ids}

    async def _prepare_subject_knowledge(
        self,
        task_id: str,
        course_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Compile the course-owned knowledge blueprint before content generation.

        The historical method name is retained for checkpoint compatibility.
        Knowledge identity is compiled only from this course.
        """
        working = deepcopy(course_data)
        await self._update_phase(
            task_id,
            "course_knowledge_blueprint",
            46,
            "正在编译已冻结的知识节点、能力包与稳定 ID",
            phase_progress=35,
        )
        course_map = compile_course_knowledge_map(working)
        course_knowledge_base = compile_course_knowledge_base(
            working,
            course_map=course_map,
            assets=working.get("learning_assets") or {},
        )
        course_map = bind_course_knowledge_base_to_map(
            course_map,
            course_knowledge_base,
        )
        working["course_knowledge_map"] = course_map
        working["course_knowledge_base"] = course_knowledge_base
        working["course_knowledge_quality_report"] = course_knowledge_base.get(
            "quality_report"
        )
        blueprint = working.get("course_blueprint")
        if isinstance(blueprint, dict):
            blueprint.pop("reference_catalog_revision_id", None)
            blueprint["course_knowledge_base_revision_id"] = course_knowledge_base.get(
                "revision_id"
            )
        await self._update_phase(
            task_id,
            "knowledge_mapping",
            49,
            "正在检查稳定知识 ID 与精确教学绑定",
            phase_progress=100,
            phase_detail={
                "course_knowledge_base_revision_id": course_knowledge_base.get(
                    "revision_id"
                ),
                "lifecycle_status": course_knowledge_base.get("lifecycle_status"),
                "quality_report": course_knowledge_base.get("quality_report"),
                "reference_catalog_required": False,
                "knowledge_identity_scope": "current_course_only",
            },
        )
        return working

    @staticmethod
    def _require_course_knowledge_ready(course_data: dict[str, Any]) -> None:
        knowledge_base = course_data.get("course_knowledge_base") or {}
        if knowledge_base.get("lifecycle_status") == "active":
            return
        report = knowledge_base.get("quality_report") or {}
        messages = [
            str(item.get("message") or "")
            for item in report.get("blocking_issues") or report.get("issues") or []
            if str(item.get("message") or "").strip()
        ]
        detail = "；".join(messages[:6]) or "课程知识库缺失或结构不完整"
        raise RuntimeError(f"正文生成已停止：{detail}")

    async def _pause_for_guided_review(
        self,
        task_id: str,
        course_data: dict[str, Any],
        step: str,
        *,
        phase: str,
        progress: int,
        message: str,
        revision: str | None = None,
        phase_detail: dict[str, Any] | None = None,
    ) -> None:
        task = self.tasks.get(task_id)
        if not task or not isinstance(task.get("guided_workflow"), dict):
            return
        artifact_id = revision or guided_artifact_revision(
            step,
            course_data,
            request=task.get("request_snapshot") or {},
        )
        async with self._lock:
            mark_guided_step_waiting(
                task["guided_workflow"],
                step,
                revision=artifact_id,
            )
            task["updated_at"] = datetime.now().isoformat()
            self.save_tasks()
        await self._save_task_course(task_id, course_data)
        await self._update_phase(
            task_id,
            phase,
            progress,
            message,
            phase_progress=100,
            phase_detail={
                "artifact_type": step,
                "artifact_revision": artifact_id,
                **(phase_detail or {}),
            },
        )
        await self._update_task_status(
            task_id,
            "waiting_for_review",
            message=message,
        )
        await self._push_progress(task_id)

    async def _process_task(self, task_id: str) -> None:
        """处理单个任务：分析课程结构并调度节点。

        Args:
            task_id: 任务 ID
        """
        task = self.tasks.get(task_id)
        if not task:
            return

        if task["status"] == "paused":
            return

        course_id = task["course_id"]
        await self._update_task_status(task_id, "running", message="正在处理...")

        course_data = self._load_task_course(task_id)
        if not course_data:
            await self._update_task_status(
                task_id, "failed", error="Course not found"
            )
            return

        request = task.get("request_snapshot") or course_data.get("generation_request") or {}
        guided_workflow = task.get("guided_workflow")
        guided = isinstance(guided_workflow, dict)
        if guided and not guided_workflow.get("review_step"):
            current_guided_step = str(
                guided_workflow.get("current_step") or "outline"
            )
            mark_guided_step_running(guided_workflow, current_guided_step)
            async with self._lock:
                task["updated_at"] = datetime.now().isoformat()
                self.save_tasks()
        request_mode = str(request.get("generation_mode") or "review_blueprint")
        review_pending = (
            guided and not guided_step_confirmed(guided_workflow, "outline")
        ) or (
            not guided
            and request_mode == "review_blueprint"
            and not task.get("blueprint_confirmed")
        )
        knowledge_base = course_data.get("course_knowledge_base") or {}
        pipeline_ready = bool(
            course_data.get("course_blueprint")
            and knowledge_base.get("lifecycle_status") == "active"
        )
        if task.get("type") == "course_generation" and not pipeline_ready:

            async def on_phase(
                phase: str,
                progress: int,
                message: str,
                phase_progress: int,
                phase_detail: dict[str, Any],
            ) -> None:
                await self._update_phase(
                    task_id,
                    phase,
                    progress,
                    message,
                    phase_progress=phase_progress,
                    phase_detail=phase_detail,
                )

            async def on_checkpoint(checkpoint: dict[str, Any]) -> None:
                fresh = self._load_task_course(task_id) or course_data
                fresh.update(checkpoint)
                await self._save_task_course(task_id, fresh)

            stop_after_outline = bool(
                review_pending and not course_data.get("course_outline")
            )
            course_data = await self.course_service.build_course_draft(
                course_id=course_id,
                topic=str(request.get("subject") or course_data.get("course_name") or ""),
                target_audience=str(request.get("target_audience") or "大学生"),
                depth=str(request.get("difficulty") or "intermediate"),
                style=request.get("style"),
                composition_style=request.get("composition_style"),
                requirements=str(request.get("requirements") or ""),
                materials=request.get("materials") or [],
                material_bindings=request.get("material_bindings") or [],
                grounding_strategy=str(request.get("grounding_strategy") or "material_first"),
                learner_profile_summary=str(request.get("learner_profile_summary") or ""),
                current_readiness=request.get("current_readiness"),
                adaptation_preference=str(
                    request.get("adaptation_preference") or "preserve_target_extend"
                ),
                pedagogy_mode=str(request.get("pedagogy_mode") or "auto"),
                secondary_mode=request.get("secondary_mode"),
                secondary_intensity=request.get("secondary_intensity"),
                generation_mode=str(request.get("generation_mode") or "fast"),
                course_purpose=str(request.get("course_purpose") or "systematic"),
                asset_preferences=request.get("asset_preferences") or {},
                web_question_enrichment=request.get("web_question_enrichment") or {"enabled": False},
                existing_course_data=course_data,
                stop_after_outline=stop_after_outline,
                on_phase=on_phase,
                on_checkpoint=on_checkpoint,
            )
            if stop_after_outline:
                draft = build_blueprint_draft(course_data)
                impact = analyze_blueprint_impact(course_data, draft)
                draft["impact_report"] = impact
                self._version_repository.save_draft(course_id, draft)
                outline_actual = (
                    course_data.get("course_outline_constraint_report") or {}
                ).get("actual") or {}
                course_data["generation_status"] = "outline_ready"
                await self._save_task_course(task_id, course_data)
                if guided:
                    await self._pause_for_guided_review(
                        task_id,
                        course_data,
                        "outline",
                        phase="outline_ready",
                        progress=35,
                        message="课程目录等待确认；确认后将规划全课小节教案并生成正文",
                        revision=guided_artifact_revision(
                            "outline",
                            course_data,
                            request=task.get("request_snapshot") or {},
                        ),
                        phase_detail={
                            "completed_items": int(outline_actual.get("section_count") or 0),
                            "total_items": int(outline_actual.get("section_count") or 0),
                        },
                    )
                    return
                await self._update_phase(
                    task_id,
                    "outline_ready",
                    35,
                    "轻量课程目录等待确认",
                    phase_progress=100,
                    phase_detail={
                        "artifact_type": "course_outline",
                        "blueprint_revision_id": impact.get("draft_blueprint_revision_id"),
                        "completed_items": int(outline_actual.get("section_count") or 0),
                        "total_items": int(outline_actual.get("section_count") or 0),
                    },
                )
                await self._update_task_status(
                    task_id,
                    "waiting_for_review",
                    message="课程目录等待确认；确认后将规划全课小节教案并生成正文",
                    completed_nodes=0,
                    total_nodes=int(outline_actual.get("section_count") or 0),
                )
                await self._push_progress(task_id)
                return
            if (
                course_data.get("course_knowledge_base") or {}
            ).get("lifecycle_status") != "active":
                course_data = await self._prepare_subject_knowledge(task_id, course_data)
            self._require_course_knowledge_ready(course_data)
            frozen = self._version_repository.freeze_blueprint(course_id, course_data)
            course_data["blueprint_revision_id"] = frozen["blueprint_revision_id"]
            task["blueprint_revision_id"] = frozen["blueprint_revision_id"]
            await self._save_task_course(task_id, course_data)

        if task.get("type") == "course_generation" and not review_pending:
            if not course_data.get("course_knowledge_base"):
                course_data = await self._prepare_subject_knowledge(task_id, course_data)
                await self._save_task_course(task_id, course_data)
            self._require_course_knowledge_ready(course_data)

        if task.get("type") == "course_generation":
            teaching_stage = (
                course_data.get("generation_stage_artifacts") or {}
            ).get("course_teaching_plan") or {}
            teaching_ready = bool(
                teaching_stage.get("status") == "completed"
                and all(
                    node.get("module_plan")
                    for node in course_data.get("nodes") or []
                    if int(node.get("node_level") or 1) == 2
                )
            )
            if not teaching_ready and hasattr(
                self.course_service,
                "compile_teaching_plan",
            ):
                # Only persisted pre-v9 checkpoints reach this deterministic
                # adapter. New jobs already contain the one-call plan.
                course_data = self.course_service.compile_teaching_plan(course_data)
                await self._save_task_course(task_id, course_data)
            if not course_data.get("learning_asset_plan"):
                course_data["learning_asset_plan"] = compile_learning_asset_plan(course_data)
                if isinstance(course_data.get("course_blueprint"), dict):
                    course_data["course_blueprint"]["learning_asset_plan"] = course_data["learning_asset_plan"]
                await self._save_task_course(task_id, course_data)
            course_data["generation_status"] = "content_generation"
            await self._save_task_course(task_id, course_data)

        if task.get("status") == "paused":
            return
        if hasattr(self.course_service, "register_course_generation_metadata"):
            self.course_service.register_course_generation_metadata(course_id, course_data)
            # 读取适配器可能为旧课程补齐难度契约，立即持久化以供恢复和最终质检使用。
            await self._save_task_course(task_id, course_data)

        nodes = course_data.get("nodes", [])
        l2_nodes = [n for n in nodes if n.get("node_level", 1) == 2]

        # The V2 blueprint already owns the complete L1/L2 structure.
        incomplete_l2 = [n for n in l2_nodes if not self._is_content_complete(n)]
        if incomplete_l2:
            total = len(l2_nodes)
            completed = len(l2_nodes) - len(incomplete_l2)
            await self._update_task_status(
                task_id,
                "running",
                message="正在根据小节教案并行生成正文",
                completed_nodes=completed,
                total_nodes=total,
            )
            await self._update_phase(
                task_id,
                "content_generation",
                max(55, task.get("progress", 55)),
                "正在根据小节教案并行生成正文",
                phase_progress=int(
                    completed / max(1, total) * 100
                ),
                phase_detail={
                    "artifact_type": "course_content",
                    "completed_items": completed,
                    "total_items": total,
                    "teaching_plan_status": "completed",
                    "knowledge_compilation": "deterministic_completed",
                    "graph_compilation": "deterministic_completed",
                },
            )
            await self._schedule_nodes(task_id, incomplete_l2)

        course_data = self._load_task_course(task_id) or course_data
        if guided and not guided_step_confirmed(guided_workflow, "content"):
            l2_nodes = [
                node
                for node in course_data.get("nodes") or []
                if int(node.get("node_level") or 1) == 2
            ]
            (
                course_data,
                _quality_report,
                _failed_nodes,
                _strict_quality_passed,
                _publication_allowed,
            ) = await self._prepare_content_candidate(task_id, course_data)
            content_revision = guided_artifact_revision(
                "content",
                course_data,
                request=task.get("request_snapshot") or {},
            )
            async with self._lock:
                mark_guided_step_waiting(
                    guided_workflow,
                    "content",
                    revision=content_revision,
                )
                confirm_waiting_step(
                    guided_workflow,
                    "content",
                    revision=content_revision,
                )
                task["phase"] = "content_confirmed"
                task["current_phase"] = "content_confirmed"
                task["phase_progress"] = 100
                task["message"] = "课程正文已完成，正在准备最终发布确认"
                task["updated_at"] = datetime.now().isoformat()
                self.save_tasks()
            await self._save_task_course(task_id, course_data)
            await self._push_progress(task_id)
        await self._complete_task(task_id, course_data)

    async def _save_generated_node_content(
        self,
        task_id: str,
        course_id: str,
        node_id: str,
        fixed_content: str,
        generated_chars: int,
        grounding_annotations: list[dict[str, Any]] | None = None,
        grounding_invalid_refs: list[str] | None = None,
        generation_quality: dict[str, Any] | None = None,
        needs_manual_review: bool = False,
    ) -> dict[str, Any] | None:
        def update(fresh_data: dict[str, Any]) -> dict[str, Any]:
            for node in fresh_data.get("nodes", []):
                if node.get("node_id") == node_id:
                    set_node_content_blocks(node, fixed_content)
                    node["generation_status"] = NodeStatus.COMPLETED.value
                    node["generated_chars"] = generated_chars
                    node["grounding_annotations"] = grounding_annotations or []
                    node["grounding_invalid_refs"] = grounding_invalid_refs or []
                    node["error_summary"] = None
                    node.pop("node_content_draft", None)
                    # Persist deterministic diagnostics without starting a
                    # second model scoring/repair chain.
                    node["generation_quality"] = (
                        generation_quality
                        if generation_quality is not None
                        else evaluate_node_content(fixed_content, node)
                    )
                    node["needs_manual_review"] = bool(
                        needs_manual_review
                    )
                    break
            return fresh_data

        return await self._mutate_task_course(task_id, update)

    async def _save_node_draft(
        self, task_id: str, course_id: str, node_id: str, content: str
    ) -> None:
        if not content:
            return
        def update(fresh_data: dict[str, Any]) -> dict[str, Any]:
            for item in fresh_data.get("nodes", []):
                if item.get("node_id") == node_id:
                    item["node_content_draft"] = content
                    item["generation_status"] = NodeStatus.PENDING.value
                    break
            return fresh_data

        await self._mutate_task_course(task_id, update)

    async def _publish_node_completion(
        self,
        course_id: str,
        task_id: str,
        node: dict,
        fixed_content: str,
        generated_chars: int,
        content_blocks: list[dict[str, Any]] | None = None,
    ) -> None:
        if not self.ws_service:
            return

        node_id = node.get("node_id", "")
        node_name = node.get("node_name", "")
        payload = {
            "task_id": task_id,
            "node_id": node_id,
            "node_name": node_name,
            "node_content": fixed_content,
            "content_blocks": list(content_blocks or []),
            "generated_chars": generated_chars,
        }
        if hasattr(self.ws_service, "push_node_finalized"):
            await self.ws_service.push_node_finalized(
                course_id,
                {**payload, "phase": "final"},
            )
        await self.ws_service.push_node_completed(course_id, payload)

    async def _process_node(self, task_id: str, node: dict) -> None:
        """处理单个节点，包含重试和错误恢复。

        使用 asyncio.Semaphore 控制并发，指数退避重试。

        **Validates: Requirements 3.2, 3.5, 13.1, 13.4**

        Args:
            task_id: 任务 ID
            node: 节点字典
        """
        node_id = node.get("node_id", "")
        node_name = node.get("node_name", "")
        task = self.tasks.get(task_id)
        if not task:
            return

        course_id = task["course_id"]
        retries = self._node_retries.setdefault(task_id, {})
        retry_count = retries.get(node_id, 0)

        async with self._semaphore:
            if not self._running or task.get("status") == "paused":
                return

            start_time = datetime.now()

            async with self._lock:
                node_info = {
                    "node_id": node_id,
                    "node_name": node_name,
                    "action": "生成中",
                    "type": "content" if node.get("node_level", 1) == 2 else "structure",
                    "generated_chars": 0,
                }
                current_nodes = task.get("current_nodes", [])
                current_nodes.append(node_info)
                task["current_nodes"] = current_nodes
                if current_nodes:
                    task["current_node_name"] = current_nodes[0].get("node_name", "")
                self.save_tasks()

            self._add_log_entry(
                task_id, node_id, node_name=node_name,
                event="start", message=f"Starting generation for {node_name}",
            )

            await self._push_progress(task_id)

            try:
                await self._set_node_status(
                    task_id, course_id, node_id, NodeStatus.GENERATING
                )

                while retry_count <= MAX_RETRIES:
                    try:
                        config = self._build_node_config(node)

                        accumulated: list[str] = []
                        streamed_chars = 0
                        last_progress_push = time.monotonic()
                        last_checkpoint = time.monotonic()
                        fresh_course = self._load_task_course(task_id) or {}
                        fresh_node = next(
                            (item for item in fresh_course.get("nodes", []) if item.get("node_id") == node_id),
                            node,
                        )
                        existing_draft = str(fresh_node.get("node_content_draft") or "")

                        async def on_chunk(chunk: str) -> None:
                            nonlocal streamed_chars, last_progress_push, last_checkpoint
                            accumulated.append(chunk)
                            streamed_chars += len(chunk)
                            if self.ws_service:
                                await self.ws_service.push_stream_chunk(
                                    course_id, node_id, chunk
                                )
                            now = time.monotonic()
                            if now - last_progress_push >= STREAM_PROGRESS_INTERVAL_SECONDS:
                                await self._mark_node_streaming(
                                    task_id, node_id, streamed_chars
                                )
                                await self._push_progress(task_id)
                                last_progress_push = now
                            if now - last_checkpoint >= DRAFT_CHECKPOINT_INTERVAL_SECONDS:
                                await self._save_node_draft(
                                    task_id, course_id, node_id, existing_draft + "".join(accumulated)
                                )
                                last_checkpoint = now

                        content = await self.course_service.generate_node_content_stream(
                            course_id=course_id,
                            node=node,
                            config=config,
                            on_chunk=on_chunk,
                            course_data=fresh_course,
                            existing_draft=existing_draft,
                        )

                        end_time = datetime.now()
                        duration_ms = (end_time - start_time).total_seconds() * 1000
                        
                        fixed_content = fix_latex_content(content)
                        generated_chars = len(fixed_content) if fixed_content else 0

                        fresh_data = await self._save_generated_node_content(
                            task_id,
                            course_id,
                            node_id,
                            fixed_content,
                            generated_chars,
                            grounding_annotations=node.get("grounding_annotations") or [],
                            grounding_invalid_refs=node.get("grounding_invalid_refs") or [],
                            generation_quality=node.get("generation_quality"),
                            needs_manual_review=bool(node.get("needs_manual_review")),
                        )

                        self._add_log_entry(
                            task_id, node_id, node_name=node_name,
                            event="complete",
                            message=f"Completed {node_name} ({generated_chars} chars)",
                            retry_count=retry_count,
                            generated_chars=generated_chars,
                            duration_ms=duration_ms,
                        )

                        await self._publish_node_completion(
                            course_id,
                            task_id,
                            node,
                            fixed_content,
                            generated_chars,
                            content_blocks=(next(
                                (
                                    item.get("content_blocks") or []
                                    for item in (fresh_data or {}).get("nodes", [])
                                    if item.get("node_id") == node_id
                                ),
                                [],
                            )),
                        )

                        await self._update_progress(task_id, fresh_data)
                        await self._push_progress(task_id)

                        return

                    except asyncio.CancelledError:
                        draft = existing_draft + "".join(accumulated)
                        await asyncio.shield(self._save_node_draft(task_id, course_id, node_id, draft))
                        logger.info("Node %s generation cancelled", node_id)
                        raise

                    except Exception as e:
                        non_retryable = getattr(e, "retryable", True) is False
                        retry_count = MAX_RETRIES + 1 if non_retryable else retry_count + 1
                        retries[node_id] = retry_count
                        error_msg = str(e)

                        if not non_retryable and retry_count <= MAX_RETRIES:
                            delay = min(
                                (2 ** retry_count) * BACKOFF_BASE, BACKOFF_MAX
                            )
                            self._add_log_entry(
                                task_id, node_id, node_name=node_name,
                                event="retry",
                                message=f"Retry {retry_count}/{MAX_RETRIES}: {error_msg[:100]}",
                                retry_count=retry_count,
                            )
                            logger.warning(
                                "Node %s failed (retry %d/%d), backoff %.1fs: %s",
                                node_id, retry_count, MAX_RETRIES, delay, error_msg[:100],
                            )
                            await asyncio.sleep(delay)
                        else:
                            end_time = datetime.now()
                            duration_ms = (end_time - start_time).total_seconds() * 1000

                            await self._set_node_status(
                                task_id, course_id, node_id, NodeStatus.ERROR,
                                error_summary=error_msg[:200],
                            )

                            self._add_log_entry(
                                task_id, node_id, node_name=node_name,
                                event="error",
                                message=(
                                    f"Non-retryable failure: {error_msg[:200]}"
                                    if non_retryable
                                    else f"Failed after {MAX_RETRIES} retries: {error_msg[:200]}"
                                ),
                                retry_count=retry_count,
                                duration_ms=duration_ms,
                            )

                            if self.ws_service:
                                await self.ws_service.push_error(
                                    course_id,
                                    {
                                        "task_id": task_id,
                                        "node_id": node_id,
                                        "node_name": node_name,
                                        "error": error_msg[:200],
                                        "retry_count": retry_count,
                                    },
                                )

                            await self._push_progress(task_id)
                            return

            finally:
                async with self._lock:
                    current_nodes = task.get("current_nodes", [])
                    task["current_nodes"] = [
                        n for n in current_nodes if n.get("node_id") != node_id
                    ]
                    if task["current_nodes"]:
                        task["current_node_name"] = task["current_nodes"][0].get("node_name", "")
                    else:
                        task["current_node_name"] = ""
                    self.save_tasks()
                await self._update_progress(task_id)
                await self._push_progress(task_id)

        node_tasks = self._running_node_tasks.get(task_id, {})
        node_tasks.pop(node_id, None)

    # -------------------------------------------------------------------------
    # Command handler (for WebSocketService integration)
    # -------------------------------------------------------------------------

    async def handle_command(self, cmd_type: str, data: dict) -> None:
        """Handle commands from WebSocketService.

        This method is passed as the command_handler callback to WebSocketService.

        Args:
            cmd_type: Command type string
            data: Command data dict with course_id, node_id, payload
        """
        course_id = data.get("course_id", "")
        node_id = data.get("node_id", "")
        payload = data.get("payload") or {}

        # Find the active task for this course
        task_id = self._find_active_task(course_id)
        if not task_id:
            logger.warning(
                "handle_command: no active task for course %s", course_id
            )
            return

        if cmd_type == "skip_node":
            await self.skip_node(task_id, node_id)
        elif cmd_type == "retry_node":
            await self.retry_node(task_id, node_id)
        elif cmd_type == "stop_node":
            await self.stop_node(task_id, node_id)
        elif cmd_type == "retry_all_failed":
            await self.retry_all_failed(task_id)
        elif cmd_type == "custom_instruction":
            # Store custom instruction on the node config
            instruction = payload.get("instruction", "")
            await self._set_custom_instruction(task_id, node_id, instruction)
        else:
            logger.warning("handle_command: unknown command %s", cmd_type)

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    def load_tasks(self) -> None:
        """从文件加载任务。"""
        source = TASKS_FILE
        if (
            not source.exists()
            and TASKS_FILE == DEFAULT_TASKS_FILE
            and LEGACY_TASKS_FILE.exists()
        ):
            source = LEGACY_TASKS_FILE
        try:
            if not source.exists():
                self.tasks = {}
                return
            with source.open(encoding="utf-8") as handle:
                loaded = json.load(handle)
            if not isinstance(loaded, dict):
                raise ValueError("Generation job index must contain an object")
            self.tasks = loaded
            for task_id, task in self.tasks.items():
                task.setdefault("id", task_id)
                task.setdefault("type", "legacy_content_generation")
                task.setdefault("phase", "content_generation")
                task.setdefault("phase_progress", 0)
                task.setdefault("phase_detail", {})
                task.setdefault("request_snapshot", {})
                task.setdefault("node_drafts", {})
                task.setdefault("operation", "generate")
                task.setdefault("candidate_id", None)
                task.setdefault("base_version_id", None)
                task.setdefault("blueprint_confirmed", False)
                task.setdefault("blueprint_revision_id", None)
                task.setdefault("workspace_id", None)
                task.setdefault("base_document_revision", None)
                workflow = task.get("guided_workflow")
                if isinstance(workflow, dict):
                    legacy_review = str(
                        workflow.get("review_step") or ""
                    )
                    task["guided_workflow"] = migrate_guided_workflow(
                        workflow,
                        request=task.get("request_snapshot") or {},
                    )
                    if (
                        legacy_review in {"knowledge", "teaching"}
                        and task.get("status") == "waiting_for_review"
                    ):
                        task["status"] = "pending"
                        task["phase"] = "course_teaching_plan_migrated"
                        task["message"] = (
                            "旧知识或教学确认点已合并，正在按新链路继续生成课程"
                        )
                if task.get("type") != "course_generation":
                    task["legacy_read_only"] = True
                    if task.get("status") in ("pending", "running", "paused"):
                        task["status"] = "completed"
                        task["phase"] = "legacy_read_only"
                        task["message"] = "旧版任务仅供历史查看"
            if source == LEGACY_TASKS_FILE:
                self.save_tasks(strict=True)
        except Exception as e:
            logger.error("Failed to load tasks: %s", e)
            self.tasks = {}

    def save_tasks(self, *, strict: bool = False) -> None:
        """Atomically persist jobs to the deployment-persistent data root."""
        try:
            TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
            temp_path = TASKS_FILE.with_suffix(".tmp")
            with temp_path.open("w", encoding="utf-8") as handle:
                json.dump(self.tasks, handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, TASKS_FILE)
        except Exception as e:
            logger.error("Failed to save tasks: %s", e)
            if strict:
                raise

    @staticmethod
    def _quality_allows_publication(
        course_data: dict[str, Any],
        quality_report: dict[str, Any],
    ) -> bool:
        """Separate strict quality scoring from the minimum publishability gate."""
        # Demo recordings: RELEASE_QUALITY_GATE=advisory downgrades the asset
        # quality gate to warnings so a generated course can actually reach
        # release; the quality report itself stays attached and truthful.
        # Nodes that failed generation outright still block publication.
        advisory = os.getenv(
            "RELEASE_QUALITY_GATE", ""
        ).strip().lower() == "advisory"
        if any(
            node.get("generation_status") == NodeStatus.ERROR.value
            for node in course_data.get("nodes") or []
        ):
            return False
        asset_report = (
            course_data.get("asset_quality_report")
            or quality_report.get("asset_quality")
            or {}
        )
        if asset_report and not asset_report.get("passed", False):
            if not advisory:
                return False
        if advisory:
            return True
        explicit = quality_report.get("publication_allowed")
        if explicit is not None:
            return bool(explicit)
        return quality_report.get("final_status") == "passed"

    async def _save_course(self, course_id: str, course_data: dict[str, Any]) -> None:
        load_course = getattr(self.storage, "load_course", None)
        current = load_course(course_id) if callable(load_course) else None
        if isinstance(current, dict) and current.get("course_schema_version") == "course_document_v1":
            raise RuntimeError(
                "Canonical course documents cannot be overwritten by the legacy generation saver"
            )
        result = self.storage.save_course(course_id, course_data)
        if inspect.isawaitable(result):
            await result

    def _load_task_course(self, task_id: str) -> dict[str, Any] | None:
        """Load the isolated course workspace owned by one generation job."""
        task = self.tasks.get(task_id)
        if not task:
            return None
        workspace_id = task.get("workspace_id")
        if workspace_id:
            try:
                return self._generation_workspace_repository.load_course(str(workspace_id))
            except GenerationWorkspaceNotFound:
                return None
        candidate_id = task.get("candidate_id")
        if candidate_id:
            try:
                candidate = self._version_repository.load_candidate(
                    str(task["course_id"]), str(candidate_id)
                )
            except KeyError:
                return None
            course_data = candidate.get("course_data")
            return course_data if isinstance(course_data, dict) else None
        return self.storage.load_course(str(task["course_id"]))

    async def _save_task_course(
        self, task_id: str, course_data: dict[str, Any]
    ) -> None:
        """Persist to a candidate workspace without mutating the current course."""
        task = self.tasks.get(task_id)
        if not task:
            return
        course_id = str(task["course_id"])
        workspace_id = task.get("workspace_id")
        if workspace_id:
            self._generation_workspace_repository.save_course(str(workspace_id), course_data)
            return
        candidate_id = task.get("candidate_id")
        if not candidate_id:
            await self._save_course(course_id, course_data)
            return
        candidate = self._version_repository.load_candidate(
            course_id, str(candidate_id)
        )
        candidate["course_data"] = course_data
        candidate["status"] = (
            "running" if task.get("status") in {"pending", "running"}
            else candidate.get("status", "pending")
        )
        candidate["updated_at"] = datetime.now().isoformat()
        self._version_repository.save_candidate(
            course_id, str(candidate_id), candidate
        )

    # -------------------------------------------------------------------------
    # Task logging
    # -------------------------------------------------------------------------

    def _add_log_entry(
        self,
        task_id: str,
        node_id: str,
        node_name: str = "",
        event: str = "start",
        message: str = "",
        retry_count: int = 0,
        generated_chars: int = 0,
        duration_ms: float = 0.0,
    ) -> None:
        """添加任务执行日志条目。

        **Validates: Requirements 13.5**

        Args:
            task_id: 任务 ID
            node_id: 节点 ID
            node_name: 节点名称
            event: 事件类型
            message: 日志消息
            retry_count: 重试次数
            generated_chars: 生成字符数
            duration_ms: 耗时（毫秒）
        """
        entry = TaskLogEntry(
            timestamp=datetime.now(),
            node_id=node_id,
            node_name=node_name,
            event=event,
            message=message,
            retry_count=retry_count,
            generated_chars=generated_chars,
            duration_ms=duration_ms if duration_ms else None,
        )
        self._task_logs.setdefault(task_id, []).append(entry)

        # Also add to the task dict for backward compat
        task = self.tasks.get(task_id)
        if task:
            if "logs" not in task:
                task["logs"] = []
            timestamp = datetime.now().strftime("%H:%M:%S")
            task["logs"].append(f"[{timestamp}] {message}")
            if len(task["logs"]) > 50:
                task["logs"] = task["logs"][-50:]

    def _get_task_log(self, task_id: str) -> list[TaskLogEntry]:
        """获取任务执行日志。

        Args:
            task_id: 任务 ID

        Returns:
            TaskLogEntry 列表
        """
        return self._task_logs.get(task_id, [])

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    async def _update_phase(
        self,
        task_id: str,
        phase: str,
        progress: int,
        message: str,
        *,
        phase_progress: int | None = None,
        phase_detail: dict[str, Any] | None = None,
    ) -> None:
        """Persist one backend-owned generation phase and broadcast it."""
        async with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return
            bounded_progress = max(0, min(int(progress), 100))
            task["phase"] = phase
            task["current_phase"] = phase
            task["phase_progress"] = max(
                0,
                min(int(phase_progress if phase_progress is not None else bounded_progress), 100),
            )
            task["phase_detail"] = phase_detail or {}
            task["progress"] = max(int(task.get("progress") or 0), bounded_progress)
            task["message"] = message
            task["updated_at"] = datetime.now().isoformat()
            self.save_tasks()
        await self._push_progress(task_id)

    async def _update_task_status(
        self,
        task_id: str,
        status: str,
        message: str | None = None,
        error: str | None = None,
        completed_nodes: int | None = None,
        total_nodes: int | None = None,
    ) -> None:
        """更新任务状态。"""
        async with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return
            task["status"] = status
            if message is not None:
                task["message"] = message
            if error is not None:
                task["error"] = error
            if completed_nodes is not None:
                task["completed_nodes"] = completed_nodes
            if total_nodes is not None:
                task["total_nodes"] = total_nodes
            task["updated_at"] = datetime.now().isoformat()
            self.save_tasks()

    async def _update_progress(
        self, task_id: str, course_data: dict | None = None
    ) -> None:
        """Recalculate and update task progress from course data.

        **Validates: Requirements 8.4**
        """
        task = self.tasks.get(task_id)
        if not task:
            return

        if course_data is None:
            course_data = self._load_task_course(task_id)
        if not course_data:
            return

        nodes = course_data.get("nodes", [])
        l1_nodes = [n for n in nodes if n.get("node_level", 1) == 1]
        l2_nodes = [n for n in nodes if n.get("node_level", 1) == 2]

        completed_l2 = sum(
            1 for n in l2_nodes if self._is_content_complete(n)
            or n.get("generation_status") in (
                NodeStatus.COMPLETED.value, NodeStatus.SKIPPED.value
            )
        )
        if task.get("type") == "course_generation":
            total = len(l2_nodes)
            completed = completed_l2
            content_progress = int(completed / max(1, total) * 40) if total else 0
            progress = 50 + content_progress
        else:
            total = len(l1_nodes) + len(l2_nodes)
            completed = len(l1_nodes) + completed_l2
            progress = int(completed / max(1, total) * 100) if total > 0 else 0

        async with self._lock:
            task["completed_nodes"] = completed
            task["total_nodes"] = total
            if task.get("type") == "course_generation" and task.get("phase") == "content_generation":
                task["phase_progress"] = int(completed / max(1, total) * 100) if total else 0
            task["progress"] = max(
                int(task.get("progress") or 0),
                min(progress, 90 if task.get("type") == "course_generation" else 100),
            )
            task["updated_at"] = datetime.now().isoformat()
            self.save_tasks()

    async def _push_progress(self, task_id: str) -> None:
        """Push progress update via WebSocket."""
        task = self.tasks.get(task_id)
        if not task or not self.ws_service:
            return

        course_id = task["course_id"]
        current_nodes = task.get("current_nodes", [])
        completed_nodes = task.get("completed_nodes", 0)
        total_nodes = task.get("total_nodes", 0)
        progress = task.get("progress", 0)
        if current_nodes and total_nodes and progress < 100:
            remaining = max(total_nodes - completed_nodes, 0)
            active_credit = min(len(current_nodes), remaining) * ACTIVE_NODE_PROGRESS_CREDIT
            ratio = (completed_nodes + active_credit) / max(1, total_nodes)
            if task.get("type") == "course_generation":
                visible_progress = 50 + int(ratio * 40)
            else:
                visible_progress = int(ratio * 100)
            progress = max(progress, min(visible_progress, 99))

        await self.ws_service.push_progress_update(
            course_id,
            {
                "task_id": task_id,
                "course_id": course_id,
                "status": task.get("status", ""),
                "phase": task.get("phase", ""),
                "current_phase": task.get("current_phase", ""),
                "phase_progress": task.get("phase_progress", 0),
                "phase_detail": task.get("phase_detail", {}),
                "guided_workflow": deepcopy(task.get("guided_workflow")),
                "message": task.get("message", ""),
                "error": task.get("error"),
                "progress": progress,
                "current_node_name": task.get("current_node_name", ""),
                "current_nodes": current_nodes,
                "completed_nodes": completed_nodes,
                "total_nodes": total_nodes,
                "estimated_time_remaining": 0,
                "bytes_generated": sum(
                    int(node.get("generated_chars") or 0)
                    for node in current_nodes
                ),
            },
        )

    async def _mark_node_streaming(
        self, task_id: str, node_id: str, generated_chars: int
    ) -> None:
        """Record visible streaming work for the active node."""
        async with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return
            for active_node in task.get("current_nodes", []):
                if active_node.get("node_id") == node_id:
                    active_node["generated_chars"] = generated_chars
                    break
            task["updated_at"] = datetime.now().isoformat()
            self.save_tasks()

    async def _prepare_content_candidate(
        self,
        task_id: str,
        course_data: dict,
    ) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], bool, bool]:
        """Finish every content mutation before the user reviews step five."""
        task = self.tasks.get(task_id)
        if not task:
            raise ValueError("Task not found")
        fresh_course = self._load_task_course(task_id) or course_data
        stage_artifacts = fresh_course.setdefault("generation_stage_artifacts", {})
        prepared = stage_artifacts.get("content_candidate") or {}
        if (
            prepared.get("status") == "completed"
            and fresh_course.get("generation_quality_report")
            and fresh_course.get("asset_quality_report")
            and fresh_course.get("learning_asset_bundle_revision_id")
        ):
            quality_report = fresh_course["generation_quality_report"]
            failed_nodes = [
                node
                for node in fresh_course.get("nodes") or []
                if node.get("generation_status") == NodeStatus.ERROR.value
            ]
            strict_quality_passed = (
                quality_report.get("final_status") == "passed"
                and fresh_course["asset_quality_report"].get("passed", False)
                and not failed_nodes
            )
            publication_allowed = bool(
                quality_report.get("publication_allowed")
            )
            return (
                fresh_course,
                quality_report,
                failed_nodes,
                strict_quality_passed,
                publication_allowed,
            )

        for node in fresh_course.get("nodes") or []:
            if (
                int(node.get("node_level") or 1) == 2
                and str(node.get("node_content") or "").strip()
                and not node.get("content_blocks")
            ):
                set_node_content_blocks(node, str(node.get("node_content") or ""))

        coherence_report = evaluate_course_coherence(fresh_course)
        fresh_course["course_coherence_contract"] = compile_course_coherence_contract(
            fresh_course
        )
        fresh_course["course_coherence_quality_report"] = coherence_report
        await self._save_task_course(task_id, fresh_course)

        await self._update_phase(
            task_id,
            "learning_assets",
            87,
            "正在编译课程练习、掌握标准和课程知识映射",
            phase_progress=20,
        )
        asset_course = deepcopy(fresh_course)
        if hasattr(self.course_service, "load_course_evidence_catalog"):
            asset_course["evidence_catalog"] = self.course_service.load_course_evidence_catalog(
                fresh_course
            )
        asset_bundle = compile_learning_assets(asset_course)
        question_bank_bundle = asset_bundle.pop("question_bank_bundle")
        await self._update_phase(
            task_id,
            "question_bank",
            92,
            "正在整理课程题库、覆盖矩阵与风险审核队列",
            phase_progress=55,
        )
        question_bank_bundle = await enrich_question_bank_with_web(
            fresh_course,
            question_bank_bundle,
        )
        previous_question_bank = self._question_bank_repository.load_bundle(
            str(task["course_id"])
        )
        question_bank_bundle = reconcile_question_bank(
            previous_question_bank,
            question_bank_bundle,
        )
        # Recompile from the reconciled source of truth so teacher-reviewed
        # prompts and answer rubrics are the tasks frozen into this asset bundle.
        asset_bundle = compile_learning_assets(
            asset_course,
            question_bank_bundle=question_bank_bundle,
        )
        asset_bundle.pop("question_bank_bundle", None)
        # Learning-asset compilation deterministically assigns the objective
        # identities and course-knowledge bindings used by its own contracts.
        # Persist that exact node projection before evaluating or publishing so
        # the course and its generated assets share one source of truth.
        fresh_course["nodes"] = deepcopy(asset_course.get("nodes") or [])
        fresh_course["question_analysis_required"] = True
        analyzed_questions = [
            item
            for _, item in assessment_assets(asset_bundle["assets"])
        ]
        asset_bundle["quality_report"] = evaluate_learning_asset_quality(
            fresh_course,
            asset_bundle["plan"],
            asset_bundle["assets"],
        )
        fresh_course["question_analysis_status"] = (
            "passed"
            if all(
                (item.get("question_analysis") or {}).get("status")
                == "passed"
                for item in analyzed_questions
            )
            else "blocked"
        )
        fresh_course["question_analysis_summary"] = {
            "source": "compiled_contract",
            "model_call_count": 0,
            "total": len(analyzed_questions),
            "passed": sum(
                (item.get("question_analysis") or {}).get("status")
                == "passed"
                for item in analyzed_questions
            ),
            "blocked": sum(
                (item.get("question_analysis") or {}).get("status")
                == "blocked"
                for item in analyzed_questions
            ),
        }
        question_bank_bundle = self._question_bank_repository.save_bundle(
            str(task["course_id"]),
            question_bank_bundle,
            activate=False,
        )
        asset_bundle = self._learning_asset_repository.save_bundle(
            str(task["course_id"]),
            asset_bundle,
            activate=False,
        )
        fresh_course["learning_asset_plan"] = asset_bundle["plan"]
        fresh_course["learning_assets"] = asset_bundle["assets"]
        fresh_course["learning_asset_bundle_revision_id"] = asset_bundle[
            "bundle_revision_id"
        ]
        fresh_course["asset_quality_report"] = asset_bundle["quality_report"]
        fresh_course["question_bank_bundle_revision_id"] = question_bank_bundle[
            "bundle_revision_id"
        ]
        fresh_course["question_bank_coverage"] = question_bank_bundle["coverage"]
        fresh_course["question_bank_review_queue"] = question_bank_bundle["review_queue"]
        fresh_course["web_question_enrichment"] = question_bank_bundle["web_enrichment"]
        compiled_knowledge_base = next(
            iter(fresh_course["learning_assets"].get("course_knowledge_base") or []),
            None,
        )
        if compiled_knowledge_base:
            fresh_course["course_knowledge_base"] = compiled_knowledge_base
            fresh_course["course_knowledge_quality_report"] = (
                compiled_knowledge_base.get("quality_report")
            )
        compiled_knowledge_map = next(
            iter(fresh_course["learning_assets"].get("course_knowledge_map") or []),
            None,
        )
        if compiled_knowledge_map:
            fresh_course["course_knowledge_map"] = compiled_knowledge_map
        fresh_course["course_coherence_contract"] = compile_course_coherence_contract(
            fresh_course
        )
        fresh_course["course_coherence_quality_report"] = evaluate_course_coherence(
            fresh_course
        )
        await self._save_task_course(task_id, fresh_course)

        await self._update_phase(
            task_id,
            "content_validation",
            88,
            "正在执行课程结构、引用与资产完整性检查",
            phase_progress=60,
        )
        nodes = fresh_course.get("nodes", [])
        failed_nodes = [
            node
            for node in nodes
            if node.get("generation_status") == NodeStatus.ERROR.value
        ]
        quality_report = build_final_course_quality_report(
            fresh_course,
            job_id=task_id,
        )
        quality_report["asset_quality"] = fresh_course["asset_quality_report"]
        if (
            quality_report.get("final_status") == "passed"
            and not fresh_course["asset_quality_report"].get("passed", False)
        ):
            quality_report["final_status"] = "completed_with_warnings"
        publication_allowed = self._quality_allows_publication(
            fresh_course,
            quality_report,
        )
        quality_report["publication_allowed"] = publication_allowed
        fresh_course["generation_quality_report"] = quality_report
        fresh_course["generation_status"] = "content_candidate_ready"
        fresh_course["generation_completed_at"] = datetime.now().isoformat()
        stage_artifacts = fresh_course.setdefault("generation_stage_artifacts", {})
        stage_artifacts["content_candidate"] = {
            "status": "completed",
            "schema_version": "course_content_candidate_v1",
            "learning_asset_bundle_revision_id": fresh_course.get(
                "learning_asset_bundle_revision_id"
            ),
        }
        await self._save_task_course(task_id, fresh_course)
        await self._update_progress(task_id, fresh_course)
        strict_quality_passed = (
            quality_report.get("final_status") == "passed"
            and fresh_course["asset_quality_report"].get("passed", False)
            and not failed_nodes
        )
        return (
            fresh_course,
            quality_report,
            failed_nodes,
            strict_quality_passed,
            publication_allowed,
        )

    async def _complete_task(
        self, task_id: str, course_data: dict
    ) -> None:
        """Mark task as completed and send failure report if needed.

        **Validates: Requirements 13.2**
        """
        task = self.tasks.get(task_id)
        if not task:
            return
        guided_workflow = task.get("guided_workflow")
        content_stage = (
            course_data.get("generation_stage_artifacts") or {}
        ).get("content_candidate") or {}
        confirmed_content_checkpoint = bool(
            isinstance(guided_workflow, dict)
            and guided_step_confirmed(guided_workflow, "content")
            and content_stage.get("status") == "completed"
            and isinstance(
                course_data.get("generation_quality_report"),
                dict,
            )
            and isinstance(course_data.get("asset_quality_report"), dict)
        )
        if confirmed_content_checkpoint:
            # A confirmed content candidate is immutable. Recompiling assets
            # here can create new revisions after the user reviewed them and
            # would both waste work and invalidate the source-chain proof.
            fresh_course = deepcopy(course_data)
            quality_report = deepcopy(
                fresh_course.get("generation_quality_report") or {}
            )
            failed_nodes = [
                node
                for node in fresh_course.get("nodes") or []
                if node.get("generation_status") == NodeStatus.ERROR.value
            ]
            publication_allowed = self._quality_allows_publication(
                fresh_course,
                quality_report,
            )
            strict_quality_passed = bool(
                quality_report.get("final_status") == "passed"
                and (
                    fresh_course.get("asset_quality_report") or {}
                ).get("passed", False)
                and not failed_nodes
            )
        else:
            (
                fresh_course,
                quality_report,
                failed_nodes,
                strict_quality_passed,
                publication_allowed,
            ) = await self._prepare_content_candidate(
                task_id,
                course_data,
            )
        nodes = fresh_course.get("nodes", [])
        await self._update_phase(
            task_id,
            "finalizing",
            98,
            "正在保存最终课程",
            phase_progress=90,
        )

        if isinstance(guided_workflow, dict):
            # The reviewed content candidate stays immutable after step three,
            # while the release gate remains a derived decision over that
            # candidate and the latest confirmed workflow state.
            publication_allowed = self._quality_allows_publication(
                fresh_course,
                quality_report,
            )
            source_chain_report = build_source_chain_report(
                guided_workflow,
                fresh_course,
                request=task.get("request_snapshot") or {},
            )
            fresh_course["generation_source_chain_report"] = source_chain_report
            publication_allowed = bool(
                publication_allowed and source_chain_report.get("can_publish")
            )
            quality_report["publication_allowed"] = publication_allowed
            quality_report["source_chain_passed"] = bool(
                source_chain_report.get("can_publish")
            )
            fresh_course["generation_quality_report"] = quality_report
            await self._save_task_course(task_id, fresh_course)
            if not guided_step_confirmed(guided_workflow, "release"):
                await self._pause_for_guided_review(
                    task_id,
                    fresh_course,
                    "release",
                    phase="release_ready",
                    progress=98,
                    message=(
                        "全部检查通过，等待确认发布"
                        if publication_allowed
                        else "发布检查发现阻断问题，请查看检查结果"
                    ),
                    phase_detail={
                        "publication_allowed": publication_allowed,
                        "source_chain_passed": bool(
                            source_chain_report.get("can_publish")
                        ),
                        "blocking_issue_count": len(
                            quality_report.get("blocking_issues") or []
                        )
                        + len(source_chain_report.get("issues") or []),
                    },
                )
                return

        candidate_id = task.get("candidate_id")
        workspace_id = task.get("workspace_id")
        version_entry: dict[str, Any] | None = None
        promotion_conflict: str | None = None
        if candidate_id:
            candidate = self._version_repository.load_candidate(
                str(task["course_id"]), str(candidate_id)
            )
            if publication_allowed:
                try:
                    promoted, version_entry = self._version_repository.promote_candidate(
                        str(task["course_id"]),
                        str(candidate_id),
                        reason=str((task.get("request_snapshot") or {}).get("reason") or "局部再生成"),
                        operation=str(task.get("operation") or "regenerate"),
                    )
                    promoted["generation_quality_report"] = quality_report
                    promoted["generation_status"] = quality_report["final_status"]
                    self._learning_asset_repository.activate_bundle(
                        str(task["course_id"]),
                        str(promoted.get("learning_asset_bundle_revision_id") or ""),
                    )
                    if promoted.get("question_bank_bundle_revision_id"):
                        self._question_bank_repository.activate_bundle(
                            str(task["course_id"]),
                            str(promoted["question_bank_bundle_revision_id"]),
                        )
                    await self._save_course(str(task["course_id"]), promoted)
                    fresh_course = promoted
                except CourseVersionConflict as exc:
                    promotion_conflict = str(exc)
            else:
                candidate["status"] = "quality_failed"
                candidate["quality_report"] = quality_report
                self._version_repository.save_candidate(
                    str(task["course_id"]), str(candidate_id), candidate
                )
        elif workspace_id:
            if publication_allowed:
                document = document_from_generation_draft(fresh_course)
                self._learning_asset_repository.activate_bundle(
                    str(task["course_id"]),
                    str(fresh_course.get("learning_asset_bundle_revision_id") or ""),
                )
                if fresh_course.get("question_bank_bundle_revision_id"):
                    self._question_bank_repository.activate_bundle(
                        str(task["course_id"]),
                        str(fresh_course["question_bank_bundle_revision_id"]),
                    )
                receipt = await self._course_document_repository.publish_generated_course(
                    str(task["course_id"]),
                    document,
                    job_id=task_id,
                    command_id=f"publish-generation:{task_id}",
                    expected_revision=str(task.get("base_document_revision") or ""),
                    metadata=fresh_course,
                    quality_status=str(quality_report.get("final_status") or "passed"),
                )
                version_entry = {"version_id": receipt["document_revision"]}
                self._generation_workspace_repository.set_status(
                    str(workspace_id),
                    "published",
                    result={
                        "document_revision": receipt["document_revision"],
                        "quality_status": quality_report.get("final_status"),
                    },
                )
                fresh_course = self._course_document_repository.load_course_view(str(task["course_id"]))
            else:
                await self._course_document_repository.update_generation_state(
                    str(task["course_id"]),
                    job_id=task_id,
                    status="completed_with_warnings",
                    quality_report=quality_report,
                )
                self._generation_workspace_repository.set_status(
                    str(workspace_id),
                    "quality_failed",
                    result={"quality_report": quality_report},
                )
        elif publication_allowed and not task.get("course_version_id"):
            current_version_id = self._version_repository.current_version_id(str(task["course_id"]))
            version_entry = self._version_repository.create_version(
                str(task["course_id"]),
                fresh_course,
                reason="完成首次课程生成",
                operation="generate",
                base_version_id=current_version_id,
                changed_node_ids=[
                    str(node.get("node_id") or "") for node in nodes
                ],
            )
            fresh_course["current_course_version_id"] = version_entry["version_id"]
            fresh_course["blueprint_revision_id"] = version_entry["blueprint_revision_id"]
            self._learning_asset_repository.activate_bundle(
                str(task["course_id"]),
                str(fresh_course.get("learning_asset_bundle_revision_id") or ""),
            )
            if fresh_course.get("question_bank_bundle_revision_id"):
                self._question_bank_repository.activate_bundle(
                    str(task["course_id"]),
                    str(fresh_course["question_bank_bundle_revision_id"]),
                )
            await self._save_course(str(task["course_id"]), fresh_course)

        if publication_allowed:
            try:
                published_document, canonical = self._course_document_repository.load_document(
                    str(task["course_id"])
                )
                if canonical:
                    await asyncio.to_thread(
                        compile_core_representations,
                        published_document,
                        self._course_document_repository.load_course_view(str(task["course_id"])),
                        teaching_representation_repository,
                    )
            except Exception as exc:
                logger.warning(
                    "课程已发布，但基础教学表达编译将在后续对账中重试：%s",
                    exc,
                )

        if promotion_conflict:
            await self._update_task_status(
                task_id,
                "conflict",
                message="候选课程基于旧版本，未覆盖当前课程",
                error=promotion_conflict,
            )
        elif failed_nodes:
            # Generate failure report
            course_id = task["course_id"] if task else ""

            report = {
                "task_id": task_id,
                "course_id": course_id,
                "failed_nodes": [
                    {
                        "node_id": n.get("node_id", ""),
                        "node_name": n.get("node_name", ""),
                        "error": n.get("error_summary", "Unknown error"),
                        "retry_count": self._node_retries.get(
                            task_id, {}
                        ).get(n.get("node_id", ""), 0),
                    }
                    for n in failed_nodes
                ],
                "total_failed": len(failed_nodes),
            }

            if self.ws_service:
                await self.ws_service.push_failure_report(course_id, report)

            learning_node_count = len([
                node for node in nodes if int(node.get("node_level") or 1) == 2
            ])
            all_learning_nodes_failed = bool(learning_node_count) and len(failed_nodes) >= learning_node_count
            await self._update_task_status(
                task_id,
                "failed" if all_learning_nodes_failed else "completed_with_warnings",
                message=(
                    "课程生成失败：全部学习节点生成失败"
                    if all_learning_nodes_failed
                    else f"课程部分完成（{len(failed_nodes)} 个节点失败）"
                ),
            )
        elif candidate_id and not publication_allowed:
            await self._update_task_status(
                task_id,
                "completed_with_warnings",
                message="候选课程存在阻断性质量问题，当前版本保持不变",
            )
        elif not publication_allowed:
            await self._update_task_status(
                task_id,
                "completed_with_warnings",
                message="课程存在阻断性质量问题，未发布当前版本",
            )
        elif not strict_quality_passed:
            await self._update_task_status(
                task_id,
                "completed_with_warnings",
                message="课程已生成并发布，仍有非阻断性优化建议",
            )
        else:
            await self._update_task_status(
                task_id, "completed",
                message="课程生成完成",
            )

        task = self.tasks.get(task_id)
        async with self._lock:
            if task:
                task["progress"] = 100
                terminal_phase = "conflict" if promotion_conflict else (
                    "quality_failed" if not publication_allowed else "completed"
                )
                task["phase"] = terminal_phase
                task["current_phase"] = terminal_phase
                task["phase_progress"] = 100
                if version_entry:
                    task["course_version_id"] = version_entry.get("version_id")
                task["quality_status"] = quality_report.get("final_status")
                task["publication_allowed"] = publication_allowed
                task["updated_at"] = datetime.now().isoformat()
            self.save_tasks()

        if task and self.ws_service:
            await self.ws_service.push_task_completed(
                task["course_id"],
                {
                    "task_id": task_id,
                    "status": task.get("status", "completed"),
                    "progress": 100,
                    "completed_nodes": task.get("completed_nodes", 0),
                    "total_nodes": task.get("total_nodes", 0),
                    "phase": task.get("phase", "completed"),
                    "quality_status": quality_report.get("final_status"),
                    "publication_allowed": publication_allowed,
                    "course_version_id": task.get("course_version_id"),
                    "candidate_id": candidate_id,
                },
            )

    async def _set_node_status(
        self,
        task_id: str,
        course_id: str,
        node_id: str,
        status: NodeStatus,
        error_summary: str | None = None,
    ) -> None:
        """Update a node's generation_status in course data."""
        def update(course_data: dict[str, Any]) -> dict[str, Any]:
            for node in course_data.get("nodes", []):
                if node.get("node_id") == node_id:
                    node["generation_status"] = status.value
                    if error_summary is not None:
                        node["error_summary"] = error_summary
                    break
            return course_data

        await self._mutate_task_course(task_id, update)

    async def _set_custom_instruction(
        self, task_id: str, node_id: str, instruction: str
    ) -> None:
        """Store a custom instruction on a node's generation_config."""
        def update(course_data: dict[str, Any]) -> dict[str, Any]:
            for node in course_data.get("nodes", []):
                if node.get("node_id") == node_id:
                    config = node.get("generation_config") or {}
                    config["custom_instruction"] = instruction
                    node["generation_config"] = config
                    break
            return course_data

        await self._mutate_task_course(task_id, update)

    async def _mutate_task_course(
        self,
        task_id: str,
        updater: Callable[[dict[str, Any]], dict[str, Any] | None],
    ) -> dict[str, Any] | None:
        task = self.tasks.get(task_id)
        if not task:
            return None
        workspace_id = task.get("workspace_id")
        if workspace_id:
            return self._generation_workspace_repository.update_course(str(workspace_id), updater)
        course_data = self._load_task_course(task_id)
        if not course_data:
            return None
        updated = updater(course_data)
        if updated is not None:
            course_data = updated
        await self._save_task_course(task_id, course_data)
        return course_data

    async def _record_workspace_failure(self, task_id: str, error: str) -> None:
        task = self.tasks.get(task_id)
        if not task or not task.get("workspace_id"):
            return
        workspace_id = str(task["workspace_id"])
        try:
            workspace = self._generation_workspace_repository.load(workspace_id)
        except GenerationWorkspaceNotFound:
            workspace = None
        if workspace and workspace.get("status") == "published":
            return
        if workspace:
            self._generation_workspace_repository.set_status(
                workspace_id,
                "failed",
                result={"error": error},
            )
        try:
            await self._course_document_repository.update_generation_state(
                str(task["course_id"]),
                job_id=task_id,
                status="failed",
                error=error,
            )
        except (CourseDocumentNotFound, CourseDocumentConflict) as exc:
            logger.warning("Could not record generation shell failure for %s: %s", task_id, exc)

    def _find_active_task(self, course_id: str) -> str | None:
        """Find the most recent active task for a course."""
        candidates = [
            t for t in self.tasks.values()
            if t["course_id"] == course_id
            and t["status"] in ("pending", "running", "waiting_for_review")
        ]
        if candidates:
            candidates.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            return candidates[0]["id"]
        return None

    @staticmethod
    def _find_node_name(course_data: dict, node_id: str) -> str:
        """Find a node's name from course data."""
        for node in course_data.get("nodes", []):
            if node.get("node_id") == node_id:
                return node.get("node_name", "")
        return ""

    @staticmethod
    def _is_content_complete(node: dict) -> bool:
        """检查节点内容是否完整。"""
        content = node.get("node_content", "")
        status = node.get("generation_status", "")
        if status in (NodeStatus.COMPLETED.value, NodeStatus.SKIPPED.value):
            return True
        return len(content) > CONTENT_COMPLETE_THRESHOLD

    @staticmethod
    def _build_node_config(node: dict) -> NodeGenerationConfig:
        """Build NodeGenerationConfig from node dict."""
        config_data = node.get("generation_config") or {}
        kwargs: dict[str, Any] = {}
        if config_data.get("difficulty"):
            kwargs["difficulty"] = config_data["difficulty"]
        if config_data.get("style"):
            kwargs["style"] = config_data["style"]
        if config_data.get("custom_instruction"):
            kwargs["custom_instruction"] = config_data["custom_instruction"]
        if config_data.get("target_word_range"):
            kwargs["target_word_range"] = tuple(config_data["target_word_range"])
        if "include_code_examples" in config_data:
            kwargs["include_code_examples"] = config_data["include_code_examples"]
        if "include_exercises" in config_data:
            kwargs["include_exercises"] = config_data["include_exercises"]
        return NodeGenerationConfig(**kwargs)
