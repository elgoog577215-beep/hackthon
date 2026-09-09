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
