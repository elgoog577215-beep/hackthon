"""Resumable migration jobs for rebuilding each course's private knowledge base."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
from typing import Any

from course_knowledge_rebuild import (
    CourseKnowledgeRebuildError,
    CourseKnowledgeRebuildService,
)
from course_repository import CourseDocumentRepository
from course_versioning import stable_hash
from storage import DATA_DIR


MIGRATION_VERSION = 4


class KnowledgeLibraryMigrationRepository:
    def __init__(self, root_dir: str | Path | None = None) -> None:
        self.root_dir = Path(root_dir or Path(DATA_DIR) / "knowledge_library_migrations")
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def save(self, job: dict[str, Any]) -> dict[str, Any]:
        path = self.root_dir / f"{job['job_id']}.json"
        self._atomic_write(path, job)
        return deepcopy(job)

    def load(self, job_id: str) -> dict[str, Any]:
        path = self.root_dir / f"{job_id}.json"
        if not path.exists():
            raise KeyError(job_id)
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _atomic_write(path: Path, value: dict[str, Any]) -> None:
        temporary = path.with_suffix(".json.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2)
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()


class KnowledgeLibraryMigrationService:
    """Migrate courses independently; no job groups courses by subject."""

    def __init__(
        self,
        course_repository: CourseDocumentRepository,
        rebuild_service: CourseKnowledgeRebuildService | None = None,
        repository: KnowledgeLibraryMigrationRepository | None = None,
    ) -> None:
        self.course_repository = course_repository
        self.rebuild_service = rebuild_service or CourseKnowledgeRebuildService(course_repository)
        self.repository = repository or KnowledgeLibraryMigrationRepository()
        self._threads: dict[str, threading.Thread] = {}

    def create_job(self) -> dict[str, Any]:
        courses = self.course_repository.storage.list_courses()
        course_ids = sorted(
            str(item.get("course_id") or "")
            for item in courses
            if item.get("course_id")
        )
        signature = stable_hash({
            "migration_version": MIGRATION_VERSION,
            "knowledge_scope": "current_course_only",
            "course_ids": course_ids,
        })
        job_id = f"klm_{signature}"
        try:
            existing = self.repository.load(job_id)
            if existing.get("status") in {"pending", "running", "completed"}:
                return existing
        except KeyError:
            pass
        job = {
            "job_id": job_id,
            "schema_version": "knowledge_library_migration_job_v2",
            "migration_version": MIGRATION_VERSION,
            "knowledge_scope": "current_course_only",
            "status": "pending",
            "course_ids": course_ids,
            "completed_count": 0,
            "failed_count": 0,
            "results": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.repository.save(job)
        self._start(job_id)
        return job

    def load_job(self, job_id: str) -> dict[str, Any]:
        return self.repository.load(job_id)

    def pause_job(self, job_id: str) -> dict[str, Any]:
        job = self.repository.load(job_id)
        if job.get("status") in {"pending", "running"}:
            job["status"] = "paused"
            self.repository.save(job)
        return job

    def resume_job(self, job_id: str) -> dict[str, Any]:
        job = self.repository.load(job_id)
        if job.get("status") == "paused":
            job["status"] = "pending"
            self.repository.save(job)
            self._start(job_id)
        return job

    def _start(self, job_id: str) -> None:
        thread = threading.Thread(target=self._run_thread, args=(job_id,), daemon=True)
        self._threads[job_id] = thread
        thread.start()

    def _run_thread(self, job_id: str) -> None:
        asyncio.run(self._run(job_id))

    async def _run(self, job_id: str) -> None:
        job = self.repository.load(job_id)
        job["status"] = "running"
        self.repository.save(job)
        processed_ids = {
            str(item.get("course_id") or "")
            for item in job.get("results") or []
        }
        semaphore = asyncio.Semaphore(2)

        async def migrate_course(course_id: str) -> dict[str, Any]:
            async with semaphore:
                try:
                    rebuilt = await self.rebuild_service.rebuild_course(course_id)
                    knowledge_base = rebuilt.get("course_knowledge_base") or {}
                    return {
                        "course_id": course_id,
                        "status": "completed",
                        "knowledge_base_id": knowledge_base.get("knowledge_base_id"),
                        "revision_id": knowledge_base.get("revision_id"),
                        "lifecycle_status": knowledge_base.get("lifecycle_status"),
                        "reused": bool(rebuilt.get("reused")),
                    }
                except CourseKnowledgeRebuildError as exc:
                    return {
                        "course_id": course_id,
                        "status": "failed",
                        "error": exc.message,
                        "error_code": exc.code,
                        "retryable": exc.retryable,
                    }
                except Exception as exc:
                    return {
                        "course_id": course_id,
                        "status": "failed",
                        "error": str(exc),
                        "error_code": "unexpected_migration_error",
                        "retryable": True,
                    }

        pending_ids = [
            course_id
            for course_id in job.get("course_ids") or []
            if str(course_id) not in processed_ids
        ]
        for offset in range(0, len(pending_ids), 2):
            current = self.repository.load(job_id)
            if current.get("status") == "paused":
                return
            results = await asyncio.gather(*(
                migrate_course(str(course_id))
                for course_id in pending_ids[offset:offset + 2]
            ))
            current["results"] = [*(current.get("results") or []), *results]
            current["completed_count"] = sum(
                item.get("status") == "completed" for item in current["results"]
            )
            current["failed_count"] = sum(
                item.get("status") == "failed" for item in current["results"]
            )
            self.repository.save(current)

        completed = self.repository.load(job_id)
        completed["status"] = "completed"
        completed["completed_at"] = datetime.now(timezone.utc).isoformat()
        self.repository.save(completed)


__all__ = ["KnowledgeLibraryMigrationRepository", "KnowledgeLibraryMigrationService"]
