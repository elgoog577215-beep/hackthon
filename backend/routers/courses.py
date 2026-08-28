# =============================================================================
# 课程管理路由
# 课程 CRUD、课程生成、节点级操作、大纲编辑、生成配置
# =============================================================================

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from typing import Optional
import sys
import os
import uuid
from datetime import date, datetime, timezone

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from models import CourseGenerationRequest, LocateNodeRequest, NodeGenerationConfig
from course_baseline import confirmed_generation_request
from storage import storage
from course_service import get_course_service
from course_space_publication import (
    MISSING_TEACHER_IDENTITY,
    SKIP_MESSAGES,
    publish_course_artifacts,
)
from learning_progress import project_learning_objective_bindings
from dependencies import (
    get_course_document_repository,
    get_course_or_404,
    require_task_manager,
    get_node_or_404,
)
from course_repository import CourseMigrationConflict
from storage_utils import save_course_compat
from task_manager import TaskManager
from learner_context import DEFAULT_USER_ID, require_actor_id, resolve_user_id
from learning_snapshots import learning_snapshot_repository
from web_material_curation import (
    CURATION_METADATA_KEY,
    load_course_exclusions,
    normalize_exclusions,
)
from teacher_course_space import teacher_course_space_repository
from material_pipeline import prepare_course_materials
from material_storage import MaterialStorageError, material_repository
from teaching_calendar import teaching_calendar_repository
from course_web_research import (
    MAX_RESULTS_PER_SESSION,
    WEB_RESEARCH_METADATA_KEY,
    normalize_candidate,
    normalize_scope,
    research_session,
    scoped_research_projection,
    upsert_research_session,
)
from web_material_search import (
    candidate_from_source,
    derive_search_queries,
    safe_query_term,
)
from web_document_reader import (
    build_research_summary,
    diversify_retrieval_sources,
    enrich_web_candidates,
)
from web_retrieval import RetrievalRequest, configured_retrieval_gateway

router = APIRouter(tags=["courses"])


# =============================================================================
# Request models for new endpoints
# =============================================================================

class CustomInstructionRequest(BaseModel):
    """Request body for setting a custom instruction on a node."""
    instruction: str


class RenderDiagnosticsRequest(BaseModel):
    """What the browser saw when it rendered a node's body.

    Posted by the frontend after it validates content with the real renderer
    (``utils/render-validation.ts``). The backend cannot run KaTeX, so this is
    the only way a genuine render failure reaches the publication gate.
    """
    math_failure_count: int = 0
    block_failure_count: int = 0


class NodeConfigUpdateRequest(BaseModel):
    """Request body for updating a node's generation config."""
    difficulty: Optional[str] = None
    style: Optional[str] = None
    target_word_range: Optional[tuple] = None
    include_code_examples: Optional[bool] = None
    include_exercises: Optional[bool] = None
    custom_instruction: Optional[str] = None


class CourseDocumentMigrationRequest(BaseModel):
    source_checksum: str
    confirm: bool = False


class TeacherCourseCreateRequest(BaseModel):
    course_name: str = Field(min_length=1, max_length=200)
    academic_year: str = Field(default="", max_length=30)
    term: str = Field(default="", max_length=30)
    course_code: str = Field(default="", max_length=64)
    course_goal: str = Field(default="", max_length=1500)
    default_location: str = Field(default="", max_length=200)
    target_grade: str = Field(default="", max_length=100)
    course_category: str = Field(default="", max_length=100)
    target_major: str = Field(default="", max_length=200)
    credits: float | None = Field(default=None, ge=0, le=100)
    total_hours: int | None = Field(default=None, ge=0, le=10000)
    assessment_method: str = Field(default="", max_length=500)
    course_intro: str = Field(default="", max_length=3000)
    teaching_goals: str = Field(default="", max_length=3000)
    generation_request: Optional[CourseGenerationRequest] = None


class WebMaterialCurationRequest(BaseModel):
    """教师剔除的联网来源，按课程持久保存。"""
    excluded_source_ids: list[str] = []
    excluded_urls: list[str] = []


class CourseWebResearchSearchRequest(BaseModel):
    """老师在课程工作台发起的显式联网调研。"""

    brief: str = Field(min_length=2, max_length=2_000)
    stage: str = Field(default="foundation", min_length=1, max_length=50)
    lesson_id: str = Field(default="", max_length=160)
    queries: list[str] = Field(default_factory=list, max_length=8)


class CourseWebResearchSelectionRequest(BaseModel):
    """老师确认要进入当前课程资料链的网页来源。"""

    selected_source_ids: list[str] = Field(default_factory=list, max_length=16)


# =============================================================================
# Core course endpoints
# =============================================================================


def _resume_summary(snapshot: dict | None) -> dict | None:
    if not snapshot or not str(snapshot.get("node_id") or "").strip():
        return None
    task = snapshot.get("task_state") if isinstance(snapshot.get("task_state"), dict) else {}
    return {
        "kind": str(task.get("kind") or "reading"),
        "status": str(task.get("status") or "active"),
        "node_id": str(snapshot.get("node_id") or ""),
        "node_name": str(snapshot.get("node_name") or ""),
        "activity_at": str(snapshot.get("activity_at") or snapshot.get("updated_at") or ""),
    }


def _list_courses_with_resume(
    user_id: str,
    known_task_ids: set[str],
    teacher_course_ids: set[str] | None = None,
) -> list[dict]:
    hidden_teacher_courses = teacher_course_ids or set()
    courses = [
        course for course in storage.list_courses()
        if course.get("authoring_surface") != "teacher"
        and str(course.get("course_id") or "") not in hidden_teacher_courses
        and (
            course.get("is_published")
            or not course.get("generation_job_id")
            or str(course.get("generation_job_id")) in known_task_ids
        )
    ]
    for course in courses:
        course.pop("owner_id", None)
        course_id = str(course.get("course_id") or "")
        summary = _resume_summary(learning_snapshot_repository.load(user_id, course_id))
        if summary:
            course["resume"] = summary
    return courses


def _list_teacher_courses(
    known_task_ids: set[str],
    next_sessions_by_course_id: dict[str, dict] | None = None,
    owner_id: str | None = None,
) -> list[dict]:
    courses = [
        course for course in storage.list_courses()
        if (
            owner_id is None
            or str(course.get("owner_id") or "") == owner_id
        )
        and (
            course.get("is_published")
            or not course.get("generation_job_id")
            or str(course.get("generation_job_id")) in known_task_ids
        )
    ]
    upcoming = next_sessions_by_course_id or {}
    for course in courses:
        course.pop("owner_id", None)
        next_session = upcoming.get(str(course.get("course_id") or ""))
        if not next_session:
            continue
        course["next_session"] = next_session
        course["academic_year"] = str(course.get("academic_year") or next_session.get("academic_year") or "")
        course["term"] = str(course.get("term") or next_session.get("term") or "")
    return courses


def _teacher_course_library_projection(owner_id: str, known_task_ids: set[str]) -> list[dict]:
    sessions = teaching_calendar_repository.list_sessions(owner_id, date_from=date.today())
    next_sessions_by_course_id: dict[str, dict] = {}
    for session in sessions:
        course_id = str(session.get("course_id") or "")
        if not course_id or course_id in next_sessions_by_course_id:
            continue
        next_sessions_by_course_id[course_id] = {
            "session_id": str(session.get("session_id") or ""),
            "sequence": int(session.get("sequence") or 0),
            "date": str(session.get("date") or ""),
            "start_time": str(session.get("start_time") or ""),
            "end_time": str(session.get("end_time") or ""),
            "content_summary": str(session.get("content_summary") or ""),
            "location": str(session.get("location") or ""),
            "lesson_plan_status": str(session.get("lesson_plan_status") or ""),
            "ppt_status": str(session.get("ppt_status") or ""),
            "academic_year": str(session.get("academic_year") or ""),
            "term": str(session.get("term") or ""),
        }
    return _list_teacher_courses(
        known_task_ids,
        next_sessions_by_course_id,
        owner_id,
    )


def _require_unpublished_teacher_course_access(course: dict, request: Request) -> None:
    """Hide an unpublished teacher course from every actor except its owner."""
    if course.get("authoring_surface") != "teacher" or (
        course.get("is_published") or course.get("course_document_publication")
    ):
        return
    owner_id = str(course.get("owner_id") or "").strip()
    if not owner_id:
        return
    actor_id = require_actor_id(request.headers.get("X-User-Id"))
    if actor_id != owner_id:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "teacher_course_unavailable",
                "message": "课程不存在或不属于当前教师",
            },
        )


def _require_teacher_course_write_access(course: dict, request: Request) -> None:
    """Require the owner for every mutation, including published courses."""
    if course.get("authoring_surface") != "teacher":
        return
    owner_id = str(course.get("owner_id") or "").strip()
    if not owner_id:
        return
    actor_id = require_actor_id(request.headers.get("X-User-Id"))
    if actor_id != owner_id:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "teacher_course_unavailable",
                "message": "课程不存在或不属于当前教师",
            },
        )


@router.get("/courses")
async def list_courses(
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
):
    user_id = resolve_user_id(request.headers.get("X-User-Id"))
    known_task_ids = {str(task_id) for task_id in tm.tasks}
    teacher_course_ids = {
        str(task.get("course_id") or "")
        for task in tm.tasks.values()
        if task.get("type") == "teacher_outline_generation"
    }
    return await run_in_threadpool(
        _list_courses_with_resume,
        user_id,
        known_task_ids,
        teacher_course_ids,
    )


@router.get("/teacher/courses")
async def list_teacher_courses(
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
):
    known_task_ids = {str(task_id) for task_id in tm.tasks}
    owner_id = require_actor_id(request.headers.get("X-User-Id"))
    return await run_in_threadpool(_teacher_course_library_projection, owner_id, known_task_ids)


@router.post("/teacher/courses", status_code=201)
async def create_teacher_course(
    body: TeacherCourseCreateRequest,
    request: Request,
):
    """Create one empty teacher course and its bound file space."""
    course_name = body.course_name.strip()
    if not course_name:
        raise HTTPException(status_code=422, detail="请填写课程名称")
    now = datetime.now(timezone.utc)
    start_year = now.year if now.month >= 8 else now.year - 1
    academic_year = body.academic_year.strip() or f"{start_year}-{start_year + 1}"
    term = body.term.strip() or ("秋季" if now.month >= 8 else "春季")
    owner_id = require_actor_id(request.headers.get("X-User-Id"))
    course_id = str(uuid.uuid4())
    generation_request = (
        confirmed_generation_request(body.generation_request)
        if body.generation_request
        else {}
    )
    repository = get_course_document_repository()
    await repository.create_teacher_draft(
        course_id,
        title=course_name,
        metadata={
            "owner_id": owner_id,
            "academic_year": academic_year,
            "term": term,
            "course_profile": {
                "course_code": body.course_code.strip(),
                "course_goal": body.course_goal.strip(),
                "default_location": body.default_location.strip(),
                "target_grade": body.target_grade.strip(),
                "course_category": body.course_category.strip(),
                "target_major": body.target_major.strip(),
                "credits": body.credits,
                "total_hours": body.total_hours,
                "assessment_method": body.assessment_method.strip(),
                "course_intro": body.course_intro.strip(),
                "teaching_goals": body.teaching_goals.strip(),
            },
            "generation_request": generation_request,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
    )
    try:
        package = await run_in_threadpool(
            teacher_course_space_repository.create_package,
            owner_id,
            course_name,
            academic_year,
            term,
            "blank",
            course_id,
        )
    except BaseException:
        storage.delete_course(course_id)
        raise
    if generation_request.get("material_bindings"):
        bound_package = teacher_course_space_repository.load_owned(
            package["package_id"], owner_id
        )
        for binding in generation_request["material_bindings"]:
            asset = material_repository.get_asset(str(binding.get("asset_id") or ""))
            if not asset:
                continue
            try:
                teacher_course_space_repository.register_material_reference(
                    owner_id,
                    asset,
                    package=bound_package,
                )
            except Exception:
                # The uploaded material remains available through material_storage;
                # a missing file-space reference must not destroy the new course shell.
                continue
    return {
        "course_id": course_id,
        "course_name": course_name,
        "package_id": package["package_id"],
        "academic_year": academic_year,
        "term": term,
        "status": "draft",
    }


@router.get("/courses/{course_id}")
async def get_course(course_id: str, request: Request):
    course = await get_course_or_404(course_id)
    _require_unpublished_teacher_course_access(course, request)
    return project_learning_objective_bindings(course)


@router.get("/courses/{course_id}/document")
async def get_course_document(course_id: str, request: Request):
    course = project_learning_objective_bindings(await get_course_or_404(course_id))
    _require_unpublished_teacher_course_access(course, request)
    repository = get_course_document_repository()
    return await run_in_threadpool(
        lambda: repository.document_envelope(
            course_id,
            prepared_legacy_course=course,
        )
    )


@router.post("/courses/{course_id}/document/migrate")
async def migrate_course_document(course_id: str, body: CourseDocumentMigrationRequest):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Explicit migration confirmation is required")
    repository = get_course_document_repository()
    try:
        return await repository.migrate_legacy_course(
            course_id,
            expected_source_checksum=body.source_checksum,
        )
    except CourseMigrationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/courses/{course_id}")
async def delete_course(
    course_id: str,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
):
    course = await get_course_or_404(course_id)
    _require_teacher_course_write_access(course, request)
    owner_id = str(course.get("owner_id") or "").strip()
    removed_tasks = await tm.delete_course(course_id)
    calendar_removed = False
    if owner_id:
        calendar_removed = await run_in_threadpool(
            teaching_calendar_repository.delete,
            owner_id,
            course_id,
        )
    return {
        "status": "success",
        "removed_tasks": removed_tasks,
        "calendar_removed": calendar_removed,
    }


@router.post("/course-generation/generate", status_code=202)
async def create_course_generation_job(
    req: CourseGenerationRequest,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
):
    """Create the sole persisted generation job and return immediately."""
    actor_id = (
        require_actor_id(request.headers.get("X-User-Id"))
        if req.target_course_id
        else resolve_user_id(request.headers.get("X-User-Id"))
    )
    if req.target_course_id:
        draft = storage.load_course(req.target_course_id)
        if not draft or draft.get("owner_id") != actor_id:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "teacher_course_draft_unavailable",
                    "message": "课程草稿不存在或不属于当前教师",
                },
            )
        if (
            draft.get("course_status") != "draft"
            or draft.get("authoring_surface") != "teacher"
            or draft.get("generation_job_id")
        ):
            raise HTTPException(status_code=409, detail="课程大纲已存在或正在生成")
    request_snapshot = req.model_dump(mode="json")
    request_snapshot["_retrieval_actor_id"] = actor_id
    return await tm.create_generation_job(request_snapshot)


@router.post("/courses/{course_id}/locate")
async def locate_node(course_id: str, req: LocateNodeRequest):
    tree_data = await get_course_or_404(course_id)
    if "nodes" not in tree_data:
        return {}
    return get_course_service().locate_node(req.keyword, tree_data["nodes"])


# =============================================================================
# Node-level operations (HTTP fallback for WebSocket commands)
# Requirements: 7.1, 7.2, 7.3, 7.4
# =============================================================================


@router.post("/courses/{course_id}/nodes/{node_id}/skip")
async def skip_node(
    course_id: str,
    node_id: str,
    tm: TaskManager = Depends(require_task_manager),
):
    """Skip a node during generation."""
    task_id = tm._find_active_task(course_id)
    if not task_id:
        raise HTTPException(status_code=404, detail="No active task for this course")
    await tm.skip_node(task_id, node_id)
    return {"status": "skipped"}


@router.post("/courses/{course_id}/nodes/{node_id}/render-diagnostics")
async def report_node_render_diagnostics(
    course_id: str,
    node_id: str,
    req: RenderDiagnosticsRequest,
    tm: TaskManager = Depends(require_task_manager),
):
    """Accept the browser's real-render verdict for one node.

    Idempotent by design: re-reporting overwrites, so a fixed node clears its
    render issues instead of accumulating stale ones.
    """
    task_id = tm._find_active_task(course_id)
    if not task_id:
        raise HTTPException(status_code=404, detail="No active task for this course")
    stored = await tm.record_node_render_diagnostics(
        task_id,
        node_id,
        req.model_dump(),
    )
    return {"status": "recorded", "render_diagnostics": stored}


@router.post("/courses/{course_id}/nodes/{node_id}/retry")
async def retry_node(
    course_id: str,
    node_id: str,
    tm: TaskManager = Depends(require_task_manager),
):
    """Retry a failed or completed node."""
    task_id = tm._find_active_task(course_id)
    if not task_id:
        raise HTTPException(status_code=404, detail="No active task for this course")
    await tm.retry_node(task_id, node_id)
    return {"status": "retry_scheduled"}


@router.post("/courses/{course_id}/nodes/{node_id}/stop")
async def stop_node(
    course_id: str,
    node_id: str,
    tm: TaskManager = Depends(require_task_manager),
):
    """Stop generating a node, keeping already-generated content."""
    task_id = tm._find_active_task(course_id)
    if not task_id:
        raise HTTPException(status_code=404, detail="No active task for this course")
    await tm.stop_node(task_id, node_id)
    return {"status": "stopped"}


@router.post("/courses/{course_id}/nodes/{node_id}/instruction")
async def set_custom_instruction(
    course_id: str,
    node_id: str,
    body: CustomInstructionRequest,
    tm: TaskManager = Depends(require_task_manager),
):
    """Set a custom generation instruction for a node."""
    task_id = tm._find_active_task(course_id)
    if not task_id:
        raise HTTPException(status_code=404, detail="No active task for this course")
    await tm._set_custom_instruction(task_id, node_id, body.instruction)
    return {"status": "instruction_set"}


@router.post("/courses/{course_id}/retry_all_failed")
async def retry_all_failed(
    course_id: str,
    tm: TaskManager = Depends(require_task_manager),
):
    """Retry all failed nodes for a course."""
    task_id = tm._find_active_task(course_id)
    if not task_id:
        raise HTTPException(status_code=404, detail="No active task for this course")
    await tm.retry_all_failed(task_id)
    return {"status": "retry_all_scheduled"}


# =============================================================================
# Generation config
# Requirements: 14.4
# =============================================================================


@router.put("/courses/{course_id}/nodes/{node_id}/config")
async def update_node_config(
    course_id: str,
    node_id: str,
    body: NodeConfigUpdateRequest,
):
    """Update generation config for a specific node."""
    tree_data = await get_course_or_404(course_id)
    node = get_node_or_404(tree_data, node_id)

    config = node.get("generation_config") or {}
    update_data = body.model_dump(exclude_none=True)
    config.update(update_data)
    node["generation_config"] = config

    await save_course_compat(storage, course_id, tree_data)
    return {"status": "config_updated", "config": config}


@router.get("/courses/{course_id}/web-material-curation")
async def get_web_material_curation(
    course_id: str,
    repository=Depends(get_course_document_repository),
):
    """读回该课程已持久化的联网来源剔除名单。"""
    await get_course_or_404(course_id)
    raw = await run_in_threadpool(repository.load_raw, course_id)
    return load_course_exclusions(raw)


@router.put("/courses/{course_id}/web-material-curation")
async def update_web_material_curation(
    course_id: str,
    body: WebMaterialCurationRequest,
    repository=Depends(get_course_document_repository),
):
    """保存剔除名单；下一轮生成会自动带上，不必教师每次重勾。"""
    await get_course_or_404(course_id)
    exclusions = normalize_exclusions(body.model_dump())
    await repository.update_metadata(
        course_id,
        {CURATION_METADATA_KEY: exclusions},
    )
    return {"status": "curation_updated", **exclusions}


def _course_research_topic(course: dict) -> str:
    return str(
        course.get("course_name")
        or course.get("subject")
        or course.get("title")
        or "课程资料"
    ).strip()[:200]


def _requested_research_queries(
    course: dict,
    body: CourseWebResearchSearchRequest,
) -> list[str]:
    explicit: list[str] = []
    for value in body.queries:
        query = safe_query_term(value)
        if len(query) >= 2 and query not in explicit:
            explicit.append(query)
    if explicit:
        return explicit[:8]
    return derive_search_queries(
        topic=_course_research_topic(course),
        requirements=body.brief,
        objectives=[],
        max_queries=8,
    )


@router.get("/courses/{course_id}/web-research")
async def get_course_web_research(
    course_id: str,
    request: Request,
    stage: str = "foundation",
    lesson_id: str = "",
    repository=Depends(get_course_document_repository),
):
    """读取当前生产阶段的最近调研与已选网页来源。"""
    course = await get_course_or_404(course_id)
    # 调研词和未入选候选属于教师备课数据；即使课程已发布也不对学生开放。
    _require_teacher_course_write_access(course, request)
    raw = await run_in_threadpool(repository.load_raw, course_id)
    return scoped_research_projection(raw, stage=stage, lesson_id=lesson_id)


@router.post("/courses/{course_id}/web-research/search")
async def search_course_web_research(
    course_id: str,
    body: CourseWebResearchSearchRequest,
    request: Request,
    repository=Depends(get_course_document_repository),
):
    """通过统一检索网关执行老师可见、可复核的查询。"""
    course = await get_course_or_404(course_id)
    _require_teacher_course_write_access(course, request)
    queries = _requested_research_queries(course, body)
    if not queries:
        raise HTTPException(
            status_code=422,
            detail={"code": "web_research_no_queries", "message": "未能从调研要求中得到有效查询"},
        )

    actor_id = resolve_user_id(request.headers.get("X-User-Id"))
    gateway, feature = configured_retrieval_gateway(actor_id)
    package = await gateway.retrieve(RetrievalRequest(
        purpose="course",
        enabled=True,
        queries=queries,
        max_queries=8,
        # 网关先保留较宽候选池；课程层再按查询与域名做多样性重排，
        # 对外仍维持既有每会话 16 条上限。
        max_sources=24,
    ))
    diversified_sources = diversify_retrieval_sources(
        [source for source in package.get("sources") or [] if isinstance(source, dict)],
        limit=MAX_RESULTS_PER_SESSION,
    )
    shallow_results = [
        normalize_candidate(candidate_from_source(source))
        for source in diversified_sources
    ]
    # 正文深读是内部增强阶段，不改变 API。单页失败只回退搜索摘要，
    # 整个检索会话仍可供教师审阅和选源。
    results = [
        normalize_candidate(candidate)
        for candidate in await enrich_web_candidates(shallow_results)
    ]
    research_summary = build_research_summary(
        queries=[str(item) for item in package.get("queries") or queries],
        candidates=results,
    )
    normalized_stage, normalized_lesson_id = normalize_scope(body.stage, body.lesson_id)
    session = {
        "session_id": f"wrs-{uuid.uuid4().hex}",
        "stage": normalized_stage,
        "lesson_id": normalized_lesson_id,
        "brief": body.brief.strip(),
        "queries": [str(item) for item in package.get("queries") or queries],
        "status": str(package.get("status") or "failed_fallback_local"),
        "provider": str(package.get("provider") or feature.get("provider") or ""),
        "provider_available": bool(feature.get("enabled_for_user", True)),
        "retrieved_at": str(package.get("retrieved_at") or ""),
        "package_hash": str(package.get("package_hash") or ""),
        "receipt": package.get("receipt") or {},
        "errors": list(package.get("errors") or []),
        "rejected_count": len(package.get("rejected_sources") or []),
        "results": results,
        "research_summary": research_summary,
        "pipeline": {
            "schema_version": "web_research_pipeline_v1",
            "stage": "review",
            "steps": [
                {"name": "search", "status": "completed" if package.get("sources") else "degraded"},
                {
                    "name": "deep_read",
                    "status": "completed" if research_summary["full_text_count"] else "degraded",
                    "completed_count": research_summary["full_text_count"],
                },
                {"name": "restructure", "status": "completed"},
            ],
        },
        "selected_source_ids": [],
        "accepted_references": [],
    }
    # 检索可能耗时；回写前重读课程，避免把同期完成的其他调研盖掉。
    latest = await run_in_threadpool(repository.load_raw, course_id)
    state = upsert_research_session(latest, session)
    await repository.update_metadata(course_id, {WEB_RESEARCH_METADATA_KEY: state})
    return session


def _existing_web_references(course: dict) -> dict[str, dict]:
    references: dict[str, dict] = {}
    state = course.get(WEB_RESEARCH_METADATA_KEY)
    if not isinstance(state, dict):
        return references
    for session in state.get("sessions") or []:
        if not isinstance(session, dict):
            continue
        for item in session.get("accepted_references") or []:
            if not isinstance(item, dict):
                continue
            source_id = str((item.get("source_metadata") or {}).get("source_id") or "")
            if source_id:
                references[source_id] = item
    return references


@router.put("/courses/{course_id}/web-research/{session_id}")
async def select_course_web_research_sources(
    course_id: str,
    session_id: str,
    body: CourseWebResearchSelectionRequest,
    request: Request,
    repository=Depends(get_course_document_repository),
):
    """把已勾选网页转成课程资料资产，并登记到当前课程文件空间。"""
    course = await get_course_or_404(course_id)
    _require_teacher_course_write_access(course, request)
    raw = await run_in_threadpool(repository.load_raw, course_id)
    session = research_session(raw, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="联网调研会话不存在")

    selected_ids = list(dict.fromkeys(
        str(value or "").strip()
        for value in body.selected_source_ids
        if str(value or "").strip()
    ))
    candidates_by_id = {
        str(item.get("source_id") or ""): item
        for item in session.get("results") or []
        if isinstance(item, dict) and str(item.get("source_id") or "")
    }
    unknown = [value for value in selected_ids if value not in candidates_by_id]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail={"code": "web_research_source_unknown", "source_ids": unknown},
        )

    owner_id = require_actor_id(request.headers.get("X-User-Id"))
    packages = teacher_course_space_repository.list_owned(owner_id, course_id)
    if not packages:
        raise HTTPException(
            status_code=409,
            detail={"code": "course_space_missing", "message": "当前课程文件空间不存在"},
        )
    package = teacher_course_space_repository.load_owned(
        str(packages[0].get("package_id") or ""), owner_id
    )

    existing = _existing_web_references(raw)
    accepted_references: list[dict] = []
    new_candidates: list[dict] = []
    for source_id in selected_ids:
        if source_id in existing:
            accepted_references.append(existing[source_id])
        else:
            new_candidates.append(candidates_by_id[source_id])

    if new_candidates:
        try:
            prepared = await prepare_course_materials(
                course_id=course_id,
                material_bindings=[],
                legacy_materials=[],
                web_search_report={
                    "enabled": True,
                    "status": "ready",
                    "degraded": False,
                    "queries": list(session.get("queries") or []),
                    "candidates": new_candidates,
                    "rejected": [],
                    "message_code": "web_research_selected",
                },
            )
        except MaterialStorageError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        assets = {
            str(item.get("asset_id") or ""): item
            for item in prepared.get("material_assets") or []
        }
        candidates = {
            str(item.get("source_id") or ""): item for item in new_candidates
        }
        for binding in prepared.get("material_bindings") or []:
            metadata = binding.get("source_metadata") or {}
            source_id = str(metadata.get("source_id") or "")
            asset_id = str(binding.get("asset_id") or "")
            asset = material_repository.get_asset(asset_id)
            candidate = candidates.get(source_id)
            if not source_id or not asset or not candidate:
                continue
            course_reference = teacher_course_space_repository.register_material_reference(
                owner_id, asset, package=package
            )
            public_asset = assets.get(asset_id) or material_repository.public_asset(asset)
            accepted_references.append({
                "package_id": str(course_reference.get("package_id") or package["package_id"]),
                "asset_id": str(course_reference.get("asset_id") or ""),
                "material_asset_id": asset_id,
                "filename": str(course_reference.get("filename") or public_asset.get("filename") or ""),
                "relative_path": str(course_reference.get("relative_path") or ""),
                "size_bytes": int(public_asset.get("size_bytes") or 0),
                "uploaded_at": str(public_asset.get("uploaded_at") or ""),
                "role": "reference",
                "origin": "web_search",
                "source_label": str(candidate.get("title") or candidate.get("domain") or "联网资料")[:200],
                "reuse_policy": str(binding.get("reuse_policy") or "reference_only"),
                "rights_basis": str(binding.get("rights_basis") or "license_unknown"),
                "source_metadata": metadata,
            })

    reference_order = {source_id: index for index, source_id in enumerate(selected_ids)}
    accepted_references.sort(key=lambda item: reference_order.get(
        str((item.get("source_metadata") or {}).get("source_id") or ""), 10_000
    ))
    session["selected_source_ids"] = selected_ids
    session["accepted_references"] = accepted_references
    session["accepted_at"] = datetime.now(timezone.utc).isoformat()

    latest = await run_in_threadpool(repository.load_raw, course_id)
    state = upsert_research_session(latest, session)
    await repository.update_metadata(course_id, {WEB_RESEARCH_METADATA_KEY: state})
    return {
        "status": "sources_selected",
        **scoped_research_projection(
            {WEB_RESEARCH_METADATA_KEY: state},
            stage=session.get("stage"),
            lesson_id=session.get("lesson_id"),
        ),
    }


@router.post("/courses/{course_id}/course-space/publish")
async def publish_course_to_space(course_id: str, request: Request):
    """F-2 回填：把已有课程的产物补写进教师课程空间。

    生成完成时会自动入库；这个入口是给**存量课程**补一次的。与自动入库共用
    同一套幂等规则（同路径同内容跳过、老师手动上传不覆盖），所以重复调用安全。
    """
    course_data = await get_course_or_404(course_id)
    # 与教师课程空间自身的写入口径一致（那边用 require_user_id）：缺身份或用了
    # 共享的 default_user 都不能建包——否则产物会落进一个所有人共用的空间，
    # 而且老师只会看到"没入库"，分不清是系统坏了还是身份没带上。
    owner_id = str(request.headers.get("X-User-Id") or "").strip()
    if not owner_id or owner_id == DEFAULT_USER_ID:
        return {
            "status": "skipped",
            "course_id": course_id,
            "package_id": "",
            "written": [],
            "unchanged": [],
            "conflicts": [],
            "failures": [],
            "reason": MISSING_TEACHER_IDENTITY,
            "message": SKIP_MESSAGES[MISSING_TEACHER_IDENTITY],
        }
    report = await run_in_threadpool(
        publish_course_artifacts,
        course_data,
        owner_id=owner_id,
    )
    return {
        "status": report.get("status"),
        "course_id": course_id,
        "package_id": report.get("package_id"),
        "written": report.get("written") or [],
        "unchanged": report.get("unchanged") or [],
        "conflicts": report.get("conflicts") or [],
        "failures": report.get("failures") or [],
        "reason": report.get("reason"),
        # 跳过时必须说清是哪一种原因（缺教师身份 / 缺 course_id / 没有产物），
        # 笼统的"入库失败"会把可自助修复的问题变成一张工单。
        "message": report.get("message") or "",
    }
