from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dependencies import require_task_manager
from routers import course_versions


class PreviewManager:
    def __init__(self):
        self.calls = []

    async def preview_outline_adjustment(self, course_id, payload):
        self.calls.append((course_id, payload))
        return {
            "proposal_id": "proposal-1",
            "source_draft_revision_id": payload["expected_draft_revision_id"],
            "operations": [],
            "summary": "未改变目录",
            "diff": {"added": [], "removed": [], "moved": [], "updated": []},
            "draft": {"nodes": []},
            "impact_report": {},
            "constraint_report": {"chapter_count": 1, "section_count": 1},
            "can_apply": True,
            "blocking_issues": [],
            "warnings": [],
        }


def test_preview_endpoint_passes_optimistic_revisions_without_writing(monkeypatch):
    manager = PreviewManager()
    app = FastAPI()
    app.include_router(course_versions.router, prefix="/api")
    app.dependency_overrides[require_task_manager] = lambda: manager
    client = TestClient(app)

    response = client.post(
        "/api/courses/course-1/blueprint/adjustments/preview",
        json={
            "request_id": "request-1",
            "base_blueprint_revision_id": "bp-1",
            "expected_draft_revision_id": "draft-1",
            "instruction": "把生命周期移到工程实践章，并新增一节组件组合",
        },
    )

    assert response.status_code == 200
    assert response.json()["proposal_id"] == "proposal-1"
    assert manager.calls == [
        (
            "course-1",
            {
                "request_id": "request-1",
                "base_blueprint_revision_id": "bp-1",
                "expected_draft_revision_id": "draft-1",
                "instruction": "把生命周期移到工程实践章，并新增一节组件组合",
            },
        )
    ]


def test_preview_instruction_contract_rejects_blank_and_oversized_input():
    manager = PreviewManager()
    app = FastAPI()
    app.include_router(course_versions.router, prefix="/api")
    app.dependency_overrides[require_task_manager] = lambda: manager
    client = TestClient(app)

    blank = client.post(
        "/api/courses/course-1/blueprint/adjustments/preview",
        json={
            "request_id": "request-blank",
            "base_blueprint_revision_id": "bp-1",
            "expected_draft_revision_id": "draft-1",
            "instruction": "   ",
        },
    )
    oversized = client.post(
        "/api/courses/course-1/blueprint/adjustments/preview",
        json={
            "request_id": "request-long",
            "base_blueprint_revision_id": "bp-1",
            "expected_draft_revision_id": "draft-1",
            "instruction": "调" * 3001,
        },
    )

    assert blank.status_code == 422
    assert oversized.status_code == 422
    assert manager.calls == []
