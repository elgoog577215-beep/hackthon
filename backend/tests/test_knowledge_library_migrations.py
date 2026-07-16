import asyncio

import pytest

from knowledge_library_migrations import (
    KnowledgeLibraryMigrationRepository,
    KnowledgeLibraryMigrationService,
)


class _Storage:
    def list_courses(self):
        return [
            {"course_id": "course-b"},
            {"course_id": "4215dc17-7c34-48ad-91c8-a1b780c0366d"},
            {"course_id": "course-fail"},
        ]


class _CourseRepository:
    storage = _Storage()

    def load_course_view(self, course_id):
        subject = "数据结构" if course_id != "course-fail" else "故障学科"
        return {
            "course_id": course_id,
            "course_name": f"{subject}课程",
            "generation_request": {"subject": subject},
            "nodes": [],
        }


class _LibraryService:
    def __init__(self):
        self.group_calls = []
        self.degraded_calls = []

    async def rebuild_courses(self, course_ids, **kwargs):
        self.group_calls.append(list(course_ids))
        await asyncio.sleep(0)
        if "course-fail" in course_ids:
            raise RuntimeError("isolated failure")
        return [
            {
                "course_id": course_id,
                "library": {
                    "library_id": "cs.data_structures",
                    "revision_id": "sklr_shared",
                    "lifecycle_status": "candidate",
                },
            }
            for course_id in course_ids
        ]

    async def rebuild_course(self, course_id):
        await asyncio.sleep(0)
        if course_id == "course-fail":
            raise RuntimeError("isolated failure")
        return {
            "library": {
                "library_id": "cs.data_structures",
                "revision_id": f"sklr_{course_id}",
                "lifecycle_status": "candidate",
            }
        }

    async def degrade_course_index(self, course_id, *, reason):
        self.degraded_calls.append((course_id, reason))
        return {
            "library": {
                "library_id": f"degraded.{course_id}",
                "revision_id": f"sklr_degraded_{course_id}",
                "lifecycle_status": "degraded",
            },
        }


@pytest.mark.asyncio
async def test_migration_prioritizes_current_course_and_isolates_failures(tmp_path, monkeypatch):
    repository = KnowledgeLibraryMigrationRepository(tmp_path)
    library_service = _LibraryService()
    service = KnowledgeLibraryMigrationService(_CourseRepository(), library_service, repository)
    monkeypatch.setattr("knowledge_library_migrations.threading.Thread.start", lambda _self: None)
    job = service.create_job()

    assert job["course_ids"][0] == "4215dc17-7c34-48ad-91c8-a1b780c0366d"
    assert job["migration_version"] == 3

    await service._run(job["job_id"])
    completed = service.load_job(job["job_id"])

    assert completed["status"] == "completed"
    assert completed["completed_count"] == 2
    assert completed["failed_count"] == 1
    assert next(item for item in completed["results"] if item["course_id"] == "course-fail")["error"] == "isolated failure"
    failed = next(item for item in completed["results"] if item["course_id"] == "course-fail")
    assert failed["lifecycle_status"] == "degraded"
    assert failed["revision_id"] == "sklr_degraded_course-fail"
    assert library_service.degraded_calls == [("course-fail", "isolated failure")]
    assert library_service.group_calls[0] == [
        "4215dc17-7c34-48ad-91c8-a1b780c0366d",
        "course-b",
    ]
    shared = [item for item in completed["results"] if item["status"] == "completed"]
    assert {item["revision_id"] for item in shared} == {"sklr_shared"}


def test_migration_creation_is_idempotent_and_pause_resume_are_persisted(tmp_path, monkeypatch):
    repository = KnowledgeLibraryMigrationRepository(tmp_path)
    service = KnowledgeLibraryMigrationService(_CourseRepository(), _LibraryService(), repository)
    monkeypatch.setattr("knowledge_library_migrations.threading.Thread.start", lambda _self: None)

    first = service.create_job()
    second = service.create_job()
    paused = service.pause_job(first["job_id"])
    resumed = service.resume_job(first["job_id"])

    assert first["job_id"] == second["job_id"]
    assert paused["status"] == "paused"
    assert resumed["status"] == "pending"
