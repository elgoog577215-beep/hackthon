"""N1：学科事实检查从通用质量门里抽出来，改成注册表。

检查本身没错（抓的是真实事实性错误），问题是通用引擎里的单课程特例会诱导
后来者继续往里加 if。这里锁住：能力不变、通用门不再认识任何具体学科。
"""
from __future__ import annotations

from assessment_subject_facts import (
    SUBJECT_FACT_ISSUE_CODES,
    check_unity_lifecycle_facts,
    subject_fact_issues,
)


def test_unity_rate_error_is_still_caught() -> None:
    issues = check_unity_lifecycle_facts(
        "在 Unity 中使用 Rigidbody.MovePosition 移动角色。",
        "FixedUpdate 默认每秒 60 次，因此每帧位移为 speed/60。",
    )
    codes = [issue["code"] for issue in issues]
    assert "UNITY_FIXEDUPDATE_RATE_INVALID" in codes
    assert all(issue["severity"] == "critical" for issue in issues)


def test_unity_speed_step_error_is_still_caught() -> None:
    question = (
        "在 Unity 中补全下面的移动逻辑：\n"
        "```csharp\n"
        "public float speed;\n"
        "void FixedUpdate() {\n"
        "    rb.MovePosition(rb.position + dir * speed);\n"
        "}\n"
        "```\n"
    )
    issues = check_unity_lifecycle_facts(question, "直接把 speed 作为位移即可。")
    assert "UNITY_SPEED_STEP_MISMATCH" in [issue["code"] for issue in issues]


def test_correct_unity_answer_is_not_flagged() -> None:
    question = (
        "在 Unity 中补全移动逻辑：\n"
        "```csharp\n"
        "public float speed;\n"
        "void FixedUpdate() {\n"
        "    rb.MovePosition(rb.position + dir * speed * Time.fixedDeltaTime);\n"
        "}\n"
        "```\n"
    )
    solution = (
        "默认 fixedDeltaTime 为 0.02 秒（50 Hz），"
        "需用 Time.fixedDeltaTime 把每秒速度换算成单步位移。"
    )
    assert check_unity_lifecycle_facts(question, solution) == []


def test_non_unity_questions_skip_the_checker_entirely() -> None:
    """一个学科的正则不能套到别的学科题面上。"""
    assert check_unity_lifecycle_facts(
        "热力学第一定律：封闭系统吸热 20 kJ、对外做功 8 kJ。",
        "ΔU = Q - W = 12 kJ。系统默认每秒 60 次采样。",
    ) == []


def test_registry_runs_registered_checkers() -> None:
    issues = subject_fact_issues(
        "Unity 中的 Rigidbody 移动",
        "FixedUpdate 默认每秒 60 次。",
    )
    assert "UNITY_FIXEDUPDATE_RATE_INVALID" in [i["code"] for i in issues]


def test_a_broken_checker_does_not_block_all_question_generation() -> None:
    """一条学科正则写错，不该升级成"所有题都过不了门"。"""
    def exploding(question_text, solution_text):
        raise RuntimeError("这条检查写坏了")

    def working(question_text, solution_text):
        return [{"code": "OK_CODE", "severity": "critical", "message": "", "evidence": {}}]

    issues = subject_fact_issues("q", "s", checkers=(exploding, working))
    assert [issue["code"] for issue in issues] == ["OK_CODE"]


def test_generic_quality_gate_no_longer_names_any_subject() -> None:
    """N1 的核心：通用引擎里不该再出现具体学科的标识符。"""
    from pathlib import Path

    source = Path("backend/assessment_quality.py").read_text(encoding="utf-8")
    assert "UNITY" not in source
    assert "MovePosition" not in source
    assert "fixedDeltaTime" not in source


def test_subject_fact_codes_are_still_treated_as_repairable() -> None:
    """抽出去之后，这些码仍要被通用门当作可修复问题。"""
    from assessment_quality import _REPAIRABLE_HARD_CODES

    assert SUBJECT_FACT_ISSUE_CODES
    assert SUBJECT_FACT_ISSUE_CODES <= _REPAIRABLE_HARD_CODES
