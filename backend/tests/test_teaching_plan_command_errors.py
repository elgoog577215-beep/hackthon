"""四族结构化命令的错误码矩阵（tasks 2.7）。

2.1 总体字段 / 2.2 小节字段 / 2.3 教学模块 / 2.4 知识语义，每一族都要有
「通过、警告、阻断、过期、锁定冲突」的明确结果，错误码见
recovered/plan-baseline 的 contracts.md §9.1。

之前这些取值校验没有任何测试：上限、枚举、整数区间散落在 _write_path 的
十几个分支里，改动某一支不会让任何断言变红。这里把四族一次钉住，顺便
固定错误码本身——前端按 code 分支渲染文案，改码即破坏 UI。
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from course_document import CourseBlock, CourseDocument, CourseSection, refresh_document_revision
from course_repository import CourseDocumentRepository
from teaching_plan_workbench import (
    TeachingPlanWorkbenchError,
    TeachingPlanWorkbenchService,
)


class MemoryStorage:
    def __init__(self, course: dict) -> None:
        self.course = deepcopy(course)

    def load_course(self, _course_id: str) -> dict:
        return deepcopy(self.course)

    async def save_course(self, _course_id: str, data: dict) -> None:
        self.course = deepcopy(data)


def _section(node_id: str, title: str, objective: str, knowledge: str) -> dict:
    return {
        "node_id": node_id,
        "key_points": [knowledge],
        "reused_knowledge_names": [],
        "knowledge_relations": [],
        "learning_objective": objective,
        "knowledge_structure": [{
            "concept_group": "核心机制",
            "knowledge_points": [{
                "name": knowledge,
                "statement": f"{knowledge}的基本陈述。",
                "capability": f"能够解释{knowledge}",
                "conditions": ["在平面直角坐标系中"],
                "mastery_criteria": [{
                    "observable_performance": f"能应用{knowledge}",
                    "verification_method": "出口题",
                }],
                "misconceptions": [],
            }],
        }],
        "teaching_modules": [{
            "module_id": "core",
            "teaching_purpose": f"建立{knowledge}直觉",
            "knowledge_names": [knowledge],
            "teaching_guidance": f"先看例子，再归纳{knowledge}。",
        }],
    }


def _course() -> dict:
    document = refresh_document_revision(CourseDocument(
        course_id="course-1",
        title="一次函数",
        sections=[
            CourseSection(
                section_id="section-1", parent_section_id="chapter-1", title="斜率",
                position=0, level=2, learning_objective="理解斜率的变化意义",
            ),
            CourseSection(
                section_id="section-2", parent_section_id="chapter-1", title="截距",
                position=1, level=2, learning_objective="理解截距的含义",
            ),
        ],
        blocks=[CourseBlock(
            block_id="block-1", section_id="section-1", position=0,
            role="concept", payload={"markdown": "斜率描述变化率。"},
        )],
    ))
    outline_section = {
        "module_plan": [{
            "module_id": "core", "label": "核心讲解", "required": True,
            "output_contract": "解释概念", "prompt_instruction": "从图像和公式说明",
        }],
    }
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
                "sections": [
                    {"node_id": "section-1", "title": "斜率",
                     "learning_objective": "理解斜率的变化意义", **deepcopy(outline_section)},
                    {"node_id": "section-2", "title": "截距",
                     "learning_objective": "理解截距的含义", **deepcopy(outline_section)},
                ],
            }],
        },
        "generation_request": {"target_audience": "初中二年级学生"},
        "subject_pedagogy_profile": {"rationale": "先观察图像，再归纳公式。"},
        "course_teaching_plan": {
            "schema_version": "course_teaching_plan_v3",
            "source_outline_revision_id": "outline-1",
            "revision_id": "teaching-initial",
            "sections": [
                _section("section-1", "斜率", "理解斜率的变化意义", "斜率"),
                _section("section-2", "截距", "理解截距的含义", "截距"),
            ],
        },
        "generation_stage_artifacts": {"course_teaching_plan": {"status": "completed"}},
    }




async def _open_draft(service: TeachingPlanWorkbenchService, actor: str = "teacher-1") -> str:
    view = service.view("course-1", actor=actor)
    created = await service.create_draft(
        "course-1",
        actor=actor,
        idempotency_key=f"create-{actor}",
        base_plan_revision_id=view["current_plan_revision_id"],
        base_course_document_revision=view["course_document_revision"],
    )
    return created["draft"]["draft_id"]


KNOWLEDGE = "sections/section-1/knowledge/斜率"
MODULE = "sections/section-1/teaching_modules/core"

# (标签, 路径, 取值, 期望错误码)
REJECTED_VALUES = [
    # 2.1 总体字段
    ("总体文本超长", "overall/positioning", "x" * 2500, "teaching_plan_invalid_value"),
    ("总体目标清空", "overall/learning_objectives", [], "teaching_plan_invalid_value"),
    ("总体目标超上限", "overall/learning_objectives",
     [f"目标{index}" for index in range(20)], "teaching_plan_value_too_long"),
    ("总课时越界", "overall/total_class_hours", 0, "teaching_plan_invalid_value"),
    ("总课时非整数", "overall/total_class_hours", "十六", "teaching_plan_invalid_value"),
    ("单次时长越界", "overall/lesson_duration_minutes", 600, "teaching_plan_invalid_value"),
    ("授课场景枚举非法", "overall/teaching_context", "hybrid", "teaching_plan_invalid_value"),
    ("班级人数越界", "overall/class_size", 99999, "teaching_plan_invalid_value"),
    # 2.2 小节字段
    ("小节时长越界", "sections/section-1/planned_minutes", 999, "teaching_plan_invalid_value"),
    ("小节列表超上限", "sections/section-1/homework",
     [f"作业{index}" for index in range(40)], "teaching_plan_value_too_long"),
    ("教学资源超上限", "sections/section-1/resource_refs",
     [f"资源{index}" for index in range(40)], "teaching_plan_value_too_long"),
    # 2.3 教学模块
    ("环节时长为负", f"{MODULE}/planned_minutes", -5, "teaching_plan_invalid_value"),
    ("环节说明清空", f"{MODULE}/teaching_guidance", "", "teaching_plan_invalid_value"),
    # 2.4 知识语义
    ("知识陈述清空", f"{KNOWLEDGE}/statement", "", "teaching_plan_invalid_value"),
    ("知识条件超上限", f"{KNOWLEDGE}/conditions",
     [f"条件{index}" for index in range(20)], "teaching_plan_value_too_long"),
]

# 路径不存在：四族都必须给同一个可分辨的错误码，不能变成 KeyError/500。
MISSING_PATHS = [
    ("不存在的小节", "sections/does-not-exist/learning_objective"),
    ("不存在的教学环节", "sections/section-1/teaching_modules/does-not-exist/teaching_guidance"),
    ("不存在的知识点", "sections/section-1/knowledge/并不存在的知识点/statement"),
    ("不存在的总体字段", "overall/not_a_real_field"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "label,path,value,expected_code",
    REJECTED_VALUES,
    ids=[case[0] for case in REJECTED_VALUES],
)
async def test_invalid_values_are_rejected_with_a_structured_code(
    label: str, path: str, value, expected_code: str,
) -> None:
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service)
    before_official = deepcopy(storage.course["course_teaching_plan"])

    with pytest.raises(TeachingPlanWorkbenchError) as error:
        await service.patch_draft(
            "course-1",
            actor="teacher-1",
            draft_id=draft_id,
            path=path,
            value=value,
            expected_value_hash="",
            base_plan_revision_id="",
            idempotency_key=f"invalid-{label}",
        )

    assert error.value.code == expected_code, label
    # 被拒绝的取值不得留在草稿里，更不得碰正式教案。
    assert storage.course["teaching_plan_workbench"]["drafts"]["teacher-1"]["changed_paths"] == []
    assert storage.course["course_teaching_plan"] == before_official


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "label,path", MISSING_PATHS, ids=[case[0] for case in MISSING_PATHS],
)
async def test_missing_paths_report_path_not_found_instead_of_crashing(
    label: str, path: str,
) -> None:
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service)

    with pytest.raises(TeachingPlanWorkbenchError) as error:
        await service.patch_draft(
            "course-1",
            actor="teacher-1",
            draft_id=draft_id,
            path=path,
            value="任意值",
            expected_value_hash="",
            base_plan_revision_id="",
            idempotency_key=f"missing-{label}",
        )

    # overall/not_a_real_field 不在白名单里，先被只读兜底接住；
    # 其余三条是路径定位失败。两者都必须是结构化领域错误。
    assert error.value.code in {
        "teaching_plan_path_not_found",
        "teaching_plan_readonly_field",
    }, label


@pytest.mark.asyncio
async def test_each_command_family_has_a_passing_case() -> None:
    """四族都要有明确的「通过」路径，否则上面全是拒绝、等于没验证正向。"""
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service)

    accepted = {
        "overall/positioning": "从真实变化情境理解一次函数",
        "sections/section-1/homework": ["完成两道斜率练习"],
        f"{MODULE}/teaching_guidance": "先比较两段路程，再归纳公式。",
        f"{KNOWLEDGE}/boundaries": ["不适用于垂直直线"],
    }
    for index, (path, value) in enumerate(accepted.items()):
        await service.patch_draft(
            "course-1",
            actor="teacher-1",
            draft_id=draft_id,
            path=path,
            value=value,
            expected_value_hash="",
            base_plan_revision_id="",
            idempotency_key=f"accepted-{index}",
        )

    changed = storage.course["teaching_plan_workbench"]["drafts"]["teacher-1"]["changed_paths"]
    assert set(changed) == set(accepted)
    # 四族全部通过校验，草稿整体可用。
    review = service.review_draft("course-1", actor="teacher-1", draft_id=draft_id)
    assert review["validation"]["passed"] is True


@pytest.mark.asyncio
async def test_expired_draft_rejects_every_command_family() -> None:
    """过期草稿对四族一视同仁地拒绝，不能有某一族绕过去。"""
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service)

    # 直接把草稿标记为已过期，模拟 TTL 到期。
    storage.course["teaching_plan_workbench"]["drafts"]["teacher-1"]["expires_at"] = (
        "2000-01-01T00:00:00+00:00"
    )

    for index, path in enumerate((
        "overall/positioning",
        "sections/section-1/homework",
        f"{MODULE}/teaching_guidance",
        f"{KNOWLEDGE}/boundaries",
    )):
        with pytest.raises(TeachingPlanWorkbenchError) as error:
            await service.patch_draft(
                "course-1",
                actor="teacher-1",
                draft_id=draft_id,
                path=path,
                value=["值"] if path.endswith(("homework", "boundaries")) else "值",
                expected_value_hash="",
                base_plan_revision_id="",
                idempotency_key=f"expired-{index}",
            )
        assert error.value.code == "teaching_plan_draft_expired", path


@pytest.mark.asyncio
async def test_warning_status_passes_but_surfaces_issues() -> None:
    """2.7「警告」：不阻断应用，但必须把问题带出来给教师看。

    警告与阻断的区别是产品判断，不是实现细节：课时对不上要提醒，
    但不该拦住教师保存；结构缺失才拦。两者混同会让教师要么被无谓拦下、
    要么把真问题带进正式修订。
    """
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service)

    # 总课时远超各小节计划时长之和：可疑但不致命。
    await service.patch_draft(
        "course-1",
        actor="teacher-1",
        draft_id=draft_id,
        path="overall/total_class_hours",
        value=40,
        expected_value_hash="",
        base_plan_revision_id="",
        idempotency_key="warning-hours",
    )

    review = service.review_draft("course-1", actor="teacher-1", draft_id=draft_id)
    validation = review["validation"]
    assert validation["status"] == "warning"
    assert validation["passed"] is True, "警告不得阻断应用"
    assert any(not issue.get("blocking") for issue in validation["issues"])

    # 带警告的草稿仍然可以生成 ready 变更集并应用。
    reviewed = await service.create_change_set(
        "course-1", actor="teacher-1", draft_id=draft_id, idempotency_key="warning-review",
    )
    change_set = next(item for item in reviewed["change_sets"] if item["status"] == "ready")
    await service.apply_change_set(
        "course-1", actor="teacher-1",
        change_set_id=change_set["change_set_id"], idempotency_key="warning-apply",
    )
    assert storage.course["course_teaching_plan"]["revision_id"] != "teaching-initial"


@pytest.mark.asyncio
async def test_lock_conflict_surfaces_as_a_structured_conflict_not_a_crash() -> None:
    """2.7「锁定冲突」：底层写冲突要变成结构化冲突，不能漏成 500。

    course_repository 在并发写同一课程时抛 CourseDocumentConflict。
    工作台自己不吞这个异常——它必须一路冒到 HTTP 边界并映射为 409，
    否则教师看到的是「服务器错误」而不是「有人同时在改，请重试」。
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from course_repository import CourseDocumentConflict
    from routers import teaching_plan_workbench as workbench_router

    storage = MemoryStorage(_course())
    repository = CourseDocumentRepository(storage)
    app = FastAPI()
    app.include_router(workbench_router.router, prefix="/api")
    app.dependency_overrides[workbench_router.get_course_document_repository] = lambda: repository
    client = TestClient(app, raise_server_exceptions=False)
    headers = {"X-User-Id": "teacher-lock"}
    base_path = "/api/courses/course-1/teaching-plan"

    workbench = client.get(f"{base_path}/workbench", headers=headers).json()["workbench"]
    draft = client.post(f"{base_path}/drafts", headers=headers, json={
        "base_plan_revision_id": workbench["current_plan_revision_id"],
        "base_course_document_revision": workbench["course_document_revision"],
        "idempotency_key": "lock-create",
    }).json()["workbench"]["draft"]

    async def conflicting_command(*_args, **_kwargs):
        raise CourseDocumentConflict("course is locked by another writer")

    repository.apply_metadata_command = conflicting_command

    response = client.patch(f"{base_path}/drafts/{draft['draft_id']}", headers=headers, json={
        "path": "overall/positioning",
        "value": "并发写入时的定位",
        "base_plan_revision_id": draft["base_plan_revision_id"],
        "idempotency_key": "lock-patch",
    })

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "course_document_conflict"
