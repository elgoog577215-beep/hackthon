#!/usr/bin/env python3
"""Run fixed, complete-course benchmarks through public HTTP APIs."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
import mimetypes
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "benchmarks" / "course_generation_v2" / "manifest.json"
TERMINAL_FAILURES = {"failed", "error", "conflict", "cancelled"}
TERMINAL_SUCCESSES = {"completed", "completed_with_warnings"}


class BenchmarkError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ApiClient:
    def __init__(self, base_url: str, user_id: str, timeout: float):
        self.base_url = base_url.rstrip("/")
        self.user_id = user_id
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        expected: set[int] | None = None,
        body: bytes | None = None,
        content_type: str = "application/json",
    ) -> tuple[int, dict[str, Any]]:
        headers = {"Accept": "application/json", "X-User-Id": self.user_id}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if body is not None:
            headers["Content-Type"] = content_type
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                status = response.status
                raw = response.read().decode("utf-8")
        except HTTPError as error:
            status = error.code
            raw = error.read().decode("utf-8")
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {"raw": raw}
        if status not in (expected or {200}):
            raise BenchmarkError(f"{method} {path} returned {status}: {data}")
        return status, data

    def upload(self, path: Path) -> dict[str, Any]:
        boundary = f"----lingzhi-benchmark-{uuid.uuid4().hex}"
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body = b"".join([
            f"--{boundary}\r\n".encode(),
            (
                f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
                f"Content-Type: {mime}\r\n\r\n"
            ).encode("utf-8"),
            path.read_bytes(),
            f"\r\n--{boundary}--\r\n".encode(),
        ])
        _, result = self.request(
            "POST",
            "/api/materials",
            body=body,
            content_type=f"multipart/form-data; boundary={boundary}",
            expected={201},
        )
        return result


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_manifest(data, path.parent)
    if errors:
        raise BenchmarkError("；".join(errors))
    return data


def validate_manifest(data: dict[str, Any], base_dir: Path) -> list[str]:
    errors: list[str] = []
    if data.get("schema_version") != "course_generation_benchmark_v1":
        errors.append("基准 schema_version 不正确")
    scenarios = data.get("scenarios") or []
    if not scenarios:
        errors.append("没有固定课程场景")
    ids: set[str] = set()
    for scenario in scenarios:
        scenario_id = str(scenario.get("id") or "")
        if not scenario_id or scenario_id in ids:
            errors.append(f"场景 ID 缺失或重复：{scenario_id}")
        ids.add(scenario_id)
        request = scenario.get("request") or {}
        brief = request.get("teacher_course_brief") or {}
        if int(brief.get("chapter_count") or 0) != int(scenario.get("expected_chapters") or 0):
            errors.append(f"{scenario_id} 的章节数不一致")
        if int(brief.get("section_count") or 0) != int(scenario.get("expected_sections") or 0):
            errors.append(f"{scenario_id} 的小节数不一致")
        if int(scenario.get("expected_sections") or 0) < 8:
            errors.append(f"{scenario_id} 不是完整课程基准")
        for relative in scenario.get("material_files") or []:
            if not (base_dir / str(relative)).is_file():
                errors.append(f"{scenario_id} 缺少资料：{relative}")
    if not (data.get("model_pool") or {}).get("smart_models"):
        errors.append("模型池未固定")
    if len((data.get("teacher_rubric") or {}).get("dimensions") or []) < 6:
        errors.append("教师质量量表不完整")
    if len(data.get("failure_set") or []) < 6:
        errors.append("质量失败集不完整")
    return errors


def _elapsed(started: float) -> float:
    return round(time.monotonic() - started, 3)


def _phase_bucket(phase: str, status: str) -> str:
    if status == "waiting_for_review":
        return "teacher_wait"
    if phase in {"queued", "requirement_analysis", "pedagogy_resolution"}:
        return "queue_and_requirements"
    if "material" in phase:
        return "material"
    if "retrieval" in phase:
        return "retrieval"
    if any(token in phase for token in ("generation", "teaching_plan", "knowledge")):
        return "model"
    return "compile_and_quality"


def _model_pool_check(preflight: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    actual = {
        model
        for route in preflight.get("provider_pool") or []
        for model in route.get("models") or []
    }
    fixed = {
        model
        for key in ("smart_models", "fast_models", "fallback_models")
        for model in expected.get(key) or []
    }
    return {
        "matched": actual == fixed,
        "expected_models": sorted(fixed),
        "actual_models": sorted(actual),
    }


def run_once(
    *,
    client: ApiClient,
    scenario: dict[str, Any],
    manifest_dir: Path,
    model_pool: dict[str, Any],
    poll_interval: float,
    timeout_seconds: float,
    auto_confirm: bool,
) -> dict[str, Any]:
    started = time.monotonic()
    payload = deepcopy(scenario["request"])
    payload["request_id"] = f"benchmark-{scenario['id']}-{uuid.uuid4()}"
    material_reports: list[dict[str, Any]] = []
    bindings: list[dict[str, Any]] = []
    for relative in scenario.get("material_files") or []:
        asset = client.upload(manifest_dir / str(relative))
        asset_id = str(asset["asset_id"])
        _, parsed = client.request("POST", f"/api/materials/{asset_id}/parse")
        material_reports.append({
            "asset_id": asset_id,
            "filename": asset.get("filename"),
            "quality_report": parsed.get("quality_report"),
        })
        bindings.append({
            "asset_id": asset_id,
            "purpose": "content_source",
            "priority": "core",
            "authority": "primary",
            "usage_policy": "must_use",
        })
    payload["material_bindings"] = bindings

    _, preflight = client.request("POST", "/api/course-generation/preflight", payload)
    result: dict[str, Any] = {
        "schema_version": "course_generation_benchmark_run_v1",
        "scenario_id": scenario["id"],
        "started_at": utc_now(),
        "success": False,
        "preflight": preflight,
        "model_pool_check": _model_pool_check(preflight, model_pool),
        "materials": material_reports,
        "milestones_seconds": {},
        "phase_seconds": {},
        "confirmations": [],
    }
    if preflight.get("status") == "blocked":
        result["failure"] = {"code": "preflight_blocked", "issues": preflight.get("issues") or []}
        result["duration_seconds"] = _elapsed(started)
        return result
    if preflight.get("status") == "degraded":
        payload["preflight_acceptance"] = {
            "preflight_id": preflight["preflight_id"],
            "accepted_issue_codes": [item.get("code") for item in preflight.get("issues") or []],
        }

    _, job = client.request(
        "POST",
        "/api/course-generation/generate",
        payload,
        expected={202},
    )
    job_id = str(job["job_id"])
    course_id = str(job["course_id"])
    result.update({"job_id": job_id, "course_id": course_id})
    milestones = result["milestones_seconds"]
    phase_seconds: dict[str, float] = result["phase_seconds"]
    last_observed = time.monotonic()
    last_phase = "queued"
    last_status = "pending"
    confirmed: set[str] = set()
    final_task: dict[str, Any] = {}

    while time.monotonic() - started <= timeout_seconds:
        _, task = client.request("GET", f"/api/tasks/{job_id}")
        now = time.monotonic()
        bucket = _phase_bucket(last_phase, last_status)
        phase_seconds[bucket] = round(
            phase_seconds.get(bucket, 0.0) + now - last_observed,
            3,
        )
        last_observed = now
        last_phase = str(task.get("phase") or task.get("current_phase") or "")
        last_status = str(task.get("status") or "")
        final_task = task
        workflow = task.get("guided_workflow") or {}
        states = {
            str(item.get("key") or ""): str(item.get("status") or "")
            for item in workflow.get("steps") or []
        }
        if "first_outline" not in milestones and (
            last_phase == "outline_ready" or states.get("outline") in {"waiting_for_confirmation", "confirmed"}
        ):
            milestones["first_outline"] = _elapsed(started)
        if "formal_lesson_plan" not in milestones and states.get("teaching") == "confirmed":
            milestones["formal_lesson_plan"] = _elapsed(started)
        if "first_section_content" not in milestones and int(task.get("completed_nodes") or 0) >= 1:
            milestones["first_section_content"] = _elapsed(started)

        review_step = str(workflow.get("review_step") or "")
        if last_status == "waiting_for_review" and review_step and review_step not in confirmed:
            if not auto_confirm:
                result["failure"] = {"code": "teacher_confirmation_required", "step": review_step}
                break
            client.request(
                "POST",
                f"/api/courses/{course_id}/generation/steps/{review_step}/confirm",
                expected={202},
            )
            confirmed.add(review_step)
            result["confirmations"].append({"step": review_step, "at_seconds": _elapsed(started)})
            continue
        if last_status in TERMINAL_SUCCESSES:
            milestones["complete_course"] = _elapsed(started)
            result["success"] = True
            break
        if last_status in TERMINAL_FAILURES:
            result["failure"] = {
                "code": str(task.get("error_code") or last_status),
                "message": str(task.get("error_user_message") or task.get("error") or task.get("message") or ""),
                "recovery": task.get("recovery") or {},
            }
            break
        time.sleep(max(0.2, poll_interval))
    else:
        result["failure"] = {"code": "benchmark_timeout", "timeout_seconds": timeout_seconds}

    result["duration_seconds"] = _elapsed(started)
    result["final_task"] = {
        key: final_task.get(key)
        for key in (
            "status", "phase", "progress", "completed_nodes", "total_nodes",
            "quality_status", "publication_allowed", "recovery", "phase_history",
        )
    }
    if result["success"]:
        _, course = client.request("GET", f"/api/courses/{course_id}")
        l2_nodes = [node for node in course.get("nodes") or [] if int(node.get("node_level") or 0) == 2]
        l1_nodes = [node for node in course.get("nodes") or [] if int(node.get("node_level") or 0) == 1]
        lesson_plan = course.get("course_teaching_plan") or {}
        result["output_contract"] = {
            "expected_chapters": scenario["expected_chapters"],
            "actual_chapters": len(l1_nodes),
            "expected_sections": scenario["expected_sections"],
            "actual_sections": len(l2_nodes),
            "lesson_plan_sections": int(lesson_plan.get("section_count") or len(lesson_plan.get("sections") or [])),
            "all_sections_have_content": all(str(node.get("node_content") or "").strip() for node in l2_nodes),
        }
        result["quality"] = {
            "generation": course.get("generation_quality_report") or {},
            "knowledge": course.get("course_knowledge_quality_report") or {},
            "coherence": course.get("course_coherence_quality_report") or {},
            "grounding": course.get("grounding_quality_report") or {},
        }
    return result


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return round(ordered[index], 3)


def summarize_runs(runs: list[dict[str, Any]], gates: dict[str, Any]) -> dict[str, Any]:
    successful = [item for item in runs if item.get("success")]
    milestones = {
        key: [
            float(item.get("milestones_seconds", {}).get(key))
            for item in successful
            if item.get("milestones_seconds", {}).get(key) is not None
        ]
        for key in ("first_outline", "formal_lesson_plan", "first_section_content", "complete_course")
    }
    success_rate = round(len(successful) / max(1, len(runs)), 4)
    return {
        "run_count": len(runs),
        "successful_runs": len(successful),
        "success_rate": success_rate,
        "p50_seconds": {key: _percentile(values, 0.5) for key, values in milestones.items()},
        "p95_seconds": {key: _percentile(values, 0.95) for key, values in milestones.items()},
        "release_gate": {
            "success_rate_passed": len(runs) > 0 and success_rate >= float(gates.get("success_rate") or 0.98),
            "sample_size_passed": sum(
                int(item.get("output_contract", {}).get("actual_sections") or 0) >= 12
                for item in runs
            ) >= int(gates.get("minimum_runs_12_sections") or 20),
            "status": "not_claimable_until_all_gates_pass",
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--user-id", default="course-benchmark")
    parser.add_argument("--scenario", action="append", default=[])
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--request-timeout", type=float, default=180.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-auto-confirm", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = load_manifest(args.manifest.resolve())
    selected = [
        item for item in manifest["scenarios"]
        if not args.scenario or item["id"] in set(args.scenario)
    ]
    unknown = set(args.scenario) - {item["id"] for item in selected}
    if unknown:
        raise BenchmarkError(f"未知场景：{', '.join(sorted(unknown))}")
    if args.dry_run:
        output = {
            "status": "validated",
            "manifest": str(args.manifest.resolve()),
            "fixture_version": manifest["fixture_version"],
            "scenario_ids": [item["id"] for item in selected],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0

    client = ApiClient(args.base_url, args.user_id, args.request_timeout)
    runs: list[dict[str, Any]] = []
    for scenario in selected:
        for _index in range(max(1, args.runs)):
            runs.append(run_once(
                client=client,
                scenario=scenario,
                manifest_dir=args.manifest.resolve().parent,
                model_pool=manifest["model_pool"],
                poll_interval=args.poll_interval,
                timeout_seconds=args.timeout,
                auto_confirm=not args.no_auto_confirm,
            ))
    report = {
        "schema_version": "course_generation_benchmark_report_v1",
        "fixture_version": manifest["fixture_version"],
        "generated_at": utc_now(),
        "teacher_rubric": manifest["teacher_rubric"],
        "failure_set": manifest["failure_set"],
        "release_gates": manifest["release_gates"],
        "summary": summarize_runs(runs, manifest["release_gates"]),
        "runs": runs,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if all(item.get("success") for item in runs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
