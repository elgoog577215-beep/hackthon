#!/usr/bin/env python3
"""Remove retired whole-course teaching-plan workbench data after backup.

The command is read-only by default. ``--apply`` writes only files that contain
the retired ``teaching_plan_workbench`` envelope or an unshipped legacy import
marker. Current ``course_teaching_plan_v3`` data and new per-lesson revisions
are intentionally preserved because the active generation chain uses them.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_ROOT = REPOSITORY_ROOT / "backend" / "data"
LEGACY_WORKBENCH_KEY = "teaching_plan_workbench"
LEGACY_IMPORT_SOURCE = "legacy_workbench_import"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("JSON 顶层必须是对象")
    return value


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _clean_course(
    value: dict[str, Any],
) -> tuple[dict[str, Any] | None, int, int]:
    if LEGACY_WORKBENCH_KEY not in value:
        return None, 0, 0
    cleaned = deepcopy(value)
    cleaned.pop(LEGACY_WORKBENCH_KEY, None)
    return cleaned, 0, 0


def _is_legacy_import(revision: Any) -> bool:
    return isinstance(revision, dict) and (
        str(revision.get("generation_source") or "") == LEGACY_IMPORT_SOURCE
        or bool(str(revision.get("legacy_source_revision_id") or ""))
    )


def _select_current_revision(
    value: dict[str, Any],
    lesson: dict[str, Any],
    remaining: list[dict[str, Any]],
) -> None:
    current = remaining[-1] if remaining else None
    current_revision_id = str((current or {}).get("revision_id") or "")
    lesson["working_revision_id"] = current_revision_id
    if not current_revision_id:
        lesson["source_state"] = "missing"
        lesson["source_state_reason"] = "legacy_plan_removed"
        return

    current_outline = str(value.get("outline_revision_id") or "")
    source_outline = str((current or {}).get("source_outline_revision_id") or "")
    arrangement_revision = str(
        (lesson.get("arrangement") or {}).get("working_revision_id") or ""
    )
    source_arrangement = str(
        (current or {}).get("source_arrangement_revision_id") or ""
    )
    is_current = (
        (not current_outline or not source_outline or source_outline == current_outline)
        and (
            not source_arrangement
            or not arrangement_revision
            or source_arrangement == arrangement_revision
        )
    )
    lesson["source_state"] = "current" if is_current else "stale"
    if is_current:
        lesson.pop("source_state_reason", None)
    else:
        lesson["source_state_reason"] = "source_changed"


def _clean_authoring(
    value: dict[str, Any],
) -> tuple[dict[str, Any] | None, int, int]:
    lessons = value.get("lessons")
    if not isinstance(lessons, dict):
        return None, 0, 0
    cleaned = deepcopy(value)
    removed_count = 0
    removed_field_count = 0

    def drop(mapping: dict[str, Any], field: str) -> None:
        nonlocal removed_field_count
        if field in mapping:
            mapping.pop(field, None)
            removed_field_count += 1

    for draft in cleaned.get("outline_material_drafts") or []:
        if isinstance(draft, dict):
            drop(draft, "confirmation_required")

    for lesson in (cleaned.get("lessons") or {}).values():
        if not isinstance(lesson, dict):
            continue
        drop(lesson, "confirmed_revision_id")
        drop(lesson, "script_confirmation")
        arrangement = lesson.get("arrangement")
        if isinstance(arrangement, dict):
            drop(arrangement, "confirmed_revision_id")
            for revision in arrangement.get("revisions") or []:
                if not isinstance(revision, dict):
                    continue
                for field in ("status", "confirmed", "confirmed_at"):
                    drop(revision, field)
        for drafts in (lesson.get("material_drafts") or {}).values():
            if not isinstance(drafts, list):
                continue
            for draft in drafts:
                if isinstance(draft, dict):
                    drop(draft, "confirmation_required")
        revisions = [
            item for item in lesson.get("revisions") or []
            if isinstance(item, dict)
        ]
        remaining = [item for item in revisions if not _is_legacy_import(item)]
        for revision in remaining:
            drop(revision, "status")
            drop(revision, "confirmed_at")
        removed_here = len(revisions) - len(remaining)
        marker_removed = "legacy_plan_import" in lesson
        drop(lesson, "legacy_plan_import")
        if not removed_here and not marker_removed:
            continue
        removed_count += removed_here
        lesson["revisions"] = remaining
        if str(lesson.get("working_revision_id") or "") not in {
            str(item.get("revision_id") or "") for item in remaining
        }:
            _select_current_revision(cleaned, lesson, remaining)
    if not removed_count and cleaned == value:
        return None, 0, 0
    return cleaned, removed_count, removed_field_count


def _teacher_outline_result_ready(course_data: Any) -> bool:
    if not isinstance(course_data, dict) or course_data.get("outline_framework_only") is True:
        return False
    outline_stage = (
        (course_data.get("generation_stage_artifacts") or {}).get("outline")
        or {}
    )
    if str(outline_stage.get("strategy") or "") in {
        "teacher_framework_then_detail_batches",
        "teacher_framework_then_lecture_tasks",
    }:
        if str(outline_stage.get("course_contract_status") or "") != "completed":
            return False
        batches = [
            item
            for item in (outline_stage.get("detail_batches") or {}).values()
            if isinstance(item, dict)
        ]
        if not batches or any(str(item.get("status") or "") != "completed" for item in batches):
            return False
        if str(outline_stage.get("status") or "") not in {
            "completed",
            "completed_with_warnings",
        }:
            return False
    nodes = [item for item in course_data.get("nodes") or [] if isinstance(item, dict)]
    return bool(nodes) and all(
        str(item.get("node_id") or "").strip()
        and str(item.get("node_name") or "").strip()
        for item in nodes
    )


def _load_workspace_course(data_root: Path, task: dict[str, Any]) -> dict[str, Any] | None:
    workspace_id = str(task.get("workspace_id") or "")
    if workspace_id:
        path = data_root / "generation_workspaces" / f"{workspace_id}.json"
        try:
            workspace = _read_json(path)
        except (OSError, json.JSONDecodeError, ValueError):
            return None
        course_data = workspace.get("course_data")
        return course_data if isinstance(course_data, dict) else None
    course_id = str(task.get("course_id") or "")
    if not course_id:
        return None
    try:
        return _read_json(data_root / "courses" / f"{course_id}.json")
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _clean_generation_jobs(
    value: dict[str, Any],
    data_root: Path,
) -> tuple[dict[str, Any] | None, int, int]:
    cleaned = deepcopy(value)
    removed_field_count = 0
    normalized_task_count = 0
    for task in cleaned.values():
        if not isinstance(task, dict) or task.get("type") != "teacher_outline_generation":
            continue
        for field in ("guided_workflow", "blueprint_confirmed", "blueprint_revision_id"):
            if field in task:
                task.pop(field, None)
                removed_field_count += 1
        if task.get("status") == "waiting_for_review":
            course_data = _load_workspace_course(data_root, task)
            if _teacher_outline_result_ready(course_data):
                task.update({
                    "status": "completed",
                    "phase": "teacher_outline_ready",
                    "current_phase": "teacher_outline_ready",
                    "progress": 100,
                    "phase_progress": 100,
                    "message": "课程大纲已生成，可选择任一讲生成教案",
                    "outline_detail_requested": False,
                    "current_nodes": [],
                    "current_node_name": "",
                })
                normalized_task_count += 1
            elif isinstance(course_data, dict) and (
                course_data.get("outline_framework_only") is True
                or bool(course_data.get("nodes"))
                or bool(course_data.get("course_outline"))
            ):
                task.update({
                    "status": "waiting_for_input",
                    "phase": "outline_framework_ready",
                    "current_phase": "outline_framework_ready",
                    "phase_progress": 100,
                    "message": "轻量讲次方案已生成，可修改后继续生成完整大纲",
                    "outline_detail_requested": False,
                    "current_nodes": [],
                    "current_node_name": "",
                })
                normalized_task_count += 1
    if cleaned == value:
        return None, 0, 0
    return cleaned, normalized_task_count, removed_field_count


def _candidate_files(data_root: Path) -> list[tuple[str, Path]]:
    candidates = [
        *(("course", path) for path in sorted((data_root / "courses").glob("*.json"))),
        *(("authoring", path) for path in sorted(
            (data_root / "teacher_lesson_authoring").glob("*.json")
        )),
    ]
    jobs_path = data_root / "generation_jobs.json"
    if jobs_path.is_file():
        candidates.append(("jobs", jobs_path))
    return candidates


def _create_backup(
    data_root: Path,
    files: list[Path],
    backup_root: Path,
) -> Path:
    try:
        backup_root.resolve().relative_to(REPOSITORY_ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("备份目录必须位于 Git 仓库之外")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destination = backup_root / f"legacy-teaching-plan-backup-{stamp}"
    destination.mkdir(parents=True, exist_ok=False)
    manifest_files: list[str] = []
    for source in files:
        relative = source.relative_to(data_root)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        manifest_files.append(str(relative))
    _atomic_write(destination / "backup-manifest.json", {
        "schema_version": "legacy_teaching_plan_backup_v1",
        "source": str(data_root.resolve()),
        "created_at": _now(),
        "files": manifest_files,
    })
    return destination


def run_cleanup(
    *,
    data_root: Path,
    backup_root: Path,
    apply: bool,
) -> dict[str, Any]:
    data_root = data_root.resolve()
    prepared: list[tuple[Path, dict[str, Any]]] = []
    results: list[dict[str, Any]] = []
    for kind, path in _candidate_files(data_root):
        try:
            original = _read_json(path)
            if kind == "course":
                cleaned, removed_count, removed_field_count = _clean_course(original)
            elif kind == "authoring":
                cleaned, removed_count, removed_field_count = _clean_authoring(original)
            else:
                cleaned, removed_count, removed_field_count = _clean_generation_jobs(
                    original,
                    data_root,
                )
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            results.append({
                "file": str(path.relative_to(data_root)),
                "kind": kind,
                "status": "invalid",
                "reason": str(exc),
            })
            continue
        if cleaned is None:
            continue
        prepared.append((path, cleaned))
        results.append({
            "file": str(path.relative_to(data_root)),
            "kind": kind,
            "status": "ready",
            "removed_workbench_envelope_count": int(
                kind == "course" and LEGACY_WORKBENCH_KEY in original
            ),
            "removed_revision_count": removed_count if kind != "jobs" else 0,
            "removed_retired_field_count": removed_field_count,
            "normalized_teacher_outline_task_count": (
                removed_count if kind == "jobs" else 0
            ),
        })

    backup_dir: Path | None = None
    if apply and prepared:
        backup_dir = _create_backup(
            data_root,
            [path for path, _value in prepared],
            backup_root.resolve(),
        )
        for path, cleaned in prepared:
            _atomic_write(path, cleaned)
        for result in results:
            if result["status"] == "ready":
                result["status"] = "cleaned"

    return {
        "schema_version": "legacy_teaching_plan_cleanup_report_v1",
        "mode": "apply" if apply else "dry_run",
        "data_root": str(data_root),
        "backup_dir": str(backup_dir) if backup_dir else None,
        "affected_file_count": len(prepared),
        "removed_workbench_envelope_count": sum(
            int(item.get("removed_workbench_envelope_count") or 0)
            for item in results
        ),
        "removed_legacy_revision_count": sum(
            int(item.get("removed_revision_count") or 0) for item in results
        ),
        "removed_retired_field_count": sum(
            int(item.get("removed_retired_field_count") or 0) for item in results
        ),
        "normalized_teacher_outline_task_count": sum(
            int(item.get("normalized_teacher_outline_task_count") or 0)
            for item in results
        ),
        "results": results,
        "completed_at": _now(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument(
        "--backup-root",
        type=Path,
        default=REPOSITORY_ROOT.parent / "backups",
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    report = run_cleanup(
        data_root=args.data_root,
        backup_root=args.backup_root,
        apply=bool(args.apply),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
