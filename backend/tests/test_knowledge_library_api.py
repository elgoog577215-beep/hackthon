from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import knowledge_libraries
from subject_library_service import SubjectLibraryVersionConflict, SubjectOntologyGenerationError


class _LibraryService:
    async def rebuild_course(self, course_id, *, force=False):
        return {
            "library": {"revision_id": "sklr_1", "lifecycle_status": "candidate"},
            "quality_report": {"passed": True},
            "binding": {"revision_id": "sklr_1"},
            "course_map": {"coverage": {"mapped_ratio": 1.0}},
            "reused_accepted": False,
        }

    def get_review(self, course_id):
        return {"library": {"revision_id": "sklr_1"}, "diff": {"added": 3, "modified": 1, "removed": 0}}

    async def review_course_library(self, course_id, *, revision_id, decision, note=""):
        if revision_id == "stale":
            raise SubjectLibraryVersionConflict("stale")
        return {"library": {"revision_id": revision_id, "lifecycle_status": "accepted"}}


class _MigrationService:
    def create_job(self):
        return {"job_id": "migration-1", "status": "pending"}

    def load_job(self, job_id):
        return {"job_id": job_id, "status": "completed", "completed_count": 2, "failed_count": 1}


def _client():
    app = FastAPI()
    app.include_router(knowledge_libraries.router, prefix="/api")
    app.dependency_overrides[knowledge_libraries.get_subject_library_service] = lambda: _LibraryService()
    app.dependency_overrides[knowledge_libraries.get_subject_library_migration_service] = lambda: _MigrationService()
    return TestClient(app)


def test_rebuild_review_and_accept_contracts():
    client = _client()

    rebuilt = client.post("/api/courses/course-1/knowledge-library/rebuild", json={"force": True})
    review = client.get("/api/courses/course-1/knowledge-library/review")
    accepted = client.post(
        "/api/courses/course-1/knowledge-library/review",
        json={"revision_id": "sklr_1", "decision": "accept", "note": "通过"},
    )
    stale = client.post(
        "/api/courses/course-1/knowledge-library/review",
        json={"revision_id": "stale", "decision": "accept"},
    )

    assert rebuilt.status_code == 200
    assert rebuilt.json()["library"]["lifecycle_status"] == "candidate"
    assert review.json()["diff"]["added"] == 3
    assert accepted.json()["library"]["lifecycle_status"] == "accepted"
    assert stale.status_code == 409


def test_migration_job_contracts():
    client = _client()

    created = client.post("/api/knowledge-libraries/migrations")
    status = client.get("/api/knowledge-libraries/migrations/migration-1")

    assert created.status_code == 202
    assert created.json()["job_id"] == "migration-1"
    assert status.json() == {
        "job_id": "migration-1",
        "status": "completed",
        "completed_count": 2,
        "failed_count": 1,
    }


def test_rebuild_exposes_retryable_provider_failure():
    class _FailingLibraryService(_LibraryService):
        async def rebuild_course(self, course_id, *, force=False):
            raise SubjectOntologyGenerationError(
                code="insufficient_quota",
                message="AI 服务额度不足，知识库未重新生成",
                retryable=True,
            )

    app = FastAPI()
    app.include_router(knowledge_libraries.router, prefix="/api")
    app.dependency_overrides[knowledge_libraries.get_subject_library_service] = lambda: _FailingLibraryService()
    client = TestClient(app)

    response = client.post("/api/courses/course-1/knowledge-library/rebuild", json={"force": True})

    assert response.status_code == 429
    assert response.json()["detail"] == {
        "code": "insufficient_quota",
        "message": "AI 服务额度不足，知识库未重新生成",
        "retryable": True,
    }
