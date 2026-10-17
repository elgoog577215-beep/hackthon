"""Course-owned knowledge endpoints; auth applies to learners' own courses too."""
import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from course_repository import CourseDocumentConflict, CourseDocumentNotFound
from dependencies import get_course_document_repository, get_teacher_lesson_authoring_repository
from knowledge_first import KnowledgeFirstService, JOB_TYPES
from learner_context import require_actor_id

router = APIRouter(tags=["knowledge_first"])


class SourceRequest(BaseModel):
    document_revision: str = Field(max_length=200)
    knowledge_revision: str = Field(default="", max_length=200)


class GenerateRequest(SourceRequest):
    lesson_id: str = Field(default="", max_length=200)
    source_mode: Literal["", "handouts"] = ""
    request_id: str = Field(min_length=1, max_length=100)


class InputRequest(SourceRequest):
    input_revision: str = Field(default="", max_length=200)
    requirements: str = Field(min_length=1, max_length=5000)
    target_audience: str = Field(default="", max_length=500)
    lesson_count: int = Field(default=3, ge=1, le=12)
    material_asset_ids: list[str] = Field(default_factory=list, max_length=30)

    @field_validator('material_asset_ids')
    @classmethod
    def valid_material_ids(cls, value):
        import re
        if len(value) != len(set(value)) or any(not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', v) for v in value):
            raise ValueError('资料ID无效或重复')
        return value


def service(course_id: str, request: Request,
            repo=Depends(get_course_document_repository), authoring=Depends(get_teacher_lesson_authoring_repository)):
    from course_exchange import remote_course_context
    remote = remote_course_context.get()
    if remote and remote["course_id"] == course_id and request.method == "GET":
        return None
    try:
        course = repo.load_raw(course_id)
    except CourseDocumentNotFound:
        raise HTTPException(404, "课程不存在")
    actor = require_actor_id(request.headers.get("X-User-Id"))
    owner = course.get("owner_id")
    from course_learning_access import CourseLearningAccess, trusted_student
    granted_read = (request.method == "GET" and trusted_student(request)
                    and bool(CourseLearningAccess(repo.storage).active(course, actor)))
    if owner != actor and not granted_read and not (request.method == "GET" and (course.get("is_published") or course.get("course_document_publication"))):
        raise HTTPException(404, "课程不存在或无权限")
    request.state.knowledge_first_course = course
    return KnowledgeFirstService(repo, authoring)


def action(fn):
    try:
        return fn()
    except CourseDocumentConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/courses/{course_id}/knowledge-first")
def read(course_id: str, request: Request, source_mode: Literal["", "handouts"] = "", svc=Depends(service)):
    if svc is None:
        from course_exchange import remote_course_context
        tree = remote_course_context.get().get("course_knowledge_base") or {}
        return {"course_id":course_id, "tree":tree, "can_edit":False, "history":[], "jobs":[],
                "candidate":None, "candidates":[], "inputs":{}, "handouts":[], "source_handouts":[], "can_generate_tree":False}
    view = svc.view(course_id, source_mode=source_mode)
    view["can_edit"] = svc.repository.load_raw(course_id).get("owner_id") == require_actor_id(request.headers.get("X-User-Id"))
    if not view["can_edit"]:
        view.update(jobs=[], active_jobs=[], blocking_job_ids=[], candidate=None, candidate_job_id="", candidates=[], lesson_options=[], inputs={}, source_handouts=[], handouts=[], can_generate_tree=False)
        # Historical candidates/source packages remain teacher data.
        view["history"] = []
        tree = view.get("tree") or {}
        if tree.get("source_mode") == "handouts":
            from course_learning_projection import public_document
            from handout_knowledge import visible_handout_tree
            raw = svc.repository.load_course_view(course_id)
            view["tree"] = visible_handout_tree(tree, public_document(raw), raw.get("teacher_handouts") or {})
    return view


@router.post("/courses/{course_id}/knowledge-first/initialize")
def initialize(course_id: str, body: SourceRequest, svc=Depends(service)):
    action(lambda: svc.initialize(course_id, body.document_revision))
    return {"initialized": True}


@router.get("/courses/{course_id}/knowledge-first/status")
def status(course_id: str, request: Request, source_mode: Literal["", "handouts"] = "", svc=Depends(service)):
    """Owner-only task metadata; published readers never see authoring activity."""
    if svc is None:
        return {"course_id": course_id, "can_edit": False, "jobs": [], "active_jobs": []}
    raw = request.state.knowledge_first_course
    if raw.get("owner_id") != require_actor_id(request.headers.get("X-User-Id")):
        return {"course_id": course_id, "can_edit": False, "jobs": [], "active_jobs": []}
    return {**svc.status(course_id, source_mode=source_mode, raw=raw), "can_edit": True}


@router.post("/courses/{course_id}/knowledge-first/inputs")
def configure(course_id: str, body: InputRequest, svc=Depends(service)):
    action(lambda: svc.configure(course_id, body.document_revision, body.knowledge_revision,
        body.model_dump(exclude={"document_revision", "knowledge_revision", "input_revision"}), body.input_revision))
    return {"saved": True}


@router.post("/courses/{course_id}/knowledge-first/generate/{topic}", status_code=202)
async def generate(course_id: str, topic: str, body: GenerateRequest, svc=Depends(service)):
    job, created = action(lambda: svc.start(course_id, topic, body.request_id, body.knowledge_revision, body.document_revision, source_mode=body.source_mode, lesson_id=body.lesson_id))
    if created:
        task = asyncio.create_task(svc.run(course_id, job["id"]), name=job["id"])
        svc.authoring.track_runtime_job(course_id, task)
    return {"job_id": job["id"], "created": created}


@router.post("/courses/{course_id}/knowledge-first/adopt/{job_id}")
def adopt(course_id: str, job_id: str, body: SourceRequest, svc=Depends(service)):
    action(lambda: svc.adopt(course_id, job_id, body.knowledge_revision, body.document_revision))
    return {"adopted": True}


@router.post("/courses/{course_id}/knowledge-first/recheck/{job_id}")
def recheck(course_id: str, job_id: str, body: GenerateRequest, svc=Depends(service)):
    result = action(lambda: svc.recheck(course_id, job_id, body.request_id, body.document_revision, body.knowledge_revision))
    return {"job_id": result["id"]}


@router.post("/courses/{course_id}/knowledge-first/cancel/{job_id}")
def cancel(course_id: str, job_id: str, svc=Depends(service)):
    job = svc.authoring.load(course_id)["jobs"].get(job_id) or {}
    if job.get("type") not in JOB_TYPES:
        raise HTTPException(404, "任务不存在")
    svc.authoring.cancel_job(course_id, job_id)
    return {"cancelled": True}
