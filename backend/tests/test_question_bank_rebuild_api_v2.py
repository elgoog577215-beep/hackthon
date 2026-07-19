from __future__ import annotations

import asyncio
from copy import deepcopy

from fastapi import FastAPI
from fastapi.testclient import TestClient

from question_bank_jobs import QuestionBankRebuildJobRepository
from routers import question_bank


class CapturingExecutor:
    def __init__(self) -> None:
        self.submissions: list[dict] = []

    def submit(
        self,
        *,
        job_id: str,
        course_id: str,
        payload,
        course: dict,
    ) -> None:
        self.submissions.append({
            "job_id": job_id,
            "course_id": course_id,
            "payload": payload.model_dump(),
            "course": deepcopy(course),
        })


def _client(monkeypatch, tmp_path):
    course = {
        "course_id": "course-jobs",
        "course_name": "跨学科课程",
        "nodes": [{
            "node_id": "node-1",
            "node_level": 2,
            "node_name": "节点一",
        }, {
            "node_id": "node-2",
            "node_level": 2,
            "node_name": "节点二",
        }],
    }

    async def get_course(course_id: str):
        return {**deepcopy(course), "course_id": course_id}

    jobs = QuestionBankRebuildJobRepository(tmp_path / "jobs")
    executor = CapturingExecutor()
    monkeypatch.setattr(
        question_bank,
        "question_bank_rebuild_job_repository",
        jobs,
    )
    monkeypatch.setattr(
        question_bank,
        "question_bank_rebuild_executor",
        executor,
    )
    monkeypatch.setattr(
        question_bank,
        "get_course_or_404",
        get_course,
    )
    app = FastAPI()
    app.include_router(question_bank.router, prefix="/api")
    return TestClient(app), jobs, executor


def test_rebuild_executor_reuses_one_event_loop_across_jobs(
    monkeypatch,
):
    loop_ids: list[int] = []
    shared_lock = asyncio.Lock()

    async def fake_run_rebuild_job(**_kwargs):
        async with shared_lock:
            loop_ids.append(id(asyncio.get_running_loop()))
            await asyncio.sleep(0.01)

    monkeypatch.setattr(
        question_bank,
        "_run_rebuild_job",
        fake_run_rebuild_job,
    )
    executor = question_bank.QuestionBankRebuildExecutor(
        max_workers=2,
    )
    try:
        futures = [
            executor.submit(
                job_id=f"job-{index}",
                course_id="course-jobs",
                payload=None,
                course={"course_id": "course-jobs"},
            )
            for index in range(3)
        ]
        for future in futures:
            future.result(timeout=2)
    finally:
        executor.shutdown()

    assert len(loop_ids) == 3
    assert len(set(loop_ids)) == 1


def test_rebuild_api_creates_real_job_and_supports_status_lookup(
    monkeypatch,
    tmp_path,
):
    client, _, executor = _client(monkeypatch, tmp_path)

    created = client.post(
        "/api/courses/course-jobs/question-bank/rebuild",
        headers={"X-User-Id": "teacher-1"},
        json={
            "request_id": "request-api-v2",
            "scope": "nodes",
            "node_ids": ["node-2", "node-1"],
            "mode": "incremental",
        },
    )

    assert created.status_code == 202
    payload = created.json()
    assert payload["schema_version"] == "question_bank_rebuild_job_v1"
    assert payload["status"] == "queued"
    assert payload["job_id"].startswith("qbr_")
    assert payload["scope"] == "nodes"
    assert payload["node_ids"] == ["node-1", "node-2"]
    assert payload["status_url"].endswith(
        f"/question-bank/rebuilds/{payload['job_id']}"
    )
    assert len(executor.submissions) == 1

    status = client.get(
        payload["status_url"],
        headers={"X-User-Id": "teacher-1"},
    )

    assert status.status_code == 200
    assert status.json()["job_id"] == payload["job_id"]
    assert status.json()["stages"] == payload["stages"]


def test_rebuild_api_deduplicates_and_validates_node_scope(
    monkeypatch,
    tmp_path,
):
    client, _, executor = _client(monkeypatch, tmp_path)
    request = {
        "request_id": "request-api-dedup",
        "scope": "course",
        "node_ids": [],
        "mode": "full",
    }

    first = client.post(
        "/api/courses/course-jobs/question-bank/rebuild",
        headers={"X-User-Id": "teacher-1"},
        json=request,
    )
    second = client.post(
        "/api/courses/course-jobs/question-bank/rebuild",
        headers={"X-User-Id": "teacher-1"},
        json=request,
    )
    invalid = client.post(
        "/api/courses/course-jobs/question-bank/rebuild",
        headers={"X-User-Id": "teacher-1"},
        json={
            "request_id": "request-api-invalid",
            "scope": "nodes",
            "node_ids": [],
            "mode": "incremental",
        },
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["job_id"] == first.json()["job_id"]
    assert second.json()["deduplicated"] is True
    assert len(executor.submissions) == 1
    assert invalid.status_code == 422


def test_rebuild_management_requires_identity(monkeypatch, tmp_path):
    client, _, _ = _client(monkeypatch, tmp_path)

    created = client.post(
        "/api/courses/course-jobs/question-bank/rebuild",
        json={
            "request_id": "request-api-auth",
            "scope": "course",
            "node_ids": [],
            "mode": "incremental",
        },
    )

    assert created.status_code == 400


def test_rebuild_api_accepts_item_scope_and_resolves_its_node(
    monkeypatch,
    tmp_path,
):
    client, _, executor = _client(monkeypatch, tmp_path)

    class ItemBank:
        @staticmethod
        def load_bundle(_course_id: str):
            return {
                "course_id": "course-jobs",
                "items": [{
                    "item_id": "item-1",
                    "revision_id": "revision-1",
                    "node_id": "node-1",
                    "node_ids": ["node-1"],
                }],
            }

    monkeypatch.setattr(
        question_bank,
        "question_bank_repository",
        ItemBank(),
    )

    created = client.post(
        "/api/courses/course-jobs/question-bank/rebuild",
        headers={"X-User-Id": "teacher-1"},
        json={
            "request_id": "request-item-rework",
            "scope": "items",
            "revision_ids": ["revision-1"],
            "mode": "incremental",
        },
    )

    assert created.status_code == 202
    assert created.json()["scope"] == "items"
    assert created.json()["revision_ids"] == ["revision-1"]
    assert created.json()["node_ids"] == ["node-1"]
    assert executor.submissions[0]["payload"]["scope"] == "items"
