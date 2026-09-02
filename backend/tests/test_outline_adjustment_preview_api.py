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


class OutlineShapeManager:
    def __init__(self):
        self.calls = []

    async def confirm_outline_shape(self, course_id, chapter_section_counts):
        self.calls.append((course_id, chapter_section_counts))
        return {
            "status": "resumed",
            "job_id": "job-shape-1",
            "course_id": course_id,
            "chapter_section_counts": chapter_section_counts,
        }


def test_outline_shape_confirmation_endpoint_resumes_teacher_job(monkeypatch):
    manager = OutlineShapeManager()

    async def load_course(course_id):
        return {"course_id": course_id}

    monkeypatch.setattr(course_versions, "get_course_or_404", load_course)
    app = FastAPI()
    app.include_router(course_versions.router, prefix="/api")
    app.dependency_overrides[require_task_manager] = lambda: manager
    client = TestClient(app)

    response = client.post(
        "/api/courses/course-1/generation/outline-shape/confirm",
        json={"chapter_section_counts": [3, 5]},
    )

    assert response.status_code == 202
    assert response.json()["job_id"] == "job-shape-1"
    assert manager.calls == [("course-1", [3, 5])]


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

    def save_draft(self, _course_id, draft, **_kwargs):
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
    quality = applied.json()["quality_report"]
    assert quality["schema_version"] == "course_outline_editorial_review_v5"
    assert quality["non_blocking"] is True
    assert saved["course_outline_quality_report"] == quality


def test_manual_formal_outline_save_persists_course_plan_and_recomputes_quality(monkeypatch):
    from course_versioning import build_blueprint_draft

    course = _canonical_course()
    course["authoring_structure_version"] = "lecture_v1"
    course["nodes"][0].update({
        "node_name": "第1讲 基础",
        "learning_objective": "解释对象生命周期",
    })
    course["nodes"][1].update({
        "node_name": "生命周期",
        "content_summary": "从对象创建、更新到销毁理解基本机制。",
        "application_anchors": ["角色生命周期日志"],
        "extension_resources": [{
            "resource_type": "website",
            "title": "Unity Manual: Order of execution",
            "edition": "",
            "locator": "Event function execution order",
            "source_ref": "Unity Manual: Order of execution",
            "verification_status": "verified",
        }],
        "learning_tasks": [{
            "mode": "offline",
            "stage": "after_class",
            "task": "标注回调日志顺序",
            "evidence": "日志截图与解释",
            "estimated_hours": 0.5,
        }],
        "education_objective_refs": ["育人目标1"],
        "ideology_implementation": "根据可复现日志讨论工程责任。",
        "hour_breakdown": {
            "classroom_lecture": 1,
            "classroom_practice": 1,
            "online_instruction": 0,
        },
        "scope_boundary": "只讨论事件回调顺序，不展开协程调度。",
        "assessment": ["根据日志解释回调顺序并标出错误。"],
    })
    course["course_plan"] = {
        "formal_syllabus_contract_version": "formal_syllabus_v2",
        "authoring_structure_version": "lecture_v1",
        "positioning": "面向初学者建立可验证的 Unity 对象生命周期认知。",
        "learning_objectives": ["掌握生命周期回调的适用时机"],
        "reference_websites": ["Unity Manual: Order of execution"],
    }
    existing = build_blueprint_draft(course)
    repository = DraftRepository(existing)

    async def load_course(_course_id):
        return course

    monkeypatch.setattr(course_versions, "_course_for_blueprint", load_course)
    monkeypatch.setattr(course_versions, "course_version_repository", repository)
    app = FastAPI()
    app.include_router(course_versions.router, prefix="/api")
    client = TestClient(app)
    completed_plan = {
        **existing["course_plan"],
        "course_intro_zh": "本课程以生命周期日志为主线，训练初学者解释和验证 Unity 回调顺序。",
        "course_intro_en": "This course uses lifecycle logs to explain and verify Unity callback order.",
        "education_objectives": ["具备依据可复现证据承担工程责任的意识"],
        "measurable_outcomes": ["能解释日志中的回调顺序并完成纠错"],
        "outcome_alignment": [{
            "outcome_number": 1,
            "objective_refs": ["学习目标1", "育人目标1"],
            "lecture_numbers": [1],
            "assessment_evidence": ["日志标注和错误解释"],
            "coverage_scope": "Unity 对象生命周期回调顺序",
        }],
        "teaching_methods": ["线下讲授与日志验证"],
        "assessment_plan": [
            {"item": "日志标注", "category": "formative", "weight_percent": 40, "criteria": "回调顺序正确且依据完整", "outcome_numbers": [1]},
            {"item": "综合纠错", "category": "summative", "weight_percent": 60, "criteria": "能定位错误并用日志验证修复", "outcome_numbers": [1]},
        ],
        "course_modules": [{"module_id": "M1", "title": "生命周期基础", "lecture_numbers": [1]}],
    }

    response = client.put(
        "/api/courses/course-1/blueprint/draft",
        json={
            "base_blueprint_revision_id": existing["base_blueprint_revision_id"],
            "expected_draft_revision_id": existing["draft_revision_id"],
            "course_plan": completed_plan,
            "nodes": existing["nodes"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["draft"]["course_plan"]["course_intro_en"].startswith("This course")
    assert payload["draft"]["course_outline"] == payload["draft"]["course_plan"]
    assert payload["quality_report"]["passed"] is True
    assert payload["draft"]["course_outline_quality_report"] == payload["quality_report"]


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
    quality = response.json()["quality"]
    assert quality["schema_version"] == "course_outline_editorial_review_v5"
    assert quality["passed"] is True


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
