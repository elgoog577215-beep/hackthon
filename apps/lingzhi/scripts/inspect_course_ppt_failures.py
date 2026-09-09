"""Read all lecture states and replay deterministic page gates without models."""
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

COURSE = "afb29754-6842-437b-af1b-5866bfb53b41"
path = Path("/opt/lingzhi/state/backend-data/teacher_lesson_authoring") / f"{COURSE}.json"
before = path.read_bytes()
authoring = json.loads(before)
with tempfile.TemporaryDirectory(prefix="ppt-course-readonly-audit-") as directory:
    os.environ["LINGZHI_DATA_DIR"] = directory
    os.environ["LINGZHI_TASK_RUNTIME_MODE"] = "read_only"
    sys.dont_write_bytecode = True
    sys.path.insert(0, "/opt/lingzhi/hackthon/backend")
    from pydantic import ValidationError
    from ppt_fixed_templates import compile_fixed_template
    from teacher_script_ppt import completion_seed_blocks, _prepare_page_candidates, validate_block_pages
    from template_layout_contract import TemplateLayoutPackContractV1

    for lesson_id, lesson in authoring.get("lessons", {}).items():
        state = lesson.get("ppt_manuscript") or {}
        job = authoring.get("jobs", {}).get(state.get("task_id"), {})
        script = next((r for r in lesson.get("script_revisions", [])
                       if r.get("revision_id") == lesson.get("working_script_revision_id")), {})
        blocks = [b for s in script.get("sections", []) for b in s.get("blocks", [])]
        errors = [e for b in (job.get("bundle_blocks") or {}).values() for e in b.get("ppt_errors", [])]
        report = {"event": "lecture_summary", "lesson_id": lesson_id,
                  "manuscript_status": state.get("status"), "has_manuscript": bool(state.get("manuscript")),
                  "page_count": (state.get("manuscript") or {}).get("page_count"),
                  "job_status": job.get("status"), "attempt": job.get("attempt_number"),
                  "updated_at": job.get("updated_at"), "error_code": (job.get("error") or {}).get("code"),
                  "source_blocks": len(blocks), "checkpoint_blocks": len(job.get("bundle_blocks") or {}),
                  "checkpoint_errors": [{k: e.get(k) for k in ("block_id", "page_index", "message")} for e in errors[:8]]}
        if state.get("manuscript") or job.get("status") in {"running", "pending"}:
            print(json.dumps(report, ensure_ascii=True), flush=True)
            continue
        template_payload = (job.get("request_snapshot") or {}).get("ppt_template")
        template = TemplateLayoutPackContractV1.model_validate(template_payload) if template_payload else compile_fixed_template("qizhi-classroom")
        seeds = completion_seed_blocks(blocks, job.get("bundle_blocks") or {})
        valid, invalid = 0, []
        for block in seeds.values():
            pages = _prepare_page_candidates(block.get("ppt_pages") or [], block)
            groups = block.get("ppt_page_groups") or [[p] for p in pages] or [[]]
            for index, group in enumerate(groups):
                try:
                    candidates = _prepare_page_candidates(group, block)
                    validate_block_pages({**block, "ppt_pages": candidates}, template)
                    valid += 1
                except Exception as error:
                    issue = {"block_id": block["block_id"], "group": index,
                             "layouts": [p.get("layout_id") for p in group if isinstance(p, dict)],
                             "error": str(error).splitlines()[0][:400]}
                    if isinstance(error, ValidationError):
                        issue["fields"] = [{"type": e["type"], "path": list(e.get("loc") or [])} for e in error.errors()]
                    invalid.append(issue)
        report.update(valid_page_groups=valid, invalid_page_groups=len(invalid), invalid_details=invalid[:12])
        print(json.dumps(report, ensure_ascii=True), flush=True)
print(json.dumps({"event": "read_only_proof", "course_state_unchanged": path.read_bytes() == before}), flush=True)
