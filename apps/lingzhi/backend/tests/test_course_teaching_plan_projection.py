from course_generation.workflow import compile_course_teaching_plan_modules
from course_teaching_plan_projection import project_course_teaching_plan


def test_projects_overall_plan_and_binds_section_knowledge_ids():
    course = {
        "course_id": "course-1",
        "course_name": "一次函数",
        "target_audience": "初中二年级学生",
        "generation_request": {
            "target_audience": "已经学习平面直角坐标系的初中二年级学生",
        },
        "subject_pedagogy_profile": {
            "primary_mode": "conceptual",
            "secondary_mode": "worked_examples",
            "rationale": "先建立图像直觉，再进入代数表达。",
        },
        "course_plan": {
            "course_title": "一次函数",
            "positioning": "从变化率出发理解一次函数",
            "learning_objectives": [
                "理解斜率表示的变化关系",
                "能够根据图像判断变化快慢",
            ],
            "prerequisites": ["平面直角坐标系"],
            "chapters": [{
                "chapter_number": 1,
                "title": "变化率与图像",
                "learning_focus": "建立斜率的几何与情境直觉",
                "sections": [{"node_id": "section-1"}],
            }],
        },
        "course_teaching_plan": {
            "revision_id": "teaching-1",
            "sections": [{
                "node_id": "section-1",
                "key_points": ["一次函数斜率"],
                "reused_knowledge_names": [],
                "knowledge_relations": [],
                "teaching_modules": [{
                    "module_id": "core",
                    "teaching_purpose": "建立变化率直觉",
                    "knowledge_names": ["一次函数斜率"],
                }],
                "knowledge_structure": [{
                    "concept_group": "变化率",
                    "knowledge_points": [{
                        "name": "一次函数斜率",
                        "statement": "斜率表示横坐标每变化一个单位时纵坐标的变化量。",
                        "mastery_criteria": [{
                            "observable_performance": "根据两点独立求出斜率",
                            "verification_method": "出口题",
                        }],
                    }],
                }],
            }],
        },
        "course_knowledge_base": {
            "knowledge_points": [{
                "knowledge_id": "knowledge-slope",
                "name": "一次函数斜率",
                "aliases": ["斜率"],
            }],
        },
        "generation_stage_artifacts": {
            "course_teaching_plan": {
                "status": "completed",
                "section_count": 1,
                "knowledge_point_count": 1,
                "teaching_module_count": 1,
            },
        },
    }

    projection = project_course_teaching_plan(course)

    assert projection["overall"]["course_title"] == "一次函数"
    assert projection["overall"]["target_audience"].startswith("已经学习")
    assert projection["overall"]["chapters"][0]["learning_focus"] == "建立斜率的几何与情境直觉"
    assert projection["overall"]["assessment_methods"] == ["出口题"]
    assert projection["overall"]["knowledge_tags"] == [{
        "knowledge_id": "knowledge-slope",
        "name": "一次函数斜率",
        "section_count": 1,
    }]
    point = projection["sections"][0]["knowledge_structure"][0]["knowledge_points"][0]
    assert point["knowledge_id"] == "knowledge-slope"
    assert point["knowledge_status"] == "bound"


def test_uncompiled_knowledge_is_explicitly_marked_pending():
    projection = project_course_teaching_plan({
        "course_teaching_plan": {
            "sections": [{
                "node_id": "section-1",
                "knowledge_structure": [{
                    "concept_group": "变化率",
                    "knowledge_points": [{
                        "name": "一次函数斜率",
                        "statement": "斜率表示变化率。",
                    }],
                }],
                "key_points": ["一次函数斜率"],
                "reused_knowledge_names": [],
                "knowledge_relations": [],
                "teaching_modules": [],
            }],
        },
    })

    point = projection["sections"][0]["knowledge_structure"][0]["knowledge_points"][0]
    assert point["knowledge_id"] == ""
    assert point["knowledge_status"] == "awaiting_compilation"


def _plan_section(node_id, *, minutes=None, checks=()):
    section = {
        "node_id": node_id,
        "key_points": [f"{node_id} 知识"],
        "reused_knowledge_names": [],
        "knowledge_relations": [],
        "in_class_checks": list(checks),
        "teaching_modules": [
            {"module_id": "lesson_goal", "teaching_purpose": "说明任务"},
            {"module_id": "core_explanation", "teaching_purpose": "讲清内容"},
        ],
        "knowledge_structure": [{
            "concept_group": "核心机制",
            "knowledge_points": [{
                "name": f"{node_id} 知识",
                "statement": "说明。",
            }],
        }],
    }
    if minutes:
        section["planned_minutes"] = minutes
    return section


def _outline_section(node_id):
    return {
        "node_id": node_id,
        "title": f"{node_id} 标题",
        "learning_objective": f"{node_id} 目标",
        "module_plan": [
            {
                "module_id": "lesson_goal",
                "label": "本节任务",
                "block_role": "objective",
                "required": True,
            },
            {
                "module_id": "core_explanation",
                "label": "核心教学",
                "block_role": "concept",
                "required": True,
            },
        ],
    }


def test_projection_attaches_uniform_lesson_dossiers_and_course_consistency():
    """投影必须给每一节挂上同一套栏目，并给出全课颗粒度对照。

    这是 P1-3 的验收面：教师任取三节，栏目结构与颗粒度要能直接比。
    """
    course = {
        "course_plan": {
            "chapters": [{
                "chapter_number": 1,
                "title": "第一章",
                "sections": [_outline_section(f"section-{index}") for index in (1, 2, 3)],
            }],
        },
        "course_teaching_plan": {
            "sections": [
                _plan_section("section-1", minutes=45, checks=["出口题"]),
                _plan_section("section-2"),
                _plan_section("section-3"),
            ],
        },
    }

    projection = project_course_teaching_plan(course)

    dossiers = [section["dossier"] for section in projection["sections"]]
    assert [dossier["sequence"] for dossier in dossiers] == [1, 2, 3]
    assert dossiers[0]["title"] == "section-1 标题"
    assert dossiers[0]["chapter_title"] == "第一章"
    # 三节栏目键完全一致，这是“任取三节结构一致”的直接证据。
    keys = {tuple(item["key"] for item in dossier["rubrics"]) for dossier in dossiers}
    assert len(keys) == 1

    # 只有第 1 节声明了课时长度；其余两节用全课中位数兜底，时序不再一节有一节无。
    timelines = [
        next(item for item in dossier["rubrics"] if item["key"] == "timeline")
        for dossier in dossiers
    ]
    assert [item["minutes_basis"] for item in timelines] == [
        "section_planned", "course_median", "course_median",
    ]
    assert all(item["total_minutes"] == 45 for item in timelines)
    assert all(item["continuous"] for item in timelines)
    # 环节名来自目录冻结的 module_plan，不是模型标题。
    assert [entry["label"] for entry in timelines[1]["entries"]] == ["本节任务", "核心教学"]

    consistency = projection["dossier_consistency"]
    assert consistency["uniform_rubric_structure"] is True
    assert consistency["section_count"] == 3
    assert consistency["outlier_node_ids"] == []
    coverage = {item["key"]: item["filled_sections"] for item in consistency["rubric_coverage"]}
    assert coverage["timeline"] == 3
    assert coverage["homework"] == 0


def test_projection_without_teaching_plan_still_reports_empty_consistency():
    projection = project_course_teaching_plan({})

    assert projection["sections"] == []
    assert projection["dossier_consistency"]["section_count"] == 0
    assert projection["dossier_consistency"]["uniform_rubric_structure"] is True


def test_compiled_teaching_plan_preserves_concise_outline_objective():
    outline = _outline_section("section-1")
    generated = _plan_section("section-1")
    generated["knowledge_structure"][0]["knowledge_points"][0][
        "capability_points"
    ] = [
        {"observable_behavior": f"原子能力 {index}"}
        for index in range(1, 9)
    ]

    compiled = compile_course_teaching_plan_modules(
        {
            "schema_version": "course_teaching_plan_v3",
            "sections": [generated],
        },
        sections=[outline],
    )

    assert compiled["sections"][0]["learning_objective"] == "section-1 目标"
