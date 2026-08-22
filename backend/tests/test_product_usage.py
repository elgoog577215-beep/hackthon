"""UsageEvent contract, retention, aggregation, and governance tests."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import product_usage
from routers import usage_events


class MemoryStorage:
    def __init__(self):
        self.data: dict[str, object] = {}

    def load_data(self, filename):
        return deepcopy(self.data.get(filename))

    def save_data(self, filename, value):
        self.data[filename] = deepcopy(value)


@pytest.fixture
def memory_storage(monkeypatch):
    value = MemoryStorage()
    monkeypatch.setattr(product_usage, "storage", value)
    return value


@pytest.fixture
async def client(memory_storage):
    app = FastAPI()
    app.include_router(usage_events.router, prefix="/api")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as value:
        yield value


def _event(
    client_event_id: str,
    *,
    event_name: str = "page_viewed",
    properties: dict | None = None,
    client_occurred_at: str = "2026-08-20T12:00:00Z",
) -> dict:
    if properties is None:
        properties = {"navigation_kind": "route"}
    return {
        "client_event_id": client_event_id,
        "event_name": event_name,
        "session_id": "usage-session-1",
        "surface": "learner",
        "route_name": "learning",
        "course_id": "course-1",
        "properties": properties,
        "client_occurred_at": client_occurred_at,
    }


def test_append_is_idempotent_per_user_and_client_event(memory_storage):
    first = product_usage.append_usage_events(
        user_id="learner-1", events=[_event("client-event-1")],
    )
    retry = product_usage.append_usage_events(
        user_id="learner-1", events=[_event("client-event-1")],
    )
    other_user = product_usage.append_usage_events(
        user_id="learner-2", events=[_event("client-event-1")],
    )

    assert first["accepted"] == 1
    assert retry["duplicates"] == 1
    assert retry["items"][0]["event_id"] == first["items"][0]["event_id"]
    assert other_user["accepted"] == 1
    assert len(product_usage.load_usage_events()) == 2


def test_server_side_collection_switch_drops_without_persisting(memory_storage, monkeypatch):
    monkeypatch.setenv("LINGZHI_USAGE_TRACKING_ENABLED", "false")

    result = product_usage.append_usage_events(
        user_id="learner-1", events=[_event("disabled-event")],
    )

    assert result["status"] == "disabled"
    assert result["dropped"] == 1
    assert product_usage.load_usage_events() == []


@pytest.mark.parametrize("properties", [
    {"navigation_kind": "route", "page_title": "private title"},
    {"navigation_kind": {"nested": "private content"}},
])
def test_unregistered_or_nested_content_is_rejected(memory_storage, properties):
    with pytest.raises(ValueError):
        product_usage.append_usage_events(
            user_id="learner-1",
            events=[_event("client-event-private", properties=properties)],
        )
    assert product_usage.load_usage_events() == []


def test_api_templates_reject_queries_and_failure_status_mismatch(memory_storage):
    with pytest.raises(ValueError):
        product_usage.append_usage_events(
            user_id="learner-1",
            events=[_event(
                "client-event-query",
                event_name="api_action_completed",
                properties={
                    "method": "POST",
                    "route_template": "/api/courses/:course_id?secret=value",
                    "status_code": 200,
                    "duration_ms": 20,
                },
            )],
        )
    with pytest.raises(ValueError):
        product_usage.append_usage_events(
            user_id="learner-1",
            events=[_event(
                "client-event-status",
                event_name="api_action_failed",
                properties={
                    "method": "POST",
                    "route_template": "/api/courses/:course_id",
                    "status_code": 201,
                    "duration_ms": 20,
                },
            )],
        )


def test_retention_and_capacity_are_enforced_on_append(memory_storage, monkeypatch):
    now = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    memory_storage.data[product_usage.USAGE_EVENTS_FILE] = [{
        "event_id": "expired",
        "client_event_id": "expired-client",
        "event_name": "page_viewed",
        "user_id": "learner-1",
        "session_id": "old-session",
        "received_at": (now - timedelta(days=181)).isoformat(),
    }]
    monkeypatch.setattr(product_usage, "maximum_records", lambda: 3)

    product_usage.append_usage_events(
        user_id="learner-1",
        events=[_event(f"client-event-{index}") for index in range(5)],
        now=now,
    )

    stored = product_usage.load_usage_events()
    assert len(stored) == 3
    assert {item["client_event_id"] for item in stored} == {
        "client-event-2", "client-event-3", "client-event-4",
    }
    assert all(item["event_id"] != "expired" for item in stored)


def test_summary_uses_server_receipt_time_and_action_outcomes(memory_storage):
    now = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    product_usage.append_usage_events(
        user_id="learner-1",
        now=now,
        events=[
            _event("page", client_occurred_at="2000-01-01T00:00:00Z"),
            _event(
                "success",
                event_name="api_action_completed",
                properties={
                    "method": "POST",
                    "route_template": "/api/courses/:course_id/learning-progress/nodes/:node_id",
                    "status_code": 200,
                    "duration_ms": 30,
                },
            ),
            _event(
                "failure",
                event_name="api_action_failed",
                properties={
                    "method": "DELETE",
                    "route_template": "/api/courses/:course_id",
                    "status_code": 500,
                    "duration_ms": 80,
                },
            ),
        ],
    )

    summary = product_usage.summarize_usage_events(days=1, now=now)
    assert summary["metrics"] == {
        "meaningful_active_users": 1,
        "meaningful_active_sessions": 1,
        "page_views": 1,
        "successful_actions": 1,
        "failed_actions": 1,
        "action_success_rate": 0.5,
        "client_errors": 0,
        "total_events": 3,
    }
    assert summary["daily"][0]["date"] == "2026-08-22"


def test_export_and_delete_are_isolated_by_identity(memory_storage):
    product_usage.append_usage_events(user_id="learner-1", events=[_event("one")])
    product_usage.append_usage_events(user_id="learner-2", events=[_event("two")])

    exported = product_usage.export_usage_events(user_id="learner-1")
    receipt = product_usage.delete_usage_events(user_id="learner-1")

    assert exported["manifest"]["event_count"] == 1
    assert {item["user_id"] for item in exported["events"]} == {"learner-1"}
    assert receipt["deleted_event_count"] == 1
    assert product_usage.load_usage_events(user_id="learner-1") == []
    assert len(product_usage.load_usage_events(user_id="learner-2")) == 1


@pytest.mark.asyncio
async def test_routes_require_identity_and_keep_raw_events_private(client):
    missing = await client.post("/api/usage-events/batch", json={"events": [_event("one")]})
    assert missing.status_code == 400

    accepted = await client.post(
        "/api/usage-events/batch",
        headers={"X-User-Id": "learner-1"},
        json={"events": [_event("one")]},
    )
    assert accepted.status_code == 200
    summary = await client.get(
        "/api/usage-events/summary",
        headers={"X-User-Id": "learner-1"},
    )
    assert summary.status_code == 200
    assert summary.json()["metrics"]["page_views"] == 1

    other_export = await client.get(
        "/api/usage-events/export",
        headers={"X-User-Id": "learner-2"},
    )
    assert other_export.json()["manifest"]["event_count"] == 0


@pytest.mark.asyncio
async def test_delete_route_requires_explicit_confirmation(client):
    await client.post(
        "/api/usage-events/batch",
        headers={"X-User-Id": "learner-1"},
        json={"events": [_event("one")]},
    )
    rejected = await client.post(
        "/api/usage-events/delete",
        headers={"X-User-Id": "learner-1"},
        json={"confirmation": "yes"},
    )
    assert rejected.status_code == 422
    deleted = await client.post(
        "/api/usage-events/delete",
        headers={"X-User-Id": "learner-1"},
        json={"confirmation": "delete_my_usage_events"},
    )
    assert deleted.json()["deleted_event_count"] == 1


@pytest.mark.asyncio
async def test_admin_summary_is_disabled_or_token_protected(client, monkeypatch):
    monkeypatch.delenv("LINGZHI_ANALYTICS_ADMIN_TOKEN", raising=False)
    disabled = await client.get("/api/usage-events/admin/summary")
    assert disabled.status_code == 404

    monkeypatch.setenv("LINGZHI_ANALYTICS_ADMIN_TOKEN", "analytics-secret")
    denied = await client.get(
        "/api/usage-events/admin/summary",
        headers={"X-Analytics-Admin-Token": "wrong"},
    )
    assert denied.status_code == 403
    allowed = await client.get(
        "/api/usage-events/admin/summary",
        headers={"X-Analytics-Admin-Token": "analytics-secret"},
    )
    assert allowed.status_code == 200
    assert "events" not in allowed.json()
