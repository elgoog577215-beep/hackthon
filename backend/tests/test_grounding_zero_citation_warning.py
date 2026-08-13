"""零引用告警：配了资料却一条没用，必须看得见。

诊断实测：`required_evidence_ids` 只有 `usage_policy=must_use` 且词面重叠
时才填，通常为空，于是 required=0、missing=0，`evaluate_node_grounding`
**空转判过**——一个有 24 条可用来源、正文一条都没引的节点照样 passed=True。

本轮口径（用户明确要求）：**先告警不阻断**。存量课程大量是零引用，
直接阻断会把它们全判失败。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_quality import evaluate_node_grounding  # noqa: E402

CODE = "grounding:no_source_used"


def _codes(result: dict) -> list[str]:
    return [str(item.get("code")) for item in result["issues"]]


def test_sources_available_but_never_cited_raises_warning():
    """核心回归：这正是改动前完全测不出来的情形。"""
    result = evaluate_node_grounding({
        "node_id": "L2-1-1",
        "available_source_ids": ["s1", "s2"],
        "grounding_contract": {},
    })
    assert CODE in _codes(result)
    severity = next(
        item["severity"] for item in result["issues"]
        if item["code"] == CODE
    )
    assert severity == "warning"
    assert result["available_source_count"] == 2
    assert result["citation_count"] == 0


def test_warning_does_not_block_publication():
    """告警不得阻断：passed 必须仍为 True。"""
    result = evaluate_node_grounding({
        "available_source_ids": ["s1"],
        "grounding_contract": {},
    })
    assert result["passed"] is True


def test_no_warning_when_sources_are_cited():
    result = evaluate_node_grounding({
        "available_source_ids": ["s1"],
        "citation_map": {"S1": "s1"},
        "grounding_contract": {},
    })
    assert CODE not in _codes(result)


def test_no_warning_when_course_has_no_sources():
    """没有资料的课程不该被责怪没引用资料。"""
    result = evaluate_node_grounding({"grounding_contract": {}})
    assert _codes(result) == []
    assert result["passed"] is True


def test_evidence_annotations_also_count_as_usage():
    """资料侧走 [[evidence:]] 通道，同样算"用了来源"。"""
    result = evaluate_node_grounding({
        "grounding_contract": {"optional_evidence_ids": ["e1"]},
        "grounding_annotations": [{"evidence_id": "e1"}],
    })
    assert CODE not in _codes(result)


def test_existing_blocking_issues_still_block():
    """新增告警不得削弱既有 major/critical 判定。"""
    missing_required = evaluate_node_grounding({
        "available_source_ids": ["s1"],
        "grounding_contract": {"required_evidence_ids": ["e1"]},
    })
    assert missing_required["passed"] is False
    assert "grounding:missing_required_evidence" in _codes(missing_required)

    invalid = evaluate_node_grounding({
        "grounding_contract": {"optional_evidence_ids": ["e1"]},
        "grounding_annotations": [{"evidence_id": "e_unauthorized"}],
    })
    assert invalid["passed"] is False
    assert "grounding:invalid_reference" in _codes(invalid)


def test_invalid_citations_suppress_the_zero_use_warning():
    """已经报了"引用非法"就不必再叠一条"没引用"，避免重复噪音。"""
    result = evaluate_node_grounding({
        "available_source_ids": ["s1"],
        "grounding_contract": {"optional_evidence_ids": ["e1"]},
        "grounding_annotations": [{"evidence_id": "bad"}],
    })
    assert CODE not in _codes(result)
