"""Read only the requested lecture's latest export failure metadata."""
import json
from pathlib import Path

root = Path("/opt/lingzhi/state/backend-data")
course = "afb29754-6842-437b-af1b-5866bfb53b41"
data = json.loads((root / "teacher_lesson_authoring" / f"{course}.json").read_text(encoding="utf-8"))
jobs = [j for j in data.get("jobs", {}).values()
        if j.get("lesson_unit_id") == "L1-1" and j.get("type") == "teacher_lesson_ppt_generation"]
for job in sorted(jobs, key=lambda j: str(j.get("updated_at") or ""), reverse=True)[:1]:
    print(json.dumps({"event": "requested_export_failure", **{k: job.get(k) for k in (
        "id", "status", "phase", "attempt_number", "updated_at", "error", "last_attempt_error", "execution_task_id")}}, ensure_ascii=True))
