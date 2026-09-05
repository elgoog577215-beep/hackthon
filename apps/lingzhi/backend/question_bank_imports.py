"""Durable teacher file-import sessions for the canonical question bank."""

from __future__ import annotations

import json
import os
import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from course_versioning import stable_hash
from material_models import DocumentBlock, ParsedDocument
from storage import DATA_DIR

QUESTION_BANK_IMPORT_SCHEMA = "question_bank_import_session_v1"
QUESTION_BANK_IMPORT_DIR = Path(DATA_DIR) / "question_bank_imports"
_STORAGE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}")
_QUESTION_START_RE = re.compile(
    r"^\s*(?:第\s*)?(\d{1,3})(?:\s*题)?\s*[\.\u3001．:：\)）]\s*(.*)$"
)
_LABELED_QUESTION_RE = re.compile(r"^\s*(?:题目|问题|试题)\s*[:：]\s*(.*)$")
_OPTION_RE = re.compile(
    r"(?:^|\n|\s)([A-H])[\.\u3001．:：\)）]\s*(.+?)"
    r"(?=(?:\n|\s)[A-H][\.\u3001．:：\)）]\s*|"
    r"(?:\n|\s)(?:参考答案|答案|解析|解答|分值|满分)\s*[:：]|$)",
    re.IGNORECASE | re.DOTALL,
)
_ANSWER_RE = re.compile(
    r"(?:^|\n|\s)(?:参考答案|答案)\s*[:：]\s*(.+?)"
    r"(?=(?:\n|\s)(?:解析|解答|分值|满分)\s*[:：]|$)",
    re.IGNORECASE | re.DOTALL,
)
_EXPLANATION_RE = re.compile(
    r"(?:^|\n|\s)(?:解析|解答)\s*[:：]\s*(.+?)"
    r"(?=(?:\n|\s)(?:分值|满分)\s*[:：]|$)",
    re.IGNORECASE | re.DOTALL,
)
_SCORE_RE = re.compile(r"(?:分值|满分)\s*[:：]?\s*(\d{1,3})\s*分?")
_SECTION_TYPES = (
    ("多项选择", "multiple_choice"),
    ("多选", "multiple_choice"),
    ("单项选择", "single_choice"),
    ("单选", "single_choice"),
    ("选择题", "single_choice"),
    ("判断题", "true_false"),
    ("填空题", "fill_blank"),
    ("计算题", "calculation"),
    ("简答题", "short_answer"),
    ("论述题", "essay"),
)
_QUESTION_TYPES = {
    "single_choice",
    "multiple_choice",
    "true_false",
    "fill_blank",
    "calculation",
    "short_answer",
    "essay",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _storage_id(value: Any) -> str:
    normalized = str(value or "").strip()
    if not _STORAGE_ID_RE.fullmatch(normalized) or normalized in {".", ".."}:
        raise ValueError("invalid question import storage identifier")
    return normalized


def _clean(value: Any, *, limit: int = 12000) -> str:
    return "\n".join(
        line.rstrip()
        for line in str(value or "").replace("\r\n", "\n").split("\n")
    ).strip()[:limit]


def _section_type(text: str) -> str:
    normalized = " ".join(text.split())
    for marker, question_type in _SECTION_TYPES:
        if marker in normalized:
            return question_type
    return ""


def _page_text(document: ParsedDocument) -> list[dict[str, Any]]:
    pages: dict[int, list[str]] = {}
    for block in sorted(document.blocks, key=lambda item: item.order):
        text = _clean(block.text)
        if not text:
            continue
        page = int(block.locator.page or 1)
        pages.setdefault(page, []).append(text)
    return [
        {"page": page, "text": "\n\n".join(parts)[:50000]}
        for page, parts in sorted(pages.items())
    ]


def _draft_warnings(
    *,
    prompt: str,
    options: list[dict[str, str]],
    answer: str,
    question_type: str,
    degraded: bool,
) -> list[str]:
    warnings: list[str] = []
    if len(prompt.strip()) < 4:
        warnings.append("prompt_missing")
    if not answer.strip():
        warnings.append("answer_missing")
    if question_type in {"single_choice", "multiple_choice"} and len(options) < 2:
        warnings.append("options_incomplete")
    if degraded:
        warnings.append("source_parse_degraded")
    return warnings


def _parse_group(
    group: dict[str, Any],
    *,
    asset_id: str,
    document_id: str,
    degraded: bool,
    index: int,
    default_node_id: str,
) -> dict[str, Any]:
    raw = _clean("\n".join(group["lines"]))
    for _ in range(2):
        question_start = _QUESTION_START_RE.match(raw)
        if not question_start:
            break
        raw = question_start.group(2)
    raw = _LABELED_QUESTION_RE.sub(lambda match: match.group(1), raw, count=1)
    answer_match = _ANSWER_RE.search(raw)
    explanation_match = _EXPLANATION_RE.search(raw)
    score_match = _SCORE_RE.search(raw)
    answer = _clean(answer_match.group(1) if answer_match else "", limit=2000)
    explanation = _clean(
        explanation_match.group(1) if explanation_match else "",
        limit=8000,
    )
    options = [
        {"id": match.group(1).upper(), "text": _clean(match.group(2), limit=3000)}
        for match in _OPTION_RE.finditer(raw)
    ]
    cut_points = [
        match.start()
        for match in (
            _OPTION_RE.search(raw),
            _ANSWER_RE.search(raw),
            _EXPLANATION_RE.search(raw),
            _SCORE_RE.search(raw),
        )
        if match is not None
    ]
    prompt = _clean(raw[: min(cut_points)] if cut_points else raw)
    question_type = str(group.get("question_type") or "")
    if not question_type:
        if options:
            question_type = (
                "multiple_choice"
                if len(re.findall(r"[A-H]", answer.upper())) > 1
                else "single_choice"
            )
        else:
            question_type = "short_answer"
    warnings = _draft_warnings(
        prompt=prompt,
        options=options,
        answer=answer,
        question_type=question_type,
        degraded=degraded,
    )
    draft_id = stable_hash(
        {
            "asset_id": asset_id,
            "index": index,
            "prompt": " ".join(prompt.split()),
        },
        prefix="qid_",
    )
    return {
        "draft_id": draft_id,
        "document_id": document_id,
        "sequence": index,
        "prompt": prompt,
        "question_type": question_type,
        "options": options,
        "answer": answer,
        "explanation": explanation,
        "score": int(score_match.group(1)) if score_match else None,
        "node_id": default_node_id,
        "source_page": group.get("page"),
        "section_path": deepcopy(group.get("section_path") or []),
        "block_ids": list(dict.fromkeys(group.get("block_ids") or [])),
        "confidence": "low" if degraded or len(warnings) > 1 else ("medium" if warnings else "high"),
        "warnings": warnings,
        "confirmed": not warnings,
        "updated_at": _now(),
    }


def extract_question_drafts(
    document: ParsedDocument,
    *,
    node_ids: Iterable[str] = (),
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split a parsed PDF/DOCX into editable, source-located questions."""
    groups: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    active_type = ""
    for block in sorted(document.blocks, key=lambda item: item.order):
        block_text = _clean(block.text)
        if not block_text:
            continue
        detected_type = _section_type(block_text)
        if detected_type and len(block_text) <= 100:
            active_type = detected_type
            if current:
                current.setdefault("section_path", []).extend(block.locator.section_path)
            continue
        for line in block_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            start = _QUESTION_START_RE.match(line) or _LABELED_QUESTION_RE.match(line)
            if start:
                if current:
                    groups.append(current)
                current = {
                    "lines": [line],
                    "question_type": active_type,
                    "page": block.locator.page or 1,
                    "section_path": list(block.locator.section_path),
                    "block_ids": [block.block_id],
                }
            elif current:
                current["lines"].append(line)
                current["block_ids"].append(block.block_id)
    if current:
        groups.append(current)

    if not groups:
        for block in sorted(document.blocks, key=lambda item: item.order):
            if block.kind != "question" or not _clean(block.text):
                continue
            groups.append({
                "lines": [_clean(block.text)],
                "question_type": _section_type(block.text),
                "page": block.locator.page or 1,
                "section_path": list(block.locator.section_path),
                "block_ids": [block.block_id],
            })
    default_node_id = next(
        (str(value).strip() for value in node_ids if str(value).strip()),
        "",
    )
    drafts = [
        _parse_group(
            group,
            asset_id=document.asset_id,
            document_id=document.document_id,
            degraded=document.parse_status == "degraded",
            index=index,
            default_node_id=default_node_id,
        )
        for index, group in enumerate(groups, start=1)
    ]
    drafts = [draft for draft in drafts if draft["prompt"]]
    return drafts, _page_text(document)


def _pending_count(session: dict[str, Any]) -> int:
    return sum(
        1
        for item in session.get("questions") or []
        if not item.get("confirmed")
    )


def refresh_import_session(session: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(session)
    result["pending_count"] = _pending_count(result)
    result["question_count"] = len(result.get("questions") or [])
    if result.get("status") != "committed":
        result["status"] = "needs_review" if result["pending_count"] else "ready"
        result["step"] = "review"
    result["updated_at"] = _now()
    return result


class QuestionBankImportRepository:
    def __init__(self, root_dir: str | Path | None = None) -> None:
        self.root_dir = Path(root_dir or QUESTION_BANK_IMPORT_DIR)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, course_id: str, import_id: str) -> Path:
        return self.root_dir / _storage_id(course_id) / f"{_storage_id(import_id)}.json"

    def create(
        self,
        *,
        course_id: str,
        actor_id: str,
        asset: Any,
        document: ParsedDocument,
        questions: list[dict[str, Any]],
        source_pages: list[dict[str, Any]],
        course_asset_id: str = "",
        package_id: str = "",
    ) -> dict[str, Any]:
        import_id = f"qimp-{uuid.uuid4().hex}"
        now = _now()
        session = refresh_import_session({
            "schema_version": QUESTION_BANK_IMPORT_SCHEMA,
            "import_id": import_id,
            "course_id": course_id,
            "actor_id": actor_id,
            "asset_id": str(getattr(asset, "asset_id", "") or ""),
            "course_asset_id": course_asset_id,
            "package_id": package_id,
            "document_id": document.document_id,
            "filename": str(getattr(asset, "filename", "") or ""),
            "extension": str(getattr(asset, "extension", "") or ""),
            "size_bytes": int(getattr(asset, "size_bytes", 0) or 0),
            "parse_status": document.parse_status,
            "parse_warnings": list(document.warnings),
            "questions": questions,
            "source_pages": source_pages,
            "status": "needs_review",
            "step": "review",
            "result_bundle_revision_id": "",
            "created_at": now,
            "updated_at": now,
        })
        for question in session["questions"]:
            question["import_id"] = import_id
        self.save(session)
        return session

    def save(self, session: dict[str, Any]) -> dict[str, Any]:
        stored = refresh_import_session(session)
        path = self._path(stored["course_id"], stored["import_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".json.tmp")
        try:
            with temp.open("w", encoding="utf-8") as handle:
                json.dump(stored, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()
        return stored

    def load(self, course_id: str, import_id: str) -> dict[str, Any] | None:
        path = self._path(course_id, import_id)
        if not path.exists():
            return None
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else None

    def list(self, course_id: str, *, actor_id: str = "") -> list[dict[str, Any]]:
        directory = self.root_dir / _storage_id(course_id)
        result: list[dict[str, Any]] = []
        for path in directory.glob("qimp-*.json") if directory.exists() else []:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(value, dict):
                continue
            if actor_id and value.get("actor_id") != actor_id:
                continue
            result.append(value)
        result.sort(key=lambda value: str(value.get("updated_at") or ""), reverse=True)
        return result

    def update_question(
        self,
        course_id: str,
        import_id: str,
        draft_id: str,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        session = self.load(course_id, import_id)
        if not session:
            raise FileNotFoundError(import_id)
        if session.get("status") == "committed":
            raise ValueError("committed import sessions are immutable")
        question = next(
            (
                item
                for item in session.get("questions") or []
                if item.get("draft_id") == draft_id
            ),
            None,
        )
        if question is None:
            raise FileNotFoundError(draft_id)
        for field, limit in {
            "prompt": 12000,
            "answer": 2000,
            "explanation": 8000,
            "node_id": 200,
        }.items():
            if field in changes:
                question[field] = _clean(changes[field], limit=limit)
        if "question_type" in changes:
            question_type = str(changes["question_type"] or "").strip()
            if question_type not in _QUESTION_TYPES:
                raise ValueError("unsupported imported question type")
            question["question_type"] = question_type
        if "score" in changes:
            score = changes["score"]
            question["score"] = None if score in {None, ""} else max(1, min(1000, int(score)))
        if "options" in changes:
            options = []
            for option in list(changes["options"] or [])[:8]:
                option_id = str(option.get("id") or "").strip().upper()
                option_text = _clean(option.get("text"), limit=3000)
                if re.fullmatch(r"[A-H]", option_id) and option_text:
                    options.append({"id": option_id, "text": option_text})
            question["options"] = options
        question["warnings"] = _draft_warnings(
            prompt=str(question.get("prompt") or ""),
            options=list(question.get("options") or []),
            answer=str(question.get("answer") or ""),
            question_type=str(question.get("question_type") or "short_answer"),
            degraded="source_parse_degraded" in (question.get("warnings") or []),
        )
        if "confirmed" in changes:
            question["confirmed"] = bool(changes["confirmed"])
        elif any(field in changes for field in {"prompt", "answer", "options", "question_type"}):
            question["confirmed"] = not question["warnings"]
        question["updated_at"] = _now()
        return self.save(session)

    def mark_committed(
        self,
        course_id: str,
        import_id: str,
        bundle_revision_id: str,
    ) -> dict[str, Any]:
        session = self.load(course_id, import_id)
        if not session:
            raise FileNotFoundError(import_id)
        session["status"] = "committed"
        session["step"] = "complete"
        session["result_bundle_revision_id"] = bundle_revision_id
        session["committed_at"] = _now()
        stored = refresh_import_session(session)
        stored["status"] = "committed"
        stored["step"] = "complete"
        return self.save(stored)


question_bank_import_repository = QuestionBankImportRepository()


__all__ = [
    "QUESTION_BANK_IMPORT_SCHEMA",
    "QuestionBankImportRepository",
    "extract_question_drafts",
    "question_bank_import_repository",
    "refresh_import_session",
]
