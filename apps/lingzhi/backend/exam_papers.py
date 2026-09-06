"""Course-owned exam papers composed from immutable question revisions."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from course_versioning import stable_hash
from storage import DATA_DIR


EXAM_PAPER_SCHEMA = "exam_paper_v1"
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}")


class ExamPaperRepository:
    """Persist one current immutable revision for every course exam paper."""

    def __init__(self, root_dir: str | Path | None = None) -> None:
        self.root_dir = Path(root_dir or Path(DATA_DIR) / "exam_papers")
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        *,
        course_id: str,
        actor_id: str,
        title: str,
        duration_minutes: int,
        total_score: float,
        bundle_revision_id: str,
        questions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        normalized_course_id = _storage_id(course_id)
        normalized_title = str(title or "").strip()
        if not normalized_title:
            raise ValueError("exam paper title is required")
        if not questions:
            raise ValueError("exam paper requires at least one question")

        paper_id = f"paper_{uuid4().hex}"
        created_at = _now()
        scores = _distribute_scores(total_score, len(questions))
        question_refs = [
            {
                "position": index,
                "item_id": str(question.get("item_id") or ""),
                "question_revision_id": str(question.get("revision_id") or ""),
                "node_id": str(question.get("node_id") or ""),
                "question_type": str(question.get("question_type") or ""),
                "score": scores[index - 1],
            }
            for index, question in enumerate(questions, start=1)
        ]
        payload = {
            "schema_version": EXAM_PAPER_SCHEMA,
            "paper_id": paper_id,
            "course_id": normalized_course_id,
            "title": normalized_title,
            "status": "draft",
            "duration_minutes": int(duration_minutes),
            "total_score": round(float(total_score), 2),
            "source_bundle_revision_id": str(bundle_revision_id or ""),
            "question_refs": question_refs,
            "item_count": len(question_refs),
            "created_by": str(actor_id or "")[:200],
            "created_at": created_at,
            "updated_at": created_at,
        }
        payload["revision_id"] = stable_hash(payload, prefix="paperrev_")
        self._write_revision(payload)
        return deepcopy(payload)

    def list_course(self, course_id: str) -> list[dict[str, Any]]:
        course_dir = self.root_dir / _storage_id(course_id)
        if not course_dir.exists():
            return []
        papers = []
        for paper_dir in course_dir.iterdir():
            if not paper_dir.is_dir():
                continue
            paper = self._load_current(course_id, paper_dir.name)
            if paper:
                papers.append(paper)
        papers.sort(
            key=lambda item: (
                str(item.get("updated_at") or ""),
                str(item.get("paper_id") or ""),
            ),
            reverse=True,
        )
        return deepcopy(papers)

    def load(self, course_id: str, paper_id: str) -> dict[str, Any] | None:
        return deepcopy(self._load_current(course_id, paper_id))

    def _load_current(
        self, course_id: str, paper_id: str
    ) -> dict[str, Any] | None:
        normalized_course_id = _storage_id(course_id)
        normalized_paper_id = _storage_id(paper_id)
        pointer = (
            self.root_dir
            / normalized_course_id
            / normalized_paper_id
            / "current.json"
        )
        if not pointer.exists():
            return None
        revision_id = str(self._read(pointer).get("revision_id") or "")
        if not revision_id:
            return None
        path = pointer.parent / "revisions" / f"{_storage_id(revision_id)}.json"
        if not path.exists():
            return None
        paper = self._read(path)
        if str(paper.get("course_id") or "") != normalized_course_id:
            raise ValueError("exam paper course scope is invalid")
        return paper

    def _write_revision(self, paper: dict[str, Any]) -> None:
        course_id = _storage_id(str(paper.get("course_id") or ""))
        paper_id = _storage_id(str(paper.get("paper_id") or ""))
        revision_id = _storage_id(str(paper.get("revision_id") or ""))
        directory = self.root_dir / course_id / paper_id
        revision_path = directory / "revisions" / f"{revision_id}.json"
        if not revision_path.exists():
            _atomic_write(revision_path, paper)
        _atomic_write(directory / "current.json", {"revision_id": revision_id})

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise ValueError("exam paper repository expected a JSON object")
        return value


def _distribute_scores(total_score: float, count: int) -> list[float]:
    normalized_total = round(float(total_score), 2)
    if normalized_total <= 0 or normalized_total > 10000:
        raise ValueError("exam paper total score is invalid")
    if count <= 0:
        return []
    base = round(normalized_total / count, 2)
    scores = [base for _ in range(count)]
    scores[-1] = round(normalized_total - sum(scores[:-1]), 2)
    return scores


def _storage_id(value: str) -> str:
    normalized = str(value or "").strip()
    if not _ID_RE.fullmatch(normalized):
        raise ValueError("invalid storage identifier")
    return normalized


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.flush()
    temporary.replace(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


exam_paper_repository = ExamPaperRepository()


__all__ = [
    "EXAM_PAPER_SCHEMA",
    "ExamPaperRepository",
    "exam_paper_repository",
]
