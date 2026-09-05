"""课程联网来源冻结边界。"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_web_research_policy import course_generation_view  # noqa: E402
from routers import courses  # noqa: E402


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(courses.router, prefix="/api")
    return TestClient(app)


def test_all_course_web_research_routes_are_frozen() -> None:
    client = _client()
    requests = [
        client.get("/api/courses/course-1/web-research"),
        client.get("/api/courses/course-1/web-research/capability"),
        client.post(
            "/api/courses/course-1/web-research/search",
            json={"brief": "查找导数资料"},
        ),
        client.put(
            "/api/courses/course-1/web-research/session-1",
            json={"selected_source_ids": ["source-1"]},
        ),
    ]

    for response in requests:
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "course_web_research_frozen"


def test_historical_web_sources_are_excluded_from_new_generation_view() -> None:
    course = {
        "material_bindings": [
            {"asset_id": "material-1", "source_metadata": {"origin": "material"}},
            {"asset_id": "web-1", "source_metadata": {"origin": "web_search"}},
        ],
        "evidence_catalog": [
            {"evidence_id": "e-material", "asset_id": "material-1"},
            {"evidence_id": "e-web", "asset_id": "web-1"},
        ],
        "retrieval_package": {"sources": [{"source_id": "web-source"}]},
        "retrieval_acceptance": {"accepted_source_ids": ["web-source"]},
        "outline_research": {"status": "accepted"},
        "generation_stage_artifacts": {
            "web_retrieval": {"status": "frozen"},
            "assessment_retrieval": {"status": "frozen"},
            "local_artifact": {"status": "ready"},
        },
    }

    view = course_generation_view(course)

    assert [item["asset_id"] for item in view["material_bindings"]] == ["material-1"]
    assert [item["evidence_id"] for item in view["evidence_catalog"]] == ["e-material"]
    assert "retrieval_package" not in view
    assert "retrieval_acceptance" not in view
    assert "outline_research" not in view
    assert "web_retrieval" not in view["generation_stage_artifacts"]
    assert "assessment_retrieval" not in view["generation_stage_artifacts"]
    assert view["generation_stage_artifacts"]["local_artifact"]["status"] == "ready"
    assert "retrieval_package" in course
