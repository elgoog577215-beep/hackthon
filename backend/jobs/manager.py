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
# 3. 分批生成并确认全课小节教案 → 4. 并行生成正文
# 5. 编译学习资产并执行确定性结构校验 → 6. 保存并推送进度
#
# Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 10.1, 10.2, 10.3, 10.4,
#               6.5, 7.1, 7.2, 7.5, 13.1, 13.2, 13.4, 13.5
# =============================================================================

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import os
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - production runs on Linux.
    fcntl = None

from ai_base import AIProviderRequestError, AIProviderUnavailable
from assessment_blueprint import compile_course_assessment_blueprint
from assessment_contracts import (
    compile_assessment_objectives,
    compile_course_assessment_profile,
)
from assessment_generation_policy import (
    ASSESSMENT_GENERATION_POLICY_VERSION,
    normalize_assessment_generation_profile,
)
from assessment_orchestrator import AssessmentGenerationOrchestrator
from assessment_retrieval import (
    compile_local_reference_package,
    enrich_reference_package_with_web,
)
from content_blocks import set_node_content_blocks
from course_coherence import (
    compile_course_coherence_contract,
    evaluate_course_coherence,
)
from course_composition import compile_composition_profile
from course_difficulty import repair_compiled_difficulty_double_spikes
from course_document import document_from_generation_draft
from course_generation.outline import (
    normalize_outline_skeleton,
    review_course_outline_document,
    validate_outline_skeleton,
)
from course_generation.workflow import PIPELINE_VERSION
from course_generation_budget import (
    CourseGenerationBudget,
    CourseGenerationDeadlineExceeded,
)
from course_generation_errors import classify_generation_failure
from course_knowledge_base import (
    bind_course_knowledge_base_to_map,
    compile_course_knowledge_base,
)
from course_knowledge_map import compile_course_knowledge_map
from course_outline_adjustments import (
    OutlineAdjustmentError,
    apply_outline_operations,
    compile_outline_draft,
    describe_outline_diff,
)
from course_quality import (
    build_final_course_quality_report,
    dedupe_quality_issues,
    evaluate_node_content,
)
from course_repository import (
    CourseDocumentConflict,
    CourseDocumentNotFound,
    CourseDocumentRepository,
)
from course_retrieval import (
    build_course_retrieval_queries,
    build_outline_research_instruction,
    build_outline_research_proposal,
)
from course_space_publication import (
    MISSING_TEACHER_IDENTITY,
    PUBLISH_SCHEMA_VERSION,
    SKIP_MESSAGES,
    publish_course_artifacts,
)
from course_teaching_plan_projection import project_course_teaching_plan
from course_versioning import (
    analyze_blueprint_impact,
    blueprint_draft_revision_id,
    blueprint_revision_id,
    build_blueprint_draft,
    merge_blueprint_draft,
    outline_adjustment_proposal_id,
    stable_hash,
)
from course_versions import (
    CourseVersionConflict,
    CourseVersionRepository,
    course_version_repository,
)
from course_web_research_policy import (
    COURSE_WEB_RESEARCH_ENABLED,
    course_generation_view,
)
from generation_workspace import (
    GenerationWorkspaceNotFound,
    GenerationWorkspaceRepository,
    generation_workspace_repository,
)
from guided_generation import (
    GUIDED_STEP_KEYS,
    build_source_chain_report,
    confirm_waiting_step,
    create_guided_workflow,
    migrate_guided_workflow,
)
from guided_generation import (
    artifact_revision as guided_artifact_revision,
)
from guided_generation import (
    expected_input_revisions as guided_expected_input_revisions,
)
from guided_generation import (
    invalidate_after as invalidate_guided_steps_after,
)
from guided_generation import (
    is_confirmed as guided_step_confirmed,
)
from guided_generation import (
    mark_running as mark_guided_step_running,
)
from guided_generation import (
    mark_waiting as mark_guided_step_waiting,
)
from guided_generation import (
    step_state as guided_step_state,
)
from jobs.content_processing import (
    _remap_assessment_revision_references,  # noqa: F401 - compatibility import
    fix_latex_content,
)
from jobs.node_progress import build_node_locations
from jobs.slide_build import (
    _rebuild_slide_variant_with_quality_fallback,
    _source_first_slide_ai_workers,
    _source_first_slide_visual_ai_worker,
    _source_first_story_ai_worker,
)
from learning_asset_storage import LearningAssetRepository, learning_asset_repository
from learning_assets import (
    assessment_assets,
    compile_learning_asset_plan,
    compile_learning_assets,
    evaluate_learning_asset_quality,
)
from markdown_parser import parse_markdown_to_nodes
from material_pipeline import ingest_legacy_material_inputs
from material_storage import material_repository
from models import (
    NodeGenerationConfig,
    NodeStatus,
    TaskLogEntry,
)
from ppt_template_packs import ppt_template_pack_repository
from question_bank import (
    QuestionBankRepository,
    question_bank_repository,
    reconcile_question_bank,
    reconcile_scoped_question_bank,
)
from representation_compiler import (
    compile_core_representations,
    rebuild_core_representations_safely,
    validate_compiled_representations,
)
from runtime_metrics import (
    record_model_error,
    record_persistence_failure,
    record_recovery_result,
    record_task_wait,
)
from slide_ai_planning_v6 import (
    build_ai_base_story_planner_v6,
    build_ai_base_visual_planner_v2,
)
from slide_deck_v3 import (
    SLIDE_DECK_V3_COMPILER_VERSION,
    SlideAllocationPlanV2,
    fragment_course_document,
    normalize_slide_deck_theme,
    plan_slide_deck_v3,
    slide_deck_preflight_quality,
    slide_deck_variant_key,
    split_slide_deck_plan_by_chapter,
)
from slide_deck_v4 import (
    allocation_from_story_plan_v2,
    build_signature_v4,
)
from slide_deck_v5 import (
    SlideDeckV5BuildError,
    allocation_from_story_plan_v5,
    build_signature_v5,
    compact_story_plan_v5,
)
from slide_deck_v6 import V6BuildError, compile_shadow_chapter_document
from slide_deck_v6_orchestrator import (
    SLIDE_DECK_V6_BUILD_CONTRACT_VERSION,
    SlideDeckV6CandidateRepository,
    SlideDeckV6Orchestrator,
)
from slide_story_plan import (
    SlideStoryPlanPrerequisiteError,
    SlideStoryPlanV2,
    compile_slide_story_plan_v2,
    plan_slide_story_v2,
    resolve_slide_deck_schema,
)
from slide_theme import slide_theme_version
from slide_visuals import (
    SlideVisualPlanV1,
    build_signature,
    plan_slide_visuals,
)
from storage import DATA_DIR
from teaching_design import (
    compatible_course_purpose,
    course_purpose_for_type,
    default_composition_style,
    ensure_course_type_enabled,
    resolve_course_teaching_type,
    resolve_course_type,
    resolve_learning_purpose,
)
from teaching_representations import teaching_representation_repository
from template_layout_contract import (
    TemplateLayoutPackContractV1,
    compile_builtin_template_layout_contract_v1,
)
from web_material_curation import (
    load_course_exclusions,
    merge_ingest_exclusions,
)
from web_retrieval import (
    RetrievalRequest,
    configured_retrieval_gateway,
    resolve_retrieval_policy,
)

logger = logging.getLogger(__name__)

DEFAULT_TASKS_FILE = Path(DATA_DIR) / "generation_jobs.json"
TASKS_FILE = DEFAULT_TASKS_FILE
LEGACY_TASKS_FILE = Path(__file__).with_name("tasks.json")

# 正文并行阶段的默认并发。真正的取值来自
# `CourseGenerationBudget.content_concurrency`（可用 COURSE_CONTENT_CONCURRENCY
# 覆盖）；这个常量只是没有传入预算时的兜底，两者必须保持一致。
# 8 是按端点实测容量定的，依据见 course_generation_budget.py 的注释。
DEFAULT_MAX_CONCURRENCY = 8
DEFAULT_MAX_COURSE_CONCURRENCY = 2
QUALITY_REPAIR_POLICY_VERSION = "quality_repair_v2.2"

# 内容完整性阈值（字符数）
CONTENT_COMPLETE_THRESHOLD = 600

STREAM_PROGRESS_INTERVAL_SECONDS = 1.5
DRAFT_CHECKPOINT_INTERVAL_SECONDS = 8.0
ACTIVE_NODE_PROGRESS_CREDIT = 0.35





# 指数退避参数
BACKOFF_BASE = 2
BACKOFF_MAX = 60

# Task polling is a control-plane read. Large representation artifacts and event
# payloads stay in their dedicated repositories/endpoints instead of being
# copied into every five-second task-list response.
PUBLIC_TASK_OMITTED_FIELDS = frozenset({
    "event_history",
    "last_event",
    "result",
    "representation_deck_plan",
    "representation_deck_plan_v3",
    "representation_story_plan_v2",
    "request_snapshot",
    "node_drafts",
})
PUBLIC_TASK_LOG_LIMIT = 100
SLIDE_BUILD_REQUEST_CONTRACT_FIELDS = (
    "operation",
    "mode",
    "theme",
    "variant_key",
    "target_schema",
    "template_contract",
    "template_selector",
    "force_rebuild",
    "shadow_only",
    "chapter_id",
    "source_course_document_revision",
    "representation_id",
    "target_page_ids",
)


def _persisted_task_owner_id(task: dict[str, Any]) -> str:
    return str(
        task.get("owner_id")
        or (task.get("request_snapshot") or {}).get("_retrieval_actor_id")
        or ""
    )


def _slide_build_request_contract(
    request_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    """Keep immutable slide routing inputs after bulky terminal data is pruned."""

    request = request_snapshot or {}
    return {
        "schema_version": "slide_build_request_contract_v1",
        **{
            field: deepcopy(request[field])
            for field in SLIDE_BUILD_REQUEST_CONTRACT_FIELDS
            if field in request
        },
    }


def _slide_build_task_request(task: dict[str, Any]) -> dict[str, Any]:
    """Resolve slide routing from the live request or its durable contract."""

    request = task.get("request_snapshot")
    if isinstance(request, dict) and request:
        return request
    contract = task.get("slide_build_request_contract")
    if (
        isinstance(contract, dict)
        and contract.get("schema_version")
        == "slide_build_request_contract_v1"
    ):
        return contract
    return {}


def _persisted_slide_progress_projection(
    manifest: dict[str, Any],
) -> dict[str, Any] | None:
    """Project the persisted V6 manifest back into the public task view."""

    if manifest.get("schema_version") != "slide_build_progress_v2":
        return None
    context = manifest.get("current_context") or {}
    if not isinstance(context, dict):
        context = {}
    projection = deepcopy(manifest)
    projection.update({
        "percent": int(manifest.get("display_percent") or 0),
        "stage": str(context.get("stage") or "source"),
        "current_chapter_id": str(context.get("chapter_id") or ""),
        "current_batch_id": str(context.get("batch_id") or ""),
        "current_page_id": str(context.get("page_id") or ""),
    })
    return projection


TERMINAL_TASK_STATUSES = frozenset({
    "cancelled",
    "canceled",
    "completed",
    "completed_with_warnings",
    "error",
    "failed",
})
BACKGROUND_ACTIVE_TASK_STATUSES = frozenset({"pending", "running"})
BACKGROUND_FROZEN_TASK_STATUSES = frozenset({
    *TERMINAL_TASK_STATUSES,
    "paused",
    "waiting_for_input",
    "waiting_for_review",
    "conflict",
})
MAX_TERMINAL_TASK_HISTORY = max(
    1,
    int(os.getenv("GENERATION_JOB_HISTORY_LIMIT", "100")),
)
MAX_TASK_INDEX_BYTES = max(
    1024 * 1024,
    int(os.getenv("GENERATION_JOB_INDEX_MAX_BYTES", str(96 * 1024 * 1024))),
)
TASK_INDEX_LAST_GOOD_SCHEMA = "generation_job_index_last_good_v1"


def _public_representation_quality(
    quality: Any,
) -> dict[str, Any] | None:
    if not isinstance(quality, dict):
        return None
    blockers = list(quality.get("blockers") or [])
    warnings = list(quality.get("warnings") or [])
    return {
        key: deepcopy(quality[key])
        for key in ("passed", "score", "planning")
        if key in quality
    } | {
        "blockers": deepcopy(blockers[:24]),
        "warnings": deepcopy(warnings[:24]),
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
    }


def _teacher_outline_result_ready(course_data: Any) -> bool:
    """Return whether every lecture of the teacher outline is complete."""
    if not isinstance(course_data, dict):
        return False
    if course_data.get("outline_framework_only") is True:
        return False
    outline_stage = (
        (course_data.get("generation_stage_artifacts") or {}).get("outline")
        or {}
    )
    strategy = str(outline_stage.get("strategy") or "")
    if strategy in {
        "teacher_framework_then_detail_batches",
        "teacher_framework_then_lecture_tasks",
    }:
        if str(outline_stage.get("course_contract_status") or "") != "completed":
            return False
        detail_records = [
            item
            for item in (outline_stage.get("detail_batches") or {}).values()
            if isinstance(item, dict)
        ]
        if not detail_records or any(
            str(item.get("status") or "") != "completed"
            for item in detail_records
        ):
            return False
        if str(outline_stage.get("status") or "") not in {
            "completed",
            "completed_with_warnings",
        }:
            return False
    nodes = [item for item in course_data.get("nodes") or [] if isinstance(item, dict)]
    return bool(nodes) and all(
        str(item.get("node_id") or "").strip()
        and str(item.get("node_name") or "").strip()
        for item in nodes
    )




class TaskRecoveryConflict(RuntimeError):
    def __init__(self, message: str, *, recovery: dict[str, Any]) -> None:
        super().__init__(message)
        self.recovery = deepcopy(recovery)


class TaskStateConflict(RuntimeError):
    def __init__(self, message: str, *, status: str) -> None:
        super().__init__(message)
        self.status = status


class TaskIndexDegradedError(RuntimeError):
    """Raised when task writes are unsafe because no valid index is available."""

    code = "generation_job_index_degraded"


class TaskLeaderConflictError(RuntimeError):
    """Raised before task loading when another process owns the data directory."""

    code = "generation_job_leader_unavailable"




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
        max_concurrency: int | None = None,
        max_course_concurrency: int = DEFAULT_MAX_COURSE_CONCURRENCY,
        version_repository: CourseVersionRepository | None = None,
        asset_repository: LearningAssetRepository | None = None,
        workspace_repository: GenerationWorkspaceRepository | None = None,
        document_repository: CourseDocumentRepository | None = None,
        question_bank_repository_override: QuestionBankRepository | None = None,
        assessment_orchestrator_override: AssessmentGenerationOrchestrator | None = None,
        runtime_mode: str | None = None,
    ) -> None:
        self.storage = storage
        self.course_service = course_service
        self.ws_service = ws_service
        runtime_budget = getattr(
            course_service,
            "_generation_budget",
            None,
        )
        self._generation_budget = (
            runtime_budget
            if isinstance(runtime_budget, CourseGenerationBudget)
            else CourseGenerationBudget.from_env()
        )
        resolved_max_concurrency = (
            self._generation_budget.content_concurrency
            if max_concurrency is None
            else max_concurrency
        )
        resolved_max_concurrency = max(
            1,
            min(16, int(resolved_max_concurrency)),
        )
        self._content_max_retries = (
            self._generation_budget.content_max_retries
        )
        self._content_inactivity_timeout_seconds = (
            self._generation_budget.content_inactivity_timeout_seconds
        )
        self._material_repository = getattr(course_service, "_material_repository", material_repository)
        storage_data_dir = Path(
            getattr(storage, "_data_dir", Path(TASKS_FILE).parent)
        )
        self._storage_data_dir = storage_data_dir
        self._runtime_mode = str(
            runtime_mode
            or os.getenv("LINGZHI_TASK_RUNTIME_MODE")
            or "leader"
        ).strip().lower()
        if self._runtime_mode not in {"leader", "isolated_test", "read_only"}:
            raise ValueError(
                "LINGZHI_TASK_RUNTIME_MODE must be leader, isolated_test, or read_only"
            )
        self._leader_lock_path = storage_data_dir / "generation_jobs.leader.lock"
        self._leader_lock_handle: Any | None = None
        self._leader_state = (
            "not_required"
            if self._runtime_mode == "isolated_test"
            else "read_only"
            if self._runtime_mode == "read_only"
            else "acquiring"
        )
        if self._runtime_mode == "leader":
            self._acquire_leader_lock()
        self._import_sources_dir = storage_data_dir / "course_import_sources"
        if self._runtime_mode != "read_only":
            self._import_sources_dir.mkdir(parents=True, exist_ok=True)
        self._version_repository = version_repository or course_version_repository
        self._learning_asset_repository = asset_repository or learning_asset_repository
        self._question_bank_repository = (
            question_bank_repository_override or question_bank_repository
        )
        self._assessment_orchestrator = (
            assessment_orchestrator_override or AssessmentGenerationOrchestrator()
        )
        self._generation_workspace_repository = workspace_repository or generation_workspace_repository
        self._course_document_repository = document_repository or CourseDocumentRepository(storage)
        self.max_concurrency = resolved_max_concurrency
        self.max_course_concurrency = max_course_concurrency

        # Task state
        self.tasks: dict[str, dict[str, Any]] = {}
        self._task_index_state = "loading"
        self._task_index_recovery = "none"
        self._task_index_error_code: str | None = None
        self._lock: asyncio.Lock = asyncio.Lock()
        self._creation_lock: asyncio.Lock = asyncio.Lock()

        # asyncio.Queue for producer-consumer pattern
        self._task_queue: asyncio.Queue[str] = asyncio.Queue()

        # Semaphore for concurrency control
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(
            resolved_max_concurrency
        )
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
        if self._runtime_mode == "read_only":
            raise TaskLeaderConflictError(
                "Read-only TaskManager cannot start a task consumer"
            )
        if self._runtime_mode == "leader" and self._leader_state != "acquired":
            raise TaskLeaderConflictError(
                "Task consumer requires the data-directory leader lock"
            )

        original_tasks = self.tasks
        self.tasks = deepcopy(self.tasks)
        resumable_task_ids: list[str] = []
        try:
            for task_id in list(self.tasks):
                task_before = deepcopy(self.tasks.get(task_id) or {})
                resumable = await self._reconcile_task_after_restart(task_id)
                if resumable:
                    resumable_task_ids.append(task_id)
                if str(task_before.get("status") or "") in {"pending", "running"}:
                    task_after = self.tasks.get(task_id) or {}
                    after_status = str(task_after.get("status") or "")
                    recovery_result = (
                        "resumed"
                        if resumable
                        else "completed"
                        if after_status == "completed"
                        else "unavailable"
                        if after_status in {"failed", "cancelled"}
                        else "skipped"
                    )
                    record_recovery_result(
                        task_type=task_before.get("type"),
                        trigger="service_restart",
                        result=recovery_result,
                    )
            self._save_tasks_strict()
        except BaseException:
            self.tasks = original_tasks
            raise
        for task_id in resumable_task_ids:
            await self._task_queue.put(task_id)
        self._running = True
        self._consumer_task = asyncio.create_task(self._consumer_loop())
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

        try:
            if self._runtime_mode != "read_only":
                self.save_tasks()
        finally:
            self._release_leader_lock()
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
        self._ensure_task_index_writable()
        task_id = task_id or str(uuid.uuid4())
        now = datetime.now().isoformat()
        normalized_request_snapshot = deepcopy(request_snapshot or {})
        normalized_generation_profile = (
            normalize_assessment_generation_profile(
                normalized_request_snapshot.get(
                    "assessment_generation_profile"
                )
            )
        )
        if (
            task_type in {"course_generation", "teacher_outline_generation"}
            or "assessment_generation_profile"
            in normalized_request_snapshot
        ):
            normalized_request_snapshot[
                "assessment_generation_profile"
            ] = normalized_generation_profile
        task: dict[str, Any] = {
            "id": task_id,
            "course_id": course_id,
            "owner_id": str(
                normalized_request_snapshot.get("_retrieval_actor_id") or ""
            ),
            "type": task_type,
            "course_name": course_name,
            "course_type": str(
                normalized_request_snapshot.get("course_type")
                or "systematic"
            ),
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
            "heartbeat_at": now,
            "phase_history": [],
            "error": None,
            "retry_count": 0,
            "logs": [],
            "request_snapshot": normalized_request_snapshot,
            "assessment_generation_profile": normalized_generation_profile,
            "assessment_generation_policy_version": (
                ASSESSMENT_GENERATION_POLICY_VERSION
            ),
            "node_drafts": {},
            "operation": str(
                normalized_request_snapshot.get("operation") or "generate"
            ),
            "candidate_id": normalized_request_snapshot.get("candidate_id"),
            "base_version_id": normalized_request_snapshot.get(
                "base_version_id"
            ),
            "blueprint_confirmed": bool(
                normalized_request_snapshot.get("blueprint_confirmed", False)
            ),
            "blueprint_revision_id": normalized_request_snapshot.get(
                "blueprint_revision_id"
            ),
            "workspace_id": workspace_id,
            "base_document_revision": base_document_revision,
        }
        if task_type == "slide_deck_variant_build":
            task["slide_build_request_contract"] = (
                _slide_build_request_contract(normalized_request_snapshot)
            )
            if str(
                normalized_request_snapshot.get("target_schema") or ""
            ) == (
                "slide_deck_v6"
            ):
                task["slide_build_contract_version"] = (
                    SLIDE_DECK_V6_BUILD_CONTRACT_VERSION
                )
        if (
            task_type == "course_generation"
            and workspace_id
            and task["operation"] == "generate"
        ):
            task["guided_workflow"] = create_guided_workflow(task["request_snapshot"])
        async with self._lock:
            task = self._commit_task_draft(
                task_id,
                task,
                allow_create=True,
            )
            self._task_logs[task_id] = []
            self._node_retries[task_id] = {}

        if enqueue:
            try:
                await self._task_queue.put(task_id)
            except BaseException:
                async with self._lock:
                    self._remove_task_strict(task_id)
                    self._task_logs.pop(task_id, None)
                    self._node_retries.pop(task_id, None)
                raise
        logger.info("Created task %s for course %s", task_id, course_id)
        return task_id

    def import_source_path(self, task_id: str) -> Path:
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", str(task_id))
        return self._import_sources_dir / f"{safe_id}.md"

    def import_checkpoint_path(self, task_id: str) -> Path:
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", str(task_id))
        return self._import_sources_dir / f"{safe_id}.parsed.json"

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)

    async def create_markdown_import_job(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str,
        actor_id: str = "",
        enqueue: bool = True,
    ) -> dict[str, str]:
        """Create a durable Markdown import job without exposing source bytes."""
        if not content:
            raise ValueError("上传的文件为空")
        if len(content) > 20 * 1024 * 1024:
            raise ValueError("文件过大，最大支持 20 MB")
        allowed_mime = {"text/markdown", "text/plain", "application/octet-stream"}
        if content_type not in allowed_mime:
            raise ValueError("不支持的文件类型，请上传 .md 或 .txt 文件")

        task_id = str(uuid.uuid4())
        course_id = str(uuid.uuid4())
        safe_filename = Path(filename or "import.md").name
        await self.create_task(
            course_id,
            "course_import",
            course_name=Path(safe_filename).stem or "待导入课程",
            request_snapshot={
                "operation": "import",
                "filename": safe_filename,
                "content_type": content_type,
                "_retrieval_actor_id": str(actor_id or ""),
            },
            task_id=task_id,
            enqueue=False,
        )
        try:
            self.import_source_path(task_id).write_bytes(content)
            await self._update_phase(
                task_id,
                "material_receiving",
                5,
                "资料已接收，等待解析",
                phase_progress=100,
                phase_detail={"filename": safe_filename, "received_bytes": len(content)},
            )
            if enqueue:
                await self._task_queue.put(task_id)
        except BaseException:
            async with self._lock:
                self._remove_task_strict(task_id)
                self._task_logs.pop(task_id, None)
                self._node_retries.pop(task_id, None)
            self.import_source_path(task_id).unlink(missing_ok=True)
            raise
        return {"job_id": task_id, "course_id": course_id}

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
                        "course_type": str(existing.get("course_type") or "systematic"),
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
        course_type, course_type_source = resolve_course_type(
            request_snapshot.get("learning_purpose")
            or request_snapshot.get("course_type"),
            course_purpose=request_snapshot.get("course_purpose"),
            composition_style=request_snapshot.get("composition_style"),
        )
        request_snapshot["course_type"] = course_type
        ensure_course_type_enabled(course_type)
        request_snapshot["course_purpose"] = (
            course_purpose_for_type(course_type)
            if course_type_source == "course_type"
            else compatible_course_purpose(
                course_type,
                request_snapshot.get("course_purpose"),
            )
        )
        learning_purpose = resolve_learning_purpose(
            request_snapshot.get("learning_purpose"),
            legacy_course_type=course_type,
        )
        course_teaching_type, _ = resolve_course_teaching_type(
            request_snapshot.get("course_teaching_type"),
            learning_purpose=learning_purpose,
            legacy_course_type=course_type,
            composition_style=request_snapshot.get("composition_style"),
        )
        request_snapshot["learning_purpose"] = learning_purpose
        request_snapshot["course_teaching_type"] = course_teaching_type
        if not request_snapshot.get("composition_style") and not request_snapshot.get("style"):
            request_snapshot["composition_style"] = default_composition_style(course_type)
        composition_profile = compile_composition_profile(
            request_snapshot.get("composition_style"),
            legacy_style=request_snapshot.get("style"),
        )
        request_snapshot["composition_style"] = composition_profile["style"]
        # First-time generation has one product path. Submitting requirements
        # confirms step 1; only the outline and final release wait for review.
        # Teaching-plan/content production stays inside the same durable job.
        request_snapshot["generation_mode"] = "review_blueprint"
        legacy_bindings, metadata_only = await ingest_legacy_material_inputs(
            request_snapshot.get("materials") or [],
            repository=self._material_repository,
        )
        existing_bindings = list(request_snapshot.get("material_bindings") or [])
        request_snapshot["material_bindings"] = existing_bindings + legacy_bindings
        request_snapshot["materials"] = metadata_only
        target_course_id = str(request_snapshot.get("target_course_id") or "").strip()
        course_id = target_course_id or str(uuid.uuid4())
        draft_snapshot: dict[str, Any] | None = None
        if target_course_id:
            if not self.storage:
                raise CourseDocumentConflict("Teacher draft storage is unavailable")
            candidate = self.storage.load_course(target_course_id)
            if not isinstance(candidate, dict) or not candidate:
                raise CourseDocumentConflict("Teacher draft does not exist")
            if (
                candidate.get("course_status") != "draft"
                or candidate.get("authoring_surface") != "teacher"
                or candidate.get("generation_job_id")
            ):
                raise CourseDocumentConflict("Course is not an available teacher draft")
            draft_snapshot = deepcopy(candidate)
        task_id = str(uuid.uuid4())
        task_type = (
            "teacher_outline_generation"
            if request_snapshot.get("teacher_authoring_mode") == "lesson_assets_v1"
            else "course_generation"
        )
        course_data = {
            "course_id": course_id,
            "course_name": subject,
            "generation_schema_version": PIPELINE_VERSION,
            "generation_status": "queued",
            "nodes": [],
            "generation_request": request_snapshot,
            "course_type": course_type,
            "course_intent": deepcopy(request_snapshot.get("course_intent") or {}),
            "learner_starting_profile": deepcopy(
                request_snapshot.get("learner_starting_profile") or {}
            ),
            "generation_quality_report": None,
            "course_purpose": request_snapshot.get("course_purpose") or "systematic",
            "generation_mode": "review_blueprint",
            "asset_preferences": deepcopy(request_snapshot.get("asset_preferences") or {}),
            "web_question_enrichment": deepcopy(
                request_snapshot.get("web_question_enrichment") or {"enabled": False}
            ),
            "web_material_ingest": deepcopy(
                request_snapshot.get("web_material_ingest") or {}
            ),
            "authoring_surface": (
                "teacher" if task_type == "teacher_outline_generation" else "shared"
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
            if draft_snapshot is not None:
                shell = await self._course_document_repository.claim_teacher_draft_for_generation(
                    course_id,
                    title=subject,
                    job_id=task_id,
                    metadata=course_data,
                )
            else:
                shell = await self._course_document_repository.create_generation_shell(
                    course_id,
                    title=subject,
                    job_id=task_id,
                    metadata=course_data,
                )
            task_id = await self.create_task(
                course_id,
                task_type,
                course_name=subject,
                request_snapshot=request_snapshot,
                task_id=task_id,
                workspace_id=task_id,
                base_document_revision=str(shell["document"]["document_revision"]),
            )
        except BaseException:
            raw = self.storage.load_course(course_id) if self.storage else None
            if draft_snapshot is not None and self.storage:
                await self.storage.save_course(course_id, draft_snapshot)
            elif isinstance(raw, dict) and raw.get("generation_job_id") == task_id:
                await self._delete_stored_course(course_id)
            if workspace_created:
                self._generation_workspace_repository.delete(task_id)
            self._version_repository.delete_course(course_id)
            self._learning_asset_repository.delete_course(course_id)
            self._question_bank_repository.delete_course(course_id)
            self._reset_course_service_runtime(
                course_id,
                preserve_course=draft_snapshot is not None,
            )
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
        """Compile a complete plan from the editable ordered tree."""
        if any(int(node.get("node_level") or 0) == 1 for node in nodes):
            return compile_outline_draft({
                "nodes": deepcopy(nodes),
                "course_plan": deepcopy(plan),
            })["course_plan"]

        # Compatibility for old flat blueprints created before chapter nodes
        # became part of the canonical tree. New adjustment proposals never
        # use this path.
        synced = deepcopy(plan)
        by_id = {
            str(node.get("node_id") or ""): node
            for node in nodes
            if isinstance(node, dict)
        }
        for chapter in synced.get("chapters") or []:
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
                    "learning_path_role",
                    "path_reason",
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
        impact: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Discard stale downstream data when an approved upstream step changes.

        With an ``impact`` analysis the node-level discard is scoped to the
        sections the edit actually reaches.  Sections the analysis proves
        untouched keep their generated body, so retitling one section no
        longer forces every section to be written again.  Course-level
        derived artifacts are still dropped: they are recompiled locally
        without model calls, so keeping them would risk staleness for no gain.
        """
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
        preserved_node_ids: set[str] = set()
        if isinstance(impact, dict) and not (impact.get("global_changes") or []):
            preserved_node_ids = {
                str(node_id)
                for node_id in (
                    list(impact.get("unchanged_node_ids") or [])
                    + list(impact.get("display_only_node_ids") or [])
                )
                if node_id
            } - {
                str(node_id)
                for node_id in (
                    list(impact.get("affected_node_ids") or [])
                    + list(impact.get("added_node_ids") or [])
                    + list(impact.get("removed_node_ids") or [])
                )
                if node_id
            }
        for node in working.get("nodes") or []:
            if str(node.get("node_id") or "") in preserved_node_ids:
                continue
            for field in downstream_node_fields:
                node.pop(field, None)
            node["generation_status"] = "pending"
        working["outline_change_preserved_node_ids"] = sorted(
            preserved_node_ids
        )

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

    async def preview_outline_adjustment(
        self,
        course_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate and validate a non-persistent reviewable outline proposal."""
        started_at = time.monotonic()
        request_id = str(payload.get("request_id") or "")
        course_data = self.get_generation_workspace_course_for_task(
            course_id,
            task_type="teacher_outline_generation",
            require_usable_outline=True,
        )
        if not isinstance(course_data, dict) and self.storage:
            course_data = self.storage.load_course(course_id)
        if not isinstance(course_data, dict):
            raise ValueError("Course not found")

        current_blueprint_revision = blueprint_revision_id(course_data)
        expected_base = str(payload.get("base_blueprint_revision_id") or "")
        if expected_base and expected_base != current_blueprint_revision:
            raise CourseVersionConflict("课程基础蓝图已变化，请重新载入并生成方案")
        source_draft = (
            self._version_repository.load_draft(course_id)
            or build_blueprint_draft(course_data)
        )
        source_draft["draft_revision_id"] = blueprint_draft_revision_id(source_draft)
        expected_draft = str(payload.get("expected_draft_revision_id") or "")
        if expected_draft != source_draft["draft_revision_id"]:
            raise CourseVersionConflict("目录草稿已被其他页面修改，请重新载入并生成方案")
        if not self.course_service or not hasattr(
            self.course_service,
            "propose_outline_adjustment",
        ):
            raise AIProviderUnavailable("outline_adjustment_not_configured")

        instruction = str(payload.get("instruction") or "").strip()
        target_quality_issue_code = str(
            payload.get("target_quality_issue_code") or ""
        ).strip()
        source_quality_report: dict[str, Any] = {}
        source_quality_issue: dict[str, Any] | None = None
        if target_quality_issue_code:
            source_quality_report = review_course_outline_document(
                source_draft.get("course_plan")
                or source_draft.get("course_outline")
                or {},
                course_context={**course_data, **source_draft},
            )
            source_quality_issue = next(
                (
                    deepcopy(issue)
                    for issue in source_quality_report.get("issues") or []
                    if str(issue.get("code") or "")
                    == target_quality_issue_code
                ),
                None,
            )
        last_operations: list[dict[str, Any]] = []
        last_error: OutlineAdjustmentError | None = None
        result: dict[str, Any] | None = None
        correction: dict[str, Any] | None = None
        candidate_quality_report: dict[str, Any] = {}
        unresolved_quality_issue: dict[str, Any] | None = None
        for attempt in range(2):
            model_result = await self.course_service.propose_outline_adjustment(
                draft=source_draft,
                instruction=instruction,
                correction=correction,
            )
            operations = model_result.get("operations") if isinstance(model_result, dict) else None
            last_operations = operations if isinstance(operations, list) else []
            try:
                if not isinstance(operations, list):
                    raise OutlineAdjustmentError(
                        "model_operations_missing",
                        "AI 没有返回合法的目录操作列表",
                    )
                result = apply_outline_operations(source_draft, operations)
            except OutlineAdjustmentError as exc:
                last_error = exc
                if attempt == 0:
                    correction = {
                        "message": "上一版操作未通过确定性校验，请只修正操作列表",
                        "validation_error": exc.as_issue(),
                        "previous_operations": last_operations,
                    }
                continue

            if target_quality_issue_code and source_quality_issue:
                candidate_draft = result["draft"]
                candidate_quality_report = review_course_outline_document(
                    candidate_draft.get("course_plan")
                    or candidate_draft.get("course_outline")
                    or {},
                    course_context={**course_data, **candidate_draft},
                )
                unresolved_quality_issue = next(
                    (
                        deepcopy(issue)
                        for issue in candidate_quality_report.get("issues") or []
                        if str(issue.get("code") or "")
                        == target_quality_issue_code
                    ),
                    None,
                )
                if unresolved_quality_issue and attempt == 0:
                    correction = {
                        "message": (
                            "上一版候选没有解决指定的大纲审阅问题。"
                            "请重新生成操作，确保复审后该问题代码消失。"
                        ),
                        "target_quality_issue": source_quality_issue,
                        "validation_issue": unresolved_quality_issue,
                        "previous_operations": last_operations,
                    }
                    result = None
                    continue
            break

        proposal_id = outline_adjustment_proposal_id(
            source_draft["draft_revision_id"],
            last_operations,
        )
        elapsed_ms = round((time.monotonic() - started_at) * 1000)
        if result is None:
            issue = (
                last_error.as_issue()
                if last_error
                else {"code": "model_output_invalid", "message": "AI 未能形成合法目录方案"}
            )
            logger.warning(
                "outline_adjustment_preview_invalid request_id=%s proposal_id=%s latency_ms=%s "
                "operation_count=%s validation_code=%s",
                request_id,
                proposal_id,
                elapsed_ms,
                len(last_operations),
                issue.get("code"),
            )
            return {
                "proposal_id": proposal_id,
                "source_draft_revision_id": source_draft["draft_revision_id"],
                "operations": last_operations,
                "summary": "AI 暂时无法把这句话转换为安全的目录调整，请换一种说法后重试。",
                "diff": {
                    "added": [],
                    "removed": [],
                    "moved": [],
                    "updated": [],
                    "before": {},
                    "after": {},
                },
                "draft": source_draft,
                "impact_report": {},
                "constraint_report": {"valid": False},
                "can_apply": False,
                "blocking_issues": [issue],
                "warnings": [],
            }

        proposed_draft = result["draft"]
        proposed_draft["base_blueprint_revision_id"] = current_blueprint_revision
        proposed_draft["draft_revision_id"] = blueprint_draft_revision_id(proposed_draft)
        impact = analyze_blueprint_impact(course_data, proposed_draft)
        blocking_issues = [
            {
                "code": "blueprint_lock_conflict",
                "message": "调整影响了已锁定的目录节点",
                "details": deepcopy(item),
            }
            for item in impact.get("lock_conflicts") or []
        ]
        if target_quality_issue_code and not source_quality_issue:
            blocking_issues.append({
                "code": "outline_quality_issue_stale",
                "message": (
                    "这项审阅建议已不属于当前大纲，"
                    "请放弃候选并刷新后再试。"
                ),
            })
        elif unresolved_quality_issue:
            blocking_issues.append({
                "code": "outline_quality_issue_unresolved",
                        "message": (
                            "这版 AI 候选仍未解决目标审阅问题，"
                            "已暂停采用；可以重试或放弃，不影响继续编辑当前大纲。"
                        ),
                "target_issue_code": target_quality_issue_code,
                "details": deepcopy(unresolved_quality_issue),
            })
        can_apply = bool(impact.get("can_confirm", False)) and not blocking_issues
        diff = describe_outline_diff(
            source_draft,
            proposed_draft,
            result.get("id_map") or {},
        )
        summary = str(model_result.get("summary") or "").strip()
        if not summary:
            source_plan = source_draft.get("course_plan") or source_draft.get("course_outline") or {}
            source_shape = (
                (source_draft.get("course_generation_brief") or {})
                .get("course_shape_constraints") or {}
            )
            if (
                source_draft.get("authoring_structure_version") == "lecture_v1"
                or source_plan.get("authoring_structure_version") == "lecture_v1"
                or source_shape.get("teacher_lecture_mode")
            ):
                summary = (
                    f"大纲将从 {diff['before']['chapter_count']} 讲调整为 "
                    f"{diff['after']['chapter_count']} 讲。"
                )
            else:
                summary = (
                    f"目录将从 {diff['before']['chapter_count']} 章"
                    f"{diff['before']['section_count']} 节调整为 "
                    f"{diff['after']['chapter_count']} 章{diff['after']['section_count']} 节。"
                )
        logger.info(
            "outline_adjustment_preview request_id=%s proposal_id=%s latency_ms=%s "
            "operation_count=%s validation_code=%s",
            request_id,
            proposal_id,
            elapsed_ms,
            len(last_operations),
            "ok" if can_apply else "blocked",
        )
        return {
            "proposal_id": proposal_id,
            "source_draft_revision_id": source_draft["draft_revision_id"],
            "operations": last_operations,
            "summary": summary,
            "diff": diff,
            "draft": proposed_draft,
            "impact_report": impact,
            "constraint_report": result["constraint_report"],
            "quality_report": candidate_quality_report,
            "target_quality_issue_code": target_quality_issue_code or None,
            "can_apply": can_apply,
            "blocking_issues": blocking_issues,
            "warnings": [],
        }

    async def _prepare_course_outline_research(
        self,
        course_data: dict[str, Any],
        request: dict[str, Any],
        *,
        package_revision: int = 1,
    ) -> dict[str, Any]:
        """Retrieve once and create a non-applied source-backed outline draft."""

        if not COURSE_WEB_RESEARCH_ENABLED:
            course_data = course_generation_view(course_data)
            course_data.setdefault("generation_stage_artifacts", {})[
                "web_retrieval"
            ] = {
                "status": "disabled",
                "reason": "course_web_research_frozen",
            }
            return course_data

        policy = resolve_retrieval_policy(request)
        artifacts = course_data.setdefault(
            "generation_stage_artifacts", {}
        )
        existing = deepcopy(artifacts.get("web_retrieval") or {})
        if existing.get("package"):
            return course_data
        if "course" not in policy.get("scopes", []):
            artifacts["web_retrieval"] = {
                "status": "disabled",
                "authorization": policy,
            }
            return course_data

        queries = build_course_retrieval_queries(course_data, request)
        gateway, feature = configured_retrieval_gateway(
            str(request.get("_retrieval_actor_id") or "") or None
        )
        package = await gateway.retrieve(
            RetrievalRequest(
                purpose="course",
                enabled=True,
                queries=queries,
                request_fingerprint=stable_hash(
                    {
                        "course_id": course_data.get("course_id"),
                        "subject": request.get("subject"),
                        "difficulty": request.get("difficulty"),
                        "course_intent": request.get("course_intent") or {},
                        "outline_revision": blueprint_revision_id(course_data),
                    },
                    prefix="rrq_",
                ),
                revision=max(1, int(package_revision)),
            )
        )
        artifact = {
            "schema_version": "course_web_retrieval_v2",
            "status": package.get("status"),
            "authorization": policy,
            "feature": feature,
            "package": deepcopy(package),
            "proposal": None,
        }
        artifacts["web_retrieval"] = artifact
        course_data["retrieval_package"] = deepcopy(package)
        if package.get("status") != "completed":
            artifact["notice"] = "联网核验未完成，可重试或离线继续"
            return course_data

        base_draft = build_blueprint_draft(course_data)
        try:
            model_result = await self.course_service.propose_outline_adjustment(
                draft=base_draft,
                instruction=build_outline_research_instruction(package),
                correction=None,
            )
            proposal = build_outline_research_proposal(
                course=course_data,
                base_draft=base_draft,
                model_result=model_result,
                retrieval_package=package,
            )
            if not proposal.get("operations"):
                proposal["status"] = "no_changes"
            artifact["proposal"] = proposal
            artifact["status"] = (
                "waiting_for_confirmation"
                if proposal.get("operations")
                else "completed_no_changes"
            )
            course_data["outline_research"] = {
                key: deepcopy(proposal.get(key))
                for key in (
                    "schema_version",
                    "proposal_id",
                    "status",
                    "reason",
                    "diff",
                    "source_ids",
                    "tier_b_source_ids",
                    "sources",
                    "retrieval_package_revision",
                )
            }
        except (
            OutlineAdjustmentError,
            AIProviderRequestError,
            AIProviderUnavailable,
            ValueError,
            TypeError,
        ) as exc:
            artifact["status"] = "proposal_failed_fallback_local"
            artifact["notice"] = (
                "联网资料已取得，但目录调整提案未完成；当前显示本地蓝图"
            )
            artifact["proposal_error"] = {
                "code": "outline_proposal_failed",
                "message": str(exc)[:500],
            }
        return course_data

    @staticmethod
    def _accept_outline_research(
        course_data: dict[str, Any],
    ) -> dict[str, Any]:
        if not COURSE_WEB_RESEARCH_ENABLED:
            return course_generation_view(course_data)
        artifacts = course_data.get("generation_stage_artifacts") or {}
        artifact = artifacts.get("web_retrieval") or {}
        proposal = artifact.get("proposal") or {}
        package = artifact.get("package") or {}
        if proposal.get("status") not in {
            "waiting_for_confirmation",
            "no_changes",
        }:
            return course_data
        accepted_ids = list(proposal.get("tier_b_source_ids") or [])
        for source in package.get("sources") or []:
            if source.get("source_id") in accepted_ids:
                source["accepted_for_generation"] = True
        proposal["status"] = "accepted"
        artifact["status"] = "frozen"
        artifact["accepted_source_ids"] = accepted_ids
        course_data["retrieval_acceptance"] = {
            "schema_version": "retrieval_acceptance_v1",
            "proposal_id": proposal.get("proposal_id"),
            "accepted_source_ids": accepted_ids,
            "package_revision": package.get("revision"),
            "package_hash": package.get("package_hash"),
        }
        course_data["retrieval_package"] = deepcopy(package)
        if isinstance(course_data.get("outline_research"), dict):
            course_data["outline_research"]["status"] = "accepted"
        return course_data

    @staticmethod
    def _has_downstream_outline_artifacts(course_data: dict[str, Any]) -> bool:
        if any(
            course_data.get(field)
            for field in (
                "course_teaching_plan",
                "course_knowledge_base",
                "course_knowledge_map",
                "learning_assets",
            )
        ):
            return True
        return any(
            str(node.get("node_content") or "").strip()
            for node in course_data.get("nodes") or []
            if isinstance(node, dict)
        )

    @staticmethod
    def _outline_shape_growth(
        skeleton: dict[str, Any],
        *,
        state: str = "shape_review",
    ) -> dict[str, Any]:
        chapters = [
            {
                "chapter_number": int(item.get("chapter_number") or index),
                "title": str(item.get("title") or ""),
                "content_summary": str(item.get("content_summary") or ""),
                "learning_focus": str(item.get("learning_focus") or ""),
                "section_count": int(item.get("section_count") or 0),
                "completed_section_count": 0,
                "status": "waiting",
                "sections": [],
            }
            for index, item in enumerate(
                skeleton.get("chapters") or [],
                start=1,
            )
            if isinstance(item, dict)
        ]
        return {
            "schema_version": "course_outline_growth_v1",
            "state": state,
            "course_title": str(skeleton.get("course_title") or ""),
            "positioning": str(skeleton.get("positioning") or ""),
            "completed_batches": 0,
            "total_batches": 0,
            "completed_sections": 0,
            "total_sections": sum(
                int(item.get("section_count") or 0) for item in chapters
            ),
            "chapters": chapters,
        }

    async def _compile_teacher_outline_framework(
        self,
        task_id: str,
        course_data: dict[str, Any],
        *,
        draft: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Compile the current editable framework into the detail input."""
        task = self.tasks.get(task_id) or {}
        course_id = str(task.get("course_id") or course_data.get("course_id") or "")
        draft = deepcopy(draft) if isinstance(draft, dict) else (
            self._version_repository.load_draft(course_id)
            or build_blueprint_draft(course_data)
        )
        if any(
            int(node.get("node_level") or 0) == 1
            for node in draft.get("nodes") or []
            if isinstance(node, dict)
        ):
            draft = compile_outline_draft(draft)
        compiled = merge_blueprint_draft(course_data, draft)
        plan = compiled.get("course_plan") or compiled.get("course_outline") or {}
        outline_stage = (
            (compiled.get("generation_stage_artifacts") or {}).get("outline")
            or {}
        )
        raw_skeleton = outline_stage.get("skeleton")
        if not isinstance(raw_skeleton, dict):
            raise ValueError("The editable course framework is unavailable")
        raw_chapters = [
            item
            for item in raw_skeleton.get("chapters") or []
            if isinstance(item, dict)
        ]
        detail_fields = (
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
        lectures: list[dict[str, Any]] = []
        for index, chapter in enumerate(plan.get("chapters") or [], start=1):
            if not isinstance(chapter, dict):
                continue
            raw = raw_chapters[index - 1] if index <= len(raw_chapters) else {}
            sections = [
                item
                for item in chapter.get("sections") or []
                if isinstance(item, dict)
            ]
            section = sections[0] if sections else {}
            lecture = {
                **deepcopy(raw),
                "lecture_number": index,
                "title": str(chapter.get("title") or raw.get("title") or ""),
                "learning_objective": str(
                    chapter.get("learning_objective")
                    or chapter.get("learning_focus")
                    or section.get("learning_objective")
                    or raw.get("learning_objective")
                    or ""
                ),
                "scope_boundary": str(
                    section.get("scope_boundary")
                    or chapter.get("scope_boundary")
                    or raw.get("scope_boundary")
                    or ""
                ),
                "hour_breakdown": deepcopy(
                    section.get("hour_breakdown")
                    or chapter.get("hour_breakdown")
                    or raw.get("hour_breakdown")
                    or {}
                ),
            }
            for field in detail_fields:
                for owner in (section, chapter, raw):
                    value = owner.get(field)
                    if value not in (None, "", [], {}):
                        lecture[field] = deepcopy(value)
                        break
            lectures.append(lecture)

        payload = {
            key: deepcopy(plan.get(key, raw_skeleton.get(key)))
            for key in (
                "course_title",
                "positioning",
                "learning_objectives",
                "prerequisites",
                "course_intro_zh",
                "course_intro_en",
                "education_objectives",
                "measurable_outcomes",
                "outcome_alignment",
                "teaching_methods",
                "assessment_methods",
                "assessment_plan",
                "course_modules",
                "ideology_cases",
                "reference_books",
                "reference_websites",
                "course_website",
            )
        }
        payload.update({
            "authoring_structure_version": "lecture_v1",
            "course_title": str(
                compiled.get("course_name")
                or plan.get("course_title")
                or raw_skeleton.get("course_title")
                or "课程"
            ),
            "lectures": lectures,
        })
        request_fingerprint = str(outline_stage.get("request_fingerprint") or "")
        skeleton = normalize_outline_skeleton(
            payload,
            topic=str(payload["course_title"]),
            request_fingerprint=request_fingerprint,
            teacher_light_plan_only=True,
        )
        shape_constraints = deepcopy(
            (compiled.get("course_generation_brief") or {}).get(
                "course_shape_constraints"
            )
            or {}
        )
        shape_constraints.update({
            "teacher_lecture_mode": True,
            "chapter_count": len(lectures),
            "section_count": len(lectures),
            "lecture_count": len(lectures),
        })
        report = validate_outline_skeleton(
            skeleton,
            shape_constraints=shape_constraints,
            request_fingerprint=request_fingerprint,
            course_type_contract=(
                (compiled.get("course_generation_brief") or {}).get(
                    "course_type_contract"
                )
                or {}
            ),
        )
        if not report.get("passed"):
            messages = "；".join(
                str(item.get("message") or "课程方案无效")
                for item in report.get("issues") or []
            )
            raise ValueError(messages or "The editable course framework is invalid")

        previous_revision = str(outline_stage.get("skeleton_revision_id") or "")
        if previous_revision and previous_revision != skeleton.get("revision_id"):
            outline_stage["batches"] = {}
            outline_stage["detail_batches"] = {}
            outline_stage["fallback_units"] = []
            for key in (
                "course_contract_status",
                "course_contract",
                "course_contract_validation_report",
                "course_contract_duration_ms",
                "course_contract_failure_reason",
            ):
                outline_stage.pop(key, None)
        outline_stage.update({
            "status": "framework_ready",
            "strategy": "teacher_framework_then_lecture_tasks",
            "skeleton": skeleton,
            "skeleton_revision_id": skeleton.get("revision_id"),
            "skeleton_validation_report": report,
            "chapter_count": len(lectures),
            "section_count": len(lectures),
            "detail_batch_size": 1,
        })
        compiled.setdefault("generation_stage_artifacts", {})[
            "outline"
        ] = outline_stage
        compiled["outline_framework_only"] = True
        compiled["outline_generation_status"] = "generating"
        compiled["outline_lifecycle_status"] = "draft"
        compiled["generation_status"] = "outline_detail_generation"
        await self._save_task_course(task_id, compiled)
        return compiled

    async def continue_teacher_outline_details(
        self,
        course_id: str,
        task_id: str,
    ) -> dict[str, Any]:
        """Start or retry full outline generation only on an explicit command."""
        requested_task_id = str(task_id or "").strip()
        task_record = self.tasks.get(requested_task_id)
        if not isinstance(task_record, dict):
            raise ValueError("No teacher outline job was found for this course")
        if (
            str(task_record.get("course_id") or "") != course_id
            or task_record.get("type") != "teacher_outline_generation"
        ):
            raise TaskStateConflict(
                "The requested task is not the authorized outline job for this course",
                status=str(task_record.get("status") or "unknown"),
            )
        task = deepcopy(task_record)
        task_id = requested_task_id
        if task.get("status") in {"pending", "running"}:
            return {
                "status": "already_running",
                "job_id": task_id,
                "course_id": course_id,
            }
        course_data = self._load_task_course(task_id)
        if not isinstance(course_data, dict):
            raise ValueError("Course not found")
        result_ready = _teacher_outline_result_ready(course_data)
        draft = self._version_repository.load_draft(course_id)
        if result_ready and not isinstance(draft, dict):
            return {
                "status": "already_completed",
                "job_id": task_id,
                "course_id": course_id,
            }
        allowed_statuses = {"waiting_for_input", "failed"}
        if result_ready and isinstance(draft, dict):
            allowed_statuses.update({"completed", "completed_with_warnings"})
        if task.get("status") not in allowed_statuses:
            raise TaskStateConflict(
                "The course framework is not ready for full outline generation",
                status=str(task.get("status") or "unknown"),
            )
        workspace_id = str(task.get("workspace_id") or "")
        if result_ready and workspace_id:
            workspace = self._generation_workspace_repository.load(workspace_id)
            result = deepcopy(workspace.get("result") or {})
            result["last_good_course_data"] = deepcopy(course_data)
            result["last_good_outline_revision_id"] = str(
                course_data.get("blueprint_revision_id")
                or course_data.get("course_outline_revision_id")
                or ""
            )
            await asyncio.to_thread(
                self._generation_workspace_repository.set_status,
                workspace_id,
                "active",
                result=result,
            )
        course_data = await self._compile_teacher_outline_framework(
            task_id,
            course_data,
            draft=draft,
        )
        if workspace_id:
            await asyncio.to_thread(
                self._generation_workspace_repository.set_status,
                workspace_id,
                "active",
            )
        async with self._lock:
            current = self.tasks.get(task_id)
            if current is None:
                raise KeyError(task_id)
            if current.get("status") not in allowed_statuses:
                raise TaskStateConflict(
                    "Task changed while continuing outline generation",
                    status=str(current.get("status") or "unknown"),
                )
            task = deepcopy(current)
            task["status"] = "pending"
            task["phase"] = "outline_detail_generation"
            task["current_phase"] = "outline_detail_generation"
            task["progress"] = max(32, int(task.get("progress") or 0))
            task["phase_progress"] = 0
            task["phase_detail"] = {
                "artifact_type": "course_outline",
                "status": "pending",
                "stage": "outline_detail_generation",
                "message": "已开始按讲生成完整大纲",
            }
            task["message"] = "已开始按讲生成完整大纲"
            task["outline_detail_requested"] = True
            task["error"] = None
            task["error_detail"] = None
            task["error_code"] = None
            task["error_user_message"] = None
            task["updated_at"] = datetime.now().isoformat()
            task["heartbeat_at"] = task["updated_at"]
            task = self._commit_task_draft(task_id, task)
        await self._task_queue.put(task_id)
        await self._push_progress(task_id)
        return {
            "status": "started",
            "job_id": task_id,
            "course_id": course_id,
            "outline_framework_only": bool(
                course_data.get("outline_framework_only")
            ),
        }

    async def confirm_outline_shape(
        self,
        course_id: str,
        chapter_section_counts: list[int],
    ) -> dict[str, Any]:
        """Freeze teacher-adjusted section counts and resume the same outline job."""
        counts = [int(item) for item in chapter_section_counts]
        if not counts or any(item < 1 or item > 100 for item in counts):
            raise ValueError("Each chapter must contain between 1 and 100 sections")
        if sum(counts) > 1000:
            raise ValueError("The course outline cannot exceed 1000 sections")

        related = [
            task
            for task in self.tasks.values()
            if task.get("course_id") == course_id
            and task.get("type") == "teacher_outline_generation"
        ]
        related.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        if not related:
            raise ValueError("No teacher outline job was found for this course")
        task = related[0]
        task_id = str(task["id"])
        if task.get("outline_shape_confirmed"):
            return {
                "status": "already_confirmed",
                "job_id": task_id,
                "course_id": course_id,
                "chapter_section_counts": counts,
            }
        if (
            task.get("status") != "waiting_for_review"
            or str(task.get("phase") or task.get("current_phase") or "")
            != "outline_shape_ready"
        ):
            raise ValueError("The chapter skeleton is not waiting for review")

        course_data = self._load_task_course(task_id)
        if not course_data:
            raise ValueError("Course not found")
        outline_stage = (
            (course_data.get("generation_stage_artifacts") or {}).get("outline")
            or {}
        )
        raw_skeleton = outline_stage.get("skeleton")
        if not isinstance(raw_skeleton, dict):
            raise ValueError("The chapter skeleton checkpoint is unavailable")
        chapters = [
            deepcopy(item)
            for item in raw_skeleton.get("chapters") or []
            if isinstance(item, dict)
        ]
        if len(counts) != len(chapters):
            raise ValueError("Section counts must match the generated chapter count")
        for chapter, count in zip(chapters, counts, strict=True):
            chapter["section_count"] = count

        request_fingerprint = str(outline_stage.get("request_fingerprint") or "")
        request = {
            **deepcopy(course_data.get("generation_request") or {}),
            **deepcopy(task.get("request_snapshot") or {}),
        }
        topic = str(
            request.get("subject")
            or course_data.get("course_name")
            or raw_skeleton.get("course_title")
            or "课程"
        )
        skeleton = normalize_outline_skeleton(
            {**deepcopy(raw_skeleton), "chapters": chapters},
            topic=topic,
            request_fingerprint=request_fingerprint,
        )
        confirmed_shape = {
            "chapter_count": len(chapters),
            "section_count": sum(counts),
        }
        brief = course_data.get("course_generation_brief") or {}
        report = validate_outline_skeleton(
            skeleton,
            shape_constraints=confirmed_shape,
            request_fingerprint=request_fingerprint,
            course_type_contract=brief.get("course_type_contract") or {},
        )
        if not report.get("passed"):
            messages = "；".join(
                str(item.get("message") or "章节结构无效")
                for item in report.get("issues") or []
            )
            raise ValueError(messages or "The confirmed chapter shape is invalid")

        outline_stage.update({
            "status": "shape_confirmed",
            "shape_confirmed": True,
            "confirmed_shape_constraints": confirmed_shape,
            "shape_confirmation_revision_id": stable_hash(
                {
                    "skeleton_revision_id": skeleton.get("revision_id"),
                    "chapter_section_counts": counts,
                },
                prefix="outline_shape_",
            ),
            "skeleton": skeleton,
            "skeleton_revision_id": skeleton.get("revision_id"),
            "skeleton_validation_report": report,
            "chapter_count": len(chapters),
            "section_count": sum(counts),
            "batches": {},
            "completed_batch_count": 0,
            "completed_section_count": 0,
        })
        course_data["generation_status"] = "outline_shape_confirmed"
        course_data.setdefault("generation_stage_artifacts", {})[
            "outline"
        ] = outline_stage
        await self._save_task_course(task_id, course_data)

        growth = self._outline_shape_growth(
            skeleton,
            state="shape_confirmed",
        )
        async with self._lock:
            current = self.tasks.get(task_id)
            if (
                current is None
                or current.get("status") != "waiting_for_review"
                or str(current.get("phase") or current.get("current_phase") or "")
                != "outline_shape_ready"
            ):
                raise TaskStateConflict(
                    "Task changed while confirming the outline shape",
                    status=str((current or {}).get("status") or "missing"),
                )
            task["outline_shape_confirmed"] = True
            task["status"] = "pending"
            task["phase"] = "outline_shape_confirmed"
            task["current_phase"] = "outline_shape_confirmed"
            task["phase_progress"] = 100
            task["phase_detail"] = {
                "artifact_type": "course_outline_skeleton",
                "skeleton_revision_id": skeleton.get("revision_id"),
                "outline_growth": growth,
            }
            task["message"] = "大章节与逐章小节数已确认，开始生成小章节"
            task["updated_at"] = datetime.now().isoformat()
            task = self._commit_task_draft(task_id, task)
        await self._task_queue.put(task_id)
        await self._push_progress(task_id)
        return {
            "status": "resumed",
            "job_id": task_id,
            "course_id": course_id,
            "chapter_section_counts": counts,
            "skeleton_revision_id": skeleton.get("revision_id"),
            "shape_confirmation_revision_id": outline_stage.get(
                "shape_confirmation_revision_id"
            ),
        }

    async def confirm_generation_step(
        self,
        course_id: str,
        step: str,
    ) -> dict[str, Any]:
        """Confirm a legacy whole-course artifact and resume the same job."""
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
        task = deepcopy(waiting[0])
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
            if any(
                int(node.get("node_level") or 0) == 1
                for node in confirmed.get("nodes") or []
            ):
                confirmed = compile_outline_draft(confirmed)
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
                    impact,
                )
            confirmed = self._accept_outline_research(confirmed)
            confirmed["generation_status"] = "outline_confirmed"
            confirmed["blueprint_revision_id"] = impact.get("draft_blueprint_revision_id")
            frozen = self._version_repository.freeze_blueprint(course_id, confirmed)
            confirmed["blueprint_revision_id"] = frozen["blueprint_revision_id"]
            confirmed["course_outline_revision_id"] = frozen["blueprint_revision_id"]
            course_data = confirmed
            await self._save_task_course(task_id, course_data)
            if reopened_revision and task.get("workspace_id"):
                await asyncio.to_thread(
                    self._generation_workspace_repository.clear_node_drafts,
                    str(task["workspace_id"]),
                )
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
            current = self.tasks.get(task_id)
            current_workflow = (current or {}).get("guided_workflow") or {}
            if (
                current is None
                or current.get("status") != "waiting_for_review"
                or str(current_workflow.get("review_step") or "") != step
            ):
                raise TaskStateConflict(
                    "Task changed while confirming the generation step",
                    status=str((current or {}).get("status") or "missing"),
                )
            task["status"] = "pending"
            task["phase"] = f"{step}_confirmed"
            task["current_phase"] = task["phase"]
            task["phase_progress"] = 100
            task["message"] = {
                "outline": "课程目录已确认，开始确定各节教学重点，并按课时生成详细教案与正文",
                "teaching": "全课教案已确认，开始按小节持续生成课程正文",
                "content": "课程内容已确认，开始执行结构与发布预检",
                "release": "确认发布已完成，正在发布课程",
            }.get(step, "当前步骤已确认，继续生成")
            task["updated_at"] = datetime.now().isoformat()
            task = self._commit_task_draft(task_id, task)
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
        async with self._lock:
            related = [
                task
                for task in self.tasks.values()
                if task.get("course_id") == course_id
                and task.get("type") == "course_generation"
                and isinstance(task.get("guided_workflow"), dict)
            ]
            related.sort(
                key=lambda item: item.get("updated_at", ""),
                reverse=True,
            )
            if not related:
                raise ValueError("No guided outline job was found for this course")
            task = deepcopy(related[0])
            task_id = str(task["id"])
            workflow = task["guided_workflow"]
            state = guided_step_state(workflow, step)
            current_review = str(workflow.get("review_step") or "")

            if (
                task.get("status") == "waiting_for_review"
                and current_review == step
                and state.get("status") == "waiting_for_confirmation"
            ):
                return {
                    "status": "already_reopened",
                    "job_id": task_id,
                    "course_id": course_id,
                    "review_step": step,
                    "previous_artifact_revision": str(
                        state.get("previous_confirmed_revision") or ""
                    ),
                    "invalidated_steps": [],
                    "guided_workflow": deepcopy(workflow),
                    "task": self._task_view(task),
                }

            task_status = str(task.get("status") or "")
            if task_status != "waiting_for_review" or not current_review:
                raise ValueError(
                    "The generation job must be waiting for a later review"
                )
            if (
                GUIDED_STEP_KEYS.index(current_review)
                <= GUIDED_STEP_KEYS.index(step)
            ):
                raise ValueError(
                    "The requested step is not upstream of the current review"
                )
            if state.get("status") != "confirmed":
                raise ValueError("The requested upstream step has not been confirmed")

            previous_revision = str(state.get("artifact_revision") or "")
            invalidated_steps = invalidate_guided_steps_after(workflow, step)
            state["status"] = "waiting_for_confirmation"
            state["confirmed_at"] = None
            state["previous_confirmed_revision"] = previous_revision
            state["input_revisions"] = guided_expected_input_revisions(
                workflow,
                step,
            )
            workflow["current_step"] = step
            workflow["review_step"] = step
            workflow["updated_at"] = datetime.now().isoformat()

            course_data = self._load_task_course(task_id)
            if not course_data:
                raise ValueError("Course not found")
            draft = (
                self._version_repository.load_draft(course_id)
                or build_blueprint_draft(course_data)
            )
            draft["impact_report"] = analyze_blueprint_impact(
                course_data,
                draft,
            )
            self._version_repository.save_draft(course_id, draft)

            task["status"] = "waiting_for_review"
            task["phase"] = "outline_reopened"
            task["current_phase"] = "outline_reopened"
            task["phase_progress"] = 100
            task["message"] = (
                "已进入大纲修订；再次确认后更新正式大纲，"
                "下游教学资产将按影响结果重新核对"
            )
            task["updated_at"] = datetime.now().isoformat()
            task = self._commit_task_draft(task_id, task)
        await self._push_progress(task_id)
        return {
            "status": "reopened",
            "job_id": task_id,
            "course_id": course_id,
            "review_step": step,
            "previous_artifact_revision": previous_revision,
            "invalidated_steps": invalidated_steps,
            "guided_workflow": deepcopy(workflow),
            "task": self._task_view(task),
        }

    async def confirm_blueprint(self, course_id: str) -> dict[str, Any]:
        """Compatibility alias for the former outline-only review endpoint."""
        return await self.confirm_generation_step(course_id, "outline")

    async def retry_course_outline_research(
        self,
        course_id: str,
    ) -> dict[str, Any]:
        """Retry only a failed outline retrieval while preserving the local draft."""

        candidates = [
            task
            for task in self.tasks.values()
            if task.get("course_id") == course_id and task.get("workspace_id")
        ]
        candidates.sort(
            key=lambda item: str(item.get("updated_at") or ""),
            reverse=True,
        )
        if not candidates:
            raise ValueError("Course generation task not found")
        task = candidates[0]
        workflow = task.get("guided_workflow") or {}
        if (
            task.get("status") != "waiting_for_review"
            or workflow.get("review_step") != "outline"
        ):
            raise TaskStateConflict(
                "Outline retrieval can only be retried during outline review",
                status=str(task.get("status") or "unknown"),
            )

        task_id = str(task.get("task_id") or task.get("id") or "")
        course_data = self._load_task_course(task_id)
        if not isinstance(course_data, dict):
            raise ValueError("Course generation workspace not found")
        artifact = (
            (course_data.get("generation_stage_artifacts") or {}).get(
                "web_retrieval"
            )
            or {}
        )
        package = artifact.get("package") or {}
        if artifact.get("status") in {
            "waiting_for_confirmation",
            "completed_no_changes",
            "frozen",
        }:
            raise TaskStateConflict(
                "A successful immutable retrieval package already exists",
                status=str(artifact.get("status") or "completed"),
            )
        previous_revision = max(0, int(package.get("revision") or 0))

        current_draft = self._version_repository.load_draft(course_id)
        retry_course = (
            merge_blueprint_draft(course_data, current_draft)
            if isinstance(current_draft, dict)
            else deepcopy(course_data)
        )
        retry_course.pop("retrieval_package", None)
        retry_course.pop("outline_research", None)
        retry_course.setdefault("generation_stage_artifacts", {}).pop(
            "web_retrieval",
            None,
        )
        retry_course = await self._prepare_course_outline_research(
            retry_course,
            task.get("request_snapshot") or {},
            package_revision=previous_revision + 1,
        )

        retried_artifact = (
            (retry_course.get("generation_stage_artifacts") or {}).get(
                "web_retrieval"
            )
            or {}
        )
        proposal = retried_artifact.get("proposal") or {}
        candidate = deepcopy(
            proposal.get("candidate_draft") or current_draft or {}
        ) or build_blueprint_draft(retry_course)
        candidate["impact_report"] = analyze_blueprint_impact(
            retry_course,
            candidate,
        )
        self._version_repository.save_draft(course_id, candidate)
        await self._save_task_course(task_id, retry_course)
        return deepcopy(retried_artifact)

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
            "_retrieval_actor_id": str(
                (course_data.get("generation_request") or {}).get(
                    "_retrieval_actor_id"
                )
                or ""
            ),
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
                    self._remove_task_strict(task_id)
                    self._task_logs.pop(task_id, None)
                    self._node_retries.pop(task_id, None)
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

    def get_task_summary(self, task_id: str) -> dict[str, Any] | None:
        """Return the lightweight control-plane projection used by polling APIs."""
        task = self.tasks.get(task_id)
        return self._task_summary_view(task) if task else None

    def get_all_tasks(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取所有任务，按状态优先级和时间排序。"""
        status_priority = {
            "running": 0,
            "pending": 1,
            "waiting_for_input": 2,
            "waiting_for_review": 3,
            "paused": 4,
            "failed": 5,
            "completed": 6,
        }
        tasks_list = [self._task_summary_view(task) for task in self.tasks.values()]
        tasks_list.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        tasks_list.sort(
            key=lambda x: status_priority.get(x.get("status", ""), 5)
        )
        return tasks_list[:limit]

    def get_tasks_by_course(self, course_id: str) -> list[dict[str, Any]]:
        """获取指定课程的所有任务。"""
        return [
            self._task_summary_view(task)
            for task in self.tasks.values()
            if task["course_id"] == course_id
        ]

    def get_blueprint_draft(self, course_id: str) -> dict[str, Any] | None:
        """Read the formal unconfirmed blueprint draft without mutating it."""

        draft = self._version_repository.load_draft(course_id)
        return deepcopy(draft) if isinstance(draft, dict) else None

    def get_latest_task_by_course(
        self,
        course_id: str,
        task_type: str | None = None,
    ) -> dict[str, Any] | None:
        """Return the latest task, optionally scoped to one capability type.

        A course can own independent generation, import and slide-deck jobs.
        The optional filter lets a product surface project only the job it owns
        while preserving the legacy latest-task behaviour for existing callers.
        """
        candidates = [
            task for task in self.tasks.values()
            if task.get("course_id") == course_id
            and (task_type is None or task.get("type") == task_type)
        ]
        if not candidates:
            return None
        latest = max(candidates, key=lambda item: str(item.get("updated_at") or ""))
        return self._task_summary_view(latest)

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

    def get_generation_workspace_course_for_task(
        self,
        course_id: str,
        *,
        task_type: str,
        require_confirmed_outline: bool = False,
        require_usable_outline: bool = False,
    ) -> dict[str, Any] | None:
        """Load the newest workspace owned by one generation capability.

        Teacher lesson authoring must keep consuming the newest completed teacher
        outline even when the course already has an older published document.
        Filtering by task type prevents another unfinished generation workspace
        from silently becoming that authoring source.
        """
        candidates = [
            task
            for task in self.tasks.values()
            if task.get("course_id") == course_id
            and task.get("workspace_id")
            and str(task.get("type") or "") == task_type
        ]
        candidates.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        for task in candidates:
            workflow = task.get("guided_workflow")
            if require_confirmed_outline and (
                not isinstance(workflow, dict)
                or not guided_step_confirmed(workflow, "outline")
            ):
                continue
            try:
                workspace_id = str(task["workspace_id"])
                workspace = self._generation_workspace_repository.load(workspace_id)
                if workspace.get("status") == "published":
                    continue
                course = self._generation_workspace_repository.load_course(workspace_id)
                if require_usable_outline:
                    task_completed = str(task.get("status") or "") in {
                        "completed",
                        "completed_with_warnings",
                    }
                    if task_completed and _teacher_outline_result_ready(course):
                        return course
                    last_good = (workspace.get("result") or {}).get(
                        "last_good_course_data"
                    )
                    if _teacher_outline_result_ready(last_good):
                        return deepcopy(last_good)
                    continue
                return course
            except GenerationWorkspaceNotFound:
                continue
        return None

    def get_generation_preview(
        self,
        course_id: str,
        *,
        task_types: set[str] | None = None,
    ) -> dict[str, Any] | None:
        """Project one active generation workspace into a user-safe read model."""
        candidates = [
            task for task in self.tasks.values()
            if task.get("course_id") == course_id and task.get("workspace_id")
            and (task_types is None or str(task.get("type") or "") in task_types)
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
                "learning_path_role": str(
                    raw.get("learning_path_role") or "standard"
                ),
                "path_reason": str(raw.get("path_reason") or "课程主路径"),
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
                "citation_map": deepcopy(raw.get("citation_map") or {}),
                "source_cards": deepcopy(raw.get("source_cards") or []),
                "citation_invalid_refs": deepcopy(
                    raw.get("citation_invalid_refs") or []
                ),
            }
            nodes.append(node)

        return {
            "schema_version": "generation_preview_v2",
            "projection": "generation_workspace",
            "course_id": str(course_data.get("course_id") or course_id),
            "course_name": str(course_data.get("course_name") or task.get("course_name") or ""),
            "course_type": str(
                course_data.get("course_type") or task.get("course_type") or "systematic"
            ),
            "course_intent": deepcopy(course_data.get("course_intent") or {}),
            "learner_starting_profile": deepcopy(
                course_data.get("learner_starting_profile") or {}
            ),
            "workspace_id": workspace_id,
            "workspace_status": str(workspace.get("status") or "active"),
            "updated_at": workspace.get("updated_at") or task.get("updated_at"),
            "task": {
                key: deepcopy(task_view.get(key))
                for key in (
                    "id",
                    "course_id",
                    "course_name",
                    "course_type",
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

    @staticmethod
    def project_course_coverage(course_data: dict[str, Any]) -> dict[str, Any]:
        """Project the outline-stage coverage verdict for the confirmation page.

        Read-only: the verdict is decided during outline planning (D-1) and only
        reshaped here. A course generated before D-1 has no verdict; it is
        reported as ``unknown`` rather than being presented as complete, because
        silence is what made a short course read as a full one in the first place.
        """
        verdict = (
            (course_data.get("generation_stage_artifacts") or {})
            .get("outline") or {}
        ).get("course_coverage_verdict")
        if not isinstance(verdict, dict) or not verdict:
            return {"status": "unknown", "available": False}
        uncovered = [
            str(item) for item in verdict.get("uncovered_topics") or []
        ]
        return {
            "available": True,
            "status": str(verdict.get("status") or "unknown"),
            "scale": str(verdict.get("scale") or ""),
            "scale_label": str(verdict.get("scale_label") or ""),
            "class_hours": verdict.get("class_hours"),
            "may_claim_complete_subject": bool(
                verdict.get("may_claim_complete_subject")
            ),
            "coverage_promise": str(verdict.get("coverage_promise") or ""),
            "required_positioning": str(
                verdict.get("required_positioning") or ""
            ),
            "covered_topics": [
                str(item) for item in verdict.get("covered_topics") or []
            ],
            "uncovered_topics": uncovered,
            "uncovered_count": len(uncovered),
            "advisories": [
                str(item) for item in verdict.get("advisories") or []
            ],
        }

    @staticmethod
    def _outline_review_message(
        coverage: dict[str, Any],
        *,
        is_teacher_outline: bool = False,
    ) -> str:
        """Compose the outline gate message from two independent dimensions.

        They are orthogonal and must not overwrite each other:

        * **视角** (``is_teacher_outline``) decides what happens next -- a teacher
          outline goes on to per-lesson teaching plans, a learner course goes on
          to full-course sections and body text.
        * **覆盖度** (``coverage``) is the honesty verdict from the outline stage:
          whether the requested class hours can actually cover the subject. This
          is the whole point of the D-1 gate -- telling the user *before*
          generation that a course cannot be complete, instead of shipping
          something that calls itself 完整课程 while missing half the subject.

        So the verdict is prepended to whichever next-step sentence applies,
        rather than replacing it.
        """
        next_step = (
            "课程大纲等待确认；确认后可按讲生成教案"
            if is_teacher_outline
            else "课程目录等待确认；确认后将规划全课小节教案并生成正文"
        )
        if not coverage.get("available") or coverage.get("may_claim_complete_subject"):
            return next_step
        label = coverage.get("scale_label") or "当前规格"
        uncovered = int(coverage.get("uncovered_count") or 0)
        verdict = (
            f"本次为{label}，有 {uncovered} 个核心主题不覆盖"
            if uncovered
            else f"本次为{label}，不承担学科完整覆盖"
        )
        return f"{verdict}；{next_step}"

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
            outline_quality = review_course_outline_document(
                plan,
                course_context=course_data,
            )
            artifact = {
                "course_name": str(course_data.get("course_name") or ""),
                "course_type": str(course_data.get("course_type") or "systematic"),
                "course_intent": deepcopy(course_data.get("course_intent") or {}),
                "learner_starting_profile": deepcopy(
                    course_data.get("learner_starting_profile") or {}
                ),
                # D-1：用户在确认目录时就必须看到覆盖度判断，而不是等课程生成完
                # 才发现这门"完整课程"其实没覆盖半个学科。判定在大纲阶段已算好
                # 并落在 outline stage 里，这里只做投影，不重新判定。
                "course_coverage": self.project_course_coverage(course_data),
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
                "quality_report": deepcopy(outline_quality),
                "blocking_issues": deepcopy(
                    outline_quality.get("blocking_issues") or []
                ),
                "sections": [
                    {
                        "node_id": str(node.get("node_id") or ""),
                        "parent_node_id": str(node.get("parent_node_id") or "root"),
                        "name": str(node.get("node_name") or ""),
                        "level": int(node.get("node_level") or 1),
                        "learning_objective": str(node.get("learning_objective") or ""),
                        "scope_boundary": str(node.get("scope_boundary") or ""),
                        "learning_path_role": str(
                            node.get("learning_path_role") or "standard"
                        ),
                        "path_reason": str(
                            node.get("path_reason") or "课程主路径"
                        ),
                    }
                    for node in course_data.get("nodes") or []
                ],
            }
        elif step == "teaching":
            teaching_plan = project_course_teaching_plan(course_data)
            teaching_stage = deepcopy(
                (course_data.get("generation_stage_artifacts") or {}).get(
                    "course_teaching_plan"
                ) or {}
            )
            sections = list(teaching_plan.get("sections") or [])
            artifact = {
                "status": str(teaching_plan.get("status") or teaching_stage.get("status") or ""),
                "section_count": int(teaching_plan.get("section_count") or len(sections)),
                "completed_count": len(sections),
                "knowledge_point_count": int(teaching_plan.get("knowledge_point_count") or 0),
                "teaching_module_count": int(teaching_plan.get("teaching_module_count") or 0),
                "completed_batches": int(teaching_stage.get("completed_batch_count") or teaching_stage.get("completed_batches") or 0),
                "total_batches": int(teaching_stage.get("batch_count") or teaching_stage.get("total_batches") or 0),
                "semantic_status": teaching_stage.get("semantic_status"),
                "sections": deepcopy(sections),
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
            asset_quality = deepcopy(course_data.get("asset_quality_report") or {})
            teaching_stage = deepcopy(
                (course_data.get("generation_stage_artifacts") or {}).get(
                    "course_teaching_plan"
                )
                or {}
            )
            release_blockers = dedupe_quality_issues([
                *deepcopy(quality_report.get("blocking_issues") or []),
                *deepcopy(asset_quality.get("blocking_issues") or []),
            ])
            if teaching_stage.get("semantic_status") == "retry_required":
                release_blockers.append({
                    "code": "teaching_plan:retry_required",
                    "severity": "critical",
                    "message": "全课教案仍有非 AI 语义单元，需要先重试失败批次",
                    "blocking": True,
                })
            artifact = {
                "quality_status": quality_report.get("final_status"),
                "publication_allowed": bool(quality_report.get("publication_allowed")),
                "blocking_issues": release_blockers,
                "asset_blocking_issues": deepcopy(
                    asset_quality.get("blocking_issues") or []
                ),
                "teaching_semantic_status": teaching_stage.get(
                    "semantic_status"
                ),
                "warnings": deepcopy(
                    quality_report.get("warnings")
                    or quality_report.get("quality_warnings")
                    or []
                ) + deepcopy(
                    asset_quality.get("warnings")
                    or asset_quality.get("quality_warnings")
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
                        step != "teaching"
                        or (
                            artifact.get("status") == "completed"
                            and artifact.get("completed_count") == artifact.get("section_count")
                            and artifact.get("semantic_status") != "retry_required"
                        )
                    )
                    and
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

    def _slide_build_recovery_contract(
        self,
        task: dict[str, Any],
    ) -> dict[str, Any]:
        """Return one recovery answer for task polling and explicit resume."""

        task_id = str(task.get("id") or "")
        status = str(task.get("status") or "")
        request_snapshot = _slide_build_task_request(task)
        progress_failure = (
            (task.get("slide_build_progress_v2") or {}).get("failure") or {}
        )
        error_detail = task.get("error_detail") or {}
        is_v6_slide_build = (
            task.get("type") == "slide_deck_variant_build"
            and str(request_snapshot.get("target_schema") or "") == "slide_deck_v6"
        )
        v6_checkpoint_files_available = (
            (
                self._storage_data_dir
                / "slide_deck_v6_candidates"
                / "checkpoints"
                / f"{task_id}.json"
            ).is_file()
            and (
                self._storage_data_dir
                / "slide_build_progress_v2"
                / f"{task_id}.json"
            ).is_file()
        ) if is_v6_slide_build else False
        v6_checkpoint_contract_current = bool(
            is_v6_slide_build
            and str(task.get("slide_build_contract_version") or "")
            == SLIDE_DECK_V6_BUILD_CONTRACT_VERSION
        )
        v6_checkpoint_contract_stale = bool(
            v6_checkpoint_files_available
            and not v6_checkpoint_contract_current
        )
        v6_checkpoint_available = bool(
            v6_checkpoint_files_available
            and v6_checkpoint_contract_current
        )
        failure_retryable = bool(
            progress_failure.get("retryable")
            if isinstance(progress_failure, dict) and "retryable" in progress_failure
            else error_detail.get("retryable")
            if isinstance(error_detail, dict) and "retryable" in error_detail
            else False
        )
        checkpoint = {
            "phase": str(task.get("phase") or "queued"),
            "progress": int(task.get("progress") or 0),
            "completed_representation_types": list(
                task.get("completed_representation_types") or []
            ),
            "last_event_sequence": int(task.get("event_sequence") or 0),
            "updated_at": task.get("updated_at"),
        }
        if status == "completed":
            return {
                "state": "completed",
                "can_resume": False,
                "reason_code": "already_published",
                "reason": "同源教学产物已经通过质量门并发布",
                "checkpoint": checkpoint,
            }
        can_resume = (
            status == "paused"
            and (v6_checkpoint_available if is_v6_slide_build else True)
            or status in {"failed", "error"}
            and (
                failure_retryable and v6_checkpoint_available
                if is_v6_slide_build
                else True
            )
        )
        return {
            "state": (
                "manual_resume"
                if can_resume
                else "auto_resuming"
                if status in {"pending", "running"}
                else "none"
            ),
            "can_resume": can_resume,
            "reason_code": (
                "checkpoint_available"
                if can_resume
                else "checkpoint_contract_stale"
                if v6_checkpoint_contract_stale
                else "job_active"
                if status in {"pending", "running"}
                else "not_needed"
            ),
            "reason": (
                "已完成的页面与产物会被复用，只重建未完成或失效单元"
                if can_resume
                else "生成协议已升级，请重新生成当前组合"
                if v6_checkpoint_contract_stale
                else "同源教学产物任务正在执行"
            ),
            "checkpoint": checkpoint,
        }

    def describe_task_recovery(self, task_id: str) -> dict[str, Any]:
        task = self.tasks.get(task_id)
        if not task:
            raise KeyError(task_id)

        if task.get("type") == "teacher_course_change_generation":
            return {"state": str(task.get("status") or "unknown"), "can_resume": False,
                    "reason_code": "course_change_owned_recovery",
                    "reason": "请在全局修改中继续，已完成候选会保留", "checkpoint": {"plan_id": (task.get("request_snapshot") or {}).get("plan_id")}}
        if task.get("type") == "course_import":
            status = str(task.get("status") or "")
            source_ready = self.import_source_path(task_id).is_file()
            parsed_ready = self.import_checkpoint_path(task_id).is_file()
            checkpoint = {
                "phase": str(task.get("phase") or task.get("current_phase") or "material_receiving"),
                "completed_nodes": int(task.get("completed_nodes") or 0),
                "total_nodes": int(task.get("total_nodes") or 0),
                "draft_node_ids": [],
                "failed_node_ids": [],
                "interrupted_node_ids": [],
                "source_ready": source_ready,
                "parsed_ready": parsed_ready,
                "updated_at": task.get("updated_at"),
            }
            if status == "completed":
                return {
                    "state": "completed",
                    "can_resume": False,
                    "reason_code": "already_imported",
                    "reason": "课程已经完成导入",
                    "checkpoint": checkpoint,
                }
            if status in {"cancelled", "canceled"}:
                return {
                    "state": "cancelled",
                    "can_resume": False,
                    "reason_code": "job_cancelled",
                    "reason": "导入任务已取消，不会恢复原任务",
                    "checkpoint": checkpoint,
                }
            retryable = (
                status in {"paused", "failed", "error"}
                and bool(task.get("import_retryable"))
                and source_ready
            )
            if status in {"failed", "error"} and not retryable:
                return {
                    "state": "unavailable",
                    "can_resume": False,
                    "reason_code": "replace_source_required",
                    "reason": "源文件内容需要修正，请替换文件后重新导入",
                    "checkpoint": checkpoint,
                }
            return {
                "state": "manual_resume" if retryable else "auto_resuming" if status in {"pending", "running"} else "none",
                "can_resume": retryable,
                "reason_code": "checkpoint_available" if retryable else "job_active" if status in {"pending", "running"} else "not_needed",
                "reason": (
                    "已解析的课程结构会被复用，只重试未完成的保存与导出步骤"
                    if retryable and parsed_ready
                    else "原始导入文件已保留，可以重试当前阶段"
                    if retryable
                    else "导入任务正在执行"
                ),
                "checkpoint": checkpoint,
            }

        if task.get("type") in {"teaching_representation_build", "slide_deck_variant_build"}:
            return self._slide_build_recovery_contract(task)

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
        if self._task_is_published(task):
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
        # Same judgement the polling summary uses, so the two projections cannot
        # disagree about whether this job is resumable.
        unavailable_reason = self._checkpoint_unavailable_reason(task)
        if unavailable_reason and unavailable_reason != "checkpoint_not_supported":
            return {
                **base,
                "state": "unavailable",
                "reason_code": unavailable_reason,
                "reason": self._CHECKPOINT_UNAVAILABLE_REASONS[
                    unavailable_reason
                ],
            }
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
            "phase": self._effective_phase(task),
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
            or task.get("publication_allowed") is False
            or workspace.get("status") == "quality_failed"
        ):
            return self._quality_recovery_contract(
                task,
                base=base,
                checkpoint=checkpoint,
                has_checkpoint=True,
                course_data=course_data,
            )
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
                        "已确认全部知识节点，并保留 "
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

    @staticmethod
    def _restore_confirmed_outline_identity(
        course_data: dict[str, Any],
        confirmed_snapshot: dict[str, Any],
        *,
        expected_revision: str,
        request: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Restore only frozen outline identity fields after derived drift.

        The candidate is accepted only when its artifact hash exactly matches
        the revision the user confirmed. Course content and every downstream
        field remain untouched.
        """
        current_nodes = {
            str(node.get("node_id") or ""): node
            for node in course_data.get("nodes") or []
            if isinstance(node, dict) and node.get("node_id")
        }
        confirmed_nodes = [
            node
            for node in confirmed_snapshot.get("nodes") or []
            if isinstance(node, dict) and node.get("node_id")
        ]
        confirmed_ids = [str(node.get("node_id") or "") for node in confirmed_nodes]
        if not confirmed_ids or set(confirmed_ids) != set(current_nodes):
            return None

        identity_fields = (
            "node_id",
            "parent_node_id",
            "node_name",
            "node_level",
            "learning_objective",
            "prerequisite_node_ids",
            "scope_boundary",
            "assessment",
        )
        restored = deepcopy(course_data)
        restored["course_name"] = str(
            confirmed_snapshot.get("course_name")
            or course_data.get("course_name")
            or ""
        )
        confirmed_outline = (
            confirmed_snapshot.get("course_outline")
            or confirmed_snapshot.get("course_plan")
            or {}
        )
        if not isinstance(confirmed_outline, dict) or not confirmed_outline.get(
            "chapters"
        ):
            return None
        restored["course_outline"] = deepcopy(confirmed_outline)

        restored_nodes: list[dict[str, Any]] = []
        for confirmed_node in confirmed_nodes:
            node_id = str(confirmed_node.get("node_id") or "")
            restored_node = deepcopy(current_nodes[node_id])
            for field in identity_fields:
                if field in confirmed_node:
                    restored_node[field] = deepcopy(confirmed_node[field])
                else:
                    restored_node.pop(field, None)
            restored_nodes.append(restored_node)
        restored["nodes"] = restored_nodes

        actual_revision = guided_artifact_revision(
            "outline",
            restored,
            request=request or {},
        )
        if actual_revision != expected_revision:
            return None
        return restored

    def _restore_task_confirmed_outline_snapshot(
        self,
        task: dict[str, Any],
        course_data: dict[str, Any],
    ) -> dict[str, Any]:
        workflow = task.get("guided_workflow")
        if not isinstance(workflow, dict):
            raise CourseVersionConflict("Missing guided workflow for outline repair")
        outline_state = guided_step_state(workflow, "outline")
        expected_revision = str(outline_state.get("artifact_revision") or "")
        blueprint_revision = str(course_data.get("course_outline_revision_id") or "")
        if not expected_revision or not blueprint_revision:
            raise CourseVersionConflict("Missing confirmed outline revision")
        try:
            snapshot = self._version_repository.get_blueprint_revision(
                str(task.get("course_id") or course_data.get("course_id") or ""),
                blueprint_revision,
            )
        except KeyError as exc:
            raise CourseVersionConflict(
                "Confirmed outline snapshot is unavailable"
            ) from exc
        restored = self._restore_confirmed_outline_identity(
            course_data,
            snapshot,
            expected_revision=expected_revision,
            request=task.get("request_snapshot") or {},
        )
        if restored is None:
            raise CourseVersionConflict(
                "Confirmed outline snapshot does not match the approved revision"
            )
        repairs = restored.setdefault("generation_lineage_repairs", [])
        repairs.append({
            "schema_version": "generation_lineage_repair_v1",
            "repair_type": "restore_confirmed_outline_snapshot",
            "blueprint_revision_id": blueprint_revision,
            "artifact_revision": expected_revision,
            "repaired_at": datetime.now().isoformat(),
        })
        return restored

    @staticmethod
    def _quality_failure_summary(
        course_data: dict[str, Any],
        *,
        previous: dict[str, Any] | None = None,
        advance_repeat: bool = False,
    ) -> dict[str, Any]:
        quality_report = course_data.get("generation_quality_report") or {}
        asset_quality = course_data.get("asset_quality_report") or {}
        source_chain = course_data.get("generation_source_chain_report") or {}
        source_chain_issues = [
            {
                **deepcopy(issue),
                "severity": str(issue.get("severity") or "critical"),
                "suggestion": str(
                    issue.get("suggestion")
                    or "恢复已确认的版本链，重新核对发布输入修订"
                ),
                "target_id": str(issue.get("step") or "release"),
            }
            for issue in source_chain.get("issues") or []
            if isinstance(issue, dict)
        ]
        issues = dedupe_quality_issues([
            *deepcopy(quality_report.get("blocking_issues") or []),
            *deepcopy(asset_quality.get("blocking_issues") or []),
            *source_chain_issues,
        ])
        blockers: list[dict[str, Any]] = []
        scopes: set[str] = set()
        supported = bool(issues)
        for issue in issues:
            code = str(issue.get("code") or issue.get("issue_id") or "quality:unknown")
            target_id = str(
                issue.get("node_id")
                or issue.get("asset_id")
                or issue.get("target_id")
                or ""
            )
            is_asset = bool(issue.get("asset_type")) or code.startswith("asset:")
            if code == "difficulty:double_spike":
                scopes.add("difficulty_contract")
            elif (
                code == "outline_revision_mismatch"
                and course_data.get("course_outline_revision_id")
            ):
                scopes.add("confirmed_outline_snapshot")
            elif is_asset and str(issue.get("asset_type") or "questions") == "questions":
                scopes.add("learning_assets")
            else:
                supported = False
                scopes.add("manual_review")
            blockers.append({
                "code": code,
                "severity": str(issue.get("severity") or "critical"),
                "message": str(issue.get("message") or "课程质量检查未通过"),
                "suggestion": str(issue.get("suggestion") or "按阻断提示局部修复后重新检查"),
                "target_id": target_id,
                "target_type": "asset" if is_asset else "node" if target_id else "course",
                "gate": str(issue.get("gate") or ""),
                "asset_type": str(issue.get("asset_type") or ""),
            })
        fingerprint = stable_hash(
            [
                {
                    "code": item["code"],
                    "message": item["message"],
                    "target_id": item["target_id"],
                }
                for item in blockers
            ],
            prefix="qf_",
        )
        previous = previous if isinstance(previous, dict) else {}
        same_policy = (
            previous.get("repair_policy_version") == QUALITY_REPAIR_POLICY_VERSION
        )
        same_failure = (
            bool(blockers)
            and previous.get("fingerprint") == fingerprint
            and same_policy
        )
        previous_count = int(previous.get("repeat_count") or 0)
        repeat_count = (
            previous_count + 1
            if same_failure and advance_repeat
            else previous_count
            if same_failure
            else 1
        )
        order = [
            "difficulty_contract",
            "confirmed_outline_snapshot",
            "learning_assets",
            "manual_review",
        ]
        return {
            "fingerprint": fingerprint,
            "repair_policy_version": QUALITY_REPAIR_POLICY_VERSION,
            "repeat_count": repeat_count,
            "blocker_count": len(blockers),
            "repair_scopes": [scope for scope in order if scope in scopes],
            "supported": supported,
            "blockers": blockers[:50],
            "truncated": len(blockers) > 50,
        }

    def _quality_recovery_contract(
        self,
        task: dict[str, Any],
        *,
        base: dict[str, Any],
        checkpoint: dict[str, Any],
        has_checkpoint: bool,
        course_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        previous = task.get("quality_failure")
        quality_failure = (
            self._quality_failure_summary(
                course_data,
                previous=previous if isinstance(previous, dict) else None,
            )
            if isinstance(course_data, dict)
            else deepcopy(previous) if isinstance(previous, dict) else None
        )
        if quality_failure:
            unchanged = int(quality_failure.get("repeat_count") or 0) >= 2
            supported = bool(quality_failure.get("supported"))
            can_resume = bool(has_checkpoint and supported and not unchanged)
            if unchanged:
                reason_code = "quality_gate_unchanged"
                reason = "同一批质量阻断项已连续两次未变化，已停止自动重跑；请按下方明细人工处理"
            elif not supported:
                reason_code = "quality_gate_manual_action_required"
                reason = "阻断项超出安全自动修复范围；请按下方明细人工处理后再检查"
            else:
                count = int(quality_failure.get("blocker_count") or 0)
                reason_code = "quality_gate_failed"
                reason = f"正文和教案已保留；继续后将定向修复 {count} 项阻断并重新执行发布检查"
        else:
            # Legacy jobs may not have persisted a bounded summary yet. The
            # detailed resume endpoint reloads the workspace before mutating.
            can_resume = bool(has_checkpoint)
            reason_code = "quality_gate_failed"
            reason = "正文和教案已保留；继续前将重新读取阻断明细并确认安全修复范围"
        result = {
            **base,
            "state": "quality_blocked",
            "can_resume": can_resume,
            "reason_code": reason_code,
            "reason": reason,
            "checkpoint": checkpoint,
        }
        if quality_failure:
            result["quality_failure"] = quality_failure
        return result

    def _task_recovery_summary(self, task: dict[str, Any]) -> dict[str, Any]:
        """Build a polling-safe recovery summary without loading course payloads."""
        status = str(task.get("status") or "")
        phase = str(task.get("phase") or task.get("current_phase") or "")
        if task.get("type") == "course_import":
            task_id = str(task.get("id") or "")
            source_ready = self.import_source_path(task_id).is_file()
            parsed_ready = self.import_checkpoint_path(task_id).is_file()
            checkpoint = {
                "phase": phase,
                "completed_nodes": int(task.get("completed_nodes") or 0),
                "total_nodes": int(task.get("total_nodes") or 0),
                "draft_node_ids": [],
                "failed_node_ids": [],
                "interrupted_node_ids": [],
                "source_ready": source_ready,
                "parsed_ready": parsed_ready,
                "updated_at": task.get("updated_at"),
            }
            if status == "completed":
                return {
                    "state": "completed", "can_resume": False,
                    "reason_code": "already_imported", "reason": "课程已经完成导入",
                    "checkpoint": checkpoint,
                }
            if status in {"cancelled", "canceled"}:
                return {
                    "state": "cancelled", "can_resume": False,
                    "reason_code": "job_cancelled",
                    "reason": "导入任务已取消，不会恢复原任务",
                    "checkpoint": checkpoint,
                }
            retryable = (
                status in {"paused", "failed", "error"}
                and bool(task.get("import_retryable"))
                and source_ready
            )
            if status in {"failed", "error"} and not retryable:
                return {
                    "state": "unavailable", "can_resume": False,
                    "reason_code": "replace_source_required",
                    "reason": "源文件内容需要修正，请替换文件后重新导入",
                    "checkpoint": checkpoint,
                }
            return {
                "state": "manual_resume" if retryable else "auto_resuming" if status in {"pending", "running"} else "none",
                "can_resume": retryable,
                "reason_code": "checkpoint_available" if retryable else "job_active" if status in {"pending", "running"} else "not_needed",
                "reason": (
                    "已解析的课程结构会被复用，只重试未完成的保存与导出步骤"
                    if retryable and parsed_ready
                    else "原始导入文件已保留，可以重试当前阶段"
                    if retryable
                    else "导入任务正在执行"
                ),
                "checkpoint": checkpoint,
            }
        if task.get("type") in {
            "teaching_representation_build",
            "slide_deck_variant_build",
        }:
            return self._slide_build_recovery_contract(task)
        detail = task.get("phase_detail")
        if not isinstance(detail, dict):
            detail = {}
        workflow = task.get("guided_workflow")
        if not isinstance(workflow, dict):
            workflow = {}
        step_states = {
            str(item.get("key") or ""): str(item.get("status") or "")
            for item in workflow.get("steps") or []
            if isinstance(item, dict)
        }
        completed_nodes = int(task.get("completed_nodes") or 0)
        total_nodes = int(task.get("total_nodes") or 0)
        checkpoint = {
            "phase": self._effective_phase(task),
            "assessment_generation_profile": str(
                task.get("assessment_generation_profile")
                or "complete"
            ),
            "assessment_generation_policy_version": str(
                task.get("assessment_generation_policy_version")
                or ASSESSMENT_GENERATION_POLICY_VERSION
            ),
            "completed_nodes": completed_nodes,
            "total_nodes": total_nodes,
            "draft_node_ids": list((task.get("node_drafts") or {}).keys()),
            "failed_node_ids": [],
            "interrupted_node_ids": [],
            "requirements_ready": bool(task.get("request_snapshot")),
            "outline_ready": bool(
                task.get("blueprint_confirmed")
                or step_states.get("outline") == "confirmed"
            ),
            "teaching_plan_ready": bool(
                step_states.get("teaching") == "confirmed"
                or phase in {
                    "content_generation",
                    "content_partial",
                    "learning_assets",
                    "content_validation",
                    "release_ready",
                    "release_confirmed",
                    "completed",
                }
            ),
            "completed_teaching_plan_batches": int(
                detail.get("completed_batches") or 0
            ),
            "total_teaching_plan_batches": int(detail.get("total_batches") or 0),
            "completed_teaching_plan_sections": int(
                detail.get("completed_items") or 0
            ) if "teaching" in phase else 0,
            "total_teaching_plan_sections": int(
                detail.get("total_items") or 0
            ) if "teaching" in phase else 0,
            "completed_knowledge_packages": int(
                detail.get("completed_items") or 0
            ) if "knowledge" in phase else 0,
            "total_knowledge_packages": int(
                detail.get("total_items") or 0
            ) if "knowledge" in phase else 0,
            "workspace_status": task.get("workspace_status"),
            "updated_at": task.get("updated_at"),
        }
        base = {
            "state": "none",
            "can_resume": False,
            "reason_code": "not_needed",
            "reason": "当前任务不需要恢复",
            "checkpoint": checkpoint,
        }
        if self._task_is_published(task):
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
        if status in {"pending", "running"}:
            if task.get("last_recovery_reason") in {"service_restart", "manual_resume"}:
                return {
                    **base,
                    "state": "auto_resuming",
                    "reason_code": "job_recovering",
                    "reason": "任务正在从最近保存点继续",
                }
            return base

        has_checkpoint = bool(task.get("workspace_id") or task.get("candidate_id"))
        # Presence of an id is not proof the checkpoint survives; ask the shared
        # judgement so this projection cannot advertise a resume that
        # describe_task_recovery would refuse.
        unavailable_reason = self._checkpoint_unavailable_reason(task)
        if status == "completed_with_warnings" and (
            phase == "quality_failed" or task.get("publication_allowed") is False
        ):
            return self._quality_recovery_contract(
                task,
                base=base,
                checkpoint=checkpoint,
                has_checkpoint=has_checkpoint,
            )
        if status in {"paused", "failed", "error", "completed_with_warnings"}:
            if unavailable_reason:
                return {
                    **base,
                    "state": "unavailable",
                    "reason_code": unavailable_reason,
                    "reason": self._CHECKPOINT_UNAVAILABLE_REASONS[
                        unavailable_reason
                    ],
                }
            return {
                **base,
                "state": "manual_resume",
                "can_resume": True,
                "reason_code": (
                    "checkpoint_available"
                    if checkpoint["outline_ready"] or total_nodes
                    else "stage_restart_available"
                ),
                "reason": "已保存的课程现场会被复用，可以从中断步骤继续",
            }
        return base

    def _task_summary_view(self, task: dict[str, Any]) -> dict[str, Any]:
        view = {
            key: deepcopy(value)
            for key, value in task.items()
            if key not in PUBLIC_TASK_OMITTED_FIELDS
            and key not in {"logs", "owner_id"}
        }
        last_event = task.get("last_event") or {}
        blocked_quality = (
            last_event.get("quality")
            if isinstance(last_event, dict)
            and last_event.get("event") == "build_blocked"
            else None
        )
        public_quality = _public_representation_quality(blocked_quality)
        if "quality" not in view and public_quality is not None:
            view["quality"] = public_quality
        view["logs"] = deepcopy((task.get("logs") or [])[-PUBLIC_TASK_LOG_LIMIT:])
        view["recovery"] = self._task_recovery_summary(task)
        return view

    def _task_view(self, task: dict[str, Any]) -> dict[str, Any]:
        view = deepcopy(task)
        view["recovery"] = self.describe_task_recovery(str(task["id"]))
        return view

    def _checkpoint_unavailable_reason(
        self,
        task: dict[str, Any],
    ) -> str | None:
        """Single answer to "is this job's saved checkpoint still usable?".

        Returns a ``reason_code`` when the checkpoint cannot be resumed, or
        ``None`` when it can.

        This exists for the same reason as ``_task_is_published``: the polling
        summary and the resume path must not describe the same job differently.
        The summary used to infer a usable checkpoint from the presence of a
        ``workspace_id`` on the task record, while the resume path loaded the
        workspace and answered ``workspace_missing``. A job whose workspace had
        been deleted therefore polled as "可以恢复" and refused on click.

        Existence is checked without reading the payload, so this stays cheap
        enough for the per-poll summary.
        """
        workspace_id = str(task.get("workspace_id") or "")
        candidate_id = str(task.get("candidate_id") or "")
        if workspace_id:
            if not self._generation_workspace_repository.exists(workspace_id):
                return "workspace_missing"
            return None
        if candidate_id:
            try:
                candidate = self._version_repository.load_candidate(
                    str(task.get("course_id") or ""),
                    candidate_id,
                )
            except KeyError:
                return "candidate_missing"
            if not isinstance(candidate.get("course_data"), dict):
                return "candidate_invalid"
            return None
        return "checkpoint_not_supported"

    _CHECKPOINT_UNAVAILABLE_REASONS = {
        "workspace_missing": "生成工作区已丢失，无法安全继续原任务",
        "candidate_missing": "课程候选版本已丢失，无法安全继续原任务",
        "candidate_invalid": "课程候选版本不完整，无法安全继续原任务",
        "checkpoint_not_supported": "该旧任务没有独立检查点，无法安全继续",
    }

    def _task_is_published(self, task: dict[str, Any]) -> bool:
        """Single answer to "did this job actually publish a course?".

        Both recovery projections must agree, otherwise the task list and the
        resume button describe the same job differently.

        ``completed`` is conclusive on its own. ``completed_with_warnings`` is
        not: a job can finish with warnings and never reach publication, so it
        only counts when a publication receipt exists. A receipt is also
        authoritative for a job still marked ``running`` — that is how a restart
        recognises work that finished publishing before the process died.
        """
        status = str(task.get("status") or "")
        if status == "completed":
            return True
        if status == "completed_with_warnings" and task.get("publication_allowed") is False:
            return False
        return self._publication_receipt(task) is not None

    # 恢复过程中会被短暂盖上去的阶段。它们说明"正在回到工作状态"，
    # 但答不了"回到哪一阶段"——投影直接回显它们，用户就只看得到"正在继续"。
    _TRANSIENT_PHASES = frozenset({"resuming"})

    def _effective_phase(self, task: dict[str, Any]) -> str:
        """Single answer to "which stage is this job at?".

        ``_process_task`` derives the real stage from the guided workflow via
        ``_processing_handoff`` and stamps it. Between a resume request and that
        stamp the stored phase reads ``resuming``, so a projection that echoes
        the stored value tells the task list one thing while the job is about to
        report another. Both recovery projections ask this instead, which is why
        the list, the resume dialog and the running job name the same stage.

        A stored phase that is not transient is authoritative and returned
        unchanged — this only fills the gap, it does not second-guess the job.
        """
        phase = str(task.get("phase") or task.get("current_phase") or "")
        if phase and phase not in self._TRANSIENT_PHASES:
            return phase
        derived, _message = self._processing_handoff(task)
        return derived or phase

    def _failed_node_report_entry(
        self, task_id: str, node: dict[str, Any]
    ) -> dict[str, Any]:
        """One failed section, as the production stage renders it.

        Carries the stable code alongside the raw text so the UI can explain the
        failure and say whether continuing is worth attempting, instead of
        printing a truncated exception string.
        """
        node_id = str(node.get("node_id") or "")
        return {
            "node_id": node_id,
            "node_name": node.get("node_name", ""),
            "error": node.get("error_summary", "Unknown error"),
            "error_code": node.get("error_code") or "generation_failed",
            "retryable": bool(node.get("error_retryable", True)),
            "retry_count": self._node_retries.get(task_id, {}).get(node_id, 0),
        }

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
        if task.get("type") == "teacher_course_change_generation":
            if task.get("status") not in {"pending", "running"}:
                return False
            task["status"] = "pending"
            task["message"] = "正在恢复未完成的修改候选"
            return True
        if task.get("type") == "course_import":
            if task.get("status") not in {"pending", "running"}:
                return False
            if not self.import_source_path(task_id).is_file():
                task["status"] = "failed"
                task["phase"] = "recovery_unavailable"
                task["current_phase"] = "recovery_unavailable"
                task["error_code"] = "import_source_missing"
                task["error_user_message"] = "导入源文件已不存在，请重新选择文件"
                task["message"] = task["error_user_message"]
                task["updated_at"] = datetime.now().isoformat()
                task["heartbeat_at"] = task["updated_at"]
                return False
            task["status"] = "pending"
            task["phase"] = "resuming"
            task["current_phase"] = "resuming"
            task["message"] = "服务重启后正恢复课程导入"
            task["updated_at"] = datetime.now().isoformat()
            task["heartbeat_at"] = task["updated_at"]
            return True
        if task.get("type") in {"teaching_representation_build", "slide_deck_variant_build"}:
            if task.get("status") not in {"pending", "running"}:
                return False
            if task.get("type") == "slide_deck_variant_build":
                restart_count = int(task.get("restart_recovery_count") or 0)
                if restart_count >= 3:
                    task["status"] = "failed"
                    task["phase"] = "recovery_unavailable"
                    task["current_phase"] = "recovery_unavailable"
                    task["message"] = (
                        "Slide build exceeded the bounded restart recovery limit"
                    )
                    task["error"] = task["message"]
                    task["error_detail"] = {
                        "stage": "recovery",
                        "code": "restart_recovery_limit_exceeded",
                        "message": task["message"],
                        "retryable": True,
                        "chapter_id": "",
                        "page_id": "",
                        "batch_id": "",
                    }
                    task["updated_at"] = datetime.now().isoformat()
                    return False
                request = _slide_build_task_request(task)
                selector = request.get("template_selector") or {}
                recovery_key = (
                    str(task.get("course_id") or ""),
                    str(request.get("mode") or "teaching"),
                    str(request.get("theme") or "qizhi-classroom"),
                    str(request.get("target_schema") or ""),
                    bool(request.get("shadow_only")),
                    str(request.get("chapter_id") or ""),
                    str(selector.get("pack_id") or ""),
                    str(selector.get("version") or ""),
                )
                newer_equivalent = next(
                    (
                        candidate
                        for candidate_id, candidate in self.tasks.items()
                        if candidate_id != task_id
                        and candidate.get("type") == "slide_deck_variant_build"
                        and candidate.get("status") in {"pending", "running"}
                        and (
                            str(candidate.get("course_id") or ""),
                            str(_slide_build_task_request(candidate).get("mode") or "teaching"),
                            str(_slide_build_task_request(candidate).get("theme") or "qizhi-classroom"),
                            str(_slide_build_task_request(candidate).get("target_schema") or ""),
                            bool(_slide_build_task_request(candidate).get("shadow_only")),
                            str(_slide_build_task_request(candidate).get("chapter_id") or ""),
                            str((_slide_build_task_request(candidate).get("template_selector") or {}).get("pack_id") or ""),
                            str((_slide_build_task_request(candidate).get("template_selector") or {}).get("version") or ""),
                        ) == recovery_key
                        and (
                            str(candidate.get("created_at") or ""),
                            str(candidate_id),
                        ) > (
                            str(task.get("created_at") or ""),
                            str(task_id),
                        )
                    ),
                    None,
                )
                if newer_equivalent is not None:
                    task["status"] = "cancelled"
                    task["phase"] = "superseded"
                    task["current_phase"] = "superseded"
                    task["message"] = (
                        "A newer equivalent slide build owns restart recovery"
                    )
                    task["error_detail"] = {
                        "stage": "recovery",
                        "code": "superseded_build_not_recovered",
                        "message": task["message"],
                        "retryable": False,
                        "chapter_id": "",
                        "page_id": "",
                        "batch_id": "",
                    }
                    task["updated_at"] = datetime.now().isoformat()
                    return False
            task["status"] = "pending"
            task["phase"] = "resuming"
            task["current_phase"] = "resuming"
            task["message"] = "服务重启后正从最近同源产物保存点恢复"
            task["restart_recovery_count"] = int(task.get("restart_recovery_count") or 0) + 1
            task["last_recovery_reason"] = "service_restart"
            task["updated_at"] = datetime.now().isoformat()
            return True
        if task.get("type") not in {
            "course_generation",
            "teacher_outline_generation",
        }:
            return False
        if await self._restart_legacy_compact_review_on_complete_pipeline(
            task_id,
            task,
        ):
            return True
        if await self._reconcile_release_review_after_restart(task_id, task):
            return False
        if (
            task.get("status") == "completed_with_warnings"
            and task.get("phase") == "quality_failed"
        ):
            course_data = self._load_task_course(task_id) or {}
            quality_report = build_final_course_quality_report(course_data, job_id=task_id)
            if self._quality_allows_publication(course_data, quality_report):
                logger.info("Re-evaluating publishable quality warning task %s", task_id)
                # A prior source-chain decision may have set publication_allowed
                # to false even though the immutable content candidate has no
                # quality blockers. Replace that derived decision before
                # completion so _complete_task cannot reuse the stale report.
                course_data["generation_quality_report"] = quality_report
                await self._save_task_course(task_id, course_data)
                reactivated = await self._update_task_status(
                    task_id,
                    "running",
                    message="正在重新核对历史质量阻断并完成发布",
                    allow_reactivation=True,
                )
                if reactivated:
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

    @staticmethod
    def _mark_release_gate_blocked(workflow: dict[str, Any]) -> None:
        """Remove an impossible release confirmation from the review state."""
        release_state = guided_step_state(workflow, "release")
        release_state["status"] = "needs_regeneration"
        release_state["artifact_revision"] = None
        release_state["input_revisions"] = {}
        release_state["confirmed_at"] = None
        workflow["current_step"] = "release"
        workflow["review_step"] = None
        workflow["updated_at"] = datetime.now().isoformat()

    @staticmethod
    def _repair_release_math_boundaries(course_data: dict[str, Any]) -> list[str]:
        """Apply safe formatting-only repairs to persisted release candidates."""
        repaired_node_ids: list[str] = []
        recoverable_codes = {
            "legacy_math_delimiter",
            "unclosed_math_fence",
        }
        for node in course_data.get("nodes") or []:
            if int(node.get("node_level") or 1) != 2:
                continue
            content = str(node.get("node_content") or "")
            report = evaluate_node_content(content, node)
            issue_codes = {
                str(item.get("code") or "")
                for item in report.get("issues") or []
            }
            if not issue_codes.intersection(recoverable_codes):
                continue

            changed = False
            blocks = node.get("content_blocks")
            if isinstance(blocks, list) and blocks:
                for block in blocks:
                    if not isinstance(block, dict):
                        continue
                    original = str(block.get("content") or "")
                    fixed = fix_latex_content(original)
                    if fixed != original:
                        block["content"] = fixed
                        changed = True
                if changed:
                    # Preserve logical block IDs and metadata while refreshing
                    # fingerprints, revisions and the aggregate Markdown.
                    set_node_content_blocks(node, content)
            else:
                fixed = fix_latex_content(content)
                if fixed != content:
                    node.pop("content_blocks", None)
                    set_node_content_blocks(node, fixed)
                    changed = True

            if not changed:
                continue
            node["generation_quality"] = evaluate_node_content(
                str(node.get("node_content") or ""),
                node,
            )
            repaired_node_ids.append(str(node.get("node_id") or ""))
        return repaired_node_ids

    async def _reconcile_release_review_after_restart(
        self,
        task_id: str,
        task: dict[str, Any],
    ) -> bool:
        """Re-evaluate persisted release gates instead of preserving a dead review.

        Older jobs could be saved as ``waiting_for_review`` even though the
        same artifact was stamped ``publication_allowed=false``. On restart we
        deterministically re-run the current quality rules, repair only safe
        math fence formatting, and either restore a genuinely confirmable
        release gate or settle the job as ``quality_failed``.
        """
        workflow = task.get("guided_workflow")
        if (
            task.get("status") != "waiting_for_review"
            or not isinstance(workflow, dict)
            or str(workflow.get("review_step") or "") != "release"
        ):
            return False
        course_data = self._load_task_course(task_id)
        if not isinstance(course_data, dict):
            return False
        stored_quality = course_data.get("generation_quality_report") or {}
        stored_source_chain = course_data.get("generation_source_chain_report") or {}
        if (
            stored_quality.get("publication_allowed") is True
            and stored_source_chain.get("can_publish") is True
        ):
            # A healthy release review already has a clickable confirmation
            # and must remain byte-for-byte stable across restarts.
            return False

        fresh_course = deepcopy(course_data)
        repaired_node_ids = self._repair_release_math_boundaries(fresh_course)
        if repaired_node_ids and guided_step_confirmed(workflow, "content"):
            content_state = guided_step_state(workflow, "content")
            content_state["artifact_revision"] = guided_artifact_revision(
                "content",
                fresh_course,
                request=task.get("request_snapshot") or {},
            )
            content_state["input_revisions"] = guided_expected_input_revisions(
                workflow,
                "content",
            )

        asset_plan = fresh_course.get("learning_asset_plan") or {}
        learning_assets = fresh_course.get("learning_assets") or {}
        if asset_plan and learning_assets:
            fresh_course["asset_quality_report"] = evaluate_learning_asset_quality(
                fresh_course,
                asset_plan,
                learning_assets,
            )
        asset_quality = fresh_course.get("asset_quality_report") or {}
        quality_report = build_final_course_quality_report(
            fresh_course,
            job_id=task_id,
        )
        quality_report["asset_quality"] = asset_quality
        if (
            quality_report.get("final_status") == "passed"
            and asset_quality
            and not asset_quality.get("passed", False)
        ):
            quality_report["final_status"] = "completed_with_warnings"

        publication_allowed = self._quality_allows_publication(
            fresh_course,
            quality_report,
        )
        source_chain_report = build_source_chain_report(
            workflow,
            fresh_course,
            request=task.get("request_snapshot") or {},
        )
        publication_allowed = bool(
            publication_allowed and source_chain_report.get("can_publish")
        )
        quality_report["publication_allowed"] = publication_allowed
        quality_report["source_chain_passed"] = bool(
            source_chain_report.get("can_publish")
        )
        fresh_course["generation_quality_report"] = quality_report
        fresh_course["generation_source_chain_report"] = source_chain_report
        await self._save_task_course(task_id, fresh_course)

        task["release_gate_reconciled_at"] = datetime.now().isoformat()
        task["release_gate_repaired_node_ids"] = repaired_node_ids
        if publication_allowed:
            await self._pause_for_guided_review(
                task_id,
                fresh_course,
                "release",
                phase="release_ready",
                progress=98,
                message="全部检查通过，等待确认发布",
                phase_detail={
                    "publication_allowed": True,
                    "source_chain_passed": True,
                    "blocking_issue_count": 0,
                    "restart_reconciled": True,
                    "repaired_node_ids": repaired_node_ids,
                },
            )
            return True

        self._mark_release_gate_blocked(workflow)
        await self._complete_task(task_id, fresh_course)
        return True

    async def _restart_legacy_compact_review_on_complete_pipeline(
        self,
        task_id: str,
        task: dict[str, Any],
    ) -> bool:
        """Rebuild legacy compact outlines instead of preserving their size cap.

        Review gates normally survive service restarts unchanged. V16 makes one
        deliberate migration exception: a pre-V16 course whose outline did not
        come from the hierarchical pipeline must be rebuilt before the user can
        confirm either the outline or release. This repairs already-open 3x2
        courses even if the user continued generating before deployment, without
        touching current full-pipeline reviews or published courses.
        """
        workflow = task.get("guided_workflow")
        if (
            task.get("status") != "waiting_for_review"
            or not isinstance(workflow, dict)
            or str(workflow.get("review_step") or "") not in {"outline", "release"}
        ):
            return False
        course_data = self._load_task_course(task_id) or {}
        pipeline_version = str(
            course_data.get("generation_pipeline_version")
            or course_data.get("generation_schema_version")
            or ""
        )
        outline_stage = (
            (course_data.get("generation_stage_artifacts") or {}).get("outline")
            or {}
        )
        if (
            not pipeline_version.startswith("course_generation_v")
            or pipeline_version == PIPELINE_VERSION
            or outline_stage.get("strategy") == "hierarchical_chapter_batches"
            or not course_data.get("course_outline")
        ):
            return False

        rebuilt = deepcopy(course_data)
        for field in (
            "course_plan",
            "course_outline",
            "course_blueprint",
            "course_outline_constraint_report",
            "blueprint_validation_report",
            "blueprint_revision_id",
            "course_outline_revision_id",
            "course_teaching_plan",
            "course_knowledge_base",
            "course_knowledge_map",
            "course_knowledge_graph",
            "generation_quality_report",
            "generation_source_chain_report",
            "learning_asset_plan",
            "learning_assets",
        ):
            rebuilt.pop(field, None)
        rebuilt["nodes"] = []
        rebuilt["knowledge_relations"] = []
        rebuilt["generation_stage_artifacts"] = {}
        rebuilt["generation_status"] = "outline_rebuild_required"
        await self._save_task_course(task_id, rebuilt)
        workspace_id = str(task.get("workspace_id") or "")
        if workspace_id:
            await asyncio.to_thread(
                self._generation_workspace_repository.clear_node_drafts,
                workspace_id,
            )
        self._version_repository.delete_draft(str(task.get("course_id") or ""))

        invalidate_guided_steps_after(workflow, "outline")
        outline_state = guided_step_state(workflow, "outline")
        outline_state["status"] = "pending"
        outline_state["confirmed_at"] = None
        outline_state["artifact_revision"] = None
        workflow["current_step"] = "outline"
        workflow["review_step"] = None
        workflow["updated_at"] = datetime.now().isoformat()
        task["status"] = "pending"
        task["phase"] = "outline_rebuild_required"
        task["current_phase"] = "outline_rebuild_required"
        task["phase_progress"] = 0
        task["message"] = "旧版精简目录正在按完整课程链路重新生成"
        task["blueprint_confirmed"] = False
        task.pop("blueprint_revision_id", None)
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
            draft = deepcopy(current)
            draft["status"] = "paused"
            draft["message"] = "已暂停"
            draft["updated_at"] = datetime.now().isoformat()
            task = self._commit_task_draft(task_id, draft)
        await self._cancel_runtime_tasks(task_id)
        await self._push_progress(task_id)

    async def resume_task(self, task_id: str) -> dict[str, Any]:
        """Resume one durable generation job from its existing checkpoint."""
        task = self.tasks.get(task_id)
        if not task:
            raise KeyError(task_id)
        recovery_task_type = task.get("type")

        def observe(
            payload: dict[str, Any],
            result: str,
            *,
            trigger: str = "manual_resume",
        ) -> dict[str, Any]:
            record_recovery_result(
                task_type=recovery_task_type,
                trigger=trigger,
                result=result,
            )
            return payload

        if task.get("type") == "course_import":
            recovery = self.describe_task_recovery(task_id)
            if task.get("status") in {"pending", "running"}:
                return observe(
                    {"status": "already_active", "task": self._task_view(task)},
                    "skipped",
                )
            if task.get("status") == "completed":
                return observe(
                    {"status": "completed", "task": self._task_view(task)},
                    "completed",
                )
            if not recovery.get("can_resume"):
                record_recovery_result(
                    task_type=recovery_task_type,
                    trigger="manual_resume",
                    result="unavailable",
                )
                raise TaskRecoveryConflict(
                    str(recovery.get("reason") or "当前导入任务无法继续"),
                    recovery=recovery,
                )
            async with self._lock:
                current = self.tasks.get(task_id)
                if current is None:
                    raise KeyError(task_id)
                task = deepcopy(current)
                parsed_ready = bool((recovery.get("checkpoint") or {}).get("parsed_ready"))
                task["status"] = "pending"
                task["phase"] = "resuming"
                task["current_phase"] = "resuming"
                task["progress"] = 20 if parsed_ready else 5
                task["phase_progress"] = 0
                task["message"] = "正在从导入保存点继续"
                task["error"] = None
                task["error_code"] = None
                task["error_user_message"] = None
                task["import_retryable"] = False
                task["retry_count"] = int(task.get("retry_count") or 0) + 1
                task["updated_at"] = datetime.now().isoformat()
                task["heartbeat_at"] = task["updated_at"]
                task = self._commit_task_draft(task_id, task)
            await self._task_queue.put(task_id)
            await self._push_progress(task_id)
            return observe(
                {"status": "resumed", "task": self._task_view(task)},
                "resumed",
            )

        if task.get("type") in {"teaching_representation_build", "slide_deck_variant_build"}:
            recovery = self.describe_task_recovery(task_id)
            if task.get("status") in {"pending", "running"}:
                return observe(
                    {"status": "already_active", "task": self._task_view(task)},
                    "skipped",
                )
            if task.get("status") == "completed":
                return observe(
                    {"status": "completed", "task": self._task_view(task)},
                    "completed",
                )
            if not recovery.get("can_resume"):
                record_recovery_result(
                    task_type=recovery_task_type,
                    trigger="manual_resume",
                    result="unavailable",
                )
                raise TaskRecoveryConflict(
                    str(recovery.get("reason") or "当前同源产物任务无法继续"),
                    recovery=recovery,
                )
            async with self._lock:
                current = self.tasks.get(task_id)
                if current is None:
                    raise KeyError(task_id)
                task = deepcopy(current)
                task["status"] = "pending"
                task["phase"] = "resuming"
                task["current_phase"] = "resuming"
                task["message"] = "正在从最近同源产物保存点继续"
                task["error"] = None
                task["error_detail"] = None
                task["error_code"] = None
                slide_progress = task.get("slide_build_progress_v2")
                if (
                    task.get("type") == "slide_deck_variant_build"
                    and isinstance(slide_progress, dict)
                ):
                    slide_progress = deepcopy(slide_progress)
                    slide_progress["status"] = "active"
                    slide_progress["failure"] = None
                    task["slide_build_progress_v2"] = slide_progress
                task["retry_count"] = int(task.get("retry_count") or 0) + 1
                task["updated_at"] = datetime.now().isoformat()
                task = self._commit_task_draft(task_id, task)
            await self._task_queue.put(task_id)
            await self._push_progress(task_id)
            return observe(
                {"status": "resumed", "task": self._task_view(task)},
                "resumed",
            )

        recovery = self.describe_task_recovery(task_id)
        quality_repair = recovery.get("state") == "quality_blocked"
        quality_failure = recovery.get("quality_failure") or {}
        repair_scopes = set(quality_failure.get("repair_scopes") or [])
        recovery_trigger = (
            "quality_gate_repair" if quality_repair else "manual_resume"
        )
        if task.get("status") in {"pending", "running"}:
            return observe(
                {"status": "already_active", "task": self._task_view(task)},
                "skipped",
                trigger=recovery_trigger,
            )
        if recovery.get("state") == "completed":
            return observe(
                {"status": "completed", "task": self._task_view(task)},
                "completed",
                trigger=recovery_trigger,
            )
        if not recovery.get("can_resume"):
            record_recovery_result(
                task_type=recovery_task_type,
                trigger=recovery_trigger,
                result="unavailable",
            )
            raise TaskRecoveryConflict(
                str(recovery.get("reason") or "当前任务无法从原检查点继续"),
                recovery=recovery,
            )

        checkpoint_course = self._load_task_course(task_id) or {}
        checkpoint_request = checkpoint_course.get("generation_request") or {}
        async with self._lock:
            current = self.tasks.get(task_id)
            if current is None:
                raise KeyError(task_id)
            if current.get("status") in {"pending", "running"}:
                return observe(
                    {
                        "status": "already_active",
                        "task": self._task_view(current),
                    },
                    "skipped",
                    trigger=recovery_trigger,
                )
            task = deepcopy(current)
            # Terminal task summaries intentionally omit the large request
            # snapshot.  A resumed generation task must hydrate that request
            # from its isolated workspace before it becomes active again;
            # otherwise defaults silently replace the teacher's confirmed
            # course shape and can regenerate a different outline.
            if (
                task.get("type") in {
                    "course_generation",
                    "teacher_outline_generation",
                }
                and isinstance(checkpoint_request, dict)
                and checkpoint_request
            ):
                task["request_snapshot"] = {
                    **deepcopy(checkpoint_request),
                    **deepcopy(task.get("request_snapshot") or {}),
                }
            task["status"] = "pending"
            task["phase"] = "quality_repair" if quality_repair else "resuming"
            task["current_phase"] = task["phase"]
            task["message"] = (
                f"正在保留课程正文并准备修复 {int(quality_failure.get('blocker_count') or 0)} 项质量阻断"
                if quality_repair
                else "正在确认保存点并恢复任务"
            )
            if quality_repair:
                task["quality_repair_requested"] = True
                task["quality_repair_scopes"] = sorted(repair_scopes)
                if "confirmed_outline_snapshot" in repair_scopes:
                    task["outline_repair_requested"] = True
                if "learning_assets" in repair_scopes:
                    task["asset_repair_requested"] = True
            task["updated_at"] = datetime.now().isoformat()
            task = self._commit_task_draft(task_id, task)

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
                    reason=(
                        "quality_gate_repair"
                        if quality_repair
                        else "manual_resume"
                    ),
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
                current = self.tasks.get(task_id)
                if current is None:
                    raise KeyError(task_id)
                draft = deepcopy(current)
                draft["status"] = "failed"
                draft["phase"] = "recovery_unavailable"
                draft["current_phase"] = "recovery_unavailable"
                draft["message"] = unavailable["reason"]
                draft["error"] = unavailable["reason"]
                draft["updated_at"] = datetime.now().isoformat()
                task = self._commit_task_draft(task_id, draft)
            record_recovery_result(
                task_type=recovery_task_type,
                trigger=recovery_trigger,
                result="unavailable",
            )
            raise TaskRecoveryConflict(str(unavailable["reason"]), recovery=unavailable) from exc
        except Exception:
            async with self._lock:
                current = self.tasks.get(task_id)
                if current is None:
                    raise KeyError(task_id)
                draft = deepcopy(current)
                draft["status"] = "failed"
                draft["phase"] = "recovery_failed"
                draft["current_phase"] = "recovery_failed"
                draft["message"] = "恢复检查点时发生错误，原内容未被重新生成"
                draft["error"] = draft["message"]
                draft["updated_at"] = datetime.now().isoformat()
                task = self._commit_task_draft(task_id, draft)
            record_recovery_result(
                task_type=recovery_task_type,
                trigger=recovery_trigger,
                result="failed",
            )
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
            "quality_repair"
            if quality_repair
            else
            "content_generation"
            if knowledge_ready or has_content_checkpoint
            else "course_teaching_plan"
            if has_outline
            else "requirement_analysis"
        )
        progress_cap = (
            94
            if quality_repair
            else 50
            if knowledge_ready or has_content_checkpoint
            else 35
            if has_outline
            else 0
        )
        async with self._lock:
            current = self.tasks.get(task_id)
            if current is None:
                raise KeyError(task_id)
            draft = deepcopy(current)
            draft["status"] = "pending"
            draft["phase"] = phase
            draft["current_phase"] = phase
            draft["progress"] = min(int(draft.get("progress") or 0), progress_cap)
            draft["phase_progress"] = 0
            draft["message"] = (
                "已保留全部课程内容，等待定向修复质量阻断"
                if quality_repair
                else "已从保存点恢复，等待继续"
            )
            draft["error"] = None
            draft["current_nodes"] = []
            draft["current_node_name"] = ""
            draft["recovery_count"] = int(draft.get("recovery_count") or 0) + 1
            draft["last_recovery_reason"] = (
                "quality_gate_repair"
                if quality_repair
                else "manual_resume"
            )
            draft["updated_at"] = datetime.now().isoformat()
            self._node_retries[task_id] = {}
            task = self._commit_task_draft(task_id, draft)
        await self._task_queue.put(task_id)
        await self._push_progress(task_id)
        return observe(
            {"status": "resumed", "task": self._task_view(task)},
            "resumed",
            trigger=recovery_trigger,
        )

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
                "pending", "running", "paused", "waiting_for_input",
                "waiting_for_review",
            }:
                draft = deepcopy(current)
                draft["status"] = "cancelled"
                draft["phase"] = "cancelled"
                draft["current_phase"] = "cancelled"
                draft["message"] = "任务已取消，正在清理生成状态"
                draft["updated_at"] = datetime.now().isoformat()
                self._commit_task_draft(task_id, draft)
        await self._cancel_runtime_tasks(task_id)
        await self._cleanup_task_artifacts(task_snapshot)
        async with self._lock:
            self._remove_task_strict(task_id)
            self._task_logs.pop(task_id, None)
            self._node_retries.pop(task_id, None)
            self._running_node_tasks.pop(task_id, None)
            self._running_job_tasks.pop(task_id, None)

    async def clear_failed_tasks(self, *, owner_id: str | None = None) -> int:
        """清理失败任务，返回清理数量。"""
        failed_ids = [
            task_id for task_id, task in self.tasks.items()
            if task.get("status") == "failed"
            and (
                owner_id is None
                or not _persisted_task_owner_id(task)
                or _persisted_task_owner_id(task) == owner_id
            )
        ]
        removed = 0
        for task_id in failed_ids:
            try:
                await self.delete_task(task_id)
                removed += 1
            except KeyError:
                continue
        return removed

    async def clear_task_records(
        self,
        scope: str,
        *,
        course_id: str | None = None,
        owner_id: str | None = None,
    ) -> list[str]:
        """Delete terminal task records without touching active jobs."""
        if scope not in {"invalid", "completed"}:
            raise ValueError(scope)

        def matches(task: dict[str, Any]) -> bool:
            if course_id and str(task.get("course_id") or "") != course_id:
                return False
            task_owner_id = _persisted_task_owner_id(task)
            if owner_id is not None and task_owner_id and task_owner_id != owner_id:
                return False
            status = str(task.get("status") or "")
            recovery_state = str((task.get("recovery") or {}).get("state") or "")
            published_warning = (
                status == "completed_with_warnings"
                and (
                    task.get("publication_allowed") is True
                    or recovery_state == "completed"
                )
            )
            if scope == "completed":
                return status == "completed" or published_warning
            return (
                status in {"failed", "error", "conflict", "cancelled"}
                or (status == "completed_with_warnings" and not published_warning)
            )

        task_ids = [
            task_id
            for task_id, task in self.tasks.items()
            if matches(task)
        ]
        removed_ids: list[str] = []
        for task_id in task_ids:
            try:
                await self.delete_task(task_id)
                removed_ids.append(task_id)
            except KeyError:
                continue
        return removed_ids

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
        if task.get("type") == "teacher_course_change_generation":
            # Candidate assets belong to their domain repositories, not this job.
            return
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
            task_id,
            "running",
            message=f"正在重试节点 {node_id}...",
            allow_reactivation=True,
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
            task_id,
            "running",
            message="正在重试失败节点...",
            allow_reactivation=True,
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
                task = self.tasks.get(task_id) or {}
                record_task_wait(
                    task_type=task.get("type"),
                    queued_at=task.get("updated_at") or task.get("created_at"),
                )
                await self._process_task(task_id)
        except asyncio.CancelledError:
            task = self.tasks.get(task_id)
            if task and task.get("status") not in (
                "paused",
                "cancelled",
                "waiting_for_input",
            ):
                await self._update_task_status(task_id, "pending", message="任务中断，等待恢复")
            raise
        except Exception as exc:
            logger.error("Error processing task %s: %s", task_id, exc, exc_info=True)
            # A cancel/pause request makes in-flight workers raise an ordinary
            # exception (see the teaching-representation progress callback), so
            # this handler races the request. ``cancelled`` and ``paused`` are
            # deliberate terminal states: overwriting them with ``failed`` would
            # report the user's own cancellation back to them as a build error.
            task = self.tasks.get(task_id)
            if task and task.get("status") in (
                "paused",
                "cancelled",
                "waiting_for_input",
            ):
                logger.info(
                    "Task %s ended with %s after it was %s; keeping the requested state",
                    task_id, exc, task.get("status"),
                )
            else:
                failure = classify_generation_failure(exc)
                record_model_error(
                    error_code=failure["code"],
                    retryable=failure["retryable"],
                )
                error_detail = (
                    exc.public_detail()
                    if isinstance(
                        exc,
                        (SlideStoryPlanPrerequisiteError, SlideDeckV5BuildError, V6BuildError),
                    )
                    else {
                        "code": failure["code"],
                        "translation_key": failure["translation_key"],
                        "retryable": failure["retryable"],
                    }
                )
                await self._update_task_status(
                    task_id,
                    "failed",
                    error=failure["technical_detail"],
                    error_detail=error_detail,
                )
                await self._record_workspace_failure(
                    task_id, failure["technical_detail"]
                )
        finally:
            self._running_job_tasks.pop(task_id, None)

    async def _schedule_nodes(
        self, task_id: str, nodes: list[dict]
    ) -> bool:
        """按固定正文并发预算调度所有小节。

        `prerequisite_node_ids` 是学习顺序，不是正文生成依赖。正文只读取已经
        已确认的全课教案，因此一个小节失败不会阻断其他小节。

        **Validates: Requirements 3.3, 3.4**

        Args:
            task_id: 任务 ID
            nodes: 待调度的节点列表
        """
        sorted_nodes = sorted(
            nodes, key=lambda n: (n.get("node_level", 1), nodes.index(n))
        )

        tasks: list[asyncio.Task[Any]] = []
        for node in sorted_nodes:
            if self._is_content_complete(node):
                continue
            node_id = node.get("node_id", "")
            task_obj = asyncio.create_task(
                self._process_node(task_id, node)
            )
            self._running_node_tasks.setdefault(task_id, {})[
                node_id
            ] = task_obj
            tasks.append(task_obj)

        if not tasks:
            return True
        # Course size determines how many bounded node units enter the queue;
        # it must not create a fixed wall-clock failure for otherwise healthy
        # streams.  Each node owns an inactivity watchdog, so this gather still
        # settles when a provider stalls without prematurely pausing a large
        # course that continues to make progress.
        await asyncio.gather(*tasks, return_exceptions=True)
        return True

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
            "正在编译已确认的知识节点、能力包与稳定 ID",
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

    async def _process_slide_deck_variant_v6(
        self,
        *,
        task_id: str,
        document: Any,
        course_view: dict[str, Any],
        mode: str,
        theme: str,
        variant_key: str,
        template_contract: TemplateLayoutPackContractV1,
        template_digest_provider: Callable[[], str],
        source_revision_provider: Callable[[], str],
        publish_result: bool = True,
        shadow_context: dict[str, Any] | None = None,
        visual_repair: dict[str, Any] | None = None,
    ) -> None:
        """Run the strict V6 candidate through the shared durable boundary."""

        orchestrator = SlideDeckV6Orchestrator(
            representation_repository=teaching_representation_repository,
            candidate_repository=SlideDeckV6CandidateRepository(
                self._storage_data_dir / "slide_deck_v6_candidates"
            ),
            progress_root=self._storage_data_dir / "slide_build_progress_v2",
        )

        async def record_v6_progress(payload: dict[str, object]) -> None:
            event = {
                "event": "slide_build_progress_v2",
                "progress": int(payload.get("percent") or 0),
                "stage": str(payload.get("stage") or "building"),
                "message": "V6 slide build is following the persisted server work plan",
                "slide_build_progress_v2": deepcopy(payload),
            }
            await self._record_representation_event(task_id, event)

        common = {
            "task_id": task_id,
            "document": document,
            "course_data": course_view,
            "mode": mode,
            "theme": theme,
            "story_planner": build_ai_base_story_planner_v6(),
            "visual_planner": build_ai_base_visual_planner_v2(),
            "source_revision_provider": source_revision_provider,
            "template_contract": template_contract,
            "template_digest_provider": template_digest_provider,
            "progress_callback": record_v6_progress,
        }
        if visual_repair:
            result = await orchestrator.repair_visuals(
                **common,
                representation_id=str(visual_repair.get("representation_id") or ""),
                target_page_ids=[
                    str(page_id)
                    for page_id in visual_repair.get("target_page_ids") or []
                    if str(page_id)
                ],
            )
        else:
            result = await orchestrator.build(
                **common,
                publish_result=publish_result,
                shadow_context=shadow_context,
            )
        public_result = {
            "build": result,
            "quality": result.get("quality") or {},
            "registry": result.get("registry") or {},
            "variant_key": variant_key,
            "target_schema": "slide_deck_v6",
            "shadow_context": dict(shadow_context or {}),
            "operation": (
                "repair_slide_visuals_v6"
                if visual_repair
                else "build_slide_deck_variant"
            ),
        }
        final_status = (
            "completed_with_warnings"
            if result.get("candidate_status") == "v6_needs_manual_edit"
            else "completed"
        )
        async with self._lock:
            current = self.tasks.get(task_id)
            if not current or str(current.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES:
                return
            current["result"] = public_result
            current["completed_representation_types"] = (
                [f"slide_deck:{variant_key}"] if publish_result else []
            )
            current["progress"] = 100
            current["phase_progress"] = 100
            current["phase"] = "complete"
            current["current_phase"] = "complete"
            current["message"] = (
                "V6 shadow candidate completed with pages marked for manual review"
                if not publish_result and final_status == "completed_with_warnings"
                else "V6 shadow candidate passed all fidelity and render gates"
                if not publish_result
                else "V6 deck published with pages marked for manual review"
                if final_status == "completed_with_warnings"
                else "V6 deck passed the fidelity gates and was published"
            )
            current["updated_at"] = datetime.now().isoformat()
            self.save_tasks()
        await self._record_representation_event(
            task_id,
            {"event": "build_complete", "progress": 100, **public_result},
        )
        await self._update_task_status(
            task_id,
            final_status,
            message=str(self.tasks.get(task_id, {}).get("message") or "V6 build complete"),
        )

    async def _process_slide_deck_variant_task(self, task_id: str) -> None:
        """Build one mode/theme PPT variant without rebuilding sibling artifacts."""
        task = self.tasks.get(task_id)
        if not task or str(task.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES:
            return
        request = _slide_build_task_request(task)
        course_id = str(task["course_id"])
        mode = str(request.get("mode") or "teaching")
        theme = normalize_slide_deck_theme(str(request.get("theme") or "qizhi-classroom"))
        variant_key = str(
            request.get("variant_key") or slide_deck_variant_key(mode, theme)
        )
        if not await self._update_task_status(
            task_id,
            "running",
            message=f"正在生成 {variant_key} 课程课件",
        ):
            return
        document, canonical = await asyncio.to_thread(
            self._course_document_repository.load_document, course_id,
        )
        requested_schema = str(request.get("target_schema") or "")
        operation = str(request.get("operation") or "build_slide_deck_variant")
        visual_repair = (
            {
                "representation_id": str(request.get("representation_id") or ""),
                "target_page_ids": [
                    str(page_id)
                    for page_id in request.get("target_page_ids") or []
                    if str(page_id)
                ],
            }
            if operation == "repair_slide_visuals_v6"
            else None
        )
        if visual_repair and not visual_repair["representation_id"]:
            raise V6BuildError(
                stage="visual_repair",
                code="visual_repair_base_unavailable",
                message="Visual repair requires a published representation ID",
                retryable=False,
            )
        shadow_only = bool(request.get("shadow_only"))
        chapter_id = str(request.get("chapter_id") or "").strip()
        if not canonical and not (requested_schema == "slide_deck_v6" and shadow_only):
            raise CourseDocumentConflict("Course must be canonical before building slide variants")
        source_course_document_revision = str(document.document_revision or "")
        if shadow_only:
            document = compile_shadow_chapter_document(document, chapter_id)
        course_view = await asyncio.to_thread(
            self._course_document_repository.load_course_view, course_id,
        )
        course_view = deepcopy(course_view)
        course_view["generation_request"] = {
            **(course_view.get("generation_request") or {}),
            "web_image_retrieval": deepcopy(
                request.get("web_image_retrieval") or {}
            ),
            "template_pack": deepcopy(request.get("template_pack") or {}),
        }
        story_engine_enabled = os.getenv(
            "SLIDE_STORY_ENGINE_V2_ENABLED",
            "true",
        ).strip().lower() in {"1", "true", "yes", "on"}
        slide_schema = resolve_slide_deck_schema(
            course_view,
            story_engine_enabled=story_engine_enabled,
            v5_enabled=os.getenv(
                "SLIDE_DECK_V5_ENABLED",
                "true",
            ).strip().lower() in {"1", "true", "yes", "on"},
            v6_enabled=requested_schema == "slide_deck_v6",
        )
        use_story_engine = slide_schema in {"slide_deck_v4", "slide_deck_v5", "slide_deck_v6"}
        source_revision = str(document.document_revision or "")
        await self._record_representation_event(task_id, {
            "event": "build_contract",
            "progress": 2,
            "stage": "source_preflight",
            "target_schema": slide_schema,
            "source_revision": source_revision,
        })
        if slide_schema == "slide_deck_v6":
            frozen_template_payload = request.get("template_contract")
            template_contract = (
                TemplateLayoutPackContractV1.model_validate(frozen_template_payload)
                if isinstance(frozen_template_payload, dict)
                else compile_builtin_template_layout_contract_v1(theme)
            )
            selector = request.get("template_selector") or {}
            pack_id = str(selector.get("pack_id") or "")
            if pack_id:
                pack_version = int(
                    selector.get("version") or template_contract.template_version
                )
                owner_id = str(selector.get("owner_id") or "")

                def current_template_digest() -> str:
                    return ppt_template_pack_repository.resolve_v6_layout_contract(
                        pack_id,
                        pack_version,
                        owner_id,
                    ).template_digest
            else:
                def current_template_digest() -> str:
                    if visual_repair:
                        return template_contract.template_digest
                    return compile_builtin_template_layout_contract_v1(
                        template_contract.theme_id
                    ).template_digest
            if shadow_only:
                def current_source_revision() -> str:
                    current_document, _ = self._course_document_repository.load_document(course_id)
                    return compile_shadow_chapter_document(
                        current_document,
                        chapter_id,
                    ).document_revision
            else:
                def current_source_revision() -> str:
                    return str(
                        self._course_document_repository.load_document(course_id)[0].document_revision
                        or ""
                    )
            await self._process_slide_deck_variant_v6(
                task_id=task_id,
                document=document,
                course_view=course_view,
                mode=mode,
                theme=theme,
                variant_key=variant_key,
                template_contract=template_contract,
                template_digest_provider=current_template_digest,
                source_revision_provider=current_source_revision,
                publish_result=not shadow_only,
                shadow_context=(
                    {
                        "chapter_id": chapter_id,
                        "source_course_document_revision": source_course_document_revision,
                        "source_format": "canonical" if canonical else "legacy_projection",
                    }
                    if shadow_only
                    else None
                ),
                visual_repair=visual_repair,
            )
            return
        saved_revision = str(task.get("representation_source_document_revision") or "")
        saved_variant = str(task.get("representation_variant_key") or "")
        expected_signature = (
            build_signature_v5(
                document=document,
                course_data=course_view,
                mode=mode,  # type: ignore[arg-type]
                theme=theme,  # type: ignore[arg-type]
            )
            if slide_schema == "slide_deck_v5"
            else build_signature_v4(
                document=document,
                course_data=course_view,
                mode=mode,  # type: ignore[arg-type]
                theme=theme,  # type: ignore[arg-type]
            )
            if slide_schema == "slide_deck_v4"
            else build_signature(
                source_document_revision=source_revision,
                mode=mode,
                theme=theme,
                compiler_version=SLIDE_DECK_V3_COMPILER_VERSION,
                theme_version=slide_theme_version(),
            )
        )
        saved_signature = str(task.get("representation_build_signature") or "")
        allocation_plan: SlideAllocationPlanV2 | None = None
        visual_plan: SlideVisualPlanV1 | None = None
        story_plan: SlideStoryPlanV2 | None = None
        resume_slides: list[dict[str, Any]] = []
        if (
            not bool(request.get("force_rebuild"))
            and saved_revision == source_revision
            and saved_variant == variant_key
            and saved_signature == expected_signature["signature"]
        ):
            try:
                raw_story = task.get("representation_story_plan_v2")
                if use_story_engine and isinstance(raw_story, dict):
                    story_plan = SlideStoryPlanV2.model_validate(raw_story)
            except (TypeError, ValueError):
                story_plan = None
            try:
                raw_plan = task.get("representation_deck_plan_v3")
                if isinstance(raw_plan, dict):
                    allocation_plan = SlideAllocationPlanV2.model_validate(raw_plan)
            except (TypeError, ValueError):
                allocation_plan = None
            try:
                raw_visual_plan = task.get("representation_visual_plan_v1")
                if isinstance(raw_visual_plan, dict):
                    resumed_visual_plan = deepcopy(raw_visual_plan)
                    pages_by_id = {
                        str(page.get("page_id") or ""): page
                        for page in resumed_visual_plan.get("pages") or []
                    }
                    for event in task.get("event_history") or []:
                        if (
                            event.get("event") != "asset_ready"
                            or not isinstance(event.get("visual_anchor"), dict)
                        ):
                            continue
                        page = pages_by_id.get(str(event.get("page_id") or ""))
                        if page is not None:
                            page["visual_anchor"] = deepcopy(event["visual_anchor"])
                    visual_plan = SlideVisualPlanV1.model_validate(resumed_visual_plan)
            except (TypeError, ValueError):
                visual_plan = None
            latest_slides: dict[str, dict[str, Any]] = {}
            for event in task.get("event_history") or []:
                if event.get("event") == "quality_fallback":
                    latest_slides = {}
                    continue
                if event.get("event") != "slide_upsert" or not isinstance(event.get("slide"), dict):
                    continue
                if (
                    slide_schema == "slide_deck_v5"
                    and (
                        event.get("engine_schema") != "slide_deck_v5"
                        or event.get("candidate_stage") not in {
                            "final_contract",
                            "render_verified",
                        }
                    )
                ):
                    continue
                slide = deepcopy(event["slide"])
                unit_id = str(slide.get("unit_id") or "")
                if unit_id:
                    latest_slides[unit_id] = slide
            resume_slides = sorted(
                latest_slides.values(),
                key=lambda item: int(item.get("position") or 0),
            )
            if use_story_engine and story_plan is None:
                allocation_plan = None
                visual_plan = None
                resume_slides = []
        if allocation_plan is None:
            await self._record_representation_event(task_id, {
                "event": "fragmenting",
                "progress": 3,
                "stage": "fragmenting",
                "variant_key": variant_key,
            })
            if use_story_engine:
                source_fragments = fragment_course_document(document)
                story_baseline = None
                if slide_schema == "slide_deck_v5":
                    story_baseline = compact_story_plan_v5(
                        document,
                        compile_slide_story_plan_v2(
                            document,
                            course_view,
                            source_fragments,
                            mode=mode,  # type: ignore[arg-type]
                            theme=theme,  # type: ignore[arg-type]
                        ),
                        source_fragments,
                    )
                story_plan = await plan_slide_story_v2(
                    document,
                    course_view,
                    source_fragments,
                    mode=mode,  # type: ignore[arg-type]
                    theme=theme,  # type: ignore[arg-type]
                    baseline=story_baseline,
                    ai_planner=_source_first_story_ai_worker(),
                )
                allocation_compiler = (
                    allocation_from_story_plan_v5
                    if slide_schema == "slide_deck_v5"
                    else allocation_from_story_plan_v2
                )
                allocation_plan, _ = allocation_compiler(
                    document,
                    source_fragments,
                    story_plan,
                )
                await self._record_representation_event(task_id, {
                    "event": "story_plan",
                    "progress": 6,
                    "stage": "story_plan",
                    "story_plan": story_plan.model_dump(mode="json"),
                    "variant_key": variant_key,
                })
                for chapter_index, chapter in enumerate(story_plan.chapters):
                    await self._record_representation_event(task_id, {
                        "event": "chapter_plan",
                        "progress": min(14, 8 + chapter_index),
                        "stage": "chapter_plan",
                        "chapter_id": chapter.chapter_id,
                        "chapter": chapter.model_dump(mode="json"),
                    })
                    for episode_index, episode in enumerate(chapter.episodes):
                        await self._record_representation_event(task_id, {
                            "event": "episode_progress",
                            "progress": min(18, 10 + episode_index),
                            "stage": "episode_progress",
                            "chapter_id": chapter.chapter_id,
                            "episode_id": episode.episode_id,
                            "scene_kind": episode.scene_kind,
                        })
                await self._record_representation_event(task_id, {
                    "event": "layout_plan",
                    "progress": 20,
                    "stage": "layout_plan",
                    "allocation_plan": allocation_plan.model_dump(mode="json"),
                })
            else:
                planner, reviewer = _source_first_slide_ai_workers()
                allocation_plan = await plan_slide_deck_v3(
                    document,
                    course_view,
                    mode=mode,  # type: ignore[arg-type]
                    theme=theme,  # type: ignore[arg-type]
                    ai_planner=planner,
                    ai_reviewer=reviewer,
                )
            resume_slides = []
        preflight = (
            {
                "passed": True,
                "score": 100,
                "issues": [],
                "blockers": [],
                "warnings": [],
                "estimated_slide_count": len(allocation_plan.pages),
                "maximum_slide_count": None,
            }
            if slide_schema == "slide_deck_v5"
            else slide_deck_preflight_quality(allocation_plan)
        )
        bundle_parts = []
        if not preflight["passed"]:
            bundle_parts = split_slide_deck_plan_by_chapter(
                document,
                allocation_plan,
            )
            await self._record_representation_event(task_id, {
                "event": "bundle_plan",
                "progress": 20,
                "stage": "bundle_plan",
                "quality": preflight,
                "variant_key": variant_key,
                "part_count": len(bundle_parts),
                "parts": [
                    {
                        "part_id": part.part_id,
                        "title": part.title,
                        "chapter_ids": part.chapter_ids,
                        "estimated_slide_count": len(part.allocation_plan.pages),
                    }
                    for part in bundle_parts
                ],
            })
            visual_plan = None
            resume_slides = []
        if visual_plan is None and not bundle_parts:
            visual_plan = await plan_slide_visuals(
                document,
                allocation_plan,
                fragment_course_document(document),
                ai_planner=_source_first_slide_visual_ai_worker(),
            )
            resume_slides = []
        if (
            allocation_plan is not None
            and visual_plan is not None
        ):
            async with self._lock:
                current = self.tasks.get(task_id)
                if not current or str(current.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES:
                    return
                current["representation_source_document_revision"] = source_revision
                current["representation_variant_key"] = variant_key
                current["representation_deck_plan_v3"] = allocation_plan.model_dump(mode="json")
                current["representation_story_plan_v2"] = (
                    story_plan.model_dump(mode="json")
                    if story_plan is not None
                    else None
                )
                current["representation_visual_plan_v1"] = visual_plan.model_dump(mode="json")
                current["representation_build_signature"] = expected_signature["signature"]
                current["updated_at"] = datetime.now().isoformat()
                self.save_tasks()
        await self._record_representation_event(task_id, {
            "event": "deck_plan",
            "progress": 8,
            "stage": "slide_plan",
            "strategy": "source_fragments_then_allocate",
            "planner": allocation_plan.planner,
            "fallback_reason": allocation_plan.fallback_reason,
            "estimated_slide_count": len(allocation_plan.pages),
            "variant_key": variant_key,
            "target_schema": slide_schema,
        })
        loop = asyncio.get_running_loop()

        async def record_progress(payload: dict[str, Any]) -> None:
            await self._record_representation_event(task_id, payload)
            if payload.get("event") != "asset_ready":
                return
            async with self._lock:
                current = self.tasks.get(task_id)
                if not current or str(current.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES:
                    return
                fingerprints = dict(current.get("representation_asset_fingerprints") or {})
                seeds = dict(current.get("representation_generation_seeds") or {})
                page_id = str(payload.get("page_id") or "")
                if page_id:
                    fingerprints[page_id] = str(payload.get("asset_id") or "")
                    anchor = payload.get("visual_anchor") or {}
                    seeds[page_id] = str(
                        (anchor.get("parameters") or {}).get("generation_seed") or ""
                    )
                current["representation_asset_fingerprints"] = fingerprints
                current["representation_generation_seeds"] = seeds
                current["updated_at"] = datetime.now().isoformat()
                self.save_tasks()

        def progress(payload: dict[str, Any]) -> None:
            current = self.tasks.get(task_id) or {}
            if str(current.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES:
                raise RuntimeError("slide_deck_variant_build_interrupted")
            future = asyncio.run_coroutine_threadsafe(
                record_progress(payload),
                loop,
            )
            future.result(timeout=10)

        async def save_fallback_checkpoint(
            fallback_allocation: SlideAllocationPlanV2,
            fallback_visual: SlideVisualPlanV1,
            fallback_story: SlideStoryPlanV2,
        ) -> None:
            async with self._lock:
                current = self.tasks.get(task_id)
                if not current or str(current.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES:
                    return
                current["representation_deck_plan_v3"] = (
                    fallback_allocation.model_dump(mode="json")
                )
                current["representation_story_plan_v2"] = (
                    fallback_story.model_dump(mode="json")
                )
                current["representation_visual_plan_v1"] = (
                    fallback_visual.model_dump(mode="json")
                )
                current["representation_asset_fingerprints"] = {}
                current["representation_generation_seeds"] = {}
                current["updated_at"] = datetime.now().isoformat()
                self.save_tasks()

        build_attempt = await _rebuild_slide_variant_with_quality_fallback(
            document=document,
            course_view=course_view,
            repository=teaching_representation_repository,
            mode=mode,
            theme=theme,
            slide_schema=slide_schema,
            allocation_plan=allocation_plan,
            visual_plan=visual_plan,
            story_plan=story_plan,
            progress_callback=progress,
            checkpoint_callback=save_fallback_checkpoint,
            resume_slides=resume_slides,
            source_revision_provider=lambda: str(
                self._course_document_repository.load_document(course_id)[0].document_revision
                or ""
            ),
            variant_key_override=variant_key,
        )
        build = build_attempt["build"]
        allocation_plan = build_attempt["allocation_plan"]
        visual_plan = build_attempt["visual_plan"]
        story_plan = build_attempt["story_plan"]
        quality = build.get("quality") or {}
        if not quality.get("passed"):
            failure = build.get("failure") or {}
            if slide_schema == "slide_deck_v5" and failure:
                raise SlideDeckV5BuildError(
                    stage=str(failure.get("stage") or "quality_gate"),
                    code=str(failure.get("code") or "v5_quality_gate_failed"),
                    message=str(
                        failure.get("message")
                        or "V5 候选未通过完整性或可读性门禁。"
                    ),
                    retryable=bool(failure.get("retryable")),
                    source_revision=str(
                        failure.get("source_revision") or source_revision
                    ),
                    chapter_id=str(failure.get("chapter_id") or ""),
                    page_id=str(failure.get("page_id") or ""),
                )
            raise RuntimeError("slide_deck_variant_quality_gate_failed")
        registry = teaching_representation_repository.load(course_id)
        result = {
            "build": build,
            "quality": quality,
            "registry": registry.model_dump(mode="json"),
            "variant_key": variant_key,
            "quality_fallback": {
                "used": bool(build_attempt["used_deterministic_fallback"]),
                "initial_score": (
                    (build_attempt.get("initial_quality") or {}).get("score")
                ),
                "initial_blocker_count": len(
                    (build_attempt.get("initial_quality") or {}).get("blockers") or []
                ),
            },
        }
        async with self._lock:
            current = self.tasks.get(task_id)
            if not current or str(current.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES:
                return
            current["result"] = result
            current["completed_representation_types"] = [f"slide_deck:{variant_key}"]
            current["progress"] = 100
            current["phase_progress"] = 100
            current["phase"] = "complete"
            current["current_phase"] = "complete"
            current.pop("quality", None)
            current["message"] = f"{variant_key} 课件已通过质量门并发布"
            current["updated_at"] = datetime.now().isoformat()
            self.save_tasks()
        await self._record_representation_event(task_id, {
            "event": "build_complete",
            "progress": 100,
            **result,
        })
        await self._update_task_status(task_id, "completed", message="PPT 组合生成完成")

    async def _process_teaching_representation_task(self, task_id: str) -> None:
        """Build same-source artifacts as a durable, resumable generation job."""
        task = self.tasks.get(task_id)
        if not task or str(task.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES:
            return
        course_id = str(task["course_id"])
        if not await self._update_task_status(
            task_id, "running", message="正在更新同源教案、讲义、练习与图解",
        ):
            return
        document, canonical = await asyncio.to_thread(
            self._course_document_repository.load_document, course_id,
        )
        if not canonical:
            raise CourseDocumentConflict("Course must be canonical before building representations")
        course_view = await asyncio.to_thread(
            self._course_document_repository.load_course_view, course_id,
        )
        source_revision = str(document.document_revision or "")
        async with self._lock:
            current = self.tasks.get(task_id)
            if not current or str(current.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES:
                return
            current["representation_source_document_revision"] = source_revision
            current.pop("representation_deck_plan", None)
            current["updated_at"] = datetime.now().isoformat()
            self.save_tasks()
        await self._record_representation_event(task_id, {
            "event": "representation_stage",
            "progress": 8,
            "stage": "non_slide_material_plan",
            "strategy": "current_materials_then_scoped_slide_variant",
        })
        loop = asyncio.get_running_loop()

        def progress(payload: dict[str, Any]) -> None:
            current = self.tasks.get(task_id) or {}
            if str(current.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES:
                raise RuntimeError("teaching_representation_build_interrupted")
            future = asyncio.run_coroutine_threadsafe(
                self._record_representation_event(task_id, payload), loop,
            )
            future.result(timeout=10)

        build = await asyncio.to_thread(
            rebuild_core_representations_safely,
            document,
            course_view,
            teaching_representation_repository,
            progress_callback=progress,
            include_slide_deck=False,
        )
        registry = teaching_representation_repository.load(course_id)
        current_spec_ids = {item.spec_id for item in registry.representations}
        quality = build.get("quality") or validate_compiled_representations([
            item for item in registry.specs if item.spec_id in current_spec_ids
        ])
        if not quality.get("passed"):
            raise RuntimeError("teaching_representation_quality_gate_failed")
        result = {
            "build": build,
            "quality": quality,
            "registry": registry.model_dump(mode="json"),
        }
        async with self._lock:
            task = self.tasks.get(task_id)
            if not task or str(task.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES:
                return
            task["result"] = result
            task["completed_representation_types"] = [
                item.representation_type for item in registry.representations
                if item.status == "ready"
            ]
            task["progress"] = 100
            task["phase_progress"] = 100
            task["phase"] = "complete"
            task["current_phase"] = "complete"
            task["message"] = "同源教学产物已通过质量门并发布"
            task["updated_at"] = datetime.now().isoformat()
            self.save_tasks()
        await self._record_representation_event(task_id, {
            "event": "build_complete", "progress": 100, **result,
        })
        await self._update_task_status(task_id, "completed", message="同源教学产物生成完成")

    async def _record_representation_event(
        self,
        task_id: str,
        payload: dict[str, Any],
    ) -> None:
        async with self._lock:
            current = self.tasks.get(task_id)
            if not current or str(current.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES:
                return
            task = deepcopy(current)
            previous_status = str(current.get("status") or "")
            sequence = int(task.get("event_sequence") or 0) + 1
            event = {**deepcopy(payload), "sequence": sequence}
            task["event_sequence"] = sequence
            history = list(task.get("event_history") or [])
            history.append(event)
            task["event_history"] = history[-240:]
            task["last_event"] = event
            progress_v2 = payload.get("slide_build_progress_v2")
            if (
                payload.get("event") == "slide_build_progress_v2"
                and isinstance(progress_v2, dict)
            ):
                task["slide_build_progress_v2"] = deepcopy(progress_v2)
                if str(progress_v2.get("status") or "") == "failed":
                    failure = progress_v2.get("failure") or {}
                    if isinstance(failure, dict):
                        task["status"] = "failed"
                        task["error_detail"] = deepcopy(failure)
                        task["error_code"] = str(
                            failure.get("code") or "slide_build_failed"
                        )
                        task["error"] = str(
                            failure.get("message")
                            or payload.get("message")
                            or "V6 slide build failed"
                        )
                else:
                    task["error"] = None
                    task["error_detail"] = None
                    task["error_code"] = None
            if payload.get("event") in {"build_blocked", "build_failed"}:
                public_quality = _public_representation_quality(
                    payload.get("quality")
                )
                if public_quality is not None:
                    task["quality"] = public_quality
            task["progress"] = max(
                int(task.get("progress") or 0), int(payload.get("progress") or 0),
            )
            task["phase_progress"] = int(payload.get("progress") or task.get("phase_progress") or 0)
            task["phase"] = str(payload.get("stage") or payload.get("event") or task.get("phase") or "building")
            task["current_phase"] = task["phase"]
            task["message"] = str(payload.get("message") or task.get("message") or "正在生成同源教学产物")
            task["updated_at"] = datetime.now().isoformat()
            if (
                str(task.get("status") or "") != previous_status
                and str(task.get("status") or "") in {"failed", "error"}
            ):
                self._commit_task_draft(task_id, task)
            else:
                current.clear()
                current.update(task)
                self.save_tasks()
        await self._push_progress(task_id)

    async def _fail_course_import(
        self,
        task_id: str,
        *,
        code: str,
        message: str,
        retryable: bool,
    ) -> None:
        async with self._lock:
            current = self.tasks.get(task_id)
            if not current or str(current.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES:
                return
            task = deepcopy(current)
            now = datetime.now().isoformat()
            task["status"] = "failed"
            task["error_code"] = code
            task["error_user_message"] = message
            task["error"] = code
            task["error_detail"] = {
                "code": code,
                "message": message,
                "retryable": retryable,
            }
            task["import_retryable"] = retryable
            task["message"] = message
            task["updated_at"] = now
            task["heartbeat_at"] = now
            self._record_phase_history(
                task,
                str(task.get("current_phase") or task.get("phase") or "failed"),
                "error",
                progress=int(task.get("progress") or 0),
                message=message,
                timestamp=now,
            )
            self._commit_task_draft(task_id, task)
        await self._push_progress(task_id)

    async def _process_course_import_task(self, task_id: str) -> None:
        task = self.tasks.get(task_id)
        if not task or str(task.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES:
            return
        source_path = self.import_source_path(task_id)
        checkpoint_path = self.import_checkpoint_path(task_id)
        if not source_path.is_file():
            await self._fail_course_import(
                task_id,
                code="import_source_missing",
                message="导入源文件已不存在，请重新选择文件",
                retryable=False,
            )
            return

        if not await self._update_task_status(task_id, "running", message="正在解析导入资料"):
            return
        parsed_checkpoint: dict[str, Any] | None = None
        if checkpoint_path.is_file():
            try:
                parsed_checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                parsed_checkpoint = None

        await self._update_phase(
            task_id,
            "material_parsing",
            20,
            "已恢复解析结果" if parsed_checkpoint else "正在解析 Markdown 结构",
            phase_progress=100 if parsed_checkpoint else 35,
            phase_detail={"checkpoint_reused": bool(parsed_checkpoint)},
        )
        if parsed_checkpoint:
            nodes = list(parsed_checkpoint.get("nodes") or [])
            course_name = str(parsed_checkpoint.get("course_name") or task.get("course_name") or "待导入课程")
        else:
            try:
                text = source_path.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                await self._fail_course_import(
                    task_id,
                    code="markdown_encoding_unsupported",
                    message="文件编码无法解析，请使用 UTF-8 编码后重新导入",
                    retryable=False,
                )
                return
            try:
                nodes, course_name = parse_markdown_to_nodes(
                    text,
                    Path(str((task.get("request_snapshot") or {}).get("filename") or "import.md")).stem,
                )
            except ValueError:
                await self._fail_course_import(
                    task_id,
                    code="markdown_heading_missing",
                    message="未检测到 Markdown 标题，请确保文件包含至少一个标题后重新导入",
                    retryable=False,
                )
                return
            if not any(str(node.get("node_content", "")).strip() for node in nodes):
                await self._fail_course_import(
                    task_id,
                    code="markdown_teachable_body_missing",
                    message="课程只有标题或层级，请补充至少一段可讲授正文后重新导入",
                    retryable=False,
                )
                return
            parsed_checkpoint = {"course_name": course_name, "nodes": nodes}
            self._write_json_atomic(checkpoint_path, parsed_checkpoint)

        async with self._lock:
            current = self.tasks.get(task_id)
            if not current:
                return
            current["course_name"] = course_name
            current["completed_nodes"] = len(nodes)
            current["total_nodes"] = len(nodes)
            current["import_retryable"] = True
            self.save_tasks()

        await self._update_phase(
            task_id,
            "source_retrieval",
            35,
            "本次导入使用本地资料，外部检索已跳过",
            phase_progress=100,
            phase_detail={"skipped": True, "reason": "local_import"},
        )
        await self._update_phase(
            task_id,
            "content_generation",
            60,
            "正在将解析结果编译为课程内容",
            phase_progress=100,
            phase_detail={"completed_items": len(nodes), "total_items": len(nodes)},
        )
        await self._update_phase(
            task_id,
            "quality_validation",
            80,
            "正在检查课程结构和可讲授正文",
            phase_progress=100,
            phase_detail={"checks": ["heading_hierarchy", "teachable_body"]},
        )

        course_id = str(task["course_id"])
        course_tree = {
            "course_id": course_id,
            "course_name": course_name,
            "keyword": course_name,
            "nodes": nodes,
            "difficulty": "intermediate",
            "style": "academic",
            "create_time": datetime.now().isoformat(),
        }
        await self._update_phase(
            task_id,
            "exporting",
            95,
            "正在保存课程并建立正式课程文档",
            phase_progress=60,
            phase_detail={"target": "course_document"},
        )
        try:
            await self._course_document_repository.create_imported_course(
                course_id,
                imported_course=course_tree,
            )
        except Exception:
            async with self._lock:
                current = self.tasks.get(task_id)
                if current:
                    current["error_code"] = "import_persistence_failed"
                    current["error_user_message"] = "课程保存暂时失败，已保留解析结果，可以从保存点重试"
                    current["import_retryable"] = True
                    current["message"] = current["error_user_message"]
                    self.save_tasks()
            raise

        await self._update_phase(
            task_id,
            "completed",
            100,
            "课程导入完成",
            phase_progress=100,
            phase_detail={"course_id": course_id},
        )
        await self._update_task_status(
            task_id,
            "completed",
            message="课程导入完成",
            completed_nodes=len(nodes),
            total_nodes=len(nodes),
        )
        try:
            source_path.unlink(missing_ok=True)
            checkpoint_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Unable to clean completed import source for %s", task_id)
        await self._push_progress(task_id)

    @staticmethod
    def _processing_handoff(task: dict[str, Any]) -> tuple[str, str]:
        """Return the precise phase shown while a queued generation job resumes."""
        workflow = task.get("guided_workflow")
        if isinstance(workflow, dict):
            step = str(
                workflow.get("review_step")
                or workflow.get("current_step")
                or "outline"
            )
            step_status = str(
                next(
                    (
                        item.get("status")
                        for item in workflow.get("steps") or []
                        if item.get("key") == step
                    ),
                    "",
                )
                or ""
            )
            if step == "release":
                if step_status == "confirmed":
                    return "release_confirmed", "确认发布已完成，正在发布课程"
                if step_status in {"needs_regeneration", "failed"}:
                    return "quality_failed", "发布前质量检查未通过"
                return "publication_quality_check", "正在执行发布前质量检查"
            guided_handoffs = {
                "requirements": ("requirement_analysis", "正在整理课程需求"),
                "outline": ("outline_generation", "正在生成课程目录"),
                "teaching": ("course_teaching_plan", "正在规划并汇编全课小节教案"),
                "content": ("content_generation", "正在生成课程正文"),
            }
            if step in guided_handoffs:
                return guided_handoffs[step]

        phase = str(task.get("current_phase") or task.get("phase") or "")
        message = str(task.get("message") or "").strip()
        if phase and message not in {"", "正在处理...", "正在处理…", "正在生成"}:
            return phase, message
        return phase or "requirement_analysis", "正在启动课程生成"

    async def _process_task(self, task_id: str) -> None:
        """处理单个任务：分析课程结构并调度节点。

        Args:
            task_id: 任务 ID
        """
        task = self.tasks.get(task_id)
        if (
            not task
            or str(task.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES
        ):
            return

        if str(task.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES:
            return

        if task.get("type") == "teacher_course_change_generation":
            from course_evolution.jobs import run_candidates
            await run_candidates(self, task_id)
            return
        if task.get("type") == "course_import":
            await self._process_course_import_task(task_id)
            return
        if task.get("type") == "slide_deck_variant_build":
            await self._process_slide_deck_variant_task(task_id)
            return
        if task.get("type") == "teaching_representation_build":
            await self._process_teaching_representation_task(task_id)
            return

        course_id = task["course_id"]
        handoff_phase, handoff_message = self._processing_handoff(task)
        if not await self._update_task_status(task_id, "running"):
            return
        await self._update_phase(
            task_id,
            handoff_phase,
            int(task.get("progress") or 0),
            handoff_message,
            phase_progress=int(task.get("phase_progress") or 0),
            phase_detail=task.get("phase_detail") or {},
        )
        # Lifecycle updates are copy-on-write: refresh the execution snapshot
        # after publishing ``running``/phase state instead of continuing with
        # the detached pre-transition dict.  Otherwise guided confirmations can
        # be read from the stale object and the job can skip its next review gate.
        task = self.tasks.get(task_id)
        if (
            not task
            or str(task.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES
        ):
            return

        course_data = self._load_task_course(task_id)
        if not course_data:
            await self._update_task_status(
                task_id, "failed", error="Course not found"
            )
            return

        request = {
            **deepcopy(course_data.get("generation_request") or {}),
            **deepcopy(task.get("request_snapshot") or {}),
        }
        guided_workflow = task.get("guided_workflow")
        guided = isinstance(guided_workflow, dict)
        # Teacher authoring owns everything after the generated outline through
        # lesson-scoped jobs. Finalize a resumed outline task before the shared workflow
        # advances its current step to ``teaching``; otherwise a resumed queue
        # item can accidentally enter the learner full-course plan/content path.
        if (
            task.get("type") == "teacher_outline_generation"
            and _teacher_outline_result_ready(course_data)
        ):
            course_data["generation_status"] = "teacher_outline_ready"
            course_data["outline_framework_only"] = False
            course_data["outline_generation_status"] = "completed"
            course_data["outline_lifecycle_status"] = "current"
            course_data["authoring_surface"] = "teacher"
            await self._save_task_course(task_id, course_data)
            if task.get("workspace_id"):
                await asyncio.to_thread(
                    self._generation_workspace_repository.set_status,
                    str(task["workspace_id"]),
                    "active",
                    result={},
                )
            self._version_repository.delete_draft(course_id)
            async with self._lock:
                current = self.tasks.get(task_id)
                if not current or str(current.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES:
                    return
                task = deepcopy(current)
                task["status"] = "completed"
                task["phase"] = "teacher_outline_ready"
                task["current_phase"] = "teacher_outline_ready"
                task["progress"] = 100
                task["phase_progress"] = 100
                task["message"] = "课程大纲已生成，可选择任一讲生成教案"
                task["outline_detail_requested"] = False
                task["current_nodes"] = []
                task["current_node_name"] = ""
                task["updated_at"] = datetime.now().isoformat()
                task["heartbeat_at"] = task["updated_at"]
                task = self._commit_task_draft(task_id, task)
            await self._push_progress(task_id)
            return
        if guided and not guided_workflow.get("review_step"):
            current_guided_step = str(
                guided_workflow.get("current_step") or "outline"
            )
            mark_guided_step_running(guided_workflow, current_guided_step)
            async with self._lock:
                task = self.tasks.get(task_id)
                if not task or str(task.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES:
                    return
                task["updated_at"] = datetime.now().isoformat()
                self.save_tasks()
        is_teacher_outline = task.get("type") == "teacher_outline_generation"
        request_mode = str(request.get("generation_mode") or "review_blueprint")
        review_pending = (
            not is_teacher_outline
            and guided
            and not guided_step_confirmed(guided_workflow, "outline")
        ) or (
            not is_teacher_outline
            and
            not guided
            and request_mode == "review_blueprint"
            and not task.get("blueprint_confirmed")
        )
        knowledge_base = course_data.get("course_knowledge_base") or {}
        pipeline_ready = bool(
            course_data.get("course_blueprint")
            and knowledge_base.get("lifecycle_status") == "active"
        )
        is_outline_generation = task.get("type") in {
            "course_generation",
            "teacher_outline_generation",
        }
        if is_outline_generation and not pipeline_ready:

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
                current = self.tasks.get(task_id)
                if not current or str(current.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES:
                    raise asyncio.CancelledError
                fresh = self._load_task_course(task_id) or course_data
                fresh.update(checkpoint)
                await self._save_task_course(task_id, fresh)

            stop_after_skeleton = bool(
                is_teacher_outline
                and not task.get("outline_detail_requested")
            )
            stop_after_outline = bool(
                is_teacher_outline
                or (
                    review_pending
                    and not course_data.get("course_outline")
                )
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
                course_type=request.get("course_type"),
                learning_purpose=request.get("learning_purpose"),
                course_teaching_type=request.get("course_teaching_type"),
                course_intent=request.get("course_intent") or {},
                learner_starting_profile=request.get("learner_starting_profile") or {},
                teacher_course_brief=request.get("teacher_course_brief") or {},
                current_readiness=request.get("current_readiness"),
                adaptation_preference=str(
                    request.get("adaptation_preference") or "preserve_target_extend"
                ),
                pedagogy_mode=str(request.get("pedagogy_mode") or "auto"),
                secondary_mode=request.get("secondary_mode"),
                secondary_intensity=request.get("secondary_intensity"),
                generation_mode=str(
                    request.get("generation_mode") or "review_blueprint"
                ),
                course_purpose=str(request.get("course_purpose") or "systematic"),
                asset_preferences=request.get("asset_preferences") or {},
                web_question_enrichment=request.get("web_question_enrichment") or {"enabled": False},
                web_material_ingest=merge_ingest_exclusions(
                    request.get("web_material_ingest") or {},
                    load_course_exclusions(course_data),
                ),
                existing_course_data=course_data,
                stop_after_skeleton=stop_after_skeleton,
                stop_after_outline=stop_after_outline,
                on_phase=on_phase,
                on_checkpoint=on_checkpoint,
            )
            if stop_after_outline and not is_teacher_outline:
                course_data = await self._prepare_course_outline_research(
                    course_data,
                    request,
                )
                research_proposal = (
                    (
                        course_data.get("generation_stage_artifacts")
                        or {}
                    ).get("web_retrieval")
                    or {}
                ).get("proposal") or {}
                draft = deepcopy(
                    research_proposal.get("candidate_draft") or {}
                ) or build_blueprint_draft(course_data)
                impact = analyze_blueprint_impact(course_data, draft)
                draft["impact_report"] = impact
                self._version_repository.save_draft(course_id, draft)
                outline_actual = (
                    course_data.get("course_outline_constraint_report") or {}
                ).get("actual") or {}
                course_data["generation_status"] = "outline_ready"
                await self._save_task_course(task_id, course_data)
                # D-1：确认门上的提示要带覆盖度结论，否则用户只看到"N 节已就绪"，
                # 仍然以为这是一门完整课程。
                coverage = self.project_course_coverage(course_data)
                coverage_detail = (
                    {"course_coverage": coverage} if coverage.get("available") else {}
                )
                if guided:
                    await self._pause_for_guided_review(
                        task_id,
                        course_data,
                        "outline",
                        phase="outline_ready",
                        progress=35,
                        message=self._outline_review_message(
                            coverage,
                            is_teacher_outline=is_teacher_outline,
                        ),
                        revision=guided_artifact_revision(
                            "outline",
                            course_data,
                            request=task.get("request_snapshot") or {},
                        ),
                        phase_detail={
                            "completed_items": int(outline_actual.get("section_count") or 0),
                            "total_items": int(outline_actual.get("section_count") or 0),
                            **coverage_detail,
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
                        **coverage_detail,
                    },
                )
                await self._update_task_status(
                    task_id,
                    "waiting_for_review",
                    message=self._outline_review_message(
                        coverage,
                        is_teacher_outline=is_teacher_outline,
                    ),
                    completed_nodes=0,
                    total_nodes=int(outline_actual.get("section_count") or 0),
                )
                await self._push_progress(task_id)
                return
            if not is_teacher_outline and (
                course_data.get("course_knowledge_base") or {}
            ).get("lifecycle_status") != "active":
                course_data = await self._prepare_subject_knowledge(task_id, course_data)
            if not is_teacher_outline:
                self._require_course_knowledge_ready(course_data)
                frozen = self._version_repository.freeze_blueprint(course_id, course_data)
                course_data["blueprint_revision_id"] = frozen["blueprint_revision_id"]
                task["blueprint_revision_id"] = frozen["blueprint_revision_id"]
                await self._save_task_course(task_id, course_data)

        if is_teacher_outline:
            if course_data.get("outline_framework_only") is True:
                draft = build_blueprint_draft(course_data)
                self._version_repository.save_draft(course_id, draft)
                await self._save_task_course(task_id, course_data)
                async with self._lock:
                    current = self.tasks.get(task_id)
                    if not current or str(current.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES:
                        return
                    task = deepcopy(current)
                    task["status"] = "waiting_for_input"
                    task["phase"] = "outline_framework_ready"
                    task["current_phase"] = "outline_framework_ready"
                    task["progress"] = 32
                    task["phase_progress"] = 100
                    task["phase_detail"] = {
                        "artifact_type": "course_outline_framework",
                        "status": "completed",
                        "stage": "outline_framework_ready",
                        "message": "轻量讲次方案已生成",
                    }
                    task["message"] = (
                        "轻量讲次方案已生成，"
                        "可编辑或主动生成完整大纲"
                    )
                    task["current_nodes"] = []
                    task["current_node_name"] = ""
                    task["updated_at"] = datetime.now().isoformat()
                    task["heartbeat_at"] = task["updated_at"]
                    task = self._commit_task_draft(task_id, task)
                await self._push_progress(task_id)
                return
            if not _teacher_outline_result_ready(course_data):
                await self._save_task_course(task_id, course_data)
                await self._update_phase(
                    task_id,
                    "teacher_outline_failed",
                    int(task.get("progress") or 0),
                    "课程大纲生成结果为空或结构无效",
                    phase_progress=100,
                    phase_detail={"artifact_type": "course_outline"},
                )
                await self._update_task_status(
                    task_id,
                    "failed",
                    message="课程大纲生成失败，请重试",
                    error="模型未返回可用的课程大纲结构。",
                    error_detail={
                        "code": "teacher_outline_generation_invalid",
                        "message": "模型未返回可用的课程大纲结构。",
                        "retryable": True,
                    },
                )
                await self._push_progress(task_id)
                return
            course_data["generation_status"] = "teacher_outline_ready"
            course_data["outline_framework_only"] = False
            course_data["outline_generation_status"] = "completed"
            course_data["outline_lifecycle_status"] = "current"
            course_data["authoring_surface"] = "teacher"
            await self._save_task_course(task_id, course_data)
            if task.get("workspace_id"):
                await asyncio.to_thread(
                    self._generation_workspace_repository.set_status,
                    str(task["workspace_id"]),
                    "active",
                    result={},
                )
            self._version_repository.delete_draft(course_id)
            async with self._lock:
                current = self.tasks.get(task_id)
                if not current or str(current.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES:
                    return
                task = deepcopy(current)
                task["status"] = "completed"
                task["phase"] = "teacher_outline_ready"
                task["current_phase"] = "teacher_outline_ready"
                task["progress"] = 100
                task["phase_progress"] = 100
                task["message"] = "课程大纲已生成，可选择任一讲生成教案"
                task["outline_detail_requested"] = False
                task["current_nodes"] = []
                task["current_node_name"] = ""
                task["updated_at"] = datetime.now().isoformat()
                task["heartbeat_at"] = task["updated_at"]
                task = self._commit_task_draft(task_id, task)
            await self._push_progress(task_id)
            return

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
                and teaching_stage.get("semantic_status") in {
                    None,
                    "ai_complete",
                }
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
                teaching_stage = (
                    course_data.get("generation_stage_artifacts") or {}
                ).get("course_teaching_plan") or {}
            if teaching_stage.get("semantic_status") == "retry_required":
                raise AIProviderRequestError(
                    "教案语义仍需重试，正文生成不会提前启动"
                )
            if guided and not guided_step_confirmed(guided_workflow, "teaching"):
                teaching_plan = project_course_teaching_plan(course_data)
                section_count = int(
                    teaching_plan.get("section_count")
                    or len(teaching_plan.get("sections") or [])
                )
                await self._pause_for_guided_review(
                    task_id,
                    course_data,
                    "teaching",
                    phase="teaching_plan_ready",
                    progress=max(55, int(task.get("progress") or 0)),
                    message="全课教案已生成，确认后将按小节持续生成正文",
                    phase_detail={
                        "artifact_type": "course_teaching_plan",
                        "completed_items": section_count,
                        "total_items": section_count,
                        "completed_batches": int(
                            teaching_stage.get("completed_batch_count")
                            or teaching_stage.get("completed_batches")
                            or 0
                        ),
                        "total_batches": int(
                            teaching_stage.get("batch_count")
                            or teaching_stage.get("total_batches")
                            or 0
                        ),
                    },
                )
                return
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
        # 位置表在这里算一次：这是唯一同时拿得到完整有序节点表的地方，
        # 之后推进度时只查表，不再重新加载课程。
        task["node_locations"] = build_node_locations(nodes)
        l2_nodes = [n for n in nodes if n.get("node_level", 1) == 2]

        # The V2 blueprint already owns the complete L1/L2 structure.
        incomplete_l2 = [n for n in l2_nodes if not self._is_content_complete(n)]
        if incomplete_l2:
            total = len(l2_nodes)
            completed = len(l2_nodes) - len(incomplete_l2)
            content_started_at = time.monotonic()
            content_stage = course_data.setdefault(
                "generation_stage_artifacts",
                {},
            ).setdefault("content_generation", {})
            content_stage.update({
                "status": "in_progress",
                "section_count": total,
                "pending_section_count": len(incomplete_l2),
                "max_concurrency": self.max_concurrency,
                "max_retries_per_node": self._content_max_retries,
                "inactivity_timeout_seconds": (
                    self._content_inactivity_timeout_seconds
                ),
                "completion_policy": "all_nodes_settled",
                "generation_dependency": "frozen_teaching_plan_only",
            })
            await self._save_task_course(task_id, course_data)
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
                    "max_concurrency": self.max_concurrency,
                    "max_retries_per_node": self._content_max_retries,
                    "inactivity_timeout_seconds": (
                        self._content_inactivity_timeout_seconds
                    ),
                    "completion_policy": "all_nodes_settled",
                    "generation_dependency": (
                        "frozen_teaching_plan_only"
                    ),
                },
            )
            await self._schedule_nodes(
                task_id,
                incomplete_l2,
            )
            fresh_course = self._load_task_course(task_id) or course_data
            generated_nodes = [
                node
                for node in fresh_course.get("nodes") or []
                if int(node.get("node_level") or 1) == 2
            ]
            runtimes = [
                node.get("generation_runtime") or {}
                for node in generated_nodes
                if isinstance(node.get("generation_runtime"), dict)
            ]
            stage = fresh_course.setdefault(
                "generation_stage_artifacts",
                {},
            ).setdefault("content_generation", {})
            completed_section_count = sum(
                1
                for node in generated_nodes
                if self._is_content_complete(node)
            )
            failed_section_count = sum(
                1
                for node in generated_nodes
                if node.get("generation_status") == NodeStatus.ERROR.value
            )
            stage.update({
                "status": (
                    "completed"
                    if completed_section_count == len(generated_nodes)
                    else "partial"
                ),
                "duration_ms": int(
                    (time.monotonic() - content_started_at) * 1000
                ),
                "completed_section_count": completed_section_count,
                "failed_section_count": failed_section_count,
                # E-1 验收口径：本轮（含恢复）为正文实际发出的模型调用总数。
                # 恢复后已完成小节不再进入生成，其计数不增长，因此这个总数
                # 与"重跑了多少节"一致，可以直接核对，不用肉眼判断。
                "model_call_count": sum(
                    int(item.get("model_call_count") or 0)
                    for item in runtimes
                ),
                "resume_available": (
                    completed_section_count < len(generated_nodes)
                ),
                "completion_policy": "all_nodes_settled",
                "max_prompt_tokens": max(
                    (
                        int(item.get("estimated_input_tokens") or 0)
                        for item in runtimes
                    ),
                    default=0,
                ),
                "total_prompt_tokens": sum(
                    int(item.get("estimated_input_tokens") or 0)
                    for item in runtimes
                ),
            })
            await self._save_task_course(task_id, fresh_course)
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
        generation_runtime: dict[str, Any] | None = None,
        citation_map: dict[str, str] | None = None,
        source_cards: list[dict[str, Any]] | None = None,
        citation_invalid_refs: list[str] | None = None,
    ) -> dict[str, Any] | None:
        def update(fresh_data: dict[str, Any]) -> dict[str, Any]:
            for node in fresh_data.get("nodes", []):
                if node.get("node_id") == node_id:
                    node["citation_map"] = deepcopy(citation_map or {})
                    node["source_cards"] = deepcopy(source_cards or [])
                    node["citation_invalid_refs"] = list(
                        citation_invalid_refs or []
                    )
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
                    node["generation_runtime"] = deepcopy(
                        generation_runtime or {}
                    )
                    break
            return fresh_data

        fresh_data = await self._mutate_task_course(task_id, update)
        task = self.tasks.get(task_id) or {}
        workspace_id = task.get("workspace_id")
        if fresh_data is not None and workspace_id:
            await asyncio.to_thread(
                self._generation_workspace_repository.clear_node_draft,
                str(workspace_id),
                node_id,
            )
        return fresh_data

    async def _save_node_draft(
        self,
        task_id: str,
        course_id: str,
        node_id: str,
        content: str,
        generation_runtime: dict[str, Any] | None = None,
    ) -> None:
        if not content:
            return
        task = self.tasks.get(task_id) or {}
        workspace_id = task.get("workspace_id")
        if workspace_id:
            await asyncio.to_thread(
                self._generation_workspace_repository.save_node_draft,
                str(workspace_id),
                node_id,
                content,
                generation_runtime=generation_runtime,
            )
            return

        def update(fresh_data: dict[str, Any]) -> dict[str, Any]:
            for item in fresh_data.get("nodes", []):
                if item.get("node_id") == node_id:
                    item["node_content_draft"] = content
                    item["generation_status"] = NodeStatus.PENDING.value
                    if generation_runtime:
                        item["generation_runtime"] = deepcopy(
                            generation_runtime
                        )
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

    async def _await_content_progress(
        self,
        node_name: str,
        generation: Awaitable[str],
        activity_event: asyncio.Event,
    ) -> str:
        """Wait while a stream is productive; stop only after no progress."""
        generation_task = asyncio.create_task(generation)
        activity_waiter: asyncio.Task[bool] | None = None
        try:
            while True:
                activity_waiter = asyncio.create_task(activity_event.wait())
                done, _pending = await asyncio.wait(
                    {generation_task, activity_waiter},
                    timeout=self._content_inactivity_timeout_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if generation_task in done:
                    activity_waiter.cancel()
                    await asyncio.gather(
                        activity_waiter,
                        return_exceptions=True,
                    )
                    return generation_task.result()
                if activity_waiter in done:
                    activity_event.clear()
                    activity_waiter = None
                    continue

                # Progress can arrive exactly as ``asyncio.wait`` snapshots a
                # timeout.  Re-check both signals before cancelling the
                # generation task, otherwise a productive stream may be
                # mistaken for an inactive one on coarse event loops.
                if generation_task.done():
                    activity_waiter.cancel()
                    await asyncio.gather(
                        activity_waiter,
                        return_exceptions=True,
                    )
                    return generation_task.result()
                if activity_event.is_set():
                    activity_event.clear()
                    activity_waiter.cancel()
                    await asyncio.gather(
                        activity_waiter,
                        return_exceptions=True,
                    )
                    activity_waiter = None
                    continue

                activity_waiter.cancel()
                await asyncio.gather(
                    activity_waiter,
                    return_exceptions=True,
                )
                activity_waiter = None
                generation_task.cancel()
                await asyncio.gather(
                    generation_task,
                    return_exceptions=True,
                )
                raise CourseGenerationDeadlineExceeded(
                    f"小节 {node_name} 连续 "
                    f"{self._content_inactivity_timeout_seconds} 秒没有新内容；"
                    "已停止当前小节并保留流式草稿"
                )
        finally:
            if activity_waiter is not None and not activity_waiter.done():
                activity_waiter.cancel()
                await asyncio.gather(
                    activity_waiter,
                    return_exceptions=True,
                )
            if not generation_task.done():
                generation_task.cancel()
                await asyncio.gather(
                    generation_task,
                    return_exceptions=True,
                )

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
                location = (task.get("node_locations") or {}).get(node_id) or {}
                if location:
                    node_info["location"] = deepcopy(location)
                current_nodes = task.get("current_nodes", [])
                current_nodes.append(node_info)
                task["current_nodes"] = current_nodes
                if current_nodes:
                    task["current_node_name"] = current_nodes[0].get("node_name", "")
                    task["current_node_location"] = deepcopy(
                        current_nodes[0].get("location") or {}
                    )
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

                existing_draft = ""
                accumulated: list[str] = []
                while retry_count <= self._content_max_retries:
                    try:
                        config = self._build_node_config(node)

                        accumulated = []
                        streamed_chars = 0
                        last_progress_push = time.monotonic()
                        last_checkpoint = time.monotonic()
                        activity_event = asyncio.Event()
                        fresh_course = self._load_task_course(task_id) or {}
                        fresh_node = next(
                            (item for item in fresh_course.get("nodes", []) if item.get("node_id") == node_id),
                            node,
                        )
                        existing_draft = str(fresh_node.get("node_content_draft") or "")

                        async def on_chunk(chunk: str) -> None:
                            nonlocal streamed_chars, last_progress_push, last_checkpoint
                            activity_event.set()
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

                        content = await self._await_content_progress(
                            node_name,
                            self.course_service.generate_node_content_stream(
                                course_id=course_id,
                                node=node,
                                config=config,
                                on_chunk=on_chunk,
                                on_activity=activity_event.set,
                                course_data=fresh_course,
                                existing_draft=existing_draft,
                            ),
                            activity_event,
                        )

                        end_time = datetime.now()
                        duration_ms = (end_time - start_time).total_seconds() * 1000
                        
                        fixed_content = fix_latex_content(content)
                        generated_chars = len(fixed_content) if fixed_content else 0

                        generation_quality = evaluate_node_content(
                            fixed_content,
                            node,
                        )
                        generation_runtime = deepcopy(
                            node.get("generation_runtime") or {}
                        )
                        generation_runtime.update({
                            "timeout_policy": "stream_inactivity",
                            "inactivity_timeout_seconds": (
                                self._content_inactivity_timeout_seconds
                            ),
                        })
                        fresh_data = await self._save_generated_node_content(
                            task_id,
                            course_id,
                            node_id,
                            fixed_content,
                            generated_chars,
                            grounding_annotations=node.get("grounding_annotations") or [],
                            grounding_invalid_refs=node.get("grounding_invalid_refs") or [],
                            generation_quality=generation_quality,
                            needs_manual_review=(
                                bool(node.get("needs_manual_review"))
                                or not generation_quality.get("passed", False)
                            ),
                            generation_runtime=generation_runtime,
                            citation_map=node.get("citation_map") or {},
                            source_cards=node.get("source_cards") or [],
                            citation_invalid_refs=node.get(
                                "citation_invalid_refs"
                            )
                            or [],
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
                        await asyncio.shield(
                            self._save_node_draft(
                                task_id,
                                course_id,
                                node_id,
                                draft,
                                node.get("generation_runtime"),
                            )
                        )
                        logger.info("Node %s generation cancelled", node_id)
                        raise

                    except Exception as e:
                        failure = classify_generation_failure(e)
                        non_retryable = getattr(e, "retryable", True) is False
                        draft = existing_draft + "".join(accumulated)
                        if draft:
                            await self._save_node_draft(
                                task_id,
                                course_id,
                                node_id,
                                draft,
                                node.get("generation_runtime"),
                            )
                        retry_count = (
                            self._content_max_retries + 1
                            if non_retryable
                            else retry_count + 1
                        )
                        retries[node_id] = retry_count
                        error_msg = str(e)

                        if (
                            not non_retryable
                            and retry_count <= self._content_max_retries
                        ):
                            delay = min(
                                (2 ** retry_count) * BACKOFF_BASE, BACKOFF_MAX
                            )
                            self._add_log_entry(
                                task_id, node_id, node_name=node_name,
                                event="retry",
                                message=(
                                    f"Retry {retry_count}/"
                                    f"{self._content_max_retries}: "
                                    f"{error_msg[:100]}"
                                ),
                                retry_count=retry_count,
                            )
                            logger.warning(
                                "Node %s failed (retry %d/%d), backoff %.1fs: %s",
                                node_id,
                                retry_count,
                                self._content_max_retries,
                                delay,
                                error_msg[:100],
                            )
                            await asyncio.sleep(delay)
                        else:
                            end_time = datetime.now()
                            duration_ms = (end_time - start_time).total_seconds() * 1000

                            await self._set_node_status(
                                task_id, course_id, node_id, NodeStatus.ERROR,
                                error_summary=error_msg[:200],
                                error_code=failure["code"],
                                error_retryable=failure["retryable"],
                            )

                            self._add_log_entry(
                                task_id, node_id, node_name=node_name,
                                event="error",
                                message=(
                                    f"Non-retryable failure: {error_msg[:200]}"
                                    if non_retryable
                                    else (
                                        "Failed after "
                                        f"{self._content_max_retries} retries: "
                                        f"{error_msg[:200]}"
                                    )
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
                                        "error_code": failure["code"],
                                        "retryable": failure["retryable"],
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
                        task["current_node_location"] = deepcopy(
                            task["current_nodes"][0].get("location") or {}
                        )
                    else:
                        task["current_node_name"] = ""
                        task["current_node_location"] = {}
                    self.save_tasks()
                await self._update_progress(task_id)
                await self._push_progress(task_id)
                self._running_node_tasks.get(task_id, {}).pop(
                    node_id,
                    None,
                )

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

    @staticmethod
    def _task_index_last_good_path() -> Path:
        return TASKS_FILE.with_name(f"{TASKS_FILE.stem}.last-good.json")

    @staticmethod
    def _task_index_digest(tasks: dict[str, Any]) -> str:
        payload = json.dumps(
            tasks,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @classmethod
    def _task_index_last_good_envelope(
        cls,
        tasks: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "schema_version": TASK_INDEX_LAST_GOOD_SCHEMA,
            "checksum": cls._task_index_digest(tasks),
            "tasks": tasks,
        }

    @classmethod
    def _read_task_index(cls, path: Path) -> dict[str, Any]:
        if path.stat().st_size > MAX_TASK_INDEX_BYTES:
            raise ValueError("generation_job_index_oversized")
        with path.open(encoding="utf-8") as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, dict):
            raise ValueError("generation_job_index_not_object")
        return loaded

    @classmethod
    def _read_last_good_task_index(cls) -> dict[str, Any] | None:
        path = cls._task_index_last_good_path()
        if not path.exists():
            return None
        if path.stat().st_size > MAX_TASK_INDEX_BYTES:
            raise ValueError("generation_job_last_good_oversized")
        with path.open(encoding="utf-8") as handle:
            envelope = json.load(handle)
        if not isinstance(envelope, dict):
            raise ValueError("generation_job_last_good_not_object")
        if envelope.get("schema_version") != TASK_INDEX_LAST_GOOD_SCHEMA:
            raise ValueError("generation_job_last_good_schema_invalid")
        tasks = envelope.get("tasks")
        if not isinstance(tasks, dict):
            raise ValueError("generation_job_last_good_tasks_invalid")
        checksum = str(envelope.get("checksum") or "")
        if checksum != cls._task_index_digest(tasks):
            raise ValueError("generation_job_last_good_checksum_invalid")
        return tasks

    @staticmethod
    def _write_task_index_atomic(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(
            f".{path.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _quarantine_task_index(source: Path, *, reason: str) -> Path:
        archive = source.with_name(
            f"{source.stem}.{reason}-"
            f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-"
            f"{uuid.uuid4().hex[:8]}{source.suffix}"
        )
        os.replace(source, archive)
        return archive

    def _acquire_leader_lock(self) -> None:
        """Acquire the process lock before reading or recovering task state."""
        if fcntl is None:
            raise TaskLeaderConflictError(
                "Task scheduling requires an operating-system file lock"
            )
        self._leader_lock_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            self._leader_lock_path,
            os.O_RDWR | os.O_CREAT,
            0o600,
        )
        handle = os.fdopen(descriptor, "r+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.close()
            self._leader_state = "conflict"
            raise TaskLeaderConflictError(
                "Another TaskManager owns this data directory"
            ) from exc
        try:
            handle.seek(0)
            handle.truncate()
            json.dump(
                {
                    "pid": os.getpid(),
                    "acquired_at": datetime.now().isoformat(),
                },
                handle,
                ensure_ascii=False,
            )
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
            self._leader_state = "failed"
            raise
        self._leader_lock_handle = handle
        self._leader_state = "acquired"

    def _release_leader_lock(self) -> None:
        handle = self._leader_lock_handle
        if handle is None:
            return
        self._leader_lock_handle = None
        try:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
            self._leader_state = "released"

    def leader_health(self) -> dict[str, Any]:
        return {
            "mode": self._runtime_mode,
            "state": self._leader_state,
            "ready": (
                self._runtime_mode == "isolated_test"
                or (
                    self._runtime_mode == "leader"
                    and self._leader_state == "acquired"
                )
            ),
        }

    def _ensure_task_index_writable(self) -> None:
        if self._runtime_mode == "read_only":
            raise TaskLeaderConflictError(
                "Read-only TaskManager cannot modify task state"
            )
        if self._runtime_mode == "leader" and self._leader_state != "acquired":
            raise TaskLeaderConflictError(
                "Task writes require the data-directory leader lock"
            )
        if self._task_index_state == "degraded":
            raise TaskIndexDegradedError(
                "任务索引不可恢复，当前仅允许读取课程；请先修复任务索引"
            )

    def _commit_task_draft(
        self,
        task_id: str,
        draft: dict[str, Any],
        *,
        allow_create: bool = False,
    ) -> dict[str, Any]:
        """Persist a detached task draft before publishing it to readers."""
        self._ensure_task_index_writable()
        current = self.tasks.get(task_id)
        if current is None and not allow_create:
            raise KeyError(task_id)
        # Always persist a detached snapshot. Some legacy callers still pass the
        # currently published dict; assigning that object directly and then
        # clearing ``current`` after the save would otherwise erase the draft.
        published = deepcopy(draft)
        self.tasks[task_id] = published
        try:
            self._save_tasks_strict()
        except BaseException:
            if current is None:
                self.tasks.pop(task_id, None)
            else:
                self.tasks[task_id] = current
            raise
        if current is not None:
            # Long-running generation keeps references to both the task and its
            # guided workflow. Publish the durable snapshot through those same
            # objects so later review gates cannot mutate a detached workflow.
            current_workflow = current.get("guided_workflow")
            published_workflow = published.get("guided_workflow")
            current.clear()
            current.update(published)
            if isinstance(current_workflow, dict) and isinstance(
                published_workflow,
                dict,
            ):
                current_workflow.clear()
                current_workflow.update(published_workflow)
                current["guided_workflow"] = current_workflow
            self.tasks[task_id] = current
            return current
        return published

    def _remove_task_strict(self, task_id: str) -> dict[str, Any]:
        """Persist task removal, restoring the in-memory task on failure."""
        self._ensure_task_index_writable()
        current = self.tasks.pop(task_id, None)
        if current is None:
            raise KeyError(task_id)
        try:
            self._save_tasks_strict()
        except BaseException:
            self.tasks[task_id] = current
            raise
        return current

    def task_index_health(self) -> dict[str, Any]:
        return {
            "state": self._task_index_state,
            "ready": self._task_index_state == "ready",
            "recovery": self._task_index_recovery,
            "error_code": self._task_index_error_code,
        }

    def _tasks_for_persistence(self) -> dict[str, dict[str, Any]]:
        terminal = sorted(
            (
                (task_id, task)
                for task_id, task in self.tasks.items()
                if str(task.get("status") or "") in TERMINAL_TASK_STATUSES
            ),
            key=lambda item: str(
                item[1].get("updated_at")
                or item[1].get("created_at")
                or ""
            ),
            reverse=True,
        )
        retained_terminal_ids = {
            task_id
            for task_id, _task in terminal[:MAX_TERMINAL_TASK_HISTORY]
        }
        persisted: dict[str, dict[str, Any]] = {}
        for task_id, task in self.tasks.items():
            is_terminal = (
                str(task.get("status") or "") in TERMINAL_TASK_STATUSES
            )
            if is_terminal and task_id not in retained_terminal_ids:
                continue
            if is_terminal:
                persisted[task_id] = {
                    key: value
                    for key, value in task.items()
                    if key not in PUBLIC_TASK_OMITTED_FIELDS
                }
            else:
                persisted[task_id] = task
        return persisted

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
                recovered = self._read_last_good_task_index()
                if recovered is None:
                    self.tasks = {}
                    self._task_index_state = "ready"
                    return
                loaded = recovered
                self._task_index_recovery = "last_good"
            else:
                try:
                    loaded = self._read_task_index(source)
                except Exception as primary_error:
                    reason = (
                        "oversized"
                        if str(primary_error) == "generation_job_index_oversized"
                        else "corrupt"
                    )
                    if self._runtime_mode == "read_only":
                        logger.error(
                            "Read-only task index check failed at %s: %s",
                            source,
                            primary_error,
                        )
                    else:
                        archive = self._quarantine_task_index(source, reason=reason)
                        logger.error(
                            "Quarantined invalid generation job index at %s: %s",
                            archive,
                            primary_error,
                        )
                    try:
                        recovered = self._read_last_good_task_index()
                    except Exception as backup_error:
                        recovered = None
                        logger.error(
                            "Generation job last-good index is invalid: %s",
                            backup_error,
                        )
                    if recovered is None:
                        self.tasks = {}
                        self._task_index_state = "degraded"
                        self._task_index_recovery = "unavailable"
                        self._task_index_error_code = (
                            "generation_job_index_unrecoverable"
                        )
                        return
                    loaded = recovered
                    self._task_index_recovery = "last_good"
            self.tasks = loaded
            migrated_slide_contract = False
            migrated_teacher_lifecycle = False
            for task_id, task in self.tasks.items():
                task.setdefault("id", task_id)
                task.setdefault("type", "legacy_content_generation")
                task.setdefault("phase", "content_generation")
                task.setdefault("phase_progress", 0)
                task.setdefault("phase_detail", {})
                task.setdefault("request_snapshot", {})
                if task.get("type") == "slide_deck_variant_build":
                    persisted_contract = task.get(
                        "slide_build_request_contract"
                    )
                    if not isinstance(persisted_contract, dict):
                        persisted_contract = None
                    if not persisted_contract:
                        checkpoint_path = (
                            self._storage_data_dir
                            / "slide_deck_v6_candidates"
                            / "checkpoints"
                            / f"{task_id}.json"
                        )
                        try:
                            checkpoint = json.loads(
                                checkpoint_path.read_text(encoding="utf-8")
                            )
                        except (OSError, TypeError, ValueError):
                            checkpoint = None
                        if (
                            isinstance(checkpoint, dict)
                            and checkpoint.get("schema_version")
                            == "slide_deck_v6_checkpoint_v1"
                            and str(checkpoint.get("task_id") or "") == task_id
                            and str(checkpoint.get("course_id") or "")
                            == str(task.get("course_id") or "")
                        ):
                            mode = str(
                                checkpoint.get("mode") or "teaching"
                            )
                            theme = str(
                                checkpoint.get("theme")
                                or "qizhi-classroom"
                            )
                            persisted_contract = (
                                _slide_build_request_contract({
                                    "mode": mode,
                                    "theme": theme,
                                    "variant_key": slide_deck_variant_key(
                                        mode,
                                        theme,
                                    ),
                                    "target_schema": "slide_deck_v6",
                                    "force_rebuild": True,
                                })
                            )
                            task["slide_build_request_contract"] = (
                                persisted_contract
                            )
                            progress_path = (
                                self._storage_data_dir
                                / "slide_build_progress_v2"
                                / f"{task_id}.json"
                            )
                            try:
                                progress_manifest = json.loads(
                                    progress_path.read_text(encoding="utf-8")
                                )
                            except (OSError, TypeError, ValueError):
                                progress_manifest = None
                            if isinstance(progress_manifest, dict):
                                projection = (
                                    _persisted_slide_progress_projection(
                                        progress_manifest
                                    )
                                )
                                if (
                                    projection is not None
                                    and str(projection.get("task_id") or "")
                                    == task_id
                                ):
                                    task["slide_build_progress_v2"] = projection
                                    task["progress"] = int(
                                        projection.get("percent") or 0
                                    )
                                    task["phase"] = str(
                                        projection.get("stage") or "resuming"
                                    )
                                    task["current_phase"] = task["phase"]
                                    progress_failure = (
                                        projection.get("failure") or {}
                                    )
                                    if isinstance(progress_failure, dict):
                                        task["error_detail"] = deepcopy(
                                            progress_failure
                                        )
                                        task["error"] = str(
                                            progress_failure.get("message")
                                            or task.get("error")
                                            or ""
                                        )
                            migrated_slide_contract = True
                    if (
                        persisted_contract
                        and not task.get("request_snapshot")
                    ):
                        task["request_snapshot"] = {
                            key: deepcopy(value)
                            for key, value in persisted_contract.items()
                            if key != "schema_version"
                        }
                try:
                    persisted_generation_profile = (
                        normalize_assessment_generation_profile(
                            task.get("assessment_generation_profile")
                            or (task.get("request_snapshot") or {}).get(
                                "assessment_generation_profile"
                            )
                        )
                    )
                except ValueError:
                    persisted_generation_profile = "complete"
                task["assessment_generation_profile"] = (
                    persisted_generation_profile
                )
                request_snapshot = task.get("request_snapshot")
                if (
                    isinstance(request_snapshot, dict)
                    and request_snapshot
                    and (
                        str(task.get("type") or "") in {
                            "course_generation",
                            "teacher_outline_generation",
                        }
                        or "assessment_generation_profile"
                        in request_snapshot
                    )
                ):
                    request_snapshot["assessment_generation_profile"] = (
                        persisted_generation_profile
                    )
                task.setdefault(
                    "assessment_generation_policy_version",
                    ASSESSMENT_GENERATION_POLICY_VERSION,
                )
                task.setdefault("node_drafts", {})
                task.setdefault("operation", "generate")
                task.setdefault("candidate_id", None)
                task.setdefault("base_version_id", None)
                if task.get("type") != "teacher_outline_generation":
                    task.setdefault("blueprint_confirmed", False)
                    task.setdefault("blueprint_revision_id", None)
                task.setdefault("workspace_id", None)
                task.setdefault("base_document_revision", None)
                workflow = task.get("guided_workflow")
                if task.get("type") == "teacher_outline_generation":
                    for retired_field in (
                        "guided_workflow",
                        "blueprint_confirmed",
                        "blueprint_revision_id",
                    ):
                        if retired_field in task:
                            task.pop(retired_field, None)
                            migrated_teacher_lifecycle = True
                    if task.get("status") == "waiting_for_review":
                        course_data = self._load_task_course(task_id)
                        if _teacher_outline_result_ready(course_data):
                            task.update({
                                "status": "completed",
                                "phase": "teacher_outline_ready",
                                "current_phase": "teacher_outline_ready",
                                "progress": 100,
                                "phase_progress": 100,
                                "message": "课程大纲已生成，可选择任一讲生成教案",
                                "outline_detail_requested": False,
                                "current_nodes": [],
                                "current_node_name": "",
                            })
                            migrated_teacher_lifecycle = True
                        elif isinstance(course_data, dict) and (
                            course_data.get("outline_framework_only") is True
                            or bool(course_data.get("nodes"))
                            or bool(course_data.get("course_outline"))
                        ):
                            task.update({
                                "status": "waiting_for_input",
                                "phase": "outline_framework_ready",
                                "current_phase": "outline_framework_ready",
                                "phase_progress": 100,
                                "message": "轻量讲次方案已生成，可修改后继续生成完整大纲",
                                "outline_detail_requested": False,
                                "current_nodes": [],
                                "current_node_name": "",
                            })
                            migrated_teacher_lifecycle = True
                elif isinstance(workflow, dict):
                    legacy_review = str(
                        workflow.get("review_step") or ""
                    )
                    task["guided_workflow"] = migrate_guided_workflow(
                        workflow,
                        request=task.get("request_snapshot") or {},
                    )
                    if (
                        legacy_review == "knowledge"
                        and task.get("status") == "waiting_for_review"
                    ):
                        task["status"] = "pending"
                        task["phase"] = "course_teaching_plan_migrated"
                        task["message"] = (
                            "旧知识或教学确认点已合并，正在按新链路继续生成课程"
                        )
                if task.get("type") not in {
                    "course_generation",
                    "teacher_outline_generation",
                    "teaching_representation_build",
                    "slide_deck_variant_build",
                }:
                    task["legacy_read_only"] = True
                    if task.get("status") in ("pending", "running", "paused"):
                        task["status"] = "completed"
                        task["phase"] = "legacy_read_only"
                        task["message"] = "旧版任务仅供历史查看"
            if (
                source == LEGACY_TASKS_FILE
                or migrated_slide_contract
                or migrated_teacher_lifecycle
                or self._task_index_recovery == "last_good"
            ) and self._runtime_mode != "read_only":
                self._save_tasks_strict()
            self._task_index_state = "ready"
            self._task_index_error_code = None
        except Exception as e:
            logger.error("Failed to load tasks: %s", e)
            self.tasks = {}
            self._task_index_state = "degraded"
            self._task_index_recovery = "unavailable"
            self._task_index_error_code = "generation_job_index_unrecoverable"

    def _save_tasks_strict(self) -> None:
        """Invoke the persistence hook in strict mode without assuming its signature."""
        save_tasks = self.save_tasks
        try:
            parameters = inspect.signature(save_tasks).parameters.values()
        except (TypeError, ValueError):
            save_tasks(strict=True)
            return
        supports_strict = any(
            parameter.name == "strict"
            or parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in parameters
        )
        if supports_strict:
            save_tasks(strict=True)
            return
        # Some test and integration adapters replace the historical no-argument
        # persistence hook. Their own exceptions must still propagate so the
        # copy-on-write caller can restore the previous in-memory state.
        save_tasks()

    def save_tasks(self, *, strict: bool = False) -> None:
        """Atomically persist jobs to the deployment-persistent data root."""
        self._ensure_task_index_writable()
        try:
            TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
            persisted_tasks = self._tasks_for_persistence()
            last_good_path = self._task_index_last_good_path()
            if TASKS_FILE.exists():
                previous = self._read_task_index(TASKS_FILE)
                self._write_task_index_atomic(
                    last_good_path,
                    self._task_index_last_good_envelope(previous),
                )
            elif not last_good_path.exists():
                self._write_task_index_atomic(
                    last_good_path,
                    self._task_index_last_good_envelope({}),
                )
            self._write_task_index_atomic(TASKS_FILE, persisted_tasks)
        except Exception as e:
            logger.error("Failed to save tasks: %s", e)
            record_persistence_failure(
                component="task_index",
                operation="lifecycle_save" if strict else "save",
                error=e,
            )
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
            await asyncio.to_thread(
                self._generation_workspace_repository.save_course,
                str(workspace_id),
                course_data,
            )
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

    @staticmethod
    def _record_phase_history(
        task: dict[str, Any],
        phase: str,
        status: str,
        *,
        progress: int,
        message: str,
        timestamp: str,
    ) -> None:
        history = list(task.get("phase_history") or [])
        if history and history[-1].get("phase") == phase:
            last_status = str(history[-1].get("status") or "")
            if last_status in {"active", "paused"} or status != "active":
                history[-1] = {
                    **history[-1],
                    "status": status,
                    "progress": progress,
                    "message": message,
                    "updated_at": timestamp,
                }
            else:
                history.append({
                    "phase": phase,
                    "status": status,
                    "progress": progress,
                    "message": message,
                    "started_at": timestamp,
                    "updated_at": timestamp,
                })
        else:
            if history and history[-1].get("status") == "active":
                history[-1] = {
                    **history[-1],
                    "status": "completed",
                    "updated_at": timestamp,
                }
            history.append({
                "phase": phase,
                "status": status,
                "progress": progress,
                "message": message,
                "started_at": timestamp,
                "updated_at": timestamp,
            })
        task["phase_history"] = history[-24:]

    async def _update_phase(
        self,
        task_id: str,
        phase: str,
        progress: int,
        message: str,
        *,
        phase_progress: int | None = None,
        phase_detail: dict[str, Any] | None = None,
    ) -> bool:
        """Persist one backend-owned generation phase and broadcast it."""
        async with self._lock:
            task = self.tasks.get(task_id)
            if not task or str(task.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES:
                return False
            bounded_progress = max(0, min(int(progress), 100))
            previous_phase = str(task.get("current_phase") or task.get("phase") or "")
            previous_detail = task.get("phase_detail")
            next_detail = deepcopy(phase_detail or {})
            if (
                phase.startswith("outline_detail")
                and previous_phase.startswith("outline_detail")
                and isinstance(previous_detail, dict)
            ):
                # Several lecture tasks stream concurrently. Keep their state
                # keyed by lesson_id so a heartbeat or a faster sibling cannot
                # erase the visible content already received for another one.
                merged_lesson_statuses = deepcopy(
                    previous_detail.get("lesson_statuses") or {}
                )
                if isinstance(next_detail.get("lesson_statuses"), dict):
                    merged_lesson_statuses.update(
                        deepcopy(next_detail["lesson_statuses"])
                    )
                lesson_id = str(next_detail.get("lesson_id") or "")
                if lesson_id:
                    current_lesson = deepcopy(
                        merged_lesson_statuses.get(lesson_id) or {}
                    )
                    current_lesson["lesson_id"] = lesson_id
                    for field in (
                        "status",
                        "stage",
                        "message",
                        "progress",
                        "stream_preview",
                    ):
                        if field in next_detail:
                            current_lesson[field] = deepcopy(next_detail[field])
                    merged_lesson_statuses[lesson_id] = current_lesson
                    if (
                        "stream_preview" not in next_detail
                        and current_lesson.get("stream_preview")
                    ):
                        next_detail["stream_preview"] = str(
                            current_lesson["stream_preview"]
                        )
                if merged_lesson_statuses:
                    next_detail["lesson_statuses"] = merged_lesson_statuses
            if (
                phase == previous_phase == "outline_generation"
                and isinstance(previous_detail, dict)
                and isinstance(previous_detail.get("outline_growth"), dict)
            ):
                previous_growth = previous_detail["outline_growth"]
                next_growth = next_detail.get("outline_growth")
                if not isinstance(next_growth, dict):
                    # Heartbeats carry only the active provider unit. Keep the
                    # latest persisted tree so the visible outline never shrinks.
                    next_detail["outline_growth"] = deepcopy(previous_growth)
                elif int(next_growth.get("completed_sections") or 0) < int(
                    previous_growth.get("completed_sections") or 0
                ):
                    # Parallel chapter calls can report an older snapshot after
                    # another chapter saved. Preserve the monotonic tree while
                    # still following the newly active batch.
                    merged_growth = deepcopy(previous_growth)
                    merged_growth["active_batch_id"] = next_growth.get(
                        "active_batch_id"
                    )
                    merged_growth["active_chapter_number"] = next_growth.get(
                        "active_chapter_number"
                    )
                    next_detail["outline_growth"] = merged_growth
            task["phase"] = phase
            task["current_phase"] = phase
            task["phase_progress"] = max(
                0,
                min(int(phase_progress if phase_progress is not None else bounded_progress), 100),
            )
            task["phase_detail"] = next_detail
            task["progress"] = max(int(task.get("progress") or 0), bounded_progress)
            task["message"] = message
            now = datetime.now().isoformat()
            task["updated_at"] = now
            task["heartbeat_at"] = now
            self._record_phase_history(
                task,
                phase,
                "active",
                progress=bounded_progress,
                message=message,
                timestamp=now,
            )
            self.save_tasks()
        await self._push_progress(task_id)
        return True

    async def _update_task_status(
        self,
        task_id: str,
        status: str,
        message: str | None = None,
        error: str | None = None,
        error_detail: dict[str, Any] | None = None,
        completed_nodes: int | None = None,
        total_nodes: int | None = None,
        allow_reactivation: bool = False,
    ) -> bool:
        """更新任务状态，并阻止迟到后台协程覆盖人工或终态决定。"""
        async with self._lock:
            current = self.tasks.get(task_id)
            if not current:
                return False
            current_status = str(current.get("status") or "")
            if (
                current_status in BACKGROUND_FROZEN_TASK_STATUSES
                and not allow_reactivation
            ):
                return False
            task = deepcopy(current)
            task["status"] = status
            if status in {
                "pending",
                "running",
                "waiting_for_input",
                "waiting_for_review",
                "completed",
                "completed_with_warnings",
            }:
                # A recovered task must not keep the failure metadata from its
                # previous attempt.  Otherwise the workbench can render a
                # successful result together with a stale provider error.
                task["error"] = None
                task["error_detail"] = None
                task["error_code"] = None
                task["error_user_message"] = None
            elif status in {"failed", "error"}:
                task["error_user_message"] = None
            if message is not None:
                task["message"] = message
            if error is not None:
                task["error"] = error
            if error_detail is not None:
                task["error_detail"] = deepcopy(error_detail)
                detail_code = str(error_detail.get("code") or "")
                if detail_code:
                    task["error_code"] = detail_code
            if completed_nodes is not None:
                task["completed_nodes"] = completed_nodes
            if total_nodes is not None:
                task["total_nodes"] = total_nodes
            now = datetime.now().isoformat()
            task["updated_at"] = now
            task["heartbeat_at"] = now
            phase_status = {
                "completed": "completed",
                "completed_with_warnings": "completed",
                "failed": "error",
                "error": "error",
                "paused": "paused",
            }.get(status)
            if phase_status:
                self._record_phase_history(
                    task,
                    str(task.get("current_phase") or task.get("phase") or status),
                    phase_status,
                    progress=int(task.get("progress") or 0),
                    message=str(task.get("message") or error or ""),
                    timestamp=now,
                )
            self._commit_task_draft(task_id, task)
            return True

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
            task = self.tasks.get(task_id)
            if not task or str(task.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES:
                return
            task["completed_nodes"] = completed
            task["total_nodes"] = total
            if task.get("type") == "course_generation" and task.get("phase") == "content_generation":
                task["phase_progress"] = int(completed / max(1, total) * 100) if total else 0
            task["progress"] = max(
                int(task.get("progress") or 0),
                min(progress, 90 if task.get("type") == "course_generation" else 100),
            )
            task["updated_at"] = datetime.now().isoformat()
            task["heartbeat_at"] = task["updated_at"]
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
                "error_code": task.get("error_code"),
                "error_user_message": task.get("error_user_message"),
                "progress": progress,
                "current_node_name": task.get("current_node_name", ""),
                "current_node_location": deepcopy(
                    task.get("current_node_location") or {}
                ),
                "current_nodes": current_nodes,
                "completed_nodes": completed_nodes,
                "total_nodes": total_nodes,
                "estimated_time_remaining": 0,
                "updated_at": task.get("updated_at"),
                "heartbeat_at": task.get("heartbeat_at"),
                "phase_history": deepcopy(task.get("phase_history") or []),
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
            if not task or str(task.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES:
                return
            for active_node in task.get("current_nodes", []):
                if active_node.get("node_id") == node_id:
                    active_node["generated_chars"] = generated_chars
                    break
            task["updated_at"] = datetime.now().isoformat()
            self.save_tasks()

    @staticmethod
    def _failed_practice_targets(
        assets: dict[str, list[dict[str, Any]]],
        *,
        expected_node_ids: list[str] | None = None,
    ) -> dict[str, list[str]]:
        """Return rejected and completely absent exercise slots by section."""
        expected_levels = (
            "concept_check",
            "objective_practice",
            "mastery_check",
        )
        failed: dict[str, list[str]] = {}
        valid_slots: set[tuple[str, str]] = set()
        for question in assets.get("questions") or []:
            quality = question.get("quality_report") or {}
            node_id = str(question.get("node_id") or "")
            practice_level = str(question.get("practice_level") or "")
            valid = (
                question.get("quality_status") != "passed"
                or quality.get("passed") is not True
                or not question.get("practice_contract_revision_id")
                or not question.get("input_contract")
            ) is False
            if node_id and practice_level and valid:
                valid_slots.add((node_id, practice_level))
            elif node_id and practice_level:
                failed.setdefault(node_id, []).append(practice_level)

        for node_id in expected_node_ids or []:
            normalized_node_id = str(node_id or "")
            if not normalized_node_id:
                continue
            for practice_level in expected_levels:
                if (normalized_node_id, practice_level) not in valid_slots:
                    failed.setdefault(normalized_node_id, []).append(practice_level)
        return {
            node_id: list(dict.fromkeys(levels))
            for node_id, levels in failed.items()
        }

    async def _repair_failed_practice_nodes(
        self,
        task_id: str,
        asset_course: dict[str, Any],
        question_bank_bundle: dict[str, Any],
        asset_bundle: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Use AI only for sections rejected by deterministic compilation.

        Course content and already valid exercises stay immutable. This closes
        the former gap where the generation pipeline required universal
        exercises but never invoked the universal assessment orchestrator.
        """
        asset_plan = asset_bundle.get("plan") or {}
        questions_enabled = (
            not asset_plan
            or "questions" in (asset_plan.get("enabled_asset_types") or [])
        )
        expected_node_ids = (
            [
                str(node.get("node_id") or "")
                for node in asset_course.get("nodes") or []
                if int(node.get("node_level") or 1) == 2
                and node.get("node_id")
            ]
            if questions_enabled
            else []
        )
        failed_targets = (
            self._failed_practice_targets(
                asset_bundle.get("assets") or {},
                expected_node_ids=expected_node_ids,
            )
            if questions_enabled
            else {}
        )
        failed_node_ids = list(failed_targets)
        if not failed_node_ids:
            return question_bank_bundle, asset_bundle, {
                "status": "not_needed",
                "target_node_ids": [],
                "target_node_count": 0,
            }

        self.tasks[task_id]["asset_repair_requested"] = True
        self.save_tasks()
        await self._update_phase(
            task_id,
            "practice_repair",
            94,
            f"正在定向修复 {len(failed_node_ids)} 个小节的练习，不重做课程正文",
            phase_progress=70,
            phase_detail={
                "target_node_ids": failed_node_ids,
                "target_node_count": len(failed_node_ids),
                "repair_scope": "failed_practice_only",
            },
        )
        completed_repair_nodes: list[str] = []

        async def checkpoint_repair_progress(event: dict[str, Any]) -> None:
            completed_items = max(0, int(event.get("completed_items") or 0))
            total_items = max(1, int(event.get("total_items") or 0))
            await self._update_phase(
                task_id,
                "practice_repair",
                94,
                f"正在生成并验证练习 {completed_items}/{total_items}",
                phase_progress=(
                    70 + int(min(completed_items, total_items) / total_items * 20)
                ),
                phase_detail={
                    "completed_item_count": completed_items,
                    "target_item_count": total_items,
                    "target_node_count": len(failed_node_ids),
                    "repair_scope": "failed_practice_only",
                },
            )

        async def checkpoint_repaired_node(event: dict[str, Any]) -> None:
            nonlocal question_bank_bundle
            node_id = str(event.get("node_id") or "")
            contracts = event.get("contracts") or {}
            if not node_id or not contracts:
                return
            # Checkpoint per question, not per section: keep whichever
            # practice levels settled on their own merit even when a sibling
            # in the same section failed, so a retry only redoes the failures.
            requested_levels = list(failed_targets.get(node_id) or [])
            settled_levels = [
                str(level)
                for level in (event.get("settled_practice_levels") or [])
                if str(level) in contracts
            ]
            if not settled_levels:
                return
            persisted_levels = [
                level for level in requested_levels if level in settled_levels
            ] or settled_levels
            settled_contracts = {
                level: deepcopy(value)
                for level, value in contracts.items()
                if str(level) in set(settled_levels)
            }
            partial_course = deepcopy(asset_course)
            partial_course["_assessment_generated_contracts"] = {
                node_id: settled_contracts,
            }
            partial_compilation = compile_learning_assets(partial_course)
            partial_question_bank = partial_compilation.pop(
                "question_bank_bundle"
            )
            web_enrichment = deepcopy(
                question_bank_bundle.get("web_enrichment") or {}
            )
            question_bank_bundle = reconcile_scoped_question_bank(
                question_bank_bundle,
                partial_question_bank,
                node_ids=[node_id],
                practice_levels_by_node={
                    node_id: persisted_levels,
                },
                preserve_reviewed=True,
                preserve_global_assessments=True,
            )
            question_bank_bundle["web_enrichment"] = web_enrichment
            question_bank_bundle = self._question_bank_repository.save_bundle(
                str(self.tasks[task_id]["course_id"]),
                question_bank_bundle,
                activate=False,
            )
            if event.get("passed"):
                completed_repair_nodes.append(node_id)
            await self._update_phase(
                task_id,
                "practice_repair",
                94,
                (
                    f"练习已修复 {len(completed_repair_nodes)}/"
                    f"{len(failed_node_ids)} 个小节"
                ),
                phase_progress=(
                    70
                    + int(
                        len(completed_repair_nodes)
                        / max(1, len(failed_node_ids))
                        * 25
                    )
                ),
                phase_detail={
                    "completed_node_ids": completed_repair_nodes,
                    "completed_node_count": len(completed_repair_nodes),
                    "target_node_count": len(failed_node_ids),
                    "checkpoint_policy": "per_question",
                },
            )

        prepared_course = await self._assessment_orchestrator.prepare_course(
            asset_course,
            node_ids=failed_node_ids,
            practice_levels_by_node=failed_targets,
            on_progress=checkpoint_repair_progress,
            on_chapter_complete=checkpoint_repaired_node,
            reference_package=deepcopy(
                asset_course.get("_question_reference_package") or {}
            )
            or None,
            generation_profile=str(
                (self.tasks[task_id].get("request_snapshot") or {}).get(
                    "assessment_generation_profile"
                )
                or "complete"
            ),
            generation_scope="scoped_repair",
        )
        repaired_compilation = compile_learning_assets(prepared_course)
        rebuilt_question_bank = repaired_compilation.pop("question_bank_bundle")
        repaired_question_bank = reconcile_scoped_question_bank(
            question_bank_bundle,
            rebuilt_question_bank,
            node_ids=failed_node_ids,
            preserve_reviewed=True,
            preserve_global_assessments=True,
            practice_levels_by_node=failed_targets,
        )
        # Web evidence belongs to the course-level source package. A scoped
        # exercise repair must not erase the enrichment receipt of other nodes.
        repaired_question_bank["web_enrichment"] = deepcopy(
            question_bank_bundle.get("web_enrichment") or {}
        )
        repaired_assets = compile_learning_assets(
            prepared_course,
            question_bank_bundle=repaired_question_bank,
        )
        repaired_assets.pop("question_bank_bundle", None)
        remaining_targets = self._failed_practice_targets(
            repaired_assets.get("assets") or {},
            expected_node_ids=expected_node_ids,
        )
        remaining_node_ids = list(remaining_targets)
        return repaired_question_bank, repaired_assets, {
            "status": "passed" if not remaining_node_ids else "incomplete",
            "target_node_ids": failed_node_ids,
            "target_node_count": len(failed_node_ids),
            "target_slot_count": sum(len(levels) for levels in failed_targets.values()),
            "target_practice_levels": deepcopy(failed_targets),
            "remaining_node_ids": remaining_node_ids,
            "remaining_node_count": len(remaining_node_ids),
            "generation_audit": deepcopy(
                prepared_course.get("_assessment_generation_audit") or {}
            ),
        }

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
        if task.get("outline_repair_requested"):
            fresh_course = self._restore_task_confirmed_outline_snapshot(
                task,
                fresh_course,
            )
            await self._save_task_course(task_id, fresh_course)
            await self._update_phase(
                task_id,
                "quality_repair",
                85,
                "已恢复教师确认的目录版本，正在定向修复学习资产",
                phase_progress=10,
                phase_detail={
                    "repair_scope": "confirmed_outline_snapshot",
                    "outline_artifact_revision": guided_step_state(
                        task["guided_workflow"],
                        "outline",
                    ).get("artifact_revision"),
                },
            )
        stage_artifacts = fresh_course.setdefault("generation_stage_artifacts", {})
        prepared = stage_artifacts.get("content_candidate") or {}
        repair_requested = bool(
            task.get("asset_repair_requested")
            or task.get("quality_repair_requested")
            or task.get("outline_repair_requested")
        )
        if (
            not repair_requested
            and prepared.get("status") == "completed"
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

        repaired_difficulty_node_ids: list[str] = []
        if task.get("quality_repair_requested"):
            repaired_difficulty_node_ids = repair_compiled_difficulty_double_spikes(
                fresh_course
            )
            if repaired_difficulty_node_ids:
                await self._update_phase(
                    task_id,
                    "quality_repair",
                    86,
                    f"已校正 {len(repaired_difficulty_node_ids)} 处难度曲线支架，正在重新检查学习资产",
                    phase_progress=15,
                    phase_detail={
                        "repaired_difficulty_node_ids": repaired_difficulty_node_ids,
                        "repaired_difficulty_count": len(repaired_difficulty_node_ids),
                        "repair_scope": "quality_gate",
                    },
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
            "正在编译课程学习资产与知识映射",
            phase_progress=20,
        )
        asset_course = deepcopy(fresh_course)
        if hasattr(self.course_service, "load_course_evidence_catalog"):
            asset_course["evidence_catalog"] = self.course_service.load_course_evidence_catalog(
                fresh_course
            )
        questions_enabled = "questions" in (
            compile_learning_asset_plan(asset_course).get("enabled_asset_types") or []
        )
        assessment_profile = compile_course_assessment_profile(
            asset_course
        )
        assessment_objectives = compile_assessment_objectives(
            asset_course,
            assessment_profile,
        )
        assessment_blueprint = compile_course_assessment_blueprint(
            asset_course,
            profile=assessment_profile,
            objectives=assessment_objectives,
        )
        retrieval_artifact = deepcopy(
            stage_artifacts.get("assessment_retrieval") or {}
        )
        reference_package = deepcopy(
            retrieval_artifact.get("reference_package") or {}
        )
        if (
            questions_enabled
            and (
                not reference_package
                or reference_package.get("blueprint_revision_id")
                != assessment_blueprint.get("blueprint_revision_id")
            )
        ):
            reference_package = compile_local_reference_package(
                asset_course,
                objectives=assessment_objectives,
                blueprint=assessment_blueprint,
            )
            course_retrieval_package = deepcopy(
                (
                    stage_artifacts.get("web_retrieval") or {}
                ).get("package")
                or fresh_course.get("retrieval_package")
                or {}
            )
            reference_package = await enrich_reference_package_with_web(
                asset_course,
                reference_package,
                objectives=assessment_objectives,
                retrieval_package=course_retrieval_package or None,
                user_id=str(
                    (task.get("request_snapshot") or {}).get(
                        "_retrieval_actor_id"
                    )
                    or ""
                )
                or None,
            )
            stage_artifacts["assessment_retrieval"] = {
                "status": "frozen",
                "reference_package": deepcopy(reference_package),
                "package_revision_id": reference_package.get(
                    "package_revision_id"
                ),
            }
            await self._save_task_course(task_id, fresh_course)
        asset_course["_question_reference_package"] = deepcopy(
            reference_package
        )
        if questions_enabled and reference_package.get("retrieval_mode") != "off":
            asset_course = await self._assessment_orchestrator.prepare_course(
                asset_course,
                reference_package=reference_package,
                generation_profile=str(
                    (task.get("request_snapshot") or {}).get(
                        "assessment_generation_profile"
                    )
                    or "complete"
                ),
                generation_scope="full_generation",
            )
        asset_bundle = compile_learning_assets(asset_course)
        question_bank_bundle = asset_bundle.pop("question_bank_bundle")
        await self._update_phase(
            task_id,
            "question_bank",
            92,
            (
                "正在整理课程题库、覆盖矩阵与风险审核队列"
                if questions_enabled
                else "已按设置暂缓生成题目"
            ),
            phase_progress=55,
        )
        previous_question_bank = self._question_bank_repository.load_bundle(
            str(task["course_id"])
        )
        if repair_requested and previous_question_bank:
            # Node-level repair checkpoints are already immutable, validated
            # question-bank revisions. Rebuilding them from deterministic
            # fallbacks would throw away successful work from a prior run.
            question_bank_bundle = previous_question_bank
        else:
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
        (
            question_bank_bundle,
            asset_bundle,
            practice_repair_summary,
        ) = await self._repair_failed_practice_nodes(
            task_id,
            asset_course,
            question_bank_bundle,
            asset_bundle,
        )
        # Learning-asset compilation deterministically assigns the objective
        # identities and course-knowledge bindings used by its own contracts.
        # Persist that exact node projection before evaluating or publishing so
        # the course and its generated assets share one source of truth.
        fresh_course["nodes"] = deepcopy(asset_course.get("nodes") or [])
        fresh_course["question_analysis_required"] = questions_enabled
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
            "not_required"
            if not questions_enabled
            else "passed"
            if all(
                (item.get("question_analysis") or {}).get("status")
                == "passed"
                for item in analyzed_questions
            )
            else "blocked"
        )
        fresh_course["question_analysis_summary"] = {
            "source": (
                "deferred_by_user"
                if not questions_enabled
                else "targeted_ai_repair"
                if practice_repair_summary.get("target_node_count")
                else "compiled_contract"
            ),
            "model_call_count": int(
                (
                    practice_repair_summary.get("generation_audit") or {}
                ).get("model_call_count")
                or 0
            ),
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
        fresh_course["practice_repair_summary"] = practice_repair_summary
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
            "practice_repair": deepcopy(practice_repair_summary),
        }
        if repair_requested and isinstance(task.get("guided_workflow"), dict):
            workflow = task["guided_workflow"]
            if guided_step_confirmed(workflow, "content"):
                content_state = guided_step_state(workflow, "content")
                content_state["artifact_revision"] = guided_artifact_revision(
                    "content",
                    fresh_course,
                    request=task.get("request_snapshot") or {},
                )
                content_state["input_revisions"] = (
                    guided_expected_input_revisions(workflow, "content")
                )
        await self._save_task_course(task_id, fresh_course)
        task.pop("asset_repair_requested", None)
        task.pop("outline_repair_requested", None)
        task.pop("quality_repair_requested", None)
        task.pop("quality_repair_scopes", None)
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

    async def _publish_course_artifacts_to_space(
        self, task_id: str, course_data: dict
    ) -> dict[str, Any]:
        """Write finished artifacts into the teacher's course space (F-2).

        Runs at completion, after artifacts are final. Failure is recorded on the
        task and surfaced to the caller, but never changes the generation outcome:
        the course generated fine, filing it is a downstream action.
        """
        task = self.tasks.get(task_id) or {}
        owner_id = str(
            (task.get("request_snapshot") or {}).get("_retrieval_actor_id")
            or (course_data.get("generation_request") or {}).get("_retrieval_actor_id")
            or ""
        ).strip()
        if not owner_id:
            # 缺教师身份时不建包、不写文件，并如实说明原因——否则老师只会看到
            # "没入库"，分不清是系统坏了还是身份没带上。
            report = {
                "schema_version": PUBLISH_SCHEMA_VERSION,
                "status": "skipped",
                "reason": MISSING_TEACHER_IDENTITY,
                "message": SKIP_MESSAGES[MISSING_TEACHER_IDENTITY],
                "package_id": "",
                "written": [],
                "unchanged": [],
                "conflicts": [],
                "failures": [],
            }
        else:
            report = await asyncio.to_thread(
                publish_course_artifacts,
                course_data,
                owner_id=owner_id,
            )
        async with self._lock:
            fresh = self.tasks.get(task_id)
            if fresh is not None:
                fresh["course_space_publication"] = deepcopy(report)
                self.save_tasks()
        if report.get("status") == "failed":
            logger.warning(
                "课程产物入教师文件空间部分失败（课程仍然有效）：%s",
                report.get("failures"),
            )
        return report

    async def _complete_task(
        self, task_id: str, course_data: dict
    ) -> None:
        """Mark task as completed and send failure report if needed.

        **Validates: Requirements 13.2**
        """
        task = self.tasks.get(task_id)
        if (
            not task
            or str(task.get("status") or "") not in BACKGROUND_ACTIVE_TASK_STATUSES
        ):
            return
        guided_workflow = task.get("guided_workflow")
        content_stage = (
            course_data.get("generation_stage_artifacts") or {}
        ).get("content_candidate") or {}
        confirmed_content_checkpoint = bool(
            isinstance(guided_workflow, dict)
            and guided_step_confirmed(guided_workflow, "content")
            and not task.get("asset_repair_requested")
            and not task.get("quality_repair_requested")
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
        if not await self._update_phase(
            task_id,
            "finalizing",
            98,
            "正在保存最终课程",
            phase_progress=90,
        ):
            return

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
                if publication_allowed:
                    await self._pause_for_guided_review(
                        task_id,
                        fresh_course,
                        "release",
                        phase="release_ready",
                        progress=98,
                        message="全部检查通过，等待确认发布",
                        phase_detail={
                            "publication_allowed": True,
                            "source_chain_passed": True,
                            "blocking_issue_count": 0,
                        },
                    )
                    return
                # A release step cannot simultaneously be waiting for user
                # confirmation and be impossible to confirm. Keep the quality
                # evidence, clear the false review gate, and let the existing
                # terminal branch settle this workspace as quality_failed.
                self._mark_release_gate_blocked(guided_workflow)

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

        # F-2：产物已经定稿，落进教师文件空间。这是下游动作——写入失败如实记在
        # 任务上，但绝不改变课程的生成结果（`publish_course_artifacts` 本身
        # 不抛异常，这里再加一层保险）。
        try:
            await self._publish_course_artifacts_to_space(task_id, course_data)
        except Exception as exc:  # noqa: BLE001 - 入库失败不得回滚课程
            logger.warning("课程产物入教师文件空间失败：%s", exc)

        status_updated = False
        if promotion_conflict:
            status_updated = await self._update_task_status(
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
                    self._failed_node_report_entry(task_id, n)
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
            status_updated = await self._update_task_status(
                task_id,
                "failed" if all_learning_nodes_failed else "completed_with_warnings",
                message=(
                    "课程生成失败：全部学习节点生成失败"
                    if all_learning_nodes_failed
                    else f"课程部分完成（{len(failed_nodes)} 个节点失败）"
                ),
            )
        elif candidate_id and not publication_allowed:
            status_updated = await self._update_task_status(
                task_id,
                "completed_with_warnings",
                message="候选课程存在阻断性质量问题，当前版本保持不变",
            )
        elif not publication_allowed:
            status_updated = await self._update_task_status(
                task_id,
                "completed_with_warnings",
                message="课程存在阻断性质量问题，未发布当前版本",
            )
        elif not strict_quality_passed:
            status_updated = await self._update_task_status(
                task_id,
                "completed_with_warnings",
                message="课程已生成并发布，仍有非阻断性优化建议",
            )
        else:
            status_updated = await self._update_task_status(
                task_id, "completed",
                message="课程生成完成",
            )

        # The user may pause or cancel while finalization is doing its last
        # file-space work. If that decision won the race, keep its progress and
        # phase intact instead of painting a completed projection over it.
        if not status_updated:
            return

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
                if publication_allowed:
                    task.pop("quality_failure", None)
                else:
                    task["quality_failure"] = self._quality_failure_summary(
                        fresh_course,
                        previous=(
                            task.get("quality_failure")
                            if isinstance(task.get("quality_failure"), dict)
                            else None
                        ),
                        advance_repeat=True,
                    )
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

    async def record_node_render_diagnostics(
        self,
        task_id: str,
        node_id: str,
        diagnostics: dict[str, Any],
    ) -> dict[str, Any]:
        """Store what the browser actually saw when it rendered this node.

        The backend gate is pure string matching and cannot run KaTeX, so
        without this channel a formula the renderer refuses to draw is
        indistinguishable from one that renders fine. The frontend validates
        with the real renderer and posts the counts here; the stored value is
        then fed to ``evaluate_node_content`` so a render failure becomes a
        blocking issue instead of a silent degradation.

        Re-validating the same node overwrites the previous record: the newest
        render is the truth, and a fixed node must be able to clear its issues.
        """
        math_failures = max(0, int(diagnostics.get("math_failure_count") or 0))
        block_failures = max(0, int(diagnostics.get("block_failure_count") or 0))
        stored = {
            "math_failure_count": math_failures,
            "block_failure_count": block_failures,
            "reported_at": datetime.now().isoformat(),
        }

        def update(course_data: dict[str, Any]) -> dict[str, Any]:
            for node in course_data.get("nodes", []):
                if str(node.get("node_id") or "") != node_id:
                    continue
                node["render_diagnostics"] = deepcopy(stored)
                # Re-score immediately so the node's own quality reflects the
                # render verdict without waiting for the next generation pass.
                node["generation_quality"] = evaluate_node_content(
                    str(node.get("node_content") or ""),
                    node,
                    render_diagnostics=stored,
                )
                break
            return course_data

        await self._mutate_task_course(task_id, update)
        await self._push_progress(task_id)
        return stored

    async def _set_node_status(
        self,
        task_id: str,
        course_id: str,
        node_id: str,
        status: NodeStatus,
        error_summary: str | None = None,
        error_code: str | None = None,
        error_retryable: bool | None = None,
    ) -> None:
        """Update a node's generation_status in course data.

        ``error_summary`` stays the raw technical text; ``error_code`` is the
        stable classification the UI explains the failure from.
        """
        def update(course_data: dict[str, Any]) -> dict[str, Any]:
            for node in course_data.get("nodes", []):
                if node.get("node_id") == node_id:
                    node["generation_status"] = status.value
                    if error_summary is not None:
                        node["error_summary"] = error_summary
                    if error_code is not None:
                        node["error_code"] = error_code
                    if error_retryable is not None:
                        node["error_retryable"] = error_retryable
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
            return await asyncio.to_thread(
                self._generation_workspace_repository.update_course,
                str(workspace_id),
                updater,
            )
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
            and t["status"] in (
                "pending",
                "running",
                "waiting_for_input",
                "waiting_for_review",
            )
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
