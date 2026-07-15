from __future__ import annotations

from pathlib import Path

import pytest

import ai_teacher_actions
import ai_teacher_context
import learning_runtime
from ai_qa_service import AIQAService
from ai_teacher_actions import build_trigger_candidate, execute_proposal, propose_action, undo_receipt
from ai_teacher_context import build_ai_teacher_context, context_public_summary, format_ai_teacher_context_prompt
from ai_teacher_state import AITeacherRepository
from learning_records import LearningRecordRepository


class _EmptyRuntimeRepository:
    def list(self, *_args):
        return []

    def load(self, *_args):
        return None


def _course() -> dict:
    return {
        "course_id": "course-ai",
        "current_course_version_id": "cv-1",
        "course_name": "AI protocol",
        "nodes": [{
            "node_id": "node-1",
            "node_name": "变量",
            "node_level": 2,
            "node_content": "## 变量\n变量用于保存可以变化的值。\n\n### 示例\n令 x = 1。",
            "learning_objective": "理解变量",
        }],
    }


def _runtime(action_type: str = "complete_reading") -> dict:
    return {
        "runtime_revision_id": "runtime-1",
        "revision_vector": {"course_version_id": "cv-1", "events": "e1"},
        "context": {
            "course_id": "course-ai",
            "course_version_id": "cv-1",
            "chapter_id": "chapter-1",
            "node_id": "node-1",
            "objective_id": "obj-1",
            "objective_revision_id": "objr-1",
        },
        "active_task": {
            "kind": "reading",
            "object_id": "obj-1",
            "status": "active",
            "task_revision_id": "objr-1",
        },
        "progress": {"nodes": [{"node_id": "node-1", "reading_status": "in_progress"}]},
        "records": {"open_issues": 0},
        "practice": {"active_attempt_count": 0},
        "diagnostic": {},
        "learner_model": {
            "model_revision_id": "model-1",
            "observed_at": "2026-07-14T00:00:00+00:00",
            "data_sufficiency": {"level": "limited", "formal_evidence_count": 0},
            "summary": {"total_objectives": 1, "needs_attention_objectives": 1},
            "current_objective": {
                "node_id": "node-1",
                "objective_revision_id": "objr-1",
                "reading_status": "in_progress",
                "mastery_status": "evidence_insufficient",
                "confidence": "low",
                "support_need": {"status": "needs_support", "reason_code": "open_user_issue"},
                "evidence_refs": [{
                    "source_id": "record-1",
                    "type": "learning_record:issue",
                    "status": "open",
                    "outcome": "user_retained",
                    "strength": "self_report",
                    "observed_at": "2026-07-14T00:00:00+00:00",
                }],
            },
            "strengths": [],
            "needs_attention": [{"node_id": "node-1", "reason_code": "open_user_issue"}],
        },
        "continuation": {
            "primary_action": {
                "action_id": "action-1",
                "action_type": action_type,
                "reason_code": "reading_in_progress",
                "task_ref": {"kind": "reading", "object_id": "obj-1", "task_revision_id": "objr-1"},
            }
        },
    }


def test_repository_keeps_receipt_audit_when_conversation_is_deleted(tmp_path: Path):
    repository = AITeacherRepository(tmp_path)
    conversation = repository.create_conversation("u1", "course-ai", title="变量")
    message = repository.append_message(
        "u1",
        "course-ai",
        conversation["conversation_id"],
        {"role": "user", "content": "变量是什么"},
    )
    assert message["role"] == "user"
    receipt = repository.save_receipt("u1", "course-ai", {
        "conversation_id": conversation["conversation_id"],
        "idempotency_key": "receipt-key-1",
        "status": "succeeded",
    })

    assert repository.delete_conversation("u1", "course-ai", conversation["conversation_id"])
    assert repository.list_conversations("u1", "course-ai") == []
    preserved = repository.get_receipt("u1", "course-ai", receipt["receipt_id"])
    assert preserved["conversation_deleted"] is True


def test_context_package_is_scoped_and_never_includes_reference_answer(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(ai_teacher_context, "build_learning_runtime", lambda *args, **kwargs: _runtime())
    monkeypatch.setattr(ai_teacher_context.practice_attempt_repository, "list", lambda *args, **kwargs: [])

    package = build_ai_teacher_context(
        _course(),
        user_id="u1",
        question="我在变量这里的薄弱点是什么？",
        node_id="node-1",
        selection="变量用于保存可以变化的值",
        entrypoint="selection",
        conversation={"conversation_id": "c1", "messages": []},
    )

    assert package["runtime"]["runtime_revision_id"] == "runtime-1"
    assert package["runtime"]["progress_summary"]["reading_status"] == "in_progress"
    assert 1 <= len(package["sources"]) <= ai_teacher_context.MAX_SOURCES
    assert package["task"]["answer_disclosure"]["reference_answer_in_context"] is False
    assert any(item["type"] == "learning_record:issue" for item in package["learner_evidence"])
    assert package["learner_model"]["model_revision_id"] == "model-1"
    assert package["learner_model"]["current_objective"]["support_need"]["reason_code"] == "open_user_issue"
    public = context_public_summary(package)
    assert all("content" not in item for item in public["sources"])
    assert "learner_evidence" not in public
    assert public["learner_model_revision_id"] == "model-1"


def test_ai_teacher_receives_bounded_formal_knowledge_as_reference_only(monkeypatch):
    monkeypatch.setattr(ai_teacher_context, "build_learning_runtime", lambda *args, **kwargs: _runtime())
    monkeypatch.setattr(ai_teacher_context.practice_attempt_repository, "list", lambda *args, **kwargs: [])
    course = _course()
    course["course_name"] = "线性代数"
    course["nodes"][0].update({
        "node_name": "高斯消元",
        "key_points": ["高斯消元法步骤与行简化阶梯形"],
        "node_content": "## 高斯消元\n使用高斯消元法步骤与行简化阶梯形求解。",
    })

    package = build_ai_teacher_context(
        course,
        user_id="u1",
        question="为什么行变换不会改变解集？",
        node_id="node-1",
        entrypoint="selection",
    )

    context = package["knowledge_context"]
    assert context["knowledge_library_id"] == "math.linear_algebra.v1"
    assert 1 <= len(context["knowledge_nodes"]) <= 16
    assert context["skill_units"]
    assert context["mistake_points"]
    assert context["usage_policy"]["role"] == "reference_only"
    assert context["usage_policy"]["allowed_fit"] == ["hit", "partial", "miss"]
    assert context["usage_policy"]["may_invent_formal_ids"] is False
    prompt = format_ai_teacher_context_prompt(package)
    assert "必须先依据当前正文、任务和证据判断" in prompt
    assert context_public_summary(package)["knowledge"]["course_map_revision_id"]


def test_explanation_context_does_not_load_unrelated_model_details(monkeypatch):
    monkeypatch.setattr(ai_teacher_context, "build_learning_runtime", lambda *args, **kwargs: _runtime())
    monkeypatch.setattr(ai_teacher_context.practice_attempt_repository, "list", lambda *args, **kwargs: [])

    package = build_ai_teacher_context(
        _course(),
        user_id="u1",
        question="变量为什么可以变化？",
        node_id="node-1",
        entrypoint="selection",
    )

    assert package["request"]["intent"] == "explain_content"
    assert package["learner_evidence"] == []
    assert "current_objective" not in package["learner_model"]


def test_ai_teacher_downgrades_expired_model_evidence(monkeypatch):
    runtime = _runtime()
    runtime["learner_model"]["current_objective"]["valid_until"] = "2000-01-01T00:00:00+00:00"
    runtime["learner_model"]["needs_attention"][0]["valid_until"] = "2000-01-01T00:00:00+00:00"
    monkeypatch.setattr(ai_teacher_context, "build_learning_runtime", lambda *args, **kwargs: runtime)
    monkeypatch.setattr(ai_teacher_context.practice_attempt_repository, "list", lambda *args, **kwargs: [])

    package = build_ai_teacher_context(
        _course(),
        user_id="u1",
        question="我在变量这里的薄弱点是什么？",
        node_id="node-1",
        entrypoint="global",
    )

    assert package["learner_model"]["current_objective"]["support_need"]["reason_code"] == "evidence_expired"
    assert package["learner_model"]["needs_attention"] == []
    assert package["learner_evidence"] == []
    assert context_public_summary(package)["data_sufficiency"]["level"] == "limited"


def test_context_does_not_trust_client_task_status_for_answer_disclosure(monkeypatch):
    monkeypatch.setattr(ai_teacher_context, "build_learning_runtime", lambda *args, **kwargs: _runtime())
    monkeypatch.setattr(ai_teacher_context.practice_attempt_repository, "list", lambda *args, **kwargs: [])

    package = build_ai_teacher_context(
        _course(),
        user_id="u1",
        question="直接告诉我答案",
        node_id="node-1",
        entrypoint="practice",
        task_ref={"kind": "practice", "object_id": "forged", "status": "graded"},
    )

    assert package["task"]["answer_disclosure"] == {
        "full_solution_allowed": False,
        "reference_answer_in_context": False,
        "reason": "formal_task_not_submitted",
    }


def test_block_answer_prompt_forbids_proactive_next_step(monkeypatch):
    monkeypatch.setattr(ai_teacher_context, "build_learning_runtime", lambda *args, **kwargs: _runtime())
    monkeypatch.setattr(ai_teacher_context.practice_attempt_repository, "list", lambda *args, **kwargs: [])

    package = build_ai_teacher_context(
        _course(),
        user_id="u1",
        question="请解释当前内容块",
        node_id="node-1",
        entrypoint="block",
        context_ref={"content_anchor": {"block_id": "block-1"}},
    )
    prompt = format_ai_teacher_context_prompt(package)

    assert "不得主动提出下一步、出题、保存或课程改写" in prompt
    assert "如果你愿意" in prompt


def test_record_action_is_idempotent_and_undo_archives_without_erasing(monkeypatch, tmp_path: Path):
    interactions = AITeacherRepository(tmp_path / "interactions")
    records = LearningRecordRepository(tmp_path / "records")
    monkeypatch.setattr(ai_teacher_actions, "build_learning_runtime", lambda *args, **kwargs: _runtime())
    monkeypatch.setattr(ai_teacher_actions, "learning_record_repository", records)
    monkeypatch.setattr(ai_teacher_actions, "record_learning_event", lambda **kwargs: None)

    proposal = propose_action(
        _course(),
        user_id="u1",
        action_type="create_note",
        target_ref={"node_id": "node-1"},
        payload={"node_id": "node-1", "title": "变量", "content": "变量保存可变化的值"},
        confirmation_mode="user_command",
        origin="user_command",
        repository=interactions,
    )
    first = execute_proposal(
        _course(),
        user_id="u1",
        proposal_id=proposal["proposal_id"],
        idempotency_key="execute-note-1",
        repository=interactions,
    )
    second = execute_proposal(
        _course(),
        user_id="u1",
        proposal_id=proposal["proposal_id"],
        idempotency_key="execute-note-1",
        repository=interactions,
    )

    assert first["receipt_id"] == second["receipt_id"]
    assert len(records.list("u1", "course-ai")) == 1

    undone = undo_receipt(
        _course(),
        user_id="u1",
        receipt_id=first["receipt_id"],
        idempotency_key="undo-note-1",
        repository=interactions,
    )
    assert undone["status"] == "succeeded"
    assert records.list("u1", "course-ai")[0]["status"] == "archived"


def test_trigger_requires_strong_runtime_action_and_respects_suppression(monkeypatch, tmp_path: Path):
    interactions = AITeacherRepository(tmp_path)
    monkeypatch.setattr(ai_teacher_actions, "build_learning_runtime", lambda *args, **kwargs: _runtime("complete_reading"))
    assert build_trigger_candidate(_course(), user_id="u1", node_id="node-1", repository=interactions) is None

    monkeypatch.setattr(ai_teacher_actions, "build_learning_runtime", lambda *args, **kwargs: _runtime("resume_diagnostic"))
    candidate = build_trigger_candidate(_course(), user_id="u1", node_id="node-1", repository=interactions)
    assert candidate["trigger_type"] == "runtime_support"
    interactions.save_suppression("u1", "course-ai", {
        "suppression_key": candidate["dedupe_key"],
        "evidence_revision": candidate["runtime_revision_id"],
        "mode": "not_now",
    })
    assert build_trigger_candidate(_course(), user_id="u1", node_id="node-1", repository=interactions) is None


@pytest.mark.asyncio
async def test_ai_teacher_converts_provider_error_chunk_to_failure():
    service = AIQAService()

    async def failed_stream(*args, **kwargs):
        yield "\n[Error: provider authentication failed]"

    service._stream_llm = failed_stream
    with pytest.raises(RuntimeError, match="AI provider unavailable"):
        async for _ in service.answer_question_stream(
            "解释变量",
            context_package={"conversation": {"recent_messages": []}},
        ):
            pass


@pytest.mark.asyncio
async def test_provider_failure_does_not_change_deterministic_learning_runtime(monkeypatch):
    monkeypatch.setattr(learning_runtime, "load_learning_events", lambda **_kwargs: [])
    monkeypatch.setattr(learning_runtime, "practice_attempt_repository", _EmptyRuntimeRepository())
    monkeypatch.setattr(learning_runtime, "learning_record_repository", _EmptyRuntimeRepository())
    monkeypatch.setattr(learning_runtime, "learning_snapshot_repository", _EmptyRuntimeRepository())
    monkeypatch.setattr(
        learning_runtime,
        "workflow_view",
        lambda *_args, **_kwargs: {"phase": "practice", "case": None, "session": None, "current_task": None},
    )
    service = AIQAService()

    async def failed_stream(*args, **kwargs):
        yield "\n[Error: provider timed out]"

    service._stream_llm = failed_stream
    before = learning_runtime.build_learning_runtime(_course(), user_id="u-provider-down")

    with pytest.raises(RuntimeError, match="AI provider unavailable"):
        async for _ in service.answer_question_stream(
            "解释变量",
            context_package={"conversation": {"recent_messages": []}},
        ):
            pass

    after = learning_runtime.build_learning_runtime(_course(), user_id="u-provider-down")
    assert after["runtime_revision_id"] == before["runtime_revision_id"]
    assert after["continuation"]["primary_action"] == before["continuation"]["primary_action"]
    assert after["course_availability"] == before["course_availability"]
