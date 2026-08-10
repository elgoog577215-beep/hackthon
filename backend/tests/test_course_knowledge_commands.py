"""知识白名单命令与原子协调测试（需求 9 第 2 项）。

核心判据不是"命令能跑通"，而是"失败时什么都没变"：知识修订与课程修订
必须要么一起生效、要么一起回退。因此每个拒绝路径都断言活动知识库仍是
原修订，而不只是断言抛了异常。
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from content_blocks import set_node_content_blocks
from course_document import (
    CourseBlock,
    CourseDocument,
    CourseSection,
    refresh_document_revision,
)
from course_knowledge_base import compile_course_knowledge_base
from course_knowledge_commands import (
    KNOWLEDGE_COMMANDS,
    CourseKnowledgeCommandService,
    KnowledgeCommandRejected,
    build_knowledge_candidate,
)
from course_knowledge_map import compile_course_knowledge_map
from course_repository import CourseDocumentRepository


class MemoryStorage:
    def __init__(self, course: dict) -> None:
        self.course = deepcopy(course)
        self.save_count = 0

    def load_course(self, _course_id: str) -> dict:
        return deepcopy(self.course)

    async def save_course(self, _course_id: str, data: dict) -> None:
        self.course = deepcopy(data)
        self.save_count += 1


class FailingStorage(MemoryStorage):
    """保存时抛错，用来验证"提交失败 -> 知识库不变"。"""

    async def save_course(self, _course_id: str, _data: dict) -> None:
        raise RuntimeError("存储写入失败")


def _knowledge_points() -> list[dict]:
    return [
        {
            "name": "容量耗尽判定",
            "statement": "当元素数量等于当前容量时，下一次插入必须先获得更大的连续存储空间。",
            "knowledge_type": "rule",
            "conditions": ["使用连续存储且不存在可用槽位"],
            "boundaries": ["尚有空闲槽位时不触发扩容"],
            "capability_points": [{
                "name": "判断扩容触发时机",
                "observable_behavior": "给定长度与容量，准确判断下一次插入是否触发扩容",
            }],
            "mastery_criteria": [{
                "name": "扩容触发判断达标",
                "observable_performance": "在不同长度与容量组合中独立判断扩容时机并说明依据",
                "verification_method": "使用至少三个边界案例进行判断并核对结果",
            }],
            "entry_reason": "这是理解动态数组扩容机制的课程入口。",
            "aliases": ["满容量判定"],
            "relations": [{
                "target_name": "动态数组扩容",
                "relation_type": "prerequisite",
                "reason": "必须先识别容量耗尽，才能确定何时执行扩容",
            }],
        },
        {
            "name": "动态数组扩容",
            "statement": "倍增扩容把少数 O(n) 复制成本分摊到一系列插入，使平均单次插入保持常数阶。",
            "knowledge_type": "principle",
            "conditions": ["扩容因子大于 1 且按几何级数增长"],
            "boundaries": ["结论描述摊还成本，不等于每次插入的最坏成本"],
            "capability_points": [{
                "name": "动态数组扩容实现",
                "observable_behavior": "独立实现倍增扩容并用复制次数解释摊还复杂度",
            }],
            "misconceptions": [{
                "name": "把单次复制成本当作每次插入成本",
                "observable_error_pattern": "看到一次扩容需要复制 n 个元素，就断言每次插入都是 O(n)",
                "discrimination": "区分单次操作最坏成本与一系列操作的摊还成本",
                "repair_strategy": "列出连续插入过程中的扩容位置与累计复制次数后重新计算平均成本",
            }],
            "mastery_criteria": [{
                "name": "扩容实现与分析达标",
                "observable_performance": "独立实现倍增扩容，并正确说明最坏成本与摊还成本的区别",
                "verification_method": "运行连续插入测试并提交复杂度推导",
            }],
            "aliases": ["可变长数组"],
        },
    ]


def _blueprint_course() -> dict:
    course = {
        "course_id": "course-1",
        "course_name": "数据结构",
        "course_purpose": "systematic",
        "nodes": [{
            "node_id": "section-1",
            "node_level": 2,
            "node_name": "线性表与动态数组",
            "learning_objective": "能够实现动态数组扩容并分析摊还复杂度",
            "knowledge_structure": [{
                "concept_group": "动态容量管理",
                "description": "识别扩容触发条件，并解释倍增扩容的摊还成本",
                "knowledge_points": _knowledge_points(),
            }],
            "key_points": ["容量耗尽判定", "动态数组扩容"],
            "content_blocks": [],
            "generation_status": "completed",
            "node_content": (
                "## 容量耗尽判定\n\n根据长度与容量识别扩容触发时机。\n\n"
                "## 动态数组扩容\n\n实现倍增扩容，并区分最坏成本与摊还成本。"
            ),
        }],
    }
    set_node_content_blocks(course["nodes"][0], course["nodes"][0]["node_content"])
    return course


def _compiled_knowledge_base() -> dict:
    course = _blueprint_course()
    return compile_course_knowledge_base(
        course, course_map=compile_course_knowledge_map(course),
    )


def _canonical_course() -> dict:
    document = refresh_document_revision(CourseDocument(
        course_id="course-1",
        title="数据结构",
        sections=[CourseSection(
            section_id="section-1",
            parent_section_id="chapter-1",
            title="线性表与动态数组",
            position=0,
            level=2,
            learning_objective="能够实现动态数组扩容并分析摊还复杂度",
        )],
        blocks=[
            CourseBlock(
                block_id="section-1-1-custom",
                section_id="section-1",
                position=0,
                role="concept",
                payload={"markdown": "扩容触发条件。"},
            ),
            CourseBlock(
                block_id="section-1-2-custom",
                section_id="section-1",
                position=1,
                role="concept",
                payload={"markdown": "倍增扩容与摊还成本。"},
            ),
        ],
    ))
    return {
        "course_id": "course-1",
        "course_name": "数据结构",
        "course_schema_version": "course_document_v1",
        "course_document_authoritative": True,
        "course_document": document.model_dump(mode="json"),
        "course_document_revision": document.document_revision,
        "current_course_version_id": document.document_revision,
        "course_operation_log": [],
        "course_knowledge_base": _compiled_knowledge_base(),
    }


def _service(course: dict | None = None) -> tuple[CourseKnowledgeCommandService, MemoryStorage]:
    storage = MemoryStorage(course if course is not None else _canonical_course())
    repository = CourseDocumentRepository(storage)
    return CourseKnowledgeCommandService(repository), storage


def _revised_knowledge_base(course: dict) -> dict:
    """一次合法的知识修订：改写一个知识点的陈述。"""
    revised = deepcopy(course["course_knowledge_base"])
    for point in revised["knowledge_points"]:
        if point["name"] == "容量耗尽判定":
            point["statement"] = "长度等于容量时，插入前必须先获得更大的连续存储空间。"
            point["revision_id"] = "ckpr_revised"
    revised["revision_id"] = "ckbr_revised"
    return revised


def _candidate(course: dict, **overrides):
    payload = overrides.pop("proposed_knowledge_base", None)
    return build_knowledge_candidate(
        course,
        operation=overrides.pop("operation", "revise_knowledge_point"),
        proposed_knowledge_base=payload if payload is not None else _revised_knowledge_base(course),
        reason=overrides.pop("reason", "补充扩容触发条件的精确表述"),
        **overrides,
    )


# --- 白名单与候选门 ---------------------------------------------------------


def test_command_outside_whitelist_is_refused() -> None:
    """白名单之外的操作在读取任何状态之前就被拒绝。"""
    course = _canonical_course()

    with pytest.raises(KnowledgeCommandRejected) as error:
        _candidate(course, operation="delete_everything")

    assert error.value.code == "knowledge_command_not_whitelisted"


def test_whitelist_covers_the_documented_operations() -> None:
    """六类关系调整、拆分合并等操作都必须在白名单内可表达。"""
    assert {
        "add_knowledge_point", "revise_knowledge_point", "split_knowledge_point",
        "merge_knowledge_points", "rename_knowledge_point", "retire_knowledge_point",
        "adjust_relation", "adjust_binding",
    } == KNOWLEDGE_COMMANDS


def test_command_without_reason_is_refused() -> None:
    """没有理由的知识修改无法审阅，不允许进入候选。"""
    with pytest.raises(KnowledgeCommandRejected) as error:
        _candidate(_canonical_course(), reason="   ")

    assert error.value.code == "knowledge_command_missing_reason"


def test_identity_moving_command_requires_an_identity_map() -> None:
    """拆分/合并/退役会移动稳定 ID，必须显式给出旧新映射。"""
    course = _canonical_course()

    with pytest.raises(KnowledgeCommandRejected) as error:
        _candidate(course, operation="split_knowledge_point")

    assert error.value.code == "knowledge_identity_map_required"


def test_candidate_does_not_touch_the_active_knowledge_base() -> None:
    """确认前活动知识库必须原封不动 —— 候选只是提案。"""
    course = _canonical_course()
    before = deepcopy(course["course_knowledge_base"])

    candidate = _candidate(course)

    assert candidate["confirmable"] is True
    assert course["course_knowledge_base"] == before
    assert candidate["base_knowledge_revision_id"] == before["revision_id"]
    assert candidate["impact_report"]["changed_knowledge_ids"]


def test_candidate_failing_quality_gate_is_not_confirmable() -> None:
    """未通过知识质量门的候选会带着原因返回，但不可确认。"""
    course = _canonical_course()
    broken = deepcopy(course["course_knowledge_base"])
    # 清空知识点：结构门必然报 critical。
    broken["knowledge_points"] = []
    broken["revision_id"] = "ckbr_broken"

    candidate = _candidate(course, proposed_knowledge_base=broken)

    assert candidate["confirmable"] is False
    assert candidate["blocking_issues"]


# --- 原子协调：要么一起生效，要么一起回退 -----------------------------------


async def test_confirmed_command_commits_knowledge_and_course_revision_together() -> None:
    """确认后知识库与课程修订向量在同一次提交中一起生效。"""
    course = _canonical_course()
    service, storage = _service(course)
    candidate = _candidate(course)
    proposed = _revised_knowledge_base(course)

    receipt = await service.confirm_knowledge_candidate(
        "course-1",
        command_id="cmd-1",
        candidate=candidate,
        proposed_knowledge_base=proposed,
    )

    assert receipt["knowledge_revision_id"] == "ckbr_revised"
    assert receipt["operation"] == "knowledge:revise_knowledge_point"
    saved = storage.course
    assert saved["course_knowledge_base"]["revision_id"] == "ckbr_revised"
    # 同一次提交同时推进了课程修订向量里的知识键。
    vector = saved["course_revision_vector"]["revisions"]
    assert vector["course_knowledge_base"] == "ckbr_revised"
    # 课程正文没有被知识命令改动。
    assert saved["course_document"] == course["course_document"]
    assert storage.save_count == 1


async def test_replaying_the_same_command_id_is_idempotent() -> None:
    """重试同一 command_id 返回原回执，不重复应用。"""
    course = _canonical_course()
    service, storage = _service(course)
    candidate = _candidate(course)
    proposed = _revised_knowledge_base(course)

    first = await service.confirm_knowledge_candidate(
        "course-1", command_id="cmd-1",
        candidate=candidate, proposed_knowledge_base=proposed,
    )
    saves_after_first = storage.save_count
    second = await service.confirm_knowledge_candidate(
        "course-1", command_id="cmd-1",
        candidate=candidate, proposed_knowledge_base=proposed,
    )

    assert second["command_id"] == first["command_id"]
    assert storage.save_count == saves_after_first
    assert len(service.knowledge_revision_log("course-1")) == 1


async def test_stale_knowledge_base_revision_is_rejected_and_nothing_changes() -> None:
    """知识库在确认前已变化时拒绝应用，活动知识库保持当前修订。"""
    course = _canonical_course()
    service, storage = _service(course)
    candidate = _candidate(course)
    candidate["base_knowledge_revision_id"] = "ckbr_someone_elses_revision"

    with pytest.raises(KnowledgeCommandRejected) as error:
        await service.confirm_knowledge_candidate(
            "course-1", command_id="cmd-1",
            candidate=candidate,
            proposed_knowledge_base=_revised_knowledge_base(course),
        )

    assert error.value.code == "knowledge_base_revision_changed"
    assert storage.course["course_knowledge_base"]["revision_id"] == (
        course["course_knowledge_base"]["revision_id"]
    )
    assert storage.save_count == 0


async def test_stale_course_document_revision_is_rejected_and_nothing_changes() -> None:
    """课程正文在确认前发生变化时，知识修订不得基于过期课程落地。"""
    course = _canonical_course()
    service, storage = _service(course)
    candidate = _candidate(course)
    candidate["base_document_revision"] = "cdr_stale"

    with pytest.raises(KnowledgeCommandRejected) as error:
        await service.confirm_knowledge_candidate(
            "course-1", command_id="cmd-1",
            candidate=candidate,
            proposed_knowledge_base=_revised_knowledge_base(course),
        )

    assert error.value.code == "course_document_revision_changed"
    assert storage.course["course_knowledge_base"]["revision_id"] == (
        course["course_knowledge_base"]["revision_id"]
    )
    assert storage.save_count == 0


async def test_unconfirmable_candidate_cannot_be_applied() -> None:
    """未通过质量门的候选即使被直接提交也必须拒绝。"""
    course = _canonical_course()
    service, storage = _service(course)
    broken = deepcopy(course["course_knowledge_base"])
    broken["knowledge_points"] = []
    broken["revision_id"] = "ckbr_broken"
    candidate = _candidate(course, proposed_knowledge_base=broken)

    with pytest.raises(KnowledgeCommandRejected) as error:
        await service.confirm_knowledge_candidate(
            "course-1", command_id="cmd-1",
            candidate=candidate, proposed_knowledge_base=broken,
        )

    assert error.value.code == "knowledge_candidate_not_confirmable"
    assert storage.course["course_knowledge_base"]["knowledge_points"]
    assert storage.save_count == 0


async def test_storage_failure_leaves_the_previous_knowledge_base_intact() -> None:
    """提交过程中存储失败时，知识修订整体不生效 —— 这是原子性的正面证据。"""
    course = _canonical_course()
    original_revision = course["course_knowledge_base"]["revision_id"]
    storage = FailingStorage(course)
    service = CourseKnowledgeCommandService(CourseDocumentRepository(storage))
    candidate = _candidate(course)

    with pytest.raises(RuntimeError, match="存储写入失败"):
        await service.confirm_knowledge_candidate(
            "course-1", command_id="cmd-1",
            candidate=candidate,
            proposed_knowledge_base=_revised_knowledge_base(course),
        )

    # 内存里的课程仍是原修订：没有半生效状态。
    assert storage.course["course_knowledge_base"]["revision_id"] == original_revision
    assert "course_knowledge_revision_log" not in storage.course


async def test_confirmed_command_records_an_auditable_revision_log() -> None:
    """每次确认留下可追溯回执：谁、为什么、从哪个修订到哪个修订。"""
    course = _canonical_course()
    service, _ = _service(course)
    candidate = _candidate(course)

    await service.confirm_knowledge_candidate(
        "course-1", command_id="cmd-1",
        candidate=candidate,
        proposed_knowledge_base=_revised_knowledge_base(course),
        actor="teacher-1",
    )

    log = service.knowledge_revision_log("course-1")
    assert len(log) == 1
    entry = log[0]
    assert entry["operation"] == "revise_knowledge_point"
    assert entry["actor"] == "teacher-1"
    assert entry["reason"] == "补充扩容触发条件的精确表述"
    assert entry["previous_revision_id"] == course["course_knowledge_base"]["revision_id"]
    assert entry["revision_id"] == "ckbr_revised"
    assert entry["changed_source_keys"]


async def test_command_without_id_is_refused() -> None:
    """没有 command_id 就无法保证幂等，直接拒绝。"""
    course = _canonical_course()
    service, storage = _service(course)

    with pytest.raises(KnowledgeCommandRejected) as error:
        await service.confirm_knowledge_candidate(
            "course-1", command_id="",
            candidate=_candidate(course),
            proposed_knowledge_base=_revised_knowledge_base(course),
        )

    assert error.value.code == "knowledge_command_missing_id"
    assert storage.save_count == 0


async def test_confirmed_revision_survives_a_later_recompile() -> None:
    """确认后的知识修订必须挺过下一次知识视图重编译。

    apply_persisted_course_knowledge_base 会在指纹失配时拒绝存量知识库并按
    蓝图重编译。实测仓库里全部真实课程的指纹都是失配的，所以若确认写回时不
    重新盖章，教师确认的修订会被"提交成功 -> 日志有记录 -> 下次重编译静默丢弃"
    ——改动看得见、然后消失，比直接失败更难排查。
    """
    from copy import deepcopy

    from course_knowledge_base import (
        apply_persisted_course_knowledge_base,
        course_knowledge_source_fingerprint,
    )

    course = _canonical_course()
    service, storage = _service(course)
    candidate = _candidate(course)

    await service.confirm_knowledge_candidate(
        "course-1", command_id="cmd-1",
        candidate=candidate,
        proposed_knowledge_base=_revised_knowledge_base(course),
    )

    saved = storage.course
    view = service.repository.load_course_view("course-1")
    stored = saved["course_knowledge_base"]
    # 盖章必须对得上当前课程，否则存量库会被拒绝。
    assert stored["source_course_fingerprint"] == course_knowledge_source_fingerprint(view)
    # 真正的判据：存量库能被接受，且修订内容还在。
    assert apply_persisted_course_knowledge_base(deepcopy(view), stored) is True
    revised = next(
        item for item in stored["knowledge_points"] if item["name"] == "容量耗尽判定"
    )
    assert revised["statement"].startswith("长度等于容量时")
