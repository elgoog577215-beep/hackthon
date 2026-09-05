"""证据范围纠正：不静默改写历史事实。

任务书要求：证据被记到错误范围时须有纠正路径，留审计痕迹，**不得静默改写历史
事实**。所以核心断言是：纠正之后，原事实的原始坐标仍然可查，纠正痕迹可查，
而投影读到的是纠正后的范围。
"""

from __future__ import annotations

import pytest

import learning_events
from learning_scope_corrections import (
    ScopeCorrectionError,
    apply_scope_corrections,
    load_corrected_learning_events,
    record_scope_correction,
)


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
def storage(monkeypatch):
    store = MemoryStorage()
    monkeypatch.setattr(learning_events, "storage", store)
    return store


def _event(**kwargs):
    payload = {
        "event_type": "learner_self_reported",
        "actor": "user",
        "user_id": "learner-1",
        "course_id": "course-wrong",
        "node_id": "node-wrong",
        "evidence": {"statement": "这段没懂"},
    }
    payload.update(kwargs)
    return learning_events.record_learning_event(**payload)


def test_correction_does_not_mutate_the_original_fact(storage):
    """最关键的一条：历史事实不得被改写。"""
    original = _event()

    record_scope_correction(
        user_id="learner-1",
        event_id=original["event_id"],
        corrections={"course_id": "course-right", "node_id": "node-right"},
    )

    stored = next(
        item for item in learning_events.load_learning_events(user_id="learner-1")
        if item["event_id"] == original["event_id"]
    )
    # 账本里的原事实仍然记着当时的坐标
    assert stored["course_id"] == "course-wrong"
    assert stored["node_id"] == "node-wrong"
    assert stored["evidence"]["statement"] == "这段没懂"


def test_correction_is_recorded_as_an_additional_fact(storage):
    original = _event()

    correction = record_scope_correction(
        user_id="learner-1",
        event_id=original["event_id"],
        corrections={"node_id": "node-right"},
        reason_code="misattributed_scope",
    )

    assert correction["event_type"] == "learning_scope_corrected"
    assert correction["result"]["corrected_event_id"] == original["event_id"]
    # 审计痕迹：纠正前的值必须留下
    assert correction["result"]["previous"] == {"node_id": "node-wrong"}
    assert correction["result"]["reason_code"] == "misattributed_scope"


def test_projection_reads_the_corrected_scope(storage):
    original = _event()
    record_scope_correction(
        user_id="learner-1",
        event_id=original["event_id"],
        corrections={"course_id": "course-right", "node_id": "node-right"},
    )

    corrected = apply_scope_corrections(
        learning_events.load_learning_events(user_id="learner-1")
    )
    target = next(
        item for item in corrected if item["event_id"] == original["event_id"]
    )

    # 投影读到纠正后的范围
    assert target["course_id"] == "course-right"
    assert target["node_id"] == "node-right"
    # 但纠正痕迹随投影一起可见，而不是悄悄换掉
    assert target["scope_correction"]["corrected"] is True
    assert target["scope_correction"]["history"][0]["previous"] == {
        "course_id": "course-wrong",
        "node_id": "node-wrong",
    }


def test_uncorrected_facts_carry_no_correction_marker(storage):
    _event()

    corrected = apply_scope_corrections(
        learning_events.load_learning_events(user_id="learner-1")
    )

    assert "scope_correction" not in corrected[0]


def test_loading_by_course_follows_the_correction(storage):
    """被纠正到本课程的证据必须出现在本课程下，否则纠正等于没生效。"""
    original = _event(course_id="course-wrong")
    record_scope_correction(
        user_id="learner-1",
        event_id=original["event_id"],
        corrections={"course_id": "course-right"},
    )

    in_right = load_corrected_learning_events(
        user_id="learner-1", course_id="course-right",
    )
    assert original["event_id"] in {item["event_id"] for item in in_right}

    in_wrong = load_corrected_learning_events(
        user_id="learner-1", course_id="course-wrong",
    )
    assert original["event_id"] not in {item["event_id"] for item in in_wrong}


def test_later_correction_supersedes_the_earlier_one(storage):
    original = _event()
    record_scope_correction(
        user_id="learner-1",
        event_id=original["event_id"],
        corrections={"node_id": "node-second"},
    )
    record_scope_correction(
        user_id="learner-1",
        event_id=original["event_id"],
        corrections={"node_id": "node-third"},
    )

    corrected = apply_scope_corrections(
        learning_events.load_learning_events(user_id="learner-1")
    )
    target = next(
        item for item in corrected if item["event_id"] == original["event_id"]
    )

    assert target["node_id"] == "node-third"
    # 两次纠正都留痕，不是后一次抹掉前一次
    assert target["scope_correction"]["correction_count"] == 2


def test_content_fields_cannot_be_rewritten_through_correction(storage):
    """纠正的是范围，不是内容。允许改内容就等于改写历史。"""
    original = _event()

    with pytest.raises(ScopeCorrectionError):
        record_scope_correction(
            user_id="learner-1",
            event_id=original["event_id"],
            corrections={"evidence": {"statement": "改写后的说法"}},
        )

    with pytest.raises(ScopeCorrectionError):
        record_scope_correction(
            user_id="learner-1",
            event_id=original["event_id"],
            corrections={"result": {"passed": True}},
        )


def test_correcting_another_learners_fact_is_refused(storage):
    other = _event(user_id="learner-2")

    with pytest.raises(ScopeCorrectionError):
        record_scope_correction(
            user_id="learner-1",
            event_id=other["event_id"],
            corrections={"node_id": "node-right"},
        )


def test_empty_or_unknown_correction_is_refused(storage):
    original = _event()

    with pytest.raises(ScopeCorrectionError):
        record_scope_correction(
            user_id="learner-1", event_id=original["event_id"], corrections={},
        )
    with pytest.raises(ScopeCorrectionError):
        record_scope_correction(
            user_id="learner-1",
            event_id=original["event_id"],
            corrections={"totally_unknown_field": "x"},
        )
