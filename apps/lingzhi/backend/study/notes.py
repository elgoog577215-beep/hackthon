"""Personal annotations, owned by the existing material revision's notes."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field

from study.repository import StudyConflict, StudyRepository, now


class CreateNote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{16,64}$")
    revision_id: str = Field(min_length=1, max_length=80)
    section_id: str = Field(default="", max_length=160)
    block_id: str = Field(default="", max_length=160)
    quote: str = Field(default="", max_length=3000)
    anchor_prefix: str = Field(default="", max_length=160)
    anchor_suffix: str = Field(default="", max_length=160)
    content: str = Field(default="", max_length=20000)
    kind: Literal["mark", "note"] = "note"
    question_state: Literal["none", "open", "answered"] = "none"
    important: bool = False
    source_message_id: str = Field(default="", max_length=100)


class UpdateNote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    content: str | None = Field(default=None, max_length=20000)
    kind: Literal["mark", "note"] | None = None
    question_state: Literal["none", "open", "answered"] | None = None
    important: bool | None = None
    source_message_id: str | None = Field(default=None, max_length=100)


PUBLIC_FIELDS = (
    "id", "revision_id", "section_id", "section_title", "block_id", "block_title",
    "content_type", "quote", "anchor_prefix", "anchor_suffix", "content", "kind",
    "question_state", "important", "version", "source_type", "source_message_id",
    "created_at", "updated_at", "source_sha256",
)


def _all_entries(material: dict):
    for notes in material.get("notes", {}).values():
        yield from notes.get("entries", [])


def _find(material: dict, note_id: str, *, include_deleted: bool = False) -> dict:
    note = next((entry for entry in _all_entries(material)
                 if entry.get("id") == note_id and (include_deleted or not entry.get("deleted_at"))), None)
    if note is None:
        raise KeyError(note_id)
    return note


def _digest(block: dict) -> str:
    return hashlib.sha256(block.get("content", "").encode()).hexdigest()


def location_status(material: dict, note: dict) -> str:
    current = material["revisions"][-1]
    if note["revision_id"] != current["id"]:
        return "historical"
    section = next((s for s in current.get("sections", []) if s["id"] == note.get("section_id")), None)
    if note.get("section_id") and section is None:
        return "missing"
    if note.get("block_id"):
        block = next((b for b in (section or {}).get("blocks", []) if b["block_id"] == note["block_id"]), None)
        if block is None:
            return "missing"
        if note.get("source_sha256") != _digest(block):
            return "changed"
    return "current"


def public_note(material: dict, note: dict) -> dict:
    return {**{key: deepcopy(note.get(key)) for key in PUBLIC_FIELDS}, "location_status": location_status(material, note)}


def get_note(material: dict, note_id: str, revision_id: str | None = None) -> dict:
    """Read one live record from an already authorized material, without writing."""
    note = _find(material, note_id)
    if revision_id is not None and note["revision_id"] != revision_id:
        raise KeyError(note_id)
    return public_note(material, note)


def resolve_note_context(material: dict, note_id: str, expected_version: int | None = None) -> dict:
    """An AI request must use the same still-current note and original passage."""
    try:
        note = get_note(material, note_id)
    except KeyError:
        raise StudyConflict("笔记已不存在，请重新打开笔记") from None
    if expected_version is not None and note["version"] != expected_version:
        raise StudyConflict("笔记已被修改，请重新打开后继续讨论")
    if note["location_status"] != "current":
        raise StudyConflict("笔记原文已变化，请核对来源后再继续讨论；原记录仍保留")
    return note


def list_notes(material: dict, revision_id: str | None = None) -> list[dict]:
    revision_id = revision_id or material["revisions"][-1]["id"]
    if not any(revision["id"] == revision_id for revision in material["revisions"]):
        raise StudyConflict("讲义版本已不存在，请重新打开讲义")
    return [public_note(material, note) for note in material.get("notes", {}).get(revision_id, {}).get("entries", [])
            if not note.get("deleted_at")]


def public_notes(material: dict) -> dict:
    """Keep legacy whole-handout notes while hiding tombstones and request keys."""
    return {revision_id: {**{key: deepcopy(value) for key, value in note.items() if key != "entries"},
                          "entries": [public_note(material, entry) for entry in note.get("entries", []) if not entry.get("deleted_at")]}
            for revision_id, note in material.get("notes", {}).items()}


def _source(material: dict, payload: dict) -> dict:
    revision = material["revisions"][-1]
    if payload["revision_id"] != revision["id"]:
        raise StudyConflict("讲义版本已改变，请重新打开后记录")
    section_id, block_id = payload.get("section_id", ""), payload.get("block_id", "")
    section = next((s for s in revision.get("sections", []) if s["id"] == section_id), None)
    if section_id and section is None:
        raise StudyConflict("所选讲次不属于当前讲义，请重新选择")
    block = next((b for b in (section or {}).get("blocks", []) if b["block_id"] == block_id), None)
    if block_id and block is None:
        raise StudyConflict("所选正文块不属于当前讲义，请重新选择")
    if payload["kind"] == "mark" and not block:
        raise StudyConflict("请先选择要标记的正文")
    if (payload.get("quote") or payload.get("anchor_prefix") or payload.get("anchor_suffix")) and not block:
        raise StudyConflict("原文摘录必须关联具体正文块")
    return {"section_id": section_id, "section_title": section.get("title", "") if section else "",
            "block_id": block_id, "block_title": block.get("title", "") if block else "",
            "content_type": block.get("content_type", "") if block else "",
            "source_sha256": _digest(block) if block else ""}


def _ai_source(owner: str, material: dict, payload: dict, *, note_id: str | None = None,
               expected_note_version: int | None = None) -> dict:
    # Import the same repository instance the personal assistant uses. A
    # message from another user/material/revision cannot be looked up here.
    from study.assistant import ai_teacher_repository
    conversation = ai_teacher_repository.material_conversation(owner, material["id"], payload["revision_id"])
    message = next((m for m in conversation["messages"] if m["message_id"] == payload["source_message_id"]), None)
    if not message or message.get("role") != "assistant" or message.get("status") != "complete":
        raise StudyConflict("这条 AI 回复尚未完成或不属于当前材料，不能保存为笔记")
    context = message.get("context_ref", {})
    if context.get("material_id") != material["id"] or context.get("revision_id") != payload["revision_id"]:
        raise StudyConflict("AI 回复与当前讲义版本不匹配，请回到原对话")
    if note_id is not None and (context.get("note_id") != note_id or context.get("note_version") != expected_note_version):
        raise StudyConflict("AI 整理稿不属于这条笔记的当前版本，请核对后重新讨论")
    for key in ("section_id", "block_id"):
        if payload.get(key) and payload[key] != context.get(key, ""):
            raise StudyConflict("AI 回复引用的是另一处正文，请回到原对话保存")
    return {**payload, "section_id": context.get("section_id", ""), "block_id": context.get("block_id", ""),
            "quote": context.get("quote", ""), "anchor_prefix": "", "anchor_suffix": ""}


def _record_saved(owner: str, material: dict, note: dict) -> None:
    from learning_events import record_learning_event
    record_learning_event(
        event_type="personal_note_saved", actor="student", source="personal_study", user_id=owner,
        entity_type="personal_material", entity_id=material["id"], entity_revision=note["revision_id"],
        task_purpose=material.get("purpose"), record_type="personal_note", record_id=note["id"],
        idempotency_key=f"note:{material['id']}:{note['id']}:{note['version']}",
        result={"saved": True},  # A saved note or answered doubt is not mastery evidence.
    )


def create_note(repo: StudyRepository, owner: str, material_id: str, payload: dict) -> dict:
    material = repo.get(owner, material_id)
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    effective = _ai_source(owner, material, payload) if payload.get("source_message_id") else payload
    note_id = str(uuid.uuid5(uuid.NAMESPACE_URL, json.dumps([owner, material_id, payload["request_id"]])))
    changed = False

    def change(current):
        nonlocal changed
        existing = next((n for n in _all_entries(current) if n.get("request_id") == payload["request_id"]), None)
        if existing:
            if existing.get("fingerprint") != fingerprint:
                raise StudyConflict("这个保存请求已用于另一条笔记，请重新保存")
            if existing.get("deleted_at"):
                raise StudyConflict("这条笔记已删除，如需重新记录请发起新的保存")
            return
        source = _source(current, effective)
        if effective["kind"] == "note" and not effective["content"].strip() and not effective.get("quote", "").strip():
            raise StudyConflict("请先写下笔记或选择原文")
        stamp = now()
        note = {"id": note_id, "request_id": payload["request_id"], "fingerprint": fingerprint,
                "revision_id": effective["revision_id"], **source,
                **{key: effective[key] for key in ("quote", "anchor_prefix", "anchor_suffix", "content", "kind", "question_state", "important")},
                "source_type": "ai" if payload.get("source_message_id") else "self",
                "source_message_id": payload.get("source_message_id", ""), "version": 1,
                "created_at": stamp, "updated_at": stamp}
        bucket = current.setdefault("notes", {}).setdefault(effective["revision_id"], {})
        bucket.setdefault("entries", []).append(note)
        changed = True

    saved = repo.mutate_notes(owner, material_id, change)
    note = get_note(saved, note_id)
    if changed:
        _record_saved(owner, saved, note)
    return note


def update_note(repo: StudyRepository, owner: str, material_id: str, note_id: str, payload: dict) -> dict:
    material = repo.get(owner, material_id)
    existing = get_note(material, note_id)
    if payload.get("source_message_id"):
        resolve_note_context(material, note_id, payload["expected_version"])
        _ai_source(owner, material, {**existing, "source_message_id": payload["source_message_id"]},
                   note_id=note_id, expected_note_version=payload["expected_version"])

    def change(material):
        note = _find(material, note_id)
        if note["version"] != payload["expected_version"]:
            raise StudyConflict("笔记已被修改，请重新打开；你的输入仍可保留")
        if payload.get("source_message_id"):
            resolve_note_context(material, note_id, payload["expected_version"])
        values = {key: value for key, value in payload.items()
                  if key not in {"expected_version", "source_message_id"} and value is not None}
        if payload.get("source_message_id"):
            # The student may edit the suggested draft before saving it. The
            # participation marker records origin without claiming authorship
            # or independent understanding.
            values.update(source_message_id=payload["source_message_id"], source_type="ai")
        if values.get("kind", note["kind"]) == "mark" and not note.get("block_id"):
            raise StudyConflict("整讲笔记不能转为原文标记")
        if values.get("kind", note["kind"]) == "note" and not values.get("content", note["content"]).strip() and not note.get("quote"):
            raise StudyConflict("请先写下笔记，或删除这条空记录")
        note.update(**values, version=note["version"] + 1, updated_at=now())

    saved = repo.mutate_notes(owner, material_id, change)
    note = get_note(saved, note_id)
    _record_saved(owner, saved, note)
    return note


def delete_note(repo: StudyRepository, owner: str, material_id: str, note_id: str, expected_version: int) -> dict:
    def change(material):
        note = _find(material, note_id, include_deleted=True)
        if note.get("deleted_at") and expected_version in {note["version"], note["version"] - 1}:
            return
        if note.get("deleted_at") or note["version"] != expected_version:
            raise StudyConflict("笔记已被修改，请重新打开后再删除")
        note.update(deleted_at=now(), updated_at=now(), version=note["version"] + 1)

    saved = repo.mutate_notes(owner, material_id, change)
    tombstone = _find(saved, note_id, include_deleted=True)
    return {"deleted": True, "id": note_id, "version": tombstone["version"]}
