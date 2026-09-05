import tempfile
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from course_companion_documents import (
    CompanionDocumentError,
    CompanionDocumentRepository,
    compile_document,
    export_document,
    list_templates,
)
from routers import companion_documents as companion_router


def _course():
    return {
        "course_id": "course-1",
        "course_name": "设计思维与创新设计",
        "academic_year": "2026-2027",
        "term": "春夏",
        "course_profile": {
            "course_code": "DES101",
            "course_category": "通识课",
        },
    }


def test_known_teacher_samples_become_two_companion_templates():
    templates = list_templates(_course())

    assert [item["template_id"] for item in templates] == [
        "zju-grading-rubric-v1",
        "zju-exam-course-material-checklist-v1",
    ]
    rubric = templates[0]
    checklist = templates[1]
    assert rubric["default_inputs"]["course_name"] == "设计思维与创新设计"
    assert sum(item["weight"] for item in rubric["default_inputs"]["components"]) == 100
    assert checklist["default_inputs"]["course_code"] == "DES101"
    assert len(checklist["default_inputs"]["items"]) == 13
    assert all(item["completed"] is False for item in checklist["default_inputs"]["items"])


def test_grading_rubric_rejects_weight_total_other_than_one_hundred():
    inputs = list_templates(_course())[0]["default_inputs"]
    inputs["components"][0]["weight"] = 19

    with pytest.raises(CompanionDocumentError, match="合计必须为100%"):
        compile_document("zju-grading-rubric-v1", inputs, _course())


def test_companion_document_revisions_are_idempotent_and_editable():
    repository = CompanionDocumentRepository(Path(tempfile.mkdtemp()))
    inputs = list_templates(_course())[0]["default_inputs"]
    compiled = compile_document("zju-grading-rubric-v1", inputs, _course())

    first = repository.save_revision(
        course_id="course-1",
        actor_id="teacher-a",
        compiled=compiled,
    )
    duplicate = repository.save_revision(
        course_id="course-1",
        actor_id="teacher-a",
        compiled=compiled,
    )
    inputs["teacher_name"] = "张老师"
    revised = repository.save_revision(
        course_id="course-1",
        actor_id="teacher-a",
        compiled=compile_document("zju-grading-rubric-v1", inputs, _course()),
    )

    assert duplicate["revision_id"] == first["revision_id"]
    assert revised["document_id"] == first["document_id"]
    assert revised["revision_number"] == 2
    assert repository.list_course("course-1") == [revised]


@pytest.mark.parametrize(
    ("template_id", "expected_text"),
    [
        ("zju-grading-rubric-v1", "课程成绩评定细则"),
        ("zju-exam-course-material-checklist-v1", "考试课程材料自查清单"),
    ],
)
def test_companion_documents_export_as_real_docx(template_id, expected_text):
    repository = CompanionDocumentRepository(Path(tempfile.mkdtemp()))
    template = next(item for item in list_templates(_course()) if item["template_id"] == template_id)
    document = repository.save_revision(
        course_id="course-1",
        actor_id="teacher-a",
        compiled=compile_document(template_id, template["default_inputs"], _course()),
    )

    payload, media_type, filename = export_document(document, "docx")

    assert payload.startswith(b"PK")
    assert media_type.endswith("document")
    assert filename.endswith(".docx")
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    assert expected_text in xml


def test_companion_document_api_lists_generates_and_exports(monkeypatch, tmp_path):
    repository = CompanionDocumentRepository(tmp_path)

    async def get_course(course_id: str):
        assert course_id == "course-1"
        return _course()

    monkeypatch.setattr(companion_router, "companion_document_repository", repository)
    monkeypatch.setattr(companion_router, "get_course_or_404", get_course)
    app = FastAPI()
    app.include_router(companion_router.router, prefix="/api")
    client = TestClient(app, headers={"X-User-Id": "teacher-a"})

    listing = client.get("/api/courses/course-1/companion-documents")
    assert listing.status_code == 200
    template = listing.json()["templates"][0]

    generated = client.post(
        f"/api/courses/course-1/companion-documents/{template['template_id']}/generate",
        json={"inputs": template["default_inputs"]},
    )
    assert generated.status_code == 200
    document = generated.json()
    assert document["revision_number"] == 1

    exported = client.get(
        f"/api/courses/course-1/companion-documents/{document['document_id']}/export",
        params={"format": "docx"},
    )
    assert exported.status_code == 200
    assert exported.content.startswith(b"PK")
