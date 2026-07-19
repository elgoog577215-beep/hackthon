#!/usr/bin/env python3
"""Safely migrate explicit course knowledge blueprints to the course-local v2 model."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from course_document import course_view_from_document  # noqa: E402
from course_knowledge_base import COURSE_KNOWLEDGE_BASE_SCHEMA  # noqa: E402
from course_knowledge_map import project_learning_assets_to_knowledge  # noqa: E402
from course_versioning import stable_hash  # noqa: E402


SNAPSHOT_PATTERN = re.compile(r"\.v\d+\.json$")
BACKUP_EXCLUDED_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".DS_Store",
    "tmp",
    "temp",
    "test",
    "tests",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _current_course_files(courses_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in courses_dir.glob("*.json")
        if not SNAPSHOT_PATTERN.search(path.name)
    )


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("课程文件顶层必须是 JSON 对象")
    return value


def _course_view(course: dict[str, Any]) -> dict[str, Any]:
    document = course.get("course_document")
    if isinstance(document, dict):
        return course_view_from_document(course, document)
    return deepcopy(course)


def _explicit_knowledge_summary(course_view: dict[str, Any]) -> dict[str, int]:
    section_count = 0
    group_count = 0
    point_count = 0
    for section in course_view.get("nodes") or []:
        if int(section.get("node_level") or 1) != 2:
            continue
        groups = [
            group
            for group in section.get("knowledge_structure") or []
            if isinstance(group, dict)
            and any(
                isinstance(point, dict) and str(point.get("name") or "").strip()
                for point in group.get("knowledge_points") or []
            )
        ]
        if not groups:
            continue
        section_count += 1
        group_count += len(groups)
        point_count += sum(
            1
            for group in groups
            for point in group.get("knowledge_points") or []
            if isinstance(point, dict) and str(point.get("name") or "").strip()
        )
    return {
        "section_count": section_count,
        "concept_group_count": group_count,
        "knowledge_point_count": point_count,
    }


def _blocking_messages(knowledge_base: dict[str, Any]) -> list[str]:
    quality = knowledge_base.get("quality_report") or {}
    return [
        str(item.get("message") or "").strip()
        for item in quality.get("blocking_issues") or quality.get("issues") or []
        if str(item.get("message") or "").strip()
    ]


def prepare_course_migration(
    course: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Return migrated data only when an explicit blueprint passes the v2 gate."""
    view = _course_view(course)
    summary = _explicit_knowledge_summary(view)
    course_id = str(course.get("course_id") or "")
    base_result: dict[str, Any] = {
        "course_id": course_id,
        "course_name": str(course.get("course_name") or ""),
        **summary,
    }
    if summary["knowledge_point_count"] == 0:
        return None, {
            **base_result,
            "status": "skipped",
            "reason": "没有显式知识结构，保留原课程并等待独立知识化",
        }

    working = deepcopy(view)
    working.pop("course_knowledge_base", None)
    working.pop("course_knowledge_map", None)
    assets = project_learning_assets_to_knowledge(
        working,
        course.get("learning_assets") or {},
    )
    knowledge_base = next(iter(assets.get("course_knowledge_base") or []), None)
    course_map = next(iter(assets.get("course_knowledge_map") or []), None)
    if not isinstance(knowledge_base, dict) or not isinstance(course_map, dict):
        return None, {
            **base_result,
            "status": "failed",
            "reason": "未编译出课程知识库或课程知识映射",
        }
    if (
        knowledge_base.get("schema_version") != COURSE_KNOWLEDGE_BASE_SCHEMA
        or knowledge_base.get("lifecycle_status") != "active"
    ):
        return None, {
            **base_result,
            "status": "skipped",
            "reason": "显式知识结构未通过 v2 发布质量门",
            "blocking_issues": _blocking_messages(knowledge_base)[:12],
        }

    migrated = deepcopy(course)
    migrated.pop("knowledge_library_binding", None)
    migrated["course_knowledge_base"] = knowledge_base
    migrated["course_knowledge_map"] = course_map
    migrated["course_knowledge_quality_report"] = knowledge_base.get("quality_report")
    migrated["learning_assets"] = assets
    migrated["learning_asset_bundle_revision_id"] = stable_hash(
        {
            "course_id": course_id,
            "knowledge_scope": "current_course_only",
            "assets": assets,
        },
        prefix="labr_",
    )
    migrated["course_knowledge_migration"] = {
        "schema_version": "course_local_knowledge_migration_v1",
        "knowledge_scope": "current_course_only",
        "source_schema_version": (
            (course.get("course_knowledge_base") or {}).get("schema_version")
        ),
        "target_schema_version": COURSE_KNOWLEDGE_BASE_SCHEMA,
        "source_course_fingerprint": knowledge_base.get("source_course_fingerprint"),
        "migrated_at": _now(),
        **summary,
    }
    return migrated, {
        **base_result,
        "status": "ready",
        "knowledge_base_id": knowledge_base.get("knowledge_base_id"),
        "revision_id": knowledge_base.get("revision_id"),
    }


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _backup_ignore(_directory: str, names: list[str]) -> set[str]:
    ignored = {
        name
        for name in names
        if name in BACKUP_EXCLUDED_NAMES or name.endswith((".tmp", ".pyc"))
    }
    return ignored


def create_backup(data_dir: Path, backup_root: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destination = backup_root / f"hackthon-data-{timestamp}"
    backup_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(data_dir, destination, ignore=_backup_ignore)
    file_count = sum(1 for path in destination.rglob("*") if path.is_file())
    _atomic_write(destination / "backup-manifest.json", {
        "schema_version": "hackthon_data_backup_v1",
        "source": str(data_dir.resolve()),
        "created_at": _now(),
        "file_count": file_count,
        "excluded_names": sorted(BACKUP_EXCLUDED_NAMES),
    })
    return destination


def run_migration(
    *,
    data_dir: Path,
    backup_root: Path,
    apply: bool,
) -> dict[str, Any]:
    courses_dir = data_dir / "courses"
    if not courses_dir.is_dir():
        raise FileNotFoundError(f"课程目录不存在：{courses_dir}")

    prepared: list[tuple[Path, dict[str, Any]]] = []
    results: list[dict[str, Any]] = []
    for path in _current_course_files(courses_dir):
        try:
            course = _load_json(path)
            migrated, result = prepare_course_migration(course)
            result["file"] = path.name
            results.append(result)
            if migrated is not None:
                prepared.append((path, migrated))
        except Exception as exc:
            results.append({
                "file": path.name,
                "status": "invalid",
                "reason": str(exc),
            })

    backup_dir: Path | None = None
    if apply and prepared:
        backup_dir = create_backup(data_dir, backup_root)
        for path, migrated in prepared:
            _atomic_write(path, migrated)
        for result in results:
            if result.get("status") == "ready":
                result["status"] = "migrated"

    status_counts = {
        status: sum(item.get("status") == status for item in results)
        for status in {"ready", "migrated", "skipped", "failed", "invalid"}
    }
    return {
        "schema_version": "course_local_knowledge_migration_report_v1",
        "mode": "apply" if apply else "dry_run",
        "knowledge_scope": "current_course_only",
        "data_dir": str(data_dir.resolve()),
        "backup_dir": str(backup_dir) if backup_dir else None,
        "current_course_file_count": len(results),
        "status_counts": status_counts,
        "results": results,
        "completed_at": _now(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="备份真实数据，并把已有显式知识结构迁移为单课程知识库 v2。",
    )
    parser.add_argument(
        "--data-dir",
        default=str(BACKEND_DIR / "data"),
        help="包含 courses/ 的数据目录。",
    )
    parser.add_argument(
        "--backup-root",
        default=str(PROJECT_DIR.parent / "backups"),
        help="应用迁移前保存完整数据备份的目录。",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真正写入；默认只做只读预检。",
    )
    args = parser.parse_args()
    report = run_migration(
        data_dir=Path(args.data_dir).expanduser(),
        backup_root=Path(args.backup_root).expanduser(),
        apply=bool(args.apply),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
