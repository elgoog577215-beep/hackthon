"""Durable asynchronous job state for course question-bank rebuilds."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from threading import RLock
from typing import Any
from uuid import uuid4

from course_versioning import stable_hash
from storage import DATA_DIR


QUESTION_BANK_REBUILD_JOB_SCHEMA = "question_bank_rebuild_job_v1"
QUESTION_BANK_REBUILD_STAGES: tuple[tuple[str, str], ...] = (
    ("material_parsing", "资料解析"),
    ("assessment_profile", "测评画像"),
    ("objective_compilation", "目标编译"),
    ("source_retrieval", "来源检索"),
    ("archetype_planning", "题型规划"),
    ("question_generation", "题目生成"),
    ("independent_solving", "独立求解"),
    ("quality_validation", "质量验证"),
    ("waiting_review", "等待审核"),
    ("publication", "发布完成"),
)

_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}")


class QuestionBankRebuildJobRepository:
    """Store immutable request scope and monotonic rebuild progress."""

    def __init__(self, root_dir: str | Path | None = None) -> None:
        self.root_dir = Path(
            root_dir or Path(DATA_DIR) / "question_bank_rebuilds"
        )
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def create_job(
        self,
        course_id: str,
        *,
        request_id: str | None,
        scope: str,
        node_ids: list[str],
        mode: str,
        actor_id: str,
        revision_ids: list[str] | None = None,
        worker_id: str = "",
    ) -> tuple[dict[str, Any], bool]:
        normalized_course_id = _storage_id(course_id)
        normalized_scope = str(scope or "course")
        normalized_mode = str(mode or "incremental")
        normalized_nodes = sorted({
            str(value).strip()
            for value in node_ids
            if str(value).strip()
        })
        normalized_revisions = sorted({
            str(value).strip()
            for value in revision_ids or []
            if str(value).strip()
        })
        if normalized_scope not in {"course", "nodes", "items"}:
            raise ValueError("scope must be course, nodes, or items")
        if normalized_mode not in {"incremental", "full"}:
            raise ValueError("mode must be incremental or full")
        if normalized_scope == "nodes" and not normalized_nodes:
            raise ValueError("node_ids are required when scope is nodes")
        if normalized_scope == "items" and not normalized_revisions:
            raise ValueError(
                "revision_ids are required when scope is items"
            )
        if normalized_scope == "course":
            normalized_nodes = []
            normalized_revisions = []
        elif normalized_scope == "nodes":
            normalized_revisions = []
        request_key = str(request_id or uuid4().hex).strip()
        normalized_actor_id = str(actor_id or "")[:200]
        normalized_worker_id = str(worker_id or "")[:200]
        job_id = stable_hash(
            {
                "course_id": normalized_course_id,
                "request_id": request_key,
                "scope": normalized_scope,
                "node_ids": normalized_nodes,
                "revision_ids": normalized_revisions,
                "mode": normalized_mode,
            },
            prefix="qbr_",
        )
        with self._lock:
            directory = self.root_dir / normalized_course_id
            if directory.exists():
                for active_path in directory.glob("*.json"):
                    active = self._read(active_path)
                    if not _same_active_scope(
                        active,
                        scope=normalized_scope,
                        node_ids=normalized_nodes,
                        revision_ids=normalized_revisions,
                        mode=normalized_mode,
                        actor_id=normalized_actor_id,
                    ):
                        continue
                    active_worker_id = str(
                        active.get("worker_id") or ""
                    )
                    if (
                        normalized_worker_id
                        and active_worker_id != normalized_worker_id
                    ):
                        _mark_worker_restarted(active)
                        self._write(active_path, active)
                        continue
                    return deepcopy(active), False
            path = self._path(normalized_course_id, job_id)
            if path.exists():
                return self._read(path), False
            now = _now()
            job = {
                "schema_version": QUESTION_BANK_REBUILD_JOB_SCHEMA,
                "job_id": job_id,
                "course_id": normalized_course_id,
                "request_id": request_id,
                "request_key": request_key,
                "scope": normalized_scope,
                "node_ids": normalized_nodes,
                "revision_ids": normalized_revisions,
                "mode": normalized_mode,
                "actor_id": normalized_actor_id,
                "worker_id": normalized_worker_id,
                "status": "queued",
                "progress": 0,
                "current_stage": QUESTION_BANK_REBUILD_STAGES[0][0],
                "current_stage_index": 0,
                "message": "题库重建任务已进入队列",
                "stages": [
                    {
                        "stage_id": stage_id,
                        "label": label,
                        "status": "pending",
                    }
                    for stage_id, label in QUESTION_BANK_REBUILD_STAGES
                ],
                "result": None,
                "error": None,
                "created_at": now,
                "started_at": None,
                "updated_at": now,
                "completed_at": None,
            }
            self._write(path, job)
            return deepcopy(job), True

    def load(
        self,
        course_id: str,
        job_id: str,
    ) -> dict[str, Any] | None:
        path = self._path(_storage_id(course_id), _storage_id(job_id))
        if not path.exists():
            return None
        return self._read(path)

    def latest_for_course(
        self,
        course_id: str,
    ) -> dict[str, Any] | None:
        directory = self.root_dir / _storage_id(course_id)
        if not directory.exists():
            return None
        jobs = [
            self._read(path)
            for path in directory.glob("*.json")
            if path.is_file()
        ]
        if not jobs:
            return None
        return deepcopy(max(
            jobs,
            key=lambda job: (
                str(job.get("created_at") or ""),
                str(job.get("job_id") or ""),
            ),
        ))

    def start(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            path, job = self._load_by_job_id(job_id)
            if job["status"] in {
                "completed",
                "waiting_review",
                "failed",
            }:
                return deepcopy(job)
            job["status"] = "running"
            job["started_at"] = job.get("started_at") or _now()
            job["stages"][0]["status"] = "running"
            job["message"] = "正在解析课程资料"
            job["updated_at"] = _now()
            self._write(path, job)
            return deepcopy(job)

    def advance(
        self,
        job_id: str,
        *,
        stage_id: str,
        message: str = "",
    ) -> dict[str, Any]:
        stage_ids = [
            value for value, _ in QUESTION_BANK_REBUILD_STAGES
        ]
        if stage_id not in stage_ids:
            raise ValueError(f"unknown rebuild stage: {stage_id}")
        target_index = stage_ids.index(stage_id)
        with self._lock:
            path, job = self._load_by_job_id(job_id)
            current_index = int(job.get("current_stage_index") or 0)
            if target_index < current_index:
                raise ValueError("cannot move backwards in rebuild stages")
            if job.get("status") in {
                "completed",
                "waiting_review",
                "failed",
            }:
                raise ValueError("cannot advance a terminal rebuild job")
            for index, stage in enumerate(job["stages"]):
                stage["status"] = (
                    "completed"
                    if index < target_index
                    else (
                        "running"
                        if index == target_index
                        else "pending"
                    )
                )
            job["status"] = "running"
            job["current_stage"] = stage_id
            job["current_stage_index"] = target_index
            job["progress"] = int(
                target_index * 100
                / len(QUESTION_BANK_REBUILD_STAGES)
            )
            if message:
                job["message"] = str(message)[:1000]
            job["updated_at"] = _now()
            self._write(path, job)
            return deepcopy(job)

    def complete(
        self,
        job_id: str,
        *,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            path, job = self._load_by_job_id(job_id)
            review_count = int(
                (result.get("review_queue") or {}).get(
                    "blocking_count"
                )
                or 0
            )
            publication_mode = str(
                result.get("publication_mode") or ""
            )
            waiting_review = bool(
                review_count
                or "waiting_review" in publication_mode
            )
            job["status"] = (
                "waiting_review" if waiting_review else "completed"
            )
            job["current_stage"] = (
                "waiting_review" if waiting_review else "publication"
            )
            job["current_stage_index"] = (
                8 if waiting_review else 9
            )
            job["progress"] = 100
            for index, stage in enumerate(job["stages"]):
                if waiting_review and index == 8:
                    stage["status"] = "waiting_review"
                elif waiting_review and index > 8:
                    stage["status"] = "pending"
                else:
                    stage["status"] = "completed"
            job["message"] = (
                "候选题已生成，正在等待教师审核"
                if waiting_review
                else "题库重建并发布完成"
            )
            job["result"] = deepcopy(result)
            job["error"] = None
            job["completed_at"] = _now()
            job["updated_at"] = job["completed_at"]
            self._write(path, job)
            return deepcopy(job)

    def heartbeat(
        self,
        job_id: str,
        *,
        stage_id: str,
        progress: int,
        message: str = "",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        stage_ids = [
            value for value, _ in QUESTION_BANK_REBUILD_STAGES
        ]
        if stage_id not in stage_ids:
            raise ValueError(f"unknown rebuild stage: {stage_id}")
        with self._lock:
            path, job = self._load_by_job_id(job_id)
            if job.get("status") in {
                "completed",
                "waiting_review",
                "failed",
            }:
                raise ValueError("cannot heartbeat a terminal rebuild job")
            if str(job.get("current_stage") or "") != stage_id:
                raise ValueError("heartbeat stage must match current stage")
            stage_index = stage_ids.index(stage_id)
            next_stage_progress = int(
                (stage_index + 1) * 100
                / len(QUESTION_BANK_REBUILD_STAGES)
            )
            bounded_progress = min(
                max(int(progress), int(job.get("progress") or 0)),
                max(0, next_stage_progress - 1),
            )
            job["progress"] = bounded_progress
            if message:
                job["message"] = str(message)[:1000]
            job["stage_details"] = deepcopy(details or {})
            job["updated_at"] = _now()
            self._write(path, job)
            return deepcopy(job)

    def fail(
        self,
        job_id: str,
        *,
        code: str,
        message: str,
        retryable: bool,
    ) -> dict[str, Any]:
        with self._lock:
            path, job = self._load_by_job_id(job_id)
            job["status"] = "failed"
            job["stages"][
                int(job.get("current_stage_index") or 0)
            ]["status"] = "failed"
            job["message"] = str(message)[:1000]
            job["error"] = {
                "code": str(code)[:200],
                "message": str(message)[:1000],
                "retryable": bool(retryable),
            }
            job["completed_at"] = _now()
            job["updated_at"] = job["completed_at"]
            self._write(path, job)
            return deepcopy(job)

    def _load_by_job_id(
        self,
        job_id: str,
    ) -> tuple[Path, dict[str, Any]]:
        normalized_job_id = _storage_id(job_id)
        matches = list(
            self.root_dir.glob(f"*/{normalized_job_id}.json")
        )
        if len(matches) != 1:
            raise KeyError(f"question bank rebuild job not found: {job_id}")
        return matches[0], self._read(matches[0])

    def _path(self, course_id: str, job_id: str) -> Path:
        return self.root_dir / course_id / f"{job_id}.json"

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _write(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
        temporary.replace(path)


def _storage_id(value: str) -> str:
    normalized = str(value or "").strip()
    if not _ID_RE.fullmatch(normalized):
        raise ValueError("invalid storage identifier")
    return normalized


def _same_active_scope(
    job: dict[str, Any],
    *,
    scope: str,
    node_ids: list[str],
    revision_ids: list[str],
    mode: str,
    actor_id: str,
) -> bool:
    return (
        str(job.get("status") or "") in {"queued", "running"}
        and str(job.get("scope") or "") == scope
        and sorted(str(value) for value in job.get("node_ids") or [])
        == node_ids
        and sorted(
            str(value)
            for value in job.get("revision_ids") or []
        ) == revision_ids
        and str(job.get("mode") or "") == mode
        and str(job.get("actor_id") or "") == actor_id
    )


def _mark_worker_restarted(job: dict[str, Any]) -> None:
    job["status"] = "failed"
    current_index = int(job.get("current_stage_index") or 0)
    stages = job.get("stages") or []
    if 0 <= current_index < len(stages):
        stages[current_index]["status"] = "failed"
    job["message"] = "服务已重启，请重新提交题库重建任务"
    job["error"] = {
        "code": "rebuild_worker_restarted",
        "message": "后台生成进程已重启，原任务已安全终止",
        "retryable": True,
    }
    job["completed_at"] = _now()
    job["updated_at"] = job["completed_at"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


question_bank_rebuild_job_repository = (
    QuestionBankRebuildJobRepository()
)


__all__ = [
    "QUESTION_BANK_REBUILD_JOB_SCHEMA",
    "QUESTION_BANK_REBUILD_STAGES",
    "QuestionBankRebuildJobRepository",
    "question_bank_rebuild_job_repository",
]
