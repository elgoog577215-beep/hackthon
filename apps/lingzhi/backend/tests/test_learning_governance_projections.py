"""删除事实后，派生投影必须一致失效或重算——正面验证。

任务书要求：删除类操作必须有正面测试证明"派生投影一致失效或重算"，不能只测接口
返回 200。所以这里断言的是投影**内容的变化**：

- 持久化的 `CourseEvolutionState`：引用已删事实的 EvidenceItem 被丢弃，失去全部
  支撑的假设被标为 expired，pending 计划变 stale。这是引用空洞的真正风险面。
- 每次请求重算的 `LearnerModel`：被删事实不再出现在 evidence_catalog。
"""

from __future__ import annotations

from pathlib import Path

import pytest

import learning_events
import learning_governance
from course_evolution import (
    AdaptationHypothesis,
    CourseEvolutionRepository,
    CourseEvolutionState,
    EvidenceAnchor,
    EvidenceItem,
)
from learning_governance import delete_learning_facts


class MemoryStorage:
    def __init__(self):
        self.data: dict[str, object] = {}

    def load_data(self, filename):
        import copy

        return copy.deepcopy(self.data.get(filename))

    def save_data(self, filename, value):
        import copy

        self.data[filename] = copy.deepcopy(value)


@pytest.fixture
def memory_storage(monkeypatch):
    storage = MemoryStorage()
    monkeypatch.setattr(learning_events, "storage", storage)
    monkeypatch.setattr(learning_governance, "storage", storage)
    return storage


@pytest.fixture
def evolution_repository(tmp_path, monkeypatch):
    import course_evolution

    repository = CourseEvolutionRepository(tmp_path / "course_evolution")
    monkeypatch.setattr(course_evolution, "course_evolution_repository", repository)
    return repository


def _seed_state_referencing(event_id: str, *, repository, evidence_id="evi_1"):
    """构造一个引用该事实的持久化演进状态。"""
    now = "2026-08-12T00:00:00+00:00"
    state = CourseEvolutionState(
        user_id="learner-1",
        course_id="course-1",
        evidence_items=[
            EvidenceItem(
                evidence_id=evidence_id,
                user_id="learner-1",
                course_id="course-1",
                source_type="learning_event",
                source_id=event_id,
                evidence_kind="explicit_comprehension_gap",
                summary="这段没懂",
                strength=0.9,
                anchor=EvidenceAnchor(section_id="objective-1", block_id="block-1"),
                created_at=now,
            ),
        ],
        hypotheses=[
            AdaptationHypothesis(
                hypothesis_id="hyp_1",
                user_id="learner-1",
                course_id="course-1",
                problem_type="comprehension_gap",
                claim="学习者在向量定义处存在理解断裂",
                target_block_id="block-1",
                support_evidence_ids=[evidence_id],
                confidence=0.8,
                status="actionable",
                created_at=now,
                updated_at=now,
            ),
        ],
        updated_at=now,
    )
    return repository.save(state)


def test_deleting_a_fact_drops_the_persisted_evidence_item(
    memory_storage, evolution_repository,
):
    event = learning_events.record_learning_event(
        event_type="learner_self_reported",
        user_id="learner-1",
        course_id="course-1",
        node_id="objective-1",
        evidence={"statement": "这段没懂"},
    )
    _seed_state_referencing(event["event_id"], repository=evolution_repository)

    before = evolution_repository.load("learner-1", "course-1")
    assert len(before.evidence_items) == 1

    delete_learning_facts(
        user_id="learner-1", scope="event", event_id=event["event_id"],
    )

    after = evolution_repository.load("learner-1", "course-1")
    # 投影确实变了：不留指向已删事实的 EvidenceItem
    assert after.evidence_items == []
    assert not any(
        item.source_id == event["event_id"] for item in after.evidence_items
    )


def test_hypothesis_losing_all_support_expires_instead_of_dangling(
    memory_storage, evolution_repository,
):
    event = learning_events.record_learning_event(
        event_type="learner_self_reported",
        user_id="learner-1",
        course_id="course-1",
        evidence={"statement": "这段没懂"},
    )
    _seed_state_referencing(event["event_id"], repository=evolution_repository)

    delete_learning_facts(
        user_id="learner-1", scope="event", event_id=event["event_id"],
    )

    after = evolution_repository.load("learner-1", "course-1")
    hypothesis = after.hypotheses[0]
    # 失去全部支撑事实的结论不能继续驱动行为，也不能留下悬空引用
    assert hypothesis.support_evidence_ids == []
    assert hypothesis.status == "expired"
    assert hypothesis.confidence == 0.0
    assert "supporting_evidence_deleted" in hypothesis.confidence_reasons


def test_receipt_names_the_projection_it_invalidated(
    memory_storage, evolution_repository,
):
    event = learning_events.record_learning_event(
        event_type="learner_self_reported",
        user_id="learner-1",
        course_id="course-1",
        evidence={"statement": "这段没懂"},
    )
    _seed_state_referencing(event["event_id"], repository=evolution_repository)

    receipt = delete_learning_facts(
        user_id="learner-1", scope="event", event_id=event["event_id"],
    )

    invalidated = receipt["invalidated_projections"]
    assert any(
        item["projection"] == "course_evolution_state"
        and item["course_id"] == "course-1"
        and item["dropped_evidence_count"] == 1
        for item in invalidated
    )


def test_course_wide_deletion_uses_the_same_invalidation_path(
    memory_storage, evolution_repository,
):
    """口径 2：整体删除不另走快路径，投影失效行为必须与单条删除一致。"""
    event = learning_events.record_learning_event(
        event_type="learner_self_reported",
        user_id="learner-1",
        course_id="course-1",
        evidence={"statement": "这段没懂"},
    )
    _seed_state_referencing(event["event_id"], repository=evolution_repository)

    receipt = delete_learning_facts(
        user_id="learner-1", scope="course", course_id="course-1",
    )

    after = evolution_repository.load("learner-1", "course-1")
    assert after.evidence_items == []
    assert after.hypotheses[0].status == "expired"
    assert any(
        item["projection"] == "course_evolution_state"
        for item in receipt["invalidated_projections"]
    )


def test_learner_wide_deletion_also_invalidates_persisted_projections(
    memory_storage, evolution_repository,
):
    event = learning_events.record_learning_event(
        event_type="learner_self_reported",
        user_id="learner-1",
        course_id="course-1",
        evidence={"statement": "这段没懂"},
    )
    _seed_state_referencing(event["event_id"], repository=evolution_repository)

    receipt = delete_learning_facts(user_id="learner-1", scope="learner")

    after = evolution_repository.load("learner-1", "course-1")
    assert after.evidence_items == []
    assert any(
        item["projection"] == "course_evolution_state"
        for item in receipt["invalidated_projections"]
    )


def test_another_learner_projection_is_untouched(
    memory_storage, evolution_repository,
):
    mine = learning_events.record_learning_event(
        event_type="learner_self_reported",
        user_id="learner-1",
        course_id="course-1",
        evidence={"statement": "我的"},
    )
    learning_events.record_learning_event(
        event_type="learner_self_reported",
        user_id="learner-2",
        course_id="course-1",
        evidence={"statement": "别人的"},
    )
    _seed_state_referencing(mine["event_id"], repository=evolution_repository)

    other_now = "2026-08-12T00:00:00+00:00"
    evolution_repository.save(CourseEvolutionState(
        user_id="learner-2",
        course_id="course-1",
        evidence_items=[
            EvidenceItem(
                evidence_id="evi_other",
                user_id="learner-2",
                course_id="course-1",
                source_type="learning_event",
                source_id="evt_other",
                evidence_kind="explicit_comprehension_gap",
                summary="别人的证据",
                strength=0.9,
                anchor=EvidenceAnchor(section_id="objective-1", block_id="block-1"),
                created_at=other_now,
            ),
        ],
        updated_at=other_now,
    ))

    delete_learning_facts(user_id="learner-1", scope="learner")

    other = evolution_repository.load("learner-2", "course-1")
    assert len(other.evidence_items) == 1


def test_learner_model_no_longer_reports_the_deleted_fact(memory_storage):
    """每次请求重算的投影：删除后不该再看到这条事实。"""
    from learner_model import build_learner_model
    from learning_runtime import build_runtime_revision_vector

    event = learning_events.record_learning_event(
        event_type="learner_self_reported",
        user_id="learner-1",
        course_id="course-1",
        node_id="objective-1",
        evidence={"statement": "这段没懂"},
    )

    def model_for(events):
        course = {"course_id": "course-1", "nodes": []}
        # 用真实的运行时修订向量，否则模型修订号不会随事实变化，
        # 断言就退化成"两个空向量相等"这种没有证明力的检查。
        revision_vector = build_runtime_revision_vector(
            course=course,
            events=events,
            snapshot=None,
            records=[],
            attempts=[],
            workflow={},
            continuation={},
        )
        return build_learner_model(
            course,
            user_id="learner-1",
            events=events,
            snapshot=None,
            records=[],
            attempts=[],
            workflow={},
            progress={"nodes": []},
            source_revision_vector=revision_vector,
        )

    before = model_for(learning_events.load_learning_events(user_id="learner-1"))
    assert any(
        item["source_id"] == event["event_id"]
        for item in before["evidence_catalog"]
    )

    delete_learning_facts(
        user_id="learner-1", scope="event", event_id=event["event_id"],
    )

    after = model_for(learning_events.load_learning_events(user_id="learner-1"))
    assert after["evidence_catalog"] == []
    assert after["self_reports"] == []
    # 重算而不是就地改写：源事实变了，模型修订号必须随之改变
    assert after["model_revision_id"] != before["model_revision_id"]
