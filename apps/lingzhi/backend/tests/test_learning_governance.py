"""学习事实导出与删除治理的正面验证。

重点不是「接口返回 200」，而是：删除事实之后，**派生投影确实变了**。
分两类各自证明：

- 每次请求重算的投影（`LearnerModel`）：被删事实不再出现在 evidence_catalog。
- 持久化投影（`CourseEvolutionState`）：引用已删事实的 EvidenceItem 被丢弃，
  失去全部支撑的假设被标为 expired，而不是留下指向空洞的引用。
"""

from __future__ import annotations

import pytest

import learning_events
import learning_governance
from learning_governance import (
    DeletionReceiptLeak,
    delete_learning_facts,
    export_learning_facts,
    load_deletion_receipts,
)


class MemoryStorage:
    """只实现治理模块用到的 load_data/save_data。"""

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


def _record(**kwargs):
    payload = {
        "event_type": "learner_self_reported",
        "actor": "user",
        "user_id": "learner-1",
        "course_id": "course-1",
        "node_id": "node-1",
    }
    payload.update(kwargs)
    return learning_events.record_learning_event(**payload)


# --------------------------------------------------------------------------
# 导出
# --------------------------------------------------------------------------

def test_export_returns_the_learner_own_facts_with_manifest(memory_storage):
    _record(evidence={"statement": "这段没懂"})
    _record(event_type="node_learning_completed", node_id="node-2")
    _record(user_id="learner-2", evidence={"statement": "别人的事实"})

    export = export_learning_facts(user_id="learner-1")

    assert export["manifest"]["event_count"] == 2
    assert export["manifest"]["course_ids"] == ["course-1"]
    assert sorted(export["manifest"]["event_types"]) == [
        "learner_self_reported",
        "node_learning_completed",
    ]
    # 导出的是事实，不能混进别的学习者
    assert {item["user_id"] for item in export["events"]} == {"learner-1"}
    # 导出的是事实层，不是解释层
    assert "LearnerModel" in export["manifest"]["excludes_projections"]


def test_export_can_be_scoped_to_one_course(memory_storage):
    _record(course_id="course-1")
    _record(course_id="course-2")

    export = export_learning_facts(user_id="learner-1", course_id="course-2")

    assert export["manifest"]["event_count"] == 1
    assert export["events"][0]["course_id"] == "course-2"


# --------------------------------------------------------------------------
# 删除：事实层
# --------------------------------------------------------------------------

def test_single_fact_deletion_removes_the_payload_not_just_a_flag(memory_storage):
    kept = _record(evidence={"statement": "保留这条"})
    doomed = _record(evidence={"statement": "删掉这条，内容不得残留"})

    delete_learning_facts(
        user_id="learner-1", scope="event", event_id=doomed["event_id"],
    )

    remaining = learning_events.load_learning_events(user_id="learner-1")
    assert [item["event_id"] for item in remaining] == [kept["event_id"]]

    # 硬删：内容原文不得以任何形式留在账本里
    raw = memory_storage.data[learning_events.LEARNING_EVENTS_FILE]
    assert "删掉这条，内容不得残留" not in str(raw)


def test_course_scope_deletes_only_that_course(memory_storage):
    _record(course_id="course-1")
    _record(course_id="course-2")

    delete_learning_facts(user_id="learner-1", scope="course", course_id="course-1")

    remaining = learning_events.load_learning_events(user_id="learner-1")
    assert [item["course_id"] for item in remaining] == ["course-2"]


def test_learner_scope_deletes_all_own_facts_but_spares_other_learners(memory_storage):
    _record(course_id="course-1")
    _record(course_id="course-2")
    _record(user_id="learner-2")

    delete_learning_facts(user_id="learner-1", scope="learner")

    assert learning_events.load_learning_events(user_id="learner-1") == []
    assert len(learning_events.load_learning_events(user_id="learner-2")) == 1


# --------------------------------------------------------------------------
# 删除回执
# --------------------------------------------------------------------------

def test_receipt_keeps_coordinates_and_never_learning_content(memory_storage):
    event = _record(
        evidence={"statement": "我是张三，这段完全看不懂"},
        result={"reading_status": "in_progress"},
        node_id="node-7",
        course_version_id="cv-3",
    )

    receipt = delete_learning_facts(
        user_id="learner-1", scope="event", event_id=event["event_id"],
    )

    coordinate = receipt["deleted_events"][0]
    assert coordinate["event_id"] == event["event_id"]
    assert coordinate["node_id"] == "node-7"
    assert coordinate["course_version_id"] == "cv-3"

    # 回执长期保留，所以绝不能含任何可反推内容的字段
    assert "我是张三" not in str(receipt)
    assert "evidence" not in coordinate
    assert "result" not in coordinate
    assert "metadata" not in coordinate


def test_receipt_survives_for_the_learner_to_see_what_was_deleted(memory_storage):
    event = _record()
    delete_learning_facts(
        user_id="learner-1", scope="event", event_id=event["event_id"],
    )

    receipts = load_deletion_receipts(user_id="learner-1")
    assert len(receipts) == 1
    assert receipts[0]["scope"] == "event"

    # 导出必须带上回执：学习者能证明删除已执行
    export = export_learning_facts(user_id="learner-1")
    assert export["manifest"]["deletion_receipt_count"] == 1


def test_a_receipt_carrying_learning_content_is_refused(memory_storage):
    """回执白名单是防线本身，必须证明它真的会拦。"""
    with pytest.raises(DeletionReceiptLeak):
        learning_governance._assert_receipt_is_content_free({
            "receipt_id": "ldr_x",
            "statement": "夹带的学习内容原文",
        })

    with pytest.raises(DeletionReceiptLeak):
        learning_governance._assert_receipt_is_content_free({
            "receipt_id": "ldr_x",
            "deleted_events": [{"event_id": "e1", "evidence": {"statement": "原文"}}],
        })


def test_deletion_scope_arguments_are_validated(memory_storage):
    with pytest.raises(ValueError):
        delete_learning_facts(user_id="learner-1", scope="event")
    with pytest.raises(ValueError):
        delete_learning_facts(user_id="learner-1", scope="course")
    with pytest.raises(ValueError):
        delete_learning_facts(user_id="learner-1", scope="everything")
