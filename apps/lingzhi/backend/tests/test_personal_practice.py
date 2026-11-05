import asyncio
from copy import deepcopy
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import pytest

from practice_attempts import AttemptConflict, PracticeAttemptRepository
from storage import Storage
from study import practice
from study.auth import study_identity
from study.repository import StudyRepository

BASE = "/api/study/materials/m/practice"


@pytest.fixture
def env(tmp_path, monkeypatch):
    repo = StudyRepository(Storage(str(tmp_path / "data")))
    attempts = PracticeAttemptRepository(tmp_path / "attempts")
    events, calls = [], []
    monkeypatch.setattr(practice, "practice_attempt_repository", attempts)
    monkeypatch.setattr(practice, "record_learning_event", lambda **kw: events.append(kw))

    async def grade(_self, question, attempt):
        calls.append((deepcopy(question), deepcopy(attempt)))
        return {"status": "graded", "passed": False, "score": 30, "feedback": "请核对条件。",
                "grading_confidence": .94, "grading_method": "rubric_ai", "mastery_eligible": True}
    monkeypatch.setattr(practice.PersonalPracticeGrader, "grade", grade)
    material = {"id": "m", "owner_id": "student", "request_key": "material-request-0001", "fingerprint": "f",
                "title": "一门课", "purpose": "systematic", "status": "completed", "task_id": "t",
                "updated_at": "now", "request": {"source_sections": []},
                "revisions": [{"id": "r", "sections": [{"id": "s", "title": "第一讲", "complete": True, "blocks": [
                    {"block_id": "example", "content_type": "example", "title": "例题", "content": "解法直接展示。"},
                    {"block_id": "q", "content_type": "exercise", "title": "练一练", "content": "求解。<details><summary>提示</summary>先核对条件。</details>"},
                    {"block_id": "a", "content_type": "answer", "title": "参考解答", "content": "隐含解答-secret", "answer_to": "q"},
                    {"block_id": "no-answer", "content_type": "question", "title": "旧题", "content": "阐明观点。"},
                    {"block_id": "unbound", "content_type": "answer", "title": "答案", "content": "未关联，不能配给邻题。"},
                ]}]}]}
    repo.reserve("student", material["request_key"], "f", material)
    app = FastAPI()
    app.include_router(practice.router, prefix="/api")
    app.dependency_overrides[practice.repository] = lambda: repo

    def identity(request: Request):
        return {"id": request.headers.get("x-test-user", "student"), "role": "student"}
    app.dependency_overrides[study_identity] = identity
    return SimpleNamespace(client=TestClient(app), repo=repo, attempts=attempts, events=events, calls=calls)


def start(env, index=0, **extra):
    questions = env.client.get(BASE).json()["questions"]
    response = env.client.post(BASE + "/attempts", json={"revision_id": "r", "question_id": questions[index]["question_id"],
                                                       "request_id": "practice-create-0001", **extra})
    assert response.status_code == 200, response.text
    return response.json()


def submit(env, attempt, answer="我的原始答案", **extra):
    response = env.client.post(BASE + f"/attempts/{attempt['attempt_id']}/submit", json={
        "expected_revision": attempt["revision"], "request_id": "practice-submit-0001", "answer": answer, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def test_questions_use_semantic_type_explicit_bindings_and_never_expose_answers(env):
    response = env.client.get(BASE)
    assert response.status_code == 200
    questions = response.json()["questions"]
    assert [q["block_id"] for q in questions] == ["q", "no-answer"]
    assert questions[0]["has_answer"] and questions[0]["has_hint"]
    assert not questions[1]["has_answer"]
    assert questions[0]["prompt"] == "求解。"
    assert "secret" not in response.text and "先核对条件" not in response.text
    assert env.calls == [] and env.events == [] and env.attempts.list("student", "personal-material:m") == []


def test_create_is_private_idempotent_and_does_not_touch_material_or_course(env):
    before = env.repo.get("student", "m")
    created = start(env)
    assert start(env) == created
    assert "_question" not in created["metadata"] and "secret" not in str(created)
    assert created["metadata"].get("review") is None
    assert len(env.attempts.list("student", "personal-material:m")) == 1
    assert env.attempts.list("student", "m") == []
    assert env.repo.get("student", "m") == before
    for path in [BASE, BASE + f"/attempts/{created['attempt_id']}/solution"]:
        response = env.client.get(path, headers={"x-test-user": "another"}) if path == BASE else env.client.post(path, headers={"x-test-user": "another"}, json={"expected_revision": 1})
        assert response.status_code == 404
    assert all(event.get("course_id") is None for event in env.events)
    question2 = env.client.get(BASE).json()["questions"][1]
    assert env.client.post(BASE + "/attempts", json={"revision_id": "r", "question_id": question2["question_id"], "request_id": "practice-create-0001"}).status_code == 409


def test_submission_freezes_original_and_replay_does_not_grade_twice(env):
    created = start(env)
    path = BASE + f"/attempts/{created['attempt_id']}"
    drafted = env.client.put(path + "/draft", json={"expected_revision": 1, "answer": "草稿"}).json()
    assert drafted["revision"] == 2
    stale = env.client.put(path + "/draft", json={"expected_revision": 1, "answer": "迟到覆盖"})
    assert stale.status_code == 409 and "secret" not in stale.text and "_question" not in stale.text
    graded = submit(env, drafted)
    assert graded["submitted_answer_payload"] == {"text": "我的原始答案"}
    assert graded["result"]["passed"] is False and graded["result"]["mastery_eligible"] is False
    assert len(env.calls) == 1 and env.calls[0][0]["answer_spec"]["canonical_answer"] == "隐含解答-secret"
    assert submit(env, drafted) == graded and len(env.calls) == 1
    changed = env.client.post(path + "/submit", json={"expected_revision": 2, "request_id": "practice-submit-0001", "answer": "偷偷改原答"})
    assert changed.status_code == 409
    assert env.client.put(path + "/draft", json={"expected_revision": graded["revision"], "answer": "覆盖原答"}).status_code == 409


def test_missing_or_blank_answers_are_saved_pending_without_model_calls(env):
    pending = submit(env, start(env, index=1), answer="关于观点的原答")
    assert pending["result"]["reason"] == "missing_answer" and pending["result"]["passed"] is None
    assert pending["submitted_answer_payload"]["text"] == "关于观点的原答" and env.calls == []
    blank = submit(env, start(env, request_id="practice-create-0002"), answer="   ")
    assert blank["result"]["reason"] == "empty_answer" and env.calls == []


def test_hints_and_reference_are_explicit_facts_and_exposure_survives_retry(env):
    created = start(env)
    path = BASE + f"/attempts/{created['attempt_id']}"
    hint = env.client.post(path + "/hint", json={"expected_revision": created["revision"]}).json()
    assert hint["content"] == "先核对条件。" and len(hint["attempt"]["revealed_hints"]) == 1
    solution = env.client.post(path + "/solution", json={"expected_revision": hint["attempt"]["revision"]}).json()
    assert solution["content"] == "隐含解答-secret" and solution["attempt"]["solution_revealed"]
    graded = submit(env, solution["attempt"])
    correction = start(env, intent="correction", origin_attempt_id=graded["attempt_id"], request_id="practice-correct-001")
    assert correction["answer_payload"] == graded["submitted_answer_payload"]
    assert correction["solution_revealed"] and correction["origin_attempt_id"] == graded["attempt_id"]
    retry = start(env, intent="retry", origin_attempt_id=graded["attempt_id"], request_id="practice-retry-00001")
    assert retry["answer_payload"] == {"text": ""} and retry["solution_revealed"]
    assert env.attempts.get("student", "personal-material:m", graded["attempt_id"])["submitted_answer_payload"] == {"text": "我的原始答案"}
    assert {e["event_type"] for e in env.events} >= {"personal_practice_hint_viewed", "personal_practice_solution_viewed"}


def test_review_never_overrides_verdict_or_original_and_is_revision_checked(env):
    graded = submit(env, start(env))
    path = BASE + f"/attempts/{graded['attempt_id']}/review"
    response = env.client.put(path, json={"expected_revision": graded["revision"], "error_type": "condition", "reflection": "漏看了适用条件", "state": "corrected"})
    assert response.status_code == 200
    reviewed = response.json()
    assert reviewed["metadata"]["review"]["state"] == "corrected" and reviewed["metadata"]["review_updated"]
    assert reviewed["result"] == graded["result"] and reviewed["submitted_answer_payload"] == graded["submitted_answer_payload"]
    assert env.client.put(path, json={"expected_revision": graded["revision"], "reflection": "迟到覆盖"}).status_code == 409


def test_updated_question_blocks_old_attempt_even_when_material_revision_id_is_same(env):
    created = start(env)
    material = env.repo.get("student", "m")
    material["revisions"][0]["sections"][0]["blocks"][2]["content"] = "修订答案"
    env.repo.update("student", "m", {"revisions": material["revisions"]})
    listing = env.client.get(BASE).json()
    assert listing["attempts"][0]["can_continue"] is False
    assert listing["questions"][0]["question_revision_id"] != created["question_revision_id"]
    assert env.client.post(BASE + "/attempts", json={"revision_id": "r", "question_id": listing["questions"][0]["question_id"],
                                                    "request_id": "practice-create-0001"}).status_code == 409
    path = BASE + f"/attempts/{created['attempt_id']}"
    assert env.client.put(path + "/draft", json={"expected_revision": 1, "answer": "不覆盖旧题"}).status_code == 409
    old_solution = env.client.post(path + "/solution", json={"expected_revision": 1})
    assert old_solution.status_code == 200 and old_solution.json()["content"] == "隐含解答-secret"


def test_old_revision_remains_readable_reviewable_but_not_repeatable(env):
    graded = submit(env, start(env))
    material = env.repo.get("student", "m")
    revised = deepcopy(material["revisions"][0])
    revised["id"] = "r2"
    env.repo.update("student", "m", {"revisions": [*material["revisions"], revised]})
    listing = env.client.get(BASE).json()
    assert listing["revision_id"] == "r2" and not listing["attempts"][0]["can_continue"]
    path = BASE + f"/attempts/{graded['attempt_id']}"
    assert env.client.put(path + "/review", json={"expected_revision": graded["revision"], "reflection": "旧答案反思"}).status_code == 200
    assert env.client.post(path + "/grade", json={"expected_revision": graded["revision"]}).status_code == 409


def test_revoked_source_permission_blocks_all_practice_access(env, monkeypatch):
    created = start(env)
    material = env.repo.get("student", "m")
    env.repo.update("student", "m", {"request": {"source_sections": [{"course_origin": {"course_id": "teacher-course"}}]}})
    def denied(*args):
        raise KeyError("revoked")
    monkeypatch.setattr(env.repo, "require_origin_access", denied)
    assert env.client.get(BASE).status_code == 404
    assert env.client.post(BASE + f"/attempts/{created['attempt_id']}/solution", json={"expected_revision": 1}).status_code == 404


def test_failed_evaluation_keeps_answer_and_only_retries_when_requested(env, monkeypatch):
    calls = []
    async def failed(*args):
        calls.append(1)
        raise RuntimeError("provider failure")
    monkeypatch.setattr(practice.PersonalPracticeGrader, "grade", failed)
    graded = submit(env, start(env))
    assert len(calls) == 1 and graded["result"]["reason"] == "evaluation_unavailable"
    assert env.client.get(BASE).json()["attempts"][0]["submitted_answer_payload"]["text"] == "我的原始答案"
    assert len(calls) == 1
    response = env.client.post(BASE + f"/attempts/{graded['attempt_id']}/grade", json={"expected_revision": graded["revision"]})
    assert response.status_code == 200 and len(calls) == 2


def test_grading_claim_blocks_concurrent_evaluation_and_keeps_reflection(env):
    created = start(env)
    submitted, _ = env.attempts.submit("student", "personal-material:m", created["attempt_id"], expected_revision=1,
                                     request_id="direct-submit", answer_payload={"text": "原答"}, active_seconds=0)
    claimed = env.attempts.claim_grading("student", "personal-material:m", created["attempt_id"], expected_revision=submitted["revision"], claim_id="one")
    response = env.client.post(BASE + f"/attempts/{created['attempt_id']}/grade", json={"expected_revision": claimed["revision"]})
    assert response.status_code == 409 and env.calls == []
    reviewed = env.attempts.update_review("student", "personal-material:m", created["attempt_id"], expected_revision=claimed["revision"], review={"reflection": "保留"})
    finished = env.attempts.finish_claimed_grade("student", "personal-material:m", created["attempt_id"], claim_id="one", result={"status": "graded", "passed": False})
    assert finished["metadata"]["review"] == reviewed["metadata"]["review"]


def expire_claim(repo, attempt):
    return repo._update("student", "personal-material:m", attempt["attempt_id"],
                        expected_revision=attempt["revision"], allowed_statuses={"grading"},
                        mutate=lambda item: item["grading_claim"].update(expires_at=0))


def test_restart_preserves_submission_and_expired_claim_requires_explicit_resume(env, monkeypatch):
    created = start(env)
    submitted, _ = env.attempts.submit("student", "personal-material:m", created["attempt_id"], expected_revision=1,
                                     request_id="durable-submit", answer_payload={"text": "重启前原答"}, active_seconds=0)
    claimed = env.attempts.claim_grading("student", "personal-material:m", created["attempt_id"],
                                       expected_revision=submitted["revision"], claim_id="old-worker")
    restarted = PracticeAttemptRepository(env.attempts.root)
    monkeypatch.setattr(practice, "practice_attempt_repository", restarted)
    current = env.client.get(BASE).json()["attempts"][0]
    assert current["grading_state"] == "running" and not current["can_request_grade"]
    assert 0 < current["grading_retry_after_seconds"] <= 120 and "grading_claim" not in current
    path = BASE + f"/attempts/{created['attempt_id']}/grade"
    assert env.client.post(path, json={"expected_revision": current["revision"]}).status_code == 409
    assert env.calls == []
    expired = expire_claim(restarted, claimed)
    recovered = env.client.get(BASE).json()["attempts"][0]
    assert recovered["grading_state"] == "interrupted" and recovered["can_request_grade"]
    assert recovered["submitted_answer_payload"] == {"text": "重启前原答"} and env.calls == []
    response = env.client.post(path, json={"expected_revision": expired["revision"]})
    assert response.status_code == 200, response.text
    assert response.json()["grading_state"] == "complete" and len(env.calls) == 1
    assert response.json()["submitted_answer_payload"] == {"text": "重启前原答"}
    with pytest.raises(AttemptConflict):
        restarted.finish_claimed_grade("student", "personal-material:m", created["attempt_id"],
                                       claim_id="old-worker", result={"status": "graded", "passed": True})
    assert env.client.get(BASE).json()["attempts"][0]["result"]["passed"] is False


def test_cancelled_grade_has_bounded_recovery_without_get_or_replay_retry(env, monkeypatch):
    created = start(env)
    submitted, _ = env.attempts.submit("student", "personal-material:m", created["attempt_id"], expected_revision=1,
                                     request_id="cancelled-submit", answer_payload={"text": "取消时的原答"}, active_seconds=0)
    async def cancelled(*args):
        raise asyncio.CancelledError()
    monkeypatch.setattr(practice.PersonalPracticeGrader, "grade", cancelled)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(practice._grade("student", "m", submitted, submitted["revision"]))
    stored = env.attempts.get("student", "personal-material:m", created["attempt_id"])
    assert stored["status"] == "grading" and stored["grading_claim"]["id"]
    assert stored["submitted_answer_payload"] == {"text": "取消时的原答"}
    expired = expire_claim(env.attempts, stored)
    assert env.client.get(BASE).json()["attempts"][0]["can_request_grade"] is True
    replay = env.client.post(BASE + f"/attempts/{created['attempt_id']}/submit", json={
        "expected_revision": 1, "request_id": "cancelled-submit", "answer": "取消时的原答"})
    assert replay.status_code == 200 and replay.json()["revision"] == expired["revision"]
    assert replay.json()["grading_state"] == "interrupted" and env.calls == []


def test_expired_worker_cannot_replace_new_claim_before_it_finishes(env):
    created = start(env)
    submitted, _ = env.attempts.submit("student", "personal-material:m", created["attempt_id"], expected_revision=1,
                                     request_id="claim-submit", answer_payload={"text": "原答"}, active_seconds=0)
    old = env.attempts.claim_grading("student", "personal-material:m", created["attempt_id"],
                                   expected_revision=submitted["revision"], claim_id="old")
    expired = expire_claim(env.attempts, old)
    replacement = env.attempts.claim_grading("student", "personal-material:m", created["attempt_id"],
                                            expected_revision=expired["revision"], claim_id="replacement")
    with pytest.raises(AttemptConflict):
        env.attempts.finish_claimed_grade("student", "personal-material:m", created["attempt_id"],
                                         claim_id="old", result={"status": "graded", "passed": True})
    assert env.attempts.get("student", "personal-material:m", created["attempt_id"])["revision"] == replacement["revision"]


def test_fold_parser_preserves_question_and_hides_nested_or_unclosed_details():
    prompt, hints, solutions = practice._split_content("题干 $x < y$\n<details><summary>解答</summary>答案<details><summary>推导</summary>细节</details></details>末尾")
    assert prompt == "题干 $x < y$\n末尾" and "答案" in solutions[0] and hints == []
    assert practice._split_content("题干<details><summary>解答</summary>半个答案")[0] == "题干"
    code = "解释此代码：\n```html\n<details><summary>答案</summary>示例元素</details>\n```\n以及 `<details>` 的作用。"
    assert practice._split_content(code) == (code, [], [])


def test_personal_grader_pins_approved_model_and_one_call(monkeypatch):
    from ai_base import AIBase
    calls = []
    async def call(_self, prompt, **kw):
        calls.append((prompt, kw))
        return '{"score":90,"confidence":0.9,"passed":true,"feedback":"Checked against the reference."}'
    monkeypatch.setattr(AIBase, "_call_llm", call)
    grader = practice.PersonalPracticeGrader("en")
    asyncio.run(grader._call_llm("concise Chinese feedback", retry_count=8))
    assert grader.smart_models == ["qwen3.8-27b"]
    assert grader._supports_stream_usage() is False and calls[0][1]["json_mode"] is False
    assert len(calls) == 1 and calls[0][1]["retry_count"] == calls[0][1]["max_attempts"] == 1
    assert "English" in calls[0][0] and calls[0][1]["require_stop"]


@pytest.mark.parametrize("bad", ['{"score":90,"confidence":0.9,"passed":"true","feedback":"ok"}',
                                  '{"score":"96s","confidence":0.9,"passed":true,"feedback":"ok"}',
                                  '{"score":101,"confidence":0.9,"passed":true,"feedback":"ok"}'])
def test_personal_grader_rejects_malformed_judgements(monkeypatch, bad):
    from ai_base import AIBase
    async def call(*args, **kwargs):
        return bad
    monkeypatch.setattr(AIBase, "_call_llm", call)
    with pytest.raises(ValueError, match="unreliable_evaluation"):
        asyncio.run(practice.PersonalPracticeGrader()._call_llm("data"))
