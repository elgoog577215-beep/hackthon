#!/usr/bin/env python3
"""Run a read-only, in-memory production assessment-chain diagnostic."""

from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

from assessment_blueprint import compile_course_assessment_blueprint
from assessment_contracts import (
    compile_assessment_objectives,
    compile_course_assessment_profile,
)
from assessment_orchestrator import AssessmentGenerationOrchestrator
from assessment_retrieval import (
    compile_local_reference_package,
    enrich_reference_package_with_web,
)
from question_bank import build_question_bank


NODE_ID = "unity-lifecycle-1"
PRACTICE_ORDER = {
    "concept_check": 0,
    "objective_practice": 1,
    "mastery_check": 2,
}


def diagnostic_course() -> dict[str, Any]:
    return {
        "course_id": "diagnostic-unity-6-lifecycle",
        "course_name": "Unity 6 游戏脚本基础",
        "course_purpose": "systematic",
        "difficulty": "intermediate",
        "subject_pedagogy_profile": {
            "primary_mode": "programming_engineering",
            "user_locked": True,
        },
        "generation_request": {
            "course_purpose": "systematic",
            "retrieval": {"enabled": True},
            "web_question_enrichment": {
                "enabled": True,
                "mode": "always",
            },
        },
        "material_bindings": [],
        "evidence_catalog": [],
        "nodes": [{
            "node_id": NODE_ID,
            "node_level": 2,
            "node_name": "MonoBehaviour 的 Update、FixedUpdate 与 LateUpdate",
            "node_content": (
                "在 Unity 6 中，Update 通常每个渲染帧调用一次，帧间隔会变化；"
                "按每秒速度推进普通 Transform 时，应使用 Time.deltaTime 抵消帧率变化。"
                "FixedUpdate 按固定时间步执行，默认 Time.fixedDeltaTime 通常为 0.02 秒；"
                "一次渲染帧之间可能执行零次、一次或多次，基于 Rigidbody 的物理操作应放在这里。"
                "LateUpdate 在当帧所有 Update 之后执行，适合让相机跟随已经完成移动的目标。"
                "同一位移若同时在 Update 和 FixedUpdate 应用，会造成速度叠加；"
                "在 Update 中直接按帧累加固定距离会产生帧率依赖。"
            ),
            "learning_objective": (
                "根据调用时序选择 Update、FixedUpdate 或 LateUpdate，"
                "实现帧率无关移动、Rigidbody 物理移动和稳定的相机跟随，并能诊断抖动或重复位移"
            ),
            "key_points": [
                "Update 与 Time.deltaTime",
                "FixedUpdate 与 Time.fixedDeltaTime",
                "Rigidbody 物理操作",
                "LateUpdate 相机跟随",
                "重复位移与帧率依赖的调试",
            ],
            "assessment": [
                "根据具体需求选择正确回调并解释调用时序",
                "补全或修正 Unity C# 脚本并给出可验证的运行结果",
                "根据渲染帧和固定时间步的调用轨迹诊断抖动、速度叠加或帧率依赖",
            ],
            "grounding_contract": {"question_evidence_ids": []},
            "difficulty_contract": {"target_level": "intermediate"},
        }],
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def retrieval_projection(package: dict[str, Any]) -> dict[str, Any]:
    web = package.get("web") or {}
    references = [
        *(package.get("content_evidence") or []),
        *(package.get("authoring_patterns") or []),
    ]
    source_rows = []
    seen: set[tuple[str, str]] = set()
    for item in references:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or item.get("source_url") or "")
        title = str(
            item.get("title")
            or (item.get("source") or {}).get("title")
            or item.get("source_type")
            or ""
        )
        key = (title, url)
        if key in seen:
            continue
        seen.add(key)
        source_rows.append({
            "source_type": item.get("source_type"),
            "title": title,
            "url": url,
            "evidence_role": item.get("evidence_role"),
        })
    return {
        "retrieval_mode": package.get("retrieval_mode"),
        "package_revision_id": package.get("package_revision_id"),
        "web": deepcopy(web),
        "objective_coverage": deepcopy(package.get("objective_coverage") or []),
        "source_count": len(source_rows),
        "sources": source_rows[:12],
    }


async def prepare_reference(output: Path) -> dict[str, Any]:
    course = diagnostic_course()
    profile = compile_course_assessment_profile(course)
    objectives = compile_assessment_objectives(course, profile)
    blueprint = compile_course_assessment_blueprint(
        course,
        profile=profile,
        objectives=objectives,
    )
    package = compile_local_reference_package(
        course,
        objectives=objectives,
        blueprint=blueprint,
    )
    package = await enrich_reference_package_with_web(
        course,
        package,
        objectives=objectives,
        user_id="production-assessment-diagnostic",
    )
    write_json(output, package)
    return {
        "status": "completed",
        "course_id": course["course_id"],
        **retrieval_projection(package),
    }


def question_projection(
    item: dict[str, Any],
    solution: dict[str, Any],
) -> dict[str, Any]:
    levels = list(item.get("practice_levels") or [])
    quality = item.get("quality_report") or {}
    return {
        "practice_level": levels[0] if levels else "",
        "question_type": item.get("question_type"),
        "difficulty": item.get("difficulty"),
        "prompt": item.get("prompt"),
        "options": deepcopy(item.get("options") or []),
        "input_contract": deepcopy(item.get("input_contract") or {}),
        "canonical_answer": deepcopy(solution.get("canonical_answer")),
        "worked_solution": deepcopy(solution.get("worked_solution") or {}),
        "rubric": deepcopy(solution.get("rubric") or []),
        "validation_mode": solution.get("validation_mode"),
        "quality": {
            "passed": quality.get("passed"),
            "status": quality.get("status"),
            "score": quality.get("score"),
            "issues": deepcopy(quality.get("issues") or []),
        },
        "risk_flags": deepcopy(item.get("risk_flags") or []),
        "review_required": bool(item.get("review_required")),
        "generation_status": item.get("generation_status"),
        "retrieval_summary": deepcopy(item.get("retrieval_summary") or {}),
    }


async def run_profile(profile: str, reference_path: Path) -> dict[str, Any]:
    course = diagnostic_course()
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    started = time.perf_counter()
    prepared = await AssessmentGenerationOrchestrator().prepare_course(
        course,
        node_ids=[NODE_ID],
        reference_package=reference,
        generation_profile=profile,
        generation_scope="full_generation",
    )
    elapsed_ms = int(round((time.perf_counter() - started) * 1000))
    audit = deepcopy(prepared.get("_assessment_generation_audit") or {})
    bundle = build_question_bank(prepared)
    selected = [
        item
        for item in bundle.get("items") or []
        if (
            item.get("assessment_role") == "practice"
            and str(item.get("node_id") or "") == NODE_ID
        )
    ]
    selected.sort(key=lambda item: PRACTICE_ORDER.get(
        str(next(iter(item.get("practice_levels") or []), "")),
        99,
    ))
    envelopes = bundle.get("solution_envelopes") or {}
    questions = [
        question_projection(
            item,
            envelopes.get(str(item.get("solution_revision_id") or "")) or {},
        )
        for item in selected
    ]
    physical_calls = [
        item
        for item in audit.get("physical_calls") or []
        if isinstance(item, dict)
    ]
    completed_calls = [
        item for item in physical_calls if item.get("status") == "completed"
    ]
    has_degraded_fallback = any(
        "ai_validation_unavailable" in (question.get("risk_flags") or [])
        for question in questions
    )
    real_model_output = bool(
        len(questions) == 3
        and completed_calls
        and not has_degraded_fallback
        and int(audit.get("failure_count") or 0) == 0
    )
    return {
        "status": "completed",
        "profile": profile,
        "provider_forced": "modelscope_fallback",
        "configured_model": os.getenv("MODELSCOPE_MODEL", ""),
        "real_model_output": real_model_output,
        "elapsed_ms": elapsed_ms,
        "retrieval": retrieval_projection(reference),
        "metrics": {
            key: deepcopy(audit.get(key))
            for key in (
                "assessment_generation_policy_version",
                "generation_scope",
                "wall_clock_ms",
                "logical_call_count",
                "physical_model_call_count",
                "provider_attempt_count",
                "estimated_input_tokens",
                "estimated_output_tokens",
                "provider_queue_wait_ms",
                "request_spacing_wait_ms",
                "transport_setup_ms",
                "time_to_first_token_ms",
                "stream_duration_ms",
                "thinking_requested_call_count",
                "thinking_requested_duration_ms",
                "non_thinking_duration_ms",
                "first_pass_pass_count",
                "first_pass_pass_rate",
                "review_required_count",
                "review_required_rate",
                "generation_calls",
                "batch_generation_calls",
                "independent_solution_calls",
                "batch_independent_solution_calls",
                "local_independent_solution_count",
                "semantic_evaluation_calls",
                "batch_semantic_evaluation_calls",
                "repair_calls",
                "fallback_count",
                "failure_count",
            )
        },
        "call_timings": deepcopy(audit.get("call_timings") or []),
        "physical_calls": physical_calls,
        "questions": questions,
    }


def failure_payload(operation: str, error: Exception) -> dict[str, Any]:
    return {
        "status": "failed",
        "operation": operation,
        "error_type": type(error).__name__,
        "error": str(error)[:2000],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--reference", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--profile", choices=("fast", "deliberate"), required=True)
    run.add_argument("--reference", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output
    try:
        if args.command == "prepare":
            payload = asyncio.run(prepare_reference(args.reference))
        else:
            payload = asyncio.run(run_profile(args.profile, args.reference))
    except Exception as error:  # Diagnostic must preserve failure evidence.
        payload = failure_payload(args.command, error)
    write_json(output, payload)
    print(json.dumps({
        "status": payload.get("status"),
        "operation": args.command,
        "profile": payload.get("profile"),
        "real_model_output": payload.get("real_model_output"),
        "question_count": len(payload.get("questions") or []),
        "metrics": payload.get("metrics") or {},
        "error_type": payload.get("error_type"),
        "error": payload.get("error"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
