"""正式教案修订仓库的连续修订、历史边界与回执回归测试。

对应 openspec/changes/upgrade-teaching-plan-workbench/tasks.md 的 1.3 / 1.4 / 1.6。

夹具刻意使用生成链规范化后的真实小节 ID（`L2-<章>-<节>`）。
`normalize_course_plan_contract()` 会把 `course_plan` 的 `node_id` 无条件
规范化成该格式；如果夹具用别的写法，第一次应用后 `course_plan` 与
`course_teaching_plan` 的小节 ID 就会错位，后续修订被结构门永久阻断。
这里测的是连续修订，因此必须用真实格式。
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


SECTION_ID = "L2-1-1"


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
            section_id=SECTION_ID,
            parent_section_id="chapter-1",
            title="斜率",
            position=0,
            level=2,
            learning_objective="理解斜率的变化意义",
        )],
        blocks=[CourseBlock(
            block_id="block-1",
            section_id=SECTION_ID,
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
                    "node_id": SECTION_ID,
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
                "node_id": SECTION_ID,
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


async def _apply_once(
    service: TeachingPlanWorkbenchService,
    *,
    actor: str,
    positioning: str,
    key: str,
) -> dict:
    """走完整的 草稿 → patch → 变更集 → 应用 闭环，返回应用回执。"""
    view = service.view("course-1", actor=actor)
    base = view["current_plan_revision_id"]
    created = await service.create_draft(
        "course-1",
        actor=actor,
        idempotency_key=f"create-{key}",
        base_plan_revision_id=base,
        base_course_document_revision=view["course_document_revision"],
    )
    draft_id = created["draft"]["draft_id"]
    await service.patch_draft(
        "course-1",
        actor=actor,
        draft_id=draft_id,
        path="overall/positioning",
        value=positioning,
        expected_value_hash="",
        base_plan_revision_id=base,
        idempotency_key=f"patch-{key}",
    )
    reviewed = await service.create_change_set(
        "course-1",
        actor=actor,
        draft_id=draft_id,
        idempotency_key=f"review-{key}",
    )
    ready = next(
        item for item in reviewed["change_sets"]
        if item["draft_id"] == draft_id and item["status"] == "ready"
    )
    return await service.apply_change_set(
        "course-1",
        actor=actor,
        change_set_id=ready["change_set_id"],
        idempotency_key=f"apply-{key}",
    )


# --- 1.3 正式修订仓库 ---------------------------------------------------------


@pytest.mark.asyncio
async def test_consecutive_revisions_keep_numbering_and_parent_chain() -> None:
    """连续多次应用必须持续成功，并保持修订编号单调、父链连贯。

    这条用例守住的是"第一次应用之后课程还能不能继续修订"。
    """
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    baseline = service.view("course-1", actor="teacher-1")["current_plan_revision_id"]

    applied = []
    for index, text in enumerate(["第一次修订的定位", "第二次修订的定位", "第三次修订的定位"], start=1):
        receipt = await _apply_once(
            service, actor="teacher-1", positioning=text, key=str(index),
        )
        applied.append(receipt["workbench"]["current_plan_revision_id"])

    # 每次都产生了不同的正式修订。
    assert len(set(applied)) == 3
    assert baseline not in applied

    revisions = storage.course["teaching_plan_workbench"]["revisions"]
    # 基线 + 三次应用。
    assert [item["revision_number"] for item in revisions] == [1, 2, 3, 4]
    assert all(
        revisions[index]["parent_revision_id"] == revisions[index - 1]["revision_id"]
        for index in range(1, len(revisions))
    )
    assert revisions[0]["parent_revision_id"] == ""
    assert revisions[-1]["revision_id"] == storage.course["course_teaching_plan"]["revision_id"]


@pytest.mark.asyncio
async def test_each_revision_stores_a_full_immutable_snapshot() -> None:
    """历史修订保存完整快照，而不是只可恢复的差分；且后续应用不改写它。"""
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))

    await _apply_once(service, actor="teacher-1", positioning="第一次修订的定位", key="1")
    first = deepcopy(storage.course["teaching_plan_workbench"]["revisions"][-1])
    await _apply_once(service, actor="teacher-1", positioning="第二次修订的定位", key="2")

    revisions = storage.course["teaching_plan_workbench"]["revisions"]
    stored_first = next(
        item for item in revisions if item["revision_id"] == first["revision_id"]
    )
    # 不可变：第二次应用没有改写第一次的历史快照。
    assert stored_first == first

    # 完整快照：四个正式来源都在，且是应用当时的内容。
    snapshot = stored_first["snapshot"]
    assert set(snapshot) == {
        "course_plan",
        "generation_request",
        "subject_pedagogy_profile",
        "course_teaching_plan",
    }
    assert snapshot["course_plan"]["positioning"] == "第一次修订的定位"
    assert snapshot["course_teaching_plan"]["sections"]
    # 最新历史修订才等于当前正式内容。
    assert revisions[-1]["snapshot"]["course_plan"]["positioning"] == "第二次修订的定位"


@pytest.mark.asyncio
async def test_revision_records_source_vector_quality_report_and_receipt() -> None:
    """1.3 要求每个修订保存来源向量、质量报告，并留下可追溯的操作回执。"""
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    applied = await _apply_once(
        service, actor="teacher-1", positioning="带回执的修订", key="1",
    )
    receipt = applied["receipt"]

    revision = storage.course["teaching_plan_workbench"]["revisions"][-1]
    assert revision["source_revision_vector"]["revisions"]["course_teaching_plan"] == (
        revision["revision_id"]
    )
    assert revision["quality_report"]["passed"] is True
    assert revision["created_by"] == "teacher-1"
    assert revision["change_set_id"]
    assert revision["created_at"]

    # 操作回执：命令 ID、修订事件与来源键变化都可追溯。
    assert receipt["operation"] == "apply_teaching_plan_change_set"
    assert receipt["revision_change"]["event_id"].startswith("cre_")
    assert "course_teaching_plan" in receipt["revision_change"]["changed_source_keys"]
    logged = [
        item for item in storage.course["course_operation_log"]
        if item["operation"] == "apply_teaching_plan_change_set"
    ]
    assert len(logged) == 1
    assert logged[0]["actor"] == "teacher-1"
    assert logged[0]["receipt"]["revision_change"]["event_id"] == (
        receipt["revision_change"]["event_id"]
    )


# --- 1.4 当前正式修订与历史修订的边界 -----------------------------------------


@pytest.mark.asyncio
async def test_only_the_latest_revision_is_current_across_vector_and_envelope() -> None:
    """课程修订向量、envelope 与工作台读路径必须一致指向最新正式修订。"""
    storage = MemoryStorage(_course())
    repository = CourseDocumentRepository(storage)
    service = TeachingPlanWorkbenchService(repository)

    await _apply_once(service, actor="teacher-1", positioning="第一次修订的定位", key="1")
    superseded = storage.course["course_teaching_plan"]["revision_id"]
    await _apply_once(service, actor="teacher-1", positioning="第二次修订的定位", key="2")
    current = storage.course["course_teaching_plan"]["revision_id"]
    assert current != superseded

    # 课程修订向量指向当前，不指向历史。
    vector = storage.course["course_revision_vector"]["revisions"]
    assert vector["course_teaching_plan"] == current

    # envelope 的下游来源读取同样只看到当前。
    envelope = repository.document_envelope("course-1")
    assert envelope["teaching_plan"]["revision_id"] == current

    # 历史修订仍然可列出，但不是当前。
    view = service.view("course-1", actor="teacher-1")
    assert view["current_plan_revision_id"] == current
    listed = {item["revision_id"] for item in view["revisions"]}
    assert superseded in listed and current in listed
    # 列表按修订编号倒序，最新在前。
    assert view["revisions"][0]["revision_id"] == current


@pytest.mark.asyncio
async def test_revision_list_never_leaks_snapshots_into_the_read_path() -> None:
    """历史快照是审计数据，不能通过工作台读路径变成第二课程真源。"""
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    await _apply_once(service, actor="teacher-1", positioning="第一次修订的定位", key="1")

    view = service.view("course-1", actor="teacher-1")
    assert view["revisions"]
    assert all("snapshot" not in item for item in view["revisions"])
    # 但仓库里确实留了完整快照供恢复与审计。
    assert all(
        item.get("snapshot")
        for item in storage.course["teaching_plan_workbench"]["revisions"]
    )


@pytest.mark.asyncio
async def test_restore_creates_a_new_revision_instead_of_rewinding_history() -> None:
    """恢复历史修订必须前进为新修订，不能倒退或删除既有历史。"""
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    await _apply_once(service, actor="teacher-1", positioning="第一次修订的定位", key="1")
    first = storage.course["course_teaching_plan"]["revision_id"]
    await _apply_once(service, actor="teacher-1", positioning="第二次修订的定位", key="2")
    second = storage.course["course_teaching_plan"]["revision_id"]
    history_before = len(storage.course["teaching_plan_workbench"]["revisions"])

    restored = await service.restore_revision(
        "course-1",
        actor="teacher-1",
        revision_id=first,
        idempotency_key="restore-1",
    )
    current = restored["workbench"]["current_plan_revision_id"]

    # 新修订，而不是回到旧 ID。
    assert current not in {first, second}
    revisions = storage.course["teaching_plan_workbench"]["revisions"]
    assert len(revisions) == history_before + 1
    assert revisions[-1]["restored_from_revision_id"] == first
    assert revisions[-1]["parent_revision_id"] == second
    # 历史没有被删除。
    assert {first, second} <= {item["revision_id"] for item in revisions}
    # 内容确实回到了第一次修订。
    assert storage.course["course_plan"]["positioning"] == "第一次修订的定位"
    assert storage.course["course_revision_vector"]["revisions"]["course_teaching_plan"] == current


@pytest.mark.asyncio
async def test_restore_is_refused_while_a_draft_is_still_open() -> None:
    """有未处理草稿时恢复历史必须被拒绝，避免草稿与恢复互相覆盖。"""
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    await _apply_once(service, actor="teacher-1", positioning="第一次修订的定位", key="1")
    target = storage.course["course_teaching_plan"]["revision_id"]
    before = deepcopy(storage.course["course_plan"])

    view = service.view("course-1", actor="teacher-1")
    await service.create_draft(
        "course-1",
        actor="teacher-1",
        idempotency_key="create-open",
        base_plan_revision_id=view["current_plan_revision_id"],
        base_course_document_revision=view["course_document_revision"],
    )
    with pytest.raises(TeachingPlanWorkbenchError) as error:
        await service.restore_revision(
            "course-1",
            actor="teacher-1",
            revision_id=target,
            idempotency_key="restore-blocked",
        )
    assert error.value.code == "teaching_plan_draft_active"
    assert storage.course["course_plan"] == before


@pytest.mark.asyncio
async def test_replayed_restore_key_creates_only_one_revision() -> None:
    """恢复同样要幂等：重放同一个键不得反复追加修订。"""
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    await _apply_once(service, actor="teacher-1", positioning="第一次修订的定位", key="1")
    target = storage.course["course_teaching_plan"]["revision_id"]
    await _apply_once(service, actor="teacher-1", positioning="第二次修订的定位", key="2")
    before = len(storage.course["teaching_plan_workbench"]["revisions"])

    first = await service.restore_revision(
        "course-1", actor="teacher-1", revision_id=target, idempotency_key="restore-once",
    )
    replay = await service.restore_revision(
        "course-1", actor="teacher-1", revision_id=target, idempotency_key="restore-once",
    )

    assert (
        first["workbench"]["current_plan_revision_id"]
        == replay["workbench"]["current_plan_revision_id"]
    )
    assert len(storage.course["teaching_plan_workbench"]["revisions"]) == before + 1


@pytest.mark.asyncio
async def test_unknown_revision_restore_leaves_the_official_plan_untouched() -> None:
    storage = MemoryStorage(_course())
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(storage))
    await _apply_once(service, actor="teacher-1", positioning="第一次修订的定位", key="1")
    before = deepcopy(storage.course["course_plan"])
    revisions_before = deepcopy(storage.course["teaching_plan_workbench"]["revisions"])

    with pytest.raises(TeachingPlanWorkbenchError) as error:
        await service.restore_revision(
            "course-1",
            actor="teacher-1",
            revision_id="tpr_does_not_exist",
            idempotency_key="restore-missing",
        )
    assert error.value.code == "teaching_plan_revision_not_found"
    assert storage.course["course_plan"] == before
    assert storage.course["teaching_plan_workbench"]["revisions"] == revisions_before
