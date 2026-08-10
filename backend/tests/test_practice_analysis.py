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


def test_single_choice_diagnosis_receives_only_selected_option_evidence():
    question = _question()
    question.update({
        "prompt": "下列哪个判断同时比较了向量的大小和方向？",
        "question_type": "single_choice",
        "options": [
            {"option_id": "A", "text": "只比较大小"},
            {"option_id": "B", "text": "分别比较大小和方向"},
            {"option_id": "C", "text": "只比较方向"},
            {"option_id": "D", "text": "不比较任何属性"},
        ],
        "question_analysis": {
            "status": "passed",
            "question_understanding": {
                "task_goal": "选择完整的向量比较判断",
            },
        },
    })
    service = PracticeAnalysisService()
    service.client = object()
    calls = []

    async def fake_call_json(payload, *, system_prompt):
        calls.append((payload, system_prompt))
        if len(calls) == 1:
            assert payload["student_answer"] == {
                "selected_option_id": "A",
                "selected_option_text": "只比较大小",
                "evidence_scope": "selected_option_only",
            }
            assert payload["question"]["options"] == question["options"]
            assert "不得声称其使用了某个计算步骤" in system_prompt
            return {
                "task_goal": "选择完整的向量比较判断",
                "required_actions": ["比较所选命题与两个必要条件"],
                "student_approach": "学习者选择了只比较大小的命题",
                "correct_parts": ["识别到大小是比较条件之一"],
                "behavior_gap": "所选命题遗漏方向条件",
                "issues": [],
                "uncertainty": "未提供推理过程，无法判断选择原因",
            }
        return {
            "mapping": {
                "knowledge_ids": ["kp-1"],
                "skill_ids": ["skill-1"],
                "misconception_ids": ["mistake-1"],
            },
            "issue_mappings": [],
            "student_feedback": {
                "summary": "所选命题遗漏方向条件。",
                "next_action": "逐项检查命题是否同时覆盖大小和方向。",
            },
        }

    service._call_json = fake_call_json
    result = asyncio.run(service.diagnose_answer(
        question,
        {"submitted_answer_payload": {"selected_option_id": "A"}},
    ))

    assert result["status"] == "completed"
    assert result["student_response"]["approach"] == (
        "学习者选择了只比较大小的命题"
    )
    assert len(calls) == 2


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


# --- J2: 诊断只用可见证据（常驻回归） ----------------------------------------
#
# 现有 prompt 已经守住"不得补写学生没有表达的推理"这条诚实性底线，本节把它
# 钉成常驻回归，防止后续被改坏。覆盖三种可见证据不足的形态：
#   - 空白答案：什么都没写；
#   - 半截答案：只做了一半就停笔；
#   - 单选：只有"选了哪个选项"这一条证据（已有一条测试，这里补 prompt 约束）。


def _short_answer_question():
    question = _question()
    question.update({
        "prompt": "说明两个向量相同需要满足哪些条件，并给出判断依据。",
        "question_type": "short_answer",
        "question_analysis": {
            "status": "passed",
            "question_understanding": {"task_goal": "说明向量相同的条件"},
        },
    })
    return question


def _capture_diagnosis(question, answer_payload, free_result):
    """跑一次 diagnose_answer，返回 (传给模型的 payload 列表, 归一化结果)。"""
    service = PracticeAnalysisService()
    service.client = object()
    calls = []

    async def fake_call_json(payload, *, system_prompt):
        calls.append((payload, system_prompt))
        if len(calls) == 1:
            return free_result
        return {
            "mapping": {
                "knowledge_ids": ["kp-1"],
                "skill_ids": [],
                "misconception_ids": [],
            },
            "issue_mappings": [],
            "student_feedback": {
                "summary": "目前还看不到可评阅的作答证据。",
                "next_action": "先写下你判断两个向量相同时用到的第一个条件。",
            },
        }

    service._call_json = fake_call_json
    result = asyncio.run(service.diagnose_answer(
        question,
        {"submitted_answer_payload": answer_payload},
    ))
    return calls, result


def test_blank_answer_diagnosis_carries_no_invented_reasoning():
    """空白答案：模型只拿到空 payload，禁止补写推理的约束必须在 prompt 里。"""
    question = _short_answer_question()
    free = {
        "task_goal": "说明向量相同的条件",
        "required_actions": ["列出条件", "给出判断依据"],
        "student_approach": "",
        "correct_parts": [],
        "behavior_gap": "没有提交任何可评阅内容",
        "issues": [],
        "uncertainty": "答案为空，无法判断学习者的思路",
    }
    calls, result = _capture_diagnosis(question, {"text": ""}, free)

    payload, system_prompt = calls[0]
    # 送进模型的就是学生真实写下的东西——空的。
    assert payload["student_answer"] == {"text": ""}
    # 这条禁令必须常驻在 prompt 里。
    assert "不得补写学生没有表达的推理" in system_prompt

    # 归一化后不得凭空出现"学生的思路"或"做对的部分"。
    assert result["status"] == "completed"
    assert result["student_response"]["approach"] == ""
    assert result["student_response"]["correct_parts"] == []
    # 证据不足必须落在 uncertainty 上，而不是被写成结论。
    assert result["diagnosis"]["uncertainty"] == "答案为空，无法判断学习者的思路"
    assert result["diagnosis"]["issues"] == []


def test_half_finished_answer_diagnosis_keeps_unwritten_steps_uncertain():
    """半截答案：只认学生写下来的那一半，没写的那一半只能进 uncertainty。"""
    question = _short_answer_question()
    half = "两个向量相同，首先大小要相等，"
    free = {
        "task_goal": "说明向量相同的条件",
        "required_actions": ["列出条件", "给出判断依据"],
        "student_approach": "写到大小相等就停笔了",
        "correct_parts": ["识别出大小是必要条件之一"],
        "behavior_gap": "没有写出方向条件，也没有给出判断依据",
        "issues": [{
            "issue_id": "I1",
            "title": "条件不完整",
            "what_happened": "只写了大小相等，句子未写完",
            "why_it_matters": "缺少方向条件就无法判定两个向量相同",
            "evidence": ["答案止于“首先大小要相等，”"],
            "confidence": 0.8,
        }],
        "uncertainty": "学生是否知道方向条件无法从这半句判断",
    }
    calls, result = _capture_diagnosis(question, {"text": half}, free)

    payload, system_prompt = calls[0]
    assert payload["student_answer"] == {"text": half}
    assert "不得补写学生没有表达的推理" in system_prompt

    # 只保留写下来的部分，不得替学生"补完"方向条件。
    assert result["student_response"]["correct_parts"] == [
        "识别出大小是必要条件之一"
    ]
    issue = result["diagnosis"]["issues"][0]
    # 每条问题都必须带可见证据。
    assert issue["evidence"] == ["答案止于“首先大小要相等，”"]
    # 没写出来的部分只能是不确定，不能变成"学生不知道方向条件"这种断言。
    assert result["diagnosis"]["uncertainty"] == (
        "学生是否知道方向条件无法从这半句判断"
    )


def test_single_choice_prompt_forbids_inferring_unshown_reasoning():
    """单选：prompt 必须常驻"只能描述选了哪一种判断"的降级约束。"""
    from practice_analysis import _ANSWER_FREE_SYSTEM_PROMPT

    assert "不得补写学生没有表达的推理" in _ANSWER_FREE_SYSTEM_PROMPT
    assert "single_choice" in _ANSWER_FREE_SYSTEM_PROMPT
    assert "只能描述" in _ANSWER_FREE_SYSTEM_PROMPT
    assert "不得声称其使用了某个计算步骤" in _ANSWER_FREE_SYSTEM_PROMPT
    assert "必须写入 uncertainty" in _ANSWER_FREE_SYSTEM_PROMPT


def test_mapping_prompt_forbids_inventing_ids_to_fill_the_slot():
    """同源映射：不得为了填 ID 强行套库，ID 只能来自 assessment_intent。"""
    from practice_analysis import _ANSWER_MAPPING_SYSTEM_PROMPT

    assert "不得为了填 ID 强行套库" in _ANSWER_MAPPING_SYSTEM_PROMPT
    assert "ID 只能来自 assessment_intent" in _ANSWER_MAPPING_SYSTEM_PROMPT
