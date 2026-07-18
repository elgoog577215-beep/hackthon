import asyncio

from practice_analysis import (
    PracticeAnalysisService,
    _normalize_answer_diagnosis,
    build_assessment_intent,
    normalize_question_analysis,
)
from task_manager import _remap_assessment_revision_references


def _knowledge_base():
    return {
        "course_id": "course-1",
        "knowledge_points": [{
            "knowledge_id": "kp-1",
            "name": "向量方向",
            "statement": "向量由大小和方向共同确定。",
            "conditions": ["方向可比较"],
            "boundaries": ["不能只比较大小"],
        }],
        "skill_units": [{
            "skill_id": "skill-1",
            "name": "比较向量",
            "primary_knowledge_id": "kp-1",
            "observable_behavior": "分别比较大小和方向并说明判断依据",
        }],
        "misconceptions": [{
            "misconception_id": "mistake-1",
            "name": "只比较大小",
            "primary_knowledge_id": "kp-1",
            "observable_error_pattern": "把大小相同当作向量相同",
            "discrimination": "继续比较方向",
        }],
        "mastery_criteria": [{
            "criterion_id": "criterion-1",
            "name": "向量比较达标",
            "knowledge_ids": ["kp-1"],
            "observable_performance": "独立比较两个向量",
            "verification_method": "给出判断和依据",
        }],
    }


def _question():
    question = {
        "question_id": "q-1",
        "revision_id": "qr-1",
        "practice_level": "objective_practice",
        "course_knowledge_refs": ["kp-1"],
        "course_skill_refs": ["skill-1"],
        "course_misconception_refs": ["mistake-1"],
        "course_mastery_refs": ["criterion-1"],
        "answer_spec": {
            "criteria": ["分别比较大小和方向", "说明判断依据"],
        },
        "difficulty_contract": {"target_level": "beginner"},
    }
    question["assessment_intent"] = build_assessment_intent(
        question,
        _knowledge_base(),
    )
    question["assessment_intent_revision_id"] = question[
        "assessment_intent"
    ]["revision_id"]
    return question


def test_assessment_intent_is_compiled_from_course_local_truth():
    intent = _question()["assessment_intent"]

    assert [item["id"] for item in intent["target_knowledge"]] == ["kp-1"]
    assert [item["id"] for item in intent["target_skills"]] == ["skill-1"]
    assert [item["id"] for item in intent["target_misconceptions"]] == [
        "mistake-1"
    ]
    assert intent["observable_actions"] == [
        "分别比较大小和方向并说明判断依据"
    ]
    assert intent["answer_invariants"] == [
        "分别比较大小和方向",
        "说明判断依据",
    ]


def test_question_analysis_blocks_unknown_ids_and_accepts_real_hit():
    question = _question()
    free = {
        "task_goal": "比较两个向量是否相同",
        "required_actions": ["比较大小", "比较方向"],
        "answer_invariants": ["大小与方向都相同"],
    }
    passed = normalize_question_analysis(
        question,
        free,
        {
            "mapping": {
                "knowledge_ids": ["kp-1"],
                "skill_ids": ["skill-1"],
                "misconception_ids": ["mistake-1"],
            },
            "quality": {"passed": True, "issues": []},
            "reference_solution": {
                "approach": "分别检查两个维度",
                "key_steps": ["先比大小", "再比方向"],
                "self_check": "两个条件是否同时成立",
            },
        },
    )
    blocked = normalize_question_analysis(
        question,
        free,
        {
            "mapping": {
                "knowledge_ids": ["outside-course"],
                "skill_ids": [],
                "misconception_ids": [],
            },
            "quality": {"passed": True, "issues": []},
        },
    )

    assert passed["status"] == "passed"
    assert passed["mapping"]["library_fit"] == "HIT"
    assert blocked["status"] == "blocked"
    assert blocked["mapping"]["library_fit"] == "MISS"
    assert any(
        item["gate"] == "same_source_scope"
        for item in blocked["quality"]["issues"]
    )


def test_answer_diagnosis_preserves_real_issue_and_maps_only_allowed_ids():
    result = _normalize_answer_diagnosis(
        _question(),
        {
            "task_goal": "比较两个向量是否相同",
            "required_actions": ["比较大小", "比较方向"],
            "student_approach": "只比较了大小",
            "correct_parts": ["大小比较正确"],
            "behavior_gap": "没有检查方向",
            "issues": [{
                "issue_id": "I1",
                "title": "遗漏方向",
                "what_happened": "学生只比较大小，没有比较方向",
                "why_it_matters": "向量相同要求两个条件同时成立",
                "evidence": ["答案只写了大小相同"],
                "confidence": 0.9,
            }],
        },
        {
            "mapping": {
                "knowledge_ids": ["kp-1", "outside-course"],
                "skill_ids": ["skill-1"],
                "misconception_ids": ["mistake-1"],
            },
            "issue_mappings": [{
                "issue_id": "I1",
                "knowledge_ids": ["kp-1"],
                "skill_ids": ["skill-1"],
                "misconception_ids": ["mistake-1"],
            }],
            "student_feedback": {
                "summary": "大小判断正确，但还没有比较方向。",
                "next_action": "补充检查两个向量的方向是否一致。",
            },
        },
    )

    assert result["status"] == "completed"
    assert result["diagnosis"]["knowledge_ids"] == ["kp-1"]
    assert result["diagnosis"]["library_fit"] == "HIT"
    assert result["diagnosis"]["issues"][0]["misconception_ids"] == [
        "mistake-1"
    ]
    assert result["student_feedback"]["next_action"].startswith("补充检查")


def test_blocked_question_is_repaired_in_place_without_changing_intent():
    question = _question()
    question["prompt"] = "比较两个向量。"
    question["question_analysis"] = {
        "status": "blocked",
        "quality": {
            "issues": [{
                "gate": "answerability",
                "severity": "critical",
                "message": "题干没有说明交付形式和判断依据。",
            }],
        },
    }
    service = PracticeAnalysisService()
    service.client = object()

    async def fake_call_json(payload, *, system_prompt):
        assert payload["questions"][0]["assessment_intent"][
            "revision_id"
        ] == question["assessment_intent"]["revision_id"]
        assert "只重写题干" in system_prompt
        return {
            "repairs": [{
                "question_revision_id": "qr-1",
                "prompt": "分别比较两个向量的大小和方向，给出是否相同的结论并说明判断依据。",
                "repair_summary": "补齐可观察动作、交付形式和判断条件。",
            }],
        }

    service._call_json = fake_call_json
    repaired = asyncio.run(service.repair_blocked_questions([question]))[0]

    assert repaired["revision_id"].startswith("qrr_")
    assert repaired["question_repair"]["source_revision_id"] == "qr-1"
    assert repaired["assessment_intent"] == question["assessment_intent"]
    assert "question_analysis" not in repaired
    assert "大小和方向" in repaired["prompt"]


def test_question_repair_remaps_every_formal_revision_reference():
    assets = {
        "mastery_criteria": [{"assessment_bindings": ["qr-old"]}],
        "misconceptions": [{"assessment_bindings": ["qr-old", "qr-other"]}],
        "final_assessment": [{
            "question_revision_ids": ["qr-old", "qr-other"],
        }],
    }

    _remap_assessment_revision_references(
        assets,
        {"qr-old": "qrr-new"},
    )

    assert assets["mastery_criteria"][0]["assessment_bindings"] == ["qrr-new"]
    assert assets["misconceptions"][0]["assessment_bindings"] == [
        "qrr-new",
        "qr-other",
    ]
    assert assets["final_assessment"][0]["question_revision_ids"] == [
        "qrr-new",
        "qr-other",
    ]
