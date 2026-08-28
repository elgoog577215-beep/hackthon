"""教案批次读得到证据：知识库这一环不再凭模型常识写。

诊断结论：`course_knowledge_base.compile_course_knowledge_base` 没有 LLM 调用，
知识点字段全部取自教案批次产出的 `knowledge_structure`。而批次 prompt 此前
**完全没有证据段**（六个数据段里没有任何资料原文），于是「资料/联网 → 知识库」
这一环是断的。这组用例钉住修复后的行为。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from course_generation.adaptive import compact_planning_context  # noqa: E402
from course_generation.prompts import get_course_prompt_composer  # noqa: E402

EVIDENCE_MARK = "可依据的资料证据"


def _hints(count: int = 4) -> list[dict[str, str]]:
    return [
        {
            "evidence_id": f"ev{index}",
            "kind": "definition",
            "summary": f"证据{index}：导数刻画函数在一点处的瞬时变化率。" * 6,
        }
        for index in range(count)
    ]


def _sections(with_evidence: bool = True) -> list[dict]:
    section = {
        "node_id": "L2-1-1",
        "section_number": "1.1",
        "title": "导数的定义",
        "learning_objective": "掌握导数定义",
        "scope_boundary": "不含积分",
    }
    if with_evidence:
        section["evidence_hints"] = _hints()
    return [section]


def _prompt(sections: list[dict], detail_level: str = "full") -> str:
    return get_course_prompt_composer().build_teaching_plan_batch_v3_prompt(
        course_title="微积分",
        positioning="大一基础课",
        batch_spec={"batch_id": "B1", "expected_node_ids": ["L2-1-1"]},
        batch_sections=sections,
        knowledge_registry=[{
            "knowledge_key": "K001",
            "name": "导数",
            "statement": "瞬时变化率",
            "owner_node_id": "L2-1-1",
        }],
        section_identities=[{
            "node_id": "L2-1-1",
            "owned_knowledge_keys": ["K001"],
        }],
        module_catalog=[],
        skeleton_revision_id="rev-1",
        detail_level=detail_level,
    )


def _evidence_block(prompt: str) -> str:
    """只取证据段本身。

    注意：`evidence_hints` 也会随 `batch_sections` 的 JSON 一起出现在
    prompt 里，所以断言"整篇 prompt 含 ev0"是**测不出**证据段有没有接上的
    ——必须只在证据段范围内断言。第一版用例就栽在这里：把证据段整段删掉
    仍然全绿。
    """
    assert EVIDENCE_MARK in prompt
    start = prompt.index(EVIDENCE_MARK)
    end = prompt.index("## 当前批次知识与直接依赖闭包", start)
    return prompt[start:end]


def test_batch_prompt_now_carries_evidence():
    """核心回归：批次 prompt 必须出现**独立的**证据段并含证据内容。"""
    block = _evidence_block(_prompt(_sections()))
    assert "ev0" in block
    assert "瞬时变化率" in block


def test_evidence_survives_every_detail_level():
    """minimal 档原本把证据整个丢弃——降级不该让链路悄悄退化成无依据生成。"""
    for level in ("full", "compact", "minimal"):
        block = _evidence_block(_prompt(_sections(), detail_level=level))
        assert "ev0" in block, level


def test_prompt_instructs_model_to_use_evidence():
    """证据只放进 prompt 而不下指令，等于没接：约束里必须点名。"""
    prompt = _prompt(_sections())
    assert "必须优先依据这些证据" in prompt
    # 同时要守住"不得编造"，避免模型把通识包装成资料结论
    assert "不得把通识伪装成资料结论" in prompt


def test_no_evidence_section_when_course_has_none():
    """无资料的课程不应凭空多出证据段，也不该谎称有依据。"""
    prompt = _prompt(_sections(with_evidence=False))
    assert "ev0" not in prompt
    assert _evidence_block(prompt).count("evidence_id") == 0


def test_evidence_budget_shrinks_with_detail_level():
    """预算收紧方向必须单调：full ≥ compact ≥ minimal。"""
    sizes = [
        len(_prompt(_sections(), detail_level=level))
        for level in ("full", "compact", "minimal")
    ]
    assert sizes[0] > sizes[1] > sizes[2], sizes


def test_minimal_detail_keeps_evidence_ids_in_planning_context():
    """compact_planning_context 在 minimal 档保底留下证据 ID 与短摘要。"""
    context = compact_planning_context(
        {"sections": _sections()},
        detail_level="minimal",
    )
    hints = context["sections"][0].get("evidence_hints")
    assert hints, "minimal 档不应把证据整个丢弃"
    assert hints[0]["evidence_id"] == "ev0"
    assert len(hints[0]["summary"]) <= 60


def test_evidence_growth_stays_within_input_budget():
    """加证据不能把教案批次 prompt 推爆——这是上一轮实测过的真实痛点。"""
    from course_generation.budget import (
        CoursePlanningBudget,
        estimate_json_tokens,
    )

    budget = CoursePlanningBudget.from_env()
    prompt = _prompt(_sections())
    assert estimate_json_tokens(prompt) < budget.max_input_tokens
