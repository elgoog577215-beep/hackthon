"""结构操作走目录真源：教案命令不得绕过 CourseDocument。

对应 ~/dev-requirements/upgrade-teaching-plan-workbench.md 的 tasks 2.5 与
spec「教师尝试修改章节结构」场景，合同见 recovered/plan-baseline 分支的
contracts.md §4.1（返回体）与 §9.2（错误码 + HTTP 409）。

`CourseDocument + ordered CourseBlock[]` 是课程结构真源。章节/小节的增删、
排序与标题属于目录，教案只描述「怎么教」。这条边界如果只靠「教案里没有
这个字段」被动兜住，就会退化成一句无信息的「暂不支持编辑」——教师不知道
该去哪里改，前端也拿不到目录修订去跳转。
"""
from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from course_document import CourseBlock, CourseDocument, CourseSection, refresh_document_revision
from course_repository import CourseDocumentRepository
from teaching_plan_workbench import (
    TeachingPlanWorkbenchError,
    TeachingPlanWorkbenchService,
    field_permission,
    outline_redirect_reason,
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


def _official(storage: MemoryStorage) -> dict:
    return deepcopy({
        "course_plan": storage.course["course_plan"],
        "course_teaching_plan": storage.course["course_teaching_plan"],
    })


async def _open_draft(service: TeachingPlanWorkbenchService, actor: str) -> str:
    view = service.view("course-1", actor=actor)
    created = await service.create_draft(
        "course-1",
        actor=actor,
        idempotency_key=f"create-{actor}",
        base_plan_revision_id=view["current_plan_revision_id"],
        base_course_document_revision=view["course_document_revision"],
    )
    return created["draft"]["draft_id"]


# --- 判定本身 ---------------------------------------------------------------


def test_outline_owned_paths_are_recognised_and_teaching_paths_are_not() -> None:
    """目录拥有的是「有哪些节、什么顺序、叫什么」，不是「怎么教」。"""
    for path in (
        "course_plan/chapters",
        "chapters/chapter-1/title",
        "outline/sections",
        "sections/section-1/position",
        "sections/section-1/title",
        "sections/section-1/level",
        "sections/section-1/parent_section_id",
    ):
        assert outline_redirect_reason(path), f"{path} 应当回到目录编辑器"

    # 这些是教案自己的字段，必须继续可编辑，不能被重定向误伤。
    for path in (
        "overall/positioning",
        "sections/section-1/learning_objective",
        "sections/section-1/key_points",
        "sections/section-1/teaching_modules/core/teaching_guidance",
        "sections/section-1/knowledge/斜率/statement",
    ):
        assert not outline_redirect_reason(path), f"{path} 是教案字段，不该被重定向"
        assert field_permission(path)["state"] != "readonly"


def test_chapter_permission_carries_the_redirect_marker() -> None:
    permission = field_permission("course_plan/chapters")
    assert permission["state"] == "readonly"
    assert permission["redirect"] == "redirect_to_outline_edit"


# --- 领域层 -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_structural_patch_returns_redirect_with_the_current_outline_revision() -> None:
    """spec：MUST 返回 redirect_to_outline_edit 与当前目录修订信息。"""
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service, "teacher-1")
    before = _official(storage)
    outline_revision = storage.course["course_document_revision"]

    for index, path in enumerate((
        "course_plan/chapters",
        "chapters/chapter-1/title",
        "sections/section-1/position",
    )):
        with pytest.raises(TeachingPlanWorkbenchError) as error:
            await service.patch_draft(
                "course-1",
                actor="teacher-1",
                draft_id=draft_id,
                path=path,
                value="不应写入教案",
                expected_value_hash="",
                base_plan_revision_id="",
                idempotency_key=f"structural-{index}",
            )
        assert error.value.code == "redirect_to_outline_edit"
        assert error.value.details["outline_revision_id"] == outline_revision
        assert error.value.details["course_id"] == "course-1"
        assert error.value.details["path"] == path

    # 被拒绝的结构操作不得在草稿或正式教案里留下任何痕迹。
    assert _official(storage) == before
    draft = storage.course["teaching_plan_workbench"]["drafts"]["teacher-1"]
    assert draft["changed_paths"] == []
    assert draft["operations"] == []


@pytest.mark.asyncio
async def test_redirect_does_not_block_teaching_edits_in_the_same_draft() -> None:
    """拒绝结构操作之后，同一份草稿仍能继续正常编辑教案字段。"""
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service, "teacher-1")

    with pytest.raises(TeachingPlanWorkbenchError):
        await service.patch_draft(
            "course-1",
            actor="teacher-1",
            draft_id=draft_id,
            path="sections/section-1/title",
            value="改标题应当回目录",
            expected_value_hash="",
            base_plan_revision_id="",
            idempotency_key="structural-title",
        )

    updated = await service.patch_draft(
        "course-1",
        actor="teacher-1",
        draft_id=draft_id,
        path="sections/section-1/learning_objective",
        value="能由两点求斜率并解释正负",
        expected_value_hash="",
        base_plan_revision_id="",
        idempotency_key="teaching-after-redirect",
    )
    assert updated["draft"]["changed_paths"] == ["sections/section-1/learning_objective"]


# --- HTTP 边界 --------------------------------------------------------------


def test_router_maps_redirect_to_409_with_the_outline_revision() -> None:
    """contracts.md §9.2：redirect_to_outline_edit → HTTP 409。"""
    from routers import teaching_plan_workbench as workbench_router

    storage = MemoryStorage(_course())
    repository = CourseDocumentRepository(storage)
    app = FastAPI()
    app.include_router(workbench_router.router, prefix="/api")
    app.dependency_overrides[workbench_router.get_course_document_repository] = lambda: repository
    client = TestClient(app)
    headers = {"X-User-Id": "teacher-http"}
    base_path = "/api/courses/course-1/teaching-plan"

    workbench = client.get(f"{base_path}/workbench", headers=headers).json()["workbench"]
    draft = client.post(f"{base_path}/drafts", headers=headers, json={
        "base_plan_revision_id": workbench["current_plan_revision_id"],
        "base_course_document_revision": workbench["course_document_revision"],
        "idempotency_key": "http-create",
    }).json()["workbench"]["draft"]

    response = client.patch(f"{base_path}/drafts/{draft['draft_id']}", headers=headers, json={
        "path": "course_plan/chapters",
        "value": "不应写入教案",
        "base_plan_revision_id": draft["base_plan_revision_id"],
        "idempotency_key": "http-structural",
    })

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "redirect_to_outline_edit"
    assert detail["outline_revision_id"] == workbench["course_document_revision"]
    assert detail["course_id"] == "course-1"


def test_redirect_points_at_the_real_outline_editor_endpoint() -> None:
    """重定向要能真的把教师送到目录编辑器，不只是说一句「去目录改」。

    团队在 main 上新增了 /blueprint 目录编辑器（course_outline_adjustments）。
    这里钉住两件事：
    1. 重定向给出可跳转的 endpoint，而不是让前端自己猜；
    2. 明确 outline_revision_id 与蓝图自己的 blueprint_revision_id 是**两个
       不同的标识**——教案侧给的是 course_document_revision（cdr_…），
       蓝图编辑器用的是 bp_…。前端若把前者当蓝图修订回传，会被
       blueprint_base_conflict 挡下。所以只暴露该去哪读，不暴露一个会被误用的值。
    """
    from routers import teaching_plan_workbench as workbench_router

    storage = MemoryStorage(_course())
    repository = CourseDocumentRepository(storage)
    app = FastAPI()
    app.include_router(workbench_router.router, prefix="/api")
    app.dependency_overrides[workbench_router.get_course_document_repository] = lambda: repository
    client = TestClient(app)
    headers = {"X-User-Id": "teacher-redirect"}
    base_path = "/api/courses/course-1/teaching-plan"

    workbench = client.get(f"{base_path}/workbench", headers=headers).json()["workbench"]
    draft = client.post(f"{base_path}/drafts", headers=headers, json={
        "base_plan_revision_id": workbench["current_plan_revision_id"],
        "base_course_document_revision": workbench["course_document_revision"],
        "idempotency_key": "redirect-endpoint-create",
    }).json()["workbench"]["draft"]

    response = client.patch(f"{base_path}/drafts/{draft['draft_id']}", headers=headers, json={
        "path": "course_plan/chapters",
        "value": "不应写入教案",
        "base_plan_revision_id": draft["base_plan_revision_id"],
        "idempotency_key": "redirect-endpoint-patch",
    })
    assert response.status_code == 409
    detail = response.json()["detail"]
    editor = detail["outline_editor"]
    assert editor["endpoint"] == "/api/courses/course-1/blueprint"
    assert editor["revision_field"] == "current_blueprint_revision_id"
    # 教案侧的目录修订仍然给出，但它不是蓝图修订。
    assert detail["outline_revision_id"] == workbench["course_document_revision"]
    assert not detail["outline_revision_id"].startswith("bp_")
