import os
import sys
from copy import deepcopy

import pytest
from httpx import ASGITransport, AsyncClient


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))


class MockStorage:
    def __init__(self):
        self.data = {}

    def load_data(self, filename):
        return deepcopy(self.data.get(filename))

    def save_data(self, filename, data):
        self.data[filename] = deepcopy(data)


def test_learning_event_ledger_is_idempotent_and_entity_linked(monkeypatch):
    import learning_events

    storage = MockStorage()
    monkeypatch.setattr(learning_events, "storage", storage)
    payload = {
        "event_type": "learning_record_created",
        "actor": "user",
        "source": "test",
        "user_id": "u1",
        "course_id": "course-1",
        "node_id": "node-1",
        "operation_id": "op-1",
        "idempotency_key": "record-1:create",
        "entity_type": "learning_record",
        "entity_id": "record-1",
        "entity_revision": "1",
    }

    first = learning_events.record_learning_event(**payload)
    second = learning_events.record_learning_event(**payload)

    assert first == second
    assert first["schema_version"] == 8
    assert first["entity_type"] == "learning_record"
    assert first["entity_id"] == "record-1"
    assert len(learning_events.load_learning_events(user_id="u1", course_id="course-1")) == 1


def test_ai_output_quality_assessment_is_not_a_learner_fact(monkeypatch):
    import ai_output_quality
    import learning_events

    storage = MockStorage()
    monkeypatch.setattr(learning_events, "storage", storage)
    assessment = ai_output_quality.assess_ai_output(
        output_type="node_extension",
        output_text="## 例子\n\n用一个具体例子解释左右极限，并给出一道可验证的自测题。",
        context_text="当前课程节点需要补充例子。",
        require_markdown_structure=True,
    )

    assert assessment.passed is True
    assert learning_events.load_learning_events() == []


@pytest.mark.asyncio
async def test_legacy_annotation_and_learning_os_write_routes_are_gone():
    from main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-User-Id": "u1"},
    ) as client:
        annotation = await client.post("/api/annotations", json={
            "node_id": "node-1",
            "course_id": "course-1",
            "question": "User Note",
            "answer": "旧笔记入口不再接受新写入。",
            "source_type": "user",
        })
        learning_os = await client.post("/api/learning-os/block-event", json={
            "course_id": "course-1",
            "node_id": "node-1",
            "block_id": "block-1",
            "action_type": "ask",
        })

    assert annotation.status_code == 404
    assert learning_os.status_code == 404
