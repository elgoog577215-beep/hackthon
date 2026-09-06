from __future__ import annotations

from copy import deepcopy

from fastapi import FastAPI
from fastapi.testclient import TestClient

from exam_papers import ExamPaperRepository
from routers import question_bank


class MemoryQuestionBankRepository:
    def __init__(self, bundle: dict):
        self.current_revision_id = str(bundle["bundle_revision_id"])
        self.revisions = {
            self.current_revision_id: deepcopy(bundle),
        }

    def load_bundle(
        self,
        course_id: str,
        bundle_revision_id: str | None = None,
    ) -> dict | None:
        assert course_id == "course-papers"
        revision_id = bundle_revision_id or self.current_revision_id
        value = self.revisions.get(revision_id)
        return deepcopy(value) if value else None


def _bundle() -> dict:
    return {
        "course_id": "course-papers",
        "bundle_revision_id": "bundle_v1",
        "items": [
            {
                "item_id": "item-1",
                "revision_id": "question-rev-1",
                "prompt": "解释设计思维中的共情。",
                "question_type": "short_answer",
                "node_id": "node-1",
                "lifecycle_status": "approved",
                "quality_report": {"passed": True},
            },
            {
                "item_id": "item-2",
                "revision_id": "question-rev-2",
                "prompt": "给出一个原型验证方案。",
                "question_type": "case_analysis",
                "node_id": "node-2",
                "lifecycle_status": "approved",
                "quality_report": {"passed": True},
            },
            {
                "item_id": "item-3",
                "revision_id": "question-rev-review",
                "prompt": "尚待审核的题目。",
                "question_type": "short_answer",
                "node_id": "node-2",
                "lifecycle_status": "needs_review",
                "quality_report": {"passed": True},
            },
        ],
    }


def _client(monkeypatch, tmp_path):
    bundle = _bundle()
    questions = MemoryQuestionBankRepository(bundle)

    async def get_course(course_id: str):
        return {"course_id": course_id, "course_name": "设计思维"}

    monkeypatch.setattr(
        question_bank,
        "get_course_or_404",
        get_course,
    )
    monkeypatch.setattr(
        question_bank,
        "question_bank_repository",
        questions,
    )
    monkeypatch.setattr(
        question_bank,
        "exam_paper_repository",
        ExamPaperRepository(tmp_path / "exam-papers"),
    )
    monkeypatch.setattr(
        question_bank,
        "_require_bundle",
        lambda _course: deepcopy(
            questions.revisions[questions.current_revision_id]
        ),
    )
    app = FastAPI()
    app.include_router(question_bank.router, prefix="/api")
    return TestClient(app), questions


def _create_payload(**overrides):
    return {
        "title": "期中测试卷",
        "duration_minutes": 90,
        "total_score": 100,
        "question_revision_ids": [
            "question-rev-1",
            "question-rev-2",
        ],
        "expected_bundle_revision_id": "bundle_v1",
        **overrides,
    }


def test_exam_paper_requires_teacher_identity(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)

    response = client.get(
        "/api/courses/course-papers/question-bank/exam-papers"
    )

    assert response.status_code == 400


def test_create_list_and_get_exam_paper(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)
    headers = {"X-User-Id": "teacher-1"}

    created = client.post(
        "/api/courses/course-papers/question-bank/exam-papers",
        headers=headers,
        json=_create_payload(),
    )

    assert created.status_code == 201
    paper = created.json()["paper"]
    assert paper["status"] == "draft"
    assert paper["item_count"] == 2
    assert paper["source_bundle_revision_id"] == "bundle_v1"
    assert sum(item["score"] for item in paper["questions"]) == 100
    assert [item["prompt"] for item in paper["questions"]] == [
        "解释设计思维中的共情。",
        "给出一个原型验证方案。",
    ]
    assert all("solution" not in item for item in paper["questions"])

    listed = client.get(
        "/api/courses/course-papers/question-bank/exam-papers",
        headers=headers,
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["papers"][0]["paper_id"] == paper["paper_id"]

    loaded = client.get(
        "/api/courses/course-papers/question-bank/"
        f"exam-papers/{paper['paper_id']}",
        headers=headers,
    )
    assert loaded.status_code == 200
    assert loaded.json()["paper"]["revision_id"] == paper["revision_id"]


def test_exam_paper_rejects_unapproved_questions(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)

    response = client.post(
        "/api/courses/course-papers/question-bank/exam-papers",
        headers={"X-User-Id": "teacher-1"},
        json=_create_payload(
            question_revision_ids=["question-rev-review"],
        ),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == (
        "exam_paper_questions_not_approved"
    )


def test_exam_paper_keeps_original_question_revision(monkeypatch, tmp_path):
    client, questions = _client(monkeypatch, tmp_path)
    headers = {"X-User-Id": "teacher-1"}
    created = client.post(
        "/api/courses/course-papers/question-bank/exam-papers",
        headers=headers,
        json=_create_payload(question_revision_ids=["question-rev-1"]),
    ).json()["paper"]
    questions.revisions["bundle_v2"] = {
        **_bundle(),
        "bundle_revision_id": "bundle_v2",
        "items": [{
            **_bundle()["items"][0],
            "revision_id": "question-rev-new",
            "prompt": "新版题目不应静默替换旧试卷。",
        }],
    }
    questions.current_revision_id = "bundle_v2"

    loaded = client.get(
        "/api/courses/course-papers/question-bank/"
        f"exam-papers/{created['paper_id']}",
        headers=headers,
    ).json()["paper"]

    assert loaded["source_bundle_revision_id"] == "bundle_v1"
    assert loaded["questions"][0]["question_revision_id"] == (
        "question-rev-1"
    )
    assert loaded["questions"][0]["prompt"] == (
        "解释设计思维中的共情。"
    )
