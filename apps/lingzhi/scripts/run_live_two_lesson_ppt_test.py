"""Run two approved production PPTs only through the formal website API."""

import hashlib
import io
import json
import re
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path


COURSE_ID = "2b3f4d8c-2af7-4133-a4f2-1060e8e9f54b"
LESSONS = (
    ("L1-1", "tlsr-1097b09406b5080ff21e0afd"),
    ("L1-2", "tlsr-a209b5939e3dba285598986c"),
)
ROOT = Path("/opt/lingzhi/state/backend-data")
BASE = "http://127.0.0.1:7862"
COURSE_API = f"/api/teacher/courses/{COURSE_ID}"


def emit(**value) -> None:
    print(json.dumps(value, ensure_ascii=True), flush=True)


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

    def api(path: str, payload: dict | None = None, *, timeout: int = 180) -> dict:
        with request(path, payload, timeout=timeout) as response:
            return json.load(response)

    def manuscript_state(lesson_id: str) -> dict:
        return api(
            f"{COURSE_API}/lessons/{lesson_id}/ppt-v6/manuscript"
        )["ppt_manuscript_state"]

    def job(task_id: str) -> dict:
        return api(f"{COURSE_API}/lesson-jobs/{task_id}")["job"]

    def stopped(lesson_id: str, current: dict) -> None:
        failure = current.get("error") or {}
        emit(
            event="lesson_generation_failed",
            lesson_id=lesson_id,
            task_id=current.get("id"),
            status=current.get("status"),
            phase=current.get("phase"),
            progress=current.get("progress"),
            error_code=failure.get("code"),
            failed_step=failure.get("failed_step"),
            failed_block_id=failure.get("failed_block_id"),
            technical_detail=str(failure.get("technical_detail") or "")[:1200],
        )
        raise ValueError(f"lesson_test_failed:{lesson_id}")

    def wait_for_job(lesson_id: str, task_id: str) -> None:
        deadline = time.monotonic() + 2400
        previous = None
        while time.monotonic() < deadline:
            current = job(task_id)
            summary = {
                "status": current.get("status"),
                "phase": current.get("phase"),
                "progress": current.get("progress"),
                "message": current.get("message"),
            }
            if summary != previous:
                emit(event="lesson_progress", lesson_id=lesson_id, task_id=task_id, **summary)
                previous = summary
            if current.get("status") not in {"pending", "running"}:
                if current.get("status") != "completed":
                    stopped(lesson_id, current)
                return
            time.sleep(15)
        raise ValueError(f"lesson_test_observation_timeout:{lesson_id}")

    def verify_export(lesson_id: str, state: dict) -> None:
        if not state.get("manuscript") or not state.get("can_export"):
            raise ValueError(f"lesson_manuscript_not_exportable:{lesson_id}")
        ppt_api = f"{COURSE_API}/lessons/{lesson_id}/ppt-v6"
        revision = str(state.get("revision") or "")
        page_ids = [page["page_id"] for page in state["manuscript"]["pages"]]
        physical_pages = 0
        for offset in range(0, len(page_ids), 10):
            preview = api(
                ppt_api + "/preview",
                {
                    "expected_manuscript_revision": revision,
                    "page_ids": page_ids[offset : offset + 10],
                },
            )
            if preview.get("manuscript_revision") != revision:
                raise ValueError(f"lesson_preview_revision_changed:{lesson_id}")
            physical_pages += len(preview["deck"]["pages"])
        emit(
            event="lesson_preview_complete",
            lesson_id=lesson_id,
            logical_pages=len(page_ids),
            physical_pages=physical_pages,
        )

        representation_id = ""
        with request(
            ppt_api + "/build/stream",
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
                    failure = (event.get("job") or {}).get("error") or event.get("failure") or {}
                    emit(
                        event="lesson_export_failed",
                        lesson_id=lesson_id,
                        code=failure.get("code") or event.get("code"),
                        phase=(event.get("job") or {}).get("phase") or event.get("stage"),
                    )
                    raise ValueError(f"lesson_export_failed:{lesson_id}")
        if not representation_id:
            raise ValueError(f"lesson_export_incomplete:{lesson_id}")

        with request(
            ppt_api + f"/{representation_id}/export.pptx", timeout=300
        ) as response:
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
        expected = int(state["manuscript"]["page_count"])
        if len(slides) != expected or len(notes) != len(slides) or physical_pages != expected:
            raise ValueError(f"lesson_export_page_count_mismatch:{lesson_id}")
        emit(
            event="lesson_export_complete",
            lesson_id=lesson_id,
            task_id=state.get("task_id"),
            manuscript_revision=revision,
            representation_id=representation_id,
            pages=len(slides),
            notes=len(notes),
            pptx_bytes=len(content),
            pptx_sha256=hashlib.sha256(content).hexdigest(),
        )

    for lesson_id, source_revision in LESSONS:
        state = manuscript_state(lesson_id)
        if state.get("source_script_revision_id") not in {None, "", source_revision}:
            raise ValueError(f"lesson_source_changed:{lesson_id}")
        if not state.get("manuscript"):
            task_id = str(state.get("task_id") or "")
            if task_id:
                current = job(task_id)
                if current.get("status") not in {"pending", "running"}:
                    stopped(lesson_id, current)
            else:
                response = api(
                    f"{COURSE_API}/lessons/{lesson_id}/ppt-v6/manuscript/complete",
                    {"source_script_revision_id": source_revision, "task_id": ""},
                    timeout=1800,
                )
                task_id = str(response["job"]["id"])
                emit(event="lesson_generation_started", lesson_id=lesson_id, task_id=task_id)
            wait_for_job(lesson_id, task_id)
            state = manuscript_state(lesson_id)
        emit(
            event="lesson_manuscript_complete",
            lesson_id=lesson_id,
            task_id=state.get("task_id"),
            pages=(state.get("manuscript") or {}).get("page_count"),
        )
        verify_export(lesson_id, state)

    emit(event="two_lesson_test_complete", lessons=[item[0] for item in LESSONS])


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as error:
        detail = ""
        try:
            detail = json.load(error).get("detail", {})
        except Exception:
            pass
        emit(
            event="test_stopped",
            error_type="HTTPError",
            status=error.code,
            detail=detail if isinstance(detail, dict) else {},
        )
        raise
    except Exception as error:
        emit(event="test_stopped", error_type=type(error).__name__, code=str(error))
        raise
