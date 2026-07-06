import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from conftest import MockStorage


def test_learner_context_aggregates_profile_notes_and_mistakes(monkeypatch):
    import learner_context as learner_mod

    mock_storage = MockStorage()
    mock_storage.annotations = [
        {
            "anno_id": "n1",
            "course_id": "course-1",
            "node_id": "node-1",
            "source_type": "user",
            "anno_summary": "极限定义笔记",
            "answer": "我不理解 epsilon-delta 的顺序。",
            "timestamp": "2026-07-06T10:00:00",
        },
        {
            "anno_id": "w1",
            "course_id": "course-1",
            "node_id": "node-1",
            "source_type": "wrong",
            "anno_summary": "错题：极限左右方向",
            "question": "为什么左极限和右极限要同时存在？",
            "timestamp": "2026-07-06T11:00:00",
        },
    ]
    monkeypatch.setattr(learner_mod, "storage", mock_storage)

    learner_mod.save_profile_snapshot(
        ai_profile="完整画像",
        persona_summary="偏好先看例子再看形式定义",
        self_evaluation="数学基础一般",
    )

    context = learner_mod.build_learner_context(course_id="course-1", node_id="node-1")

    assert "极限定义笔记" in context.notes
    assert "左右方向" in context.mistakes
    assert "偏好先看例子" in context.to_prompt()
    assert "数学基础一般" in context.preferences


def test_learner_context_request_persona_overrides_snapshot(monkeypatch):
    import learner_context as learner_mod

    mock_storage = MockStorage()
    mock_storage.data[learner_mod.PROFILE_SNAPSHOT_FILE] = {
        learner_mod.DEFAULT_USER_ID: {"persona_summary": "旧画像"}
    }
    monkeypatch.setattr(learner_mod, "storage", mock_storage)

    context = learner_mod.build_learner_context(request_persona="当前请求画像")

    assert context.persona_summary == "当前请求画像"
