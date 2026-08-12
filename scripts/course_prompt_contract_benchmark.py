#!/usr/bin/env python3
"""Compare the production course prompt with a generic role-only baseline.

This benchmark does not call an AI provider and therefore does not claim
content quality or latency.  It checks whether a prompt exposes the contracts
that a human or model needs before it can produce a reliable course artifact.
Provider or manual output review remains a separate acceptance layer.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for module_root in (ROOT, BACKEND):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from ai_base import AIBase  # noqa: E402
from course_design_contract import (  # noqa: E402
    COURSE_DESIGN_CONTRACT_VERSION,
    compile_course_design_contract,
)
from course_difficulty import (  # noqa: E402
    assess_readiness,
    compile_difficulty_profile,
    decide_adaptation,
)
from course_generation_workflow import (  # noqa: E402
    attach_difficulty_artifacts,
    attach_pedagogy_profile,
    build_course_generation_artifacts,
)
from course_pedagogy import resolve_pedagogy_profile  # noqa: E402
from course_prompt_composer import (  # noqa: E402
    PROMPT_CONTRACT_VERSION,
    CoursePromptComposer,
)


DEFAULT_MANIFEST = ROOT / "benchmarks" / "course_generation_v2" / "manifest.json"
PROMPT_BUDGET_CHARS = 20_000
PROMPT_BUDGET_TOKENS = 7_000


def generic_role_prompt(scenario: dict[str, Any]) -> str:
    """Return the common role-only prompt used as the weak baseline."""
    request = scenario.get("request") or {}
    return (
        "你是一名资深课程设计专家。请为"
        f"「{request.get('subject') or ''}」生成一门高质量课程。"
        f"学习对象是{request.get('target_audience') or '学习者'}，"
        f"难度为{request.get('difficulty') or 'intermediate'}，"
        f"生成 {scenario.get('expected_chapters') or 0} 章"
        f" {scenario.get('expected_sections') or 0} 节。"
        "课程要专业、完整、循序渐进，请输出 JSON。"
    )


def _compile_production_outline_prompt(
    scenario: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    request = deepcopy(scenario.get("request") or {})
    artifacts = build_course_generation_artifacts(
        course_id=str(scenario.get("id") or "prompt-benchmark"),
        topic=str(request.get("subject") or ""),
        difficulty=str(request.get("difficulty") or "intermediate"),
        style="balanced",
        requirements=str(request.get("requirements") or ""),
        target_audience=str(request.get("target_audience") or ""),
        course_type=str(request.get("course_type") or "systematic"),
        course_intent=request.get("course_intent"),
        teacher_course_brief=request.get("teacher_course_brief"),
        grounding_strategy="material_first",
        course_purpose=str(request.get("course_type") or "systematic"),
    )
    profile = resolve_pedagogy_profile(
        subject=str(request.get("subject") or ""),
        requirements=str(request.get("requirements") or ""),
        materials=[],
        requested_mode=str(request.get("pedagogy_mode") or "auto"),
    )
    attach_pedagogy_profile(artifacts, profile)
    difficulty = compile_difficulty_profile(
        request.get("difficulty") or "intermediate",
        primary_mode=profile.primary_mode,
        secondary_mode=profile.secondary_mode,
    )
    gap = assess_readiness(difficulty, None)
    adaptation = decide_adaptation(gap)
    attach_difficulty_artifacts(
        artifacts,
        profile=difficulty,
        gap_assessment=gap,
        adaptation_decision=adaptation,
    )
    design_contract = compile_course_design_contract(
        brief=artifacts["course_generation_brief"],
        subject_template=artifacts["subject_generation_template"],
        difficulty_profile=difficulty.to_dict(),
        gap_assessment=gap.to_dict(),
        adaptation_decision=adaptation.to_dict(),
        grounding_strategy="material_first",
    )
    prompt = CoursePromptComposer().build_outline_skeleton_v2_prompt(
        subject=str(request.get("subject") or ""),
        audience=str(request.get("target_audience") or ""),
        brief=artifacts["course_generation_brief"],
        profile=profile,
        difficulty_profile=difficulty.to_dict(),
        gap_assessment=gap.to_dict(),
        adaptation_decision=adaptation.to_dict(),
        material_context=(
            "当前场景含准入资料。"
            if scenario.get("material_files")
            else ""
        ),
        design_contract=design_contract,
    )
    return prompt, {
        "template_id": artifacts["subject_generation_template"]["template_id"],
        "primary_mode": profile.primary_mode.value,
        "subject_variant_id": profile.subject_variant_id,
    }


def evaluate_prompt_contract(
    prompt: str,
    *,
    template_id: str = "",
) -> dict[str, Any]:
    """Score observable prompt-contract coverage, not generated content."""
    checks = {
        "single_stage_scope": all(
            marker in prompt
            for marker in ("唯一责任", "唯一允许输出", "禁止修改")
        ),
        "instruction_precedence": "执行优先级" in prompt,
        "data_instruction_isolation": "输入隔离" in prompt,
        "result_density": "结果密度" in prompt,
        "domain_contract": bool(template_id and template_id in prompt),
        "decision_sequence": "决策顺序" in prompt,
        "silent_preflight": "提交前静默核验" in prompt,
        "artifact_quality_bar": "产物质量门" in prompt,
        "grounding_boundary": "不得伪造" in prompt,
        "machine_output_contract": "JSON Schema" in prompt,
    }
    chars = len(prompt)
    tokens = AIBase.estimate_request_tokens("", prompt)
    return {
        "passed_dimensions": sum(checks.values()),
        "dimension_count": len(checks),
        "checks": checks,
        "prompt_chars": chars,
        "estimated_input_tokens": tokens,
        "budget_passed": (
            chars <= PROMPT_BUDGET_CHARS
            and tokens <= PROMPT_BUDGET_TOKENS
        ),
    }


def without_execution_control(prompt: str) -> str:
    """Remove the V31 execution-control layer for an ablation comparison."""
    omitted_labels = (
        "- 执行优先级：",
        "- 输入隔离：",
        "- 结果密度：",
        "- 决策顺序：",
        "- 提交前静默核验：",
        "- 产物质量门：",
    )
    return "\n".join(
        line for line in prompt.splitlines()
        if not line.startswith(omitted_labels)
    )


def build_report(manifest: dict[str, Any]) -> dict[str, Any]:
    comparisons: list[dict[str, Any]] = []
    scenarios = list(manifest.get("scenarios") or []) + list(
        manifest.get("prompt_contract_scenarios") or []
    )
    for scenario in scenarios:
        production, context = _compile_production_outline_prompt(scenario)
        baseline = generic_role_prompt(scenario)
        structured_without_control = without_execution_control(production)
        comparisons.append({
            "scenario_id": scenario.get("id"),
            "discipline": scenario.get("discipline"),
            **context,
            "variants": {
                "generic_role_only": evaluate_prompt_contract(baseline),
                "structured_without_execution_control": (
                    evaluate_prompt_contract(
                        structured_without_control,
                        template_id=context["template_id"],
                    )
                ),
                "production_contract": evaluate_prompt_contract(
                    production,
                    template_id=context["template_id"],
                ),
            },
        })
    production_results = [
        item["variants"]["production_contract"]
        for item in comparisons
    ]
    return {
        "schema_version": "course_prompt_contract_benchmark_v1",
        "prompt_contract_version": PROMPT_CONTRACT_VERSION,
        "course_design_contract_version": COURSE_DESIGN_CONTRACT_VERSION,
        "scope": (
            "静态合同覆盖与输入预算；不代表真实模型内容质量或延迟"
        ),
        "all_production_contracts_passed": all(
            item["passed_dimensions"] == item["dimension_count"]
            and item["budget_passed"]
            for item in production_results
        ),
        "comparisons": comparisons,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = build_report(manifest)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["all_production_contracts_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
