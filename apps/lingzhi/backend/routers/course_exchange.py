"""Teacher publication, learner synchronization, and explicit feedback receipts."""

from copy import deepcopy
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, field_validator

from course_exchange import ExchangeClient, ExchangeConfig, ExchangeRepository, INTERNAL_PREFIX, now, require_peer, register_learning_summary_validator
from course_exchange_digest import digest
from dependencies import get_course_or_404
from routers.course_learning_access import owner_course
from storage import storage
from study.auth import study_identity
from course_exchange_ppt import public_ppt_options, published_ppt_path

router = APIRouter(tags=["course-exchange"])
PEER_ROUTE_PREFIX = INTERNAL_PREFIX.removeprefix("/api")


def _learning_summary_allowed(actor, local_course_id, payload):
    from companion_learning import CompanionService
    from ai_teacher_state import ai_teacher_repository
    state=CompanionService(ai_teacher_repository).read(actor,local_course_id)
    return payload.get('consent_revision')==state['revision'] and bool(payload.get('withdrawn'))!=bool(state['feedback_consent'])


register_learning_summary_validator(_learning_summary_allowed)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Actor(StrictModel):
    actor_id: str = Field(min_length=1, max_length=160, pattern=r"^(qizhi:|local-student:).+")


class ReleaseRead(Actor):
    course_id: str = Field(min_length=1, max_length=200)
    release_id: str = Field(min_length=1, max_length=200)


class PublishRequest(StrictModel):
    expected_revision: str = Field(min_length=1, max_length=200)
    ppt_project_ids: list[str] = Field(default_factory=list, max_length=20)


class GradeRequest(ReleaseRead):
    task_revision_id: str = Field(min_length=1, max_length=200)
    attempt_id: str = Field(min_length=1, max_length=200)
    attempt: dict = Field(default_factory=dict)


class HintRequest(ReleaseRead):
    task_revision_id: str = Field(min_length=1, max_length=200)
    level: int = Field(ge=1, le=3)


class SolutionRequest(ReleaseRead):
    task_revision_id: str = Field(min_length=1, max_length=200)


class PptRequest(ReleaseRead):
    asset_id: str = Field(pattern=r"^ppt_[0-9a-f]{32}$")


class FeedbackEnvelope(ReleaseRead):
    feedback_id: str = Field(min_length=1, max_length=160, pattern=r"^feedback_[0-9a-f]{32}$")
    source_node_id: str = Field(min_length=1, max_length=64)
    kind: str = Field(pattern=r"^(course_question|practice_result|learning_summary)$")
    payload: dict


class StudentFeedback(StrictModel):
    request_id: str = Field(min_length=1, max_length=160)
    expected_release_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=6000)

    @field_validator("text")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("课程问题不能为空")
        return value.strip()


class AdoptVersion(StrictModel):
    expected_release_id: str = Field(min_length=1, max_length=200)


class TeacherReply(StrictModel):
    expected_revision: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=6000)

    @field_validator("text")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("回复不能为空")
        return value.strip()


class IdentityLookup(StrictModel):
    username: str = Field(min_length=3, max_length=40)


def publisher(config=Depends(require_peer)):
    if config.role != "teacher":
        raise HTTPException(403, "此节点不是课程发布方")
    return config


def teacher_config():
    config = ExchangeConfig.environment().validate()
    if config.role != "teacher":
        raise HTTPException(403, "当前服务不是教师发布方")
    return config


def consumer_config():
    config = ExchangeConfig.environment().validate()
    if config.role != "student":
        raise HTTPException(403, "当前服务不是学生学习端")
    return config


def task_in_release(release, revision_id):
    task = next(
        (q for q in release["private_tasks"] if str(q.get("task_revision_id") or q.get("revision_id")) == revision_id),
        None,
    )
    if not task:
        raise HTTPException(404, "题目不属于这个发布版本")
    return task


@router.get("/teacher/courses/{course_id}/exchange")
async def teacher_exchange(course_id: str, request: Request):
    owner_course(course_id, request)
    config = ExchangeConfig.environment()
    repo = ExchangeRepository(storage, config)
    publication = repo.ledger().get("publications", {}).get(course_id) or {}
    course = await get_course_or_404(course_id)
    if publication.get("owner_id") != course.get("owner_id"):
        publication = {}
    from course_learning_projection import public_document

    document = public_document(course)
    return {
        "enabled": config.enabled and config.role == "teacher",
        "current_revision": document["document_revision"],
        "published_release_id": publication.get("current_release_id", ""),
        "status": publication.get("status", "unpublished"),
        "feedback_count": sum(
            i["envelope"]["course_id"] == course_id and i.get("owner_id") == request.headers.get("X-User-Id")
            for i in repo.ledger().get("received", {}).values()
        ),
        "ppt_options": public_ppt_options(course, document, storage=storage),
    }


@router.post("/teacher/courses/{course_id}/exchange/publish")
async def publish_course(course_id: str, body: PublishRequest, request: Request):
    owner_course(course_id, request)
    config = teacher_config()
    course = await get_course_or_404(course_id)
    from learning_progress import project_learning_objective_bindings
    from routers.practice import _questions

    projected = project_learning_objective_bindings(course)
    tasks = await run_in_threadpool(_questions, projected, node_id=None, scope="all")
    final_tasks = await run_in_threadpool(_questions, projected, node_id=None, scope="final")
    by_revision = {str(t.get("task_revision_id") or t.get("revision_id")): t for t in [*tasks, *final_tasks]}
    public = await run_in_threadpool(
        ExchangeRepository(storage, config).publish,
        course,
        list(by_revision.values()),
        expected_revision=body.expected_revision,
        ppt_project_ids=body.ppt_project_ids,
    )
    return {
        "release_id": public["release_id"],
        "source_document_revision": public["source_document_revision"],
        "question_count": sum(
            len(public["course"]["learning_assets"][key]) for key in ("questions", "final_assessment")
        ),
        "status": "published",
    }


@router.delete("/teacher/courses/{course_id}/exchange/publication")
def withdraw_course(course_id: str, request: Request):
    owner_course(course_id, request)
    teacher_config()
    ExchangeRepository(storage).unpublish(course_id)
    return {"status": "withdrawn"}


@router.post(PEER_ROUTE_PREFIX + "identity")
def peer_identity(body: IdentityLookup, config=Depends(require_peer)):
    if config.role != "student" or storage is None:
        raise HTTPException(403, "此节点不提供学生身份查询")
    import os

    if os.getenv("QIZHI_AUTH_VERIFY_URL", "") or os.getenv("LINGZHI_LOCAL_STUDY_AUTH", "").lower() != "true":
        raise HTTPException(403, "统一登录环境请使用学生身份 ID")
    account = (storage.load_data("study_accounts.json") or {}).get("users", {}).get(body.username.strip().lower())
    if not account:
        raise HTTPException(404, "学生账号不存在")
    return {"node_id": config.node_id, "actor_id": account["id"], "label": account["username"]}


@router.post(PEER_ROUTE_PREFIX + "catalogue")
def catalogue(body: Actor, config=Depends(publisher)):
    repo = ExchangeRepository(storage, config)
    publications = []
    for course_id in repo.ledger().get("publications", {}):
        try:
            publications.append(repo.publication(course_id, body.actor_id)["public"])
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
    return {"node_id": config.node_id, "publications": publications}


@router.post(PEER_ROUTE_PREFIX + "read")
def peer_read(body: ReleaseRead, config=Depends(publisher)):
    return {
        "node_id": config.node_id,
        "publication": ExchangeRepository(storage, config).publication(body.course_id, body.actor_id, body.release_id)[
            "public"
        ],
    }


@router.post(PEER_ROUTE_PREFIX + "grade")
async def grade(body: GradeRequest, config=Depends(publisher)):
    from course_exchange import publisher_grade_lock

    key = digest([config.peer_id, body.actor_id, body.attempt_id])
    async with publisher_grade_lock(storage, key):
        return await grade_locked(body, config)


@router.post(PEER_ROUTE_PREFIX + "ppt")
def peer_ppt(body: PptRequest, config=Depends(publisher)):
    from fastapi.responses import FileResponse

    release = ExchangeRepository(storage, config).publication(body.course_id, body.actor_id, body.release_id)
    manifest = next(
        (p for p in release["public"]["course"].get("published_ppts") or [] if p["asset_id"] == body.asset_id), None
    )
    if not manifest:
        raise HTTPException(404, "PPT 不属于这个发布版本")
    return FileResponse(
        published_ppt_path(storage, manifest),
        headers={"X-Lingzhi-Node": config.node_id},
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=manifest["filename"],
    )


async def grade_locked(body, config):
    repo = ExchangeRepository(storage, config)
    release = repo.publication(body.course_id, body.actor_id, body.release_id)
    task = task_in_release(release, body.task_revision_id)
    # Peer may forward evidence fields, never a grade, rubric or hidden tests.
    attempt = {
        key: deepcopy(body.attempt[key])
        for key in ("submitted_answer_payload", "revealed_hint_levels", "solution_revealed", "ai_support_level")
        if key in body.attempt
    }
    if len(str(attempt)) > 100000:
        raise HTTPException(422, "作答过大")
    identity = [config.peer_id, body.actor_id, body.attempt_id]
    key = digest(identity)
    fingerprint = digest([body.course_id, body.release_id, body.task_revision_id, attempt])
    old = repo.ledger().get("grades", {}).get(key)
    if old:
        if old["fingerprint"] != fingerprint:
            raise HTTPException(409, "同一次作答的冻结内容不一致")
        return {"node_id": config.node_id, "result": old["result"], "receipt_id": old["receipt_id"]}
    from practice_grading import practice_grader

    result = await practice_grader.grade(task, attempt)
    receipt = {
        "receipt_id": "grade_" + uuid4().hex,
        "fingerprint": fingerprint,
        "actor_id": body.actor_id,
        "attempt_id": body.attempt_id,
        "course_id": body.course_id,
        "release_id": body.release_id,
        "task_revision_id": body.task_revision_id,
        "answer_payload": attempt.get("submitted_answer_payload") or {},
        "result": result,
        "support": {"ai_support_level":attempt.get('ai_support_level',0),"hint_used":bool(attempt.get('revealed_hint_levels')),"solution_revealed":bool(attempt.get('solution_revealed'))},
        "created_at": now(),
    }

    def save(value):
        grades = value.setdefault("grades", {})
        prior = grades.get(key)
        if prior and prior["fingerprint"] != fingerprint:
            raise HTTPException(409, "作答已变化")
        grades.setdefault(key, receipt)
        return value

    saved = repo.update(save)["grades"][key]
    return {"node_id": config.node_id, "result": saved["result"], "receipt_id": saved["receipt_id"]}


@router.post(PEER_ROUTE_PREFIX + "hint")
def hint(body: HintRequest, config=Depends(publisher)):
    task = task_in_release(
        ExchangeRepository(storage, config).publication(body.course_id, body.actor_id, body.release_id),
        body.task_revision_id,
    )
    selected = next(
        (h for h in (task.get("hint_contract") or {}).get("levels") or [] if h.get("level") == body.level), None
    )
    if not selected:
        raise HTTPException(404, "此题没有这一层提示")
    return {"node_id": config.node_id, "hint": selected}


@router.post(PEER_ROUTE_PREFIX + "solution")
def solution(body: SolutionRequest, config=Depends(publisher)):
    repo = ExchangeRepository(storage, config)
    task = task_in_release(repo.publication(body.course_id, body.actor_id, body.release_id), body.task_revision_id)
    if not any(
        g["actor_id"] == body.actor_id
        and g["course_id"] == body.course_id
        and g["release_id"] == body.release_id
        and g["task_revision_id"] == body.task_revision_id
        for g in repo.ledger().get("grades", {}).values()
    ):
        raise HTTPException(409, "先完成一次正式提交，再查看解答")
    from routers.practice import _solution_payload

    return {"node_id": config.node_id, "solution": _solution_payload(task)}


@router.post(PEER_ROUTE_PREFIX + "feedback")
def receive_feedback(body: FeedbackEnvelope, config=Depends(publisher)):
    repo = ExchangeRepository(storage, config)
    if body.kind == "course_question":
        if (
            set(body.payload) != {"text"}
            or not isinstance(body.payload["text"], str)
            or not 1 <= len(body.payload["text"].strip()) <= 6000
        ):
            raise HTTPException(422, "课程反馈格式不正确")
    elif body.kind == 'learning_summary':
        from companion_teaching_feedback import learning_summary
        public=body.payload
        if set(public)-{'schema_version','consent_revision','withdrawn','goal','formal_evidence_count'} or public.get('schema_version')!='companion_feedback_v1' or type(public.get('withdrawn')) is not bool or type(public.get('consent_revision')) is not int:
            raise HTTPException(422,'Invalid learning summary')
        if public['withdrawn']:
            if set(public)!={'schema_version','consent_revision','withdrawn'}:raise HTTPException(422,'Withdrawn summary contains data')
        else:
            goal=public.get('goal') or {}
            if set(goal)!={'text','purpose'} or not isinstance(goal.get('text'),str) or len(goal['text'])>2000 or goal.get('purpose') not in {'systematic','exam','project','mixed'} or type(public.get('formal_evidence_count')) is not int or public['formal_evidence_count']<0:raise HTTPException(422,'Invalid goal summary')
    else:
        receipt_id = body.payload.get("receipt_id")
        receipt = next((g for g in repo.ledger().get("grades", {}).values() if g["receipt_id"] == receipt_id), None)
        if (
            not receipt
            or receipt["actor_id"] != body.actor_id
            or receipt["course_id"] != body.course_id
            or receipt["release_id"] != body.release_id
            or receipt["attempt_id"] != body.payload.get("attempt_id")
        ):
            raise HTTPException(422, "作答反馈缺少对应的批改回执")
        if set(body.payload) != {"attempt_id", "attempt_revision", "receipt_id"}:
            raise HTTPException(422, "作答反馈只能引用正式作答和批改回执")
    return repo.receive(body.model_dump(), config.peer_id)


@router.post(PEER_ROUTE_PREFIX + "feedback-status")
def feedback_status(body: ReleaseRead, config=Depends(publisher)):
    repo = ExchangeRepository(storage, config)
    repo.publication(body.course_id, body.actor_id, body.release_id)
    replies = [
        {
            "feedback_id": key,
            "reply": item["reply"],
            "revision": item["revision"],
            "replied_at": item.get("replied_at", ""),
        }
        for key, item in repo.ledger().get("received", {}).items()
        if item["envelope"]["actor_id"] == body.actor_id and item["envelope"]["course_id"] == body.course_id
    ]
    return {"node_id": config.node_id, "replies": replies}


@router.get("/teacher/courses/{course_id}/exchange/feedback")
def teacher_feedback(course_id: str, request: Request):
    owner_course(course_id, request)
    value = ExchangeRepository(storage).ledger()
    grades = {g["receipt_id"]: g for g in value.get("grades", {}).values()}
    items = []
    for key, item in value.get("received", {}).items():
        envelope = item["envelope"]
        if envelope["course_id"] != course_id or item.get("owner_id") != request.headers.get("X-User-Id"):
            continue
        row = {
            "feedback_id": key,
            **deepcopy(envelope),
            "reply": item["reply"],
            "revision": item["revision"],
            "received_at": item["received_at"],
        }
        if envelope["kind"] == "practice_result":
            grade_record = grades.get(envelope["payload"].get("receipt_id")) or {}
            release = ((value.get("publications", {}).get(course_id) or {}).get("releases") or {}).get(
                envelope["release_id"]
            ) or {}
            task = next(
                (
                    t
                    for t in release.get("private_tasks") or []
                    if str(t.get("task_revision_id") or t.get("revision_id")) == grade_record.get("task_revision_id")
                ),
                {},
            )
            row["assessment"] = {
                key: deepcopy(grade_record.get(key)) for key in ("task_revision_id", "answer_payload", "result")
            }
            row['assessment']['support'] = deepcopy(grade_record.get('support') or {})
            row["assessment"]["task"] = {
                key: deepcopy(task[key]) for key in ("prompt", "question_type", "options", "node_id", "concept_ids", "knowledge_revision_refs", "knowledge_name") if key in task
            }
        items.append(row)
    latest_summaries={}
    for item in items:
        if item.get('kind')!='learning_summary':continue
        key=(item['actor_id'],item['release_id'])
        prior=latest_summaries.get(key)
        if not prior or (item['payload'].get('consent_revision',0),item['received_at'])>(prior['payload'].get('consent_revision',0),prior['received_at']):latest_summaries[key]=item
    items=[i for i in items if i.get('kind')!='learning_summary']+[i for i in latest_summaries.values() if not i['payload'].get('withdrawn')]
    return {"items": items, "count": len(items)}


@router.get('/teacher/courses/{course_id}/exchange/learning-analysis')
def teacher_learning_analysis(course_id:str,request:Request,release_id:str=Query(default='',max_length=200),since:str=Query(default='',max_length=40),until:str=Query(default='',max_length=40)):
    from course_learning_access import CourseLearningAccess
    from companion_teaching_feedback import summarize_feedback
    from companion_learning import CompanionService
    course=owner_course(course_id,request)
    publication=ExchangeRepository(storage).ledger().get('publications',{}).get(course_id) or {}
    release_id=release_id or publication.get('current_release_id','')
    roster=[r for r in CourseLearningAccess(storage).list(course_id) if r.get('owner_id')==course['owner_id']]
    rows=teacher_feedback(course_id,request)['items']
    projection=summarize_feedback(roster,rows,release_id=release_id,since=since,until=until)
    actors={r['learner_id'] for r in roster if r.get('status')=='active'}
    summaries={}
    for row in sorted(rows,key=lambda r:r.get('received_at') or ''):
        if row.get('kind')=='learning_summary' and row.get('actor_id') in actors and row.get('release_id')==release_id:
            summaries[row['actor_id']]=row['payload']
    for actor in actors:
        local=CompanionService(__import__('ai_teacher_state').ai_teacher_repository).read(actor,course_id)
        if local['feedback_consent']:
            from companion_teaching_feedback import learning_summary
            summaries[actor]=learning_summary(local,{})
    projection['shared_goals']=[{'actor_id':actor,**s} for actor,s in summaries.items() if not s.get('withdrawn')]
    projection['available_releases']=list(publication.get('releases',{}))
    return projection


class CompanionSummaryRequest(StrictModel):
    request_id:str=Field(min_length=8,max_length=160)

@router.post('/study/courses/{course_id}/exchange/learning-summary')
def send_companion_summary(course_id:str,body:CompanionSummaryRequest,user=Depends(study_identity)):
    from ai_teacher_state import ai_teacher_repository
    from companion_learning import CompanionService
    from companion_teaching_feedback import learning_summary
    repo=ExchangeRepository(storage)
    ref=repo.reference(user['id'],course_id)
    if not ref:raise HTTPException(404,'Published course not found')
    repo.read(user['id'],course_id)
    payload=learning_summary(CompanionService(ai_teacher_repository).read(user['id'],course_id),{})
    feedback_id=repo.queue_feedback(user['id'],course_id,request_id=body.request_id,kind='learning_summary',payload=payload,release_id=ref['release_id'])
    return repo.deliver(user['id'],feedback_id)


@router.post("/teacher/courses/{course_id}/exchange/feedback/{feedback_id}/reply")
def reply(course_id: str, feedback_id: str, body: TeacherReply, request: Request):
    owner_course(course_id, request)
    repo = ExchangeRepository(storage)

    def save(value):
        item = value.get("received", {}).get(feedback_id)
        if (
            not item
            or item["envelope"]["course_id"] != course_id
            or item.get("owner_id") != request.headers.get("X-User-Id")
        ):
            raise HTTPException(404, "反馈不存在")
        if item["revision"] != body.expected_revision:
            raise HTTPException(409, "反馈已经更新，请刷新")
        item.update(reply=body.text.strip(), revision=item["revision"] + 1, replied_at=now())
        return value

    saved = repo.update(save)["received"][feedback_id]
    return {"feedback_id": feedback_id, "revision": saved["revision"], "reply": saved["reply"]}


@router.post("/study/courses/{course_id}/exchange/update")
def update_course(course_id: str, body: AdoptVersion, user=Depends(study_identity)):
    consumer_config()
    ref = ExchangeRepository(storage).adopt(user["id"], course_id, body.expected_release_id)
    return {"release_id": ref["release_id"], "status": "updated"}


@router.post("/study/courses/{course_id}/exchange/ppt/{asset_id}/download")
def download_student_ppt(course_id: str, asset_id: str, body: AdoptVersion, user=Depends(study_identity)):
    from fastapi.responses import Response
    import hashlib

    consumer_config()
    course = ExchangeRepository(storage).read(user["id"], course_id)
    origin = course["exchange_origin"]
    if origin["release_id"] != body.expected_release_id:
        raise HTTPException(409, "课程版本已变化，请刷新")
    manifest = next((p for p in course.get("published_ppts") or [] if p["asset_id"] == asset_id), None)
    if not manifest:
        raise HTTPException(404, "PPT 不属于这个发布版本")
    content = ExchangeClient().call(
        "POST",
        INTERNAL_PREFIX + "ppt",
        {
            "actor_id": user["id"],
            "course_id": origin["source_course_id"],
            "release_id": origin["release_id"],
            "asset_id": asset_id,
        },
        binary=True,
    )
    if len(content) != manifest["size_bytes"] or hashlib.sha256(content).hexdigest() != manifest["sha256"]:
        raise HTTPException(503, "PPT 成品校验失败")
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")


@router.post("/study/courses/{course_id}/exchange/feedback")
def student_feedback(course_id: str, body: StudentFeedback, user=Depends(study_identity)):
    consumer_config()
    repo = ExchangeRepository(storage)
    ref = repo.reference(user["id"], course_id)
    if ref.get("status") != "active":
        raise HTTPException(404, "课程来源已不可用")
    if ref["release_id"] != body.expected_release_id:
        raise HTTPException(409, "课程版本已变化，请刷新后提交反馈")
    try:
        repo.read(user["id"], course_id)
    except HTTPException as exc:
        if exc.status_code != 503:
            raise
        # Only an owned question is saved offline; the publisher revalidates
        # access on delivery. No course content is returned by this endpoint.
    key = repo.queue_feedback(
        user["id"], course_id, request_id=body.request_id, kind="course_question", payload={"text": body.text.strip()}
    )
    delivered = repo.deliver(user["id"], key)
    return {"feedback_id": key, "status": delivered["status"]}


@router.get("/study/courses/{course_id}/exchange/feedback")
def student_feedback_history(course_id: str, user=Depends(study_identity)):
    consumer_config()
    repo = ExchangeRepository(storage)
    ref = repo.reference(user["id"], course_id)
    try:
        received = ExchangeClient().call(
            "POST",
            INTERNAL_PREFIX + "feedback-status",
            {"actor_id": user["id"], "course_id": ref["source_course_id"], "release_id": ref["release_id"]},
        )
        replies_available = True
    except HTTPException as exc:
        if exc.status_code != 503:
            raise
        received, replies_available = {"replies": []}, False
    replies = {r["feedback_id"]: r for r in received["replies"]}
    rows = [
        {
            "feedback_id": key,
            "kind": item["envelope"]["kind"],
            "payload": item["envelope"]["payload"],
            "status": item["status"],
            "created_at": item["created_at"],
            **replies.get(key, {}),
        }
        for key, item in repo.ledger().get("outbox", {}).items()
        if item["envelope"]["actor_id"] == user["id"] and item["local_course_id"] == course_id
    ]
    return {"items": rows, "replies_available": replies_available}


@router.post("/study/courses/{course_id}/exchange/feedback/{feedback_id}/retry")
def retry_feedback(course_id: str, feedback_id: str, user=Depends(study_identity)):
    consumer_config()
    repo = ExchangeRepository(storage)
    item = repo.ledger().get("outbox", {}).get(feedback_id)
    if not item or item["local_course_id"] != course_id:
        raise HTTPException(404, "反馈不存在")
    delivered = repo.deliver(user["id"], feedback_id)
    return {"feedback_id": feedback_id, "status": delivered["status"]}
