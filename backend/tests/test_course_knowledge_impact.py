"""知识 -> 下游双向影响与失败保留测试（需求 9 第 3、4 项）。

快照只断言"哪些对象进入哪一组"。理由文案、修订号和时间戳会随无关改动漂移，
写进快照只会制造假失败，掩盖真正的影响面回归。

夹具在本文件内自建：仓库根目录与 backend 下各有一个 `tests` 包，收集时互相
遮蔽，跨文件 import 同级测试模块在 pytest 下不可靠（这也是 AGENTS.md 要求
两套测试目录分别收集的原因）。夹具刻意与 test_teaching_plan_impact 使用同一
课程形状，使知识影响与教案影响在相同输入上可对照。
"""

from __future__ import annotations

from copy import deepcopy

from content_blocks import set_node_content_blocks
from course_document import (
    CourseBlock,
    CourseDocument,
    CourseSection,
    refresh_document_revision,
)
from course_knowledge_base import compile_course_knowledge_base
from course_knowledge_impact import (
    build_knowledge_impact_report,
    dependent_knowledge_ids,
    knowledge_coverage_check,
    knowledge_impact_for_revision,
    knowledge_impact_snapshot,
)
from course_knowledge_map import compile_course_knowledge_map
from course_knowledge_revisions import knowledge_revision_event
from teaching_plan_impact import (
    KnowledgeReferenceIndex,
    build_downstream_state,
    downstream_state_snapshot,
    record_rebuild_outcome,
)


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
    """知识编译输入：带知识结构的小节蓝图。"""
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


def _course(*, with_knowledge_base: bool = False) -> dict:
    """正式课程外壳：CourseDocument + 两个小节，第二节不引用本节知识。"""
    document = refresh_document_revision(CourseDocument(
        course_id="course-1",
        title="数据结构",
        sections=[
            CourseSection(
                section_id="section-1",
                parent_section_id="chapter-1",
                title="线性表与动态数组",
                position=0,
                level=2,
                learning_objective="能够实现动态数组扩容并分析摊还复杂度",
            ),
            CourseSection(
                section_id="section-2",
                parent_section_id="chapter-1",
                title="链表",
                position=1,
                level=2,
                learning_objective="能够比较链表与数组的插入代价",
            ),
        ],
        blocks=[
            # 正文块 ID 与知识绑定的目标一致：真实课程的正文与知识库编译自
            # 同一份蓝图，若测试里各用一套 ID，覆盖检查就永远测不到"已覆盖"分支。
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
            CourseBlock(
                block_id="block-2",
                section_id="section-2",
                position=0,
                role="concept",
                payload={"markdown": "链表插入代价。"},
            ),
        ],
    ))
    course = {
        "course_id": "course-1",
        "course_name": "数据结构",
        "course_schema_version": "course_document_v1",
        "course_document_authoritative": True,
        "course_document": document.model_dump(mode="json"),
        "course_document_revision": document.document_revision,
        "current_course_version_id": document.document_revision,
        "course_operation_log": [],
        "course_teaching_plan": {
            "schema_version": "course_teaching_plan_v3",
            "revision_id": "teaching-initial",
            "sections": [],
        },
        "nodes": [
            {
                "node_id": "section-1",
                "node_name": "线性表与动态数组",
                "learning_objective": "能够实现动态数组扩容并分析摊还复杂度",
            },
            {
                "node_id": "section-2",
                "node_name": "链表",
                "learning_objective": "能够比较链表与数组的插入代价",
            },
        ],
    }
    if with_knowledge_base:
        course["course_knowledge_base"] = _compiled_knowledge_base()
    return course


def _question_for_section(course: dict, section_id: str, question_id: str) -> dict:
    """一道服务于该小节当前学习目标的正式练习。

    使用真实的 learning_objective_identity，这样目标修订对比走的是生产代码
    同一条路径，而不是测试自己造的假修订号。
    """
    from learning_progress import learning_objective_identity

    section = next(
        item for item in course["course_document"]["sections"]
        if item["section_id"] == section_id
    )
    identity = learning_objective_identity(course["course_id"], {
        "node_id": section["section_id"],
        "node_name": section["title"],
        "learning_objective": section["learning_objective"],
    })
    return {
        "question_id": question_id,
        "node_id": section_id,
        "objective_id": identity["objective_id"],
        "objective_revision_id": identity["objective_revision_id"],
    }


def _knowledge_course() -> dict:
    return _course(with_knowledge_base=True)


def _point_id(knowledge_base: dict, name: str) -> str:
    index = KnowledgeReferenceIndex(knowledge_base)
    knowledge_id = index.resolve("section-1", name)
    assert knowledge_id, f"知识点 {name} 未解析到稳定 ID"
    return knowledge_id


def _edit_statement(knowledge_base: dict, knowledge_id: str) -> dict:
    """改写一个知识点的陈述，模拟一次真实的知识修订。"""
    edited = deepcopy(knowledge_base)
    for point in edited["knowledge_points"]:
        if point["knowledge_id"] == knowledge_id:
            point["statement"] = "改写后的知识陈述，用于验证影响面。"
            point["revision_id"] = "ckpr_edited"
    edited["revision_id"] = "ckbr_edited"
    return edited


# --- 知识变化 -> 下游影响 ---------------------------------------------------


def test_knowledge_edit_only_hits_objects_that_reference_it() -> None:
    """改一个知识点，只有引用它的下游对象需要重建，不是整门课程。"""
    base = _compiled_knowledge_base()
    target = _point_id(base, "容量耗尽判定")
    other = _point_id(base, "动态数组扩容")

    _, report = knowledge_impact_for_revision(
        base, _edit_statement(base, target), course_data=_knowledge_course(),
    )

    assert report["knowledge_index_available"] is True
    assert report["changed_knowledge_ids"] == [target]
    assert report["blocking"] is False

    index = KnowledgeReferenceIndex(base)
    expected = set(index.referencing_targets(target))
    assert expected, "测试前提：该知识点应有下游引用"
    regenerate = {(item["type"], item["id"]) for item in report["needs_regeneration"]}
    assert expected <= regenerate

    # 只被另一个知识点引用的对象不得进入直接重建组。
    exclusive_to_other = set(index.referencing_targets(other)) - expected
    assert exclusive_to_other, "测试前提：两个知识点的引用面应当不同"
    assert not (exclusive_to_other & regenerate)


def test_relation_dependency_marks_downstream_stale_not_regenerate() -> None:
    """经前置依赖受影响的知识，其下游是待复核（stale），不是直接重建。"""
    base = _compiled_knowledge_base()
    source = _point_id(base, "容量耗尽判定")
    dependent = _point_id(base, "动态数组扩容")
    assert any(
        relation["source_knowledge_id"] == source
        and relation["target_knowledge_id"] == dependent
        for relation in base["relations"]
    ), "测试前提：应存在 容量耗尽判定 -> 动态数组扩容 的前置关系"

    _, report = knowledge_impact_for_revision(
        base, _edit_statement(base, source), course_data=_knowledge_course(),
    )

    assert dependent in report["dependent_knowledge_ids"]
    stale_knowledge = {item.get("knowledge_id") for item in report["stale"]}
    assert dependent in stale_knowledge
    assert all(item.get("resolution") == "relation_dependency" for item in report["stale"])


def test_relation_traversal_is_depth_bounded() -> None:
    """关系遍历必须有界：无界传播会把"精确影响面"变成"几乎整门课程"。"""
    base = _compiled_knowledge_base()
    first = _point_id(base, "容量耗尽判定")
    second = _point_id(base, "动态数组扩容")

    reached = dependent_knowledge_ids(base, [first], max_depth=1)
    assert second in reached
    assert reached[second]["depth"] == 1
    assert reached[second]["relation_type"] == "prerequisite"

    # depth=0 表示不沿关系传播，只保留直接变化。
    assert dependent_knowledge_ids(base, [first], max_depth=0) == {}


def test_identity_violation_blocks_instead_of_silently_rebuilding() -> None:
    """身份被破坏时反查不可信，必须 blocked，不能给出一份看似精确的重建清单。"""
    base = _compiled_knowledge_base()
    dropped = _point_id(base, "动态数组扩容")
    after = deepcopy(base)
    after["knowledge_points"] = [
        point for point in after["knowledge_points"]
        if point["knowledge_id"] != dropped
    ]

    _, report = knowledge_impact_for_revision(
        base, after, course_data=_knowledge_course(), operation="split_point",
    )

    assert report["blocking"] is True
    assert report["identity_preserved"] is False
    blocked = {item["id"] for item in report["blocked"]}
    assert dropped in blocked
    assert all(
        item.get("resolution") == "requires_identity_migration"
        for item in report["blocked"]
    )
    # 被阻断的知识点不得同时出现在重建组里。
    assert dropped not in {item.get("knowledge_id") for item in report["needs_regeneration"]}


def test_course_without_knowledge_base_degrades_to_course_wide_review() -> None:
    """没有编译知识库时诚实降级为整门课程复核，不伪造更窄的影响面。"""
    base = _compiled_knowledge_base()
    event = knowledge_revision_event(base, _edit_statement(base, _point_id(base, "容量耗尽判定")))

    report = build_knowledge_impact_report(event, course_data=_course(), knowledge_base={})

    assert report["knowledge_index_available"] is False
    assert report["blocking"] is True
    assert [item["resolution"] for item in report["blocked"]] == ["course_fallback"]


def test_unreferenced_knowledge_change_is_reported_as_safe() -> None:
    """没有下游引用的知识点变化是安全状态，应显式说明而不是静默丢弃。"""
    base = _compiled_knowledge_base()
    after = deepcopy(base)
    orphan = {
        "knowledge_id": "ckp_orphan",
        "course_id": base["course_id"],
        "name": "尚未被引用的知识点",
        "statement": "该知识点还没有任何正文、练习或课件引用。",
        "knowledge_type": "definition",
        "revision_id": "ckpr_orphan",
        "section_refs": ["section-1"],
        "status": "active",
    }
    after["knowledge_points"] = after["knowledge_points"] + [orphan]
    after["revision_id"] = "ckbr_with_orphan"

    _, report = knowledge_impact_for_revision(
        base, after, course_data=_knowledge_course(),
    )

    changed = {
        item["id"] for item in report["changed"]
        if item.get("resolution") == "no_referencing_object"
    }
    assert "ckp_orphan" in changed
    assert report["blocking"] is False


def test_knowledge_impact_snapshot_is_stable_and_compact() -> None:
    """快照只保留分组与对象 ID，不 dump 整棵对象树。"""
    base = _compiled_knowledge_base()
    target = _point_id(base, "容量耗尽判定")
    _, report = knowledge_impact_for_revision(
        base, _edit_statement(base, target), course_data=_knowledge_course(),
    )

    snapshot = knowledge_impact_snapshot(report)

    assert snapshot["blocking"] is False
    assert snapshot["knowledge_index_available"] is True
    assert snapshot["identity_preserved"] is True
    assert set(snapshot["groups"]) <= {
        "changed", "needs_regeneration", "stale", "unchanged", "blocked",
    }
    for entries in snapshot["groups"].values():
        assert entries == sorted(entries)
        assert all(":" in entry for entry in entries)
    # 快照必须可重复：同一份报告两次投影结果相同。
    assert knowledge_impact_snapshot(report) == snapshot


# --- 反向：正文变化 -> 知识覆盖检查 -----------------------------------------


def test_changed_block_without_binding_is_reported_as_coverage_gap() -> None:
    """正文新增了知识库不认识的内容时，必须报出缺口以便发起知识维护候选。"""
    course = _knowledge_course()
    course["course_document"]["blocks"].append({
        "block_id": "block-new",
        "section_id": "section-1",
        "position": 2,
        "role": "concept",
        "payload": {"markdown": "新增的一段独立知识内容。"},
        "status": "active",
        "internal_revision": "cbr_new",
    })

    result = knowledge_coverage_check(course, changed_block_ids=["block-new"])

    assert result["requires_knowledge_review"] is True
    assert [item["gap"] for item in result["gaps"]] == ["block_without_knowledge_binding"]
    assert result["gaps"][0]["block_id"] == "block-new"


def test_changed_block_with_binding_reports_no_gap() -> None:
    """已被知识绑定覆盖的正文变化不该报缺口，否则每次改字都要求知识复核。"""
    course = _knowledge_course()
    bound = next(
        item["target_id"] for item in course["course_knowledge_base"]["bindings"]
        if item.get("target_type") == "course_block"
    )

    result = knowledge_coverage_check(course, changed_block_ids=[bound])

    assert result["gaps"] == []
    assert result["requires_knowledge_review"] is False
    assert [item["block_id"] for item in result["covered"]] == [bound]


def test_coverage_check_flags_block_missing_from_document() -> None:
    """引用了不存在的正文块时说明无法判断，而不是默默当作已覆盖。"""
    result = knowledge_coverage_check(_knowledge_course(), changed_block_ids=["block-ghost"])

    assert [item["gap"] for item in result["gaps"]] == ["block_not_in_document"]


# --- 失败保留：旧的正文、练习和 PPT 必须继续可读 -----------------------------


def _downstream_for_knowledge_edit() -> dict:
    """把一次知识修订的影响投影到下游状态，复用教案侧同一状态机。"""
    course = _knowledge_course()
    course["learning_assets"] = {
        "assets": {
            "questions": [
                _question_for_section(course, "section-1", "question-1"),
                _question_for_section(course, "section-2", "question-2"),
            ],
        },
    }
    base = course["course_knowledge_base"]
    _, report = knowledge_impact_for_revision(
        base,
        _edit_statement(base, _point_id(base, "容量耗尽判定")),
        course_data=course,
    )
    return build_downstream_state(
        report,
        plan_revision_id=course["course_teaching_plan"]["revision_id"],
        course_data=course,
    )


def test_failed_rebuild_keeps_old_body_practice_and_deck_readable() -> None:
    """产品级承诺：基于新知识重建失败时，旧的正文、练习和 PPT 仍可读。"""
    downstream = _downstream_for_knowledge_edit()
    readable_before = {
        (item["type"], item["id"])
        for item in downstream["items"]
        if isinstance(item.get("last_available"), dict)
    }
    assert readable_before, "测试前提：重建前应有可读的下游产物"

    failed = downstream
    for object_type, object_id in sorted(readable_before):
        failed = record_rebuild_outcome(
            failed,
            object_type=object_type,
            object_id=object_id,
            outcome="failed",
            error="知识变化后重建失败",
        )

    for item in failed["items"]:
        key = (item["type"], item["id"])
        if key not in readable_before:
            continue
        assert item["state"] == "rebuild_required"
        assert isinstance(item["last_available"], dict)
        assert item["last_available"]["readable"] is True
        assert item["last_build_error"] == "知识变化后重建失败"
        assert "保留" in item["reason"]

    assert failed["readable_fallback_count"] == len(readable_before)


def test_repeated_failures_never_downgrade_the_last_available_version() -> None:
    """反复失败不得逐次侵蚀最后可用版本，否则失败保留只在第一次成立。"""
    downstream = _downstream_for_knowledge_edit()
    target = next(
        item for item in downstream["items"]
        if isinstance(item.get("last_available"), dict)
    )
    original = deepcopy(target["last_available"])

    state = downstream
    for attempt in range(3):
        state = record_rebuild_outcome(
            state,
            object_type=target["type"],
            object_id=target["id"],
            outcome="failed",
            error=f"第 {attempt + 1} 次重建失败",
        )

    current = next(
        item for item in state["items"]
        if item["type"] == target["type"] and item["id"] == target["id"]
    )
    assert current["last_available"] == original


def test_successful_rebuild_moves_object_to_current() -> None:
    """成功重建后对象回到 current，并把最后可用版本推进到新修订。"""
    downstream = _downstream_for_knowledge_edit()
    target = next(
        item for item in downstream["items"]
        if item["state"] == "rebuild_required"
    )

    state = record_rebuild_outcome(
        downstream,
        object_type=target["type"],
        object_id=target["id"],
        outcome="succeeded",
        revision="rebuilt-1",
    )

    current = next(
        item for item in state["items"]
        if item["type"] == target["type"] and item["id"] == target["id"]
    )
    assert current["state"] == "current"
    assert current["last_available"]["revision"] == "rebuilt-1"
    assert "last_build_error" not in current


def test_downstream_state_snapshot_stays_readable() -> None:
    """下游状态快照同样只保留状态与可读集合。"""
    snapshot = downstream_state_snapshot(_downstream_for_knowledge_edit())

    assert snapshot["readable"] == sorted(snapshot["readable"])
    assert set(snapshot["states"].values()) <= {
        "current", "candidate", "rebuild_required", "lock_conflict", "blocked",
    }
