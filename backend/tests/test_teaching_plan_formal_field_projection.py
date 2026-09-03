from course_generation.workflow import normalize_course_teaching_plan
from course_teaching_plan_v3 import assemble_course_teaching_plan_v3


def _section():
    return {
        "node_id": "L2-1-1",
        "class_summary": ["总结高斯定理的条件与应用边界。"],
        "extension_learning": ["比较积分形式与微分形式。"],
        "homework_submission": "下次课前提交到课程平台。",
        "homework_evaluation": "结论正确，推导完整，边界说明清楚。",
        "next_lesson_connection": "为下一讲的边值问题建立前置基础。",
        "teaching_modules": [{
            "module_id": "math_formalization",
            "label": "高斯定理形式化推导",
            "teaching_purpose": "推导积分形式。",
            "handout_ppt_mapping": "讲义第二节与 PPT 第 4—6 页。",
        }],
    }


def test_normalization_preserves_formal_lesson_fields_and_block_label():
    normalized = normalize_course_teaching_plan({
        "schema_version": "course_teaching_plan_v3",
        "sections": [_section()],
    })
    section = normalized["sections"][0]
    assert section["class_summary"]
    assert section["homework_evaluation"].startswith("结论正确")
    assert section["teaching_modules"][0]["label"] == "高斯定理形式化推导"


def test_v3_assembly_preserves_formal_lesson_fields_and_block_label():
    assembled = assemble_course_teaching_plan_v3(
        skeleton={
            "revision_id": "skeleton-1",
            "knowledge_registry": [],
            "sections": [{
                "node_id": "L2-1-1",
                "owned_knowledge_keys": [],
                "reused_knowledge_keys": [],
            }],
        },
        batches=[{"sections": [_section()]}],
        outline_revision_id="outline-1",
    )
    section = assembled["sections"][0]
    assert section["class_summary"]
    assert section["next_lesson_connection"].startswith("为下一讲")
    assert section["teaching_modules"][0]["label"] == "高斯定理形式化推导"
