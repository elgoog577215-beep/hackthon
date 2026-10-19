"""Explicit course grants; course content and learner facts keep their owners."""

from __future__ import annotations

from datetime import datetime, timezone
from contextvars import ContextVar
from urllib.parse import unquote
from uuid import uuid4

LEARNER_DOMAINS = frozenset(
    {
        "learning-progress",
        "learning-snapshot",
        "learner-model",
        "learning-runtime",
        "learning-continuation",
        "learning-records",
        "learning-assets",
        "practice",
        "review",
        "personal-adaptation",
    }
)
learner_request_course = ContextVar("learner_request_course", default="")


def learner_api_allowed(path: str, method: str = "GET") -> bool:
    parts = [unquote(p) for p in path.split("/") if p]
    read = method.upper() in {"GET", "HEAD"}
    if parts[:2] == ["api", "study"]:
        return True
    if parts[:2] == ["api", "ai-teacher"] or path == "/api/ask_events":
        return True
    if parts[:2] != ["api", "courses"] or len(parts) < 3:
        return path in {"/api/usage-events", "/api/usage-events/batch"} and method.upper() == "POST"
    if len(parts) == 3:
        return read
    if parts[3] in LEARNER_DOMAINS:
        return True
    return read and len(parts) == 4 and parts[3] in {"document", "knowledge-first"}


class CourseLearningAccess:
    def __init__(self, storage):
        self.storage = storage

    def records(self) -> dict:
        return self.storage.load_data("course_learning_access.json") or {}

    def active(self, course: dict, learner_id: str) -> dict | None:
        grant = self.records().get(str(course.get("course_id")), {}).get(learner_id)
        if grant and grant.get("status") == "active" and grant.get("owner_id") == course.get("owner_id"):
            return grant
        return None

    def list(self, course_id: str) -> list[dict]:
        return list(self.records().get(course_id, {}).values())

    def grant(self, course: dict, learner_id: str, *, label: str = "") -> dict:
        result = {}

        def update(current):
            current = current or {}
            grants = current.setdefault(course["course_id"], {})
            old = grants.get(learner_id, {})
            now = datetime.now(timezone.utc).isoformat()
            grant = {
                "grant_id": old.get("grant_id") or str(uuid4()),
                "course_id": course["course_id"],
                "owner_id": course["owner_id"],
                "learner_id": learner_id,
                "label": label or old.get("label", learner_id),
                "status": "active",
                "created_at": old.get("created_at") or now,
                "updated_at": now,
                "permissions": ["read", "practice", "derive"],
            }
            grants[learner_id] = grant
            result.update(grant)
            return current

        self.storage.update_data("course_learning_access.json", update)
        return result

    def revoke(self, course_id: str, learner_id: str) -> dict:
        result = {}

        def update(current):
            current = current or {}
            grant = current.get(course_id, {}).get(learner_id)
            if not grant:
                raise KeyError(learner_id)
            grant.update(status="revoked", updated_at=datetime.now(timezone.utc).isoformat())
            result.update(grant)
            return current

        self.storage.update_data("course_learning_access.json", update)
        return result


def trusted_student(request) -> bool:
    identity = getattr(request.state, "qizhi_identity", None)
    return bool(getattr(identity, "role", "") == "student" or getattr(request.state, "local_study_identity", None))
