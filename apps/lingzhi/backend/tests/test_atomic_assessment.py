from copy import deepcopy

from assessment_blueprint import compile_course_assessment_blueprint, slot_for
from question_knowledge_binding import knowledge_point_coverage
from routers.question_bank import _question_source_revision, _item_practice_levels_by_node


def atomic_course():
    return {
        "course_id": "atomic-course", "course_name": "C语言", "nodes": [{
            "node_id": "types", "node_level": 2, "node_name": "类型",
            "key_points": ["整数除法", "赋值转换"],
            "node_content": "整数除法先计算整数结果，再把该结果转换为赋值目标类型。" * 8,
        }],
        "course_knowledge_base": {
            "lifecycle_status": "active", "revision_id": "baseline-1",
            "knowledge_points": [{
                "knowledge_id": key, "revision_id": key + "-v1", "status": "active",
                "granularity_status": "atomic", "section_refs": ["types"],
                "name": name, "statement": statement, "meta_question": question,
                "conditions": ["C17，操作数为int且除数不为零"], "source_refs": ["source-1"],
            } for key, name, statement, question in [
                ("division", "整数除法", "整数除法截去小数部分", "5/2的结果是什么？"),
                ("conversion", "赋值转换", "转为double不能恢复已截去的小数", "double x=5/2能恢复小数吗？"),
            ]],
            "sources": [{"source_id": "source-1", "text": "C17课程复核材料"}],
            "relations": [],
        },
    }


def test_atomic_plan_has_one_exact_target_per_point_instead_of_three_chapter_slots():
    course = atomic_course()
    blueprint = compile_course_assessment_blueprint(course)
    slots = blueprint["nodes"][0]["slots"]
    assert len(slots) == 2
    assert {tuple(s["primary_knowledge_ids"]) for s in slots} == {("division",), ("conversion",)}
    assert len({s["generation_key"] for s in slots}) == 2
    for slot in slots:
        assert slot_for(blueprint, "types", slot["generation_key"]) == slot
        assert slot["knowledge_baseline_revision"] == "baseline-1"
        assert slot["assessment_purpose"] == "atomic_check"


def test_atomic_plan_ignores_candidates_and_does_not_fall_back_to_broad_slots():
    course = atomic_course()
    course["course_knowledge_base"]["knowledge_points"][0]["status"] = "candidate"
    slots = compile_course_assessment_blueprint(course)["nodes"][0]["slots"]
    assert len(slots) == 1
    assert slots[0]["primary_knowledge_ids"] == ["conversion"]


def test_question_source_snapshot_detects_knowledge_revision_change():
    course = atomic_course()
    before = _question_source_revision(course)
    course["course_knowledge_base"]["knowledge_points"][0]["revision_id"] = "division-v2"
    assert _question_source_revision(course) != before


def test_item_rebuild_selects_exact_atomic_slot():
    item = {"revision_id": "q1", "node_id": "types", "practice_levels": ["concept_check"],
            "generation_key": "atomic-division"}
    assert _item_practice_levels_by_node({"items": [item]}, revision_ids=["q1"]) == {"types": ["atomic-division"]}


def test_coverage_distinguishes_current_approved_evidence_from_mentions():
    course = atomic_course()
    items = [{"item_id": "q1", "course_knowledge_refs": ["division", "conversion"],
              "lifecycle_status": "candidate"}]
    report = knowledge_point_coverage(course, items)
    assert report["covered_knowledge_point_count"] == 2
    assert report["assessable_knowledge_point_count"] == 0
