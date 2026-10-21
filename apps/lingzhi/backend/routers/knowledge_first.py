"""Course-owned knowledge endpoints; auth applies to learners' own courses too."""
import asyncio
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
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
    pipeline: Literal['', 'inventory_atomic_v1', 'knowledge_relations_v1'] = ''
    resume_job_id: str = Field(default='', max_length=200)
    retry_batch_id: str = Field(default='', max_length=100)
    organize_hierarchy: bool = True
    extraction_mode: Literal['', 'single_pass_v1'] = 'single_pass_v1'
    include_relations: bool = True
    teaching_focus: list[str] | None = Field(default=None,max_length=8)
    coverage_units: list[dict] | None = Field(default=None,max_length=120)


class AdoptRequest(SourceRequest):
    confirm_identity_changes: bool = False
    confirm_atomic_review: bool = False
    confirm_relations: bool = False
    selected_relation_ids: list[str] | None = Field(default=None,max_length=800)


class DisplayLabel(BaseModel):
    model_config = {'extra': 'forbid'}
    knowledge_id: str = Field(min_length=1, max_length=200)
    knowledge_revision: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)


class PresentationRequest(SourceRequest):
    model_config = {'extra': 'forbid'}
    command_id: str = Field(min_length=1, max_length=100)
    presentation_revision: str = Field(default='', max_length=200)
    tree_revision: str = Field(min_length=1, max_length=200)
    labels: list[DisplayLabel] = Field(min_length=1, max_length=240)


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
        view.update(jobs=[], active_jobs=[], atomic_runs=[], generation_previews=[], relation_runs=[], blocking_job_ids=[], candidate=None, candidate_job_id="", candidates=[], lesson_options=[], inputs={}, source_handouts=[], handouts=[], can_generate_tree=False)
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


@router.post('/courses/{course_id}/knowledge-first/presentation')
def presentation(course_id: str, body: PresentationRequest, request: Request, svc=Depends(service)):
    return action(lambda: svc.update_presentation(course_id,
        actor=require_actor_id(request.headers.get('X-User-Id')), command_id=body.command_id,
        expected_document=body.document_revision, expected_knowledge=body.knowledge_revision,
        expected_presentation=body.presentation_revision, tree_revision=body.tree_revision,
        labels=[row.model_dump() for row in body.labels]))


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


@router.get('/courses/{course_id}/knowledge-first/events/{job_id}')
async def events(course_id: str, job_id: str, request: Request, svc=Depends(service)):
    """Observe the existing durable job; disconnect never cancels generation."""
    actor = require_actor_id(request.headers.get('X-User-Id'))
    if svc is None or request.state.knowledge_first_course.get('owner_id') != actor:
        raise HTTPException(404, '任务不存在或无权限')
    from knowledge_atomic import project_preview
    from knowledge_generation_status import job_status
    from knowledge_first import now

    def snapshot():
        if svc.repository.load_raw(course_id).get('owner_id') != actor:
            raise HTTPException(404, '任务不存在或无权限')
        def project(state):
            job = state.get('jobs', {}).get(job_id) or {}
            if job.get('type') not in JOB_TYPES:
                raise HTTPException(404, '任务不存在或无权限')
            pipeline = (job.get('checkpoint') or {}).get('atomic_pipeline') or {}
            revision = pipeline.get('revision', 0)
            return {'job': job_status(job, now()), 'preview_revision': revision,
                    'preview': project_preview(job, course_id)}
        return svc.authoring.read_projection(course_id, project)

    initial = await run_in_threadpool(snapshot)
    async def stream():
        value, last_revision = initial, None
        while True:
            if await request.is_disconnected(): return
            payload = {**value, 'job_id': job_id}
            if value['preview_revision'] == last_revision: payload.pop('preview', None)
            yield 'event: snapshot\ndata: ' + json.dumps(payload, ensure_ascii=False) + '\n\n'
            last_revision = value['preview_revision']
            if value['job']['status'] not in {'pending', 'running'}:
                yield 'event: complete\ndata: ' + json.dumps({'job_id': job_id}) + '\n\n'
                return
            await asyncio.sleep(1)
            try: value = await run_in_threadpool(snapshot)
            except HTTPException: return
    return StreamingResponse(stream(), media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@router.get("/courses/{course_id}/knowledge-first/source")
def source(course_id: str, request: Request, tree_revision: str = Query(min_length=1, max_length=200),
           knowledge_id: str = Query(min_length=1, max_length=200), evidence_id: str = Query(min_length=1, max_length=200),
           svc=Depends(service)):
    from knowledge_evidence import KnowledgeSourceNotFound
    if svc is None or request.state.knowledge_first_course.get('owner_id') != require_actor_id(request.headers.get('X-User-Id')):
        raise HTTPException(404, '来源不存在或无权限')
    try:
        return svc.source(course_id, tree_revision, knowledge_id, evidence_id, raw=request.state.knowledge_first_course)
    except KnowledgeSourceNotFound:
        raise HTTPException(404, '来源不存在或无权限') from None


@router.post("/courses/{course_id}/knowledge-first/generate/{topic}", status_code=202)
async def generate(course_id: str, topic: str, body: GenerateRequest, svc=Depends(service)):
    job, created = action(lambda: svc.start(course_id, topic, body.request_id, body.knowledge_revision, body.document_revision,
        source_mode=body.source_mode, lesson_id=body.lesson_id, pipeline=body.pipeline,
        resume_job_id=body.resume_job_id, retry_batch_id=body.retry_batch_id, organize_hierarchy=body.organize_hierarchy,
        extraction_mode=body.extraction_mode, include_relations=body.include_relations,teaching_focus=body.teaching_focus,coverage_units=body.coverage_units))
    if created:
        task = asyncio.create_task(svc.run(course_id, job["id"]), name=job["id"])
        svc.authoring.track_runtime_job(course_id, task)
    return {"job_id": job["id"], "created": created}


@router.post("/courses/{course_id}/knowledge-first/adopt/{job_id}")
def adopt(course_id: str, job_id: str, body: AdoptRequest, svc=Depends(service)):
    action(lambda: svc.adopt(course_id, job_id, body.knowledge_revision, body.document_revision,
        confirm_identity_changes=body.confirm_identity_changes, confirm_atomic_review=body.confirm_atomic_review,
        confirm_relations=body.confirm_relations, selected_relation_ids=body.selected_relation_ids))
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
