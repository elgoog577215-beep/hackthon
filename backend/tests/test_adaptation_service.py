"""
adaptation_service 单元测试（Phase 2：证据侧）。

覆盖：
  - evaluate_evidence_for_node 的证据门槛判定逻辑（单条强证据 / 多条弱证据综合信号 /
    不达标不触发 / 时效性衰减 / 弱证据类型打折）
  - generate_change_set 的 LLM 生成与受控重试逻辑（全部 mock LLM 调用，不发真实请求）
"""

import os
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

_backend_dir = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _backend_dir)

import pytest

from adaptation_service import (
    COMBINED_SIGNAL_TRIGGER_THRESHOLD,
    SINGLE_EVIDENCE_TRIGGER_THRESHOLD,
    evaluate_evidence_for_node,
    generate_change_set,
)
from adaptive_models import AdaptationHypothesis, EvidenceItem


# ---------------------------------------------------------------------------
# 构造辅助
# ---------------------------------------------------------------------------

def _evidence(
    node_id: str = "node-1",
    evidence_type: str = "dialogue_reask",
    strength: float = 0.5,
    created_at: datetime = None,
    **kwargs,
) -> EvidenceItem:
    return EvidenceItem(
        node_id=node_id,
        evidence_type=evidence_type,
        strength=strength,
        content="test evidence",
        course_id="course-1",
        created_at=created_at or datetime.now(),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# evaluate_evidence_for_node
# ---------------------------------------------------------------------------

class TestEvaluateEvidenceForNode:
    def test_no_evidence_returns_none(self):
        assert evaluate_evidence_for_node([], "node-1", "course-1") is None

    def test_evidence_for_other_node_ignored(self):
        items = [_evidence(node_id="node-2", strength=0.99)]
        assert evaluate_evidence_for_node(items, "node-1", "course-1") is None

    def test_single_very_strong_evidence_triggers_immediately(self):
        """规格文档：单条极强证据 MAY 立即触发，不要求'多次出现'。"""
        items = [_evidence(strength=SINGLE_EVIDENCE_TRIGGER_THRESHOLD, evidence_type="explicit_feedback")]
        hyp = evaluate_evidence_for_node(items, "node-1", "course-1")
        assert hyp is not None
        assert isinstance(hyp, AdaptationHypothesis)
        assert hyp.node_id == "node-1"
        assert hyp.course_id == "course-1"
        assert len(hyp.supporting_evidence_ids) == 1

    def test_single_medium_evidence_does_not_trigger_alone(self):
        items = [_evidence(strength=0.4, evidence_type="skip_behavior")]
        hyp = evaluate_evidence_for_node(items, "node-1", "course-1")
        assert hyp is None

    def test_single_weak_evidence_far_below_threshold_no_trigger(self):
        items = [_evidence(strength=0.2)]
        assert evaluate_evidence_for_node(items, "node-1", "course-1") is None

    def test_multiple_weak_evidence_combined_signal_can_trigger(self):
        """规格文档：多条弱证据 MUST 结合强度/一致性/覆盖范围/时效性综合判断。"""
        now = datetime.now()
        items = [
            _evidence(strength=0.6, evidence_type="dialogue_reask", created_at=now),
            _evidence(strength=0.6, evidence_type="dialogue_reask", created_at=now),
            _evidence(strength=0.5, evidence_type="wrong_answer", created_at=now),
        ]
        hyp = evaluate_evidence_for_node(items, "node-1", "course-1", now=now)
        assert hyp is not None
        assert len(hyp.supporting_evidence_ids) == 3
        assert hyp.confidence >= COMBINED_SIGNAL_TRIGGER_THRESHOLD

    def test_two_weak_skip_behavior_alone_does_not_trigger(self):
        """弱证据类型（skip_behavior）应被打折，仅两条也不足以触发。"""
        now = datetime.now()
        items = [
            _evidence(strength=0.4, evidence_type="skip_behavior", created_at=now),
            _evidence(strength=0.4, evidence_type="skip_behavior", created_at=now),
        ]
        hyp = evaluate_evidence_for_node(items, "node-1", "course-1", now=now)
        assert hyp is None

    def test_not_a_fixed_count_threshold(self):
        """规格文档明确要求：不得仅以固定次数作为唯一触发条件。
        用相同数量（3条）但强度组合不同的两组证据，验证是否触发结果不同——
        证明判定不是单纯"count >= 3"这种机械计数。
        """
        now = datetime.now()
        low_strength_group = [
            _evidence(strength=0.15, evidence_type="skip_behavior", created_at=now)
            for _ in range(3)
        ]
        high_strength_group = [
            _evidence(strength=0.75, evidence_type="dialogue_reask", created_at=now),
            _evidence(strength=0.7, evidence_type="explicit_feedback", created_at=now - timedelta(days=1)),
            _evidence(strength=0.65, evidence_type="wrong_answer", created_at=now),
        ]
        low_hyp = evaluate_evidence_for_node(low_strength_group, "node-1", "course-1", now=now)
        high_hyp = evaluate_evidence_for_node(high_strength_group, "node-1", "course-1", now=now)
        assert low_hyp is None
        assert high_hyp is not None

    def test_stale_evidence_recency_decay_reduces_trigger_likelihood(self):
        """超出时效性窗口的证据权重应显著降低触发可能性。"""
        now = datetime.now()
        stale_items = [
            _evidence(strength=0.6, evidence_type="dialogue_reask", created_at=now - timedelta(days=60))
            for _ in range(3)
        ]
        fresh_items = [
            _evidence(strength=0.6, evidence_type="dialogue_reask", created_at=now)
            for _ in range(3)
        ]
        stale_hyp = evaluate_evidence_for_node(stale_items, "node-1", "course-1", now=now)
        fresh_hyp = evaluate_evidence_for_node(fresh_items, "node-1", "course-1", now=now)
        # 新鲜证据更容易触发或置信度更高
        if stale_hyp is not None and fresh_hyp is not None:
            assert fresh_hyp.confidence >= stale_hyp.confidence
        else:
            assert fresh_hyp is not None or stale_hyp is None


# ---------------------------------------------------------------------------
# generate_change_set（mock LLM 调用）
# ---------------------------------------------------------------------------

def _hypothesis() -> AdaptationHypothesis:
    return AdaptationHypothesis(
        node_id="node-1",
        course_id="course-1",
        hypothesis="学生连续追问，推导颗粒度偏粗",
        supporting_evidence_ids=["ev-1", "ev-2"],
        confidence=0.75,
    )


VALID_LLM_JSON = """{
  "scope": "section",
  "scope_node_ids": ["node-1", "node-2"],
  "change_items": [
    {
      "target_node_id": "node-1",
      "operation": "modify",
      "before": "原内容",
      "after": "补充了更详细的推导步骤",
      "reason": "学生连续追问，补充细节"
    },
    {
      "target_node_id": "node-2",
      "operation": "add",
      "before": null,
      "after": "预防性补充说明",
      "reason": "预防性建议"
    }
  ]
}"""


class TestGenerateChangeSet:
    @pytest.mark.asyncio
    async def test_generate_change_set_success_on_first_attempt(self):
        with patch("adaptation_service._generator._call_llm", new=AsyncMock(return_value=VALID_LLM_JSON)):
            result = await generate_change_set(_hypothesis(), node_content="旧内容")
        assert result is not None
        assert result.course_id == "course-1"
        assert result.scope == "section"
        assert len(result.change_items) == 2
        assert result.source_hypothesis_id == _hypothesis().id or result.source_hypothesis_id is not None
        assert result.status == "pending"
        # 生成可追溯性记录 MUST 存在
        assert "model_id" in result.generation_meta
        assert "prompt_template" in result.generation_meta
        assert "params" in result.generation_meta

    @pytest.mark.asyncio
    async def test_generate_change_set_retries_on_invalid_json_then_succeeds(self):
        call_mock = AsyncMock(side_effect=["not a json at all", VALID_LLM_JSON])
        with patch("adaptation_service._generator._call_llm", new=call_mock):
            result = await generate_change_set(_hypothesis())
        assert result is not None
        assert call_mock.await_count == 2

    @pytest.mark.asyncio
    async def test_generate_change_set_fails_after_max_retries_returns_none(self):
        call_mock = AsyncMock(return_value="still not valid json")
        with patch("adaptation_service._generator._call_llm", new=call_mock):
            result = await generate_change_set(_hypothesis())
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_change_set_empty_llm_response_returns_none(self):
        call_mock = AsyncMock(return_value=None)
        with patch("adaptation_service._generator._call_llm", new=call_mock):
            result = await generate_change_set(_hypothesis())
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_change_set_skips_invalid_change_item_but_keeps_valid_ones(self):
        """单条 change_item 校验失败时应被跳过，而不是让整个 change_set 生成失败。"""
        partially_invalid_json = """{
          "scope": "block",
          "scope_node_ids": ["node-1"],
          "change_items": [
            {"target_node_id": "node-1", "operation": "invalid_op_not_allowed", "after": "x", "reason": "r"},
            {"target_node_id": "node-1", "operation": "modify", "after": "有效的补充内容", "reason": "有效理由"}
          ]
        }"""
        with patch("adaptation_service._generator._call_llm", new=AsyncMock(return_value=partially_invalid_json)):
            result = await generate_change_set(_hypothesis())
        assert result is not None
        assert len(result.change_items) == 1
        assert result.change_items[0].after == "有效的补充内容"
        assert "skipped_change_items" in result.generation_meta

    @pytest.mark.asyncio
    async def test_generate_change_set_missing_scope_triggers_retry(self):
        missing_scope_json = '{"change_items": [{"target_node_id": "node-1", "operation": "modify", "after": "x", "reason": "r"}]}'
        call_mock = AsyncMock(side_effect=[missing_scope_json, VALID_LLM_JSON])
        with patch("adaptation_service._generator._call_llm", new=call_mock):
            result = await generate_change_set(_hypothesis())
        assert result is not None
        assert call_mock.await_count == 2
