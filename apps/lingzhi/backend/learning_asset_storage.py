"""Immutable storage for compiled learning-asset bundles."""

from __future__ import annotations

import json
import os
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

from course_versioning import stable_hash
from storage import DATA_DIR


class LearningAssetRepository:
    def __init__(self, root_dir: str | Path | None = None) -> None:
        self.root_dir = Path(root_dir or Path(DATA_DIR) / "learning_assets")
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def save_bundle(
        self,
        course_id: str,
        bundle: dict[str, Any],
        *,
        activate: bool = True,
    ) -> dict[str, Any]:
        bundle_id = stable_hash(bundle.get("assets") or {}, prefix="lab_")
        stored = deepcopy(bundle)
        stored["bundle_revision_id"] = bundle_id
        directory = self.root_dir / course_id
        path = directory / "revisions" / f"{bundle_id}.json"
        if not path.exists():
            self._atomic_write(path, stored)
        if activate:
            self.activate_bundle(course_id, bundle_id)
        return stored

    def activate_bundle(self, course_id: str, bundle_revision_id: str) -> None:
        path = self.root_dir / course_id / "revisions" / f"{bundle_revision_id}.json"
        if not path.exists():
            raise KeyError(f"Unknown learning asset bundle: {bundle_revision_id}")
        self._atomic_write(
            self.root_dir / course_id / "current.json",
            {"bundle_revision_id": bundle_revision_id},
        )

    def load_bundle(self, course_id: str, bundle_revision_id: str | None = None) -> dict[str, Any] | None:
        directory = self.root_dir / course_id
        if bundle_revision_id is None:
            pointer = directory / "current.json"
            if not pointer.exists():
                return None
            bundle_revision_id = self._read(pointer).get("bundle_revision_id")
        path = directory / "revisions" / f"{bundle_revision_id}.json"
        return self._read(path) if path.exists() else None

    def delete_bundle(self, course_id: str, bundle_revision_id: str) -> bool:
        """Delete an inactive bundle; the active bundle is always preserved."""
        directory = self.root_dir / course_id
        pointer = directory / "current.json"
        if pointer.exists() and self._read(pointer).get("bundle_revision_id") == bundle_revision_id:
            return False
        path = directory / "revisions" / f"{bundle_revision_id}.json"
        if not path.exists():
            return False
        path.unlink()
        return True

    def delete_course(self, course_id: str) -> bool:
        directory = self.root_dir / course_id
        if not directory.exists():
            return False
        shutil.rmtree(directory)
        return True

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise ValueError("Learning asset repository expected a JSON object")
        return value

    @staticmethod
    def _atomic_write(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        try:
            with temp.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()


learning_asset_repository = LearningAssetRepository()


__all__ = ["LearningAssetRepository", "learning_asset_repository"]
