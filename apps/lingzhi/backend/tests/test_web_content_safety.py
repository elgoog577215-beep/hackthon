"""P0 语义级内容安全：敏感主题标记层。

对应 `docs/研究/联网资料内容安全最小方案-2026-08-09.md` 第 1 层。
四条原则在用例里都有对应守卫：只标记不审查、不阻断生成、
不引外部依赖、不自动删改内容。
"""

from __future__ import annotations

import pytest

from web_content_safety import (
    SENSITIVE_TOPICS,
    assess_sensitivity,
    needs_teacher_review,
)
from web_material_search import candidate_from_source


# ------------------------------------------------------ 必须标记的样本


@pytest.mark.parametrize("title,excerpt,topic", [
    ("用药指南", "成人剂量为每日两次，注意不良反应。", "medical_advice"),
    ("Treatment protocol", "The recommended dosage is 5 mg/kg.", "medical_advice"),
    ("最新研究", "该结论尚有争议，有待验证。", "unsettled_science"),
    ("Study note", "This hypothesis remains controversial.", "unsettled_science"),
])
def test_sensitive_sources_are_flagged(title, excerpt, topic):
    result = assess_sensitivity(title, excerpt)
    assert result["level"] == "review_recommended"
    assert topic in result["topics"]
    assert result["matched_terms"], "必须回传命中词，教师要看到为什么被标"


def test_matched_terms_are_capped():
    """命中词只用于解释，不需要全量回传。"""
    excerpt = "剂量 处方 禁忌症 不良反应 副作用 诊断标准 适应症 用药 疗程"
    result = assess_sensitivity("用药", excerpt)
    assert 0 < len(result["matched_terms"]) <= 5


# ------------------------------------------------ 必须放行的样本（防误标）


@pytest.mark.parametrize("title,excerpt", [
    ("Eigenvalues and eigenvectors", "The eigenvalue problem Ax = lambda x."),
    ("特征值与特征向量", "特征值刻画线性变换的伸缩比例。"),
    ("Linear algebra notes", "Diagonalization requires n independent eigenvectors."),
    ("", ""),
])
def test_ordinary_teaching_material_is_not_flagged(title, excerpt):
    result = assess_sensitivity(title, excerpt)
    assert result["level"] == "none"
    assert result["topics"] == []


def test_english_terms_respect_word_boundary():
    """英文词做词边界匹配，避免"hypothesis"命中无关长词造成误标。"""
    assert assess_sensitivity("", "hypothesis") ["level"] == "review_recommended"
    # 不应因为词出现在别的单词内部而误标
    assert assess_sensitivity("", "prescriptionless philosophy")["level"] == "none"


# ------------------------------------------------------ 只降级，不拒绝


def _source(title: str, excerpt: str, **overrides):
    base = {
        "source_id": "s1",
        "url": "https://example.edu/a",
        "title": title,
        "excerpt": excerpt,
        "trust_tier": "tier_a",
        "accepted_for_generation": True,
    }
    base.update(overrides)
    return base


def test_sensitive_source_is_demoted_not_removed():
    """P0 核心：命中敏感主题的来源仍留在候选里，只是不再自动进链。"""
    candidate = candidate_from_source(_source("用药指南", "成人剂量为每日两次。"))

    assert candidate["accepted_for_generation"] is False
    assert candidate["sensitivity"]["level"] == "review_recommended"
    # 内容原样保留——不自动删改
    assert candidate["text"] == "成人剂量为每日两次。"
    assert candidate["title"] == "用药指南"
    # 仍然是一条完整候选，教师可以接受
    assert candidate["url"] == "https://example.edu/a"


def test_safe_source_keeps_auto_acceptance():
    candidate = candidate_from_source(
        _source("Eigenvalues", "The eigenvalue problem Ax = lambda x.")
    )
    assert candidate["accepted_for_generation"] is True
    assert candidate["sensitivity"]["level"] == "none"


def test_already_rejected_source_stays_rejected():
    """网关本就没准入的来源，不会因为"内容安全"反而被放行。"""
    candidate = candidate_from_source(
        _source("Eigenvalues", "safe", accepted_for_generation=False)
    )
    assert candidate["accepted_for_generation"] is False


def test_assessment_never_raises_on_malformed_input():
    """不阻断生成：任何输入都不得抛异常。"""
    for title, excerpt in [(None, None), ("", None), (123, 456)]:
        result = assess_sensitivity(title, excerpt)  # type: ignore[arg-type]
        assert result["level"] in {"none", "review_recommended"}


def test_needs_teacher_review_helper():
    assert needs_teacher_review({"level": "review_recommended"}) is True
    assert needs_teacher_review({"level": "none"}) is False
    assert needs_teacher_review(None) is False


def test_no_blocked_level_exists():
    """这一层只标记不阻断——不应出现 blocked 之类的拒绝态。"""
    result = assess_sensitivity("用药指南", "剂量")
    assert result["level"] != "blocked"


def test_topic_table_is_non_empty_and_documented():
    assert set(SENSITIVE_TOPICS) >= {"medical_advice", "unsettled_science"}
    for terms in SENSITIVE_TOPICS.values():
        assert terms, "主题词表不得为空，否则该主题静默失效"
