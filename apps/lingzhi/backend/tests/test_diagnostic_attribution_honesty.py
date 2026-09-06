"""没有诊断结论时不得编造归因（需求 C3）。

原实现在 `diagnostic_hypotheses` 末尾有一条兜底：只要该目标下挂着易错点，
且答案诊断没有给出结论，就取 `misconceptions[0]` 拼一条"可能混淆：…"的假设，
并把那条易错点的 ID 填进 `candidate_mistake_point_ids`。

这不是保守兜底，是伪造证据。被选中的易错点与学生这次的作答之间没有任何联系
——它只是列表里的第一个；若该目标挂了三个易错点，另外两个同样"可能"。下游会
拿这个 ID 去生成定向探针、写进补救单元，并在 evidence_for 里标成
`formal_failure`，也就是把"我们不知道"包装成"我们查到了"。

判据因此有两层：假设里不得出现凭顺序取来的易错点归因，且系统必须留下一条
"无法归因"的显式记录，让下一步去测而不是去假装已经知道。
"""

from __future__ import annotations

from copy import deepcopy

from diagnostic_workflows import diagnostic_hypotheses

# 不从 tests.test_diagnostic_remediation 借夹具：仓库根目录也有一个名为 `tests` 的
# 包且在 sys.path 中排在 backend 前面，backend/tests 里的模块无法按兄弟名导入。
_OBJECTIVE = {
    "objective_id": "lo1",
    "objective_revision_id": "lor1",
    "node_id": "n1",
    "learning_objective": "能够说明向量的大小与方向",
    "concept_ids": ["math.vector"],
    "skill_unit_ids": ["skill.vector.describe"],
    "mistake_point_ids": ["mistake.vector.direction"],
}


def _course() -> dict:
    question = {
        **_OBJECTIVE,
        "revision_id": "qr1",
        "question_type": "short_answer",
        "practice_level": "mastery_check",
        "answer_spec": {"type": "exact", "correct_answer": "大小和方向", "pass_score": 70},
    }
    return {
        "course_id": "c1",
        "current_course_version_id": "cv1",
        "nodes": [{"node_id": "n1", "node_name": "向量"}],
        "learning_assets": {"questions": [question], "misconceptions": []},
    }


def _course_with_misconceptions() -> dict:
    """同一目标下挂三个易错点：足以说明"取第一个"是任意的。"""
    course = deepcopy(_course())
    course["learning_assets"]["misconceptions"] = [
        {
            "mistake_point_id": f"mistake.vector.{name}",
            "revision_id": f"mpr{index}",
            "objective_revision_id": "lor1",
            "error_pattern": pattern,
        }
        for index, (name, pattern) in enumerate([
            ("direction", "只比较大小，忽略方向"),
            ("zero", "把零向量当成有方向的向量"),
            ("unit", "把单位向量当成任意同向向量"),
        ])
    ]
    return course


def _undiagnosed_attempt() -> dict:
    """作答失败，但答案诊断没有产出结论 —— 这正是兜底原来会介入的场景。"""
    return {
        "attempt_id": "a-undiagnosed",
        "result": {
            "passed": False,
            "rubric_results": [],
            "answer_diagnosis": {"status": "failed", "diagnosis": {}},
        },
    }


def _hypotheses(course: dict, attempt: dict) -> list[dict]:
    return diagnostic_hypotheses(course, course["learning_assets"]["questions"][0], attempt)


def test_no_diagnosis_does_not_borrow_the_first_misconception() -> None:
    """核心判据：没有结论时不得把列表里第一个易错点说成"可能混淆"。"""
    course = _course_with_misconceptions()

    hypotheses = _hypotheses(course, _undiagnosed_attempt())

    assert all("可能混淆" not in item["claim"] for item in hypotheses)
    assert all(
        "mistake.vector.direction" not in item["candidate_mistake_point_ids"]
        for item in hypotheses
    )


def test_no_diagnosis_attributes_to_no_single_misconception() -> None:
    """三个易错点同样"可能"，所以一个都不能被单独指认。"""
    course = _course_with_misconceptions()
    every_id = {
        item["mistake_point_id"] for item in course["learning_assets"]["misconceptions"]
    }

    hypotheses = _hypotheses(course, _undiagnosed_attempt())

    attributed = {
        point_id
        for item in hypotheses
        for point_id in item["candidate_mistake_point_ids"]
    }
    # 允许把整组列为待测范围，但不允许只挑出其中一个当结论。
    assert len(attributed & every_id) != 1


def test_unattributable_case_is_reported_rather_than_guessed() -> None:
    """必须留下显式的"无法归因"记录，否则"不知道"会被静默吞掉。"""
    course = _course_with_misconceptions()

    hypotheses = _hypotheses(course, _undiagnosed_attempt())

    assert hypotheses
    unattributed = [item for item in hypotheses if item.get("attribution") == "unattributed"]
    assert unattributed, "没有诊断结论时必须有假设如实标为无法归因"
    assert all(item["confidence_level"] == "low" for item in unattributed)
    assert all(
        item["evidence_for"][0]["kind"] == "unattributed_failure"
        for item in unattributed
    )
    # 待测范围与怀疑对象必须分开表达：范围可以有，结论不能有。
    assert all(item["candidate_mistake_point_ids"] == [] for item in unattributed)
    assert any(item["probe_scope_mistake_point_ids"] for item in unattributed)


def test_diagnosed_attribution_is_untouched_and_marked_diagnosed() -> None:
    """有结论时归因照旧生效 —— C3 只删兜底，不削弱真实诊断。"""
    course = _course_with_misconceptions()
    attempt = {
        "attempt_id": "a-diagnosed",
        "result": {
            "passed": False,
            "rubric_results": [],
            "answer_diagnosis": {
                "status": "completed",
                "diagnosis": {"issues": [{
                    "what_happened": "学生只比较大小，没有比较方向",
                    "confidence": 0.9,
                    "misconception_ids": ["mistake.vector.direction"],
                }]},
            },
        },
    }

    hypotheses = _hypotheses(course, attempt)

    assert hypotheses[0]["claim"] == "学生只比较大小，没有比较方向"
    assert hypotheses[0]["candidate_mistake_point_ids"] == ["mistake.vector.direction"]
    assert hypotheses[0]["attribution"] == "diagnosed"
    assert all(item.get("attribution") != "unattributed" for item in hypotheses)


def test_failed_rubric_criteria_still_drive_claims() -> None:
    """量规明确失败时仍按量规立论，这是有依据的归因，不受 C3 影响。"""
    course = _course_with_misconceptions()
    attempt = {
        "attempt_id": "a-rubric",
        "result": {
            "passed": False,
            "rubric_results": [{"criterion": "说明方向的判断依据", "met": False}],
            "answer_diagnosis": {"status": "failed", "diagnosis": {}},
        },
    }

    hypotheses = _hypotheses(course, attempt)

    assert hypotheses[0]["claim"] == "说明方向的判断依据"
    assert hypotheses[0]["attribution"] == "formal_failure"
