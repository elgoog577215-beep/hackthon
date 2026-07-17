from copy import deepcopy

from fastapi import FastAPI
from fastapi.testclient import TestClient

from course_knowledge_rebuild import CourseKnowledgeRebuildError
from routers import knowledge_libraries


def _course():
    return {
        "course_id": "course-1",
        "course_name": "变量课程",
        "course_purpose": "systematic",
        "nodes": [{
            "node_id": "node-1",
            "node_level": 2,
            "node_name": "变量基础",
            "node_content": "变量绑定与重新赋值。",
            "learning_objective": "能够解释变量绑定与重新赋值",
            "assessment": ["解释一组赋值语句"],
            "knowledge_structure": [{
                "concept_group": "变量语义",
                "description": "区分绑定与重新赋值",
                "knowledge_points": [{
                    "name": "变量绑定",
                    "statement": "变量名通过绑定关系指向当前值。",
                    "knowledge_type": "definition",
                    "conditions": ["已经执行赋值语句"],
                    "boundaries": ["变量名本身不是值对象"],
                    "capability_points": [{
                        "name": "解释变量绑定",
                        "observable_behavior": "给定赋值语句，标出变量名、绑定和值",
                    }],
                    "misconceptions": [{
                        "name": "把变量名当成值",
                        "observable_error_pattern": "认为变量名就是值对象本身",
                        "discrimination": "分别标注变量名、绑定和值",
                        "repair_strategy": "绘制变量绑定图后重新解释",
                    }],
                    "mastery_criteria": [{
                        "name": "变量绑定解释达标",
                        "observable_performance": "独立解释变量名、绑定和值",
                        "verification_method": "分析三个赋值案例",
                    }],
                    "entry_reason": "变量绑定是本课入口。",
                    "relations": [{
                        "target_name": "重新赋值",
                        "relation_type": "prerequisite",
                        "reason": "理解已有绑定后才能解释重新赋值",
                    }],
                }, {
                    "name": "重新赋值",
                    "statement": "重新赋值会更新变量名指向的当前值。",
                    "knowledge_type": "rule",
                    "conditions": ["执行新的赋值语句"],
                    "boundaries": ["对象原地修改不属于重新绑定"],
                    "capability_points": [{
                        "name": "追踪重新赋值",
                        "observable_behavior": "逐步追踪多次赋值后的变量当前值",
                    }],
                    "mastery_criteria": [{
                        "name": "重新赋值追踪达标",
                        "observable_performance": "独立追踪多步赋值并解释绑定变化",
                        "verification_method": "完成多步赋值状态追踪",
                    }],
                }],
            }],
        }],
    }


class _CourseRepository:
    def __init__(self, course=None):
        self.course = deepcopy(course or _course())
        self.course["course_knowledge_base"] = {
            "knowledge_base_id": "ckb_course_1",
            "revision_id": "ckbr_1",
            "lifecycle_status": "active",
            "quality_report": {"strict_passed": True},
        }

    def load_course_view(self, _course_id):
        return deepcopy(self.course)

    async def update_metadata(self, _course_id, metadata):
        self.course.update(deepcopy(metadata))
        return deepcopy(self.course)


class _RebuildService:
    async def rebuild_course(self, course_id, *, force=False):
        return {
            "course_id": course_id,
            "force": force,
            "library": {
                "schema_version": "knowledge_library_view_v3",
                "lifecycle_status": "accepted",
                "identity_scope": "course_local",
            },
            "course_knowledge_base": {"schema_version": "course_knowledge_base_v2"},
            "course_map": {"coverage": {"mapped_ratio": 1.0}},
            "quality_report": {"passed": True, "strict_passed": True},
            "reference_catalog_required": False,
        }


class _MigrationService:
    def create_job(self):
        return {"job_id": "migration-1", "status": "pending"}

    def load_job(self, job_id):
        return {"job_id": job_id, "status": "completed", "completed_count": 2, "failed_count": 1}


def _client():
    course_repository = _CourseRepository()
    app = FastAPI()
    app.include_router(knowledge_libraries.router, prefix="/api")
    app.dependency_overrides[knowledge_libraries.get_course_knowledge_rebuild_service] = lambda: _RebuildService()
    app.dependency_overrides[knowledge_libraries.get_course_document_repository] = lambda: course_repository
    app.dependency_overrides[knowledge_libraries.get_course_library_migration_service] = lambda: _MigrationService()
    return TestClient(app)


def test_rebuild_review_and_accept_contracts():
    client = _client()

    rebuilt = client.post("/api/courses/course-1/knowledge-library/rebuild", json={"force": True})
    review = client.get("/api/courses/course-1/knowledge-library/review")
    accepted = client.post(
        "/api/courses/course-1/knowledge-library/review",
        json={"revision_id": "ckbr_1", "decision": "accept", "note": "通过"},
    )
    stale = client.post(
        "/api/courses/course-1/knowledge-library/review",
        json={"revision_id": "stale", "decision": "accept"},
    )

    assert rebuilt.status_code == 200
    assert rebuilt.json()["library"]["identity_scope"] == "course_local"
    assert rebuilt.json()["course_knowledge_base"]["schema_version"] == "course_knowledge_base_v2"
    assert review.json()["knowledge_scope"] == "current_course_only"
    assert review.json()["revision_id"] == "ckbr_1"
    assert accepted.json()["decision"] == "accept"
    assert accepted.json()["governance"]["knowledge_scope"] == "current_course_only"
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


def test_rebuild_exposes_course_provider_failure_without_replacing_the_library():
    class _FailingRebuildService:
        async def rebuild_course(self, course_id, *, force=False):
            raise CourseKnowledgeRebuildError(
                code="provider_request_failed",
                message="课程知识库生成失败，原版本保持不变",
                retryable=True,
                status_code=503,
            )

    app = FastAPI()
    app.include_router(knowledge_libraries.router, prefix="/api")
    app.dependency_overrides[knowledge_libraries.get_course_knowledge_rebuild_service] = (
        lambda: _FailingRebuildService()
    )
    client = TestClient(app)

    response = client.post("/api/courses/course-1/knowledge-library/rebuild", json={"force": True})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "provider_request_failed"
    assert response.json()["detail"]["retryable"] is True
    assert "message" in response.json()["detail"]


def test_rebuild_keeps_quality_diagnostics_inside_the_backend():
    internal_message = "知识点 L2-raw-id 未通过原子性门禁"

    class _FailingRebuildService:
        async def rebuild_course(self, course_id, *, force=False):
            raise CourseKnowledgeRebuildError(
                code="knowledge_quality_failed",
                message=internal_message,
                retryable=True,
                quality_report={
                    "blocking_issues": [{"message": internal_message}],
                },
            )

    app = FastAPI()
    app.include_router(knowledge_libraries.router, prefix="/api")
    app.dependency_overrides[knowledge_libraries.get_course_knowledge_rebuild_service] = (
        lambda: _FailingRebuildService()
    )
    client = TestClient(app)

    response = client.post("/api/courses/course-1/knowledge-library/rebuild", json={"force": True})

    detail = response.json()["detail"]
    assert response.status_code == 422
    assert detail["message"] == "知识库升级暂未完成，原课程与旧知识结构保持不变。请稍后重试。"
    assert internal_message not in response.text
    assert "quality_report" not in detail
