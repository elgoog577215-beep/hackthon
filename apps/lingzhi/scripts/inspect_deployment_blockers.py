"""Read a bounded, redacted task summary; never import the application or mutate it."""
import json
from datetime import datetime, timezone
from pathlib import Path


def summarize(path):
    if path.stat().st_size > 96 * 1024 * 1024:
        raise ValueError("task_index_oversized")
    tasks = json.loads(path.read_text(encoding="utf-8"))
    fields = ("id", "type", "status", "course_id", "phase", "progress", "created_at", "updated_at", "heartbeat_at")
    result = []
    for key, task in tasks.items():
        if not isinstance(task, dict) or task.get("status") not in {"running", "pending", "queued"}:
            continue
        item = {name: task.get(name) for name in fields if isinstance(task.get(name), (str, int, float, bool))}
        item.setdefault("id", key)
        # Only status/step identifiers: never content, owner IDs, prompts or errors.
        workflow = task.get("workflow") or {}
        if isinstance(workflow, dict):
            item["workflow_state"] = {name: workflow[name] for name in ("status", "current_step", "current_stage")
                                      if isinstance(workflow.get(name), (str, int))}
        result.append(item)
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "index_modified": path.stat().st_mtime,
            "active_count": len(result), "tasks": result[:20]}


if __name__ == "__main__":
    print(json.dumps(summarize(Path("/opt/lingzhi/state/backend-data/generation_jobs.json")), ensure_ascii=True))
    course_id = "afb29754-6842-437b-af1b-5866bfb53b41"
    root = Path("/opt/lingzhi/state/backend-data")
    authoring_path = root / "teacher_lesson_authoring" / f"{course_id}.json"
    if authoring_path.exists():
        authoring = json.loads(authoring_path.read_text(encoding="utf-8"))
        lesson = authoring.get("lessons", {}).get("L2-1-1", {})
        state = lesson.get("ppt_manuscript") or {}
        job = authoring.get("jobs", {}).get(state.get("task_id"), {})
        print(json.dumps({"requested_course": course_id, "lesson_found": bool(lesson),
            "working_script_revision_id": lesson.get("working_script_revision_id"),
            "manuscript": {k: state.get(k) for k in ("status", "revision", "task_id", "source_state")},
            "page_count": (state.get("manuscript") or {}).get("page_count"),
            "job": {k: job.get(k) for k in ("id", "status", "phase", "attempt_number", "updated_at")},
            "error_code": (job.get("error") or {}).get("code"),
            "checkpoint_blocks": len(job.get("bundle_blocks") or {})}, ensure_ascii=True))
    else:
        print(json.dumps({"requested_course": course_id, "authoring_found": False}))
