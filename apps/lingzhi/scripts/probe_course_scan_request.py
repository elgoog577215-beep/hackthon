#!/usr/bin/env python3
"""Run two disposable real analysis requests; print only bounded telemetry."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import subprocess
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "backend"))
logging.disable(logging.CRITICAL)


async def main() -> None:
    course_id = os.environ["COURSE_SCAN_COURSE_ID"]
    pid = int(subprocess.check_output(["systemctl", "show", "lingzhi", "--property=MainPID", "--value"], text=True).strip())
    process_root = Path(f"/proc/{pid}/cwd").resolve()
    process_env = dict(part.decode(errors="replace").split("=", 1)
                       for part in Path(f"/proc/{pid}/environ").read_bytes().split(b"\0") if b"=" in part)
    os.environ.clear()
    os.environ.update(process_env)
    os.chdir(process_root)
    sys.path.insert(0, str(process_root if (process_root / "ai_base.py").exists() else process_root / "backend"))
    # Match application startup: dotenv must be loaded before storage modules
    # capture LINGZHI_DATA_DIR at import time.
    from course_generation.service import CourseService
    from dependencies import get_course_document_repository, get_teacher_lesson_authoring_repository
    from question_bank import question_bank_repository
    from course_evolution.teacher_planning import build_teacher_course_change_context, rank_change_units

    document, _ = get_course_document_repository().load_document(course_id)
    context = build_teacher_course_change_context(
        course_id=course_id, document=document, preview=None,
        authoring=get_teacher_lesson_authoring_repository().load(course_id),
        question_bank=question_bank_repository.load_bundle(course_id),
    )
    instruction = "给每个章节加一个实践项目"
    overview = {
        "course_id": course_id, "course_title": context.course_title,
        "source_mode": context.source_mode,
        "assets": [item.model_dump(mode="json") for item in context.assets],
        "outline": [{k: v for k, v in node.items() if k != "section_snapshot"} for node in context.outline],
        "indexed_unit_count": len(context.units),
    }
    ranked = rank_change_units(context, instruction, limit=len(context.units), include_all=True)
    unit_map = {unit.unit_id: unit for unit in context.units}
    # Reproduce the largest code-bearing course unit, then an ordinary unit.
    candidates = [item for item in ranked if item["asset_type"] == "course_content"]
    candidates.sort(key=lambda item: len(unit_map[item["unit_id"]].text), reverse=True)
    targets = candidates[:1] + candidates[-1:]
    provider = CourseService()
    original = provider._call_llm
    attempts: list[dict] = []
    activity: list[float] = []

    async def on_activity(*args, **kwargs):
        activity.append(time.monotonic())

    async def traced(*args, **kwargs):
        kwargs.update(telemetry_sink=attempts.append, on_stream_activity=on_activity)
        return await original(*args, **kwargs)

    provider._call_llm = traced
    for index, item in enumerate(targets):
        unit = unit_map[item["unit_id"]]
        body = "\n\n".join(unit.full_text_fields.values()) or unit.text
        size = 600 if len(body) > 6000 and "```" in body else 1200
        entry = {**item, "content": body[:size], "part": 1,
                 "parts": len(range(0, max(1, len(body)), size - 100))}
        attempts.clear()
        activity.clear()
        started = time.monotonic()
        event = {"sample": index + 1, "fragment_chars": len(entry["content"]),
                 "full_unit_chars": len(body), "indexed_units": len(context.units)}
        print(json.dumps({**event, "status": "started"}), flush=True)
        try:
            result = await asyncio.wait_for(provider.analyze_teacher_course_change(overview, [entry], instruction), timeout=210)
            event.update(status="completed", valid_envelope=isinstance(result, dict),
                         affected_count=len((result or {}).get("affected_units") or []))
        except Exception as error:
            chain, seen = [], set()
            while error is not None and id(error) not in seen:
                seen.add(id(error))
                chain.append(type(error).__name__)
                error = error.__cause__ or error.__context__
            event.update(status="failed", error_chain=chain)
        event.update(duration_ms=round((time.monotonic() - started) * 1000),
                     activity_count=len(activity),
                     first_activity_ms=round((activity[0] - started) * 1000) if activity else None,
                     attempts=[{key: value for key, value in attempt.items() if key in {
                         "model_id", "provider_route", "status", "duration_ms", "first_token_ms",
                         "input_tokens", "output_tokens", "failure_kind", "queue_wait_ms"
                     }} for attempt in attempts])
        print(json.dumps(event), flush=True)
    if provider.client:
        await provider.client.close()


if __name__ == "__main__":
    asyncio.run(main())
