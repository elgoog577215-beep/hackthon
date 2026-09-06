"""Owner-only, disposable student-view trials over the formal course assets.

There are deliberately no learner repositories or mutation services here.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from assessment_contracts import project_public_question
from ai_qa_service import AIQAService, AITeacherModelFailure
from course_document import CourseDocument, stable_hash
from practice_grading import practice_grader
from question_bank import approved_formal_tasks, load_active_question_bank, question_bank_repository
from storage import storage

router = APIRouter(prefix="/teacher/courses/{course_id}/preview", tags=["teacher-preview"])
qa_service = AIQAService()


def owned_course(course_id: str, request: Request) -> dict:
    raw = storage.load_course(course_id)
    actor = str(request.headers.get("X-User-Id") or "").strip()
    if not actor or not raw or raw.get("owner_id") != actor or raw.get("authoring_surface") != "teacher":
        raise HTTPException(404, detail={"code": "teacher_course_unavailable", "message": "课程不存在或不属于当前教师"})
    if not raw.get("course_document"):
        raise HTTPException(409, detail={"code": "handout_unavailable", "message": "当前课程尚无正式讲义"})
    return raw


def public_document(raw: dict) -> dict:
    doc = CourseDocument.model_validate(raw["course_document"])
    # Unknown conditional disclosure rules are private until supported. Never
    # pass authoring metadata, candidates or source snapshots to this surface.
    blocks = []
    for b in doc.blocks:
        if b.status != "final" or (b.visibility_rule and b.visibility_rule not in ({"audience": "student"}, {"audience": "all"})):
            continue
        blocks.append({"block_id": b.block_id, "section_id": b.section_id,
            "position": b.position, "role": b.role, "kind": b.kind,
            "internal_revision": b.internal_revision,
            "payload": {key: deepcopy(b.payload[key]) for key in ("title", "markdown", "summary", "feedback_structure") if key in b.payload}})
    return {"course_id": doc.course_id, "title": doc.title, "document_revision": doc.document_revision,
        "sections": [s.model_dump(include={"section_id", "parent_section_id", "title", "position", "level"}) for s in doc.sections],
        "blocks": blocks}


def formal_questions(raw: dict) -> list[dict]:
    bundle = load_active_question_bank(raw, repository=question_bank_repository)
    return approved_formal_tasks(bundle) if bundle else []


def snapshot(raw: dict) -> tuple[dict, list[dict], str]:
    document = public_document(raw)
    questions = formal_questions(raw)
    revision = stable_hash({"document": document["document_revision"],
        "questions": [q.get("revision_id") for q in questions]}, prefix="trial_")
    return document, questions, revision


def assert_revision(actual: str, expected: str) -> None:
    if actual != expected:
        raise HTTPException(409, detail={"code": "preview_source_changed", "message": "课程或题目已更新，请刷新预览后重试"})


@router.get("")
def read_preview(course_id: str, request: Request):
    raw = owned_course(course_id, request)
    document, questions, revision = snapshot(raw)
    return {"course_id": course_id, "preview_revision": revision, "document": document,
        "questions": [project_public_question(q) for q in questions],
        "handouts": {lid: {k: b.get(k) for k in ("revision_id", "source_lesson_plan_revision_id", "source_outline_revision_id")} for lid, b in (raw.get("teacher_handouts") or {}).items()},
        "availability": {"reading": bool(document["blocks"]), "practice": bool(questions)}}


class GradeRequest(BaseModel):
    preview_revision: str = Field(min_length=1, max_length=160)
    question_revision_id: str = Field(min_length=1, max_length=160)
    answer_payload: dict[str, Any]


@router.post("/grade")
async def grade_preview(course_id: str, body: GradeRequest, request: Request):
    raw = owned_course(course_id, request)
    _, questions, revision = snapshot(raw)
    assert_revision(revision, body.preview_revision)
    question = next((q for q in questions if q.get("revision_id") == body.question_revision_id), None)
    if question is None:
        raise HTTPException(409, detail={"code": "preview_question_changed", "message": "题目已更新，请刷新预览"})
    import json
    if len(json.dumps(body.answer_payload)) > 60000:
        raise HTTPException(413, detail="Answer is too large")
    result = await practice_grader.grade(question, {"answer_payload": body.answer_payload, "hint_events": []})
    assert_revision(snapshot(owned_course(course_id, request))[2], revision)
    return {"preview_revision": revision, "question_revision_id": body.question_revision_id, "feedback": result}


class TrialMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class AskRequest(BaseModel):
    preview_revision: str = Field(min_length=1, max_length=160)
    question: str = Field(min_length=1, max_length=4000)
    section_id: str = Field(default="", max_length=160)
    block_ids: list[str] = Field(default_factory=list, max_length=20)
    messages: list[TrialMessage] = Field(default_factory=list, max_length=12)


@router.post("/ask")
async def ask_preview(course_id: str, body: AskRequest, request: Request):
    raw = owned_course(course_id, request)
    document, _, revision = snapshot(raw)
    assert_revision(revision, body.preview_revision)
    sections = {s["section_id"]: s for s in document["sections"]}
    if body.section_id and body.section_id not in sections:
        raise HTTPException(422, detail="Unknown section reference")
    visible = {b["block_id"]: b for b in document["blocks"]}
    if any(bid not in visible for bid in body.block_ids):
        raise HTTPException(422, detail="Unknown block reference")
    from ai_teacher_context import _select_sources
    safe_nodes = [{"node_id": sid, "node_name": section["title"], "content_blocks": [
        {"block_id": b["block_id"], "block_revision_id": b["internal_revision"], "title": b["payload"].get("title"), "content": b["payload"].get("markdown", "")}
        for b in visible.values() if b["section_id"] == sid and (not body.block_ids or b["block_id"] in body.block_ids)]}
        for sid, section in sections.items()]
    sources = _select_sources({"nodes": safe_nodes, "current_course_version_id": document["document_revision"]},
        node_id=body.section_id, question=body.question, selection="", perspective="teacher",
        context_ref={"content_anchor": {"file_scope": {"mode": "all"}}})
    package = {"request": {"question": body.question, "perspective": "student", "entrypoint": "teacher_preview", "intent": "explain"},
        "scene": {"course_id": course_id, "node_id": body.section_id, "document_revision": document["document_revision"]},
        "sources": sources, "conversation": {"recent_messages": [m.model_dump() for m in body.messages]},
        "permissions": {"persist": False, "modify_course": False}, "runtime": {}, "learner_model": {}, "learner_evidence": []}
    try:
        answer = "".join([chunk async for chunk in qa_service.answer_question_stream(body.question, context_package=package)])
    except AITeacherModelFailure as exc:
        raise HTTPException(503, detail={"code": exc.code, "message": exc.message}) from exc
    assert_revision(snapshot(owned_course(course_id, request))[2], revision)
    return {"preview_revision": revision, "answer": answer,
        "sources": [{k: v for k, v in s.items() if k != "content"} for s in sources]}
