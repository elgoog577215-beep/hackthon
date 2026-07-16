"""Resumable migration jobs for pinning every current course to a V3 library."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
from typing import Any

from course_repository import CourseDocumentRepository
from course_versioning import stable_hash
from storage import DATA_DIR
from subject_library_service import SubjectLibraryService
from subject_ontology import resolve_subject_identity


MIGRATION_VERSION = 3


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
    def __init__(
        self,
        course_repository: CourseDocumentRepository,
        library_service: SubjectLibraryService,
        repository: KnowledgeLibraryMigrationRepository | None = None,
    ) -> None:
        self.course_repository = course_repository
        self.library_service = library_service
        self.repository = repository or KnowledgeLibraryMigrationRepository()
        self._threads: dict[str, threading.Thread] = {}

    def create_job(self) -> dict[str, Any]:
        courses = self.course_repository.storage.list_courses()
        prioritized = sorted(
            [str(item.get("course_id") or "") for item in courses if item.get("course_id")],
            key=lambda course_id: (course_id != "4215dc17-7c34-48ad-91c8-a1b780c0366d", course_id),
        )
        signature = stable_hash({"migration_version": MIGRATION_VERSION, "course_ids": prioritized})
        job_id = f"klm_{signature}"
        try:
            existing = self.repository.load(job_id)
            if existing.get("status") in {"pending", "running", "completed"}:
                return existing
        except KeyError:
            pass
        subject_groups: list[dict[str, Any]] = []
        groups_by_subject: dict[str, dict[str, Any]] = {}
        for course_id in prioritized:
            try:
                course = self.course_repository.load_course_view(course_id)
                subject_id = resolve_subject_identity(course)["subject_id"]
            except Exception:
                subject_id = f"unresolved.{course_id}"
            group = groups_by_subject.get(subject_id)
            if group is None:
                group = {"subject_id": subject_id, "course_ids": []}
                groups_by_subject[subject_id] = group
                subject_groups.append(group)
            group["course_ids"].append(course_id)
        job = {
            "job_id": job_id,
            "schema_version": "knowledge_library_migration_job_v1",
            "migration_version": MIGRATION_VERSION,
            "status": "pending",
            "course_ids": prioritized,
            "subject_groups": subject_groups,
            "completed_count": 0,
            "failed_count": 0,
            "results": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.repository.save(job)
        thread = threading.Thread(target=self._run_thread, args=(job_id,), daemon=True)
        self._threads[job_id] = thread
        thread.start()
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
            thread = threading.Thread(target=self._run_thread, args=(job_id,), daemon=True)
            self._threads[job_id] = thread
            thread.start()
        return job

    def _run_thread(self, job_id: str) -> None:
        asyncio.run(self._run(job_id))

    async def _run(self, job_id: str) -> None:
        job = self.repository.load(job_id)
        job["status"] = "running"
        self.repository.save(job)
        completed_ids = {str(item.get("course_id")) for item in job.get("results") or []}
        semaphore = asyncio.Semaphore(2)

        async def migrate_group(group: dict[str, Any]) -> list[dict[str, Any]]:
            course_ids = [
                str(course_id)
                for course_id in group.get("course_ids") or []
                if str(course_id) not in completed_ids
            ]
            if not course_ids:
                return []
            async with semaphore:
                try:
                    if hasattr(self.library_service, "rebuild_courses"):
                        rebuilt = await self.library_service.rebuild_courses(
                            course_ids,
                            prefer_curated=True,
                        )
                    else:
                        rebuilt = [
                            {"course_id": course_id, **(await self.library_service.rebuild_course(course_id))}
                            for course_id in course_ids
                        ]
                    by_course = {
                        str(item.get("course_id") or course_id): item
                        for course_id, item in zip(course_ids, rebuilt)
                    }
                    return [
                        {
                            "course_id": course_id,
                            "subject_id": group.get("subject_id"),
                            "status": "completed",
                            "library_id": by_course[course_id]["library"].get("library_id"),
                            "revision_id": by_course[course_id]["library"].get("revision_id"),
                            "lifecycle_status": by_course[course_id]["library"].get("lifecycle_status"),
                        }
                        for course_id in course_ids
                    ]
                except Exception as exc:
                    recovered = []
                    for course_id in course_ids:
                        try:
                            try:
                                rebuilt_one = await self.library_service.rebuild_course(
                                    course_id,
                                    force=True,
                                    strict_provider=False,
                                )
                            except TypeError:
                                rebuilt_one = await self.library_service.rebuild_course(course_id)
                            recovered.append({
                                "course_id": course_id,
                                "subject_id": group.get("subject_id"),
                                "status": "completed",
                                "library_id": rebuilt_one["library"].get("library_id"),
                                "revision_id": rebuilt_one["library"].get("revision_id"),
                                "lifecycle_status": rebuilt_one["library"].get("lifecycle_status"),
                            })
                        except Exception as individual_exc:
                            degraded = None
                            if hasattr(self.library_service, "degrade_course_index"):
                                degraded = await self.library_service.degrade_course_index(
                                    course_id,
                                    reason=str(individual_exc or exc),
                                )
                            recovered.append({
                                "course_id": course_id,
                                "subject_id": group.get("subject_id"),
                                "status": "failed",
                                "error": str(individual_exc or exc),
                                "library_id": (degraded or {}).get("library", {}).get("library_id"),
                                "revision_id": (degraded or {}).get("library", {}).get("revision_id"),
                                "lifecycle_status": (degraded or {}).get("library", {}).get("lifecycle_status"),
                            })
                    return recovered

        groups = job.get("subject_groups") or [
            {"subject_id": f"legacy.{course_id}", "course_ids": [course_id]}
            for course_id in job.get("course_ids") or []
        ]
        pending_groups = [
            group for group in groups
            if any(str(course_id) not in completed_ids for course_id in group.get("course_ids") or [])
        ]
        for offset in range(0, len(pending_groups), 2):
            current = self.repository.load(job_id)
            if current.get("status") == "paused":
                return
            grouped_results = await asyncio.gather(*(
                migrate_group(group) for group in pending_groups[offset:offset + 2]
            ))
            results = [item for group_results in grouped_results for item in group_results]
            current["results"] = [*(current.get("results") or []), *results]
            current["completed_count"] = sum(item.get("status") == "completed" for item in current["results"])
            current["failed_count"] = sum(item.get("status") == "failed" for item in current["results"])
            self.repository.save(current)
        job = self.repository.load(job_id)
        job["status"] = "completed"
        job["completed_at"] = datetime.now(timezone.utc).isoformat()
        self.repository.save(job)


__all__ = ["KnowledgeLibraryMigrationRepository", "KnowledgeLibraryMigrationService"]
