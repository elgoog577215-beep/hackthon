"""Teacher PPT workspace: select sources, review pages, render."""
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from dependencies import get_teacher_lesson_authoring_repository
from material_storage import MaterialStorageError, material_repository
from ppt_projects import PptProjectService
from routers.teacher_preview import owned_course
from slide_deck_v6_renderer import export_slide_deck_v6_pptx
from storage import storage
from teacher_lesson_authoring import TeacherLessonAuthoringError

router = APIRouter(prefix="/teacher/courses/{course_id}/ppt-projects", tags=["ppt-projects"])


def service(repository=Depends(get_teacher_lesson_authoring_repository)):
    return PptProjectService(storage, repository)


def call(action):
    try:
        return action()
    except TeacherLessonAuthoringError as exc:
        raise HTTPException(409, detail={"code":exc.code, "message":str(exc)}) from exc


@router.get("")
def list_projects(course_id: str, request: Request, svc=Depends(service)):
    raw = owned_course(course_id, request)
    doc = raw["course_document"]
    return {"document_revision":raw["course_document_revision"], "course_name":raw.get("course_name", ""),
        "lectures":[{"lesson_id":s["section_id"], "title":s["title"],
            "ready":any(b.get("status") == "final" and (b["section_id"] == s["section_id"] or b["section_id"] in {c["section_id"] for c in doc["sections"] if c.get("parent_section_id")==s["section_id"]}) for b in doc["blocks"])}
            for s in doc["sections"] if s["level"]==1],
        "uploads":list((raw.get("teacher_ppt_uploads") or {}).values()),
        "projects":[{"project_id":p["project_id"], "title":p["title"], "status":p["status"]} for p in (raw.get("teacher_ppt_projects") or {}).values()]}


@router.post("/uploads", status_code=201)
async def upload(course_id: str, request: Request, file: UploadFile = File(...)):
    owned_course(course_id, request)
    actor = str(request.headers.get("X-User-Id") or "").strip()
    try:
        asset = await material_repository.save_upload(file)
    except MaterialStorageError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    entry = {"asset_id":asset.asset_id, "sha256":asset.sha256, "filename":asset.filename, "size_bytes":asset.size_bytes}
    def register(raw):
        if not raw or str(raw.get("owner_id") or "") != actor:
            raise HTTPException(404, detail="课程不存在或不属于当前教师")
        raw.setdefault("teacher_ppt_uploads", {})[asset.asset_id] = entry
        return raw
    storage.update_course_data(course_id, register)
    return entry


class CreateProject(BaseModel):
    lesson_ids: list[str] = Field(default_factory=list, max_length=60)
    asset_ids: list[str] = Field(default_factory=list, max_length=30)
    title: str = Field(default="", max_length=200)
    expected_revision: str


class ProjectRevision(BaseModel):
    expected_revision: str


class EditProject(ProjectRevision):
    page_updates: list[dict[str, Any]] = Field(max_length=500)
    pacing: dict[str, Any] | None = None


@router.post("", status_code=201)
def create(course_id: str, body: CreateProject, request: Request, svc=Depends(service)):
    owned_course(course_id, request)
    return call(lambda:svc.create(course_id, body.lesson_ids, body.asset_ids, title=body.title, expected_revision=body.expected_revision))


@router.get("/{project_id}")
def read(course_id: str, project_id: str, request: Request, svc=Depends(service)):
    owned_course(course_id, request)
    return call(lambda:svc.view(course_id, project_id))


@router.post("/{project_id}/prepare", status_code=202)
async def prepare(course_id: str, project_id: str, body: ProjectRevision, request: Request, svc=Depends(service)):
    owned_course(course_id, request)
    return call(lambda:svc.start(course_id, project_id, body.expected_revision))


@router.patch("/{project_id}/manuscript")
def edit(course_id: str, project_id: str, body: EditProject, request: Request, svc=Depends(service)):
    owned_course(course_id, request)
    return call(lambda:svc.edit(course_id, project_id, body.expected_revision, body.page_updates, body.pacing))


@router.post("/{project_id}/confirm")
def confirm(course_id: str, project_id: str, body: ProjectRevision, request: Request, svc=Depends(service)):
    owned_course(course_id, request)
    return call(lambda:svc.confirm(course_id, project_id, body.expected_revision))


@router.post("/{project_id}/render", status_code=202)
async def render(course_id: str, project_id: str, body: ProjectRevision, request: Request, svc=Depends(service)):
    owned_course(course_id, request)
    return call(lambda:svc.start(course_id, project_id, body.expected_revision, render=True))


@router.post("/{project_id}/pause")
def pause(course_id: str, project_id: str, request: Request, svc=Depends(service)):
    owned_course(course_id, request)
    with svc.jobs._course_lock(course_id):
        project = call(lambda:svc.load(course_id, project_id))
        if project.get("job_id") and project.get("status") in {"building", "rendering"}:
            svc.jobs.update_job(course_id, project["job_id"], status="paused", phase="paused")
            return call(lambda:svc.update(course_id, project_id, {"status":"paused"}, expected=project["revision"]))
        return project


@router.get("/{project_id}/export")
async def export(course_id: str, project_id: str, request: Request, svc=Depends(service)):
    owned_course(course_id, request)
    project = call(lambda:svc.load(course_id, project_id))
    rendered = project.get("last_good_render")
    if not rendered:
        raise HTTPException(409, detail="请先生成 PPT 成品。")
    # Always export the retained render with its own confirmed manuscript,
    # including when a newer handout or draft has made it stale.
    content = {**rendered["deck"], "ppt_manuscript":rendered["ppt_manuscript"]}
    path = svc.jobs.root / "ppt_project_exports" / f"{project_id}-{rendered['task_id']}.pptx"
    path.parent.mkdir(parents=True, exist_ok=True)
    import asyncio
    def export_once():
        if path.exists():
            return
        import os
        import tempfile
        with tempfile.TemporaryDirectory(prefix=".ppt-export-", dir=path.parent) as temporary:
            ready = Path(temporary) / "deck.pptx"
            export_slide_deck_v6_pptx(content, ready)
            os.replace(ready, path)
    await asyncio.to_thread(export_once)
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation", filename=f"{project['title']}.pptx")
