"""影响面明细测试（教师要能点开看到具体是哪些对象）。

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
from course_knowledge_impact import knowledge_impact_for_revision
from course_knowledge_impact_detail import (
    build_impact_detail,
    describe_impact_item,
    impact_detail_snapshot,
)
from course_knowledge_map import compile_course_knowledge_map
from teaching_plan_impact import KnowledgeReferenceIndex


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


def _knowledge_course() -> dict:
    return _course(with_knowledge_base=True)


def _point_id(knowledge_base: dict, name: str) -> str:
    knowledge_id = KnowledgeReferenceIndex(knowledge_base).resolve("section-1", name)
    assert knowledge_id, f"知识点 {name} 未解析到稳定 ID"
    return knowledge_id


def _report(course: dict) -> dict:
    base = course["course_knowledge_base"]
    edited = deepcopy(base)
    target = _point_id(base, "容量耗尽判定")
    for point in edited["knowledge_points"]:
        if point["knowledge_id"] == target:
            point["statement"] = "改写后的陈述。"
            point["revision_id"] = "ckpr_edited"
    edited["revision_id"] = "ckbr_edited"
    _, report = knowledge_impact_for_revision(base, edited, course_data=course)
    return report


def test_detail_turns_ids_into_readable_rows() -> None:
    """影响面不能只给 ID：教师要看到标题、位置和摘要。"""
    course = _knowledge_course()

    detail = build_impact_detail(_report(course), course_data=course)

    rows = detail["groups"]["needs_regeneration"]
    assert rows, "测试前提：该编辑应有直接受影响的对象"
    blocks = [row for row in rows if row["type"] == "section_content"]
    assert blocks, "测试前提：应有受影响的正文块"
    for row in blocks:
        assert row["type_label"] == "正文块"
        # 标题与摘要必须来自真实课程内容，不能是 ID 兜底。
        assert row["title"] and row["title"] != row["id"]
        assert row["excerpt"]
        assert row["section_id"]


def test_detail_counts_match_the_impact_report() -> None:
    """明细计数必须与影响报告一致，否则面板上的数字对不上。"""
    course = _knowledge_course()
    report = _report(course)

    detail = build_impact_detail(report, course_data=course)

    for group in ("needs_regeneration", "stale", "blocked", "changed"):
        assert detail["counts"][group] == len(report.get(group) or [])


def test_practice_rows_show_the_question_prompt() -> None:
    """练习题要显示题干，不是 question_id。"""
    course = _knowledge_course()
    course["learning_assets"] = {
        "questions": [{
            "question_id": "q-1",
            "node_id": "section-1",
            "prompt": "给定长度与容量，判断下一次插入是否触发扩容。",
        }],
    }
    item = {"type": "practice", "id": "q-1", "reason": "引用了变化的知识点"}

    from course_knowledge_impact_detail import _document_index, _question_index

    row = describe_impact_item(
        item,
        documents=_document_index(course),
        questions=_question_index(course),
        knowledge={},
    )

    assert row["type_label"] == "练习题"
    assert "扩容" in row["title"]
    assert row["location"] == "线性表与动态数组"


def test_missing_object_is_flagged_not_hidden() -> None:
    """引用了已不存在的对象时要显式标出，不能留一行空白。"""
    course = _knowledge_course()

    from course_knowledge_impact_detail import _document_index, _question_index

    row = describe_impact_item(
        {"type": "section_content", "id": "block-ghost"},
        documents=_document_index(course),
        questions=_question_index(course),
        knowledge={},
    )

    assert row["missing"] is True
    assert row["title"] == "block-ghost"


def test_excerpt_is_bounded() -> None:
    """摘要必须截断：明细是给教师定位用的，不是在侧栏里读全文。"""
    course = _knowledge_course()
    long_text = "很长的正文。" * 200
    course["course_document"]["blocks"][0]["payload"] = {"markdown": long_text}

    from course_knowledge_impact_detail import EXCERPT_LENGTH, _document_index, _question_index

    row = describe_impact_item(
        {"type": "section_content", "id": course["course_document"]["blocks"][0]["block_id"]},
        documents=_document_index(course),
        questions=_question_index(course),
        knowledge={},
    )

    assert len(row["excerpt"]) <= EXCERPT_LENGTH
    assert row["excerpt"].endswith("…")


def test_truncation_is_reported_rather_than_silent() -> None:
    """超过上限时必须说明被截断，否则短列表会被误读成全部。"""
    course = _knowledge_course()
    report = _report(course)
    assert len(report["needs_regeneration"]) > 1

    detail = build_impact_detail(report, course_data=course, limit_per_group=1)

    assert detail["truncated"]["needs_regeneration"] is True
    assert len(detail["groups"]["needs_regeneration"]) == 1
    # 计数仍报真实总数，不被上限影响。
    assert detail["counts"]["needs_regeneration"] == len(report["needs_regeneration"])


def test_detail_snapshot_is_stable() -> None:
    """快照只保留分组与对象 ID，不 dump 整棵明细树。"""
    course = _knowledge_course()
    detail = build_impact_detail(_report(course), course_data=course)

    snapshot = impact_detail_snapshot(detail)

    assert set(snapshot) == {"counts", "truncated", "groups"}
    assert snapshot["truncated"] == []
    for entries in snapshot["groups"].values():
        assert entries == sorted(entries)
    assert impact_detail_snapshot(detail) == snapshot
