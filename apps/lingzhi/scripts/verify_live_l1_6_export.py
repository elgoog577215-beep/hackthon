"""Verify the approved lecture-six manuscript through preview and PPTX export."""

import hashlib
import io
import json
import re
import urllib.request
import zipfile
from pathlib import Path


COURSE_ID = "afb29754-6842-437b-af1b-5866bfb53b41"
LESSON_ID = "L1-6"
TASK_ID = "tlj-8cd70ab91a694a5882d7fb213bd20241"
SOURCE_ID = "tlsr-276e30d3240818214466eac4"
RELEASE = "0422bd72"
ROOT = Path("/opt/lingzhi/state/backend-data")
BASE = "http://127.0.0.1:7862"
COURSE_API = f"/api/teacher/courses/{COURSE_ID}"
PPT_API = f"{COURSE_API}/lessons/{LESSON_ID}/ppt-v6"


def emit(**value) -> None:
    print(json.dumps(value, ensure_ascii=True), flush=True)


def load_authoring() -> dict:
    return json.loads(
        (ROOT / "teacher_lesson_authoring" / f"{COURSE_ID}.json").read_text(
            encoding="utf-8"
        )
    )


def protected_digest(payload: dict) -> str:
    protected = {}
    for number in range(1, 6):
        lesson_id = f"L1-{number}"
        protected[lesson_id] = {
            "lesson": payload["lessons"][lesson_id],
            "jobs": {
                key: value
                for key, value in payload.get("jobs", {}).items()
                if value.get("lesson_unit_id") == lesson_id
            },
        }
    return hashlib.sha256(
        json.dumps(protected, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def handout_digest(payload: dict) -> str:
    lesson = payload["lessons"][LESSON_ID]
    if lesson.get("working_script_revision_id") != SOURCE_ID:
        raise ValueError("source_revision_changed")
    revision = next(
        item
        for item in lesson.get("script_revisions", [])
        if item.get("revision_id") == SOURCE_ID
    )
    return hashlib.sha256(
        json.dumps(revision.get("sections") or [], sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def main() -> None:
    course = json.loads(
        (ROOT / "courses" / f"{COURSE_ID}.json").read_text(encoding="utf-8")
    )
    owner_id = str(course.get("owner_id") or "")
    if not owner_id:
        raise ValueError("course_owner_unavailable")
    headers = {"X-User-Id": owner_id, "Content-Type": "application/json"}

    def request(path: str, payload: dict | None = None, *, timeout: int = 180):
        body = None if payload is None else json.dumps(payload).encode()
        return urllib.request.urlopen(
            urllib.request.Request(BASE + path, data=body, headers=headers),
            timeout=timeout,
        )

    def api(path: str, payload: dict | None = None) -> dict:
        with request(path, payload) as response:
            return json.load(response)

    health = api("/api/health")
    if not health.get("ready") or not str(health.get("version") or "").startswith(RELEASE):
        raise ValueError("approved_release_not_active")

    before = load_authoring()
    protected_before = protected_digest(before)
    handout_before = handout_digest(before)
    state = api(PPT_API + "/manuscript")["ppt_manuscript_state"]
    if state.get("task_id") != TASK_ID or state.get("source_script_revision_id") != SOURCE_ID:
        raise ValueError("approved_task_or_source_changed")
    if not state.get("can_export") or not state.get("manuscript"):
        raise ValueError("manuscript_not_exportable")

    revision = state["revision"]
    page_ids = [page["page_id"] for page in state["manuscript"]["pages"]]
    physical_pages = 0
    for offset in range(0, len(page_ids), 10):
        preview = api(
            PPT_API + "/preview",
            {
                "expected_manuscript_revision": revision,
                "page_ids": page_ids[offset : offset + 10],
            },
        )
        if preview.get("manuscript_revision") != revision:
            raise ValueError("preview_revision_changed")
        physical_pages += len(preview["deck"]["pages"])
    emit(
        event="all_pages_previewed",
        logical_pages=len(page_ids),
        physical_pages=physical_pages,
    )

    representation_id = ""
    with request(
        PPT_API + "/build/stream",
        {"expected_manuscript_revision": revision},
        timeout=1200,
    ) as response:
        for raw in response:
            if not raw.startswith(b"data: "):
                continue
            event = json.loads(raw[6:])
            if event.get("event") == "build_complete":
                representation_id = str(
                    (event.get("build") or {}).get("representation_id") or ""
                )
            if event.get("event") in {"build_paused", "build_cancelled"} or event.get(
                "failure"
            ):
                raise ValueError("export_build_stopped")
    if not representation_id:
        raise ValueError("export_build_incomplete")

    with request(PPT_API + f"/{representation_id}/export.pptx", timeout=300) as response:
        content = response.read()
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        slides = [
            name
            for name in archive.namelist()
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
        ]
        notes = [
            name
            for name in archive.namelist()
            if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", name)
        ]

    expected_pages = int(state["manuscript"]["page_count"])
    if not (
        len(slides) == len(notes) == physical_pages == expected_pages == len(page_ids)
    ):
        raise ValueError("export_page_or_note_count_mismatch")

    after = load_authoring()
    if protected_digest(after) != protected_before:
        raise ValueError("protected_lessons_changed")
    if handout_digest(after) != handout_before:
        raise ValueError("handout_changed")
    current = after["lessons"][LESSON_ID].get("ppt_manuscript") or {}
    if current.get("revision") != revision:
        raise ValueError("manuscript_revision_changed")

    emit(
        event="lecture_six_export_verified",
        task_id=TASK_ID,
        source_revision=SOURCE_ID,
        manuscript_revision=revision,
        representation_id=representation_id,
        pages=len(slides),
        notes=len(notes),
        pptx_bytes=len(content),
        pptx_sha256=hashlib.sha256(content).hexdigest(),
        handout_unchanged=True,
        protected_lessons_unchanged=True,
    )


if __name__ == "__main__":
    main()
