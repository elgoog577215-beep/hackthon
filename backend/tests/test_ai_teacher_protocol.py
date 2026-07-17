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
            "node_content": (
                "## 变量绑定\n变量名通过绑定指向当前值。\n\n"
                "## 可变值更新\n重新赋值会更新变量名指向的值。"
            ),
            "learning_objective": "能够解释变量绑定与重新赋值",
            "knowledge_structure": [{
                "concept_group": "变量语义",
                "description": "区分变量名、绑定和值的更新",
                "knowledge_points": [{
                    "name": "变量绑定",
                    "statement": "变量名通过绑定关系指向当前值。",
                    "knowledge_type": "definition",
                    "conditions": ["变量名已经完成赋值"],
                    "boundaries": ["变量名本身不是被保存的值"],
                    "capability_points": [{
                        "name": "解释变量绑定",
                        "observable_behavior": "给定一条赋值语句，准确指出变量名、绑定和值",
                    }],
                    "misconceptions": [{
                        "name": "把变量名等同于值",
                        "observable_error_pattern": "认为变量名改变会直接改变原值对象",
                        "discrimination": "分别标注变量名、绑定关系和值对象",
                        "repair_strategy": "绘制赋值前后的变量绑定图再解释变化",
                    }],
                    "mastery_criteria": [{
                        "name": "变量绑定解释达标",
                        "observable_performance": "独立解释赋值语句中的变量名、绑定和值",
                        "verification_method": "分析三个赋值案例并画出绑定关系",
                    }],
                    "entry_reason": "变量绑定是理解后续赋值行为的入口。",
                    "relations": [{
                        "target_name": "可变值更新",
                        "relation_type": "prerequisite",
                        "reason": "理解原有绑定后才能解释重新赋值如何更新指向",
                    }],
                }, {
                    "name": "可变值更新",
                    "statement": "重新赋值会让变量名指向新的值，而不会改写历史绑定事实。",
                    "knowledge_type": "rule",
                    "conditions": ["执行新的赋值语句"],
                    "boundaries": ["可变对象的原地修改不是重新绑定"],
                    "capability_points": [{
                        "name": "追踪重新赋值",
                        "observable_behavior": "逐步追踪多条赋值语句后的变量当前值",
                    }],
                    "mastery_criteria": [{
                        "name": "重新赋值追踪达标",
                        "observable_performance": "独立追踪多步赋值并说明每次绑定变化",
                        "verification_method": "完成一组多步赋值追踪并核对最终状态",
                    }],
                }],
            }],
            "key_points": ["变量绑定", "可变值更新"],
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


def test_ai_teacher_receives_bounded_current_course_knowledge_as_runtime_truth(monkeypatch):
    monkeypatch.setattr(ai_teacher_context, "build_learning_runtime", lambda *args, **kwargs: _runtime())
    monkeypatch.setattr(ai_teacher_context.practice_attempt_repository, "list", lambda *args, **kwargs: [])
    course = _course()

    package = build_ai_teacher_context(
        course,
        user_id="u1",
        question="为什么重新赋值不会改写原来的值？",
        node_id="node-1",
        entrypoint="selection",
    )

    context = package["knowledge_context"]
    assert context["schema_version"] == "ai_knowledge_context_v3"
    assert context["knowledge_library_id"].startswith("ckb_")
    assert 1 <= len(context["knowledge_nodes"]) <= 16
    assert context["skill_units"]
    assert context["mistake_points"]
    assert context["relations"]
    assert context["mastery_criteria"]
    assert context["usage_policy"]["role"] == "course_runtime_truth"
    assert context["usage_policy"]["identity_scope"] == "current_course_only"
    assert context["usage_policy"]["may_invent_formal_ids"] is False
    prompt = format_ai_teacher_context_prompt(package)
    assert "当前课程知识库是本课程知识身份" in prompt
    assert context_public_summary(package)["knowledge"]["knowledge_library_id"].startswith("ckb_")


def test_ai_teacher_does_not_treat_degraded_course_index_as_runtime_truth(monkeypatch):
    monkeypatch.setattr(ai_teacher_context, "build_learning_runtime", lambda *args, **kwargs: _runtime())
    monkeypatch.setattr(ai_teacher_context.practice_attempt_repository, "list", lambda *args, **kwargs: [])
    course = _course()
    course["nodes"][0].pop("knowledge_structure", None)
    course["nodes"][0]["key_points"] = ["变量"]

    package = build_ai_teacher_context(
        course,
        user_id="u1",
        question="解释这个知识点",
        node_id="node-1",
        entrypoint="selection",
    )
    context = package["knowledge_context"]

    assert context["mapping_status"] == "degraded"
    assert context["knowledge_nodes"] == []
    assert context["skill_units"] == []
    assert context["relations"] == []
    assert context["mastery_criteria"] == []
    assert context["usage_policy"]["role"] == "unavailable_until_quality_passed"


def test_ai_teacher_uses_source_course_candidate_subject_library_as_provisional_fallback(monkeypatch):
    monkeypatch.setattr(ai_teacher_context, "build_learning_runtime", lambda *args, **kwargs: _runtime())
    monkeypatch.setattr(ai_teacher_context.practice_attempt_repository, "list", lambda *args, **kwargs: [])
    course = _course()
    section_name = str(course["nodes"][0]["node_name"])
    course["nodes"][0].pop("knowledge_structure", None)
    course["nodes"][0]["key_points"] = []
    library = {
        "schema_version": "knowledge_library_v3",
        "library_id": "subject.variables",
        "subject_id": "computer_science.variables",
        "version": "1.0.0-candidate",
        "revision_id": "sklr_variables",
        "lifecycle_status": "candidate",
        "source_course_ids": [course["course_id"]],
        "nodes": [{
            "knowledge_id": "subject.variables.root",
            "parent_id": None,
            "node_type": "subject",
            "name": "Variables",
            "aliases": [],
            "path_ids": ["subject.variables.root"],
            "path_names": ["Variables"],
        }, {
            "knowledge_id": "subject.variables.binding",
            "parent_id": "subject.variables.root",
            "node_type": "knowledge_point",
            "name": "Variable binding",
            "aliases": [section_name],
            "path_ids": ["subject.variables.root", "subject.variables.binding"],
            "path_names": ["Variables", "Variable binding"],
            "learning_actions": ["Trace a binding update"],
        }],
        "relations": [],
        "skill_units": [{
            "skill_unit_id": "skill.variables.trace",
            "name": "Trace variable bindings",
            "primary_knowledge_id": "subject.variables.binding",
            "knowledge_ids": ["subject.variables.binding"],
        }],
        "mistake_points": [],
        "improvement_points": [],
        "skill_relations": [],
        "usage_policy": {"may_invent_formal_ids": False},
    }
    monkeypatch.setattr(ai_teacher_context, "resolve_subject_library", lambda _course: library, raising=False)

    package = build_ai_teacher_context(
        course,
        user_id="u1",
        question="Explain the binding",
        node_id="node-1",
        entrypoint="selection",
    )
    context = package["knowledge_context"]

    assert context["knowledge_library_id"] == "subject.variables"
    assert [item["knowledge_id"] for item in context["knowledge_nodes"]] == ["subject.variables.binding"]
    assert context["skill_units"][0]["skill_unit_id"] == "skill.variables.trace"
    assert context["mapping_status"] == "mapped"
    assert context["usage_policy"]["role"] == "provisional_reference"


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
