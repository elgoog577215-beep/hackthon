from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dependencies import require_task_manager
from routers import course_versions


class PreviewManager:
    def __init__(self):
        self.calls = []

    async def preview_outline_adjustment(self, course_id, payload):
        self.calls.append((course_id, payload))
        return {
            "proposal_id": "proposal-1",
            "source_draft_revision_id": payload["expected_draft_revision_id"],
            "operations": [],
            "summary": "未改变目录",
            "diff": {"added": [], "removed": [], "moved": [], "updated": []},
            "draft": {"nodes": []},
            "impact_report": {},
            "constraint_report": {"chapter_count": 1, "section_count": 1},
            "can_apply": True,
            "blocking_issues": [],
            "warnings": [],
        }


def test_preview_endpoint_passes_optimistic_revisions_without_writing(monkeypatch):
    manager = PreviewManager()
    app = FastAPI()
    app.include_router(course_versions.router, prefix="/api")
    app.dependency_overrides[require_task_manager] = lambda: manager
    client = TestClient(app)

    response = client.post(
        "/api/courses/course-1/blueprint/adjustments/preview",
        json={
            "request_id": "request-1",
            "base_blueprint_revision_id": "bp-1",
            "expected_draft_revision_id": "draft-1",
            "instruction": "把生命周期移到工程实践章，并新增一节组件组合",
        },
    )

    assert response.status_code == 200
    assert response.json()["proposal_id"] == "proposal-1"
    assert manager.calls == [
        (
            "course-1",
            {
                "request_id": "request-1",
                "base_blueprint_revision_id": "bp-1",
                "expected_draft_revision_id": "draft-1",
                "instruction": "把生命周期移到工程实践章，并新增一节组件组合",
            },
        )
    ]


def test_preview_instruction_contract_rejects_blank_and_oversized_input():
    manager = PreviewManager()
    app = FastAPI()
    app.include_router(course_versions.router, prefix="/api")
    app.dependency_overrides[require_task_manager] = lambda: manager
    client = TestClient(app)

    blank = client.post(
        "/api/courses/course-1/blueprint/adjustments/preview",
        json={
            "request_id": "request-blank",
            "base_blueprint_revision_id": "bp-1",
            "expected_draft_revision_id": "draft-1",
            "instruction": "   ",
        },
    )
    oversized = client.post(
        "/api/courses/course-1/blueprint/adjustments/preview",
        json={
            "request_id": "request-long",
            "base_blueprint_revision_id": "bp-1",
            "expected_draft_revision_id": "draft-1",
            "instruction": "调" * 3001,
        },
    )

    assert blank.status_code == 422
    assert oversized.status_code == 422
    assert manager.calls == []


class DraftRepository:
    def __init__(self, draft):
        self.draft = draft
        self.saved = []

    def load_draft(self, _course_id):
        return self.draft

    def save_draft(self, _course_id, draft):
        self.saved.append(draft)
        self.draft = draft
        return draft


def _canonical_course():
    return {
        "course_id": "course-1",
        "course_name": "Unity",
        "course_type": "systematic",
        "course_purpose": "systematic",
        "nodes": [
            {
                "node_id": "L1-1",
                "parent_node_id": "root",
                "node_level": 1,
                "node_name": "基础",
                "learning_objective": "建立基础",
                "prerequisite_node_ids": [],
            },
            {
                "node_id": "L2-1-1",
                "parent_node_id": "L1-1",
                "node_level": 2,
                "node_name": "生命周期",
                "learning_objective": "选择生命周期入口",
                "prerequisite_node_ids": [],
            },
        ],
    }


def test_apply_rejects_stale_draft_and_recompiles_instead_of_trusting_client_plan(monkeypatch):
    from course_versioning import build_blueprint_draft

    course = _canonical_course()
    existing = build_blueprint_draft(course)
    repository = DraftRepository(existing)

    async def load_course(_course_id):
        return course

    monkeypatch.setattr(course_versions, "_course_for_blueprint", load_course)
    monkeypatch.setattr(course_versions, "course_version_repository", repository)
    app = FastAPI()
    app.include_router(course_versions.router, prefix="/api")
    client = TestClient(app)

    stale = client.put(
        "/api/courses/course-1/blueprint/draft",
        json={
            "base_blueprint_revision_id": existing["base_blueprint_revision_id"],
            "expected_draft_revision_id": "draft-stale",
            "nodes": existing["nodes"],
        },
    )
    assert stale.status_code == 409
    assert repository.saved == []

    nodes = existing["nodes"] + [{
        "node_id": "L2-1-2",
        "parent_node_id": "L1-1",
        "node_level": 2,
        "node_name": "组件组合",
        "learning_objective": "组合组件",
        "prerequisite_node_ids": ["L2-1-1"],
    }]
    applied = client.put(
        "/api/courses/course-1/blueprint/draft",
        json={
            "base_blueprint_revision_id": existing["base_blueprint_revision_id"],
            "expected_draft_revision_id": existing["draft_revision_id"],
            "course_blueprint": {"sections": [{"title": "客户端伪造结构"}]},
            "nodes": nodes,
        },
    )

    assert applied.status_code == 200
    saved = repository.saved[0]
    assert [section["title"] for section in saved["course_plan"]["chapters"][0]["sections"]] == [
        "1.1 生命周期",
        "1.2 组件组合",
    ]
    assert saved["course_blueprint"]["sections"] == saved["course_plan"]["chapters"]


def test_adjustment_apply_is_bound_to_previewed_operations_and_ignores_tampered_nodes(monkeypatch):
    from course_versioning import build_blueprint_draft, outline_adjustment_proposal_id

    course = _canonical_course()
    existing = build_blueprint_draft(course)
    repository = DraftRepository(existing)

    async def load_course(_course_id):
        return course

    monkeypatch.setattr(course_versions, "_course_for_blueprint", load_course)
    monkeypatch.setattr(course_versions, "course_version_repository", repository)
    app = FastAPI()
    app.include_router(course_versions.router, prefix="/api")
    client = TestClient(app)
    operations = [{
        "op": "add_node",
        "temp_ref": "tmp-components",
        "node_level": 2,
        "parent_ref": "L1-1",
        "after_ref": "L2-1-1",
        "node_name": "组件组合",
        "learning_objective": "组合组件",
        "prerequisite_refs": ["L2-1-1"],
    }]
    proposal_id = outline_adjustment_proposal_id(existing["draft_revision_id"], operations)

    applied = client.put(
        "/api/courses/course-1/blueprint/draft",
        json={
            "base_blueprint_revision_id": existing["base_blueprint_revision_id"],
            "expected_draft_revision_id": existing["draft_revision_id"],
            "adjustment_proposal_id": proposal_id,
            "adjustment_operations": operations,
            "nodes": [{"node_id": "tampered", "node_name": "被篡改"}],
            "blueprint_locks": {},
        },
    )

    assert applied.status_code == 200
    assert [node["node_name"] for node in repository.saved[0]["nodes"]] == [
        "第1章 基础",
        "1.1 生命周期",
        "1.2 组件组合",
    ]

    repository.draft = existing
    rejected = client.put(
        "/api/courses/course-1/blueprint/draft",
        json={
            "base_blueprint_revision_id": existing["base_blueprint_revision_id"],
            "expected_draft_revision_id": existing["draft_revision_id"],
            "adjustment_proposal_id": "proposal-tampered",
            "adjustment_operations": operations,
        },
    )
    assert rejected.status_code == 409
    assert len(repository.saved) == 1


# --- D-1b：大纲确认页取的是 /blueprint，覆盖度判断必须走到这里 -------------


def test_blueprint_endpoint_exposes_the_coverage_verdict(monkeypatch):
    """确认页读 /blueprint，所以覆盖度必须挂在这个响应上。"""
    course = _canonical_course()
    course["generation_stage_artifacts"] = {
        "outline": {
            "course_coverage_verdict": {
                "subject": "微积分",
                "status": "partial",
                "scale": "micro",
                "scale_label": "微型课",
                "class_hours": 8,
                "may_claim_complete_subject": False,
                "coverage_promise": "只覆盖一个可检查的核心切面",
                "required_positioning": "微积分核心概览课",
                "covered_topics": ["函数、极限与连续"],
                "uncovered_topics": ["中值定理", "洛必达法则与未定式"],
                "advisories": ["建议一：压缩为核心课"],
            },
        },
    }

    async def load_course(_course_id):
        return course

    monkeypatch.setattr(course_versions, "_course_for_blueprint", load_course)
    monkeypatch.setattr(
        course_versions, "course_version_repository", DraftRepository(None)
    )
    app = FastAPI()
    app.include_router(course_versions.router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/courses/course-1/blueprint")

    assert response.status_code == 200
    coverage = response.json()["coverage"]
    assert coverage["available"] is True
    assert coverage["scale_label"] == "微型课"
    assert coverage["may_claim_complete_subject"] is False
    assert coverage["uncovered_count"] == 2
    assert "中值定理" in coverage["uncovered_topics"]


def test_blueprint_endpoint_reports_unknown_coverage_for_pre_d1_courses(monkeypatch):
    """老课程没有判定时报 unknown，绝不能默认成"完整"。"""
    course = _canonical_course()

    async def load_course(_course_id):
        return course

    monkeypatch.setattr(course_versions, "_course_for_blueprint", load_course)
    monkeypatch.setattr(
        course_versions, "course_version_repository", DraftRepository(None)
    )
    app = FastAPI()
    app.include_router(course_versions.router, prefix="/api")
    client = TestClient(app)

    coverage = client.get("/api/courses/course-1/blueprint").json()["coverage"]

    assert coverage["available"] is False
    assert coverage["status"] == "unknown"
    assert coverage.get("may_claim_complete_subject") is not True
