"""分小节二次编辑的并发保护与「失败不污染正式教案」（需求 5 收尾）。

已有的 test_teaching_plan_draft_repository.py 在**总体字段**层面覆盖了
过期、冲突、幂等与半写入保护。本文件补的是**分小节**这一层：需求 5 的
卖点是「分小节优化和二次编辑」，那么两位教师同时改**不同小节**必须都
能落盘，同时改**同一小节同一字段**必须冲突，而任何一种失败都不能让正式
教案进入半更新状态——尤其是一份草稿里同时改了多节、其中一节非法时。

跨小节隔离是这里最容易出错的地方：如果实现按「整节替换」而不是按路径
patch，A 老师改第一节就会把 B 老师刚改完的第二节一起写回旧值，而且不会
报任何错。
"""
from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from course_document import CourseBlock, CourseDocument, CourseSection, refresh_document_revision
from course_repository import CourseDocumentRepository
from teaching_plan_workbench import (
    TeachingPlanWorkbenchError,
    TeachingPlanWorkbenchService,
    _value_hash,
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
                # 已完成知识库编译的知识点带稳定 ID；7.3 据此放行结构字段编辑。
                "knowledge_id": f"k-{knowledge}",
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


def _official(storage: MemoryStorage) -> dict:
    return deepcopy({
        "course_plan": storage.course["course_plan"],
        "course_teaching_plan": storage.course["course_teaching_plan"],
    })


def _outline_objectives(storage: MemoryStorage) -> list[str]:
    return [
        item["learning_objective"]
        for item in storage.course["course_plan"]["chapters"][0]["sections"]
    ]


async def _open_draft(
    service: TeachingPlanWorkbenchService,
    actor: str,
    key: str = "1",
) -> str:
    # 幂等键必须每轮不同：同一个键会被操作日志判为重放，直接返回原回执。
    view = service.view("course-1", actor=actor)
    created = await service.create_draft(
        "course-1",
        actor=actor,
        idempotency_key=f"create-{actor}-{key}",
        base_plan_revision_id=view["current_plan_revision_id"],
        base_course_document_revision=view["course_document_revision"],
    )
    return created["draft"]["draft_id"]


async def _patch(
    service: TeachingPlanWorkbenchService,
    *,
    actor: str,
    draft_id: str,
    path: str,
    value,
    key: str,
    expected_value_hash: str = "",
):
    return await service.patch_draft(
        "course-1",
        actor=actor,
        draft_id=draft_id,
        path=path,
        value=value,
        expected_value_hash=expected_value_hash,
        base_plan_revision_id="",
        idempotency_key=key,
    )


# --- 跨小节隔离 --------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_edits_to_different_sections_both_survive() -> None:
    """两位教师同时改不同小节：两份改动都必须落盘，互不覆盖。"""
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    first = await _open_draft(service, "teacher-1")
    second = await _open_draft(service, "teacher-2")

    await asyncio.gather(
        _patch(
            service, actor="teacher-1", draft_id=first,
            path="sections/section-1/learning_objective",
            value="能由两点求斜率并解释正负", key="s1",
        ),
        _patch(
            service, actor="teacher-2", draft_id=second,
            path="sections/section-2/learning_objective",
            value="能由图像读出截距", key="s2",
        ),
    )

    drafts = storage.course["teaching_plan_workbench"]["drafts"]
    assert drafts["teacher-1"]["changed_paths"] == ["sections/section-1/learning_objective"]
    assert drafts["teacher-2"]["changed_paths"] == ["sections/section-2/learning_objective"]
    # 每份草稿只看见自己那一节的改动，不含对方的。
    first_snapshot = drafts["teacher-1"]["snapshot"]["course_plan"]["chapters"][0]["sections"]
    assert first_snapshot[0]["learning_objective"] == "能由两点求斜率并解释正负"
    assert first_snapshot[1]["learning_objective"] == "理解截距的含义"


@pytest.mark.asyncio
async def test_applying_one_section_does_not_roll_back_another() -> None:
    """连续应用两节的改动：后一次不得把前一次写回旧值。"""
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))

    async def edit_and_apply(position: int, objective: str, tag: str) -> None:
        # 目录归一化会重编 node_id，所以每轮都从当前目录按位置取当前 ID，
        # 不能记住上一轮的旧 ID——这正是二次编辑的真实处境。
        section_id = storage.course["course_plan"]["chapters"][0]["sections"][position]["node_id"]
        draft_id = await _open_draft(service, f"teacher-{tag}")
        await _patch(
            service, actor=f"teacher-{tag}", draft_id=draft_id,
            path=f"sections/{section_id}/learning_objective",
            value=objective, key=f"patch-{tag}",
        )
        reviewed = await service.create_change_set(
            "course-1", actor=f"teacher-{tag}", draft_id=draft_id,
            idempotency_key=f"review-{tag}",
        )
        change_set = next(
            item for item in reviewed["change_sets"] if item["status"] == "ready"
        )
        await service.apply_change_set(
            "course-1", actor=f"teacher-{tag}",
            change_set_id=change_set["change_set_id"],
            idempotency_key=f"apply-{tag}",
        )

    await edit_and_apply(0, "能由两点求斜率并解释正负", "a")
    await edit_and_apply(1, "能由图像读出截距", "b")

    # 目录会按层级重排 node_id，按位置断言。
    assert _outline_objectives(storage) == [
        "能由两点求斜率并解释正负",
        "能由图像读出截距",
    ]


# --- 同一小节的字段级并发 ----------------------------------------------------


@pytest.mark.asyncio
async def test_two_writers_on_the_same_section_field_conflict_and_keep_the_first() -> None:
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service, "teacher-1")
    shared_hash = _value_hash("理解斜率的变化意义")

    await _patch(
        service, actor="teacher-1", draft_id=draft_id,
        path="sections/section-1/learning_objective",
        value="第一个页面写入的目标", key="writer-1",
        expected_value_hash=shared_hash,
    )
    with pytest.raises(TeachingPlanWorkbenchError) as conflict:
        await _patch(
            service, actor="teacher-1", draft_id=draft_id,
            path="sections/section-1/learning_objective",
            value="第二个页面写入的目标", key="writer-2",
            expected_value_hash=shared_hash,
        )

    assert conflict.value.code == "teaching_plan_field_conflict"
    assert conflict.value.details["current_value"] == "第一个页面写入的目标"
    review = service.review_draft("course-1", actor="teacher-1", draft_id=draft_id)
    kept = next(
        item for item in review["diff"]["operations"]
        if item["path"] == "sections/section-1/learning_objective"
    )
    assert kept["after"] == "第一个页面写入的目标"


# --- 失败不污染正式教案 ------------------------------------------------------


@pytest.mark.asyncio
async def test_one_invalid_edit_does_not_persist_the_valid_ones_from_the_same_call() -> None:
    """同一份草稿里改了多节，其中一节非法：正式教案与草稿都不得半更新。"""
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service, "teacher-1")

    await _patch(
        service, actor="teacher-1", draft_id=draft_id,
        path="sections/section-1/learning_objective",
        value="第一节的合法改动", key="valid-1",
    )
    before_official = _official(storage)
    before_draft = deepcopy(storage.course["teaching_plan_workbench"]["drafts"]["teacher-1"])

    # 必需环节被删：草稿层就阻断。
    with pytest.raises(TeachingPlanWorkbenchError) as blocked:
        await _patch(
            service, actor="teacher-1", draft_id=draft_id,
            path="sections/section-2/teaching_modules",
            value=[], key="invalid-1",
        )
    assert blocked.value.code == "teaching_plan_quality_blocked"

    # 先前的合法改动仍在草稿里；非法那一笔一点痕迹都没留下。
    after_draft = storage.course["teaching_plan_workbench"]["drafts"]["teacher-1"]
    assert after_draft == before_draft
    assert after_draft["changed_paths"] == ["sections/section-1/learning_objective"]
    assert _official(storage) == before_official


@pytest.mark.asyncio
async def test_blocked_change_set_leaves_every_section_on_the_old_revision() -> None:
    """校验不通过的变更集不得部分落地：两节都必须停在旧修订。"""
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    view = service.view("course-1", actor="teacher-1")
    draft_id = await _open_draft(service, "teacher-1")

    await _patch(
        service, actor="teacher-1", draft_id=draft_id,
        path="sections/section-1/learning_objective",
        value="第一节改好的目标", key="p1",
    )
    # 让整份教案结构失效：把第二节的知识陈述清空会被质量门挡下。
    with pytest.raises(TeachingPlanWorkbenchError):
        await _patch(
            service, actor="teacher-1", draft_id=draft_id,
            path="sections/section-2/knowledge/截距/statement",
            value="", key="p2",
        )

    before = _official(storage)
    reviewed = await service.create_change_set(
        "course-1", actor="teacher-1", draft_id=draft_id, idempotency_key="review",
    )
    change_set = reviewed["change_sets"][-1]

    if change_set["status"] == "ready":
        # 只有第一节的合法改动，应用后第二节必须原样不动。
        await service.apply_change_set(
            "course-1", actor="teacher-1",
            change_set_id=change_set["change_set_id"], idempotency_key="apply",
        )
        assert _outline_objectives(storage)[1] == "理解截距的含义"
        # node_id 会随目录归一化重编，比内容不比 ID。
        untouched = deepcopy(storage.course["course_teaching_plan"]["sections"][1])
        original = deepcopy(before["course_teaching_plan"]["sections"][1])
        untouched.pop("node_id", None)
        original.pop("node_id", None)
        assert untouched == original
    else:
        # 被阻断：正式教案必须完全保持原修订。
        assert _official(storage) == before
        assert (
            service.view("course-1", actor="teacher-1")["current_plan_revision_id"]
            == view["current_plan_revision_id"]
        )


@pytest.mark.asyncio
async def test_discarding_a_section_draft_restores_nothing_and_breaks_nothing() -> None:
    """放弃分小节草稿：正式教案与其他小节都不受影响。"""
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service, "teacher-1")
    before = _official(storage)

    for index, (section_id, value) in enumerate((
        ("section-1", "草稿里的第一节目标"),
        ("section-2", "草稿里的第二节目标"),
    )):
        await _patch(
            service, actor="teacher-1", draft_id=draft_id,
            path=f"sections/{section_id}/learning_objective",
            value=value, key=f"discard-{index}",
        )

    await service.discard_draft(
        "course-1", actor="teacher-1", draft_id=draft_id, idempotency_key="discard",
    )

    assert _official(storage) == before
    assert service.view("course-1", actor="teacher-1")["draft"] is None
    assert _outline_objectives(storage) == ["理解斜率的变化意义", "理解截距的含义"]


@pytest.mark.asyncio
async def test_second_round_editing_keeps_module_and_knowledge_fields_available() -> None:
    """二次编辑：应用一次之后，教学环节与知识字段必须仍然可编辑。

    回归保护。apply 内部会走 normalize_course_plan_contract 把目录小节
    重编为 L2-<章>-<节>，而教案 sections[].node_id 不在那条链路上。
    两边一旦分叉，_plan_section 找不到小节，_editable_fields 直接跳过整节
    ——该节的教学环节与知识字段会**静默地从工作台消失**，不报任何错，
    教师只会看到「这一节突然不能改了」。
    """
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))

    def module_and_knowledge_paths() -> list[str]:
        return [
            field["path"]
            for field in service.view("course-1", actor="teacher-1")["editable_fields"]
            if "teaching_modules" in field["path"] or "/knowledge/" in field["path"]
        ]

    before = module_and_knowledge_paths()
    assert before, "第一轮就应当有教学环节与知识字段"

    first_id = storage.course["course_plan"]["chapters"][0]["sections"][0]["node_id"]
    draft_id = await _open_draft(service, "teacher-1")
    await _patch(
        service, actor="teacher-1", draft_id=draft_id,
        path=f"sections/{first_id}/learning_objective",
        value="第一轮改好的目标", key="round-1",
    )
    reviewed = await service.create_change_set(
        "course-1", actor="teacher-1", draft_id=draft_id, idempotency_key="round-1-review",
    )
    change_set = next(item for item in reviewed["change_sets"] if item["status"] == "ready")
    await service.apply_change_set(
        "course-1", actor="teacher-1",
        change_set_id=change_set["change_set_id"], idempotency_key="round-1-apply",
    )

    # 应用之后：目录与教案的 node_id 必须仍然一致。
    outline_ids = [
        item["node_id"]
        for item in storage.course["course_plan"]["chapters"][0]["sections"]
    ]
    plan_ids = [item["node_id"] for item in storage.course["course_teaching_plan"]["sections"]]
    assert plan_ids == outline_ids

    # 字段数量不能因为应用过一次而缩水。
    after = module_and_knowledge_paths()
    assert len(after) == len(before)

    # 第二轮真的能改到教学环节与知识字段。
    second_draft = await _open_draft(service, "teacher-1", "round-2")
    current_id = outline_ids[0]
    await _patch(
        service, actor="teacher-1", draft_id=second_draft,
        path=f"sections/{current_id}/teaching_modules/core/teaching_guidance",
        value="第二轮补充的环节指导", key="round-2-module",
    )
    await _patch(
        service, actor="teacher-1", draft_id=second_draft,
        path=f"sections/{current_id}/knowledge/斜率/boundaries",
        value=["不适用于垂直直线"], key="round-2-knowledge",
    )
    changed = storage.course["teaching_plan_workbench"]["drafts"]["teacher-1"]["changed_paths"]
    assert len(changed) == 2
