"""Execute the explicitly approved original PPT retry via the formal local API.

No direct repository writes, no body/identity logging, and no new task if the
original task has changed or is paused/cancelled. This is an operator probe on
the diagnostic branch, not production application code.
"""
import hashlib
import io
import json
import re
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

COURSE = "afb29754-6842-437b-af1b-5866bfb53b41"
LESSON = "L1-1"
TASK = "tlj-de0142ee0a2f4c72a3f9a8a1ede1b7be"
SCRIPT = "tlsr-2b924bca800b44e3f8eac91b"
RELEASE = "a835ae52854eaac6f0874f01f1e01c84ecb9fbdc"
ROOT = Path("/opt/lingzhi/state/backend-data")
BASE = "http://127.0.0.1:7862"
API = f"/api/teacher/courses/{COURSE}"
PPT = f"{API}/lessons/{LESSON}/ppt-v6"


def emit(**value):
    print(json.dumps(value, ensure_ascii=True), flush=True)


def saved_lesson():
    value = json.loads((ROOT / "teacher_lesson_authoring" / f"{COURSE}.json").read_text(encoding="utf-8"))
    return value["lessons"][LESSON]


def handout_digest(lesson):
    if lesson.get("working_script_revision_id") != SCRIPT:
        raise ValueError("requested_handout_revision_changed")
    revision = next(r for r in lesson["script_revisions"] if r["revision_id"] == SCRIPT)
    return hashlib.sha256(json.dumps(revision["sections"], sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def main():
    course = json.loads((ROOT / "courses" / f"{COURSE}.json").read_text(encoding="utf-8"))
    if not course.get("owner_id") or course.get("authoring_surface") != "teacher":
        raise ValueError("requested_teacher_course_identity_unavailable")
    # Existing ownership remains on-server and is used only for this approved
    # course's formal API. Never print or export the identity value.
    headers = {"X-User-Id": course["owner_id"], "Content-Type": "application/json"}

    def request(path, payload=None, timeout=180):
        data = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(BASE + path, data=data, headers=headers)
        return urllib.request.urlopen(req, timeout=timeout)

    def api(path, payload=None):
        with request(path, payload) as response:
            return json.load(response)

    health = api("/api/health")
    if not health.get("ready") or health.get("version") != RELEASE:
        raise ValueError("approved_release_not_active")
    before = handout_digest(saved_lesson())
    state = api(PPT + "/manuscript")["ppt_manuscript_state"]
    if state.get("source_script_revision_id") != SCRIPT or state.get("task_id") != TASK:
        raise ValueError("requested_task_or_source_changed")
    if not state.get("manuscript"):
        job = api(API + f"/lesson-jobs/{TASK}")["job"]
        if job.get("status") == "failed":
            response = api(PPT + "/manuscript/complete", {"source_script_revision_id": SCRIPT, "task_id": TASK})
            if response["job"]["id"] != TASK:
                raise ValueError("unexpected_task_identity")
            emit(event="original_task_resumed", task_id=TASK, attempt=response["job"].get("attempt_number"))
        elif job.get("status") not in {"pending", "running"}:
            raise ValueError("original_task_not_retryable_without_new_approval")
        deadline = time.monotonic() + 720
        last = None
        while time.monotonic() < deadline:
            job = api(API + f"/lesson-jobs/{TASK}")["job"]
            summary = {k: job.get(k) for k in ("status", "phase", "progress", "attempt_number")}
            if summary != last:
                emit(event="original_task_progress", **summary)
                last = summary
            if job.get("status") not in {"pending", "running"}:
                break
            time.sleep(15)
        if job.get("status") != "completed":
            error = job.get("error") or {}
            emit(event="original_task_not_completed", status=job.get("status"),
                 error_code=error.get("code"), failed_step=error.get("failed_step"))
            raise ValueError("original_task_not_completed")
        state = api(PPT + "/manuscript")["ppt_manuscript_state"]
    if not state.get("manuscript") or not state.get("can_export"):
        raise ValueError("manuscript_not_exportable")
    if handout_digest(saved_lesson()) != before:
        raise ValueError("handout_changed_during_recovery")
    revision = state["revision"]
    page_ids = [p["page_id"] for p in state["manuscript"]["pages"]]
    physical = 0
    for offset in range(0, len(page_ids), 10):
        preview = api(PPT + "/preview", {"expected_manuscript_revision": revision, "page_ids": page_ids[offset:offset + 10]})
        if preview.get("manuscript_revision") != revision:
            raise ValueError("preview_revision_changed")
        physical += len(preview["deck"]["pages"])
    emit(event="all_pages_previewed", logical_pages=len(page_ids), physical_pages=physical)
    representation = ""
    with request(PPT + "/build/stream", {"expected_manuscript_revision": revision}) as response:
        for raw in response:
            if not raw.startswith(b"data: "):
                continue
            event = json.loads(raw[6:])
            if event.get("event") == "build_complete":
                representation = event.get("build", {}).get("representation_id", "")
            if event.get("event") in {"build_paused", "build_cancelled"} or event.get("failure"):
                failure = (event.get("job") or {}).get("error") or {}
                emit(event="export_build_stopped", code=failure.get("code") or event.get("code"),
                     reason=failure.get("message") if failure.get("code") in {"render_quality_gate_failed", "render_export_failed"} else None,
                     status=event.get("status"))
                raise ValueError("export_build_stopped")
    if not representation:
        raise ValueError("export_build_incomplete")
    with request(PPT + f"/{representation}/export.pptx") as response:
        content = response.read()
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        slides = [n for n in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
        notes = [n for n in archive.namelist() if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", n)]
    if len(slides) != physical or len(slides) != state["manuscript"]["page_count"] or len(notes) != len(slides):
        raise ValueError("export_page_or_note_count_mismatch")
    if handout_digest(saved_lesson()) != before:
        raise ValueError("handout_changed_during_export")
    if (saved_lesson().get("ppt_manuscript") or {}).get("revision") != revision:
        raise ValueError("manuscript_changed_during_export")
    emit(event="recovery_verified", course_id=COURSE, lesson_id=LESSON, original_task_id=TASK,
         manuscript_revision=revision, representation_id=representation, pages=len(slides), notes=len(notes),
         bytes=len(content), sha256=hashlib.sha256(content).hexdigest(), handout_unchanged=True)


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as error:
        try:
            detail = json.load(error).get("detail", {})
        except Exception:
            detail = {}
        emit(event="http_failure", status=error.code, code=detail.get("code") if isinstance(detail, dict) else None)
        raise SystemExit(1)
    except Exception as error:
        emit(event="probe_failed", error_type=type(error).__name__, code=str(error) if isinstance(error, ValueError) else None)
        raise SystemExit(1)
