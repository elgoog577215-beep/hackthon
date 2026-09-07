"""Offline restoration of teacher-owned bodies, with verified external backups."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import os
import re

from course_document import CourseDocument, refresh_document_revision
from course_repository import CourseDocumentConflict
from teacher_course_content import hydrate_authoring, _sections


def prepare(raw, authoring, source=None, *, allow_paused=False):
    if raw.get("authoring_surface") != "teacher":
        return {"status": "historical_student", "course": raw, "authoring": authoring}
    unsafe_statuses = {"pending", "running", "queued"} | (set() if allow_paused else {"paused"})
    if any(j.get("status") in unsafe_statuses
           for j in (authoring.get("jobs") or {}).values()):
        raise CourseDocumentConflict("课程仍有活动或可恢复任务，请自然结束后转换。")
    restored = hydrate_authoring(raw, authoring)
    for lid, binding in (raw.get("teacher_handouts") or {}).items():
        lesson = (restored.get("lessons") or {}).get(lid)
        if not lesson:
            raise CourseDocumentConflict("正文缺少对应的教师讲次，不能恢复。")
        revision = next((r for r in lesson.get("script_revisions") or [] if r.get("revision_id") == binding["revision_id"]), None)
        if revision is None or revision.get("sections") != _sections(raw, binding):
            raise CourseDocumentConflict("同一讲义版本存在不同正文，停止转换。")
    for lesson in (restored.get("lessons") or {}).values():
        for revision in lesson.get("script_revisions") or []:
            if revision.get("canonical_ref") and not revision.get("sections"):
                raise CourseDocumentConflict("讲义引用缺少正文，停止转换。")
            revision.pop("canonical_ref", None)
        lesson.pop("document_revision", None)
        lesson.pop("current_content_revision_id", None)
    restored.pop("_canonical_baselines", None)
    target = deepcopy(raw)
    old_blocks = (target.get("course_document") or {}).get("blocks") or []
    if old_blocks and not raw.get("teacher_handouts") and raw.get("teacher_body_source") != "authoring":
        raise CourseDocumentConflict("已有正文缺少教师版本绑定，不能确认归属。")
    if target.get("course_document"):
        doc = CourseDocument.model_validate(target["course_document"])
        doc.blocks = []
        doc = refresh_document_revision(doc)
        target.update(course_document=doc.model_dump(mode="json"), course_document_revision=doc.document_revision)
    target["teacher_body_source"] = "authoring"
    target.pop("teacher_handouts", None)
    target.pop("teacher_handout_history", None)
    changed = target != raw or restored != authoring
    return {"status": "ready" if changed else "already_authoritative", "course": target,
            "authoring": restored, "verified_lessons": len(restored.get("lessons") or {})}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path, data):
    fd, name = tempfile.mkstemp(prefix="." + path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def migrate(data_dir, *, mode="preflight", backup_dir=None, course_ids=None, activation_check=False):
    if mode not in {"preflight", "apply", "verify"}:
        raise ValueError("Unknown migration mode")
    if activation_check and mode != "preflight":
        raise ValueError("Activation checks must be read-only")
    root = Path(data_dir).resolve()
    if mode == "apply":
        preflight = migrate(root, mode="preflight", course_ids=course_ids)
        if any(item["status"] == "conflict" for item in preflight["courses"]):
            return {**preflight, "mode": mode}
    results = []
    backup = None
    if mode == "apply":
        if backup_dir is None:
            raise ValueError("apply requires an external backup directory")
        parent = Path(backup_dir).resolve()
        if parent == root or root in parent.parents:
            raise ValueError("backup must be outside the data directory")
        if any((p / ".git").exists() for p in [parent, *parent.parents]):
            raise ValueError("backup must be outside Git repositories")
        backup = parent / datetime.now(timezone.utc).strftime("teacher-content-%Y%m%dT%H%M%S%fZ")
        backup.mkdir(parents=True)
    for path in sorted((root / "courses").glob("*.json")):
        cid = path.stem
        if re.search(r"\.v\d+$", cid) or (course_ids and cid not in course_ids):
            continue
        ap = root / "teacher_lesson_authoring" / f"{cid}.json"
        try:
            raw = json.loads(path.read_text())
            author = json.loads(ap.read_text()) if ap.exists() else {"course_id": cid, "lessons": {}}
            inputs = [path] + ([ap] if ap.exists() else [])
            hashes = {str(p.relative_to(root)): digest(p) for p in inputs}
            result = prepare(raw, author, allow_paused=activation_check)
            status = result["status"]
            if mode == "verify" and status == "ready":
                status = "not_migrated"
            if mode == "apply" and status == "ready":
                course_backup = backup / cid
                course_backup.mkdir()
                for p in inputs:
                    dest = course_backup / p.relative_to(root)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, dest)
                    if digest(dest) != hashes[str(p.relative_to(root))]:
                        raise CourseDocumentConflict("备份校验失败。")
                atomic(course_backup / "manifest.json", {"course_id": cid, "sha256": hashes, "authoring_existed": ap.exists()})
                ap.parent.mkdir(exist_ok=True)
                # Lock both old and new writer protocols during offline conversion.
                with (ap.parent / ".authoring.lock").open("a+") as old_lock, ap.with_suffix(".lock").open("a+") as author_lock, path.with_suffix(".lock").open("a+") as course_lock:
                    for lock in (old_lock, author_lock, course_lock):
                        fcntl.flock(lock, fcntl.LOCK_EX)
                    if any(digest(p) != hashes[str(p.relative_to(root))] for p in inputs):
                        raise CourseDocumentConflict("预检后数据已变化。")
                    # Full teacher content is durable before removing old copies.
                    atomic(ap, result["authoring"])
                    atomic(path, result["course"])
                status = "migrated"
            references = sum(bool(r.get('canonical_ref')) for lesson in (author.get('lessons') or {}).values() for r in lesson.get('script_revisions') or [])
            results.append({"course_id": cid, "status": status, "lessons": result.get("verified_lessons", 0), "reference_revisions": references if mode != 'apply' else 0})
        except (CourseDocumentConflict, ValueError, KeyError, OSError) as exc:
            results.append({"course_id": cid, "status": "conflict", "reason": str(exc)})
    return {"mode": mode, "backup": str(backup) if backup else None, "courses": results}
