from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from dependencies import require_task_manager
from material_parser import parse_material_asset
from material_storage import MaterialStorageError
from storage import storage
from study.auth import GUEST_COOKIE, GUEST_SESSION_SECONDS, LocalStudyAuth, study_identity
from study.repository import StudyConflict, StudyRepository
from study.service import create_material, source_sections

router = APIRouter(prefix="/study", tags=["personal-study"])


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=8, max_length=128)


class TextSource(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=120000)


class Selection(BaseModel):
    asset_id: str = Field(pattern=r"^mat-[a-f0-9]{32}$")
    section_id: str = Field(min_length=1, max_length=160)


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{16,64}$")
    title: str = Field(min_length=1, max_length=160)
    purpose: Literal["systematic", "exam_prep"]
    selections: list[Selection] = Field(min_length=1, max_length=6)
    level: Literal["beginner", "intermediate", "advanced"] = "beginner"
    time_minutes: int = Field(default=60, ge=10, le=600)
    requirements: str = Field(default="", max_length=2000)
    language: Literal["zh", "en"] = "zh"


class NoteRequest(BaseModel):
    revision_id: str = Field(min_length=1, max_length=80)
    content: str = Field(max_length=20000)


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{16,64}$")
    revision_id: str = Field(min_length=1, max_length=80)
    section_id: str = Field(min_length=1, max_length=160)
    block_id: str = Field(default="", max_length=160)
    quote: str = Field(default="", max_length=3000)
    text: str = Field(min_length=1, max_length=6000)
    language: Literal["zh", "en"] = "zh"


def repository() -> StudyRepository:
    return StudyRepository(storage)


def material_summary(material: dict) -> dict:
    """Project recorded course relationships without exposing private source text.

    The relationship only groups owned materials in the UI. It grants no access;
    reading the material continues to use StudyRepository.get and origin checks.
    """
    result = {key: material[key] for key in ("id", "title", "purpose", "status", "task_id", "updated_at")}
    result["source_course_ids"] = sorted({
        origin["course_id"]
        for section in material.get("request", {}).get("source_sections", [])
        if isinstance(section, dict)
        and isinstance(origin := section.get("course_origin"), dict)
        and isinstance(origin.get("course_id"), str) and origin["course_id"]
    })
    return result


def public_material(material: dict) -> dict:
    # The private raw source snapshots remain server-side; source identity and
    # selected ranges are sufficient for the reading/source panel.
    result = {key: value for key, value in material.items() if key not in {"request", "fingerprint", "request_key", "planning_response"}}
    result["sources"] = [{key: section[key] for key in ("node_id", "title", "filename", "asset_id", "source_sha256", "characters")}
                         for section in material["request"]["source_sections"]]
    result["source_course_ids"] = material_summary(material)["source_course_ids"]
    return result


def material_or_404(repo, owner, material_id):
    try:
        return repo.get(owner, material_id)
    except KeyError:
        raise HTTPException(404, "学习材料不存在")


def source_view(asset, document=None):
    return {"id": asset.asset_id, "filename": asset.filename, "status": asset.status,
            "sha256": asset.sha256, "warnings": asset.warnings, "error": asset.error,
            "sections": [{key: section[key] for key in ("id", "title", "characters")}
                         for section in source_sections(asset, document)] if document else []}


@router.get("/auth/config")
def auth_config(request: Request):
    auth = LocalStudyAuth(storage)
    from study.development import development_identity
    import os
    unified = bool(os.getenv("QIZHI_AUTH_VERIFY_URL", "").strip())
    return {"local_login_enabled": auth.enabled and not unified,
            "guest_login_enabled": auth.guest_enabled and not unified,
            "development_identity": development_identity(request) is not None,
            "identity_provider": "qizhi" if unified else "local"}


@router.post("/auth/guest")
def guest_login(request: Request, response: Response):
    result = LocalStudyAuth(storage).guest(request.cookies.get(GUEST_COOKIE, ""))
    response.set_cookie(GUEST_COOKIE, result["token"], max_age=GUEST_SESSION_SECONDS,
                        httponly=True, samesite="lax", secure=request.url.scheme == "https")
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post("/auth/register")
def register(request: Credentials):
    return LocalStudyAuth(storage).login(request.username, request.password, register=True)


@router.post("/auth/login")
def login(request: Credentials):
    return LocalStudyAuth(storage).login(request.username, request.password)


@router.get("/auth/me")
def me(user=Depends(study_identity)):
    return user


@router.post("/auth/logout")
def logout(request: Request, response: Response, user=Depends(study_identity)):
    from study.development import development_identity
    if not getattr(request.state, "qizhi_identity", None) and not development_identity(request):
        LocalStudyAuth(storage).logout(request.headers.get("Authorization", ""))
        response.delete_cookie(GUEST_COOKIE)
    return {"status": "logged_out"}


@router.get("/sources")
def sources(user=Depends(study_identity), repo=Depends(repository)):
    result, source_repo = [], repo.sources(user["id"])
    for manifest in source_repo.root.glob("mat-*/manifest.json"):
        asset = source_repo.get_asset(manifest.parent.name)
        if asset:
            try:
                repo.require_origin_access(user["id"], repo.source_origin(user["id"], asset.asset_id))
            except KeyError:
                continue
            result.append(source_view(asset, source_repo.load_parsed_document(asset.asset_id)))
    return result


async def parse_source(source_repo, asset):
    document = await parse_material_asset(source_repo, asset)
    return source_view(source_repo.get_asset(asset.asset_id), document)


@router.post("/sources/text")
async def text_source(request: TextSource, user=Depends(study_identity), repo=Depends(repository)):
    source_repo = repo.sources(user["id"])
    asset = await source_repo.create_text_asset(filename=request.title, content=request.content, upload_batch_id="study")
    return await parse_source(source_repo, asset)


@router.post("/sources/upload")
async def upload_source(file: UploadFile = File(...), user=Depends(study_identity), repo=Depends(repository)):
    source_repo = repo.sources(user["id"])
    try:
        asset = await source_repo.save_upload(file, upload_batch_id="study", max_bytes=20 * 1024 * 1024,
                                             max_batch_files=100, max_batch_bytes=300 * 1024 * 1024)
        return await parse_source(source_repo, asset)
    except MaterialStorageError as exc:
        raise HTTPException(422, str(exc))


@router.get("/sources/{asset_id}/download")
def download_source(asset_id: str, user=Depends(study_identity), repo=Depends(repository)):
    try:
        repo.require_origin_access(user["id"], repo.source_origin(user["id"], asset_id))
    except KeyError:
        raise HTTPException(404, "资料不存在或来源授权已撤销") from None
    source_repo = repo.sources(user["id"])
    try:
        asset = source_repo.get_asset(asset_id)
    except MaterialStorageError:
        asset = None
    if not asset or not source_repo.source_path(asset).is_file():
        raise HTTPException(404, "资料不存在")
    return FileResponse(source_repo.source_path(asset), filename=asset.filename, media_type=asset.mime_type)


@router.get("/materials")
def materials(user=Depends(study_identity), repo=Depends(repository)):
    return [material_summary(material) for material in repo.list(user["id"])]


@router.post("/materials")
async def generate(request: GenerationRequest, user=Depends(study_identity),
                   repo=Depends(repository), manager=Depends(require_task_manager)):
    try:
        return public_material(await create_material(manager, repo, user["id"], request.model_dump()))
    except StudyConflict as exc:
        raise HTTPException(409, str(exc))
    except (ValueError, MaterialStorageError) as exc:
        raise HTTPException(422, str(exc))


@router.get("/materials/{material_id}")
def material(material_id: str, user=Depends(study_identity), repo=Depends(repository),
             manager=Depends(require_task_manager)):
    result = public_material(material_or_404(repo, user["id"], material_id))
    task = manager.tasks.get(result["task_id"])
    # Never return global task snapshots or server/provider details to this UI.
    result["task"] = {key: task.get(key) for key in ("id", "status", "progress", "completed_nodes", "total_nodes", "phase", "message", "error_code")} if task else None
    return result


@router.post("/materials/{material_id}/continue")
async def continue_material(material_id: str, user=Depends(study_identity), repo=Depends(repository),
                            manager=Depends(require_task_manager)):
    saved = material_or_404(repo, user["id"], material_id)
    task = manager.tasks.get(saved["task_id"])
    if not task or task.get("owner_id") != user["id"] or task.get("type") != "personal_handout_generation":
        raise HTTPException(409, "生成任务已不可用；讲义和资料仍保留，请重新选择范围生成")
    await manager.resume_task(task["id"])
    return {"task_id": task["id"]}


@router.put("/materials/{material_id}/note")
def note(material_id: str, request: NoteRequest, user=Depends(study_identity), repo=Depends(repository)):
    material_or_404(repo, user["id"], material_id)
    try:
        saved = repo.save_note(user["id"], material_id, request.revision_id, request.content)
        return saved["notes"][request.revision_id]
    except StudyConflict as exc:
        raise HTTPException(409, str(exc))


@router.get("/materials/{material_id}/export")
def export(material_id: str, user=Depends(study_identity), repo=Depends(repository)):
    saved = material_or_404(repo, user["id"], material_id)
    lines = [f"# {saved['title']}", "\n" + ("应试讲义" if saved["purpose"] == "exam_prep" else "整体理解讲义")]
    if saved["status"] != "completed":
        lines.append("生成尚未完成，以下包含已保存内容与片段。")
    for section in saved["revisions"][-1]["sections"]:
        lines.extend([f"\n## {section['title']}" + ("（片段）" if not section["complete"] else ""),
                      f"来源：{section['source']['filename']} · SHA-256: {section['source']['source_sha256']}", section["content"]])
    return Response("\n\n".join(lines), media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="personal-handout.md"'})


@router.get("/materials/{material_id}/assistant")
def assistant_history(material_id: str, user=Depends(study_identity), repo=Depends(repository), manager=Depends(require_task_manager)):
    from study.assistant import ai_teacher_repository, public_conversation
    saved = material_or_404(repo, user['id'], material_id)
    conversation = ai_teacher_repository.material_conversation(user['id'], material_id, saved['revisions'][-1]['id'])
    return public_conversation(conversation, manager)


@router.post("/materials/{material_id}/assistant")
async def assistant_ask(material_id: str, request: AssistantRequest, user=Depends(study_identity), repo=Depends(repository), manager=Depends(require_task_manager)):
    from study.assistant import ask
    saved = material_or_404(repo, user['id'], material_id)
    try:
        return await ask(manager, repo, user['id'], saved, request.model_dump())
    except StudyConflict as exc:
        raise HTTPException(409, str(exc))


@router.post("/materials/{material_id}/assistant/{task_id}/continue")
async def assistant_continue(material_id: str, task_id: str, user=Depends(study_identity), repo=Depends(repository), manager=Depends(require_task_manager)):
    from study.assistant import resolve_context, ai_teacher_repository
    saved = material_or_404(repo, user['id'], material_id)
    task = manager.tasks.get(task_id)
    if not task or task.get('owner_id') != user['id'] or task.get('type') != 'personal_study_assistant' or task.get('resource_ref', {}).get('id') != material_id:
        raise HTTPException(404, '回复任务不存在')
    ref = task['resource_ref']
    conv = ai_teacher_repository.material_conversation(user['id'], material_id, ref['revision_id'])
    message = next((m for m in conv['messages'] if m['message_id'] == task_id + ':user'), None)
    if not message:
        raise HTTPException(409, '问题来源已不可用；已有对话仍保留')
    try:
        resolve_context(saved, message['context_ref'])
    except StudyConflict as exc:
        raise HTTPException(409, str(exc))
    await manager.resume_task(task_id)
    return {'task_id': task_id}
