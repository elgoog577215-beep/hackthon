from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from course_document import COURSE_DOCUMENT_SCHEMA, document_from_legacy_course
from course_logic_upgrade import (
    CourseLogicUpgradeError,
    compile_course_logic_upgrade,
)
from course_repository import CourseDocumentRepository
from slide_story_plan import course_supports_slide_deck_v4
from teaching_representations import TeachingRepresentationRepository


class MemoryStorage:
    def __init__(self, course: dict) -> None:
        self.course = deepcopy(course)
        self.save_count = 0

    def load_course(self, _course_id: str) -> dict:
        return deepcopy(self.course)

    async def save_course(self, _course_id: str, data: dict) -> None:
        self.course = deepcopy(data)
        self.save_count += 1


def migrated_course_missing_logic() -> dict:
    legacy = {
        "course_id": "course-legacy-logic",
        "course_name": "热力学与统计物理",
        "nodes": [
            {
                "node_id": "chapter-1",
                "parent_node_id": "root",
                "node_name": "热力学基础",
                "node_level": 1,
                "learning_objective": "建立热力学状态与过程的整体认识",
                "node_content": "# 热力学基础",
            },
            {
                "node_id": "section-1",
                "parent_node_id": "chapter-1",
                "node_name": "热力学第一定律",
                "node_level": 2,
                "learning_objective": "能够用热力学第一定律分析封闭系统的能量变化",
                "objective_id": "objective-first-law",
                "node_content": (
                    "## 热力学第一定律\n\n"
                    "封闭系统中的能量守恒可写成 ΔU = Q + W。"
                    "应用时需要先确定系统边界和功、热量的符号约定。\n\n"
                    "## 例题\n\n分析绝热压缩过程中内能的变化。"
                ),
            },
        ],
    }
    document = document_from_legacy_course(legacy)
    return {
        "course_id": legacy["course_id"],
        "course_name": legacy["course_name"],
        "course_schema_version": COURSE_DOCUMENT_SCHEMA,
        "course_document": document.model_dump(mode="json"),
        "course_document_revision": document.document_revision,
        "course_document_authoritative": True,
        "current_course_version_id": document.document_revision,
        "course_operation_log": [],
        "generation_stage_artifacts": {},
    }


def test_upgrade_course_logic_unlocks_v4_without_rewriting_document(
    tmp_path,
    monkeypatch,
):
    from routers import teaching_representations as representation_router

    course = migrated_course_missing_logic()
    original_document = deepcopy(course["course_document"])
    storage = MemoryStorage(course)
    course_repository = CourseDocumentRepository(storage)
    representation_repository = TeachingRepresentationRepository(
        tmp_path / "representations"
    )

    monkeypatch.setattr(
        representation_router,
        "get_course_document_repository",
        lambda: course_repository,
    )
    monkeypatch.setattr(
        representation_router,
        "get_teaching_representation_repository",
        lambda: representation_repository,
    )

    async def existing_course(course_id: str):
        return course_repository.load_course_view(course_id)

    monkeypatch.setattr(
        representation_router,
        "get_course_or_404",
        existing_course,
    )
    app = FastAPI()
    app.include_router(representation_router.router, prefix="/api")
    client = TestClient(app)
    headers = {"X-User-Id": "teacher-1"}

    before = client.get(
        "/api/courses/course-legacy-logic/teaching-representations",
        headers=headers,
    )
    assert before.status_code == 200
    assert before.json()["registry"]["slide_deck_target_schema"] == "blocked"

    response = client.post(
        "/api/courses/course-legacy-logic/"
        "teaching-representations/course-logic/upgrade",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["already_ready"] is False
    assert payload["registry"]["slide_deck_target_schema"] == "slide_deck_v5"
    assert course_supports_slide_deck_v4(
        course_repository.load_course_view("course-legacy-logic")
    )
    assert storage.course["course_document"] == original_document
    assert storage.course["course_document_revision"] == original_document[
        "document_revision"
    ]
    assert storage.course["course_teaching_plan"]["sections"]
    assert storage.course["course_knowledge_base"]["lifecycle_status"] == "active"
    assert storage.course["course_coherence_contract"]["status"] == "active"
    assert payload["summary"]["recovered_section_count"] == 1
    assert storage.save_count == 1

    repeated = client.post(
        "/api/courses/course-legacy-logic/"
        "teaching-representations/course-logic/upgrade",
        headers=headers,
    )

    assert repeated.status_code == 200
    assert repeated.json()["already_ready"] is True
    assert storage.save_count == 1


def test_upgrade_rejects_missing_semantics_without_mutating_input():
    course = migrated_course_missing_logic()
    section = next(
        item
        for item in course["course_document"]["sections"]
        if item["section_id"] == "section-1"
    )
    section["attributes"]["knowledge_structure"] = []
    course["course_document"]["blocks"] = []
    before = deepcopy(course)
    repository = CourseDocumentRepository(MemoryStorage(course))

    with pytest.raises(
        CourseLogicUpgradeError,
        match="既没有结构化知识点",
    ):
        compile_course_logic_upgrade(
            repository.load_course_view("course-legacy-logic")
        )

    assert course == before


def test_upgrade_recovers_missing_objective_from_existing_section_summary():
    course = migrated_course_missing_logic()
    section = next(
        item
        for item in course["course_document"]["sections"]
        if item["section_id"] == "section-1"
    )
    section["learning_objective"] = ""
    for block in course["course_document"]["blocks"]:
        if block["section_id"] == "section-1":
            block["payload"]["markdown"] = (
                "封闭系统中的能量守恒可写成 ΔU = Q + W。"
                "应用时需要先确定系统边界和功、热量的符号约定。"
                "本节介绍了热力学第一定律及其在封闭系统能量分析中的应用。"
            )
    before = deepcopy(course)
    repository = CourseDocumentRepository(MemoryStorage(course))

    result = compile_course_logic_upgrade(
        repository.load_course_view("course-legacy-logic")
    )

    assert result["already_ready"] is False
    assert result["summary"]["recovered_section_count"] == 1
    contracts = result["updates"]["course_coherence_contract"][
        "section_contracts"
    ]
    assert contracts[0]["learning_objective"] == (
        "能够说明热力学第一定律及其在封闭系统能量分析中的应用"
    )
    assert course == before
