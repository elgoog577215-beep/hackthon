import os
import sys
from unittest.mock import MagicMock


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))


def _model(*, support_status="unknown", support_confidence="low"):
    return {
        "schema_version": "learner_model_v1",
        "model_revision_id": "lmr_test",
        "data_sufficiency": {
            "level": "limited",
            "formal_evidence_count": 1,
            "total_evidence_count": 1,
        },
        "summary": {"mastered_objectives": 0, "needs_attention_objectives": 0},
        "objectives": [{
            "objective_id": "lo_1",
            "objective_revision_id": "lor_1",
            "node_id": "node-1",
            "node_name": "极限定义",
            "statement": "能够解释极限定义",
            "reading_status": "learning",
            "mastery_status": "not_checked",
            "confidence": "low",
            "support_need": {
                "status": support_status,
                "confidence": support_confidence,
                "reason_code": (
                    "repeated_independent_failure"
                    if support_status == "needs_support"
                    else "single_formal_failure_insufficient"
                ),
                "evidence_refs": ["attempt-1"],
            },
        }],
        "strengths": [],
        "needs_attention": [],
    }


def test_ai_learning_context_uses_explicit_request_but_not_one_failure_as_weakness(monkeypatch):
    import ai_learning_context

    monkeypatch.setattr(
        ai_learning_context,
        "build_current_learner_model_for_course",
        lambda *_args, **_kwargs: _model(),
    )
    context = ai_learning_context.build_ai_learning_context(
        user_id="u1",
        course_id="course-1",
        node_id="node-1",
        node_name="极限定义",
        question="我不懂，请简化并举个例子",
        request_context="请求侧课程片段",
    )
    data = context.to_dict()
    prompt = context.to_prompt()

    assert data["learner_model"]["model_revision_id"] == "lmr_test"
    assert data["teaching_guidance"]["needs_simplification"] is True
    assert data["teaching_guidance"]["needs_examples"] is True
    assert data["teaching_guidance"]["needs_weakness_practice"] is False
    assert data["metadata"]["learner_model_revision_id"] == "lmr_test"
    assert "正式学习者模型" in prompt
    assert "单次失败不等于稳定薄弱点" in prompt
    assert "请求侧课程片段" in prompt


def test_ai_learning_context_uses_repeated_formal_failure_for_bounded_remediation(monkeypatch):
    import ai_learning_context

    monkeypatch.setattr(
        ai_learning_context,
        "build_current_learner_model_for_course",
        lambda *_args, **_kwargs: _model(
            support_status="needs_support",
            support_confidence="high",
        ),
    )
    context = ai_learning_context.build_ai_learning_context(
        user_id="u1",
        course_id="course-1",
        node_id="node-1",
    )

    assert context.teaching_guidance["needs_weakness_practice"] is True
    assert context.teaching_guidance["recommends_review"] is True
    assert context.teaching_guidance["evidence_refs"] == ["attempt-1"]


def test_ai_learning_context_does_not_use_expired_support_evidence(monkeypatch):
    import ai_learning_context

    expired = _model(support_status="needs_support", support_confidence="high")
    expired["objectives"][0]["valid_until"] = "2000-01-01T00:00:00+00:00"
    monkeypatch.setattr(
        ai_learning_context,
        "build_current_learner_model_for_course",
        lambda *_args, **_kwargs: expired,
    )

    context = ai_learning_context.build_ai_learning_context(
        user_id="u1",
        course_id="course-1",
        node_id="node-1",
    )

    assert context.teaching_guidance["needs_weakness_practice"] is False
    assert context.teaching_guidance["recommends_review"] is False
    assert "证据已过有效期" in context.learner_model_prompt


def test_course_generation_strategy_reads_formal_teaching_guidance():
    import course_generation_strategy as strategy

    general = strategy.build_course_generation_strategy_prompt(
        strategy.GENERAL_COURSE_BLUEPRINT,
    )
    remediation = strategy.build_course_generation_strategy_prompt(
        strategy.WEAKNESS_REMEDIATION_CONTENT,
        ai_learning_context={
            "teaching_guidance": {
                "needs_simplification": True,
                "needs_examples": True,
                "needs_weakness_practice": True,
                "recommends_review": True,
            }
        },
    )

    assert "生成用途：通用课程结构蓝图" in general
    assert "是否读取 AI Learning Context：否" in general
    assert "生成用途：薄弱点补充内容" in remediation
    assert "简化解释并减少跳步" in remediation
    assert "增加针对薄弱点的练习" in remediation


def test_course_service_prompt_contains_model_revision_not_legacy_state(monkeypatch):
    import ai_learning_context
    import course_service

    monkeypatch.setattr(
        ai_learning_context,
        "build_current_learner_model_for_course",
        lambda *_args, **_kwargs: _model(),
    )
    fake_context_manager = MagicMock()
    fake_context_manager.get_generation_context.return_value = {
        "ledger_context": "课程账本：极限之前要理解函数。"
    }
    service = course_service.CourseService(context_manager=fake_context_manager)

    prompt = service._build_redefine_prompt(
        course_id="course-1",
        node={
            "node_id": "node-1",
            "node_name": "极限定义",
            "node_content": "旧内容",
            "learning_objective": "理解极限",
            "scope_boundary": "只讲直觉",
            "key_points": ["左右极限"],
            "misconceptions": ["左右极限不一致"],
            "assessment": ["能判断左右极限"],
        },
        requirement="请简化并补例子",
        user_id="u1",
    )

    assert "AI Learning Context" in prompt
    assert "正式学习者模型" in prompt
    assert "lmr_test" in prompt
    assert "学习者状态摘要" not in prompt
    assert "教学决策摘要" not in prompt
    assert "课程账本：极限之前要理解函数。" in prompt


def test_course_service_quality_check_does_not_append_learner_event(monkeypatch):
    import course_service
    import learning_events

    class MemoryStorage:
        def __init__(self):
            self.data = {}

        def load_data(self, filename):
            return self.data.get(filename)

        def save_data(self, filename, value):
            self.data[filename] = value

    storage = MemoryStorage()
    monkeypatch.setattr(learning_events, "storage", storage)
    service = course_service.CourseService(context_manager=MagicMock())

    service._record_generation_quality(
        output_type="content_block",
        output_text="新的练习内容",
        context_text="课程上下文",
        source="test",
        course_id="course-1",
        node_id="node-1",
        node_name="极限定义",
    )

    assert learning_events.load_learning_events() == []
