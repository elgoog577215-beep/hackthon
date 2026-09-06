"""出题链路的 provider 重试次数必须可配置，而不是写死为 1。"""

import re

import assessment_orchestrator
from assessment_orchestrator import _assessment_retry_count


def test_default_is_not_a_single_attempt():
    """默认 1 意味着零重试：一次网络抖动就毁掉整轮生成。"""
    assert _assessment_retry_count() == 3


def test_env_override_and_bad_value_fallback(monkeypatch):
    monkeypatch.setenv("AI_ASSESSMENT_RETRY_COUNT", "5")
    assert _assessment_retry_count() == 5
    monkeypatch.setenv("AI_ASSESSMENT_RETRY_COUNT", "0")
    assert _assessment_retry_count() == 1  # 下限保护
    monkeypatch.setenv("AI_ASSESSMENT_RETRY_COUNT", "not-a-number")
    assert _assessment_retry_count() == 3


def test_no_hardcoded_retry_count_remains_in_orchestrator():
    """防回归：不允许再出现写死的 retry_count=<数字>。"""
    source = open(assessment_orchestrator.__file__, encoding="utf-8").read()
    assert not re.search(r"retry_count=\d", source)
    assert source.count("retry_count=_assessment_retry_count()") == 8
