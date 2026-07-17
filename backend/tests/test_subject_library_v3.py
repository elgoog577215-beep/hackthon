from copy import deepcopy

import pytest

from course_knowledge_map import compile_legacy_subject_course_map
from subject_library_repository import (
    SubjectLibraryConflict,
    SubjectLibraryRepository,
)
from subject_ontology import (
    build_subject_ontology,
    evaluate_subject_ontology_quality,
    resolve_subject_identity,
)


def _data_structures_course(course_id: str = "course-ds") -> dict:
    def section(node_id, name, topic, points, prerequisites=(), misconceptions=()):
        return {
            "node_id": node_id,
            "node_level": 2,
            "node_name": name,
            "learning_objective": f"掌握{name}",
            "knowledge_structure": [{
                "topic": topic,
                "description": f"{topic}的机制、边界和应用",
                "knowledge_points": [
                    {
                        "name": point,
                        "description": f"理解{point}的定义、机制与适用边界",
                        "capability": f"能够解释并应用{point}",
                        "aliases": [],
                        "prerequisite_names": [],
                    }
                    for point in points
                ],
            }],
            "key_points": list(points),
            "prerequisite_node_ids": list(prerequisites),
            "misconceptions": list(misconceptions),
            "content_blocks": [],
            "grounding_contract": {},
        }

    return {
        "course_id": course_id,
        "course_name": "高级数据结构：实现、分析与应用",
        "generation_request": {"subject": "高级数据结构"},
        "nodes": [
            section("L2-1-1", "堆的性质与应用", "堆", ["堆序性质", "完全二叉树表示"]),
            section(
                "L2-1-2", "堆操作实现", "堆操作", ["上浮操作", "下沉操作"],
                ["L2-1-1"], ["删除堆顶后忘记下沉恢复堆序"],
            ),
            section("L2-2-1", "平衡搜索树", "AVL树", ["平衡因子", "AVL旋转"], ["L2-1-1"]),
            section(
                "L2-3-1", "哈希表", "哈希表", ["哈希冲突", "开放寻址删除标记"],
                [], ["开放寻址删除时直接清空槽位导致查找链断裂"],
            ),
            section(
                "L2-4-1", "图遍历", "图算法", ["广度优先搜索", "深度优先搜索"],
                [], ["BFS出队后才标记访问导致重复入队"],
            ),
        ],
    }


def test_subject_identity_is_stable_and_shared_across_data_structure_courses():
    first = resolve_subject_identity(_data_structures_course("course-a"))
    second = resolve_subject_identity(_data_structures_course("course-b"))

    assert first["subject_id"] == "computer_science.data_structures"
    assert first["library_id"] == "cs.data_structures"
    assert first == second


@pytest.mark.parametrize(
    ("first_title", "second_title", "expected_subject"),
    [
        ("《微积分：理论与应用》", "微积分入门与工程实践", "math.calculus"),
        ("Python 高级编程：原理与实践", "Python 程序设计基础", "computer_science.python"),
        ("量子力学：从波函数到纠缠", "量子物理基础", "physics.quantum_mechanics"),
    ],
)
def test_subject_aliases_share_a_canonical_identity(first_title, second_title, expected_subject):
    first = resolve_subject_identity({"course_id": "a", "course_name": first_title, "nodes": []})
    second = resolve_subject_identity({"course_id": "b", "course_name": second_title, "nodes": []})

    assert first["subject_id"] == expected_subject
    assert second["subject_id"] == expected_subject
    assert first["library_id"] == second["library_id"]


def test_generated_ontology_is_not_a_course_outline_mirror():
    course = _data_structures_course()
    library = build_subject_ontology(course)
    course_map = compile_legacy_subject_course_map(deepcopy(course), library)
    report = evaluate_subject_ontology_quality(library, course, course_map)

    assert library["schema_version"] == "knowledge_library_v3"
    assert library["subject_id"] == "computer_science.data_structures"
    assert library["lifecycle_status"] == "candidate"
    assert {node["node_type"] for node in library["nodes"]} == {
        "subject", "domain", "topic", "concept", "knowledge_point",
    }
    assert max(node["depth"] for node in library["nodes"]) == 4
    assert len(library["relations"]) >= 5
    assert {item["relation_type"] for item in library["relations"]} >= {
        "prerequisite", "application", "confusable",
    }
    assert all(item["status"] == "candidate" for item in library["relations"])
    assert any(len(item["knowledge_ids"]) > 1 for item in library["skill_units"])
    assert any("AVL" in item["name"] or "高度" in item["description"] for item in library["mistake_points"])
    assert any("BFS" in item["name"] or "重复入队" in item["description"] for item in library["mistake_points"])
    assert course_map["schema_version"] == "course_knowledge_map_v2"
    assert course_map["coverage"]["mapped_ratio"] >= 0.85
    assert report["passed"] is True
    assert "course_outline_mirror" not in {item["code"] for item in report["issues"]}


def test_quality_gate_rejects_outline_mirror_and_repeated_templates():
    course = _data_structures_course()
    library = build_subject_ontology(course)
    concepts = [node for node in library["nodes"] if node["node_type"] == "concept"]
    library["relations"] = []
    for item in library["mistake_points"]:
        item.update({
            "description": "忽略适用条件",
            "misconception": "理解错误",
            "repair_strategy": "重新检查",
        })
    course_map = {
        "mappings": [
            {"section_id": course["nodes"][index]["node_id"], "anchor_knowledge_id": concept["knowledge_id"]}
            for index, concept in enumerate(concepts[: len(course["nodes"])])
        ],
        "coverage": {"mapped_ratio": 1.0},
    }

    report = evaluate_subject_ontology_quality(library, course, course_map)

    assert report["passed"] is False
    codes = {item["code"] for item in report["blocking_issues"]}
    assert "course_outline_mirror" in codes
    assert "missing_cross_concept_relations" in codes
    assert "repeated_mistake_templates" in codes


def test_repository_keeps_immutable_revisions_and_review_is_conflict_safe(tmp_path):
    repository = SubjectLibraryRepository(tmp_path)
    library = build_subject_ontology(_data_structures_course())

    stored = repository.save_revision(library)
    loaded = repository.load_revision(stored["library_id"], stored["revision_id"])
    accepted = repository.review_revision(
        stored["library_id"], stored["revision_id"], decision="accept", note="结构通过",
    )
    repeated = repository.review_revision(
        stored["library_id"], stored["revision_id"], decision="accept", note="重复请求",
    )

    assert loaded == stored
    assert accepted["lifecycle_status"] == "accepted"
    assert repeated["revision_id"] == accepted["revision_id"]
    assert repository.load_accepted("computer_science.data_structures")["revision_id"] == stored["revision_id"]
    with pytest.raises(SubjectLibraryConflict):
        repository.review_revision(
            stored["library_id"], stored["revision_id"], decision="reject", note="冲突决定",
        )


def test_bound_course_resolves_the_pinned_revision_not_a_dynamic_rebuild(tmp_path):
    repository = SubjectLibraryRepository(tmp_path)
    course = _data_structures_course()
    first = repository.save_revision(build_subject_ontology(course))
    changed = deepcopy(course)
    changed["nodes"][0]["knowledge_structure"][0]["knowledge_points"].append({
        "name": "堆构建",
        "description": "线性时间建堆",
        "capability": "实现自底向上建堆",
    })
    second = repository.save_revision(build_subject_ontology(changed, supersedes_revision_id=first["revision_id"]))
    course["knowledge_library_binding"] = repository.binding_for(first)

    resolved = repository.resolve_for_course(course)

    assert first["revision_id"] != second["revision_id"]
    assert resolved["revision_id"] == first["revision_id"]
    assert all(node["name"] != "堆构建" for node in resolved["nodes"])
