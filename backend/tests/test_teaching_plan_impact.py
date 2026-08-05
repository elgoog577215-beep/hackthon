"""影响矩阵与下游状态测试（tasks 3.3–3.6）。

快照测试刻意只断言"哪些对象进入哪一组"，不 dump 整棵对象树：
对象树里的 reason 文案、修订号和时间戳会随无关改动漂移，
把它们写进快照只会制造假失败，掩盖真正的影响面回归。
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from content_blocks import set_node_content_blocks
from course_document import CourseBlock, CourseDocument, CourseSection, refresh_document_revision
from course_knowledge_base import compile_course_knowledge_base
from course_knowledge_map import compile_course_knowledge_map
from course_repository import CourseDocumentRepository
from teaching_plan_impact import (
    KnowledgeReferenceIndex,
    build_downstream_state,
    build_impact_report,
    change_category,
    downstream_source_check,
    downstream_state_snapshot,
    impact_matrix_snapshot,
    record_rebuild_outcome,
)
from teaching_plan_workbench import TeachingPlanWorkbenchService
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
            "mastery_criteria": [{
                "name": "扩容实现与分析达标",
                "observable_performance": "独立实现倍增扩容，并正确说明最坏成本与摊还成本的区别",
                "verification_method": "运行连续插入测试并提交复杂度推导",
            }],
            "aliases": ["可变长数组"],
        },
    ]


def _knowledge_course() -> dict:
    """一门带真实编译知识库的课程，用于引用反查。"""
    course = {
        "course_id": "course-1",
        "course_name": "数据结构",
        "course_purpose": "systematic",
        "subject_pedagogy_profile": {
            "primary_mode": "programming_engineering",
            "secondary_mode": None,
            "secondary_intensity": None,
            "confidence": "high",
            "evidence": [],
            "rationale": "先实现再分析复杂度。",
            "enabled_module_ids": [],
            "user_locked": True,
        },
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
            "assessment": ["在不同扩容因子下比较摊还成本"],
            "difficulty_contract": {
                "challenge": {"reasoning_depth": 3, "transfer_distance": 3},
                "support": {"scaffold_intensity": 3},
                "mastery": {"independence": 3},
                "subject_task": "implementation_task",
            },
            "grounding_contract": {},
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
    course = _knowledge_course()
    return compile_course_knowledge_base(
        course, course_map=compile_course_knowledge_map(course),
    )


def _course(*, with_knowledge_base: bool = False) -> dict:
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
            CourseBlock(
                block_id="block-1",
                section_id="section-1",
                position=0,
                role="concept",
                payload={"markdown": "扩容触发条件。"},
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
        "course_plan": {
            "course_title": "数据结构",
            "positioning": "从实现到复杂度分析",
            "learning_objectives": ["理解摊还分析"],
            "prerequisites": ["基本数组操作"],
            "chapters": [{
                "chapter_number": 1,
                "title": "线性结构",
                "sections": [
                    {
                        "node_id": "section-1",
                        "title": "线性表与动态数组",
                        "learning_objective": "能够实现动态数组扩容并分析摊还复杂度",
                        "module_plan": [{
                            "module_id": "core",
                            "label": "核心讲解",
                            "required": True,
                            "output_contract": "解释扩容",
                            "prompt_instruction": "从复制次数说明摊还成本",
                        }],
                    },
                    {
                        "node_id": "section-2",
                        "title": "链表",
                        "learning_objective": "能够比较链表与数组的插入代价",
                        "module_plan": [{
                            "module_id": "core",
                            "label": "核心讲解",
                            "required": True,
                            "output_contract": "比较插入代价",
                            "prompt_instruction": "对比两种结构",
                        }],
                    },
                ],
            }],
        },
        "generation_request": {"target_audience": "计算机专业二年级学生"},
        "subject_pedagogy_profile": {"rationale": "先实现再分析复杂度。"},
        "course_teaching_plan": {
            "schema_version": "course_teaching_plan_v3",
            "source_outline_revision_id": "outline-1",
            "revision_id": "teaching-initial",
            "sections": [
                {
                    "node_id": "section-1",
                    "key_points": ["容量耗尽判定", "动态数组扩容"],
                    "reused_knowledge_names": [],
                    "knowledge_relations": [],
                    "knowledge_structure": [{
                        "concept_group": "动态容量管理",
                        "knowledge_points": [
                            {
                                "name": point["name"],
                                "statement": point["statement"],
                                "capability": point["capability_points"][0]["name"],
                                "capability_points": point["capability_points"],
                                "conditions": point.get("conditions", []),
                                "boundaries": point.get("boundaries", []),
                                "mastery_criteria": [{
                                    "observable_performance": point["mastery_criteria"][0][
                                        "observable_performance"
                                    ],
                                    "verification_method": point["mastery_criteria"][0][
                                        "verification_method"
                                    ],
                                }],
                                "misconceptions": [],
                            }
                            for point in _knowledge_points()
                        ],
                    }],
                    "teaching_modules": [{
                        "module_id": "core",
                        "teaching_purpose": "建立摊还成本直觉",
                        "knowledge_names": ["容量耗尽判定", "动态数组扩容"],
                        "teaching_guidance": "先数复制次数，再归纳摊还成本。",
                    }],
                },
                {
                    "node_id": "section-2",
                    "key_points": ["链表插入"],
                    "reused_knowledge_names": [],
                    "knowledge_relations": [],
                    "knowledge_structure": [{
                        "concept_group": "链式结构",
                        "knowledge_points": [{
                            "name": "链表插入",
                            "statement": "链表插入只需修改指针，不需要移动后继元素。",
                            "capability": "能够比较两种结构的插入代价",
                            "capability_points": [{
                                "name": "比较插入代价",
                                "observable_behavior": "能对同一插入序列说明两种结构的代价差异",
                            }],
                            "conditions": ["已持有插入位置的前驱指针"],
                            "boundaries": ["不包含查找前驱的代价"],
                            "mastery_criteria": [{
                                "observable_performance": "能说明为什么链表插入是常数阶",
                                "verification_method": "出口题",
                            }],
                            "misconceptions": [],
                        }],
                    }],
                    "teaching_modules": [{
                        "module_id": "core",
                        "teaching_purpose": "对比插入代价",
                        "knowledge_names": ["链表插入"],
                        "teaching_guidance": "用同一组插入序列对比两种结构。",
                    }],
                },
            ],
        },
        "generation_stage_artifacts": {"course_teaching_plan": {"status": "completed"}},
    }
    if with_knowledge_base:
        course["course_knowledge_base"] = _compiled_knowledge_base()
    return course


def _question_for_section(course: dict, section_id: str, question_id: str) -> dict:
    """一道服务于该小节当前学习目标的正式练习。

    使用真实的 learning_objective_identity，这样"目标被改写后练习过期"
    走的是生产代码同一条路径，而不是测试自己造的假修订号。
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


def _operations(*paths: str) -> list[dict]:
    return [{"operation_id": f"op-{index}", "path": path}
            for index, path in enumerate(paths)]


def _report(*paths: str, course: dict | None = None) -> dict:
    course_data = course if course is not None else _course()
    snapshot = {
        "course_plan": course_data.get("course_plan") or {},
        "generation_request": course_data.get("generation_request") or {},
        "subject_pedagogy_profile": course_data.get("subject_pedagogy_profile") or {},
        "course_teaching_plan": course_data.get("course_teaching_plan") or {},
    }
    return build_impact_report(
        _operations(*paths), snapshot, course_data=course_data,
    )


# --- 3.3 知识引用反查 ------------------------------------------------------


def test_knowledge_index_resolves_plan_names_and_aliases_to_stable_ids() -> None:
    index = KnowledgeReferenceIndex(_compiled_knowledge_base())
    assert index.available is True
    knowledge_id = index.resolve("section-1", "容量耗尽判定")
    assert knowledge_id.startswith("ckp_")
    # 别名必须解析到同一个稳定 ID，否则教师改别名会被当成改了另一个知识点。
    assert index.resolve("section-1", "满容量判定") == knowledge_id
    assert index.display_name(knowledge_id) == "容量耗尽判定"
    assert index.resolve("section-1", "不存在的知识点") == ""


def test_knowledge_change_only_invalidates_objects_that_reference_it() -> None:
    """3.3 的核心：两个知识点的影响面必须不同，不能整节全炸。"""
    course = _course(with_knowledge_base=True)
    index = KnowledgeReferenceIndex(course["course_knowledge_base"])
    first = index.resolve("section-1", "容量耗尽判定")
    second = index.resolve("section-1", "动态数组扩容")
    assert first and second and first != second

    first_targets = set(index.referencing_targets(first))
    second_targets = set(index.referencing_targets(second))
    assert first_targets != second_targets
    # 各自引用到不同的课程块与掌握标准，这正是局部影响预览的依据。
    first_blocks = {item for item in first_targets if item[0] == "section_content"}
    second_blocks = {item for item in second_targets if item[0] == "section_content"}
    assert first_blocks and second_blocks
    assert not (first_blocks & second_blocks)


def test_knowledge_impact_reports_referenced_blocks_and_criteria() -> None:
    course = _course(with_knowledge_base=True)
    report = _report("sections/section-1/knowledge/容量耗尽判定/statement", course=course)
    assert report["knowledge_index_available"] is True
    regenerate = {(item["type"], item["id"]) for item in report["needs_regeneration"]}
    index = KnowledgeReferenceIndex(course["course_knowledge_base"])
    knowledge_id = index.resolve("section-1", "容量耗尽判定")
    assert ("knowledge_binding", knowledge_id) in regenerate
    referenced_blocks = {
        item[1] for item in index.referencing_targets(knowledge_id)
        if item[0] == "section_content"
    }
    assert referenced_blocks
    assert all(("section_content", block) in regenerate for block in referenced_blocks)
    # 没有引用该知识点的另一小节必须留在 unchanged。
    unchanged = {item["id"] for item in report["unchanged"]}
    assert "section-2" in unchanged


def test_course_without_knowledge_bindings_degrades_conservatively() -> None:
    """缺少知识绑定时按整节保守失效，并明确标注降级原因，不伪造更窄影响面。"""
    report = _report("sections/section-1/knowledge/容量耗尽判定/statement")
    assert report["knowledge_index_available"] is False
    fallback = [
        item for item in report["needs_regeneration"]
        if item.get("resolution") == "section_fallback"
    ]
    assert fallback
    assert all(item["id"] == "section-1" for item in fallback)
    assert {item["type"] for item in fallback} == {
        "knowledge_binding", "section_content", "practice", "slide_deck",
    }


# --- 3.4 下游来源修订检查 --------------------------------------------------


def test_downstream_source_check_covers_document_blocks_practice_and_representations(
    tmp_path,
) -> None:
    course = _course()
    course["course_revision_vector"] = {
        "revisions": {"course_teaching_plan": "teaching-initial"},
    }
    course["learning_assets"] = {
        "assets": {"questions": [
            _question_for_section(course, "section-1", "q-1"),
        ]},
    }
    now = datetime.now(timezone.utc).isoformat()
    binding = SourceBinding(
        course_id="course-1",
        source_revisions={"course_teaching_plan": "teaching-initial"},
    )
    repository = TeachingRepresentationRepository(tmp_path / "representations")
    repository.register_representation(TeachingRepresentation(
        representation_id="deck-1",
        course_id="course-1",
        representation_type="slide_deck",
        source_bindings=[binding],
        source_revision_vector=binding.source_revisions,
        spec_id="spec-deck-1",
        artifact_ids=["artifact-deck-1"],
        semantic_fingerprint="fp-deck-1",
        revision="rev-deck-1",
        status="ready",
        created_at=now,
        updated_at=now,
    ))

    rows = downstream_source_check(
        plan_revision_id="teaching-initial",
        course_data=course,
        registry=repository.load("course-1"),
    )
    by_type = {row["type"] for row in rows}
    assert {"course_document", "section_content", "practice", "slide_deck"} <= by_type
    assert all(row["source_state"] == "current" for row in rows)

    # 教案修订前进后，按教案修订绑定的对象转为 stale。
    moved = downstream_source_check(
        plan_revision_id="teaching-next",
        course_data=course,
        registry=repository.load("course-1"),
    )
    by_id = {row["id"]: row for row in moved}
    assert by_id["block-1"]["source_state"] == "stale"
    assert by_id["deck-1"]["source_state"] == "stale"
    # 练习按它服务的学习目标判定：目标没被改写，练习就不该被误判为过期。
    assert by_id["q-1"]["source_state"] == "current"
    assert by_id["q-1"]["source_basis"] == "objective_revision"
    # 但 stale 不等于不可读。
    assert all(row["readable"] for row in moved)


def test_objective_revisions_match_across_legacy_and_canonical_course_shapes() -> None:
    """新旧课程形态必须算出同一组目标身份，否则历史课程会被整体误判过期。"""
    from teaching_plan_impact import _objective_revisions

    legacy = {
        "course_id": "course-1",
        "nodes": [{
            "node_id": "section-1",
            "node_name": "线性表与动态数组",
            "learning_objective": "能够实现动态数组扩容并分析摊还复杂度",
        }],
    }
    canonical = {
        "course_id": "course-1",
        "course_document": {"sections": [{
            "section_id": "section-1",
            "title": "线性表与动态数组",
            "learning_objective": "能够实现动态数组扩容并分析摊还复杂度",
        }]},
    }
    assert _objective_revisions(legacy) == _objective_revisions(canonical)
    assert _objective_revisions(legacy)
    # 没有小节的课程不应炸，只返回空映射。
    assert _objective_revisions({"course_id": "course-1"}) == {}


def test_practice_goes_stale_only_when_its_own_objective_is_rewritten() -> None:
    """练习的失效信号来自它服务的学习目标，而不是一个没有生产者写入的字段。"""
    course = _course()
    course["learning_assets"] = {
        "assets": {"questions": [
            _question_for_section(course, "section-1", "q-1"),
            _question_for_section(course, "section-2", "q-2"),
        ]},
    }
    fresh = {
        row["id"]: row for row in downstream_source_check(
            plan_revision_id="teaching-initial", course_data=course,
        )
    }
    assert fresh["q-1"]["source_state"] == "current"
    assert fresh["q-2"]["source_state"] == "current"

    # 只改写 section-1 的目标：只有服务该目标的练习过期。
    rewritten = deepcopy(course)
    section = next(
        item for item in rewritten["course_document"]["sections"]
        if item["section_id"] == "section-1"
    )
    section["learning_objective"] = "能够实现倍增扩容并用复制次数解释摊还复杂度"
    moved = {
        row["id"]: row for row in downstream_source_check(
            plan_revision_id="teaching-initial", course_data=rewritten,
        )
    }
    assert moved["q-1"]["source_state"] == "stale"
    assert moved["q-2"]["source_state"] == "current"
    # 过期不等于不可读：旧练习必须继续可用。
    assert moved["q-1"]["readable"] is True


def test_practice_without_objective_identity_is_reported_as_unverifiable() -> None:
    """无法证明新鲜度时保守判 stale，并说明依据，不假装验证过。"""
    course = _course()
    course["learning_assets"] = {
        "assets": {"questions": [{"question_id": "q-legacy", "node_id": "section-1"}]},
    }
    row = next(
        item for item in downstream_source_check(
            plan_revision_id="teaching-initial", course_data=course,
        )
        if item["id"] == "q-legacy"
    )
    assert row["source_state"] == "stale"
    assert row["source_basis"] == "objective_revision_unavailable"
    assert row["readable"] is True


def test_failed_representation_is_stale_but_still_readable(tmp_path) -> None:
    now = datetime.now(timezone.utc).isoformat()
    binding = SourceBinding(
        course_id="course-1",
        source_revisions={"course_teaching_plan": "teaching-initial"},
    )
    repository = TeachingRepresentationRepository(tmp_path / "representations")
    repository.register_representation(TeachingRepresentation(
        representation_id="deck-failed",
        course_id="course-1",
        representation_type="slide_deck",
        source_bindings=[binding],
        source_revision_vector=binding.source_revisions,
        spec_id="spec-deck-failed",
        artifact_ids=["artifact-deck-failed"],
        semantic_fingerprint="fp-failed",
        revision="rev-failed",
        status="failed",
        created_at=now,
        updated_at=now,
    ))
    rows = downstream_source_check(
        plan_revision_id="teaching-initial",
        course_data=_course(),
        registry=repository.load("course-1"),
    )
    deck = next(row for row in rows if row["id"] == "deck-failed")
    assert deck["source_state"] == "stale"
    assert deck["readable"] is True


# --- 3.5 六类变更影响矩阵快照 ----------------------------------------------


def test_change_category_classifies_the_six_matrix_rows() -> None:
    assert change_category("overall/positioning") == "descriptive"
    assert change_category("sections/section-1/learning_objective") == "objective"
    assert change_category("sections/section-1/teaching_modules/core/teaching_guidance") == "module"
    assert change_category("sections/section-1/knowledge/动态数组扩容/statement") == "knowledge"
    assert change_category("sections/section-1/key_points") == "relation"
    assert change_category("course_plan/chapters") == "chapter"


def test_descriptive_change_snapshot_keeps_content_and_practice_untouched() -> None:
    snapshot = impact_matrix_snapshot(_report("overall/positioning"))
    assert snapshot == {
        "categories": ["descriptive"],
        "knowledge_index_available": False,
        "blocking": False,
        "groups": {
            "changed": ["teacher_projection:overall", "teaching_plan:overall"],
            "unchanged": ["section_content:section-1", "section_content:section-2"],
        },
    }


def test_objective_change_snapshot_is_scoped_to_its_own_section() -> None:
    snapshot = impact_matrix_snapshot(_report("sections/section-1/learning_objective"))
    assert snapshot == {
        "categories": ["objective"],
        "knowledge_index_available": False,
        "blocking": False,
        "groups": {
            "changed": ["teaching_plan_section:section-1"],
            "needs_regeneration": [
                "practice:section-1",
                "section_content:section-1",
                "slide_deck:section-1",
            ],
            "unchanged": ["section_content:section-2"],
        },
    }


def test_module_change_snapshot_touches_lecture_but_not_practice() -> None:
    snapshot = impact_matrix_snapshot(
        _report("sections/section-1/teaching_modules/core/teaching_guidance"),
    )
    assert snapshot == {
        "categories": ["module"],
        "knowledge_index_available": False,
        "blocking": False,
        "groups": {
            "changed": ["teaching_plan_section:section-1"],
            "needs_regeneration": [
                "lecture:section-1",
                "section_content:section-1",
                "slide_deck:section-1",
            ],
            "unchanged": ["section_content:section-2"],
        },
    }


def test_knowledge_change_snapshot_follows_real_bindings() -> None:
    course = _course(with_knowledge_base=True)
    index = KnowledgeReferenceIndex(course["course_knowledge_base"])
    knowledge_id = index.resolve("section-1", "动态数组扩容")
    snapshot = impact_matrix_snapshot(
        _report("sections/section-1/knowledge/动态数组扩容/statement", course=course),
    )
    assert snapshot["categories"] == ["knowledge"]
    assert snapshot["knowledge_index_available"] is True
    assert snapshot["blocking"] is False
    assert snapshot["groups"]["changed"] == ["teaching_plan_section:section-1"]
    assert f"knowledge_binding:{knowledge_id}" in snapshot["groups"]["needs_regeneration"]
    # 未引用该知识点的小节保持不变。
    assert snapshot["groups"]["unchanged"] == ["section_content:section-2"]


def test_relation_change_snapshot_blocks_until_reviewed() -> None:
    snapshot = impact_matrix_snapshot(_report("sections/section-1/knowledge_relations"))
    assert snapshot == {
        "categories": ["relation"],
        "knowledge_index_available": False,
        "blocking": True,
        "groups": {
            "changed": ["teaching_plan_section:section-1"],
            "blocked": ["knowledge_relation:section-1"],
            "unchanged": ["section_content:section-2"],
        },
    }


def test_chapter_change_snapshot_redirects_to_the_outline_editor() -> None:
    report = _report("course_plan/chapters")
    snapshot = impact_matrix_snapshot(report)
    assert snapshot == {
        "categories": ["chapter"],
        "knowledge_index_available": False,
        "blocking": True,
        "groups": {
            "blocked": ["course_outline:course_plan/chapters"],
            "unchanged": ["section_content:section-1", "section_content:section-2"],
        },
    }
    assert report["blocked"][0]["redirect"] == "redirect_to_outline_edit"


# --- 3.6 下游状态与失败保留 ------------------------------------------------


def test_downstream_state_marks_candidates_rebuild_and_lock_conflicts(tmp_path) -> None:
    course = _course()
    course["course_revision_vector"] = {
        "revisions": {"course_teaching_plan": "teaching-initial"},
    }
    now = datetime.now(timezone.utc).isoformat()
    binding = SourceBinding(
        course_id="course-1",
        source_revisions={"course_teaching_plan": "teaching-initial"},
    )
    repository = TeachingRepresentationRepository(tmp_path / "representations")
    repository.register_representation(TeachingRepresentation(
        representation_id="deck-1",
        course_id="course-1",
        representation_type="slide_deck",
        source_bindings=[binding],
        source_revision_vector=binding.source_revisions,
        spec_id="spec-deck-1",
        artifact_ids=["artifact-deck-1"],
        semantic_fingerprint="fp-deck-1",
        revision="rev-deck-1",
        status="ready",
        created_at=now,
        updated_at=now,
    ))
    report = _report("sections/section-1/learning_objective", course=course)
    state = build_downstream_state(
        report,
        plan_revision_id="teaching-next",
        course_data=course,
        registry=repository.load("course-1"),
        locked_object_ids=["practice"],
    )
    states = downstream_state_snapshot(state)["states"]
    assert states["section_content:section-1"] == "rebuild_required"
    assert states["practice:section-1"] == "lock_conflict"
    assert state["counts"]["rebuild_required"] >= 1
    assert state["counts"]["lock_conflict"] == 1
    # 锁定冲突必须解释原因，而不是静默丢弃这次重建。
    locked = next(item for item in state["items"] if item["state"] == "lock_conflict")
    assert "其他链路" in locked["reason"]


def test_failed_rebuild_keeps_the_last_usable_artifact_readable(tmp_path) -> None:
    """3.6 的产品承诺：新产物失败时，旧正文/练习/PPT 必须继续可读。"""
    course = _course()
    course["course_revision_vector"] = {
        "revisions": {"course_teaching_plan": "teaching-initial"},
    }
    now = datetime.now(timezone.utc).isoformat()
    binding = SourceBinding(
        course_id="course-1",
        source_revisions={"course_teaching_plan": "teaching-initial"},
    )
    repository = TeachingRepresentationRepository(tmp_path / "representations")
    repository.register_representation(TeachingRepresentation(
        representation_id="deck-1",
        course_id="course-1",
        representation_type="slide_deck",
        source_bindings=[binding],
        source_revision_vector=binding.source_revisions,
        spec_id="spec-deck-1",
        artifact_ids=["artifact-deck-1"],
        semantic_fingerprint="fp-deck-1",
        revision="rev-deck-1",
        status="ready",
        created_at=now,
        updated_at=now,
    ))
    report = _report("sections/section-1/learning_objective", course=course)
    state = build_downstream_state(
        report,
        plan_revision_id="teaching-next",
        course_data=course,
        registry=repository.load("course-1"),
    )
    deck = next(item for item in state["items"] if item["id"] == "deck-1")
    assert isinstance(deck["last_available"], dict)
    assert deck["last_available"]["revision"] == "rev-deck-1"

    failed = record_rebuild_outcome(
        state,
        object_type="slide_deck",
        object_id="deck-1",
        outcome="failed",
        error="slide_variant_rebuild_failed",
    )
    after = next(item for item in failed["items"] if item["id"] == "deck-1")
    # 失败没有清空 last_available：教师仍然可以打开上一版 PPT。
    assert after["state"] == "rebuild_required"
    assert after["last_available"]["revision"] == "rev-deck-1"
    assert after["last_build_error"] == "slide_variant_rebuild_failed"
    assert "仍可查看旧内容" in after["reason"]
    assert failed["readable_fallback_count"] >= 1


def test_repeated_failures_never_downgrade_the_preserved_version(tmp_path) -> None:
    course = _course()
    now = datetime.now(timezone.utc).isoformat()
    binding = SourceBinding(
        course_id="course-1",
        source_revisions={"course_teaching_plan": "teaching-initial"},
    )
    repository = TeachingRepresentationRepository(tmp_path / "representations")
    repository.register_representation(TeachingRepresentation(
        representation_id="deck-1",
        course_id="course-1",
        representation_type="slide_deck",
        source_bindings=[binding],
        source_revision_vector=binding.source_revisions,
        spec_id="spec-deck-1",
        artifact_ids=["artifact-deck-1"],
        semantic_fingerprint="fp-deck-1",
        revision="rev-deck-1",
        status="ready",
        created_at=now,
        updated_at=now,
    ))
    report = _report("sections/section-1/learning_objective", course=course)
    state = build_downstream_state(
        report,
        plan_revision_id="teaching-next",
        course_data=course,
        registry=repository.load("course-1"),
    )
    for _ in range(3):
        state = record_rebuild_outcome(
            state,
            object_type="slide_deck",
            object_id="deck-1",
            outcome="failed",
            error="rebuild failed again",
        )
        # 反复失败后，保留的仍然是最后一个真正可用的版本。
        deck = next(item for item in state["items"] if item["id"] == "deck-1")
        assert deck["last_available"]["revision"] == "rev-deck-1"

    # 第二轮影响分析同样不能把已保留的版本抹掉。
    rebuilt = build_downstream_state(
        report,
        plan_revision_id="teaching-third",
        course_data=course,
        registry=repository.load("course-1"),
        previous=state,
    )
    deck = next(item for item in rebuilt["items"] if item["id"] == "deck-1")
    assert deck["last_available"]["revision"] == "rev-deck-1"


def test_successful_rebuild_advances_the_readable_version(tmp_path) -> None:
    course = _course()
    report = _report("sections/section-1/learning_objective", course=course)
    state = build_downstream_state(
        report,
        plan_revision_id="teaching-next",
        course_data=course,
    )
    ready = record_rebuild_outcome(
        state,
        object_type="section_content",
        object_id="section-1",
        outcome="candidate_ready",
        revision="rev-candidate",
    )
    candidate = next(
        item for item in ready["items"]
        if item["type"] == "section_content" and item["id"] == "section-1"
    )
    assert candidate["state"] == "candidate"
    assert candidate["candidate_revision"] == "rev-candidate"

    done = record_rebuild_outcome(
        ready,
        object_type="section_content",
        object_id="section-1",
        outcome="succeeded",
        revision="rev-final",
    )
    final = next(
        item for item in done["items"]
        if item["type"] == "section_content" and item["id"] == "section-1"
    )
    assert final["state"] == "current"
    assert final["last_available"]["revision"] == "rev-final"


@pytest.mark.asyncio
async def test_applying_a_plan_revision_records_downstream_state_without_touching_artifacts(
    tmp_path,
) -> None:
    """影响分析是只读的：应用教案修订不得改写正文块或 PPT 产物。"""
    storage = MemoryStorage(_course(with_knowledge_base=True))
    now = datetime.now(timezone.utc).isoformat()
    binding = SourceBinding(
        course_id="course-1",
        source_revisions={"course_teaching_plan": "teaching-initial"},
    )
    representation_repository = TeachingRepresentationRepository(tmp_path / "representations")
    representation_repository.register_representation(TeachingRepresentation(
        representation_id="deck-1",
        course_id="course-1",
        representation_type="slide_deck",
        source_bindings=[binding],
        source_revision_vector=binding.source_revisions,
        spec_id="spec-deck-1",
        artifact_ids=["artifact-deck-1"],
        semantic_fingerprint="fp-deck-1",
        revision="rev-deck-1",
        status="ready",
        created_at=now,
        updated_at=now,
    ))
    service = TeachingPlanWorkbenchService(
        CourseDocumentRepository(storage),
        representation_repository=representation_repository,
    )
    blocks_before = deepcopy(storage.course["course_document"]["blocks"])

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
        path="sections/section-1/learning_objective",
        value="能够实现倍增扩容并用复制次数解释摊还复杂度",
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
    applied = await service.apply_change_set(
        "course-1",
        actor="teacher-1",
        change_set_id=change_set["change_set_id"],
        idempotency_key="apply-1",
    )

    downstream = applied["workbench"]["downstream"]
    assert downstream["schema_version"] == "teaching_plan_downstream_state_v1"
    states = downstream_state_snapshot(downstream)["states"]
    assert states["section_content:section-1"] == "rebuild_required"
    # PPT 来源已过期，但旧产物仍被记录为可读的最后可用版本。
    deck = next(item for item in downstream["items"] if item["id"] == "deck-1")
    assert deck["last_available"]["revision"] == "rev-deck-1"
    # 只读分析：课程正文块没有被影响分析改写。
    assert storage.course["course_document"]["blocks"] == blocks_before
