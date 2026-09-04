#!/usr/bin/env python3
"""Create and restore-verify a versioned Lingzhi data backup."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

BACKUP_SCHEMA_VERSION = "lingzhi_data_backup_v1"
DATA_ROOT = "backend-data"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _regular_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"backup_source_symlink:{path.relative_to(root)}")
        if path.is_file():
            files.append(path)
    return files


def _manifest(data_root: Path, release_version: str) -> dict[str, Any]:
    files = [
        {
            "path": path.relative_to(data_root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in _regular_files(data_root)
    ]
    return {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "source_release_version": release_version,
        "created_at": datetime.now(UTC).isoformat(),
        "data_root": DATA_ROOT,
        "file_count": len(files),
        "files": files,
    }


def _safe_member_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("backup_archive_unsafe_path")
    if not path.parts or path.parts[0] not in {DATA_ROOT, "backup-manifest.json"}:
        raise ValueError("backup_archive_unknown_root")
    return path


def _extract_regular_archive(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            relative = _safe_member_path(member.name)
            target = destination.joinpath(*relative.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ValueError("backup_archive_non_regular_entry")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = bundle.extractfile(member)
            if source is None:
                raise ValueError("backup_archive_member_unreadable")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def verify_backup(archive: Path, *, temporary_parent: Path | None = None) -> dict[str, Any]:
    if not archive.is_file():
        raise ValueError("backup_archive_missing")
    temporary_parent = temporary_parent or archive.parent
    with tempfile.TemporaryDirectory(
        prefix="lingzhi-backup-restore-check-",
        dir=temporary_parent,
    ) as temporary:
        restore_root = Path(temporary)
        _extract_regular_archive(archive, restore_root)
        manifest_path = restore_root / "backup-manifest.json"
        data_root = restore_root / DATA_ROOT
        with manifest_path.open(encoding="utf-8") as handle:
            manifest = json.load(handle)
        if manifest.get("schema_version") != BACKUP_SCHEMA_VERSION:
            raise ValueError("backup_manifest_schema_invalid")
        if not str(manifest.get("source_release_version") or ""):
            raise ValueError("backup_manifest_release_missing")
        expected_files = manifest.get("files")
        if not isinstance(expected_files, list):
            raise ValueError("backup_manifest_files_invalid")
        if int(manifest.get("file_count") or 0) != len(expected_files):
            raise ValueError("backup_manifest_file_count_mismatch")
        expected_by_path = {
            str(item.get("path") or ""): item
            for item in expected_files
            if isinstance(item, dict) and str(item.get("path") or "")
        }
        actual_files = {
            path.relative_to(data_root).as_posix(): path
            for path in _regular_files(data_root)
        }
        if set(actual_files) != set(expected_by_path):
            raise ValueError("backup_manifest_file_set_mismatch")
        for relative, path in actual_files.items():
            expected = expected_by_path[relative]
            if path.stat().st_size != int(expected.get("size_bytes") or 0):
                raise ValueError(f"backup_file_size_mismatch:{relative}")
            if _sha256(path) != str(expected.get("sha256") or ""):
                raise ValueError(f"backup_file_checksum_mismatch:{relative}")

        json_files_checked = 0
        for path in sorted(data_root.rglob("*.json")):
            with path.open(encoding="utf-8") as handle:
                value = json.load(handle)
            if not isinstance(value, (dict, list)):
                raise ValueError(
                    f"backup_repository_json_root_invalid:{path.relative_to(data_root)}"
                )
            json_files_checked += 1
        jobs = data_root / "generation_jobs.json"
        if jobs.exists():
            with jobs.open(encoding="utf-8") as handle:
                if not isinstance(json.load(handle), dict):
                    raise ValueError("backup_generation_job_index_invalid")
        checksum_path = archive.with_name(f"{archive.name}.sha256")
        if checksum_path.exists():
            recorded_checksum = checksum_path.read_text(encoding="utf-8").split()[0]
            if recorded_checksum != _sha256(archive):
                raise ValueError("backup_archive_checksum_mismatch")
        return {
            "schema_version": BACKUP_SCHEMA_VERSION,
            "source_release_version": manifest["source_release_version"],
            "file_count": len(actual_files),
            "json_files_checked": json_files_checked,
            "verified_in_isolation": True,
        }


def create_backup(source: Path, output: Path, release_version: str) -> dict[str, Any]:
    source = source.resolve(strict=True)
    output = output.resolve(strict=False)
    if not source.is_dir():
        raise ValueError("backup_source_not_directory")
    if output == source or source in output.parents:
        raise ValueError("backup_output_inside_source")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_archive = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    checksum_path = output.with_name(f"{output.name}.sha256")
    temporary_checksum = checksum_path.with_name(
        f".{checksum_path.name}.{os.getpid()}.tmp"
    )
    if output.exists() or checksum_path.exists():
        raise ValueError("backup_output_already_exists")
    try:
        with tempfile.TemporaryDirectory(
            prefix="lingzhi-backup-stage-",
            dir=output.parent,
        ) as temporary:
            staging = Path(temporary)
            staged_data = staging / DATA_ROOT
            _regular_files(source)
            shutil.copytree(source, staged_data)
            manifest = _manifest(staged_data, release_version)
            (staging / "backup-manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with tarfile.open(temporary_archive, "w:gz") as bundle:
                bundle.add(staging / "backup-manifest.json", arcname="backup-manifest.json")
                bundle.add(staged_data, arcname=DATA_ROOT)
        os.replace(temporary_archive, output)
        verification = verify_backup(output, temporary_parent=output.parent)
        archive_sha256 = _sha256(output)
        temporary_checksum.write_text(
            f"{archive_sha256}  {output.name}\n",
            encoding="utf-8",
        )
        os.replace(temporary_checksum, checksum_path)
        return {
            **verification,
            "archive": str(output),
            "archive_sha256": archive_sha256,
            "checksum_file": str(checksum_path),
        }
    except Exception:
        temporary_archive.unlink(missing_ok=True)
        temporary_checksum.unlink(missing_ok=True)
        output.unlink(missing_ok=True)
        checksum_path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--source", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--release-version", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    result = (
        create_backup(args.source, args.output, args.release_version)
        if args.command == "create"
        else verify_backup(args.archive)
    )
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
