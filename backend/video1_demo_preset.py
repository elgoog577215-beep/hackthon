"""Deterministic local preset for the Video 1 same-source PPT demo.

The preset reuses the exact curated course identity used by Video 2. A reset
recreates the canonical course, learning assets, and all same-source teaching
representations without calling an external model.

Run the reset while the backend is stopped.  That keeps the file-level reset
atomic from the application's point of view and avoids stale in-process
repository state during a recording rehearsal.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
from typing import Any

from course_document import CourseDocument, refresh_document_revision
from course_revisions import revision_vector_for_document
from representation_compiler import compile_core_representations
from storage import Storage
from teaching_representations import TeachingRepresentationRepository
from video2_demo_preset import (
    COURSE_ID as SHARED_COURSE_ID,
    COURSE_TITLE as SHARED_COURSE_TITLE,
    PPT_BASELINE_GOAL,
    PPT_TARGET_GOAL,
    TARGET_SECTION_ID,
    build_video2_course_document,
    build_video2_course_envelope,
    prepare_video2_demo,
)


COURSE_ID = SHARED_COURSE_ID
COURSE_TITLE = SHARED_COURSE_TITLE
BASELINE_GOAL = PPT_BASELINE_GOAL
TARGET_GOAL = PPT_TARGET_GOAL


def build_video1_course_document() -> CourseDocument:
    """Return the same curated matrix course consumed by Video 2."""
    document = build_video2_course_document().model_copy(deep=True)
    document.course_id = COURSE_ID
    document.title = COURSE_TITLE
    target = next(
        section
        for section in document.sections
        if section.section_id == TARGET_SECTION_ID
    )
    target.learning_objective = BASELINE_GOAL
    target.attributes = {
        **target.attributes,
        "demo_baseline_goal": BASELINE_GOAL,
        "demo_target_goal": TARGET_GOAL,
    }
    return refresh_document_revision(document)


def build_video1_course_envelope() -> dict[str, Any]:
    """Build the canonical course payload consumed by the normal PPT route."""
    envelope = deepcopy(build_video2_course_envelope())
    document = build_video1_course_document()
    envelope.update({
        "course_id": COURSE_ID,
        "course_name": COURSE_TITLE,
        "course_document": document.model_dump(mode="json"),
        "course_document_revision": document.document_revision,
        "course_revision_vector": revision_vector_for_document(document).model_dump(mode="json"),
        "current_course_version_id": document.document_revision,
        "course_operation_log": [],
        "generation_schema_version": "manual_video1_demo_v1",
        "generation_source": "curated_local_preset",
        "demo_metadata": {
            "schema_version": "video_demo_preset_v1",
            "video": "结构化同源",
            "target_section_id": TARGET_SECTION_ID,
            "baseline_goal": BASELINE_GOAL,
            "target_goal": TARGET_GOAL,
            "external_model_required": False,
        },
    })
    return envelope


def prepare_video1_demo(data_dir: str | Path) -> dict[str, Any]:
    """Reset the shared course and return its ready-to-edit slide deck."""
    root = Path(data_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    shared = prepare_video2_demo(root)
    return {
        **shared,
        "course_id": COURSE_ID,
        "course_title": COURSE_TITLE,
        "target_section_id": TARGET_SECTION_ID,
        "target_slide_unit_id": shared["target_slide_unit_id"],
        "target_slide_number": shared["target_slide_number"],
        "baseline_goal": BASELINE_GOAL,
        "target_goal": TARGET_GOAL,
        "relative_url": shared["relative_ppt_url"],
    }
    _clear_previous_demo_state(root)

    course = build_video1_course_envelope()
    Storage(str(root)).save_course_sync(COURSE_ID, course)

    document = CourseDocument.model_validate(course["course_document"])
    repository = TeachingRepresentationRepository(root / "teaching_representations")
    build = compile_core_representations(document, course, repository)
    registry = repository.load(COURSE_ID)
    slide_representation = next(
        item
        for item in registry.representations
        if item.representation_type == "slide_deck"
    )
    slide_spec = next(
        item for item in registry.specs if item.spec_id == slide_representation.spec_id
    )
    slides = slide_spec.payload["content"]["slides"]
    target_index = next(
        index
        for index, slide in enumerate(slides)
        if slide.get("section_id") == TARGET_SECTION_ID
    )
    target_slide = slides[target_index]
    if target_slide.get("key_message") != BASELINE_GOAL:
        raise RuntimeError("Video 1 target slide did not compile with the expected baseline goal")

    return {
        "course_id": COURSE_ID,
        "course_title": COURSE_TITLE,
        "target_section_id": TARGET_SECTION_ID,
        "target_slide_unit_id": target_slide["unit_id"],
        "target_slide_number": target_index + 1,
        "baseline_goal": BASELINE_GOAL,
        "target_goal": TARGET_GOAL,
        "course_revision": document.document_revision,
        "representation_registry_revision": registry.registry_revision,
        "compiled_representation_count": len(build["representations"]),
        "course_file": str(root / "courses" / f"{COURSE_ID}.json"),
        "relative_url": f"/course/{COURSE_ID}/ppt",
        "external_model_required": False,
    }


def _clear_previous_demo_state(data_dir: Path) -> None:
    """Delete only artifacts that declare ownership by the Video 1 course."""
    courses_dir = data_dir / "courses"
    if courses_dir.exists():
        for path in courses_dir.glob(f"{COURSE_ID}*.json"):
            path.unlink()

    for directory_name in (
        "course_versions",
        "generation_workspaces",
        "learning_assets",
        "question_banks",
    ):
        owned_directory = data_dir / directory_name / COURSE_ID
        if owned_directory.exists():
            shutil.rmtree(owned_directory)
        _remove_course_scoped_json_files(data_dir / directory_name)

    # Teaching registries and proposals both use opaque hashed filenames.  The
    # payload, not the filename, is the authoritative ownership boundary.
    for directory_name in (
        "teaching_representations",
        "change_proposals",
        "block_regeneration_candidates",
    ):
        _remove_course_scoped_json_files(data_dir / directory_name)


def _remove_course_scoped_json_files(directory: Path) -> None:
    if not directory.exists():
        return
    for path in directory.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and str(payload.get("course_id") or "") == COURSE_ID:
            path.unlink()


__all__ = [
    "BASELINE_GOAL",
    "COURSE_ID",
    "COURSE_TITLE",
    "TARGET_GOAL",
    "TARGET_SECTION_ID",
    "build_video1_course_document",
    "build_video1_course_envelope",
    "prepare_video1_demo",
]
