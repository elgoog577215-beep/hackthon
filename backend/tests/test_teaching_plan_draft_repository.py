"""草稿仓库的生命周期、并发、幂等与"失败不污染正式课程"回归测试。

对应 openspec/changes/upgrade-teaching-plan-workbench/tasks.md 的 1.2 与 1.6。
这里只测领域/仓库层：草稿是独立临时写入区，任何过期、冲突、失败或并发都
不得让正式 `course_teaching_plan` / `course_plan` 进入半更新状态。
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
    """正式课程真源的可比较快照。"""
    return {
        "course_plan": deepcopy(storage.course.get("course_plan")),
        "generation_request": deepcopy(storage.course.get("generation_request")),
        "subject_pedagogy_profile": deepcopy(storage.course.get("subject_pedagogy_profile")),
        "course_teaching_plan": deepcopy(storage.course.get("course_teaching_plan")),
    }


async def _open_draft(service: TeachingPlanWorkbenchService, actor: str, key: str) -> str:
    view = service.view("course-1", actor=actor)
    created = await service.create_draft(
        "course-1",
        actor=actor,
        idempotency_key=key,
        base_plan_revision_id=view["current_plan_revision_id"],
        base_course_document_revision=view["course_document_revision"],
    )
    return created["draft"]["draft_id"]


# --- 1.2 草稿生命周期：单草稿、跨刷新读取、过期、删除 ---------------------------


@pytest.mark.asyncio
async def test_repeated_create_keeps_one_draft_per_actor_and_survives_reload() -> None:
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    first = await _open_draft(service, "teacher-1", "create-1")
    await service.patch_draft(
        "course-1",
        actor="teacher-1",
        draft_id=first,
        path="overall/positioning",
        value="跨刷新仍然可读的草稿内容",
        expected_value_hash="",
        base_plan_revision_id="",
        idempotency_key="patch-1",
    )

    # 同一基础修订上重复创建不得丢弃已有草稿（等价于前端重复打开工作台）。
    second = await _open_draft(service, "teacher-1", "create-2")
    assert second == first

    # 跨刷新读取：用一个全新的 service 实例从仓库重新读取。
    reloaded = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft = reloaded.view("course-1", actor="teacher-1")["draft"]
    assert draft["draft_id"] == first
    assert draft["changed_paths"] == ["overall/positioning"]
    assert draft["status"] == "active"

    # 当前用户单草稿：仓库里 teacher-1 只有一份。
    assert list(storage.course["teaching_plan_workbench"]["drafts"]) == ["teacher-1"]


@pytest.mark.asyncio
async def test_each_actor_keeps_an_independent_draft() -> None:
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    first = await _open_draft(service, "teacher-1", "create-1")
    second = await _open_draft(service, "teacher-2", "create-2")
    assert first != second

    await service.patch_draft(
        "course-1",
        actor="teacher-1",
        draft_id=first,
        path="overall/positioning",
        value="teacher-1 的私有草稿",
        expected_value_hash="",
        base_plan_revision_id="",
        idempotency_key="patch-1",
    )
    # teacher-2 不会看到 teacher-1 的草稿内容。
    assert service.view("course-1", actor="teacher-2")["draft"]["changed_paths"] == []


@pytest.mark.asyncio
async def test_expired_draft_is_rejected_and_replaced_without_touching_official_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEACHING_PLAN_DRAFT_TTL_HOURS", "1")
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service, "teacher-1", "create-1")
    await service.patch_draft(
        "course-1",
        actor="teacher-1",
        draft_id=draft_id,
        path="overall/positioning",
        value="过期前写入的草稿内容",
        expected_value_hash="",
        base_plan_revision_id="",
        idempotency_key="patch-1",
    )
    before = _official(storage)

    # 把 expires_at 拨到过去，等价于草稿放置超过 TTL。
    storage.course["teaching_plan_workbench"]["drafts"]["teacher-1"]["expires_at"] = (
        "2000-01-01T00:00:00+00:00"
    )

    assert service.view("course-1", actor="teacher-1")["draft"]["status"] == "expired"

    with pytest.raises(TeachingPlanWorkbenchError) as patch_error:
        await service.patch_draft(
            "course-1",
            actor="teacher-1",
            draft_id=draft_id,
            path="overall/positioning",
            value="过期后不允许继续写入",
            expected_value_hash="",
            base_plan_revision_id="",
            idempotency_key="patch-after-expiry",
        )
    assert patch_error.value.code == "teaching_plan_draft_expired"

    with pytest.raises(TeachingPlanWorkbenchError) as review_error:
        await service.create_change_set(
            "course-1",
            actor="teacher-1",
            draft_id=draft_id,
            idempotency_key="review-after-expiry",
        )
    assert review_error.value.code == "teaching_plan_draft_expired"

    # 过期草稿不能被审阅成正式修订，正式课程仍然完全不变。
    assert _official(storage) == before

    # 重新创建会替换掉过期草稿，而不是复用它。
    replacement = await _open_draft(service, "teacher-1", "create-after-expiry")
    assert replacement != draft_id
    assert service.view("course-1", actor="teacher-1")["draft"]["changed_paths"] == []
    assert _official(storage) == before


@pytest.mark.asyncio
async def test_discarding_draft_leaves_no_draft_state_behind() -> None:
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service, "teacher-1", "create-1")
    await service.patch_draft(
        "course-1",
        actor="teacher-1",
        draft_id=draft_id,
        path="overall/positioning",
        value="即将被放弃的草稿",
        expected_value_hash="",
        base_plan_revision_id="",
        idempotency_key="patch-1",
    )
    before = _official(storage)
    await service.discard_draft(
        "course-1",
        actor="teacher-1",
        draft_id=draft_id,
        idempotency_key="discard-1",
    )

    assert service.view("course-1", actor="teacher-1")["draft"] is None
    assert "teacher-1" not in storage.course["teaching_plan_workbench"]["drafts"]
    assert _official(storage) == before

    # 已删除的草稿不能继续被写入或审阅。
    with pytest.raises(TeachingPlanWorkbenchError) as missing:
        await service.patch_draft(
            "course-1",
            actor="teacher-1",
            draft_id=draft_id,
            path="overall/positioning",
            value="不应写入",
            expected_value_hash="",
            base_plan_revision_id="",
            idempotency_key="patch-after-discard",
        )
    assert missing.value.code == "teaching_plan_draft_not_found"


# --- 1.6 并发 -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_patches_to_distinct_fields_all_survive() -> None:
    """并发写不同字段时，仓库锁必须保证没有丢失更新。"""
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service, "teacher-1", "create-1")

    paths = {
        "overall/positioning": "并发写入的课程定位",
        "overall/target_audience": "并发写入的教学对象",
        "overall/prerequisites": ["并发写入的前置要求"],
        "sections/section-1/learning_objective": "并发写入的小节目标",
    }
    await asyncio.gather(*[
        service.patch_draft(
            "course-1",
            actor="teacher-1",
            draft_id=draft_id,
            path=path,
            value=value,
            expected_value_hash="",
            base_plan_revision_id="",
            idempotency_key=f"concurrent-{index}",
        )
        for index, (path, value) in enumerate(paths.items())
    ])

    draft = service.view("course-1", actor="teacher-1")["draft"]
    assert set(draft["changed_paths"]) == set(paths)


@pytest.mark.asyncio
async def test_concurrent_create_draft_yields_a_single_draft() -> None:
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    view = service.view("course-1", actor="teacher-1")
    results = await asyncio.gather(*[
        service.create_draft(
            "course-1",
            actor="teacher-1",
            idempotency_key=f"concurrent-create-{index}",
            base_plan_revision_id=view["current_plan_revision_id"],
            base_course_document_revision=view["course_document_revision"],
        )
        for index in range(4)
    ])
    draft_ids = {item["draft"]["draft_id"] for item in results}
    assert len(draft_ids) == 1
    assert list(storage.course["teaching_plan_workbench"]["drafts"]) == ["teacher-1"]


@pytest.mark.asyncio
async def test_expected_value_hash_rejects_the_second_writer_and_keeps_the_first() -> None:
    """两个页面基于同一旧值编辑同一字段：第二个必须冲突，第一个必须保留。"""
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service, "teacher-1", "create-1")

    from teaching_plan_workbench import _value_hash

    shared_hash = _value_hash("从变化率建立函数直觉")
    await service.patch_draft(
        "course-1",
        actor="teacher-1",
        draft_id=draft_id,
        path="overall/positioning",
        value="第一个页面保存的定位",
        expected_value_hash=shared_hash,
        base_plan_revision_id="",
        idempotency_key="writer-1",
    )
    with pytest.raises(TeachingPlanWorkbenchError) as conflict:
        await service.patch_draft(
            "course-1",
            actor="teacher-1",
            draft_id=draft_id,
            path="overall/positioning",
            value="第二个页面保存的定位",
            expected_value_hash=shared_hash,
            base_plan_revision_id="",
            idempotency_key="writer-2",
        )
    assert conflict.value.code == "teaching_plan_field_conflict"
    assert conflict.value.details["current_value"] == "第一个页面保存的定位"

    reloaded = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    review = reloaded.review_draft("course-1", actor="teacher-1", draft_id=draft_id)
    after = next(
        item for item in review["diff"]["operations"]
        if item["path"] == "overall/positioning"
    )["after"]
    assert after == "第一个页面保存的定位"


# --- 1.6 幂等 -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_replayed_patch_key_does_not_apply_the_value_twice() -> None:
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service, "teacher-1", "create-1")
    for _ in range(3):
        await service.patch_draft(
            "course-1",
            actor="teacher-1",
            draft_id=draft_id,
            path="overall/prerequisites",
            value=["幂等重放的前置要求"],
            expected_value_hash="",
            base_plan_revision_id="",
            idempotency_key="replayed-patch",
        )
    draft = service.view("course-1", actor="teacher-1")["draft"]
    assert draft["changed_paths"] == ["overall/prerequisites"]
    assert len(draft["operations"]) == 1


@pytest.mark.asyncio
async def test_replayed_apply_key_creates_only_one_official_revision() -> None:
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    view = service.view("course-1", actor="teacher-1")
    draft_id = await _open_draft(service, "teacher-1", "create-1")
    await service.patch_draft(
        "course-1",
        actor="teacher-1",
        draft_id=draft_id,
        path="overall/positioning",
        value="只应产生一个正式修订",
        expected_value_hash="",
        base_plan_revision_id="",
        idempotency_key="patch-1",
    )
    reviewed = await service.create_change_set(
        "course-1",
        actor="teacher-1",
        draft_id=draft_id,
        idempotency_key="review-1",
    )
    change_set_id = next(
        item for item in reviewed["change_sets"] if item["status"] == "ready"
    )["change_set_id"]

    first = await service.apply_change_set(
        "course-1",
        actor="teacher-1",
        change_set_id=change_set_id,
        idempotency_key="apply-once",
    )
    replay = await service.apply_change_set(
        "course-1",
        actor="teacher-1",
        change_set_id=change_set_id,
        idempotency_key="apply-once",
    )

    applied_revision = first["workbench"]["current_plan_revision_id"]
    assert replay["workbench"]["current_plan_revision_id"] == applied_revision
    assert applied_revision != view["current_plan_revision_id"]
    # 基线 + 应用后的修订，重放不得再追加。
    revisions = storage.course["teaching_plan_workbench"]["revisions"]
    assert len(revisions) == 2
    assert [item["revision_number"] for item in revisions] == [1, 2]
    assert first["receipt"]["command_id"] == replay["receipt"]["command_id"]


# --- 1.6 失败与冲突不污染正式课程 ----------------------------------------------


@pytest.mark.asyncio
async def test_blocked_change_set_never_reaches_the_official_plan() -> None:
    """质量门阻断时，正式课程必须保持应用前的状态。"""
    course = _course()
    # `_validate` 读取教案自身的 classroom，不走 teacher_course_brief 回退。
    course["course_teaching_plan"]["classroom"] = {
        "total_class_hours": 1,
        "lesson_duration_minutes": 45,
        "teaching_context": "classroom",
    }
    storage = MemoryStorage(course)
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service, "teacher-1", "create-1")
    before = _official(storage)

    # 小节时长远超总课时，触发 teaching_plan_class_hours_exceeded 阻断。
    await service.patch_draft(
        "course-1",
        actor="teacher-1",
        draft_id=draft_id,
        path="sections/section-1/planned_minutes",
        value=240,
        expected_value_hash="",
        base_plan_revision_id="",
        idempotency_key="patch-over-capacity",
    )
    reviewed = await service.create_change_set(
        "course-1",
        actor="teacher-1",
        draft_id=draft_id,
        idempotency_key="review-1",
    )
    blocked = next(
        item for item in reviewed["change_sets"]
        if item["draft_id"] == draft_id
    )
    assert blocked["status"] == "blocked"

    with pytest.raises(TeachingPlanWorkbenchError) as error:
        await service.apply_change_set(
            "course-1",
            actor="teacher-1",
            change_set_id=blocked["change_set_id"],
            idempotency_key="apply-blocked",
        )
    assert error.value.code == "teaching_plan_change_set_not_ready"
    assert _official(storage) == before
    # 只有创建草稿时写入的基线修订，阻断的变更集没有产生新的正式修订。
    revisions = storage.course["teaching_plan_workbench"]["revisions"]
    assert [item["created_by"] for item in revisions] == ["generation"]
    assert all(item["change_set_id"] == "" for item in revisions)


@pytest.mark.asyncio
async def test_draft_based_on_superseded_revision_cannot_overwrite_the_newer_plan() -> None:
    """并发编辑：teacher-2 的旧草稿不得静默覆盖 teacher-1 已应用的修订。"""
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    view = service.view("course-1", actor="teacher-1")
    base = view["current_plan_revision_id"]

    stale_draft = await _open_draft(service, "teacher-2", "create-2")
    await service.patch_draft(
        "course-1",
        actor="teacher-2",
        draft_id=stale_draft,
        path="overall/positioning",
        value="teacher-2 基于旧修订的定位",
        expected_value_hash="",
        base_plan_revision_id=base,
        idempotency_key="patch-2",
    )

    # teacher-1 先应用，正式教案前进一个修订。
    fresh_draft = await _open_draft(service, "teacher-1", "create-1")
    await service.patch_draft(
        "course-1",
        actor="teacher-1",
        draft_id=fresh_draft,
        path="overall/positioning",
        value="teacher-1 已应用的定位",
        expected_value_hash="",
        base_plan_revision_id=base,
        idempotency_key="patch-1",
    )
    reviewed = await service.create_change_set(
        "course-1",
        actor="teacher-1",
        draft_id=fresh_draft,
        idempotency_key="review-1",
    )
    await service.apply_change_set(
        "course-1",
        actor="teacher-1",
        change_set_id=next(
            item for item in reviewed["change_sets"] if item["status"] == "ready"
        )["change_set_id"],
        idempotency_key="apply-1",
    )
    applied = _official(storage)
    assert applied["course_plan"]["positioning"] == "teacher-1 已应用的定位"

    # teacher-2 的草稿现在基于被取代的修订，必须被标记并拒绝审阅。
    stale_view = service.view("course-1", actor="teacher-2")
    assert stale_view["draft"]["status"] == "stale"
    assert stale_view["draft"]["base_plan_revision_id"] == base
    assert service.review_draft(
        "course-1", actor="teacher-2", draft_id=stale_draft,
    )["status"] == "stale"

    with pytest.raises(TeachingPlanWorkbenchError) as conflict:
        await service.create_change_set(
            "course-1",
            actor="teacher-2",
            draft_id=stale_draft,
            idempotency_key="review-2",
        )
    assert conflict.value.code == "teaching_plan_base_conflict"
    assert conflict.value.details["current_plan_revision_id"] != base

    # teacher-1 的修订完好，teacher-2 的草稿内容没有泄漏进正式课程。
    assert _official(storage) == applied

    # teacher-2 重新基于当前修订创建草稿后可以正常继续。
    rebased = await _open_draft(service, "teacher-2", "create-2-rebased")
    assert rebased != stale_draft
    assert service.view("course-1", actor="teacher-2")["draft"]["status"] == "active"


@pytest.mark.asyncio
async def test_mutation_failure_does_not_persist_partial_workbench_state() -> None:
    """mutation 中途抛错时，仓库不得留下半写入的草稿状态。"""
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service, "teacher-1", "create-1")
    await service.patch_draft(
        "course-1",
        actor="teacher-1",
        draft_id=draft_id,
        path="overall/positioning",
        value="失败前的稳定草稿内容",
        expected_value_hash="",
        base_plan_revision_id="",
        idempotency_key="patch-1",
    )
    before_official = _official(storage)
    before_draft = deepcopy(storage.course["teaching_plan_workbench"]["drafts"]["teacher-1"])

    # 写入一个不存在的路径：_write_path 在 mutation 内抛错。
    with pytest.raises(TeachingPlanWorkbenchError) as error:
        await service.patch_draft(
            "course-1",
            actor="teacher-1",
            draft_id=draft_id,
            path="overall/not_a_real_field",
            value="不应落盘",
            expected_value_hash="",
            base_plan_revision_id="",
            idempotency_key="patch-invalid",
        )
    assert error.value.code in {
        "teaching_plan_path_not_found",
        "teaching_plan_readonly_field",
    }

    assert _official(storage) == before_official
    assert storage.course["teaching_plan_workbench"]["drafts"]["teacher-1"] == before_draft


@pytest.mark.asyncio
async def test_draft_state_never_leaks_into_the_official_teaching_plan_projection() -> None:
    """草稿不是第二真源：未应用前正式投影必须只反映正式教案。"""
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    draft_id = await _open_draft(service, "teacher-1", "create-1")
    before = _official(storage)

    for index, (path, value) in enumerate({
        "overall/positioning": "草稿定位不得进入正式投影",
        "overall/learning_objectives": ["草稿目标不得进入正式投影"],
        "sections/section-1/learning_objective": "草稿小节目标不得进入正式投影",
    }.items()):
        await service.patch_draft(
            "course-1",
            actor="teacher-1",
            draft_id=draft_id,
            path=path,
            value=value,
            expected_value_hash="",
            base_plan_revision_id="",
            idempotency_key=f"patch-{index}",
        )

    view = service.view("course-1", actor="teacher-1")
    assert len(view["draft"]["changed_paths"]) == 3
    # 正式课程真源与正式投影都还是应用前的内容。
    assert _official(storage) == before
    assert "草稿" not in str(view["teaching_plan"])
    assert view["current_plan_revision_id"] == before["course_teaching_plan"]["revision_id"]
