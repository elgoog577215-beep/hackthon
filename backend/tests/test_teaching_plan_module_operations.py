"""教学环节的增删、替换与排序（tasks 2.3）。

合同见 recovered/plan-baseline 的 contracts.md §4.2：这些操作在教案范围
内，不涉及目录真源；必需环节来自学科模板的
course_plan.chapters[].sections[].module_plan[].required，删除必需环节
必须结构质量阻断（spec「模块删除导致必需课程块缺失」）。

设计取舍：用一条有序 module_id 列表路径
`sections/<node_id>/teaching_modules` 同时表达新增、删除、替换与排序，
而不是四个平行命令。理由是这样 module_id 天然保持稳定（§4.2 要求），
并且复用既有的草稿 patch / 幂等 / 冲突模型，不另建一套命令通道。
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from course_document import CourseBlock, CourseDocument, CourseSection, refresh_document_revision
from course_repository import CourseDocumentRepository
from teaching_plan_workbench import (
    TeachingPlanWorkbenchError,
    TeachingPlanWorkbenchService,
    field_permission,
)


class MemoryStorage:
    def __init__(self, course: dict) -> None:
        self.course = deepcopy(course)

    def load_course(self, _course_id: str) -> dict:
        return deepcopy(self.course)

    async def save_course(self, _course_id: str, data: dict) -> None:
        self.course = deepcopy(data)


MODULE_PLAN = [
    {
        "module_id": "core",
        "label": "核心讲解",
        "required": True,
        "output_contract": "解释斜率",
        "prompt_instruction": "从图像和公式说明斜率",
    },
    {
        "module_id": "practice",
        "label": "随堂练习",
        "required": False,
        "output_contract": "当堂检验掌握情况",
        "prompt_instruction": "给两道出口题",
    },
    {
        "module_id": "warmup",
        "label": "情境导入",
        "required": False,
        "output_contract": "用真实情境引入变化率",
        "prompt_instruction": "从行程问题切入",
    },
]


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
                    "module_plan": deepcopy(MODULE_PLAN),
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


ORDER_PATH = "sections/section-1/teaching_modules"


def _draft_modules(storage: MemoryStorage, actor: str = "teacher-1") -> list[dict]:
    snapshot = storage.course["teaching_plan_workbench"]["drafts"][actor]["snapshot"]
    return snapshot["course_teaching_plan"]["sections"][0]["teaching_modules"]


def _official_modules(storage: MemoryStorage) -> list[dict]:
    return storage.course["course_teaching_plan"]["sections"][0]["teaching_modules"]


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


async def _set_order(
    service: TeachingPlanWorkbenchService,
    draft_id: str,
    order: list[str],
    key: str,
) -> dict:
    return await service.patch_draft(
        "course-1",
        actor="teacher-1",
        draft_id=draft_id,
        path=ORDER_PATH,
        value=order,
        expected_value_hash="",
        base_plan_revision_id="",
        idempotency_key=key,
    )


def test_module_order_path_is_editable_but_module_id_itself_is_not() -> None:
    assert field_permission(ORDER_PATH)["state"] == "requires_impact_review"
    # 稳定 ID 不可写：排序只改顺序，不改身份（contracts §4.2）。
    assert field_permission(f"{ORDER_PATH}/core/module_id")["state"] == "readonly"


def test_order_path_is_exposed_to_the_workbench() -> None:
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    view = service.view("course-1", actor="teacher-1")
    assert any(field["path"] == ORDER_PATH for field in view["editable_fields"])


@pytest.mark.asyncio
async def test_adding_and_reordering_modules_keeps_existing_content_intact() -> None:
    """已有环节按 id 原样搬运，不因为排序而重建内容。"""
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service)

    await _set_order(service, draft_id, ["warmup", "core", "practice"], "reorder-1")

    modules = _draft_modules(storage)
    assert [item["module_id"] for item in modules] == ["warmup", "core", "practice"]
    # 原有 core 的教学职责与指导必须原样保留。
    core = next(item for item in modules if item["module_id"] == "core")
    assert core["teaching_purpose"] == "建立变化率直觉"
    assert core["teaching_guidance"] == "先比较两段路程，再归纳斜率公式。"
    assert core["knowledge_names"] == ["斜率"]
    # 新增环节从模板取初始职责，不留空。
    warmup = next(item for item in modules if item["module_id"] == "warmup")
    assert warmup["teaching_purpose"] == "用真实情境引入变化率"


@pytest.mark.asyncio
async def test_removing_an_optional_module_is_allowed() -> None:
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service)

    await _set_order(service, draft_id, ["core", "practice", "warmup"], "add-all")
    await _set_order(service, draft_id, ["core", "warmup"], "drop-practice")

    assert [item["module_id"] for item in _draft_modules(storage)] == ["core", "warmup"]


@pytest.mark.asyncio
async def test_removing_a_required_module_is_blocked_and_leaves_the_plan_untouched() -> None:
    """spec：删除模板要求的必需模块 MUST 返回结构质量阻断。"""
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service)
    before_official = deepcopy(storage.course["course_teaching_plan"])
    before_draft = deepcopy(_draft_modules(storage))

    with pytest.raises(TeachingPlanWorkbenchError) as error:
        await _set_order(service, draft_id, ["practice"], "drop-required")

    assert error.value.code == "teaching_plan_quality_blocked"
    assert error.value.details["missing_required_module_ids"] == ["core"]
    # 正式教案保持原修订，草稿也不能留下半写入的顺序。
    assert storage.course["course_teaching_plan"] == before_official
    assert _draft_modules(storage) == before_draft


@pytest.mark.asyncio
async def test_module_outside_the_subject_template_is_rejected() -> None:
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service)

    with pytest.raises(TeachingPlanWorkbenchError) as error:
        await _set_order(service, draft_id, ["core", "invented"], "unknown-module")

    assert error.value.code == "teaching_plan_invalid_value"
    assert error.value.details["unknown_module_ids"] == ["invented"]


@pytest.mark.asyncio
async def test_module_change_reaches_the_official_plan_only_after_apply() -> None:
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    view = service.view("course-1", actor="teacher-1")
    draft_id = await _open_draft(service)

    await _set_order(service, draft_id, ["warmup", "core"], "apply-order")
    # 应用前正式教案只有原来那一个环节。
    assert [item["module_id"] for item in _official_modules(storage)] == ["core"]

    reviewed = await service.create_change_set(
        "course-1",
        actor="teacher-1",
        draft_id=draft_id,
        idempotency_key="module-review",
    )
    change_set = next(item for item in reviewed["change_sets"] if item["status"] == "ready")
    # 环节结构变化必须要求重建本节派生表达。
    regenerated = {item["type"] for item in change_set["impact_report"]["needs_regeneration"]}
    assert {"section_content", "lecture", "slide_deck"} <= regenerated

    applied = await service.apply_change_set(
        "course-1",
        actor="teacher-1",
        change_set_id=change_set["change_set_id"],
        idempotency_key="module-apply",
    )
    assert [item["module_id"] for item in _official_modules(storage)] == ["warmup", "core"]
    assert applied["workbench"]["current_plan_revision_id"] != view["current_plan_revision_id"]


@pytest.mark.asyncio
async def test_downstream_rebuild_endpoint_reaches_the_repository_command() -> None:
    """重建入口必须真的能提交到仓库命令。

    纯单测最初漏掉了这条：execute_rebuild 本身 15 个用例全绿，但
    rebuild_downstream 调 apply_metadata_command 时把关键字写成了 mutate
    （真名是 mutation），真机一调就 500。这类"接线错"只有走完整条链才暴露，
    所以这里从 service 层调进去，确保参数名对得上。
    """
    from downstream_rebuild import execute_rebuild
    from teaching_plan_impact import build_downstream_state

    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))

    # 先造出一份有待重建对象的下游状态
    impact = {
        "changed": [], "needs_regeneration": [
            {"type": "slide_deck", "id": "section-1", "reason": "教案变更"},
        ],
        "stale": [], "unchanged": [], "blocked": [], "blocking": False,
    }
    raw = storage.course
    raw.setdefault("teaching_plan_workbench", {})["downstream"] = build_downstream_state(
        impact, plan_revision_id="tpr_seed",
    )

    result = await service.rebuild_downstream(
        "course-1", actor="teacher-1", idempotency_key="rebuild-1",
    )
    assert result["receipts"], "必须返回逐对象回执"
    # 回执与下游状态都要真的落盘，不能只在内存里
    persisted = storage.course["teaching_plan_workbench"]
    assert persisted.get("rebuild_receipts")
    assert persisted["downstream"]["items"]


@pytest.mark.asyncio
async def test_rebuild_without_downstream_work_is_rejected_clearly() -> None:
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    with pytest.raises(TeachingPlanWorkbenchError) as error:
        await service.rebuild_downstream(
            "course-1", actor="teacher-1", idempotency_key="rebuild-empty",
        )
    assert error.value.code == "teaching_plan_no_downstream_work"
