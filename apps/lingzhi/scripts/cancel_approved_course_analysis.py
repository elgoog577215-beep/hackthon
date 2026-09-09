"""Cancel only the user-approved active course analysis through the formal API."""
import json
import urllib.request
from pathlib import Path

COURSE = "afb29754-6842-437b-af1b-5866bfb53b41"
TASK = "course-change-analysis-2157322d6c2d42999bef142171801c72"
ROOT = Path("/opt/lingzhi/state/backend-data")


def emit(**value):
    print(json.dumps(value, ensure_ascii=True), flush=True)


tasks_path = ROOT / "generation_jobs.json"
tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
task = tasks.get(TASK)
if not task:
    emit(event="approved_task_already_absent", task_id=TASK)
elif task.get("course_id") != COURSE or task.get("type") != "teacher_course_change_analysis":
    raise ValueError("approved_task_identity_mismatch")
elif task.get("status") not in {"pending", "queued", "running"}:
    emit(event="approved_task_already_terminal", task_id=TASK, status=task.get("status"))
else:
    course = json.loads((ROOT / "courses" / f"{COURSE}.json").read_text(encoding="utf-8"))
    owner = str(course.get("owner_id") or "")
    if not owner:
        raise ValueError("course_owner_missing")
    request = urllib.request.Request(
        f"http://127.0.0.1:7862/api/tasks/{TASK}",
        headers={"X-User-Id": owner},
        method="DELETE",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = json.load(response)
    if payload.get("status") != "deleted":
        raise ValueError("formal_cancel_not_acknowledged")
    emit(event="approved_task_cancelled", task_id=TASK)

after = json.loads(tasks_path.read_text(encoding="utf-8"))
active = [item for item in after.values() if isinstance(item, dict) and item.get("status") in {"pending", "queued", "running"}]
emit(event="post_cancel_state", approved_task_absent=TASK not in after, active_count=len(active))
