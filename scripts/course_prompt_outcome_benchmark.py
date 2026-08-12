#!/usr/bin/env python3
"""Generate fixed course artifacts with the development-only local Codex route.

The static prompt-contract benchmark checks whether instructions are present.
This runner checks the next layer: what the same model actually produces for a
fixed outline, knowledge-library and lesson-plan task.  One run is diagnostic,
not a release claim; keep model, reasoning effort and fixtures fixed when
comparing prompt revisions.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for module_root in (ROOT, BACKEND):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from codex_local_provider import CodexLocalProvider  # noqa: E402
from course_design_contract import compile_course_design_contract  # noqa: E402
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
from scripts.course_prompt_contract_benchmark import (  # noqa: E402
    DEFAULT_MANIFEST,
    _compile_production_outline_prompt,
)


def _calculus_context() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    scenario = next(
        item for item in manifest["scenarios"]
        if item["id"] == "calculus_4x8"
    )
    request = scenario["request"]
    artifacts = build_course_generation_artifacts(
        course_id="calculus-prompt-outcome-benchmark",
        topic=request["subject"],
        difficulty=request["difficulty"],
        style="balanced",
        requirements=request["requirements"],
        target_audience=request["target_audience"],
        course_type=request["course_type"],
        teacher_course_brief=request["teacher_course_brief"],
        grounding_strategy="material_first",
        course_purpose=request["course_type"],
    )
    profile = resolve_pedagogy_profile(
        subject=request["subject"],
        requirements=request["requirements"],
        requested_mode=request.get("pedagogy_mode", "auto"),
    )
    attach_pedagogy_profile(artifacts, profile)
    difficulty = compile_difficulty_profile(
        request["difficulty"],
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
    contract = compile_course_design_contract(
        brief=artifacts["course_generation_brief"],
        subject_template=artifacts["subject_generation_template"],
        difficulty_profile=difficulty.to_dict(),
        gap_assessment=gap.to_dict(),
        adaptation_decision=adaptation.to_dict(),
        grounding_strategy="material_first",
    )
    return scenario, artifacts, contract


def build_fixed_prompts() -> dict[str, str]:
    """Compile production prompts for one fixed, human-readable comparison."""
    scenario, artifacts, contract = _calculus_context()
    request = scenario["request"]
    outline, _context = _compile_production_outline_prompt(scenario)
    composer = CoursePromptComposer()
    section = {
        "node_id": "L2-1-1",
        "node_name": "函数极限：从趋近直觉到 ε-δ 定义",
        "learning_objective": (
            "能在数值、图像与符号表征之间解释函数极限，并用 ε-δ "
            "定义检验一个简单极限命题"
        ),
        "assessment": [
            "为 lim(x→2)(3x+1)=7 构造 δ(ε)，并解释每个不等式变形"
        ],
        "scope_boundary": (
            "只讨论一点处有限函数极限；不提前展开连续性、无穷极限或数列极限判别法"
        ),
        "allowed_module_ids": [
            "math_intuition",
            "math_formalization",
            "math_worked_example",
            "math_error_analysis",
        ],
        "lesson_archetype": {
            "id": "math_definition_building",
            "purpose": "从表征观察进入形式定义并以边界反例校准",
            "evidence": "学生能独立解释量词顺序并构造 δ(ε)",
        },
        "evidence_hints": [],
        "planned_minutes": 45,
    }
    registry = [
        {
            "knowledge_key": "K001",
            "name": "一点处有限函数极限",
            "statement": (
                "函数值在自变量趋近一点时可趋近确定值，极限描述邻域中的趋近而不要求"
                "点值存在或相等。"
            ),
            "owner_node_id": "L2-1-1",
            "prerequisite_keys": [],
            "module_ids": ["math_intuition", "math_worked_example"],
        },
        {
            "knowledge_key": "K002",
            "name": "函数极限的 ε-δ 定义",
            "statement": (
                "对任意 ε>0，都存在 δ>0，使 0<|x-a|<δ 时必有 |f(x)-L|<ε。"
            ),
            "owner_node_id": "L2-1-1",
            "prerequisite_keys": ["K001"],
            "module_ids": ["math_formalization", "math_error_analysis"],
        },
    ]
    identities = [{
        "node_id": "L2-1-1",
        "owned_knowledge_keys": ["K001", "K002"],
        "reused_knowledge_keys": [],
    }]
    positioning = "以极限为逻辑基础建立一元微积分的定义、推理与应用链"
    knowledge = composer.build_course_knowledge_batch_v1_prompt(
        course_title=request["subject"],
        positioning=positioning,
        batch_spec={"batch_id": "KB-01", "section_ids": ["L2-1-1"]},
        batch_sections=[section],
        knowledge_registry=registry,
        section_identities=identities,
        skeleton_revision_id="outcome-skeleton-fixed",
        subject_template=artifacts["subject_generation_template"],
        design_contract=contract,
    )
    frozen = [
        {
            **registry[0],
            "conditions": ["a 是定义域的聚点"],
            "boundaries": ["极限不决定 f(a)"],
            "positive_examples": ["f(x)=3x+1 在 x→2 时极限为 7"],
            "counterexamples": ["只检查 f(2)=7 不能证明极限为 7"],
            "capability_points": [{
                "name": "区分极限与点值",
                "observable_behavior": "根据邻域行为判断极限，不用点值代替",
                "required_evidence_types": ["practice_attempt"],
            }],
            "misconceptions": [{
                "name": "用点值代替极限",
                "observable_error_pattern": "直接以 f(a) 作为极限",
                "confused_with": "函数在点处的取值",
                "discrimination": "比较去心邻域与点值",
                "repair_strategy": "构造点值改变但极限不变的例子",
            }],
            "mastery_criteria": [{
                "name": "表征极限",
                "observable_performance": "一致解释多种表征并指出点值无关",
                "required_independence": "independent",
                "required_transfer": "variation",
                "verification_method": "判断点值改变后的极限",
                "required_evidence_types": ["practice_attempt"],
            }],
            "source_refs": [],
            "confidence": "medium",
        },
        {
            **registry[1],
            "conditions": ["量词顺序为任意 ε 后存在 δ"],
            "boundaries": ["δ 可依赖 ε，但不能依赖具体 x"],
            "positive_examples": ["对 f(x)=3x+1 取 δ=ε/3"],
            "counterexamples": ["固定 δ 再覆盖任意 ε 通常失败"],
            "capability_points": [{
                "name": "构造 δ(ε)",
                "observable_behavior": "反推并正向验证 δ",
                "required_evidence_types": ["practice_attempt"],
            }],
            "misconceptions": [{
                "name": "颠倒量词",
                "observable_error_pattern": "先选固定 δ 再处理任意 ε",
                "confused_with": "存在一个统一邻域",
                "discrimination": "检查 δ 是否随 ε 收紧",
                "repair_strategy": "用更小 ε 反驳固定 δ",
            }],
            "mastery_criteria": [{
                "name": "完成线性函数定义证明",
                "observable_performance": "独立构造 δ(ε) 并解释量词顺序",
                "required_independence": "independent",
                "required_transfer": "variation",
                "verification_method": "更换斜率与趋近点后重新证明",
                "required_evidence_types": ["practice_attempt"],
            }],
            "source_refs": [],
            "confidence": "medium",
        },
    ]
    teaching = composer.build_teaching_execution_batch_v1_prompt(
        course_title=request["subject"],
        positioning=positioning,
        batch_spec={"batch_id": "TP-01", "section_ids": ["L2-1-1"]},
        batch_sections=[section],
        frozen_knowledge=frozen,
        section_identities=identities,
        module_catalog=[
            {"module_id": "math_intuition", "label": "趋近直觉", "output_contract": "以数值或图像比较点值与邻域行为"},
            {"module_id": "math_formalization", "label": "形式定义", "output_contract": "明确量词、去心邻域与 δ 对 ε 的依赖"},
            {"module_id": "math_worked_example", "label": "完整例题", "output_contract": "完整构造并正向验证 δ(ε)"},
            {"module_id": "math_error_analysis", "label": "错误辨析", "output_contract": "用反例辨析点值替代与量词颠倒"},
        ],
        knowledge_revision_id="outcome-knowledge-fixed",
        subject_template=artifacts["subject_generation_template"],
        design_contract=contract,
        overall_guidance={
            "teaching_throughline": "从多重表征形成需要，再进入正式定义、完整例题和量词错误辨析",
            "assessment_methods": ["板演定义证明", "出口条解释量词顺序"],
        },
    )
    return {"outline": outline, "knowledge": knowledge, "teaching": teaching}


async def generate(stages: list[str]) -> dict[str, Any]:
    prompts = build_fixed_prompts()

    async def run(stage: str) -> dict[str, Any]:
        output, telemetry = await CodexLocalProvider.from_environment().complete(
            f"生成固定对照的{stage}产物，只输出符合契约的结果。",
            prompts[stage],
            use_fast_model=False,
            json_mode=True,
            max_tokens=5_000,
        )
        return {"stage": stage, "telemetry": telemetry, "output": output}

    results = await asyncio.gather(*(run(stage) for stage in stages))
    return {
        "schema_version": "course_prompt_outcome_benchmark_v1",
        "prompt_contract_version": PROMPT_CONTRACT_VERSION,
        "scope": "固定输入单次本地模型诊断，不代表生产质量或时延发布门",
        "results": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stages",
        nargs="+",
        choices=("outline", "knowledge", "teaching"),
        default=["outline", "knowledge", "teaching"],
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(json.dumps(
        asyncio.run(generate(args.stages)),
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
