from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from course_document import CourseBlock, CourseDocument, CourseSection, refresh_document_revision
from course_repository import CourseDocumentRepository
from teaching_plan_workbench import (
    TeachingPlanWorkbenchError,
    TeachingPlanWorkbenchService,
)
from teaching_representations import (
    SourceBinding,
    TeachingRepresentation,
    TeachingRepresentationRepository,
)


class MemoryStorage:
    def __init__(self, course: dict) -> None:
        self.course = deepcopy(course)

    def load_course(self, _course_id: str) -> dict:
        return deepcopy(self.course)

    async def save_course(self, _course_id: str, data: dict) -> None:
        self.course = deepcopy(data)


def _course() -> dict:
    document = refresh_document_revision(CourseDocument(
        course_id="course-1",
        title="一次函数",
        sections=[CourseSection(
            section_id="section-1",
            parent_section_id="chapter-1",
            title="斜率",
            position=0,
            level=2,
            learning_objective="理解斜率的变化意义",
        )],
        blocks=[CourseBlock(
            block_id="block-1",
            section_id="section-1",
            position=0,
            role="concept",
            payload={"markdown": "斜率描述变化率。"},
        )],
    ))
    return {
        "course_id": "course-1",
        "course_name": "一次函数",
        "course_schema_version": "course_document_v1",
        "course_document_authoritative": True,
        "course_document": document.model_dump(mode="json"),
        "course_document_revision": document.document_revision,
        "current_course_version_id": document.document_revision,
        "course_operation_log": [],
        "course_plan": {
            "course_title": "一次函数",
            "positioning": "从变化率建立函数直觉",
            "learning_objectives": ["理解斜率表示的变化关系"],
            "prerequisites": ["平面直角坐标系"],
            "chapters": [{
                "chapter_number": 1,
                "title": "变化率",
                "sections": [{
                    "node_id": "section-1",
                    "title": "斜率",
                    "learning_objective": "理解斜率的变化意义",
                    "module_plan": [{
                        "module_id": "core",
                        "label": "核心讲解",
                        "required": True,
                        "output_contract": "解释斜率",
                        "prompt_instruction": "从图像和公式说明斜率",
                    }],
                }],
            }],
        },
        "generation_request": {"target_audience": "初中二年级学生"},
        "subject_pedagogy_profile": {"rationale": "先观察图像，再归纳公式。"},
        "course_teaching_plan": {
            "schema_version": "course_teaching_plan_v3",
            "source_outline_revision_id": "outline-1",
            "revision_id": "teaching-initial",
            "sections": [{
                "node_id": "section-1",
                "key_points": ["斜率"],
                "reused_knowledge_names": [],
                "knowledge_relations": [],
                "knowledge_structure": [{
                    "concept_group": "变化率",
                    "knowledge_points": [{
                        "name": "斜率",
                        "statement": "斜率描述横坐标每变化一个单位时的纵坐标变化量。",
                        "capability": "能够解释斜率的正负与大小",
                        "conditions": ["在平面直角坐标系中"],
                        "mastery_criteria": [{
                            "observable_performance": "能由两点求斜率",
                            "verification_method": "出口题",
                        }],
                        "misconceptions": [],
                    }],
                }],
                "teaching_modules": [{
                    "module_id": "core",
                    "teaching_purpose": "建立变化率直觉",
                    "knowledge_names": ["斜率"],
                    "teaching_guidance": "先比较两段路程，再归纳斜率公式。",
                }],
            }],
        },
        "generation_stage_artifacts": {"course_teaching_plan": {"status": "completed"}},
    }


@pytest.mark.asyncio
async def test_draft_patch_review_and_apply_creates_new_official_revision() -> None:
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))

    initial = service.view("course-1", actor="teacher-1")
    assert initial["available"] is True
    initial_revision = initial["current_plan_revision_id"]

    created = await service.create_draft(
        "course-1",
        actor="teacher-1",
        idempotency_key="create-1",
        base_plan_revision_id=initial_revision,
        base_course_document_revision=initial["course_document_revision"],
    )
    draft = created["draft"]
    assert draft and draft["base_plan_revision_id"] == initial_revision

    updated = await service.patch_draft(
        "course-1",
        actor="teacher-1",
        draft_id=draft["draft_id"],
        path="overall/positioning",
        value="从真实变化情境理解一次函数斜率",
        expected_value_hash="",
        base_plan_revision_id=initial_revision,
        idempotency_key="patch-1",
    )
    assert updated["draft"]["changed_paths"] == ["overall/positioning"]
    review = service.review_draft("course-1", actor="teacher-1", draft_id=draft["draft_id"])
    assert review["validation"]["passed"] is True
    assert review["impact_report"]["changed"]

    reviewed = await service.create_change_set(
        "course-1",
        actor="teacher-1",
        draft_id=draft["draft_id"],
        idempotency_key="review-1",
    )
    change_set = next(item for item in reviewed["change_sets"] if item["status"] == "ready")
    applied = await service.apply_change_set(
        "course-1",
        actor="teacher-1",
        change_set_id=change_set["change_set_id"],
        idempotency_key="apply-1",
    )

    current = applied["workbench"]
    assert current["current_plan_revision_id"] != initial_revision
    assert current["draft"] is None
    assert storage.course["course_plan"]["positioning"] == "从真实变化情境理解一次函数斜率"
    assert storage.course["course_revision_vector"]["revisions"]["course_teaching_plan"] == current["current_plan_revision_id"]
    assert applied["receipt"]["revision_change"]["event_id"].startswith("cre_")
    assert "course_teaching_plan" in applied["receipt"]["revision_change"]["changed_source_keys"]
    assert any(item["status"] == "applied" for item in current["change_sets"])

    baseline = next(item for item in current["revisions"] if item["revision_id"] == initial_revision)
    restored = await service.restore_revision(
        "course-1",
        actor="teacher-1",
        revision_id=baseline["revision_id"],
        idempotency_key="restore-1",
    )
    restored_workbench = restored["workbench"]
    assert restored_workbench["current_plan_revision_id"] not in {
        initial_revision,
        current["current_plan_revision_id"],
    }
    assert any(
        item.get("restored_from_revision_id") == initial_revision
        for item in restored_workbench["revisions"]
    )


@pytest.mark.asyncio
async def test_classroom_constraints_validate_and_apply_from_the_same_plan_revision() -> None:
    course = _course()
    course["generation_request"]["teacher_course_brief"] = {
        "schema_version": "teacher_course_brief_v1",
        "academic_term": "2026-2027 学年第一学期",
        "target_audience": "初中二年级学生",
        "total_class_hours": 2,
        "lesson_duration_minutes": 45,
        "teaching_context": "classroom",
    }
    storage = MemoryStorage(course)
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    initial = service.view("course-1", actor="teacher-1")
    assert "overall/total_class_hours" in {
        item["path"] for item in initial["editable_fields"]
    }

    created = await service.create_draft(
        "course-1",
        actor="teacher-1",
        idempotency_key="create-classroom",
        base_plan_revision_id=initial["current_plan_revision_id"],
        base_course_document_revision=initial["course_document_revision"],
    )
    draft_id = created["draft"]["draft_id"]
    base_revision = initial["current_plan_revision_id"]

    await service.patch_draft(
        "course-1",
        actor="teacher-1",
        draft_id=draft_id,
        path="overall/total_class_hours",
        value=1,
        expected_value_hash="",
        base_plan_revision_id=base_revision,
        idempotency_key="classroom-hours",
    )
    await service.patch_draft(
        "course-1",
        actor="teacher-1",
        draft_id=draft_id,
        path="sections/section-1/planned_minutes",
        value=90,
        expected_value_hash="",
        base_plan_revision_id=base_revision,
        idempotency_key="section-over-capacity",
    )
    blocked = service.review_draft("course-1", actor="teacher-1", draft_id=draft_id)
    assert blocked["validation"]["passed"] is False
    assert "teaching_plan_class_hours_exceeded" in {
        item["code"] for item in blocked["validation"]["issues"]
    }

    patched = await service.patch_draft(
        "course-1",
        actor="teacher-1",
        draft_id=draft_id,
        path="sections/section-1/planned_minutes",
        value=45,
        expected_value_hash="",
        base_plan_revision_id=base_revision,
        idempotency_key="section-within-capacity",
    )
    await service.patch_draft(
        "course-1",
        actor="teacher-1",
        draft_id=draft_id,
        path="sections/section-1/teacher_activities",
        value=["展示两段路径变化，引导学生比较"],
        expected_value_hash="",
        base_plan_revision_id=base_revision,
        idempotency_key="section-teacher-activity",
    )
    review = service.review_draft("course-1", actor="teacher-1", draft_id=draft_id)
    assert review["validation"]["passed"] is True
    assert any(
        item["type"] == "lecture"
        for item in review["impact_report"]["needs_regeneration"]
    )

    prepared = await service.create_change_set(
        "course-1",
        actor="teacher-1",
        draft_id=patched["draft"]["draft_id"],
        idempotency_key="prepare-classroom-change",
    )
    change_set = next(item for item in prepared["change_sets"] if item["status"] == "ready")
    applied = await service.apply_change_set(
        "course-1",
        actor="teacher-1",
        change_set_id=change_set["change_set_id"],
        idempotency_key="apply-classroom-change",
    )
    assert storage.course["course_teaching_plan"]["classroom"]["total_class_hours"] == 1
    assert storage.course["course_teaching_plan"]["sections"][0]["planned_minutes"] == 45
    assert storage.course["course_teaching_plan"]["sections"][0]["teacher_activities"] == [
        "展示两段路径变化，引导学生比较"
    ]
    applied_change_set = next(
        item for item in applied["workbench"]["change_sets"]
        if item["change_set_id"] == change_set["change_set_id"]
    )
    assert applied_change_set["impact_report"]["needs_regeneration"]


@pytest.mark.asyncio
async def test_patch_rejects_readonly_identifier_and_stale_base() -> None:
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    view = service.view("course-1", actor="teacher-1")
    created = await service.create_draft(
        "course-1",
        actor="teacher-1",
        idempotency_key="create-1",
        base_plan_revision_id=view["current_plan_revision_id"],
        base_course_document_revision=view["course_document_revision"],
    )
    with pytest.raises(TeachingPlanWorkbenchError, match="自动维护") as readonly:
        await service.patch_draft(
            "course-1",
            actor="teacher-1",
            draft_id=created["draft"]["draft_id"],
            path="sections/section-1/knowledge_id",
            value="other",
            expected_value_hash="",
            base_plan_revision_id=view["current_plan_revision_id"],
            idempotency_key="patch-identifier",
        )
    assert readonly.value.code == "teaching_plan_readonly_field"

    with pytest.raises(TeachingPlanWorkbenchError) as stale:
        await service.patch_draft(
            "course-1",
            actor="teacher-1",
            draft_id=created["draft"]["draft_id"],
            path="overall/positioning",
            value="新的定位",
            expected_value_hash="",
            base_plan_revision_id="old-plan",
            idempotency_key="patch-stale",
        )
    assert stale.value.code == "teaching_plan_base_conflict"


@pytest.mark.asyncio
async def test_new_draft_edit_supersedes_old_change_set_and_empty_review_is_rejected() -> None:
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    view = service.view("course-1", actor="teacher-1")
    created = await service.create_draft(
        "course-1",
        actor="teacher-1",
        idempotency_key="create-1",
        base_plan_revision_id=view["current_plan_revision_id"],
        base_course_document_revision=view["course_document_revision"],
    )
    with pytest.raises(TeachingPlanWorkbenchError) as empty:
        await service.create_change_set(
            "course-1",
            actor="teacher-1",
            draft_id=created["draft"]["draft_id"],
            idempotency_key="empty-review",
        )
    assert empty.value.code == "teaching_plan_no_changes"

    patched = await service.patch_draft(
        "course-1",
        actor="teacher-1",
        draft_id=created["draft"]["draft_id"],
        path="overall/positioning",
        value="先观察变化，再建立函数关系",
        expected_value_hash="",
        base_plan_revision_id=view["current_plan_revision_id"],
        idempotency_key="patch-1",
    )
    reviewed = await service.create_change_set(
        "course-1",
        actor="teacher-1",
        draft_id=patched["draft"]["draft_id"],
        idempotency_key="review-1",
    )
    first_change_set = next(item for item in reviewed["change_sets"] if item["status"] == "ready")

    repatched = await service.patch_draft(
        "course-1",
        actor="teacher-1",
        draft_id=patched["draft"]["draft_id"],
        path="overall/target_audience",
        value="刚接触一次函数的初中生",
        expected_value_hash="",
        base_plan_revision_id=view["current_plan_revision_id"],
        idempotency_key="patch-2",
    )
    assert next(
        item for item in repatched["change_sets"]
        if item["change_set_id"] == first_change_set["change_set_id"]
    )["status"] == "superseded"
    rebuilt = await service.create_change_set(
        "course-1",
        actor="teacher-1",
        draft_id=repatched["draft"]["draft_id"],
        idempotency_key="review-2",
    )
    assert any(item["status"] == "ready" for item in rebuilt["change_sets"])


@pytest.mark.asyncio
async def test_discarding_a_draft_never_changes_the_official_plan() -> None:
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    view = service.view("course-1", actor="teacher-1")
    created = await service.create_draft(
        "course-1",
        actor="teacher-1",
        idempotency_key="create-discard",
        base_plan_revision_id=view["current_plan_revision_id"],
        base_course_document_revision=view["course_document_revision"],
    )
    patched = await service.patch_draft(
        "course-1",
        actor="teacher-1",
        draft_id=created["draft"]["draft_id"],
        path="overall/positioning",
        value="仅写入草稿，不能改变正式课程",
        expected_value_hash="",
        base_plan_revision_id=view["current_plan_revision_id"],
        idempotency_key="patch-discard",
    )
    discarded = await service.discard_draft(
        "course-1",
        actor="teacher-1",
        draft_id=patched["draft"]["draft_id"],
        idempotency_key="discard-1",
    )

    assert discarded["draft"] is None
    assert storage.course["course_plan"]["positioning"] == "从变化率建立函数直觉"
    assert storage.course["course_teaching_plan"]["revision_id"] == view["current_plan_revision_id"]


@pytest.mark.asyncio
async def test_ai_candidate_stays_separate_until_teacher_accepts_it() -> None:
    async def candidate_generator(**_kwargs):
        return {
            "rationale": "让课程定位更贴近学生可观察的学习结果。",
            "operations": [{
                "path": "overall/positioning",
                "after": "从真实图像变化建立一次函数斜率的解释能力",
                "reason": "先建立情境，再形成符号表达。",
            }],
        }

    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(
        CourseDocumentRepository(storage),
        candidate_generator=candidate_generator,
    )
    view = service.view("course-1", actor="teacher-1")
    created = await service.create_draft(
        "course-1",
        actor="teacher-1",
        idempotency_key="create-1",
        base_plan_revision_id=view["current_plan_revision_id"],
        base_course_document_revision=view["course_document_revision"],
    )
    candidate_view = await service.create_ai_candidate(
        "course-1",
        actor="teacher-1",
        draft_id=created["draft"]["draft_id"],
        paths=["overall/positioning"],
        instruction="把定位改得更贴近学生的学习过程",
        idempotency_key="ai-1",
    )
    candidate = candidate_view["ai_candidates"][0]
    assert candidate["status"] == "ready"
    assert candidate_view["draft"]["operations"] == []
    assert storage.course["course_plan"]["positioning"] == "从变化率建立函数直觉"

    accepted = await service.accept_ai_candidate(
        "course-1",
        actor="teacher-1",
        candidate_id=candidate["candidate_id"],
        operation_ids=[candidate["operations"][0]["operation_id"]],
        idempotency_key="ai-accept-1",
    )
    assert accepted["ai_candidates"][0]["status"] == "accepted"
    assert accepted["draft"]["operations"][0]["source"] == "ai"
    assert storage.course["course_plan"]["positioning"] == "从变化率建立函数直觉"


@pytest.mark.asyncio
async def test_official_teaching_plan_revision_marks_dependent_representation_stale(tmp_path) -> None:
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    document = CourseDocument.model_validate(storage.course["course_document"])
    now = datetime.now(timezone.utc).isoformat()
    binding = SourceBinding(
        course_id="course-1",
        source_revisions={"course_teaching_plan": "teaching-initial"},
    )
    representation_repository = TeachingRepresentationRepository(tmp_path / "representations")
    representation_repository.register_representation(TeachingRepresentation(
        representation_id="handout-from-plan",
        course_id="course-1",
        representation_type="handout",
        source_bindings=[binding],
        source_revision_vector=binding.source_revisions,
        spec_id="spec-handout-from-plan",
        semantic_fingerprint="fingerprint-handout-from-plan",
        revision="revision-handout-from-plan",
        status="ready",
        created_at=now,
        updated_at=now,
    ))
    view = service.view("course-1", actor="teacher-1")
    created = await service.create_draft(
        "course-1",
        actor="teacher-1",
        idempotency_key="create-1",
        base_plan_revision_id=view["current_plan_revision_id"],
        base_course_document_revision=view["course_document_revision"],
    )
    patched = await service.patch_draft(
        "course-1",
        actor="teacher-1",
        draft_id=created["draft"]["draft_id"],
        path="overall/positioning",
        value="从真实变化建立一次函数斜率的解释能力",
        expected_value_hash="",
        base_plan_revision_id=view["current_plan_revision_id"],
        idempotency_key="patch-1",
    )
    reviewed = await service.create_change_set(
        "course-1",
        actor="teacher-1",
        draft_id=patched["draft"]["draft_id"],
        idempotency_key="review-1",
    )
    change_set = next(item for item in reviewed["change_sets"] if item["status"] == "ready")
    await service.apply_change_set(
        "course-1",
        actor="teacher-1",
        change_set_id=change_set["change_set_id"],
        idempotency_key="apply-1",
    )

    registry = representation_repository.reconcile_course_operation_log(
        "course-1",
        storage.course["course_operation_log"],
    )
    stale = registry.representations[0]
    assert stale.status == "stale"
    assert "source_revision_changed:course_teaching_plan" in stale.stale_reasons


@pytest.mark.asyncio
async def test_feature_flag_keeps_official_plan_readable_but_blocks_writes() -> None:
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(
        CourseDocumentRepository(storage),
        feature_enabled=False,
    )
    view = service.view("course-1", actor="teacher-1")
    assert view["enabled"] is False
    assert view["available"] is False
    assert view["teaching_plan"]["status"] == "completed"
    with pytest.raises(TeachingPlanWorkbenchError) as disabled:
        await service.create_draft(
            "course-1",
            actor="teacher-1",
            idempotency_key="create-while-disabled",
            base_plan_revision_id=view["current_plan_revision_id"],
            base_course_document_revision=view["course_document_revision"],
        )
    assert disabled.value.code == "teaching_plan_workbench_disabled"
    assert "teaching_plan_workbench" not in storage.course


@pytest.mark.asyncio
async def test_v2_plan_creates_a_baseline_without_rewriting_the_official_plan() -> None:
    course = _course()
    course["course_teaching_plan"]["schema_version"] = "course_teaching_plan_v2"
    storage = MemoryStorage(course)
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    view = service.view("course-1", actor="teacher-1")
    assert view["available"] is True
    created = await service.create_draft(
        "course-1",
        actor="teacher-1",
        idempotency_key="create-v2-baseline",
        base_plan_revision_id=view["current_plan_revision_id"],
        base_course_document_revision=view["course_document_revision"],
    )
    assert created["revisions"][0]["revision_id"] == view["current_plan_revision_id"]
    assert storage.course["course_teaching_plan"]["schema_version"] == "course_teaching_plan_v2"


def test_legacy_course_is_readable_but_never_exposes_editable_fields() -> None:
    course = _course()
    for key in (
        "course_schema_version",
        "course_document",
        "course_document_revision",
        "course_document_authoritative",
    ):
        course.pop(key, None)
    storage = MemoryStorage(course)
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    view = service.view("course-1", actor="teacher-1")
    assert view["available"] is False
    assert view["editable_fields"] == []
    assert view["teaching_plan"]


def test_workbench_router_smoke_covers_draft_review_and_apply() -> None:
    from routers import teaching_plan_workbench as workbench_router

    storage = MemoryStorage(_course())
    repository = CourseDocumentRepository(storage)
    app = FastAPI()
    app.include_router(workbench_router.router, prefix="/api")
    app.dependency_overrides[workbench_router.get_course_document_repository] = lambda: repository
    client = TestClient(app)
    headers = {"X-User-Id": "teacher-api-test"}
    base_path = "/api/courses/course-1/teaching-plan"

    initial = client.get(f"{base_path}/workbench", headers=headers)
    assert initial.status_code == 200
    workbench = initial.json()["workbench"]
    created = client.post(f"{base_path}/drafts", headers=headers, json={
        "base_plan_revision_id": workbench["current_plan_revision_id"],
        "base_course_document_revision": workbench["course_document_revision"],
        "idempotency_key": "api-create",
    })
    assert created.status_code == 200
    draft = created.json()["workbench"]["draft"]
    patched = client.patch(f"{base_path}/drafts/{draft['draft_id']}", headers=headers, json={
        "path": "overall/positioning",
        "value": "从可观察的图像变化建立一次函数直觉",
        "base_plan_revision_id": draft["base_plan_revision_id"],
        "idempotency_key": "api-patch",
    })
    assert patched.status_code == 200
    reviewed = client.post(f"{base_path}/validate", headers=headers, json={
        "draft_id": draft["draft_id"], "idempotency_key": "api-validate",
    })
    assert reviewed.status_code == 200
    assert reviewed.json()["review"]["validation"]["passed"] is True
    change_set = client.post(f"{base_path}/change-sets", headers=headers, json={
        "draft_id": draft["draft_id"], "idempotency_key": "api-review",
    })
    assert change_set.status_code == 200
    ready = next(item for item in change_set.json()["workbench"]["change_sets"] if item["status"] == "ready")
    applied = client.post(
        f"{base_path}/change-sets/{ready['change_set_id']}/apply",
        headers=headers,
        json={"idempotency_key": "api-apply"},
    )
    assert applied.status_code == 200
    assert applied.json()["workbench"]["current_plan_revision_id"] != workbench["current_plan_revision_id"]


def test_router_service_reads_the_representation_registry_for_impact() -> None:
    """路由必须把表达注册表接进影响分析。

    注册表只读接入决定 needs_regeneration 是真实引用闭包还是按小节的保守答案。
    这个接线断了不会让任何断言失败——影响报告照样返回、只是变粗——
    所以在这里正面钉住它。
    """
    from routers import teaching_plan_workbench as workbench_router

    storage = MemoryStorage(_course())
    repository = CourseDocumentRepository(storage)
    service = workbench_router._service(repository)

    assert service.representation_repository is not None
    # 未知课程返回空注册表而不是抛错：影响分析退回按小节的保守答案，
    # 工作台仍然可用。
    registry = service.representation_registry("course-does-not-exist")
    assert registry is not None
    assert list(registry.representations) == []


def test_section_scoped_ai_request_accepts_a_whole_section_of_fields() -> None:
    """需求 5：教案要能分小节优化，不是只能整篇重生成。

    前端「优化当前小节」把该小节所有可编辑路径一次性发出。哪怕最小课程，
    一个小节也有 17 条可编辑路径（目标、要点、时长、7 条课堂执行列表、
    5 条模块字段、知识 statement/capability），超过原先 12 条的上限，
    于是每一次小节级优化都在 HTTP 层 422，根本到不了领域层。
    """
    from routers import teaching_plan_workbench as workbench_router

    storage = MemoryStorage(_course())
    repository = CourseDocumentRepository(storage)
    app = FastAPI()
    app.include_router(workbench_router.router, prefix="/api")
    app.dependency_overrides[workbench_router.get_course_document_repository] = lambda: repository
    client = TestClient(app)
    headers = {"X-User-Id": "teacher-section-scope"}
    base_path = "/api/courses/course-1/teaching-plan"

    workbench = client.get(f"{base_path}/workbench", headers=headers).json()["workbench"]
    draft = client.post(f"{base_path}/drafts", headers=headers, json={
        "base_plan_revision_id": workbench["current_plan_revision_id"],
        "base_course_document_revision": workbench["course_document_revision"],
        "idempotency_key": "section-scope-create",
    }).json()["workbench"]["draft"]

    section_paths = [
        field["path"]
        for field in workbench["editable_fields"]
        if field["path"].startswith("sections/section-1/") and field["state"] != "readonly"
    ]
    assert len(section_paths) > 12, "最小课程的小节路径数应当已经超过旧上限"

    response = client.post(
        f"{base_path}/drafts/{draft['draft_id']}/ai-candidates",
        headers=headers,
        json={
            "paths": section_paths,
            "instruction": "把这一节讲得更具体，给出可观察的学生行为",
            "idempotency_key": "section-scope-ai",
        },
    )
    # 这里不校验 AI 结果本身（没有真实模型），只要求请求通过 HTTP 契约校验、
    # 进入领域层：不能再是 422 too_long。
    assert response.status_code != 422, response.text


@pytest.mark.asyncio
async def test_section_optimization_touches_only_that_section_and_leaves_others_intact() -> None:
    """需求 5：分小节优化只改这一节，其他小节与总体教案保持不变。

    这是「分小节优化」相对「整篇重生成」的关键区别，也是不建平行真源的
    前提：优化仍然走草稿 → 变更集 → 应用同一条链，正式教案只有一份。
    """
    async def candidate_generator(*, paths, **_kwargs):
        # 只对本节目标提建议，模拟教师「把这一节讲得更具体」。
        assert all(path.startswith("sections/section-1/") for path in paths)
        return {
            "rationale": "让本节目标落到可观察的学生行为。",
            "operations": [{
                "path": "sections/section-1/learning_objective",
                "after": "能由任意两点求出斜率并解释其正负含义",
                "reason": "原目标只说理解，无法观察。",
            }],
        }

    course = _course()
    # 第二个小节：优化第一节时它必须一个字都不变。
    # 结构要完整——知识陈述与模块都要有，否则被教案质量门正当拦下，
    # 那测的就不是分小节优化了。
    course["course_plan"]["chapters"][0]["sections"].append({
        "node_id": "section-2",
        "title": "截距",
        "learning_objective": "理解截距的含义",
        "module_plan": [{
            "module_id": "core",
            "label": "核心讲解",
            "required": True,
            "output_contract": "解释截距",
            "prompt_instruction": "从图像说明截距",
        }],
    })
    course["course_teaching_plan"]["sections"].append({
        "node_id": "section-2",
        "key_points": ["截距"],
        "reused_knowledge_names": [],
        "knowledge_relations": [],
        "knowledge_structure": [{
            "concept_group": "位置",
            "knowledge_points": [{
                "name": "截距",
                "statement": "截距是直线与纵轴交点的纵坐标。",
                "capability": "能够从图像读出截距",
                "conditions": ["在平面直角坐标系中"],
                "mastery_criteria": [{
                    "observable_performance": "能由图像读出截距",
                    "verification_method": "出口题",
                }],
                "misconceptions": [],
            }],
        }],
        "teaching_modules": [{
            "module_id": "core",
            "teaching_purpose": "建立截距的几何含义",
            "knowledge_names": ["截距"],
            "teaching_guidance": "先看交点，再写代数表达。",
        }],
        "learning_objective": "理解截距的含义",
    })

    storage = MemoryStorage(course)
    service = TeachingPlanWorkbenchService(
        CourseDocumentRepository(storage),
        candidate_generator=candidate_generator,
    )
    view = service.view("course-1", actor="teacher-1")
    before_section_two = deepcopy(
        next(s for s in storage.course["course_teaching_plan"]["sections"] if s["node_id"] == "section-2")
    )
    before_positioning = storage.course["course_plan"]["positioning"]

    created = await service.create_draft(
        "course-1",
        actor="teacher-1",
        idempotency_key="sec-create",
        base_plan_revision_id=view["current_plan_revision_id"],
        base_course_document_revision=view["course_document_revision"],
    )
    draft_id = created["draft"]["draft_id"]

    section_paths = [
        field["path"]
        for field in view["editable_fields"]
        if field["path"].startswith("sections/section-1/") and field["state"] != "readonly"
    ]
    candidate_view = await service.create_ai_candidate(
        "course-1",
        actor="teacher-1",
        draft_id=draft_id,
        paths=section_paths,
        instruction="把这一节讲得更具体",
        idempotency_key="sec-ai",
    )
    candidate = next(item for item in candidate_view["ai_candidates"] if item["status"] == "ready")

    # 候选阶段：正式教案一个字都不能动。
    assert storage.course["course_teaching_plan"]["revision_id"] == "teaching-initial"

    accepted = await service.accept_ai_candidate(
        "course-1",
        actor="teacher-1",
        candidate_id=candidate["candidate_id"],
        operation_ids=[],
        idempotency_key="sec-accept",
    )
    assert accepted["draft"]["changed_paths"] == ["sections/section-1/learning_objective"]

    reviewed = await service.create_change_set(
        "course-1",
        actor="teacher-1",
        draft_id=draft_id,
        idempotency_key="sec-review",
    )
    change_set = next(item for item in reviewed["change_sets"] if item["status"] == "ready")
    applied = await service.apply_change_set(
        "course-1",
        actor="teacher-1",
        change_set_id=change_set["change_set_id"],
        idempotency_key="sec-apply",
    )

    # 小节目标的真源在 course_plan（目录），教案不另存一份——这正是
    # 「不建第二真源」的体现。应用时目录会按层级重排 node_id
    # （section-1 → L2-1-1），所以这里按位置断言，不按旧 id。
    outline_sections = storage.course["course_plan"]["chapters"][0]["sections"]
    assert [item["learning_objective"] for item in outline_sections] == [
        "能由任意两点求出斜率并解释其正负含义",
        "理解截距的含义",
    ], "只有被优化的第一节目标改变，第二节保持原样"

    sections = storage.course["course_teaching_plan"]["sections"]
    untouched = next(item for item in sections if item["node_id"] == "section-2")
    assert untouched == before_section_two, "分小节优化不得波及其他小节"
    assert storage.course["course_plan"]["positioning"] == before_positioning, "不得顺手改总体教案"

    # 正式教案仍然只有一份，且修订前进了一格。
    assert applied["workbench"]["current_plan_revision_id"] != view["current_plan_revision_id"]
    assert applied["workbench"]["draft"] is None
