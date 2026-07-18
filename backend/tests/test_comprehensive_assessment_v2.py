from __future__ import annotations

from question_bank import build_question_bank


def _course() -> dict:
    return {
        "course_id": "course-final-v2",
        "course_name": "综合科学",
        "course_purpose": "systematic",
        "difficulty": "intermediate",
        "asset_preferences": {"final_assessment": True},
        "subject_pedagogy_profile": {
            "primary_mode": "natural_science",
            "user_locked": True,
        },
        "generation_request": {
            "course_purpose": "systematic",
            "asset_preferences": {"final_assessment": True},
            "web_question_enrichment": {"enabled": False},
        },
        "material_bindings": [],
        "evidence_catalog": [],
        "nodes": [{
            "node_id": "science-1",
            "node_level": 2,
            "node_name": "能量守恒",
            "node_content": (
                "系统吸收热量、对外做功时，内能变化由能量守恒确定。"
                "题目必须给出热量、功、符号约定和统一单位。"
            ),
            "learning_objective": "使用能量守恒分析系统状态变化",
            "key_points": ["热量", "功", "内能"],
            "assessment": ["列式计算并检查单位"],
            "grounding_contract": {"question_evidence_ids": []},
        }, {
            "node_id": "science-2",
            "node_level": 2,
            "node_name": "控制变量实验",
            "node_content": (
                "研究温度对反应速率的影响时，只改变温度，"
                "保持浓度和体积不变，并重复测量分析随机误差。"
            ),
            "learning_objective": "设计控制变量实验并分析误差",
            "key_points": ["自变量", "因变量", "控制变量", "误差"],
            "assessment": ["提交实验方案、记录表和误差分析"],
            "grounding_contract": {"question_evidence_ids": []},
        }],
    }


def test_comprehensive_assessment_uses_v2_private_solution_contracts():
    bundle = build_question_bank(_course())
    finals = [
        item
        for item in bundle["items"]
        if item.get("assessment_role")
        in {"coverage_task", "cross_chapter_transfer"}
    ]

    assert 3 <= len(finals) <= 8
    assert all(
        item["question_spec"]["schema_version"] == "question_spec_v2"
        for item in finals
    )
    assert all(
        item["solution_revision_id"] in bundle["solution_envelopes"]
        for item in finals
    )
    assert all("answer_spec" not in item for item in finals)
    assert all(item["review_required"] is True for item in finals)
    assert all(
        item["lifecycle_status"] == "needs_review"
        for item in finals
    )
    assert all(item["deliverable"] for item in finals)
    assert all(item["input_materials"] for item in finals)
    assert all(item["constraints"] for item in finals)
    assert all(item["result_checks"] for item in finals)


def test_cross_chapter_task_uses_integrated_archetype_and_all_nodes():
    bundle = build_question_bank(_course())
    cross = next(
        item
        for item in bundle["items"]
        if item.get("assessment_role") == "cross_chapter_transfer"
    )

    assert cross["archetype_id"] == "integrated_performance"
    assert set(cross["node_ids"]) == {"science-1", "science-2"}
    assert cross["question_spec"]["target"]["knowledge"]
    assert (
        cross["question_spec"]["risk_contract"][
            "requires_teacher_review"
        ]
        is True
    )
