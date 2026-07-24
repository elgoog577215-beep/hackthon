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
