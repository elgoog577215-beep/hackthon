#!/usr/bin/env python3
"""Repair empty local teacher drafts created under a transient learner id.

The command is dry-run by default. ``--apply`` first creates a physical backup
outside the repository, then changes only empty, never-started teacher drafts.
Drafts with generated content, an active/history job, or conflicting non-empty
file packages are reported and left untouched.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_ROOT = REPOSITORY_ROOT / "backend" / "data"
DEFAULT_TARGET_OWNER = "teacher-local-workbench-v1"


@dataclass(frozen=True)
class DraftRepair:
    course_path: Path
    course_id: str
    course_name: str
    source_owner: str
    package_paths: tuple[Path, ...]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _is_empty_package(package: dict[str, Any]) -> bool:
    return not any(
        package.get(key)
        for key in ("assets", "imports", "entries", "relationships")
    )


def _is_safe_empty_draft(course: dict[str, Any]) -> bool:
    document = course.get("course_document") or {}
    return (
        course.get("authoring_surface") == "teacher"
        and course.get("course_status") == "draft"
        and not str(course.get("generation_job_id") or "").strip()
        and not (course.get("nodes") or [])
        and not (document.get("sections") or [])
        and not (document.get("blocks") or [])
    )


def discover_repairs(
    data_root: Path,
    *,
    target_owner: str,
) -> tuple[list[DraftRepair], list[str]]:
    courses_root = data_root / "courses"
    spaces_root = data_root / "teacher_course_spaces"
    packages_by_course: dict[str, list[Path]] = {}
    for manifest in spaces_root.glob("tcs-*/manifest.json"):
        try:
            package = _read_json(manifest)
        except (OSError, json.JSONDecodeError):
            continue
        course_id = str(package.get("course_id") or "").strip()
        if course_id:
            packages_by_course.setdefault(course_id, []).append(manifest)

    repairs: list[DraftRepair] = []
    skipped: list[str] = []
    for course_path in courses_root.glob("*.json"):
        if ".v" in course_path.stem:
            continue
        try:
            course = _read_json(course_path)
        except (OSError, json.JSONDecodeError):
            continue
        source_owner = str(course.get("owner_id") or "").strip()
        if not source_owner.startswith("learner_"):
            continue
        course_id = str(course.get("course_id") or course_path.stem).strip()
        if not _is_safe_empty_draft(course):
            skipped.append(f"{course_id}: 非空草稿或生成已经开始")
            continue
        package_paths = tuple(packages_by_course.get(course_id, []))
        source_packages = [
            path for path in package_paths
            if str(_read_json(path).get("owner_id") or "") == source_owner
        ]
        target_packages = [
            path for path in package_paths
            if str(_read_json(path).get("owner_id") or "") == target_owner
        ]
        foreign_packages = [
            path for path in package_paths
            if str(_read_json(path).get("owner_id") or "") not in {source_owner, target_owner}
        ]
        if foreign_packages:
            skipped.append(f"{course_id}: 存在第三方所有者的课程文件包")
            continue
        if len(source_packages) > 1 or len(target_packages) > 1:
            skipped.append(f"{course_id}: 同一所有者存在多个课程文件包")
            continue
        if source_packages and target_packages:
            source = _read_json(source_packages[0])
            target = _read_json(target_packages[0])
            if not _is_empty_package(source) and not _is_empty_package(target):
                skipped.append(f"{course_id}: 新旧文件包都含内容，不能自动合并")
                continue
        repairs.append(DraftRepair(
            course_path=course_path,
            course_id=course_id,
            course_name=str(course.get("course_name") or "未命名课程"),
            source_owner=source_owner,
            package_paths=package_paths,
        ))
    return repairs, skipped


def _backup_repairs(repairs: list[DraftRepair], backup_root: Path) -> None:
    backup_root.mkdir(parents=True, exist_ok=False)
    for repair in repairs:
        course_target = backup_root / "courses" / repair.course_path.name
        course_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repair.course_path, course_target)
        for manifest in repair.package_paths:
            package_root = manifest.parent
            shutil.copytree(
                package_root,
                backup_root / "teacher_course_spaces" / package_root.name,
            )


def apply_repairs(
    repairs: list[DraftRepair],
    *,
    target_owner: str,
    backup_root: Path,
) -> None:
    _backup_repairs(repairs, backup_root)
    for repair in repairs:
        course = _read_json(repair.course_path)
        course["owner_id"] = target_owner
        course["ownership_reconciled_at"] = datetime.now(timezone.utc).isoformat()
        course["ownership_reconciled_from"] = repair.source_owner

        source_packages: list[Path] = []
        target_packages: list[Path] = []
        for manifest in repair.package_paths:
            owner_id = str(_read_json(manifest).get("owner_id") or "")
            if owner_id == repair.source_owner:
                source_packages.append(manifest)
            elif owner_id == target_owner:
                target_packages.append(manifest)

        if source_packages and target_packages:
            source_path, target_path = source_packages[0], target_packages[0]
            source = _read_json(source_path)
            target = _read_json(target_path)
            if _is_empty_package(source):
                shutil.rmtree(source_path.parent)
            elif _is_empty_package(target):
                shutil.rmtree(target_path.parent)
                source["owner_id"] = target_owner
                source["updated_at"] = datetime.now(timezone.utc).isoformat()
                _write_json(source_path, source)
        elif source_packages:
            source = _read_json(source_packages[0])
            source["owner_id"] = target_owner
            source["updated_at"] = datetime.now(timezone.utc).isoformat()
            _write_json(source_packages[0], source)

        _write_json(repair.course_path, course)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--target-owner", default=DEFAULT_TARGET_OWNER)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", type=Path)
    args = parser.parse_args()

    repairs, skipped = discover_repairs(
        args.data_root.resolve(),
        target_owner=args.target_owner,
    )
    for repair in repairs:
        print(
            f"REPAIR {repair.course_id} {repair.course_name!r}: "
            f"{repair.source_owner} -> {args.target_owner}"
        )
    for reason in skipped:
        print(f"SKIP {reason}")
    if not args.apply:
        print(f"DRY-RUN: {len(repairs)} repair(s), {len(skipped)} skipped")
        return 0
    if not repairs:
        print("APPLIED: no changes")
        return 0

    backup_root = args.backup_dir
    if backup_root is None:
        backup_root = Path(tempfile.mkdtemp(prefix="lingzhi-teacher-draft-backup-"))
        backup_root.rmdir()
    backup_root = backup_root.resolve()
    try:
        backup_root.relative_to(REPOSITORY_ROOT)
    except ValueError:
        pass
    else:
        raise SystemExit("backup directory must be outside the repository")

    apply_repairs(
        repairs,
        target_owner=args.target_owner,
        backup_root=backup_root,
    )
    print(f"APPLIED: {len(repairs)} repair(s); backup={backup_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
