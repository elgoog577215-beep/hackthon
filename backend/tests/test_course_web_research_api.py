"""课程工作台联网调研：查询可见、来源可复核、选中后进入课程资料链。"""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_repository import CourseDocumentRepository  # noqa: E402
from routers import courses  # noqa: E402


class MemoryStorage:
    def __init__(self) -> None:
        self.course = {
            "course_id": "course-1",
            "course_name": "高等数学",
            "authoring_surface": "teacher",
            "owner_id": "teacher-1",
        }

    def load_course(self, _course_id: str) -> dict:
        return deepcopy(self.course)

    async def save_course(self, _course_id: str, data: dict) -> None:
        self.course = deepcopy(data)


class FakeGateway:
    async def retrieve(self, request):
        assert request.purpose == "course"
        assert request.enabled is True
        matched_query = str(request.queries[0])
        return {
            "schema_version": "retrieval_package_v1",
            "status": "completed",
            "provider": "searxng",
            "queries": list(request.queries),
            "sources": [{
                "source_id": "src-openstax",
                "url": "https://openstax.org/books/calculus/pages/1-introduction",
                "canonical_url": "https://openstax.org/books/calculus/pages/1-introduction",
                "domain": "openstax.org",
                "title": "Calculus introduction",
                "excerpt": "微积分用极限、导数和积分研究连续变化，这是经网关清洗的公开资料摘要。" * 5,
                "published_date": "2024-01-02",
                "retrieved_at": "2026-08-23T00:00:00+00:00",
                "content_hash": "hash-openstax",
                "provider": "searxng",
                "matched_query": matched_query,
                "relevance": 0.94,
                "trust_tier": "tier_a",
                "license": "CC BY",
                "reuse_policy": "verbatim_allowed",
                "accepted_for_generation": True,
            }],
            "rejected_sources": [{"source_id": "low-1"}],
            "errors": [],
            "retrieved_at": "2026-08-23T00:00:00+00:00",
            "package_hash": "pkg-1",
            "receipt": {"status": "completed", "source_count": 1},
        }


class FakeCourseSpace:
    def __init__(self) -> None:
        self.package = {
            "package_id": "tcs-12345678",
            "course_id": "course-1",
            "owner_id": "teacher-1",
            "assets": [],
        }

    def list_owned(self, owner_id: str, course_id: str):
        assert (owner_id, course_id) == ("teacher-1", "course-1")
        return [{"package_id": self.package["package_id"]}]

    def load_owned(self, package_id: str, owner_id: str):
        assert package_id == self.package["package_id"]
        assert owner_id == "teacher-1"
        return self.package

    def register_material_reference(self, owner_id: str, asset, *, package):
        assert owner_id == "teacher-1"
        return {
            "package_id": package["package_id"],
            "asset_id": "tca-web-source",
            "filename": asset.filename,
            "relative_path": f"00-资料收集箱/{asset.filename}",
        }


class FakeMaterialRepository:
    asset = SimpleNamespace(
        asset_id="mat-web-source",
        filename="web-01-openstax.org.md",
        size_bytes=512,
        uploaded_at="2026-08-23T00:00:00+00:00",
    )

    def get_asset(self, asset_id: str):
        return self.asset if asset_id == self.asset.asset_id else None

    def public_asset(self, asset):
        return {
            "asset_id": asset.asset_id,
            "filename": asset.filename,
            "size_bytes": asset.size_bytes,
            "uploaded_at": asset.uploaded_at,
        }


def _client(monkeypatch) -> tuple[TestClient, MemoryStorage]:
    storage = MemoryStorage()
    repository = CourseDocumentRepository(storage)

    async def _course(_course_id: str) -> dict:
        return storage.load_course(_course_id)

    async def _prepare(**kwargs):
        candidate = kwargs["web_search_report"]["candidates"][0]
        assert candidate["content_status"] == "full_text"
        assert "网页完整正文" in candidate["document_text"]
        return {
            "material_assets": [{
                "asset_id": "mat-web-source",
                "filename": "web-01-openstax.org.md",
                "size_bytes": 512,
                "uploaded_at": "2026-08-23T00:00:00+00:00",
            }],
            "material_bindings": [{
                "asset_id": "mat-web-source",
                "reuse_policy": "verbatim_allowed",
                "rights_basis": "open_license",
                "source_metadata": {
                    "origin": "web_search",
                    "source_id": candidate["source_id"],
                    "url": candidate["url"],
                    "domain": candidate["domain"],
                    "credibility": candidate["credibility"],
                },
            }],
        }

    async def _enrich(candidates):
        enriched = deepcopy(candidates)
        enriched[0].update({
            "source_type": "academic",
            "content_status": "full_text",
            "content_type": "text/html",
            "document_text": "# 导数\n\n这是网页完整正文，用于验证深读内容进入原资料链。" * 20,
            "document": {
                "schema_version": "web_document_v1",
                "url": enriched[0]["url"],
                "title": enriched[0]["title"],
                "author": "OpenStax",
                "headings": ["导数"],
                "content_type": "text/html",
                "extractor": "builtin_article_html",
                "fetched_at": "2026-08-23T00:00:01+00:00",
                "content_hash": "full-hash",
                "text_length": 600,
                "warnings": [],
            },
        })
        return enriched

    monkeypatch.setattr(courses, "get_course_or_404", _course)
    monkeypatch.setattr(
        courses,
        "configured_retrieval_gateway",
        lambda _actor: (FakeGateway(), {"provider": "searxng", "enabled_for_user": True}),
    )
    monkeypatch.setattr(courses, "prepare_course_materials", _prepare)
    monkeypatch.setattr(courses, "enrich_web_candidates", _enrich)
    monkeypatch.setattr(courses, "teacher_course_space_repository", FakeCourseSpace())
    monkeypatch.setattr(courses, "material_repository", FakeMaterialRepository())

    app = FastAPI()
    app.include_router(courses.router, prefix="/api")
    app.dependency_overrides[courses.get_course_document_repository] = lambda: repository
    return TestClient(app), storage


def test_research_session_is_reviewable_and_selected_source_becomes_course_reference(monkeypatch):
    client, storage = _client(monkeypatch)
    headers = {"X-User-Id": "teacher-1"}

    searched = client.post(
        "/api/courses/course-1/web-research/search",
        headers=headers,
        json={
            "brief": "查找李老师教材中对导数的公开讲解",
            "stage": "lesson",
            "lesson_id": "L1-1",
        },
    )
    assert searched.status_code == 200
    session = searched.json()
    assert session["queries"]
    assert session["results"][0]["source_id"] == "src-openstax"
    assert session["results"][0]["content_status"] == "full_text"
    assert session["research_summary"]["full_text_count"] == 1
    assert session["research_summary"]["query_coverage"][0]["status"] == "covered"
    assert session["pipeline"]["stage"] == "review"
    assert session["rejected_count"] == 1

    selected = client.put(
        f"/api/courses/course-1/web-research/{session['session_id']}",
        headers=headers,
        json={"selected_source_ids": ["src-openstax"]},
    )
    assert selected.status_code == 200
    reference = selected.json()["accepted_references"][0]
    assert reference["origin"] == "web_search"
    assert reference["material_asset_id"] == "mat-web-source"
    assert reference["source_metadata"]["url"].startswith("https://openstax.org/")

    reloaded = client.get(
        "/api/courses/course-1/web-research",
        headers=headers,
        params={"stage": "lesson", "lesson_id": "L1-1"},
    )
    assert reloaded.status_code == 200
    assert reloaded.json()["accepted_references"][0]["asset_id"] == "tca-web-source"
    assert storage.course["course_web_research_v1"]["sessions"][0]["selected_source_ids"] == ["src-openstax"]


def test_research_write_is_hidden_from_another_teacher(monkeypatch):
    client, _ = _client(monkeypatch)
    hidden_read = client.get(
        "/api/courses/course-1/web-research",
        headers={"X-User-Id": "teacher-2"},
    )
    assert hidden_read.status_code == 404
    response = client.post(
        "/api/courses/course-1/web-research/search",
        headers={"X-User-Id": "teacher-2"},
        json={"brief": "查找导数资料"},
    )
    assert response.status_code == 404
