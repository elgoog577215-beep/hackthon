"""从学习事实回跳到产生现场——含"来源已变更"的处理。

任务书要求：课程修订会前移，回跳要处理"来源已变更"的情形，不能 404 了事。
所以这里的核心断言是：**块内容被改写、块被删除、甚至节点被删除之后，回跳仍然
给出一个可用落点**，并明确标记来源已变更。
"""

from __future__ import annotations

import pytest

import learning_events
import learning_source_links
from learning_source_links import build_event_source_link


class MemoryStorage:
    """事实账本 + 课程读取。"""

    def __init__(self, course=None):
        import copy

        self.data: dict[str, object] = {}
        self._course = copy.deepcopy(course) if course else None

    def load_data(self, filename):
        import copy

        return copy.deepcopy(self.data.get(filename))

    def save_data(self, filename, value):
        import copy

        self.data[filename] = copy.deepcopy(value)

    def load_course(self, course_id):
        import copy

        if not self._course or self._course.get("course_id") != course_id:
            return {}
        return copy.deepcopy(self._course)

    def set_course(self, course):
        import copy

        self._course = copy.deepcopy(course)


def course_with(content: str, *, node_id="node-1", block_id="block-1"):
    return {
        "course_id": "course-1",
        "course_name": "线性代数",
        "current_course_version_id": "cv-1",
        "nodes": [
            {
                "node_id": node_id,
                "parent_node_id": "root",
                "node_name": "向量",
                "node_level": 2,
                "content_blocks": [
                    {
                        "block_id": block_id,
                        "type": "concept",
                        "title": "向量定义",
                        "content": content,
                        "order": 0,
                    },
                ],
            },
        ],
    }


@pytest.fixture
def storage(monkeypatch):
    store = MemoryStorage(course_with("向量同时具有大小和方向。"))
    monkeypatch.setattr(learning_events, "storage", store)
    monkeypatch.setattr(learning_source_links, "storage", store)
    return store


def _event(storage, **kwargs):
    """记录一条事实，并带上当前正文块的语义锚点。"""
    course = storage.load_course("course-1")
    from content_blocks import project_course_content_blocks

    projected = project_course_content_blocks(course)
    block = projected["nodes"][0]["content_blocks"][0]
    payload = {
        "event_type": "learner_self_reported",
        "actor": "user",
        "user_id": "learner-1",
        "course_id": "course-1",
        "course_version_id": "cv-1",
        "node_id": "node-1",
        "evidence": {
            "statement": "这段没懂",
            "anchor": {
                "block_id": block["block_id"],
                "block_revision_id": block["block_revision_id"],
                "content_fingerprint": block["content_fingerprint"],
            },
        },
    }
    payload.update(kwargs)
    return learning_events.record_learning_event(**payload)


def test_unchanged_source_resolves_exactly(storage):
    event = _event(storage)

    link = build_event_source_link(event)

    assert link["status"] == "exact"
    assert link["source_changed"] is False
    assert link["can_navigate"] is True
    assert link["target"]["node_id"] == "node-1"
    assert link["target"]["block_id"] == "block-1"


def test_revised_block_still_navigates_and_flags_the_change(storage):
    """课程修订前移：块还在但内容改了。必须能跳，且标记来源已变更。"""
    event = _event(storage)
    storage.set_course(course_with("向量是既有大小又有方向的量，并可用坐标表示。"))

    link = build_event_source_link(event)

    assert link["status"] == "updated_block"
    assert link["source_changed"] is True
    # 关键：来源变了不等于无处可去
    assert link["can_navigate"] is True
    assert link["target"]["block_id"] == "block-1"
    assert link["reason_code"] == "source_content_revised"


def test_retired_block_falls_back_to_the_node(storage):
    """块被整个换掉（ID 也变了）：退到节点级落点，而不是失败。"""
    event = _event(storage)
    storage.set_course(course_with("全新的讲法。", block_id="block-99"))

    link = build_event_source_link(event)

    assert link["status"] in {"node_fallback", "fingerprint_remap"}
    assert link["source_changed"] is True
    assert link["can_navigate"] is True
    assert link["target"]["node_id"] == "node-1"


def test_retired_node_falls_back_to_the_course(storage):
    """连节点都不在了：退到课程级落点，仍然不是 404。"""
    event = _event(storage)
    storage.set_course(course_with("另一节的内容。", node_id="node-42", block_id="block-42"))

    link = build_event_source_link(event)

    assert link["status"] == "course_fallback"
    assert link["source_changed"] is True
    assert link["can_navigate"] is True
    assert link["target"]["course_id"] == "course-1"
    assert link["reason_code"] == "source_node_retired_using_course"


def test_deleted_course_reports_unavailable_without_pretending_to_navigate(storage):
    event = _event(storage)
    storage._course = None

    link = build_event_source_link(event)

    assert link["status"] == "unavailable"
    assert link["can_navigate"] is False
    assert link["target"] is None
    # 即便无处可去，也要把当时的坐标交回去，而不是抹掉
    assert link["origin"]["course_id"] == "course-1"
    assert link["origin"]["node_id"] == "node-1"


def test_course_version_move_is_reported_even_when_the_block_matches(storage):
    """块没变但课程版本前移：仍应提示来源已变更。"""
    event = _event(storage, course_version_id="cv-0")

    link = build_event_source_link(event)

    assert link["status"] == "exact"
    assert link["source_changed"] is True
    assert link["reason_code"] == "source_version_moved"


def test_origin_keeps_the_attempt_and_revision_references(storage):
    """回跳要能回到"哪次作答/哪个修订"，不只是哪门课。"""
    event = _event(
        storage,
        event_type="practice_attempt_graded",
        attempt_id="pa_1",
        question_revision_id="qr_1",
        objective_revision_id="lor_1",
    )

    link = build_event_source_link(event)

    assert link["origin"]["attempt_id"] == "pa_1"
    assert link["origin"]["question_revision_id"] == "qr_1"
    assert link["origin"]["objective_revision_id"] == "lor_1"


def test_event_without_anchor_still_resolves_through_its_node(storage):
    """老事实可能没记语义锚点，不能因此失败。"""
    event = learning_events.record_learning_event(
        event_type="node_learning_completed",
        user_id="learner-1",
        course_id="course-1",
        node_id="node-1",
    )

    link = build_event_source_link(event)

    assert link["can_navigate"] is True
    assert link["target"]["node_id"] == "node-1"
