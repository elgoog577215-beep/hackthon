from __future__ import annotations

from copy import deepcopy

from fastapi import FastAPI
from fastapi.testclient import TestClient

from question_bank import QuestionBankRepository, build_question_bank
from routers import question_bank


def _course() -> dict:
    return {
        "course_id": "course-teacher",
        "course_name": "史料阅读",
        "course_purpose": "systematic",
        "difficulty": "intermediate",
        "subject_pedagogy_profile": {
            "primary_mode": "humanities_social",
            "user_locked": True,
        },
        "generation_request": {
            "course_purpose": "systematic",
            "web_question_enrichment": {"enabled": False},
        },
        "material_bindings": [],
        "evidence_catalog": [],
        "nodes": [{
            "node_id": "history-1",
            "node_level": 2,
            "node_name": "工业革命史料",
            "node_content": (
                "材料一记录工厂劳动时间变化，材料二记录城市人口变化。"
                "学生需要引用两则材料并区分相关关系和因果关系。"
            ),
            "learning_objective": "依据两则史料形成因果论证",
            "key_points": ["史料证据", "因果论证"],
            "assessment": ["形成论点、证据、推理和限定"],
            "grounding_contract": {"question_evidence_ids": []},
        }],
    }


def _client(monkeypatch, tmp_path):
    repository = QuestionBankRepository(tmp_path / "banks")
    stored = repository.save_bundle(
        "course-teacher",
        build_question_bank(_course()),
    )

    async def get_course(course_id: str):
        return {**deepcopy(_course()), "course_id": course_id}

    monkeypatch.setattr(
        question_bank,
        "question_bank_repository",
        repository,
    )
    monkeypatch.setattr(
        question_bank,
        "get_course_or_404",
        get_course,
    )
    app = FastAPI()
    app.include_router(question_bank.router, prefix="/api")
    return TestClient(app), stored


def test_question_bank_management_requires_identity(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)

    denied = client.get(
        "/api/courses/course-teacher/question-bank"
    )
    allowed = client.get(
        "/api/courses/course-teacher/question-bank",
        headers={"X-User-Id": "teacher-1"},
    )

    assert denied.status_code == 400
    assert allowed.status_code == 200
    assert allowed.json()["assessment_profile"]["course_id"] == (
        "course-teacher"
    )


def test_teacher_can_load_private_solution_by_item_revision(
    monkeypatch,
    tmp_path,
):
    client, stored = _client(monkeypatch, tmp_path)
    item = next(
        item
        for item in stored["items"]
        if item.get("solution_revision_id")
    )

    response = client.get(
        (
            "/api/courses/course-teacher/question-bank/items/"
            f"{item['revision_id']}/solution"
        ),
        headers={"X-User-Id": "teacher-1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["solution_revision_id"] == item[
        "solution_revision_id"
    ]
    assert (
        payload["solution_envelope"].get("canonical_answer") is not None
        or payload["solution_envelope"].get("rubric")
    )
    assert payload["solution_validation"] == item[
        "solution_validation"
    ]
