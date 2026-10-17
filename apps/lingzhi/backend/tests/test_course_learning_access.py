from copy import deepcopy

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from course_access import CourseOwnershipMiddleware
from course_document import CourseBlock, CourseDocument, CourseSection, refresh_document_revision
from course_learning_access import CourseLearningAccess, learner_api_allowed
from course_learning_projection import public_course, public_envelope
from routers import course_learning_access as api
from storage import Storage
from study.auth import LocalStudyAuth
from study.identity_middleware import LocalStudyIdentityMiddleware


@pytest.fixture
def setup_access(tmp_path, monkeypatch):
    monkeypatch.setenv("LINGZHI_LOCAL_STUDY_AUTH", "true")
    monkeypatch.delenv("QIZHI_AUTH_VERIFY_URL", raising=False)
    store = Storage(str(tmp_path / "data"))
    document = refresh_document_revision(
        CourseDocument(
            course_id="course",
            title="Shared course",
            sections=[CourseSection(section_id="lecture", title="Lecture", position=0, level=1)],
            blocks=[
                CourseBlock(
                    block_id="public",
                    section_id="lecture",
                    position=0,
                    payload={"markdown": "Public content", "private_note": "SECRET"},
                ),
                CourseBlock(
                    block_id="private",
                    section_id="lecture",
                    position=1,
                    payload={"markdown": "SECRET"},
                    visibility_rule={"audience": "teacher"},
                ),
            ],
        )
    )
    course = {
        "course_id": "course",
        "course_name": "Shared course",
        "owner_id": "teacher",
        "authoring_surface": "teacher",
        "course_document": document.model_dump(mode="json"),
        "current_course_version_id": document.document_revision,
        "course_profile": {"private": "SECRET"},
    }
    store.save_course_sync("course", course)
    monkeypatch.setattr(api, "storage", store)
    from routers import study
    from study.repository import StudyRepository

    monkeypatch.setattr(study, "storage", store)

    async def read_course(course_id):
        return deepcopy(course)

    monkeypatch.setattr(api, "get_course_or_404", read_course)
    first = LocalStudyAuth(store).login("student_a", "Testing2026!", register=True)
    second = LocalStudyAuth(store).login("student_b", "Testing2026!", register=True)
    app = FastAPI()
    app.include_router(api.router, prefix="/api")
    app.include_router(study.router, prefix="/api")
    from routers import practice, learning_assets

    app.include_router(practice.router, prefix="/api")
    app.include_router(learning_assets.router, prefix="/api")
    monkeypatch.setattr(practice, "get_course_or_404", read_course)
    monkeypatch.setattr(learning_assets, "get_course_or_404", read_course)
    app.dependency_overrides[study.repository] = lambda: StudyRepository(store)
    app.add_middleware(CourseOwnershipMiddleware, course_storage=store)
    app.add_middleware(LocalStudyIdentityMiddleware, course_storage=store)

    @app.get("/api/courses/{course_id}/document")
    def document_view(course_id):
        return public_envelope(course)

    @app.post("/api/courses/{course_id}/practice/fact")
    def fact(course_id, request: Request):
        return {"user_id": request.headers["X-User-Id"]}

    @app.get("/api/courses/{course_id}/diagnostics/active")
    def active_diagnostic(course_id, request: Request):
        return {"user_id": request.headers["X-User-Id"]}

    @app.post("/api/ask_events")
    def ask():
        return {"ok": True}

    @app.post("/api/courses/{course_id}/lesson-authoring")
    def author(course_id):
        return {"should_not_reach": True}

    return TestClient(app), store, course, first, second


def bearer(account):
    return {"Authorization": "Bearer " + account["token"]}


def test_student_practice_can_read_only_own_active_diagnostic(setup_access):
    client, store, course, first, second = setup_access
    CourseLearningAccess(store).grant(course, first["user"]["id"])
    path = "/api/courses/course/diagnostics/active"
    assert learner_api_allowed(path, "GET")
    response = client.get(path, headers={**bearer(first), "X-User-Id": second["user"]["id"]})
    assert response.status_code == 200
    assert response.json()["user_id"] == first["user"]["id"]
    assert client.get(path, headers=bearer(second)).status_code == 404
    assert not learner_api_allowed(path, "POST")
    assert not learner_api_allowed("/api/courses/course/diagnostics/private", "GET")


def test_owner_grants_registered_account_without_changing_course(setup_access):
    client, store, course, first, _ = setup_access
    before = store.load_course("course")
    assert (
        client.post(
            "/api/teacher/courses/course/learners",
            json={"local_username": "student_a"},
            headers={"X-User-Id": "foreign"},
        ).status_code
        == 404
    )
    response = client.post(
        "/api/teacher/courses/course/learners", json={"local_username": "student_a"}, headers={"X-User-Id": "teacher"}
    )
    assert response.status_code == 200
    assert response.json()["learner_id"] == first["user"]["id"]
    repeated = client.post(
        "/api/teacher/courses/course/learners", json={"local_username": "student_a"}, headers={"X-User-Id": "teacher"}
    )
    assert repeated.json()["grant_id"] == response.json()["grant_id"]
    assert store.load_course("course") == before


def test_granted_student_reads_public_content_and_only_own_records(setup_access):
    client, store, course, first, second = setup_access
    CourseLearningAccess(store).grant(course, first["user"]["id"])
    assert len(client.get("/api/study/courses", headers=bearer(first)).json()) == 1
    assert client.get("/api/study/courses", headers=bearer(second)).json() == []
    response = client.get("/api/courses/course/document", headers=bearer(first))
    assert response.status_code == 200
    assert "SECRET" not in response.text
    forged = {**bearer(first), "X-User-Id": second["user"]["id"]}
    fact = client.post("/api/courses/course/practice/fact", headers=forged)
    assert fact.json()["user_id"] == first["user"]["id"]
    assert client.post("/api/courses/course/practice/fact", headers=bearer(second)).status_code == 404
    assert client.post("/api/courses/course/lesson-authoring", headers=bearer(first)).status_code == 403
    assert client.get("/api/teacher/courses/course/learners", headers=bearer(first)).status_code == 403
    for action in ("accept", "undo", "adjust"):
        assert (
            client.post("/api/courses/course/personal-adaptation/plans/p/" + action, headers=bearer(first)).status_code
            == 403
        )


def test_revocation_closes_read_write_and_ai_without_deleting_facts(setup_access):
    client, store, course, first, _ = setup_access
    user_id = first["user"]["id"]
    access = CourseLearningAccess(store)
    access.grant(course, user_id)
    store.save_data("preserved_fact.json", {"user_id": user_id, "answer": "original"})
    assert client.post("/api/ask_events", json={"course_id": "course"}, headers=bearer(first)).status_code == 200
    revoked = client.delete("/api/teacher/courses/course/learners/" + user_id, headers={"X-User-Id": "teacher"})
    assert revoked.status_code == 200
    assert client.get("/api/courses/course/document", headers=bearer(first)).status_code == 404
    assert client.post("/api/courses/course/practice/fact", headers=bearer(first)).status_code == 404
    assert client.post("/api/ask_events", json={"course_id": "course"}, headers=bearer(first)).status_code == 404
    assert client.get("/api/study/courses", headers=bearer(first)).json() == []
    assert store.load_data("preserved_fact.json")["answer"] == "original"


def test_claimed_student_header_is_not_a_session(setup_access):
    client, _, _, first, _ = setup_access
    assert client.get("/api/courses/course/document", headers={"X-User-Id": first["user"]["id"]}).status_code == 401


def test_qizhi_student_bridge_consumes_grant_and_overwrites_claimed_actor(setup_access, monkeypatch):
    _, store, course, _, _ = setup_access
    from qizhi_auth import QizhiIdentityMiddleware, QizhiIdentityVerifier

    class VerifiedResponse:
        status_code = 200

        def json(self):
            return {"success": True, "data": {"id": "student-a", "role": "student"}}

    monkeypatch.setattr("qizhi_auth.requests.get", lambda *a, **kw: VerifiedResponse())
    CourseLearningAccess(store).grant(course, "qizhi:student-a")
    app = FastAPI()
    app.add_middleware(CourseOwnershipMiddleware, course_storage=store)
    app.add_middleware(QizhiIdentityMiddleware, verifier=QizhiIdentityVerifier("http://identity/current"))

    @app.get("/api/courses/{course_id}/document")
    def document(course_id, request: Request):
        return {"actor": request.headers["X-User-Id"], "document": public_envelope(course)}

    @app.post("/api/courses/{course_id}/lesson-authoring")
    def production(course_id):
        return {"private": True}

    client = TestClient(app)
    headers = {"Authorization": "Bearer verified", "X-User-Id": "teacher"}
    read = client.get("/api/courses/course/document", headers=headers)
    assert read.status_code == 200 and read.json()["actor"] == "qizhi:student-a"
    assert "SECRET" not in read.text
    assert client.post("/api/courses/course/lesson-authoring", headers=headers).status_code == 403
    CourseLearningAccess(store).revoke("course", "qizhi:student-a")
    assert client.get("/api/courses/course/document", headers=headers).status_code == 404


def test_authorized_source_preserves_revision_and_revocation_closes_download(setup_access):
    client, store, course, first, _ = setup_access
    from study.repository import StudyRepository

    access = CourseLearningAccess(store)
    owner = first["user"]["id"]
    access.grant(course, owner)
    url = "/api/study/courses/course/sources"
    assert client.post(url, json={"revision_id": "stale"}, headers=bearer(first)).status_code == 409
    source = client.post(url, json={"revision_id": course["current_course_version_id"]}, headers=bearer(first))
    assert source.status_code == 200, source.text
    source = source.json()
    assert source["course_origin"]["revision_id"] == course["current_course_version_id"]
    download_url = "/api/study/sources/" + source["id"] + "/download"
    download = client.get(download_url, headers=bearer(first))
    assert download.status_code == 200 and "SECRET" not in download.text
    repo = StudyRepository(store)
    material = {
        "id": "derived",
        "owner_id": owner,
        "request_key": "unique",
        "fingerprint": "frozen",
        "request": {"source_sections": [{"course_origin": source["course_origin"]}]},
        "updated_at": "now",
    }
    repo.reserve(owner, "unique", "frozen", material)
    assert repo.get(owner, "derived")["id"] == "derived"
    access.revoke("course", owner)
    assert client.get(download_url, headers=bearer(first)).status_code == 404
    with pytest.raises(KeyError):
        repo.get(owner, "derived")
    assert repo.ledger()["derived"]["fingerprint"] == "frozen"


def test_learning_path_uses_existing_fact_projection(setup_access, monkeypatch):
    client, store, course, first, _ = setup_access
    CourseLearningAccess(store).grant(course, first["user"]["id"])
    import learning_events, learning_progress, learning_continuation, practice_attempts
    from practice_attempts import PracticeAttemptRepository

    attempts = PracticeAttemptRepository(store._data_dir + "/practice_attempts")
    monkeypatch.setattr(learning_events, "storage", store)
    monkeypatch.setattr(learning_progress, "practice_attempt_repository", attempts)
    monkeypatch.setattr(learning_continuation, "practice_attempt_repository", attempts)
    monkeypatch.setattr(learning_continuation, "workflow_view", lambda *a, **kw: {})
    monkeypatch.setattr(learning_continuation.learning_record_repository, "list", lambda *a: [])
    monkeypatch.setattr(learning_continuation.learning_snapshot_repository, "load", lambda *a: {})
    result = client.get("/api/study/courses/course/path", headers=bearer(first))
    assert result.status_code == 200, result.text
    path = result.json()
    assert path["basis"] == "saved_learning_facts"
    assert len(path["steps"]) == 1 and path["steps"][0]["chapter_id"] == "lecture"
    assert path["attempt_count"] == 0
    assert path["unassessed_is_not_failure"] is True


def test_equal_bytes_do_not_merge_private_uploads_or_different_course_grants(setup_access, monkeypatch):
    import asyncio
    from study.repository import StudyRepository

    client, store, course, first, _ = setup_access
    owner = first["user"]["id"]
    repo = StudyRepository(store)
    private = asyncio.run(
        repo.sources(owner).create_text_asset(
            filename="My own.md", content="# Lecture\n\n" + public_course(course)["nodes"][0]["node_content"]
        )
    )
    access = CourseLearningAccess(store)
    access.grant(course, owner)

    async def read_course(course_id):
        return store.load_course(course_id)

    monkeypatch.setattr(api, "get_course_or_404", read_course)
    url = "/api/study/courses/course/sources"
    request = {"revision_id": course["current_course_version_id"]}
    first_source = client.post(url, json=request, headers=bearer(first)).json()
    repeated = client.post(url, json=request, headers=bearer(first)).json()
    assert first_source["id"] == repeated["id"] and first_source["id"] != private.asset_id
    other = deepcopy(course)
    other["course_id"] = "other"
    document = CourseDocument.model_validate(other["course_document"])
    document.course_id = "other"
    other["course_document"] = refresh_document_revision(document).model_dump(mode="json")
    other["current_course_version_id"] = other["course_document"]["document_revision"]
    store.save_course_sync("other", other)
    access.grant(other, owner)
    second_source = client.post(
        "/api/study/courses/other/sources",
        json={"revision_id": other["current_course_version_id"]},
        headers=bearer(first),
    ).json()
    assert second_source["sha256"] == first_source["sha256"] == private.sha256
    assert len({private.asset_id, first_source["id"], second_source["id"]}) == 3
    access.revoke("course", owner)
    for asset_id in (private.asset_id, second_source["id"]):
        assert client.get("/api/study/sources/" + asset_id + "/download", headers=bearer(first)).status_code == 200
    assert (
        client.get("/api/study/sources/" + first_source["id"] + "/download", headers=bearer(first)).status_code == 404
    )


def test_public_projection_removes_teacher_metadata_and_private_blocks(setup_access):
    _, _, course, _, _ = setup_access
    view = public_course(course)
    assert "SECRET" not in str(view)
    assert view["nodes"][0]["node_level"] == 1
    assert view["current_course_version_id"] == course["current_course_version_id"]


def test_authenticated_practice_wrong_retry_reopen_and_learning_path(setup_access, monkeypatch):
    """Real durable attempts and exact grader; diagnosis is explicitly unavailable."""
    client, store, course, first, second = setup_access
    import learning_events, learning_progress, learning_continuation, practice_attempts
    from practice_attempts import PracticeAttemptRepository
    from routers import practice, learning_assets
    from question_public_guard import assert_no_answer_leak

    course["nodes"] = public_course(course)["nodes"]
    course["learning_assets"] = {
        "questions": [
            {
                "asset_id": "question",
                "revision_id": "question-v1",
                "node_id": "lecture",
                "question_type": "short_answer",
                "prompt": "Name the disclosed topic.",
                "answer_spec": {"type": "exact", "correct_answer": "Public content", "pass_score": 70},
            }
        ],
        "mastery_criteria": [],
    }
    store.save_course_sync("course", course)
    CourseLearningAccess(store).grant(course, first["user"]["id"])
    path = store._data_dir + "/practice_attempts"
    attempts = PracticeAttemptRepository(path)
    monkeypatch.setattr(practice_attempts, "practice_attempt_repository", attempts)
    for module in (practice, learning_progress, learning_continuation):
        monkeypatch.setattr(module, "practice_attempt_repository", attempts)
    monkeypatch.setattr(learning_events, "storage", store)
    monkeypatch.setattr(practice, "_active_question_bank", lambda *a: None)
    monkeypatch.setattr(learning_assets, "load_active_question_bank", lambda *a, **kw: None)
    monkeypatch.setattr(practice.question_bank_rebuild_job_repository, "latest_for_course", lambda *a: None)
    monkeypatch.setattr(practice, "workflow_view", lambda *a, **kw: {})
    monkeypatch.setattr(practice, "advance_workflow_after_grade", lambda *a, **kw: {})
    monkeypatch.setattr(learning_continuation, "workflow_view", lambda *a, **kw: {})
    monkeypatch.setattr(learning_continuation.learning_record_repository, "list", lambda *a: [])
    monkeypatch.setattr(learning_continuation.learning_snapshot_repository, "load", lambda *a: {})

    class UnavailableDiagnosis:
        async def diagnose_answer(self, *args):
            raise RuntimeError("No diagnosis provider in deterministic regression")

    monkeypatch.setattr(practice, "practice_analysis_service", UnavailableDiagnosis())
    for endpoint in ("learning-assets", "learning-assets/practice", "practice?node_id=lecture"):
        response = client.get("/api/courses/course/" + endpoint, headers=bearer(first))
        assert response.status_code == 200, response.text
        assert_no_answer_leak(response.json())
    base = "/api/courses/course/practice"
    created = client.post(base + "/attempts", json={"task_revision_id": "question-v1"}, headers=bearer(first))
    assert created.status_code == 200, created.text
    original = created.json()["attempt"]
    in_progress = client.get("/api/study/courses/course/path", headers=bearer(first)).json()
    assert in_progress["next_action"]["action_type"] == "resume_practice_attempt"
    assert in_progress["attempt_count"] == 1

    def submit(attempt, answer, request_id):
        response = client.post(
            base + "/attempts/" + attempt["attempt_id"] + "/submit",
            json={
                "expected_revision": attempt["revision"],
                "answer_payload": {"text": answer},
                "active_seconds": 10,
                "request_id": request_id,
            },
            headers=bearer(first),
        )
        assert response.status_code == 200, response.text
        return response.json()["attempt"]

    wrong = submit(original, "Incorrect", "submit-wrong")
    assert wrong["result"]["passed"] is False
    mistakes = client.get(base + "/history?view=needs_review", headers=bearer(first)).json()
    assert [a["attempt_id"] for a in mistakes["attempts"]] == [original["attempt_id"]]
    retry_response = client.post(
        base + "/attempts",
        json={
            "task_revision_id": "question-v1",
            "resume": False,
            "practice_intent": "targeted_retry",
            "origin_attempt_id": original["attempt_id"],
        },
        headers=bearer(first),
    )
    assert retry_response.status_code == 200, retry_response.text
    retry = submit(retry_response.json()["attempt"], "Public content", "submit-retry")
    assert retry["result"]["passed"] is True
    assert client.get(base + "/history?view=needs_review", headers=bearer(first)).json()["attempts"] == []
    assert client.get(base + "/history", headers=bearer(second)).status_code == 404
    # Re-open the disk repository: facts and the original wrong answer survive.
    reopened = PracticeAttemptRepository(path)
    monkeypatch.setattr(practice_attempts, "practice_attempt_repository", reopened)
    assert len(reopened.list(first["user"]["id"], "course")) == 2
    assert reopened.get(first["user"]["id"], "course", original["attempt_id"])["result"]["passed"] is False
    for module in (practice, learning_progress, learning_continuation):
        monkeypatch.setattr(module, "practice_attempt_repository", reopened)
    restored = client.get("/api/study/courses/course/path", headers=bearer(first)).json()
    assert restored["attempt_count"] == 2
    assert restored["next_action"]["action_type"] != "resume_practice_attempt"
    events = learning_events.load_learning_events(user_id=first["user"]["id"], course_id="course")
    assert sum(e["event_type"] == "practice_attempt_graded" for e in events) == 2


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/courses/course/lesson-authoring", "GET"),
        ("/api/courses/course/knowledge-first/generate/tree", "POST"),
        ("/api/tasks/task/continue", "POST"),
        ("/api/teacher/courses", "GET"),
    ],
)
def test_student_role_never_opens_production_domains(path, method):
    assert not learner_api_allowed(path, method)
