"""教师剔除名单的读写端点：保存后能读回，并且真的进入下一轮生成。"""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_repository import CourseDocumentRepository  # noqa: E402
from routers import courses  # noqa: E402
from web_material_curation import (  # noqa: E402
    load_course_exclusions,
    merge_ingest_exclusions,
)


class MemoryStorage:
    def __init__(self, course: dict) -> None:
        self.course = deepcopy(course)

    def load_course(self, _course_id: str) -> dict:
        return deepcopy(self.course)

    async def save_course(self, _course_id: str, data: dict) -> None:
        self.course = deepcopy(data)


def _client(monkeypatch) -> tuple[TestClient, MemoryStorage]:
    storage = MemoryStorage({"course_id": "c1", "course_name": "导数"})
    repository = CourseDocumentRepository(storage)

    # get_course_or_404 是被直接 await 调用的，不走 Depends，
    # 所以 dependency_overrides 对它无效，只能替换模块级符号。
    async def _course(course_id: str) -> dict:
        return storage.load_course(course_id)

    monkeypatch.setattr(courses, "get_course_or_404", _course)

    app = FastAPI()
    app.include_router(courses.router, prefix="/api")
    app.dependency_overrides[courses.get_course_document_repository] = (
        lambda: repository
    )
    return TestClient(app), storage


def test_curation_defaults_to_empty_before_any_edit(monkeypatch):
    client, _ = _client(monkeypatch)
    response = client.get("/api/courses/c1/web-material-curation")
    assert response.status_code == 200
    assert response.json() == {
        "excluded_source_ids": [],
        "excluded_urls": [],
    }


def test_saved_curation_survives_reload(monkeypatch):
    """这正是原实现缺的一环：剔除只存在前端 ref 里，刷新就没了。"""
    client, storage = _client(monkeypatch)
    saved = client.put(
        "/api/courses/c1/web-material-curation",
        json={
            "excluded_source_ids": ["src_mit", "src_mit"],
            "excluded_urls": ["HTTPS://WWW.Example.com/a/"],
        },
    )
    assert saved.status_code == 200
    assert saved.json()["excluded_source_ids"] == ["src_mit"]
    assert saved.json()["excluded_urls"] == ["https://example.com/a"]

    # 重新读（模拟教师刷新页面）
    reloaded = client.get("/api/courses/c1/web-material-curation").json()
    assert reloaded["excluded_source_ids"] == ["src_mit"]
    assert reloaded["excluded_urls"] == ["https://example.com/a"]

    # 并且确实落在了课程元数据里，下一轮生成读得到
    merged = merge_ingest_exclusions({}, load_course_exclusions(storage.course))
    assert "src_mit" in merged["excluded_source_ids"]
