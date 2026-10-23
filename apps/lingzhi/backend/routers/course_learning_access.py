"""Owner-managed course access and the student's authorized course library."""

from __future__ import annotations

import os
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from course_learning_access import CourseLearningAccess
from course_learning_projection import public_course
from dependencies import get_course_or_404
from storage import storage
from study.auth import study_identity

router = APIRouter(tags=["course-learning-access"])


class GrantRequest(BaseModel):
    learner_id: str = Field(default="", max_length=160)
    local_username: str = Field(default="", max_length=40)


class CourseSourceRequest(BaseModel):
    revision_id: str = Field(min_length=1, max_length=200)


def owner_course(course_id: str, request: Request) -> dict:
    course = storage.load_course(course_id)
    if not course or course.get("owner_id") != request.headers.get("X-User-Id"):
        raise HTTPException(404, "课程不存在或不属于当前教师")
    return course


def accessible_course(course_id: str, user: dict) -> dict:
    course = storage.load_course(course_id)
    if not course or (
        course.get("owner_id") != user["id"] and not CourseLearningAccess(storage).active(course, user["id"])
    ):
        raise HTTPException(404, "课程不存在或授权已撤销")
    return course


async def read_learning_course(course_id: str, user: dict) -> dict:
    from course_exchange import is_remote_course, read_remote_course

    if is_remote_course(course_id):
        return await run_in_threadpool(read_remote_course, storage, user["id"], course_id)
    accessible_course(course_id, user)
    return await get_course_or_404(course_id)


@router.get("/teacher/courses/{course_id}/learners")
def list_grants(course_id: str, request: Request):
    owner_course(course_id, request)
    return CourseLearningAccess(storage).list(course_id)


@router.post("/teacher/courses/{course_id}/learners")
def grant_course(course_id: str, body: GrantRequest, request: Request):
    course = owner_course(course_id, request)
    learner_id, label = body.learner_id.strip(), body.learner_id.strip()
    if body.local_username:
        from course_exchange import ExchangeConfig, ExchangeClient, INTERNAL_PREFIX

        config = ExchangeConfig.environment()
        remote_lookup = config.enabled and config.role == "teacher"
        if os.getenv("QIZHI_AUTH_VERIFY_URL", "") or (
            not remote_lookup and os.getenv("LINGZHI_LOCAL_STUDY_AUTH", "").lower() != "true"
        ):
            raise HTTPException(422, "统一登录环境请填写学生身份 ID")
        account = (
            None
            if remote_lookup
            else (storage.load_data("study_accounts.json") or {})
            .get("users", {})
            .get(body.local_username.strip().lower())
        )
        if remote_lookup:
            resolved = ExchangeClient(config).call(
                "POST", INTERNAL_PREFIX + "identity", {"username": body.local_username.strip().lower()}
            )
            account = {"id": resolved["actor_id"], "username": resolved["label"]}
        if not account:
            raise HTTPException(404, "学生账号尚不存在，请先注册学生账号")
        learner_id, label = account["id"], account["username"]
    if (
        not learner_id
        or learner_id == course.get("owner_id")
        or not learner_id.startswith(("qizhi:", "local-student:"))
    ):
        raise HTTPException(422, "请填写已注册学生的身份 ID 或本地用户名")
    return CourseLearningAccess(storage).grant(course, learner_id, label=label)


@router.delete("/teacher/courses/{course_id}/learners/{learner_id}")
def revoke_course(course_id: str, learner_id: str, request: Request):
    owner_course(course_id, request)
    try:
        return CourseLearningAccess(storage).revoke(course_id, learner_id)
    except KeyError:
        raise HTTPException(404, "授权不存在") from None


@router.get("/study/courses")
async def student_courses(user=Depends(study_identity)):
    access = CourseLearningAccess(storage)
    result = []
    for course_id in access.records():
        course = storage.load_course(course_id)
        if not course or not access.active(course, user["id"]):
            continue
        view = await get_course_or_404(course_id)
        disclosed = await run_in_threadpool(public_course, view)
        result.append(
            {
                "course_id": course_id,
                "title": disclosed["course_name"],
                "revision_id": disclosed["current_course_version_id"],
                "section_count": len(disclosed["nodes"]),
                "reading_available": any(n.get("content_blocks") for n in disclosed["nodes"]),
                "grant": access.active(course, user["id"]),
            }
        )
    from course_exchange import ExchangeConfig, ExchangeRepository

    config = ExchangeConfig.environment()
    if config.enabled and config.role == "student":
        references = await run_in_threadpool(ExchangeRepository(storage, config).sync, user["id"])
        for local_id, ref in references.items():
            if ref.get("status") != "active" or ref.get("source_node_id") != config.peer_id:
                continue
            view = ExchangeRepository.projection(local_id, ref["releases"][ref["release_id"]])
            result.append(
                {
                    "course_id": local_id,
                    "title": view["course_name"],
                    "revision_id": ref["release_id"],
                    "section_count": len(view["nodes"]),
                    "reading_available": bool(view["course_document"]["blocks"]),
                    "grant": {"grant_id": "exchange", "label": user["id"]},
                    "exchange_origin": view["exchange_origin"],
                    "update_available": ref["latest_release_id"] != ref["release_id"],
                    "question_count": len(view["learning_assets"]["questions"]),
                    "published_ppts": view.get("published_ppts") or [],
                    "feedback_policy": ref["releases"][ref["release_id"]]["feedback_policy"],
                }
            )
    return result


@router.get("/study/courses/{course_id}")
async def student_course(course_id: str, user=Depends(study_identity)):
    return await run_in_threadpool(public_course, await read_learning_course(course_id, user))


@router.post("/study/courses/{course_id}/sources")
async def import_course_source(course_id: str, body: CourseSourceRequest, user=Depends(study_identity)):
    course = public_course(await read_learning_course(course_id, user))
    if course["current_course_version_id"] != body.revision_id:
        raise HTTPException(409, "教师讲义已更新，请刷新课程后重新选择")
    from study.repository import StudyRepository
    from routers.study import parse_source

    repo = StudyRepository(storage)
    text = "\n\n".join(
        "# " + node["node_name"] + "\n\n" + node["node_content"] for node in course["nodes"] if node.get("node_content")
    )
    if not text:
        raise HTTPException(422, "教师尚未提供可生成的讲义")
    source_repo = repo.sources(user["id"])
    scope = f"course:{course_id}:{body.revision_id}"
    asset = await source_repo.create_text_asset(
        filename=course["course_name"] + ".md", content=text, upload_batch_id=scope, deduplication_scope=scope
    )
    origin = {
        "course_id": course_id,
        "revision_id": body.revision_id,
        "block_ids": [b["block_id"] for b in course["course_document"]["blocks"]],
    }
    if course.get("exchange_origin"):
        origin["exchange_origin"] = course["exchange_origin"]

    result = await parse_source(source_repo, asset)
    readable = [node for node in course["nodes"] if node.get("node_content")]
    sections = result.get("sections") or []
    # Bind the parser's exact ranges to the exported lecture order. Old or
    # ambiguous sources retain course-level context rather than guessed IDs.
    if len(readable) == 1:
        origin["section_node_ids"] = {s["id"]: readable[0]["node_id"] for s in sections}
    elif len(readable) == len(sections) and all(s["title"] == n["node_name"] for s, n in zip(sections, readable)):
        origin["section_node_ids"] = {s["id"]: n["node_id"] for s, n in zip(sections, readable)}

    def save_origin(current):
        current = current or {}
        current.setdefault(user["id"], {})[asset.asset_id] = origin
        return current

    storage.update_data("study_course_sources.json", save_origin)
    result["course_origin"] = origin
    return result


@router.get("/study/courses/{course_id}/path")
async def learning_path(course_id: str, user=Depends(study_identity)):
    course = await read_learning_course(course_id, user)
    disclosed = public_course(course)
    course = {**course, **disclosed}

    def project():
        from learning_progress import build_learning_progress
        from learning_continuation import build_learning_continuation
        from practice_attempts import practice_attempt_repository

        progress = build_learning_progress(course, user_id=user["id"])
        chapters = [n for n in disclosed["nodes"] if n.get("node_level") == 1] or disclosed["nodes"]
        steps = []
        for chapter in chapters:
            state = build_learning_continuation(
                course, user_id=user["id"], node_id=chapter["node_id"], progress=progress
            )
            chapter_id = state["chapter"]["chapter_id"]
            if any(step["chapter_id"] == chapter_id for step in steps):
                continue
            steps.append(
                {
                    "chapter_id": chapter_id,
                    "title": state["chapter"]["chapter_name"],
                    "progress": state["progress"],
                    "action": state["primary_action"],
                    "risks": state["risks"],
                }
            )
        continuation = build_learning_continuation(course, user_id=user["id"])
        attempts = practice_attempt_repository.list(user["id"], course_id)
        return {
            "course_id": course_id,
            "revision_id": disclosed["current_course_version_id"],
            "steps": steps,
            "next_action": continuation["primary_action"],
            "chapter": continuation["chapter"],
            "attempt_count": len(attempts),
            "basis": "saved_learning_facts",
            "unassessed_is_not_failure": True,
        }

    return await run_in_threadpool(project)
