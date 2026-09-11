#!/usr/bin/env python3
"""Run bounded disposable analysis requests and smaller-fragment controls."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import subprocess
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "backend"))
logging.disable(logging.CRITICAL)


async def main() -> None:
    course_id = os.environ["COURSE_SCAN_COURSE_ID"]
    unit_id = os.environ.get("COURSE_SCAN_UNIT_ID", "")
    transport_control = os.environ.get("COURSE_SCAN_TRANSPORT_CONTROL") == "true"
    recovery_user_id = os.environ.get("COURSE_SCAN_RECOVERY_USER_ID", "")
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
    from course_evolution.content_patches import readable_body
    from course_evolution.patch_review import section_inventory
    from course_evolution.semantic_scan import validate_batch

    document, _ = get_course_document_repository().load_document(course_id)
    context = build_teacher_course_change_context(
        course_id=course_id, document=document, preview=None,
        authoring=get_teacher_lesson_authoring_repository().load(course_id),
        question_bank=question_bank_repository.load_bundle(course_id),
    )
    context = context.model_copy(update={"units": [unit for unit in context.units if unit.asset_type != "ppt"]})
    if recovery_user_id:
        # Execute the real planner only as far as its first progress report.
        # No model request, new job, plan save, or course mutation is permitted.
        from course_document import stable_hash
        from course_evolution.core import CourseEvolutionRepository
        from course_evolution.teacher_planning import create_teacher_course_change_plan
        state = CourseEvolutionRepository().load(recovery_user_id, course_id)
        source = next(plan for plan in reversed(state.change_sets)
                      if plan.status == "pending" and plan.teacher_change_planning
                      and plan.source_kind == "manual_request")

        class ReadOnlyRepository:
            def load(self, *args):
                return state.model_copy(deep=True)

            def update(self, *args, **kwargs):
                raise RuntimeError("Recovery inspection must not persist a plan")

        class InspectionComplete(BaseException):
            pass

        async def no_model(*args):
            raise RuntimeError("Recovery inspection must not call the model")

        async def first_progress(detail, checkpoint):
            print(json.dumps({"recovery_inspection": detail,
                              "source_plan_id": source.change_set_id,
                              "source_completed_units": source.impact_summary.get("coverage", {}).get("scanned_units"),
                              "model_called": False, "plan_saved": False}), flush=True)
            raise InspectionComplete()

        provider = CourseService()
        try:
            await create_teacher_course_change_plan(
                context=context, user_id=recovery_user_id, request_id="read-only-recovery-inspection",
                instruction=source.request_text, repository=ReadOnlyRepository(), analyzer=no_model,
                supersedes_plan_id=source.change_set_id, rescan_incomplete_only=True,
                on_scan_progress=first_progress,
                scan_model_identity=stable_hash({"endpoint": provider.api_base, "models": provider.fast_models},
                                                prefix="analysis-model-"))
        except InspectionComplete:
            return
        finally:
            if provider.client:
                await provider.client.close()
        raise RuntimeError("Recovery inspection did not reach scan progress")
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
    if unit_id:
        target = next(item for item in candidates if item["unit_id"] == unit_id)
        targets = [target, next(item for item in reversed(candidates) if item['unit_id'] != unit_id)]
    provider = CourseService()
    original = provider._call_llm
    attempts: list[dict] = []
    activity: list[float] = []
    transport: list[dict] = []

    async def trace(name, info):
        # Never emit HTTP headers, URLs, prompts or trace info (may contain keys).
        if len(transport) < 40:
            transport.append({'phase': name, 'elapsed_ms': round((time.monotonic() - started) * 1000)})

    async def trace_request(request):
        request.extensions['trace'] = trace
        if item.get('_probe_wire_escape'):
            # Diagnostic only: identical parsed JSON, different wire encoding.
            # This distinguishes payload handling before inference from model
            # behaviour without altering source content, model or credentials.
            import httpx
            original_payload = json.loads(request.content)
            def escaped_string(match):
                data = json.loads(match[0]).encode('utf-16-be')
                return '"' + ''.join('\\u' + data[i:i+2].hex() for i in range(0, len(data), 2)) + '"'
            encoded = re.sub(r'"(?:\\.|[^"\\])*"', escaped_string,
                             json.dumps(original_payload, ensure_ascii=True)).encode()
            assert json.loads(encoded) == original_payload
            request._content = encoded
            request.stream = httpx.ByteStream(encoded)
            request.headers['content-length'] = str(len(encoded))

    provider.client._client.event_hooks.setdefault('request', []).append(trace_request)

    def on_activity(*args, **kwargs):
        activity.append(time.monotonic())

    async def traced(*args, **kwargs):
        kwargs.update(telemetry_sink=attempts.append, on_stream_activity=on_activity)
        if transport_control:
            kwargs.update(json_mode=False, request_timeout_seconds=45)
        elif item.get('_probe_size') or item.get('_probe_wire_escape'):
            kwargs.update(request_timeout_seconds=45)
        return await original(*args, **kwargs)

    provider._call_llm = traced
    for index, item in enumerate(targets):
        unit = unit_map[item["unit_id"]]
        body = readable_body(unit.full_text_fields) or unit.text
        size = 600 if len(body) > 6000 and "```" in body else 1200
        parts = len(range(0, max(1, len(body)), size - 100))
        part = min(7, parts) if unit_id and index == 0 else 1
        offset = (part - 1) * (size - 100)
        offset = item.get('_probe_offset', offset)
        size = item.get('_probe_size', size)
        primary_path = next((key for key in ('/markdown', '/text', '/content') if unit.full_text_fields.get(key)), '')
        payload = (unit.metadata.get('course_block') or {}).get('payload') or {}
        entry = {**{k: v for k, v in item.items() if not k.startswith('_probe_')},
                 "content": body[offset:offset + size], "part": part, "parts": parts,
                 'content_field': primary_path.lstrip('/'), 'block_title': str(payload.get('title') or ''),
                 'existing_sections': list(section_inventory(body))}
        attempts.clear()
        activity.clear()
        transport.clear()
        started = time.monotonic()
        event = {"sample": index + 1, "unit_id": item['unit_id'], "part": part, "fragment_chars": len(entry["content"]),
                 "wire_escape_control": bool(item.get('_probe_wire_escape')),
                 "full_unit_chars": len(body), "indexed_units": len(context.units),
                 "json_mode_control_disabled": transport_control}
        print(json.dumps({**event, "status": "started"}), flush=True)
        try:
            result = await asyncio.wait_for(provider.analyze_teacher_course_change(overview, [entry], instruction), timeout=210)
            validate_batch(result, [entry])
            event.update(status="completed", valid_envelope=True,
                         affected_count=len((result or {}).get("affected_units") or []))
        except Exception as error:
            if index == 0 and len(entry['content']) == 600:
                # Two finite read-only controls, not another course job. Keep
                # all source text: overlap 50 characters at the split boundary.
                targets.extend([{**item, '_probe_offset': offset, '_probe_size': 325},
                                {**item, '_probe_offset': offset + 275, '_probe_size': 325},
                                {**item, '_probe_offset': offset, '_probe_wire_escape': True}])
            chain, seen = [], set()
            while error is not None and id(error) not in seen:
                seen.add(id(error))
                chain.append(type(error).__name__)
                error = error.__cause__ or error.__context__
            event.update(status="failed", error_chain=chain)
        event.update(duration_ms=round((time.monotonic() - started) * 1000),
                     transport=transport,
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
