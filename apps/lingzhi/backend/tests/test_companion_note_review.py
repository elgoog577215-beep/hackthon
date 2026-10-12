import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from companion_note_review import review_note


@pytest.mark.parametrize("finding,status", [
    (None, "checked"),
    ({"note_quote": "a scalar has direction", "source_quote": "a scalar has magnitude only", "explanation": "Check the distinction."}, "checked"),
    ({"note_quote": "invented evidence", "source_quote": "a scalar has magnitude only", "explanation": "Wrong."}, "unavailable"),
    ([], "unavailable"),
])
def test_requires_exact_source_and_note_evidence(finding, status):
    service = SimpleNamespace(_call_llm=AsyncMock(return_value=json.dumps({"finding": finding})))
    result = asyncio.run(review_note({"content": "I think a scalar has direction."}, "a scalar has magnitude only", language="en", service=service))
    assert result["status"] == status
    if status != "checked":
        assert result["finding"] is None


def test_missing_source_does_not_call_model():
    service = SimpleNamespace(_call_llm=AsyncMock())
    result = asyncio.run(review_note({"content": "Some note"}, "", language="zh", service=service))
    assert result["status"] == "insufficient_context"
    service._call_llm.assert_not_called()


def test_failure_is_not_pass():
    service = SimpleNamespace(_call_llm=AsyncMock(side_effect=TimeoutError()))
    result = asyncio.run(review_note({"content": "Some note"}, "Some source", language="zh", service=service))
    assert result == {"status": "unavailable", "finding": None}


def test_record_scope_and_revision_checked_before_model(monkeypatch):
    from routers import learning_records as routes
    course = {"course_id": "c", "current_course_version_id": "v1", "nodes": []}
    monkeypatch.setattr(routes, "get_course_or_404", AsyncMock(return_value=course))
    monkeypatch.setattr(routes.learning_record_repository, "list", lambda user, course: [] if user == "other" else [{"record_id": "n", "revision": 2}])
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    payload = {"expected_revision": 1, "course_version_id": "v1"}
    assert client.post('/courses/c/learning-records/n/companion-review', json=payload, headers={"X-User-Id": "other"}).status_code == 404
    assert client.post('/courses/c/learning-records/n/companion-review', json=payload, headers={"X-User-Id": "owner"}).status_code == 409
    assert client.post('/courses/c/learning-records/n/companion-review', json=payload).status_code == 400
