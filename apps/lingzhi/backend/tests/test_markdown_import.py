from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from course_document import COURSE_DOCUMENT_SCHEMA, CourseDocument
from course_repository import CourseDocumentRepository
from representation_compiler import export_slide_deck_pptx
from storage import Storage
from teaching_representations import (
    TeachingRepresentationRepository,
    TeachingRepresentationSpec,
)


class ImportRepositoryProbe:
    def __init__(self) -> None:
        self.call_count = 0

    async def create_imported_course(self, course_id: str, *, imported_course: dict):
        self.call_count += 1


def make_import_client(monkeypatch) -> tuple[TestClient, ImportRepositoryProbe]:
    from routers import markdown_import as import_router

    repository = ImportRepositoryProbe()
    monkeypatch.setattr(
        import_router,
        "get_course_document_repository",
        lambda: repository,
        raising=False,
    )
    app = FastAPI()
    app.include_router(import_router.router)
    return TestClient(app), repository


def test_markdown_import_rejects_empty_file(monkeypatch):
    client, repository = make_import_client(monkeypatch)

    response = client.post(
        "/api/import_markdown",
        files={"file": ("empty.md", b"", "text/markdown")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "上传的文件为空"
    assert repository.call_count == 0


def test_markdown_import_rejects_text_without_a_heading(monkeypatch):
    client, repository = make_import_client(monkeypatch)

    response = client.post(
        "/api/import_markdown",
        files={"file": ("notes.md", "只有正文，没有标题。", "text/markdown")},
    )

    assert response.status_code == 422
    assert "至少一个 # 标题" in response.json()["detail"]
    assert repository.call_count == 0


def test_markdown_import_rejects_title_without_teachable_body(monkeypatch):
    client, repository = make_import_client(monkeypatch)

    response = client.post(
        "/api/import_markdown",
        files={"file": ("title-only.md", "# 只有课程标题\n", "text/markdown")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "课程至少需要一段可讲授正文，不能只有标题或层级"
    assert repository.call_count == 0


def test_markdown_import_rejects_heading_hierarchy_without_teachable_body(monkeypatch):
    client, repository = make_import_client(monkeypatch)

    response = client.post(
        "/api/import_markdown",
        files={
            "file": (
                "headings-only.md",
                "# 课程\n\n## 第一章\n\n### 第一节\n",
                "text/markdown",
            ),
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "课程至少需要一段可讲授正文，不能只有标题或层级"
    assert repository.call_count == 0


def test_markdown_import_persists_canonical_course_that_compiles_representations(
    tmp_path,
    monkeypatch,
):
    from routers import markdown_import as import_router
    from routers import teaching_representations as representations_router

    monkeypatch.setattr(Storage, "_auto_sync_loop", lambda _self: None)
    storage = Storage(str(tmp_path / "storage"))
    course_repository = CourseDocumentRepository(storage)
    representation_repository = TeachingRepresentationRepository(tmp_path / "representations")

    class CanonicalImportRepositoryProbe:
        def __init__(self) -> None:
            self.call_count = 0

        async def create_imported_course(self, course_id: str, *, imported_course: dict):
            self.call_count += 1
            return await course_repository.create_imported_course(
                course_id,
                imported_course=imported_course,
            )

    import_repository = CanonicalImportRepositoryProbe()

    monkeypatch.setattr(
        import_router,
        "get_course_document_repository",
        lambda: import_repository,
        raising=False,
    )
    monkeypatch.setattr(
        representations_router,
        "get_course_document_repository",
        lambda: course_repository,
    )
    monkeypatch.setattr(
        representations_router,
        "get_teaching_representation_repository",
        lambda: representation_repository,
    )

    async def get_course_or_404(course_id: str) -> dict:
        return course_repository.load_course_view(course_id)

    monkeypatch.setattr(representations_router, "get_course_or_404", get_course_or_404)

    app = FastAPI()
    app.include_router(import_router.router)
    app.include_router(representations_router.router, prefix="/api")
    client = TestClient(app)

    imported = client.post(
        "/api/import_markdown",
        files={
            "file": (
                "linear-algebra.md",
                "# Linear Algebra\n\nVectors have magnitude and direction.\n",
                "text/markdown",
            ),
        },
    )

    assert imported.status_code == 200
    response = imported.json()
    assert response == {
        "course_id": response["course_id"],
        "course_name": "Linear Algebra",
    }
    assert import_repository.call_count == 1

    compiled = client.post(
        f"/api/courses/{response['course_id']}/teaching-representations/build",
        headers={"X-User-Id": "demo-user"},
    )

    assert compiled.status_code == 200, compiled.json()
    payload = compiled.json()
    assert payload["status"] == "success"
    assert payload["build"]["status"] == "synchronized", payload["build"]
    assert payload["build"]["quality"]["passed"] is True
    assert payload["quality"]["passed"] is True

    registry = payload["registry"]
    slide_deck = next(
        item
        for item in registry["representations"]
        if item["representation_type"] == "slide_deck"
    )
    assert slide_deck["status"] == "ready"
    slide_spec = next(
        item for item in registry["specs"]
        if item["spec_id"] == slide_deck["spec_id"]
    )
    pptx_path = export_slide_deck_pptx(
        TeachingRepresentationSpec.model_validate(slide_spec),
        tmp_path / "imported-course.pptx",
    )
    assert pptx_path.read_bytes().startswith(b"PK")
    assert pptx_path.stat().st_size > 0

    raw = storage.load_course(response["course_id"])
    assert raw is not None
    assert raw["course_schema_version"] == COURSE_DOCUMENT_SCHEMA
    assert raw["course_document_authoritative"] is True
    assert raw["learning_assets"]["questions"] == []
    assert "nodes" not in raw
    document = CourseDocument.model_validate(raw["course_document"])
    assert any(section.learning_objective for section in document.sections)
    assert (tmp_path / "storage" / "courses" / f"{response['course_id']}.json").is_file()
