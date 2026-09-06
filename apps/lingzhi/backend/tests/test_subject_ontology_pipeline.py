from __future__ import annotations

from copy import deepcopy

from course_knowledge_map import compile_legacy_subject_course_map
from subject_ontology import (
    build_subject_ontology,
    build_subject_ontology_from_proposal,
    evaluate_subject_ontology_quality,
)


def _cpp_course(course_id: str = "cpp-course") -> dict:
    def section(node_id: str, name: str, points: list[str]) -> dict:
        return {
            "node_id": node_id,
            "node_level": 2,
            "node_name": name,
            "knowledge_structure": [{
                "topic": name,
                "description": f"{name}的课程说明",
                "knowledge_points": points,
            }],
            "key_points": points,
            "content_blocks": [],
        }

    return {
        "course_id": course_id,
        "course_name": "C++：从基础语法到系统设计",
        "nodes": [
            section("s1", "1.1 C++ 简介与历史发展", ["编译型语言", "C++ 标准演进"]),
            section("s2", "2.1 变量与类型系统", ["静态类型", "值类别"]),
            section("s3", "3.1 资源管理", ["对象生命周期", "RAII"]),
            section("s4", "4.1 类与对象", ["封装", "构造函数"]),
            section("s5", "5.1 继承与多态", ["虚函数", "动态绑定"]),
        ],
    }


def _cpp_proposal() -> dict:
    return {
        "domains": [
            {
                "name": "C++ 语言基础",
                "description": "类型、表达式与编译模型",
                "topics": [
                    {
                        "name": "类型与表达式",
                        "concepts": [
                            {
                                "name": "静态类型系统",
                                "description": "编译期确定表达式类型与可用操作",
                                "knowledge_points": [
                                    {"name": "静态类型", "description": "变量和表达式具有编译期类型"},
                                    {"name": "值类别", "description": "左值、纯右值与将亡值"},
                                ],
                            },
                        ],
                    },
                    {
                        "name": "编译与标准",
                        "concepts": [
                            {
                                "name": "C++ 编译模型",
                                "description": "源代码经过预处理、编译和链接形成程序",
                                "knowledge_points": [
                                    {"name": "编译型语言", "description": "源代码需要编译和链接"},
                                    {"name": "C++ 标准演进", "description": "标准版本持续扩展语言能力"},
                                ],
                            },
                        ],
                    },
                ],
            },
            {
                "name": "C++ 对象与资源模型",
                "description": "对象生命周期、资源所有权和运行时多态",
                "topics": [
                    {
                        "name": "对象生命周期与资源",
                        "concepts": [
                            {
                                "name": "RAII 资源管理",
                                "description": "资源生命周期绑定对象生命周期",
                                "knowledge_points": [
                                    {"name": "对象生命周期", "description": "构造开始、析构结束"},
                                    {"name": "RAII", "description": "构造获取资源，析构释放资源"},
                                    {"name": "构造函数", "description": "建立对象不变量"},
                                ],
                            },
                        ],
                    },
                    {
                        "name": "面向对象机制",
                        "concepts": [
                            {
                                "name": "封装与运行时多态",
                                "description": "通过接口隐藏实现并在运行时分派",
                                "knowledge_points": [
                                    {"name": "封装", "description": "限制表示并维护不变量"},
                                    {"name": "虚函数", "description": "通过虚表进行动态分派"},
                                    {"name": "动态绑定", "description": "运行时选择最终覆写函数"},
                                ],
                            },
                        ],
                    },
                ],
            },
        ],
        "relations": [
            {"source_name": "静态类型", "target_name": "值类别", "relation_type": "prerequisite", "reason": "值类别规则依赖表达式类型"},
            {"source_name": "对象生命周期", "target_name": "RAII", "relation_type": "prerequisite", "reason": "RAII以对象生命周期为边界"},
            {"source_name": "构造函数", "target_name": "RAII", "relation_type": "application", "reason": "构造函数负责获取资源"},
            {"source_name": "封装", "target_name": "虚函数", "relation_type": "related", "reason": "接口封装是多态调用的基础"},
            {"source_name": "虚函数", "target_name": "动态绑定", "relation_type": "derives", "reason": "虚函数机制产生动态绑定"},
        ],
        "skills": [
            {"name": "解释表达式类型和值类别", "knowledge_names": ["静态类型", "值类别"], "description": "根据表达式形式判断类型和值类别"},
            {"name": "设计异常安全的资源类型", "knowledge_names": ["对象生命周期", "RAII", "构造函数"], "description": "用对象边界管理资源"},
            {"name": "实现可替换的多态接口", "knowledge_names": ["封装", "虚函数", "动态绑定"], "description": "设计接口并验证动态分派"},
        ],
        "mistakes": [
            {"name": "返回局部对象引用", "skill_name": "设计异常安全的资源类型", "knowledge_names": ["对象生命周期", "RAII"], "description": "函数返回后引用指向已销毁对象", "misconception": "认为引用会延长局部对象生命周期", "trigger": "从工厂函数返回对象时", "symptom": "出现悬空引用或未定义行为", "repair_strategy": "按值返回或明确所有权"},
            {"name": "基类析构非虚", "skill_name": "实现可替换的多态接口", "knowledge_names": ["虚函数", "动态绑定"], "description": "通过基类指针删除派生对象时析构不完整", "misconception": "认为任意虚函数都会让析构自动动态分派", "trigger": "通过基类指针释放派生对象时", "symptom": "派生资源泄漏", "repair_strategy": "把多态基类析构声明为virtual"},
        ],
        "improvements": [
            {"name": "用所有权表审查资源类型", "skill_name": "设计异常安全的资源类型", "knowledge_names": ["对象生命周期", "RAII"], "related_mistake_names": ["返回局部对象引用"], "description": "标注每个资源的拥有者和释放点", "practice_strategy": "重构一个手工new/delete类型", "student_benefit": "降低泄漏和悬空引用"},
            {"name": "验证多态析构链", "skill_name": "实现可替换的多态接口", "knowledge_names": ["虚函数", "动态绑定"], "related_mistake_names": ["基类析构非虚"], "description": "记录基类与派生类析构顺序", "practice_strategy": "编写通过基类指针delete的测试", "student_benefit": "可靠维护多态资源"},
        ],
    }


def test_full_model_proposal_builds_subject_ontology_instead_of_outline_mirror():
    course = _cpp_course()
    library = build_subject_ontology_from_proposal(course, _cpp_proposal())
    course_map = compile_legacy_subject_course_map(deepcopy(course), library)
    report = evaluate_subject_ontology_quality(library, course, course_map)

    assert {node["node_type"] for node in library["nodes"]} == {
        "subject", "domain", "topic", "concept", "knowledge_point",
    }
    assert {node["name"] for node in library["nodes"] if node["node_type"] == "domain"} == {
        "C++ 语言基础", "C++ 对象与资源模型",
    }
    assert not any(node["name"].startswith("1.1 ") for node in library["nodes"] if node["node_type"] == "concept")
    assert len(library["relations"]) == 5
    assert all(item["status"] == "candidate" for item in library["relations"])
    assert all(1 <= len(item["knowledge_ids"]) <= 5 for item in library["skill_units"])
    assert any("基类析构" in item["name"] for item in library["mistake_points"])
    assert report["passed"] is True
    assert course_map["coverage"]["mapped_ratio"] >= 0.85


def test_full_model_proposal_assigns_stable_backend_ids():
    first = build_subject_ontology_from_proposal(_cpp_course("course-a"), _cpp_proposal())
    second = build_subject_ontology_from_proposal(_cpp_course("course-b"), _cpp_proposal())

    assert [item["knowledge_id"] for item in first["nodes"]] == [
        item["knowledge_id"] for item in second["nodes"]
    ]
    assert first["revision_id"] != second["revision_id"]


def test_quality_gate_detects_outline_mirror_even_when_relations_exist():
    course = _cpp_course()
    library = build_subject_ontology(course)
    point_ids = [node["knowledge_id"] for node in library["nodes"] if node["node_type"] == "knowledge_point"]
    library["relations"] = [{
        "relation_id": "relation.fake",
        "source_knowledge_id": point_ids[0],
        "target_knowledge_id": point_ids[1],
        "relation_type": "related",
        "reason": "用于证明关系不能掩盖章节镜像",
        "status": "candidate",
        "source_type": "model_inferred",
        "confidence": 0.5,
    }]
    course_map = compile_legacy_subject_course_map(deepcopy(course), library)

    report = evaluate_subject_ontology_quality(library, course, course_map)

    assert report["passed"] is False
    assert "course_outline_mirror" in {item["code"] for item in report["issues"]}


def test_quality_gate_detects_prerequisite_relation_cycles():
    course = _cpp_course()
    library = build_subject_ontology_from_proposal(course, _cpp_proposal())
    nodes = {node["name"]: node["knowledge_id"] for node in library["nodes"]}
    library["relations"].extend([
        {
            "relation_id": "relation.cycle-a",
            "source_knowledge_id": nodes["RAII"],
            "target_knowledge_id": nodes["对象生命周期"],
            "relation_type": "prerequisite",
            "reason": "反向边形成循环",
            "status": "candidate",
            "source_type": "model_inferred",
            "confidence": 0.5,
        },
    ])
    course_map = compile_legacy_subject_course_map(deepcopy(course), library)

    report = evaluate_subject_ontology_quality(library, course, course_map)

    assert report["passed"] is False
    assert "prerequisite_cycle" in {item["code"] for item in report["issues"]}


def test_quality_gate_detects_renamed_copies_of_the_same_mistake_template():
    course = _cpp_course()
    library = build_subject_ontology_from_proposal(course, _cpp_proposal())
    point_ids = [
        node["knowledge_id"] for node in library["nodes"] if node["node_type"] == "knowledge_point"
    ]
    skill_id = library["skill_units"][0]["skill_unit_id"]
    library["mistake_points"] = [
        {
            "mistake_point_id": f"mistake.copy.{index}",
            "skill_unit_id": skill_id,
            "name": f"错误 {index}",
            "description": f"处理知识点{index}时只记结论，没有检查定义、适用条件和边界情况",
            "misconception": f"认为知识点{index}可以在所有场景无条件使用",
            "trigger": f"应用知识点{index}时",
            "symptom": f"知识点{index}答案缺少条件说明和边界检查",
            "repair_strategy": f"回到知识点{index}定义，按条件、过程、结果三步检查",
            "primary_knowledge_id": point_ids[index],
            "knowledge_ids": [point_ids[index]],
        }
        for index in range(5)
    ]
    course_map = compile_legacy_subject_course_map(deepcopy(course), library)

    report = evaluate_subject_ontology_quality(library, course, course_map)

    assert "repeated_mistake_templates" in {item["code"] for item in report["issues"]}


def test_quality_gate_rejects_relations_without_governance_metadata():
    course = _cpp_course()
    library = build_subject_ontology_from_proposal(course, _cpp_proposal())
    library["relations"][0].update({"reason": "", "source_type": "", "confidence": None, "status": ""})
    course_map = compile_legacy_subject_course_map(deepcopy(course), library)

    report = evaluate_subject_ontology_quality(library, course, course_map)

    assert "invalid_relation_metadata" in {item["code"] for item in report["issues"]}


def test_material_source_is_not_accepted_without_course_materials():
    proposal = _cpp_proposal()
    proposal["domains"][0]["topics"][0]["concepts"][0]["knowledge_points"][0]["source_type"] = "material_source"

    library = build_subject_ontology_from_proposal(_cpp_course(), proposal)

    assert "material_source" not in library["generation_audit"]["sources"]
    assert all(node.get("source_type") != "material_source" for node in library["nodes"])


def test_model_course_mappings_become_formal_aliases_for_reworded_concepts():
    course = _cpp_course()
    proposal = _cpp_proposal()
    point = proposal["domains"][0]["topics"][1]["concepts"][0]["knowledge_points"][0]
    point["name"] = "编译执行与链接模型"
    proposal["course_mappings"] = [
        {
            "course_name": "编译型语言",
            "knowledge_name": "编译执行与链接模型",
            "reason": "课程局部表述对应学科规范表述",
            "confidence": 0.95,
        },
    ]

    library = build_subject_ontology_from_proposal(course, proposal)
    course_map = compile_legacy_subject_course_map(deepcopy(course), library)

    mapping = next(item for item in course_map["mappings"] if item["local_name"] == "编译型语言")
    assert mapping["match_status"] == "exact_alias"
    assert mapping["confidence"] == 0.98
