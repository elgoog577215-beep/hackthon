"""
课程生成服务。

核心职责：
- 将生成需求、参考资料和教学画像编译为课程蓝图
- 使用持久化的节点模块契约流式生成正文
- 编译课程知识、关系、正文和题目合同，并执行确定性结构与引用检查
- 为用户主动发起的局部重写保留课程与学习上下文
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import (
    Any,
)

from ai_base import AIBase, AIProviderRequestError
from ai_learning_context import build_ai_learning_context
from ai_output_quality import assess_ai_output
from content_blocks import (
    normalize_blocks,
    set_node_content_blocks,
    strip_leading_heading,
    summarize_text,
)
from course_coherence import (
    compile_course_coherence_contract,
    evaluate_course_coherence,
)
from course_composition import (
    attach_composition_to_plan,
    compile_composition_profile,
)
from course_context import CourseContextManager, get_context_manager
from course_difficulty import (
    assess_readiness,
    attach_difficulty_contracts_to_plan,
    compile_course_difficulty_curve,
    compile_difficulty_profile,
    decide_adaptation,
    ensure_course_difficulty_contracts,
    format_difficulty_profile,
    format_node_difficulty_contract,
    parse_difficulty_level,
)
from course_generation_strategy import (
    PERSONALIZED_NODE_EXPLANATION,
    WEAKNESS_REMEDIATION_CONTENT,
    build_course_generation_strategy_prompt,
    classify_generation_use_case,
)
from course_generation_workflow import (
    PIPELINE_VERSION,
    apply_course_teaching_plan,
    apply_section_knowledge_package,
    attach_course_relation_plan,
    attach_difficulty_artifacts,
    attach_generation_artifacts_to_plan,
    attach_pedagogy_profile,
    build_course_blueprint_from_plan,
    build_course_generation_artifacts,
    build_course_knowledge_scope_contract,
    build_node_generation_context,
    build_outline_generation_context,
    build_section_knowledge_material_context,
    build_section_knowledge_scope_slice,
    build_section_knowledge_skeleton_evidence_hints,
    compile_course_teaching_plan_modules,
    merge_course_relation_batches,
    normalize_course_knowledge_skeleton,
    normalize_course_outline_contract,
    normalize_course_plan_contract,
    normalize_course_relation_batch,
    normalize_section_knowledge_node_package,
    validate_course_knowledge_skeleton,
    validate_course_outline_constraints,
    validate_course_plan_constraints,
    repair_course_relation_batch_decisions,
    validate_course_relation_batch,
    validate_course_teaching_plan,
    validate_section_knowledge_package,
)
from course_knowledge_base import (
    bind_course_knowledge_base_to_map,
    compile_course_knowledge_base,
    course_knowledge_base_prompt_context,
)
from course_knowledge_map import (
    compile_course_knowledge_map,
    normalize_knowledge_structure,
)
from course_pedagogy import (
    SubjectPedagogyProfile,
    attach_module_plans_to_plan,
    coerce_persisted_profile,
    parse_mode,
    resolve_pedagogy_profile,
)
from course_planning_budget import (
    CoursePlanningBudget,
    build_compact_planning_context,
    build_teaching_plan_batches,
    estimate_json_tokens,
)
from course_prompt_composer import (
    PROMPT_CONTRACT_VERSION,
    CoursePromptComposer,
    get_course_prompt_composer,
)
from course_teaching_plan_v3 import (
    assemble_course_teaching_plan_v3,
    normalize_teaching_plan_batch_v3,
    normalize_teaching_plan_skeleton_v3,
    validate_teaching_plan_batch_v3,
    validate_teaching_plan_skeleton_v3,
)
from course_quality import evaluate_node_content, validate_blueprint
from learner_context import DEFAULT_USER_ID
from material_evidence import attach_evidence_to_plan, extract_grounding_annotations
from material_pipeline import prepare_course_materials
from material_storage import MaterialRepository, material_repository
from models import NodeGenerationConfig

logger = logging.getLogger(__name__)

DEFAULT_COURSE_PLANNING_CONCURRENCY = 4
MAX_COURSE_PLANNING_CONCURRENCY = 8


def _resolve_course_planning_concurrency(value: int | None = None) -> int:
    raw_value: Any = (
        value
        if value is not None
        else os.getenv(
            "COURSE_GENERATION_PLANNING_CONCURRENCY",
            str(DEFAULT_COURSE_PLANNING_CONCURRENCY),
        )
    )
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        parsed = DEFAULT_COURSE_PLANNING_CONCURRENCY
    return max(1, min(MAX_COURSE_PLANNING_CONCURRENCY, parsed))


EVIDENCE_INDEX_FIELDS = (
    "evidence_id",
    "asset_id",
    "document_id",
    "kind",
    "locator",
    "purpose",
    "priority",
    "authority",
    "usage_policy",
    "factual_allowed",
    "confidence",
)


def _compact_evidence_index(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: item[key] for key in EVIDENCE_INDEX_FIELDS if key in item}
        for item in catalog
    ]


def _coherence_repair_suggestion(issue: dict[str, Any]) -> str:
    if issue.get("code") == "coherence:incorrect_next_section_handoff":
        return (
            "删除或改正错误的下一节预告，使它与全课总编契约中的实际后续小节一致；"
            "本节已经完成的知识不得再声称属于下一节"
        )
    return (
        "保留与前置章节的一两句承接，删除或重写重复讲解，"
        "把篇幅用于当前小节独有的知识、例子、任务与验收"
    )


# ---------------------------------------------------------------------------
# CourseService
# ---------------------------------------------------------------------------

class CourseService(AIBase):
    """课程生成编排门面，只依赖当前 V3 prompt 与课程上下文。"""

    def __init__(
        self,
        context_manager: CourseContextManager | None = None,
        prompt_composer: CoursePromptComposer | None = None,
        materials: MaterialRepository | None = None,
        planning_concurrency: int | None = None,
    ) -> None:
        super().__init__()
        self._context_manager = context_manager or get_context_manager()
        self._prompt_composer = prompt_composer or get_course_prompt_composer()
        self._material_repository = materials or material_repository
        self._course_generation_artifacts: dict[str, dict] = {}
        self._planning_concurrency = _resolve_course_planning_concurrency(
            planning_concurrency
        )
        self._planning_semaphore = asyncio.Semaphore(
            self._planning_concurrency
        )
        self._teaching_plan_budget = CoursePlanningBudget.from_env()
        self._teaching_plan_semaphore = asyncio.Semaphore(
            self._teaching_plan_budget.concurrency
        )

    # ------------------------------------------------------------------
    # 解析辅助方法
    # ------------------------------------------------------------------

    def _parse_difficulty(self, depth: str) -> str:
        return parse_difficulty_level(depth).value

    def _parse_audience(self, audience: str) -> str:
        mapping = {
            "高中生": "high_school",
            "大学生": "undergraduate",
            "研究生": "graduate",
            "从业者": "professional",
            "专业人员": "professional",
        }
        return mapping.get(audience, audience.strip() or "undergraduate")

    def register_course_generation_metadata(self, course_id: str, course_data: dict[str, Any]) -> None:
        """从已保存课程恢复资料增强生成上下文。

        TaskManager 可能在课程创建之后、正文生成之前重新加载课程数据；这里把
        保存到课程 JSON 的新链路中间对象重新注册回运行时，让节点正文生成可以
        继续读取 brief、证据目录和 blueprint。
        """
        if not course_id or not course_data:
            return
        pedagogy = coerce_persisted_profile(course_data)
        ensure_course_difficulty_contracts(
            course_data,
            primary_mode=pedagogy.primary_mode,
            secondary_mode=pedagogy.secondary_mode,
        )
        metadata_keys = [
            "generation_pipeline_version",
            "course_name",
            "difficulty",
            "target_audience",
            "generation_request",
            "generation_mode",
            "course_purpose",
            "asset_preferences",
            "web_question_enrichment",
            "requirements",
            "subject_pedagogy_profile",
            "difficulty_profile",
            "difficulty_gap_assessment",
            "adaptation_decision",
            "course_difficulty_curve",
            "material_cards",
            "course_generation_brief",
            "material_assets",
            "material_bindings",
            "parsed_documents",
            "evidence_index",
            "evidence_coverage_plan",
            "course_blueprint",
            "generation_quality_report",
        ]
        metadata = {key: course_data.get(key) for key in metadata_keys if course_data.get(key) is not None}
        if metadata:
            metadata["evidence_catalog"] = (
                course_data.get("evidence_catalog")
                or self._load_evidence_catalog(metadata.get("material_bindings") or [])
            )
            metadata["pipeline_version"] = metadata.get("generation_pipeline_version") or metadata.get("pipeline_version")
            self._course_generation_artifacts[course_id] = metadata

    def clear_generation_state(self, course_id: str) -> None:
        """Drop process-local generation projections for a deleted or reset course."""
        self._course_generation_artifacts.pop(course_id, None)
        self._context_manager.clear_context(course_id)

    def _load_evidence_catalog(self, bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        catalog: list[dict[str, Any]] = []
        seen: set[str] = set()
        for binding in bindings:
            asset_id = str(binding.get("asset_id") or "")
            if not asset_id or asset_id in seen:
                continue
            seen.add(asset_id)
            try:
                catalog.extend(self._material_repository.load_evidence(asset_id))
            except (OSError, ValueError):
                continue
        return catalog

    def load_course_evidence_catalog(
        self,
        course_data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Load full source text only for server-side compilation.

        Persisted course metadata intentionally keeps a compact evidence index;
        question-bank compilation resolves the full evidence from the bound
        material repository and does not publish it to learner-facing views.
        """
        catalog = course_data.get("evidence_catalog")
        if isinstance(catalog, list) and catalog:
            return deepcopy(catalog)
        return self._load_evidence_catalog(course_data.get("material_bindings") or [])

    # ------------------------------------------------------------------
    # 资料增强课程生成主链路
    # ------------------------------------------------------------------

    async def build_course_draft(
        self,
        *,
        course_id: str,
        topic: str,
        target_audience: str = "大学生",
        depth: str = "intermediate",
        style: str | None = None,
        composition_style: str | None = None,
        requirements: str = "",
        materials: list[Any] | None = None,
        material_bindings: list[Any] | None = None,
        grounding_strategy: str = "material_first",
        learner_profile_summary: str = "",
        current_readiness: str | None = None,
        adaptation_preference: str = "preserve_target_extend",
        pedagogy_mode: str = "auto",
        secondary_mode: str | None = None,
        secondary_intensity: str | None = None,
        generation_mode: str = "fast",
        course_purpose: str = "systematic",
        asset_preferences: dict[str, bool] | None = None,
        web_question_enrichment: dict[str, Any] | None = None,
        existing_course_data: dict[str, Any] | None = None,
        stop_after_outline: bool = False,
        on_phase: Callable[..., Awaitable[None] | None] | None = None,
        on_checkpoint: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
    ) -> dict[str, Any]:
        """Build and validate the persisted course blueprint for one GenerationJob."""
        difficulty = self._parse_difficulty(depth)
        audience = self._parse_audience(target_audience)
        material_inputs = materials or []
        existing = existing_course_data or {}
        composition_profile = compile_composition_profile(
            composition_style,
            legacy_style=style,
        )

        await self._notify_phase(
            on_phase,
            "requirement_analysis",
            5,
            "正在整理课程需求",
            phase_progress=100,
        )
        checkpoint_ready = all(
            key in existing
            for key in (
                "material_cards",
                "course_generation_brief",
                "evidence_index",
                "subject_pedagogy_profile",
            )
        ) and str(existing.get("generation_pipeline_version") or "") in {
            "course_generation_v3",
            "course_generation_v4",
            "course_generation_v5",
            "course_generation_v6",
            "course_generation_v7",
            "course_generation_v8",
            "course_generation_v9",
        }
        if checkpoint_ready:
            artifacts = {
                "pipeline_version": PIPELINE_VERSION,
                "material_cards": existing.get("material_cards") or [],
                "course_generation_brief": existing.get("course_generation_brief") or {},
                "material_assets": existing.get("material_assets") or [],
                "material_bindings": existing.get("material_bindings") or [],
                "parsed_documents": existing.get("parsed_documents") or [],
                "evidence_index": existing.get("evidence_index") or [],
                "evidence_catalog": (
                    existing.get("evidence_catalog")
                    or self._load_evidence_catalog(existing.get("material_bindings") or [])
                ),
                "evidence_coverage_plan": existing.get("evidence_coverage_plan") or {},
                "subject_pedagogy_profile": existing.get("subject_pedagogy_profile") or {},
                "difficulty_profile": existing.get("difficulty_profile") or {},
                "difficulty_gap_assessment": existing.get("difficulty_gap_assessment") or {},
                "adaptation_decision": existing.get("adaptation_decision") or {},
                "course_composition_profile": (
                    existing.get("course_composition_profile") or composition_profile
                ),
            }
            profile = coerce_persisted_profile(existing)
            await self._notify_phase(
                on_phase,
                "material_processing",
                25,
                "已恢复资料处理检查点",
                phase_progress=100,
            )
        else:
            async def on_material_progress(detail: dict[str, Any]) -> None:
                total = max(1, int(detail.get("item_total") or 1))
                index = max(1, int(detail.get("item_index") or 1))
                completed_credit = 1 if detail.get("status") in {"parsed", "degraded", "failed", "metadata_only"} else 0
                phase_progress = min(100, int(((index - 1 + completed_credit) / total) * 100))
                global_progress = 5 + int(phase_progress * 0.2)
                await self._notify_phase(
                    on_phase,
                    "material_processing",
                    global_progress,
                    str(detail.get("message") or "正在处理参考资料"),
                    phase_progress=phase_progress,
                    phase_detail=detail,
                )

            prepared_materials = await prepare_course_materials(
                course_id=course_id,
                material_bindings=material_bindings,
                legacy_materials=material_inputs or existing.get("material_cards") or [],
                repository=self._material_repository,
                on_progress=on_material_progress,
            )
            artifacts = build_course_generation_artifacts(
                course_id=course_id,
                topic=topic,
                difficulty=difficulty,
                style=style,
                requirements=requirements,
                target_audience=audience,
                materials=material_inputs,
                learner_profile_summary=learner_profile_summary,
                prepared_materials=prepared_materials,
                grounding_strategy=grounding_strategy,
            )

            await self._notify_phase(
                on_phase,
                "material_processing",
                25,
                "资料解析与证据目录已准备",
                phase_progress=100,
            )
            if existing.get("subject_pedagogy_profile"):
                profile = coerce_persisted_profile(existing)
            else:
                profile = await self._resolve_course_pedagogy(
                    subject=topic,
                    requirements=requirements,
                    materials=artifacts.get("material_cards") or material_inputs,
                    artifacts=artifacts,
                    requested_mode=pedagogy_mode,
                    requested_secondary_mode=secondary_mode,
                    requested_intensity=secondary_intensity,
                )
            attach_pedagogy_profile(artifacts, profile)

        artifacts["course_composition_profile"] = composition_profile

        difficulty_profile = compile_difficulty_profile(
            difficulty,
            primary_mode=profile.primary_mode,
            secondary_mode=profile.secondary_mode,
        )
        gap_assessment = assess_readiness(difficulty_profile, current_readiness)
        adaptation_decision = decide_adaptation(
            gap_assessment,
            adaptation_preference,
        )
        attach_difficulty_artifacts(
            artifacts,
            profile=difficulty_profile,
            gap_assessment=gap_assessment,
            adaptation_decision=adaptation_decision,
        )
        await self._notify_checkpoint(on_checkpoint, {
            "generation_pipeline_version": artifacts["pipeline_version"],
            "material_cards": artifacts["material_cards"],
            "course_generation_brief": artifacts["course_generation_brief"],
            "material_assets": artifacts.get("material_assets", []),
            "material_bindings": artifacts.get("material_bindings", []),
            "parsed_documents": artifacts.get("parsed_documents", []),
            "evidence_index": _compact_evidence_index(artifacts.get("evidence_catalog", [])),
            "evidence_coverage_plan": artifacts.get("evidence_coverage_plan", {}),
            "subject_pedagogy_profile": profile.to_dict(),
            "difficulty_profile": difficulty_profile.to_dict(),
            "difficulty_gap_assessment": gap_assessment.to_dict(),
            "adaptation_decision": adaptation_decision.to_dict(),
            "course_composition_profile": composition_profile,
            "generation_status": "difficulty_compiled",
        })

        await self._notify_phase(
            on_phase,
            "pedagogy_resolution",
            32,
            "教学画像与难度契约已确定",
            phase_progress=100,
        )
        saved_plan = existing.get("course_plan") or existing.get("course_outline")
        plan: dict[str, Any] | None = (
            normalize_course_outline_contract(deepcopy(saved_plan))
            if isinstance(saved_plan, dict) and saved_plan.get("chapters")
            else None
        )
        plan_constraint_report = (
            validate_course_outline_constraints(
                plan or {},
                artifacts["course_generation_brief"],
            )
        )
        outline_was_generated = not plan_constraint_report.get("passed")
        if not plan_constraint_report.get("passed"):
            prompt = self._prompt_composer.build_outline_prompt(
                subject=topic,
                audience=audience,
                brief=artifacts["course_generation_brief"],
                profile=profile,
                difficulty_profile=difficulty_profile.to_dict(),
                gap_assessment=gap_assessment.to_dict(),
                adaptation_decision=adaptation_decision.to_dict(),
                material_context=build_outline_generation_context(artifacts),
            )
            response = await self._call_llm_with_heartbeat(
                f"为「{topic}」生成轻量课程目录，只输出 JSON。",
                prompt,
                enable_thinking=True,
                on_phase=on_phase,
                phase="outline_generation",
                base_progress=32,
                heartbeat_message="仍在等待 AI 生成轻量课程目录",
            )
            plan, plan_constraint_report = self._validated_course_outline(
                response,
                artifacts["course_generation_brief"],
            )
            if not plan_constraint_report.get("passed"):
                await self._notify_phase(
                    on_phase,
                    "outline_validation",
                    34,
                    "课程目录未通过结构或数量检查，正在局部重新规划目录",
                    phase_progress=50,
                    phase_detail={
                        "artifact_type": "course_outline",
                        "issue_codes": [
                            item.get("code")
                            for item in plan_constraint_report.get("issues") or []
                        ],
                    },
                )
                correction_prompt = self._prompt_composer.build_outline_correction_prompt(
                    original_prompt=prompt,
                    brief=artifacts["course_generation_brief"],
                    issues=plan_constraint_report.get("issues") or [],
                )
                corrected_response = await self._call_llm_with_heartbeat(
                    f"重新生成「{topic}」轻量课程目录，修复上一次的验收问题。",
                    correction_prompt,
                    enable_thinking=False,
                    on_phase=on_phase,
                    phase="outline_validation",
                    base_progress=34,
                    heartbeat_message="仍在等待 AI 修复轻量课程目录",
                )
                plan, plan_constraint_report = self._validated_course_outline(
                    corrected_response,
                    artifacts["course_generation_brief"],
                )
        if not plan_constraint_report.get("passed") or plan is None:
            messages = "；".join(
                str(item.get("message") or "未知目录错误")
                for item in plan_constraint_report.get("issues") or []
            )
            raise AIProviderRequestError(
                f"轻量课程目录未通过结构验收：{messages or '无法解析完整 JSON'}"
            )
        if outline_was_generated:
            # The outline stage never gets to smuggle knowledge or relation payloads
            # past the review/freeze boundary, even if a model ignores the prompt.
            plan = self._outline_only_plan(plan)

        await self._notify_phase(
            on_phase,
            "outline_ready",
            35,
            "轻量课程目录已通过检查",
            phase_progress=100,
            phase_detail={
                "artifact_type": "course_outline",
                **(plan_constraint_report.get("actual") or {}),
            },
        )
        plan, evidence_coverage_plan = attach_evidence_to_plan(
            plan,
            evidence=artifacts.get("evidence_catalog") or [],
            bindings=artifacts.get("material_bindings") or [],
            strategy=grounding_strategy,
        )
        artifacts["evidence_coverage_plan"] = evidence_coverage_plan
        if existing.get("nodes"):
            plan = self._merge_outline_node_edits(plan, existing.get("nodes") or [])
        outline_plan = self._outline_only_plan(plan)
        outline_blueprint = build_course_blueprint_from_plan(outline_plan, artifacts)
        outline_blueprint["course_outline_constraint_report"] = plan_constraint_report
        nodes = self._merge_generation_nodes(
            self._convert_plan_to_nodes(plan, course_id),
            existing.get("nodes") or [],
        )
        course_data = {
            **deepcopy(existing),
            "course_id": course_id,
            "course_name": plan.get("course_title", topic),
            "generation_schema_version": artifacts["pipeline_version"],
            "prompt_contract_version": PROMPT_CONTRACT_VERSION,
            "generation_pipeline_version": artifacts["pipeline_version"],
            "generation_request": {
                "subject": topic,
                "difficulty": difficulty,
                "composition_style": composition_profile["style"],
                "style": style,
                "requirements": requirements,
                "target_audience": audience,
                "learner_profile_summary": learner_profile_summary,
                "current_readiness": current_readiness,
                "adaptation_preference": adaptation_preference,
                "pedagogy_mode": pedagogy_mode,
                "secondary_mode": secondary_mode,
                "secondary_intensity": secondary_intensity,
                "generation_mode": generation_mode,
                "course_purpose": course_purpose,
                "asset_preferences": deepcopy(asset_preferences or {}),
                "web_question_enrichment": deepcopy(
                    web_question_enrichment or {"enabled": False}
                ),
                "material_bindings": artifacts.get("material_bindings", []),
                "grounding_strategy": grounding_strategy,
            },
            "difficulty": difficulty,
            "composition_style": composition_profile["style"],
            "style": style,
            "requirements": requirements,
            "target_audience": audience,
            "generation_mode": generation_mode,
            "course_purpose": course_purpose,
            "asset_preferences": deepcopy(asset_preferences or {}),
            "web_question_enrichment": deepcopy(
                web_question_enrichment or {"enabled": False}
            ),
            "subject_pedagogy_profile": profile.to_dict(),
            "difficulty_profile": difficulty_profile.to_dict(),
            "difficulty_gap_assessment": gap_assessment.to_dict(),
            "adaptation_decision": adaptation_decision.to_dict(),
            "course_composition_profile": composition_profile,
            "nodes": nodes,
            "course_plan": plan,
            "course_outline": outline_plan,
            "knowledge_relations": deepcopy(existing.get("knowledge_relations") or []),
            "material_cards": artifacts["material_cards"],
            "course_generation_brief": artifacts["course_generation_brief"],
            "material_assets": artifacts.get("material_assets", []),
            "material_bindings": artifacts.get("material_bindings", []),
            "parsed_documents": artifacts.get("parsed_documents", []),
            "evidence_index": _compact_evidence_index(artifacts.get("evidence_catalog", [])),
            "evidence_coverage_plan": evidence_coverage_plan,
            "course_blueprint": outline_blueprint,
            "course_outline_constraint_report": plan_constraint_report,
            "blueprint_validation_report": validate_blueprint(outline_blueprint),
            "generation_quality_report": None,
            "generation_status": "outline_ready",
            "generation_stage_artifacts": {
                **deepcopy(existing.get("generation_stage_artifacts") or {}),
                "outline": {
                    "status": "completed",
                    "schema_version": "course_outline_v1",
                    "actual": deepcopy(plan_constraint_report.get("actual") or {}),
                },
            },
        }
        await self._notify_checkpoint(on_checkpoint, course_data)
        if stop_after_outline:
            self.register_course_generation_metadata(course_id, course_data)
            return course_data

        # The template, difficulty and composition systems define the hard
        # section skeleton before the model gets its intentionally small
        # teaching-design freedom.
        plan = attach_generation_artifacts_to_plan(plan, artifacts)
        plan = attach_module_plans_to_plan(plan, profile)
        difficulty_curve = attach_difficulty_contracts_to_plan(
            plan,
            profile=difficulty_profile,
            adaptation=adaptation_decision,
        )
        composition_artifacts = attach_composition_to_plan(
            plan,
            composition_style,
            legacy_style=style,
        )
        artifacts.update(composition_artifacts)
        course_data.update({
            "course_plan": deepcopy(plan),
            "course_module_plan": deepcopy(
                plan.get("course_module_plan") or []
            ),
            "course_composition_profile": deepcopy(
                composition_artifacts["course_composition_profile"]
            ),
            "course_block_distribution": deepcopy(
                composition_artifacts["course_block_distribution"]
            ),
            "course_difficulty_curve": difficulty_curve,
        })

        current_scope_contract = build_course_knowledge_scope_contract(plan)
        persisted_scope_contract = (
            deepcopy(course_data.get("course_knowledge_scope_contract"))
            if isinstance(
                course_data.get("course_knowledge_scope_contract"),
                dict,
            )
            else {}
        )
        knowledge_scope_contract = (
            persisted_scope_contract
            if persisted_scope_contract.get("revision_id")
            == current_scope_contract.get("revision_id")
            else current_scope_contract
        )
        course_data["course_knowledge_scope_contract"] = knowledge_scope_contract
        course_data.setdefault("generation_stage_artifacts", {})["knowledge_scope"] = {
            "status": "completed",
            "schema_version": knowledge_scope_contract.get("schema_version"),
            "revision_id": knowledge_scope_contract.get("revision_id"),
        }
        await self._notify_checkpoint(on_checkpoint, course_data)
        plan = await self._prepare_course_teaching_plan(
            course_data=course_data,
            plan=plan,
            artifacts=artifacts,
            on_phase=on_phase,
            on_checkpoint=on_checkpoint,
        )
        plan = normalize_course_plan_contract(plan)
        full_plan_report = validate_course_plan_constraints(
            plan,
            artifacts["course_generation_brief"],
        )
        if not full_plan_report.get("passed"):
            messages = "；".join(
                str(item.get("message") or "未知教案错误")
                for item in full_plan_report.get("issues") or []
            )
            raise AIProviderRequestError(
                f"全课小节教案未通过课程合同验收：{messages or '教案结构不完整'}"
            )
        blueprint = build_course_blueprint_from_plan(plan, artifacts)
        blueprint["course_plan_constraint_report"] = full_plan_report
        blueprint["course_outline_constraint_report"] = plan_constraint_report
        blueprint_report = validate_blueprint(blueprint)
        course_data.update({
            "course_name": plan.get("course_title", topic),
            "course_plan": plan,
            "knowledge_relations": deepcopy(plan.get("knowledge_relations") or []),
            "nodes": self._merge_generation_nodes(
                self._convert_plan_to_nodes(plan, course_id),
                course_data.get("nodes") or [],
            ),
            "course_blueprint": blueprint,
            "course_plan_constraint_report": full_plan_report,
            "blueprint_validation_report": blueprint_report,
            "generation_status": "teaching_plan_compiled",
        })
        course_knowledge_map = compile_course_knowledge_map(course_data)
        course_knowledge_base = compile_course_knowledge_base(
            course_data,
            course_map=course_knowledge_map,
        )
        course_knowledge_map = bind_course_knowledge_base_to_map(
            course_knowledge_map,
            course_knowledge_base,
        )
        course_data["course_knowledge_map"] = course_knowledge_map
        course_data["course_knowledge_base"] = course_knowledge_base
        course_data["course_knowledge_quality_report"] = course_knowledge_base["quality_report"]
        course_data["course_blueprint"]["course_knowledge_base_revision_id"] = (
            course_knowledge_base["revision_id"]
        )
        coherence_contract = compile_course_coherence_contract(course_data)
        course_data["course_coherence_contract"] = coherence_contract
        course_data["course_coherence_quality_report"] = coherence_contract["quality_report"]
        course_data["course_blueprint"]["course_coherence_revision_id"] = (
            coherence_contract["revision_id"]
        )
        course_data.setdefault("generation_stage_artifacts", {})[
            "teaching"
        ] = {
            "status": "completed",
            "schema_version": "course_teaching_plan_v2",
            "revision_id": (
                course_data.get("course_teaching_plan") or {}
            ).get("revision_id"),
            "knowledge_revision_id": course_knowledge_base.get(
                "revision_id"
            ),
            "compiled_from": "single_whole_course_teaching_plan",
        }
        course_data["generation_status"] = "teaching_plan_ready"
        await self._notify_checkpoint(on_checkpoint, course_data)
        await self._notify_phase(
            on_phase,
            "blueprint_validation",
            50,
            "全课小节教案、知识库与稳定知识 ID 已完成编译",
            phase_progress=100,
            phase_detail={
                "artifact_type": "course_teaching_plan",
                "completed_items": len([
                    node for node in course_data.get("nodes") or []
                    if int(node.get("node_level") or 1) == 2
                ]),
                "total_items": len([
                    node for node in course_data.get("nodes") or []
                    if int(node.get("node_level") or 1) == 2
                ]),
                "course_knowledge_base_revision_id": course_knowledge_base.get("revision_id"),
                "model_call_count": (
                    (
                        course_data.get("generation_stage_artifacts")
                        or {}
                    ).get("course_teaching_plan")
                    or {}
                ).get("model_call_count", 0),
                "knowledge_compilation_model_call_count": 0,
            },
        )
        self.register_course_generation_metadata(course_id, course_data)
        return course_data

    def compile_teaching_plan(self, course_data: dict[str, Any]) -> dict[str, Any]:
        """Read-compatible deterministic compiler for pre-v9 checkpoints.

        New generation jobs receive their knowledge and block intent together
        from ``_prepare_course_teaching_plan`` and never enter this method.
        """
        working = deepcopy(course_data)
        stage = (
            (working.get("generation_stage_artifacts") or {})
            .get("teaching")
            or {}
        )
        if (
            (working.get("course_teaching_plan") or {}).get(
                "schema_version"
            ) == "course_teaching_plan_v2"
            and stage.get("status") == "completed"
        ):
            return working
        plan = deepcopy(working.get("course_plan") or {})
        if not plan.get("chapters"):
            raise ValueError("Teaching design requires a confirmed course outline")

        request = working.get("generation_request") or {}
        profile = coerce_persisted_profile(working)
        difficulty_profile = compile_difficulty_profile(
            request.get("difficulty") or working.get("difficulty") or "intermediate",
            primary_mode=profile.primary_mode,
            secondary_mode=profile.secondary_mode,
        )
        gap_assessment = assess_readiness(
            difficulty_profile,
            request.get("current_readiness"),
        )
        adaptation_decision = decide_adaptation(
            gap_assessment,
            str(request.get("adaptation_preference") or "preserve_target_extend"),
        )
        artifacts = {
            **deepcopy(self._course_generation_artifacts.get(str(working.get("course_id") or "")) or {}),
            "course_generation_brief": deepcopy(working.get("course_generation_brief") or {}),
            "course_composition_profile": deepcopy(
                working.get("course_composition_profile") or {}
            ),
            "difficulty_profile": difficulty_profile.to_dict(),
            "difficulty_gap_assessment": gap_assessment.to_dict(),
            "adaptation_decision": adaptation_decision.to_dict(),
            "subject_pedagogy_profile": profile.to_dict(),
            "evidence_coverage_plan": deepcopy(working.get("evidence_coverage_plan") or {}),
        }

        plan = attach_generation_artifacts_to_plan(plan, artifacts)
        plan = attach_module_plans_to_plan(plan, profile)
        difficulty_curve = attach_difficulty_contracts_to_plan(
            plan,
            profile=difficulty_profile,
            adaptation=adaptation_decision,
        )
        composition_artifacts = attach_composition_to_plan(
            plan,
            request.get("composition_style")
            or working.get("composition_style")
            or (working.get("course_composition_profile") or {}).get("style"),
            legacy_style=request.get("style") or working.get("style"),
        )
        artifacts.update(composition_artifacts)
        blueprint = build_course_blueprint_from_plan(plan, artifacts)
        for key in (
            "course_outline_constraint_report",
            "course_plan_constraint_report",
            "course_knowledge_base_revision_id",
            "course_coherence_revision_id",
        ):
            if key in (working.get("course_blueprint") or {}):
                blueprint[key] = deepcopy(working["course_blueprint"][key])

        working.update(
            {
                "course_plan": plan,
                "course_module_plan": deepcopy(plan.get("course_module_plan") or []),
                "course_composition_profile": deepcopy(
                    composition_artifacts["course_composition_profile"]
                ),
                "course_block_distribution": deepcopy(
                    composition_artifacts["course_block_distribution"]
                ),
                "course_difficulty_curve": difficulty_curve,
                "difficulty_profile": difficulty_profile.to_dict(),
                "difficulty_gap_assessment": gap_assessment.to_dict(),
                "adaptation_decision": adaptation_decision.to_dict(),
                "nodes": self._merge_generation_nodes(
                    self._convert_plan_to_nodes(
                        plan,
                        str(working.get("course_id") or ""),
                    ),
                    working.get("nodes") or [],
                ),
                "course_blueprint": blueprint,
                "blueprint_validation_report": validate_blueprint(blueprint),
                "generation_status": "teaching_ready",
            }
        )
        coherence_contract = compile_course_coherence_contract(working)
        working["course_coherence_contract"] = coherence_contract
        working["course_coherence_quality_report"] = coherence_contract["quality_report"]
        working["course_blueprint"]["course_coherence_revision_id"] = (
            coherence_contract["revision_id"]
        )
        working.setdefault("generation_stage_artifacts", {})["teaching"] = {
            "status": "completed",
            "schema_version": "course_teaching_plan_legacy_adapter_v1",
            "knowledge_revision_id": (
                working.get("course_knowledge_base") or {}
            ).get("revision_id"),
            "compiled_from": "legacy_checkpoint",
        }
        self.register_course_generation_metadata(
            str(working.get("course_id") or ""),
            working,
        )
        return working

    async def _prepare_course_teaching_plan(
        self,
        *,
        course_data: dict[str, Any],
        plan: dict[str, Any],
        artifacts: dict[str, Any] | None,
        on_phase: Callable[..., Awaitable[None] | None] | None,
        on_checkpoint: Callable[[dict[str, Any]], Awaitable[None] | None] | None,
    ) -> dict[str, Any]:
        """Build one official plan through a compact or 1-N-1 path."""
        sections: list[dict[str, Any]] = []
        planning_sections: list[dict[str, Any]] = []
        for chapter_index, chapter in enumerate(plan.get("chapters") or [], start=1):
            if not isinstance(chapter, dict):
                continue
            chapter_id = str(
                chapter.get("chapter_id")
                or chapter.get("chapter_number")
                or f"chapter-{chapter_index}"
            )
            for section in chapter.get("sections") or []:
                if not isinstance(section, dict):
                    continue
                sections.append(section)
                item = deepcopy(section)
                item["chapter_id"] = chapter_id
                item["evidence_hints"] = (
                    build_section_knowledge_skeleton_evidence_hints(
                        artifacts or course_data,
                        section,
                    )
                )
                planning_sections.append(item)

        scope_contract = build_course_knowledge_scope_contract(plan)
        outline_revision_id = str(scope_contract.get("revision_id") or "")
        course_data["course_knowledge_scope_contract"] = scope_contract
        teaching_stage = course_data.setdefault(
            "generation_stage_artifacts", {}
        ).setdefault("course_teaching_plan", {})
        if (
            teaching_stage.get("source_outline_revision_id")
            and teaching_stage.get("source_outline_revision_id") != outline_revision_id
        ):
            teaching_stage.clear()

        existing_payload = (
            course_data.get("course_teaching_plan")
            if isinstance(course_data.get("course_teaching_plan"), dict)
            else {}
        )
        existing_plan = compile_course_teaching_plan_modules(
            existing_payload,
            sections=sections,
        )
        existing_report = validate_course_teaching_plan(
            existing_plan,
            sections=sections,
            expected_outline_revision_id=outline_revision_id,
        )
        if existing_report.get("passed"):
            planned_course = apply_course_teaching_plan(plan, existing_plan)
            teaching_stage.update({
                "status": "completed",
                "schema_version": existing_plan.get("schema_version"),
                "revision_id": existing_plan.get("revision_id"),
                "source_outline_revision_id": outline_revision_id,
                "validation_report": deepcopy(existing_report),
                "strategy": str(
                    teaching_stage.get("strategy") or "restored_official_plan"
                ),
                "model_call_count": 0,
                "resumed": True,
            })
            course_data.update({
                "course_teaching_plan": existing_plan,
                "course_plan": deepcopy(planned_course),
                "knowledge_relations": deepcopy(
                    planned_course.get("knowledge_relations") or []
                ),
                "generation_status": "course_teaching_plan_compiled",
            })
            return planned_course

        course_title = str(
            plan.get("course_title") or course_data.get("course_name") or ""
        )
        positioning = str(plan.get("positioning") or "")
        planning_context = build_compact_planning_context(
            planning_sections,
            composition_style=str(
                (course_data.get("course_composition_profile") or {}).get("style")
                or ""
            ),
        )
        planning_mode = self._teaching_plan_budget.choose_mode(
            sections=planning_sections,
            compact_input_tokens=estimate_json_tokens({
                "course_title": course_title,
                "positioning": positioning,
                "learning_objectives": plan.get("learning_objectives") or [],
                "planning_context": planning_context,
            }),
        )
        if planning_mode == "compact":
            planned_course = await self._prepare_course_teaching_plan_compact_legacy(
                course_data=course_data,
                plan=plan,
                artifacts=artifacts,
                on_phase=on_phase,
                on_checkpoint=on_checkpoint,
            )
            course_data["generation_stage_artifacts"]["course_teaching_plan"].update({
                "planning_mode": "compact",
                "strategy": "compact_single_call",
            })
            return planned_course

        strategy = "global_skeleton_bounded_batches"
        started_at = time.monotonic()
        counter = {
            "calls": int(teaching_stage.get("model_call_count") or 0),
            "prompt_chars": int(teaching_stage.get("prompt_chars") or 0),
        }
        counter_lock = asyncio.Lock()

        async def request_model(
            *,
            user_prompt: str,
            system_prompt: str,
            enable_thinking: bool,
            phase: str,
            progress: int,
            heartbeat_message: str,
            phase_detail: dict[str, Any],
        ) -> str:
            try:
                async with self._teaching_plan_semaphore:
                    return await self._call_llm_with_heartbeat(
                        user_prompt,
                        system_prompt,
                        enable_thinking=enable_thinking,
                        on_phase=on_phase,
                        phase=phase,
                        base_progress=progress,
                        stage_timeout_seconds=(
                            self._teaching_plan_budget.batch_timeout_seconds
                        ),
                        heartbeat_message=heartbeat_message,
                        phase_detail=phase_detail,
                    )
            finally:
                async with counter_lock:
                    counter["calls"] += 1
                    counter["prompt_chars"] += len(system_prompt)

        raw_skeleton = teaching_stage.get("skeleton")
        skeleton = normalize_teaching_plan_skeleton_v3(
            raw_skeleton if isinstance(raw_skeleton, dict) else {},
            outline_revision_id=outline_revision_id,
        )
        skeleton_report = validate_teaching_plan_skeleton_v3(
            skeleton,
            sections=planning_sections,
        )
        skeleton_is_current = bool(
            isinstance(raw_skeleton, dict)
            and raw_skeleton.get("source_outline_revision_id") == outline_revision_id
            and skeleton_report.get("passed")
        )
        if not skeleton_is_current:
            skeleton_prompt = self._prompt_composer.build_teaching_plan_skeleton_v3_prompt(
                course_title=course_title,
                positioning=positioning,
                learning_objectives=list(plan.get("learning_objectives") or []),
                planning_context=planning_context,
            )
            await self._notify_phase(
                on_phase,
                "course_teaching_plan_skeleton",
                35,
                f"正在冻结全课知识职责（0/{len(sections)} 节）",
                phase_progress=0,
                phase_detail={
                    "artifact_type": "course_teaching_plan_skeleton",
                    "completed_sections": 0,
                    "total_sections": len(sections),
                    "strategy": strategy,
                },
            )
            response = await request_model(
                user_prompt="规划全课知识职责骨架 V3，只输出 JSON。",
                system_prompt=skeleton_prompt,
                enable_thinking=True,
                phase="course_teaching_plan_skeleton",
                progress=35,
                heartbeat_message="仍在等待 AI 冻结全课知识职责",
                phase_detail={
                    "artifact_type": "course_teaching_plan_skeleton",
                    "total_sections": len(sections),
                },
            )
            parsed = self._extract_json(response) if response else None
            skeleton = normalize_teaching_plan_skeleton_v3(
                parsed if isinstance(parsed, dict) else {},
                outline_revision_id=outline_revision_id,
            )
            skeleton_report = validate_teaching_plan_skeleton_v3(
                skeleton,
                sections=planning_sections,
            )
            if not skeleton_report.get("passed"):
                correction_prompt = self._prompt_composer.build_teaching_plan_skeleton_v3_correction_prompt(
                    original_prompt=skeleton_prompt,
                    issues=skeleton_report.get("blocking_issues") or [],
                )
                corrected = await request_model(
                    user_prompt="只修复全课知识职责骨架 V3，输出完整 JSON。",
                    system_prompt=correction_prompt,
                    enable_thinking=False,
                    phase="course_teaching_plan_skeleton_validation",
                    progress=38,
                    heartbeat_message="仍在等待 AI 修复知识职责骨架",
                    phase_detail={
                        "artifact_type": "course_teaching_plan_skeleton",
                        "total_sections": len(sections),
                    },
                )
                parsed = self._extract_json(corrected) if corrected else None
                skeleton = normalize_teaching_plan_skeleton_v3(
                    parsed if isinstance(parsed, dict) else {},
                    outline_revision_id=outline_revision_id,
                )
                skeleton_report = validate_teaching_plan_skeleton_v3(
                    skeleton,
                    sections=planning_sections,
                )
            if not skeleton_report.get("passed"):
                teaching_stage.update({
                    "status": "failed",
                    "schema_version": "course_teaching_plan_v3",
                    "source_outline_revision_id": outline_revision_id,
                    "planning_mode": planning_mode,
                    "strategy": strategy,
                    "skeleton_validation_report": deepcopy(skeleton_report),
                    "model_call_count": counter["calls"],
                    "prompt_chars": counter["prompt_chars"],
                })
                course_data["generation_status"] = "course_teaching_plan_failed"
                await self._notify_checkpoint(on_checkpoint, course_data)
                messages = "；".join(
                    str(item.get("message") or "未知骨架错误")
                    for item in skeleton_report.get("blocking_issues") or []
                )
                raise AIProviderRequestError(
                    f"全课知识职责骨架未通过结构验收：{messages}"
                )

        course_data["course_teaching_plan_skeleton"] = skeleton
        batch_specs = build_teaching_plan_batches(
            list(planning_context.get("sections") or []),
            skeleton,
            self._teaching_plan_budget,
        )
        stored_batches = teaching_stage.setdefault("batches", {})
        if not isinstance(stored_batches, dict):
            stored_batches = {}
            teaching_stage["batches"] = stored_batches
        results: dict[str, dict[str, Any]] = {}
        pending_specs: list[dict[str, Any]] = []
        for spec in batch_specs:
            batch_id = str(spec.get("batch_id") or "")
            stored = stored_batches.get(batch_id)
            stored_payload = stored.get("payload") if isinstance(stored, dict) else {}
            candidate = normalize_teaching_plan_batch_v3(
                stored_payload if isinstance(stored_payload, dict) else {},
                batch_id=batch_id,
                skeleton_revision_id=str(skeleton.get("revision_id") or ""),
            )
            candidate_report = validate_teaching_plan_batch_v3(
                candidate,
                batch_spec=spec,
                skeleton=skeleton,
                sections=planning_sections,
            )
            if (
                isinstance(stored, dict)
                and stored.get("status") == "completed"
                and stored.get("skeleton_revision_id") == skeleton.get("revision_id")
                and list(stored.get("section_ids") or []) == list(spec.get("section_ids") or [])
                and candidate_report.get("passed")
            ):
                results[batch_id] = candidate
            else:
                pending_specs.append(spec)

        teaching_stage.update({
            "status": "in_progress",
            "schema_version": "course_teaching_plan_v3",
            "source_outline_revision_id": outline_revision_id,
            "planning_mode": planning_mode,
            "strategy": strategy,
            "skeleton": deepcopy(skeleton),
            "skeleton_revision_id": skeleton.get("revision_id"),
            "skeleton_validation_report": deepcopy(skeleton_report),
            "batch_count": len(batch_specs),
            "completed_batch_count": len(results),
            "completed_section_count": sum(
                len(spec.get("section_ids") or [])
                for spec in batch_specs
                if spec.get("batch_id") in results
            ),
            "section_count": len(sections),
            "max_concurrency": self._teaching_plan_budget.concurrency,
            "model_call_count": counter["calls"],
            "prompt_chars": counter["prompt_chars"],
        })
        await self._notify_checkpoint(on_checkpoint, course_data)
        batch_progress_detail: dict[str, Any] = {
            "artifact_type": "course_teaching_plan_batch",
            "completed_batches": len(results),
            "total_batches": len(batch_specs),
            "completed_sections": teaching_stage.get("completed_section_count", 0),
            "total_sections": len(sections),
        }
        state_lock = asyncio.Lock()

        async def generate_batch(spec: dict[str, Any]) -> dict[str, Any]:
            batch_id = str(spec.get("batch_id") or "")
            section_ids = list(spec.get("section_ids") or [])
            compact_by_id = {
                str(item.get("node_id") or ""): item
                for item in planning_context.get("sections") or []
            }
            identity_by_id = {
                str(item.get("node_id") or ""): item
                for item in skeleton.get("sections") or []
                if isinstance(item, dict)
            }
            batch_prompt = self._prompt_composer.build_teaching_plan_batch_v3_prompt(
                course_title=course_title,
                positioning=positioning,
                batch_spec=spec,
                batch_sections=[compact_by_id[item] for item in section_ids],
                knowledge_registry=list(skeleton.get("knowledge_registry") or []),
                section_identities=[identity_by_id[item] for item in section_ids],
                module_catalog=list(planning_context.get("module_catalog") or []),
                skeleton_revision_id=str(skeleton.get("revision_id") or ""),
            )
            previous = stored_batches.get(batch_id)
            attempt_count = int(
                (previous or {}).get("attempt_count", 0)
                if isinstance(previous, dict) else 0
            )
            try:
                async with state_lock:
                    completed_before = len(results)
                await self._notify_phase(
                    on_phase,
                    "course_teaching_plan_batch",
                    39 + int(7 * completed_before / max(1, len(batch_specs))),
                    f"正在生成第 {int(batch_id[-2:])} 批详细教案（已完成 {completed_before}/{len(batch_specs)} 批）",
                    phase_progress=int(100 * completed_before / max(1, len(batch_specs))),
                    phase_detail={
                        "artifact_type": "course_teaching_plan_batch",
                        "batch_id": batch_id,
                        "completed_batches": completed_before,
                        "total_batches": len(batch_specs),
                        "completed_sections": teaching_stage.get("completed_section_count", 0),
                        "total_sections": len(sections),
                    },
                )
                attempt_count += 1
                response = await request_model(
                    user_prompt=f"生成详细小节教案批次 {batch_id}，只输出 JSON。",
                    system_prompt=batch_prompt,
                    enable_thinking=True,
                    phase="course_teaching_plan_batch",
                    progress=40,
                    heartbeat_message=f"仍在等待 AI 完成教案批次 {batch_id}",
                    phase_detail=batch_progress_detail,
                )
                parsed = self._extract_json(response) if response else None
                batch = normalize_teaching_plan_batch_v3(
                    parsed if isinstance(parsed, dict) else {},
                    batch_id=batch_id,
                    skeleton_revision_id=str(skeleton.get("revision_id") or ""),
                )
                batch_report = validate_teaching_plan_batch_v3(
                    batch,
                    batch_spec=spec,
                    skeleton=skeleton,
                    sections=planning_sections,
                )
                if not batch_report.get("passed"):
                    correction_prompt = self._prompt_composer.build_teaching_plan_batch_v3_correction_prompt(
                        original_prompt=batch_prompt,
                        issues=batch_report.get("blocking_issues") or [],
                    )
                    attempt_count += 1
                    corrected = await request_model(
                        user_prompt=f"只修复详细教案批次 {batch_id}，输出完整 JSON。",
                        system_prompt=correction_prompt,
                        enable_thinking=False,
                        phase="course_teaching_plan_batch_validation",
                        progress=44,
                        heartbeat_message=f"仍在等待 AI 修复教案批次 {batch_id}",
                        phase_detail=batch_progress_detail,
                    )
                    parsed = self._extract_json(corrected) if corrected else None
                    batch = normalize_teaching_plan_batch_v3(
                        parsed if isinstance(parsed, dict) else {},
                        batch_id=batch_id,
                        skeleton_revision_id=str(skeleton.get("revision_id") or ""),
                    )
                    batch_report = validate_teaching_plan_batch_v3(
                        batch,
                        batch_spec=spec,
                        skeleton=skeleton,
                        sections=planning_sections,
                    )
                if not batch_report.get("passed"):
                    messages = "；".join(
                        str(item.get("message") or "未知批次错误")
                        for item in batch_report.get("blocking_issues") or []
                    )
                    raise AIProviderRequestError(
                        f"教案批次 {batch_id} 未通过结构验收：{messages}"
                    )
                async with state_lock:
                    results[batch_id] = batch
                    stored_batches[batch_id] = {
                        "status": "completed",
                        "section_ids": section_ids,
                        "skeleton_revision_id": skeleton.get("revision_id"),
                        "revision_id": batch.get("revision_id"),
                        "attempt_count": attempt_count,
                        "validation_report": deepcopy(batch_report),
                        "payload": deepcopy(batch),
                    }
                    teaching_stage["completed_batch_count"] = len(results)
                    teaching_stage["completed_section_count"] = sum(
                        len(item.get("section_ids") or [])
                        for key, item in stored_batches.items()
                        if key in results and isinstance(item, dict)
                    )
                    teaching_stage["model_call_count"] = counter["calls"]
                    teaching_stage["prompt_chars"] = counter["prompt_chars"]
                    batch_progress_detail.update({
                        "completed_batches": teaching_stage["completed_batch_count"],
                        "completed_sections": teaching_stage["completed_section_count"],
                    })
                    course_data["generation_status"] = "course_teaching_plan_in_progress"
                    await self._notify_checkpoint(on_checkpoint, course_data)
                return batch
            except Exception as exc:
                async with state_lock:
                    stored_batches[batch_id] = {
                        "status": "failed",
                        "section_ids": section_ids,
                        "skeleton_revision_id": skeleton.get("revision_id"),
                        "attempt_count": attempt_count,
                        "error": str(exc),
                    }
                    teaching_stage["failed_batch_id"] = batch_id
                    teaching_stage["model_call_count"] = counter["calls"]
                    teaching_stage["prompt_chars"] = counter["prompt_chars"]
                    await self._notify_checkpoint(on_checkpoint, course_data)
                raise

        generated = await asyncio.gather(
            *(generate_batch(spec) for spec in pending_specs),
            return_exceptions=True,
        )
        failures = [item for item in generated if isinstance(item, BaseException)]
        if failures:
            teaching_stage.update({
                "status": "failed",
                "duration_ms": int((time.monotonic() - started_at) * 1000),
                "completed_batch_count": len(results),
                "completed_section_count": sum(
                    len(spec.get("section_ids") or [])
                    for spec in batch_specs
                    if spec.get("batch_id") in results
                ),
            })
            course_data["generation_status"] = "course_teaching_plan_failed"
            await self._notify_checkpoint(on_checkpoint, course_data)
            first = failures[0]
            if isinstance(first, AIProviderRequestError):
                raise first
            raise AIProviderRequestError(str(first)) from first

        await self._notify_phase(
            on_phase,
            "course_teaching_plan_assembly",
            47,
            "正在汇编唯一的全课教案并本地编译知识库",
            phase_progress=0,
            phase_detail={
                "artifact_type": "course_teaching_plan_assembly",
                "completed_batches": len(batch_specs),
                "total_batches": len(batch_specs),
                "completed_sections": len(sections),
                "total_sections": len(sections),
            },
        )
        assembled = assemble_course_teaching_plan_v3(
            skeleton=skeleton,
            batches=[
                results[str(spec.get("batch_id") or "")]
                for spec in batch_specs
            ],
            outline_revision_id=outline_revision_id,
        )
        course_teaching_plan = compile_course_teaching_plan_modules(
            assembled,
            sections=sections,
        )
        report = validate_course_teaching_plan(
            course_teaching_plan,
            sections=sections,
            expected_outline_revision_id=outline_revision_id,
        )
        duration_ms = int((time.monotonic() - started_at) * 1000)
        if not report.get("passed"):
            teaching_stage.update({
                "status": "failed",
                "validation_report": deepcopy(report),
                "duration_ms": duration_ms,
                "model_call_count": counter["calls"],
                "prompt_chars": counter["prompt_chars"],
            })
            course_data["generation_status"] = "course_teaching_plan_failed"
            await self._notify_checkpoint(on_checkpoint, course_data)
            messages = "；".join(
                str(item.get("message") or "未知教案错误")
                for item in report.get("blocking_issues") or []
            )
            raise AIProviderRequestError(
                f"全课小节教案未通过结构验收：{messages}"
            )

        planned_course = apply_course_teaching_plan(plan, course_teaching_plan)
        teaching_stage.update({
            "status": "completed",
            "schema_version": course_teaching_plan.get("schema_version"),
            "revision_id": course_teaching_plan.get("revision_id"),
            "source_outline_revision_id": outline_revision_id,
            "validation_report": deepcopy(report),
            "duration_ms": duration_ms,
            "model_call_count": counter["calls"],
            "prompt_chars": counter["prompt_chars"],
            "planning_mode": planning_mode,
            "strategy": strategy,
            "section_count": len(sections),
            "completed_section_count": len(sections),
            "completed_batch_count": len(batch_specs),
            "batch_count": len(batch_specs),
            "knowledge_point_count": (report.get("actual") or {}).get(
                "knowledge_point_count", 0
            ),
            "teaching_module_count": (report.get("actual") or {}).get(
                "teaching_module_count", 0
            ),
            "knowledge_compilation_model_call_count": 0,
            "graph_compilation_model_call_count": 0,
        })
        teaching_stage.pop("failed_batch_id", None)
        course_data.update({
            "course_teaching_plan": course_teaching_plan,
            "course_plan": deepcopy(planned_course),
            "knowledge_relations": deepcopy(
                planned_course.get("knowledge_relations") or []
            ),
            "nodes": self._merge_generation_nodes(
                self._convert_plan_to_nodes(
                    planned_course,
                    str(course_data.get("course_id") or ""),
                ),
                course_data.get("nodes") or [],
            ),
            "generation_status": "course_teaching_plan_compiled",
        })
        if artifacts:
            course_data["course_blueprint"] = build_course_blueprint_from_plan(
                planned_course,
                artifacts,
            )
        await self._notify_checkpoint(on_checkpoint, course_data)
        await self._notify_phase(
            on_phase,
            "course_teaching_plan",
            48,
            "全课小节教案已完成，知识库与关系图已经在本地编译",
            phase_progress=100,
            phase_detail={
                "artifact_type": "course_teaching_plan",
                "completed_items": len(sections),
                "total_items": len(sections),
                "completed_batches": len(batch_specs),
                "total_batches": len(batch_specs),
                "completed_sections": len(sections),
                "total_sections": len(sections),
                "knowledge_point_count": (
                    report.get("actual") or {}
                ).get("knowledge_point_count", 0),
                "model_call_count": counter["calls"],
                "knowledge_compilation_model_call_count": 0,
                "graph_compilation_model_call_count": 0,
            },
        )
        return planned_course

    async def _prepare_course_teaching_plan_compact_legacy(
        self,
        *,
        course_data: dict[str, Any],
        plan: dict[str, Any],
        artifacts: dict[str, Any] | None,
        on_phase: Callable[..., Awaitable[None] | None] | None,
        on_checkpoint: Callable[[dict[str, Any]], Awaitable[None] | None] | None,
    ) -> dict[str, Any]:
        """Generate all section teaching plans in one whole-course model call."""
        sections = [
            section
            for chapter in plan.get("chapters") or []
            if isinstance(chapter, dict)
            for section in chapter.get("sections") or []
            if isinstance(section, dict)
        ]
        scope_contract = build_course_knowledge_scope_contract(plan)
        outline_revision_id = str(scope_contract.get("revision_id") or "")
        course_data["course_knowledge_scope_contract"] = scope_contract
        stage_artifacts = course_data.setdefault(
            "generation_stage_artifacts", {}
        )
        teaching_stage = stage_artifacts.setdefault(
            "course_teaching_plan", {}
        )

        existing_payload = (
            course_data.get("course_teaching_plan")
            if isinstance(course_data.get("course_teaching_plan"), dict)
            else {}
        )
        existing_plan = compile_course_teaching_plan_modules(
            existing_payload,
            sections=sections,
        )
        report = validate_course_teaching_plan(
            existing_plan,
            sections=sections,
            expected_outline_revision_id=outline_revision_id,
        )
        if report.get("passed"):
            planned_course = apply_course_teaching_plan(
                plan,
                existing_plan,
            )
            teaching_stage.update({
                "status": "completed",
                "schema_version": existing_plan.get("schema_version"),
                "revision_id": existing_plan.get("revision_id"),
                "source_outline_revision_id": outline_revision_id,
                "validation_report": deepcopy(report),
                "strategy": "single_whole_course_call",
                "model_call_count": 0,
                "resumed": True,
            })
            course_data.update({
                "course_teaching_plan": existing_plan,
                "course_plan": deepcopy(planned_course),
                "knowledge_relations": deepcopy(
                    planned_course.get("knowledge_relations") or []
                ),
                "generation_status": "course_teaching_plan_compiled",
            })
            return planned_course

        compact_sections: list[dict[str, Any]] = []
        for section in sections:
            compact_section = {
                key: deepcopy(section.get(key))
                for key in (
                    "node_id",
                    "section_number",
                    "title",
                    "learning_objective",
                    "scope_boundary",
                    "prerequisite_node_ids",
                )
            }
            compact_section["difficulty_contract"] = deepcopy(
                section.get("difficulty_contract") or {}
            )
            compact_section["composition_style"] = str(
                (
                    course_data.get("course_composition_profile")
                    or {}
                ).get("style")
                or ""
            )
            compact_section["allowed_teaching_modules"] = [
                {
                    key: deepcopy(module.get(key))
                    for key in (
                        "module_id",
                        "label",
                        "block_role",
                        "required",
                        "output_contract",
                    )
                }
                for module in section.get("module_plan") or []
                if isinstance(module, dict)
            ]
            compact_section["evidence_hints"] = (
                build_section_knowledge_skeleton_evidence_hints(
                    artifacts or course_data,
                    section,
                )
            )
            compact_sections.append(compact_section)

        prompt = self._prompt_composer.build_course_teaching_plan_prompt(
            course_title=str(
                plan.get("course_title")
                or course_data.get("course_name")
                or ""
            ),
            positioning=str(plan.get("positioning") or ""),
            learning_objectives=list(
                plan.get("learning_objectives") or []
            ),
            sections=compact_sections,
        )
        await self._notify_phase(
            on_phase,
            "course_teaching_plan",
            35,
            "正在一次性规划整门课所有小节教案",
            phase_progress=0,
            phase_detail={
                "artifact_type": "course_teaching_plan",
                "item_total": len(sections),
                "strategy": "single_whole_course_call",
                "model_call_budget": 1,
            },
        )
        started_at = time.monotonic()
        async with self._planning_semaphore:
            response = await self._call_llm_with_heartbeat(
                "生成整门课所有小节教案，只输出 JSON。",
                prompt,
                enable_thinking=True,
                on_phase=on_phase,
                phase="course_teaching_plan",
                base_progress=35,
                heartbeat_message="仍在等待 AI 完成全课小节教案",
                phase_detail={
                    "artifact_type": "course_teaching_plan",
                    "item_total": len(sections),
                    "strategy": "single_whole_course_call",
                },
            )
        parsed = self._extract_json(response) if response else None
        payload = parsed if isinstance(parsed, dict) else {}
        payload["source_outline_revision_id"] = outline_revision_id
        course_teaching_plan = compile_course_teaching_plan_modules(
            payload,
            sections=sections,
        )
        report = validate_course_teaching_plan(
            course_teaching_plan,
            sections=sections,
            expected_outline_revision_id=outline_revision_id,
        )
        model_call_count = 1
        if not report.get("passed"):
            correction_prompt = (
                self._prompt_composer
                .build_course_teaching_plan_correction_prompt(
                    original_prompt=prompt,
                    issues=report.get("blocking_issues") or [],
                )
            )
            async with self._planning_semaphore:
                corrected = await self._call_llm_with_heartbeat(
                    "只修复全课小节教案的结构和引用错误，输出完整 JSON。",
                    correction_prompt,
                    enable_thinking=False,
                    on_phase=on_phase,
                    phase="course_teaching_plan_validation",
                    base_progress=43,
                    heartbeat_message="仍在等待 AI 修复全课小节教案结构",
                    phase_detail={
                        "artifact_type": "course_teaching_plan",
                        "item_total": len(sections),
                    },
                )
            parsed = self._extract_json(corrected) if corrected else None
            payload = parsed if isinstance(parsed, dict) else {}
            payload["source_outline_revision_id"] = outline_revision_id
            course_teaching_plan = compile_course_teaching_plan_modules(
                payload,
                sections=sections,
            )
            report = validate_course_teaching_plan(
                course_teaching_plan,
                sections=sections,
                expected_outline_revision_id=outline_revision_id,
            )
            model_call_count += 1

        duration_ms = int((time.monotonic() - started_at) * 1000)
        if not report.get("passed"):
            teaching_stage.update({
                "status": "failed",
                "schema_version": "course_teaching_plan_v2",
                "source_outline_revision_id": outline_revision_id,
                "validation_report": deepcopy(report),
                "duration_ms": duration_ms,
                "model_call_count": model_call_count,
                "strategy": "single_whole_course_call",
            })
            course_data["generation_status"] = (
                "course_teaching_plan_failed"
            )
            await self._notify_checkpoint(on_checkpoint, course_data)
            messages = "；".join(
                str(item.get("message") or "未知教案错误")
                for item in report.get("blocking_issues") or []
            )
            raise AIProviderRequestError(
                "全课小节教案未通过结构验收："
                f"{messages or '无法解析完整教案 JSON'}"
            )

        planned_course = apply_course_teaching_plan(
            plan,
            course_teaching_plan,
        )
        teaching_stage.update({
            "status": "completed",
            "schema_version": course_teaching_plan.get(
                "schema_version"
            ),
            "revision_id": course_teaching_plan.get("revision_id"),
            "source_outline_revision_id": outline_revision_id,
            "validation_report": deepcopy(report),
            "duration_ms": duration_ms,
            "prompt_chars": len(prompt),
            "model_call_count": model_call_count,
            "strategy": "single_whole_course_call",
            "section_count": len(sections),
            "knowledge_point_count": (
                report.get("actual") or {}
            ).get("knowledge_point_count", 0),
            "teaching_module_count": (
                report.get("actual") or {}
            ).get("teaching_module_count", 0),
            "knowledge_compilation_model_call_count": 0,
            "graph_compilation_model_call_count": 0,
        })
        course_data.update({
            "course_teaching_plan": course_teaching_plan,
            "course_plan": deepcopy(planned_course),
            "knowledge_relations": deepcopy(
                planned_course.get("knowledge_relations") or []
            ),
            "nodes": self._merge_generation_nodes(
                self._convert_plan_to_nodes(
                    planned_course,
                    str(course_data.get("course_id") or ""),
                ),
                course_data.get("nodes") or [],
            ),
            "generation_status": "course_teaching_plan_compiled",
        })
        if artifacts:
            course_data["course_blueprint"] = (
                build_course_blueprint_from_plan(
                    planned_course,
                    artifacts,
                )
            )
        await self._notify_checkpoint(on_checkpoint, course_data)
        await self._notify_phase(
            on_phase,
            "course_teaching_plan",
            48,
            "全课小节教案已完成，知识库与图谱已在本地编译",
            phase_progress=100,
            phase_detail={
                "artifact_type": "course_teaching_plan",
                "completed_items": len(sections),
                "total_items": len(sections),
                "knowledge_point_count": (
                    report.get("actual") or {}
                ).get("knowledge_point_count", 0),
                "model_call_count": model_call_count,
                "knowledge_compilation_model_call_count": 0,
                "graph_compilation_model_call_count": 0,
            },
        )
        return planned_course

    async def _prepare_course_knowledge_skeleton(
        self,
        *,
        course_data: dict[str, Any],
        plan: dict[str, Any],
        artifacts: dict[str, Any] | None,
        on_phase: Callable[..., Awaitable[None] | None] | None,
        on_checkpoint: Callable[[dict[str, Any]], Awaitable[None] | None] | None,
    ) -> dict[str, Any]:
        """Freeze whole-course knowledge identity before parallel detail calls."""
        sections = [
            section
            for chapter in plan.get("chapters") or []
            if isinstance(chapter, dict)
            for section in chapter.get("sections") or []
            if isinstance(section, dict)
        ]
        current_scope_contract = build_course_knowledge_scope_contract(
            plan
        )
        persisted_scope_contract = (
            course_data.get("course_knowledge_scope_contract")
            if isinstance(
                course_data.get("course_knowledge_scope_contract"),
                dict,
            )
            else {}
        )
        course_scope_contract = (
            persisted_scope_contract
            if persisted_scope_contract.get("revision_id")
            == current_scope_contract.get("revision_id")
            else current_scope_contract
        )
        course_data["course_knowledge_scope_contract"] = (
            course_scope_contract
        )
        scope_revision_id = str(
            course_scope_contract.get("revision_id") or ""
        )
        stage_artifacts = course_data.setdefault(
            "generation_stage_artifacts", {}
        )
        skeleton_stage = stage_artifacts.setdefault(
            "course_knowledge_skeleton", {}
        )
        persisted_skeleton_payload = (
            course_data.get("course_knowledge_skeleton")
            if isinstance(
                course_data.get("course_knowledge_skeleton"),
                dict,
            )
            else {}
        )
        persisted_skeleton_scope = str(
            persisted_skeleton_payload.get(
                "source_scope_revision_id"
            )
            or ""
        )
        scope_was_invalidated = bool(
            persisted_skeleton_payload.get("sections")
            and persisted_skeleton_scope != scope_revision_id
        )
        if scope_was_invalidated:
            for section in sections:
                section["knowledge_structure"] = []
                section["reused_knowledge_names"] = []
                section["knowledge_relations"] = []
                section.pop("knowledge_package_status", None)
                section.pop("knowledge_quality_report", None)
            course_data.pop("course_knowledge_base", None)
            course_data.pop("course_knowledge_map", None)
            course_data.pop("course_knowledge_quality_report", None)
            course_data.update({
                "course_plan": deepcopy(plan),
                "knowledge_relations": [],
                "knowledge_relation_decisions": [],
                "nodes": self._merge_generation_nodes(
                    self._convert_plan_to_nodes(
                        plan,
                        str(course_data.get("course_id") or ""),
                    ),
                    course_data.get("nodes") or [],
                ),
            })
            if artifacts:
                course_data["course_blueprint"] = (
                    build_course_blueprint_from_plan(
                        plan,
                        artifacts,
                    )
                )
            skeleton_stage.clear()
            skeleton_stage.update({
                "status": "invalidated",
                "reason": "scope_revision_changed",
                "previous_scope_revision_id": (
                    persisted_skeleton_scope
                ),
                "source_scope_revision_id": scope_revision_id,
            })
            await self._notify_checkpoint(
                on_checkpoint,
                course_data,
            )
        locked_names: dict[str, list[str]] = {}
        locked_identity_keys: set[str] = set()
        available_names: list[str] = []
        for section in sections:
            section_id = str(section.get("node_id") or "")
            package = normalize_section_knowledge_node_package({
                "knowledge_structure": section.get(
                    "knowledge_structure"
                )
                or [],
                "reused_knowledge_names": section.get(
                    "reused_knowledge_names"
                )
                or [],
            })
            report = validate_section_knowledge_package(
                package,
                section_title=str(section.get("title") or section_id),
                available_knowledge_names=available_names,
                validate_relations=False,
            )
            if not report.get("passed"):
                continue
            names = [
                str(point.get("name") or "").strip()
                for group in package.get("knowledge_structure") or []
                if isinstance(group, dict)
                for point in group.get("knowledge_points") or []
                if isinstance(point, dict)
                and str(point.get("name") or "").strip()
            ]
            unique_owned_names = []
            for name in names:
                identity_key = re.sub(
                    r"[^0-9a-z\u4e00-\u9fff]+",
                    "",
                    re.sub(
                        r"^\d+(?:\.\d+)*\s*",
                        "",
                        name,
                    ).lower(),
                )
                if (
                    identity_key
                    and identity_key not in locked_identity_keys
                ):
                    locked_identity_keys.add(identity_key)
                    unique_owned_names.append(name)
            if unique_owned_names:
                locked_names[section_id] = unique_owned_names
                available_names.extend(names)

        existing_skeleton = normalize_course_knowledge_skeleton(
            persisted_skeleton_payload
        )
        report = validate_course_knowledge_skeleton(
            existing_skeleton,
            sections=sections,
            locked_knowledge_names_by_section=locked_names,
            expected_scope_revision_id=scope_revision_id,
        )
        if report.get("passed"):
            course_data["course_knowledge_skeleton"] = existing_skeleton
            skeleton_stage.update({
                "status": "completed",
                "schema_version": existing_skeleton.get(
                    "schema_version"
                ),
                "revision_id": existing_skeleton.get("revision_id"),
                "quality_report": deepcopy(report),
                "source_scope_revision_id": scope_revision_id,
                "resumed": True,
            })
            return existing_skeleton

        compact_sections = []
        for section in sections:
            compact_section = {
                key: deepcopy(section.get(key))
                for key in (
                    "node_id",
                    "section_number",
                    "title",
                    "learning_objective",
                    "scope_boundary",
                    "prerequisite_node_ids",
                )
            }
            compact_section["evidence_hints"] = (
                build_section_knowledge_skeleton_evidence_hints(
                    artifacts or course_data,
                    section,
                )
            )
            compact_sections.append(compact_section)
        prompt = (
            self._prompt_composer
            .build_course_knowledge_skeleton_prompt(
                course_title=str(
                    plan.get("course_title")
                    or course_data.get("course_name")
                    or ""
                ),
                positioning=str(plan.get("positioning") or ""),
                sections=compact_sections,
                locked_knowledge_names_by_section=locked_names,
            )
        )
        await self._notify_phase(
            on_phase,
            "course_knowledge_skeleton",
            35,
            "正在一次性规划全课知识身份与复用边界",
            phase_progress=0,
            phase_detail={
                "artifact_type": "course_knowledge_skeleton",
                "item_total": len(sections),
                "locked_section_count": len(locked_names),
                "strategy": "global_identity_then_parallel_details",
            },
        )
        started_at = time.monotonic()
        async with self._planning_semaphore:
            response = await self._call_llm_with_heartbeat(
                "规划全课知识身份骨架，只输出 JSON。",
                prompt,
                enable_thinking=True,
                on_phase=on_phase,
                phase="course_knowledge_skeleton",
                base_progress=35,
                heartbeat_message="仍在等待 AI 规划全课知识身份骨架",
                phase_detail={
                    "artifact_type": "course_knowledge_skeleton",
                    "item_total": len(sections),
                },
            )
        parsed = self._extract_json(response) if response else None
        skeleton_payload = (
            parsed if isinstance(parsed, dict) else {}
        )
        skeleton_payload["source_scope_revision_id"] = (
            scope_revision_id
        )
        skeleton = normalize_course_knowledge_skeleton(skeleton_payload)
        report = validate_course_knowledge_skeleton(
            skeleton,
            sections=sections,
            locked_knowledge_names_by_section=locked_names,
            expected_scope_revision_id=scope_revision_id,
        )
        if not report.get("passed"):
            correction_prompt = (
                self._prompt_composer
                .build_course_knowledge_skeleton_correction_prompt(
                    original_prompt=prompt,
                    issues=report.get("issues") or [],
                )
            )
            async with self._planning_semaphore:
                corrected = await self._call_llm_with_heartbeat(
                    "修复全课知识身份骨架，只输出 JSON。",
                    correction_prompt,
                    enable_thinking=False,
                    on_phase=on_phase,
                    phase="course_knowledge_skeleton_validation",
                    base_progress=35,
                    heartbeat_message="仍在等待 AI 修复全课知识身份骨架",
                    phase_detail={
                        "artifact_type": "course_knowledge_skeleton",
                        "item_total": len(sections),
                    },
                )
            parsed = self._extract_json(corrected) if corrected else None
            skeleton_payload = (
                parsed if isinstance(parsed, dict) else {}
            )
            skeleton_payload["source_scope_revision_id"] = (
                scope_revision_id
            )
            skeleton = normalize_course_knowledge_skeleton(
                skeleton_payload
            )
            report = validate_course_knowledge_skeleton(
                skeleton,
                sections=sections,
                locked_knowledge_names_by_section=locked_names,
                expected_scope_revision_id=scope_revision_id,
            )

        duration_ms = int((time.monotonic() - started_at) * 1000)
        if not report.get("passed"):
            skeleton_stage.update({
                "status": "failed",
                "schema_version": "course_knowledge_skeleton_v1",
                "quality_report": deepcopy(report),
                "prompt_chars": len(prompt),
                "duration_ms": duration_ms,
            })
            course_data["generation_status"] = (
                "course_knowledge_skeleton_failed"
            )
            await self._notify_checkpoint(on_checkpoint, course_data)
            messages = "；".join(
                str(item.get("message") or "未知知识身份错误")
                for item in report.get("issues") or []
            )
            raise AIProviderRequestError(
                "全课知识身份骨架未通过验收："
                f"{messages or '无法解析骨架 JSON'}"
            )

        course_data["course_knowledge_skeleton"] = skeleton
        skeleton_stage.update({
            "status": "completed",
            "schema_version": skeleton.get("schema_version"),
            "revision_id": skeleton.get("revision_id"),
            "source_scope_revision_id": scope_revision_id,
            "quality_report": deepcopy(report),
            "prompt_chars": len(prompt),
            "duration_ms": duration_ms,
            "locked_section_count": len(locked_names),
            "owned_knowledge_count": (
                report.get("actual") or {}
            ).get("owned_knowledge_count", 0),
            "reused_knowledge_count": (
                report.get("actual") or {}
            ).get("reused_knowledge_count", 0),
            "strategy": "global_identity_then_parallel_details",
        })
        course_data["generation_status"] = (
            "course_knowledge_skeleton_compiled"
        )
        await self._notify_checkpoint(on_checkpoint, course_data)
        await self._notify_phase(
            on_phase,
            "course_knowledge_skeleton",
            35,
            "全课知识身份与复用边界已冻结",
            phase_progress=100,
            phase_detail={
                "artifact_type": "course_knowledge_skeleton",
                "item_total": len(sections),
                "revision_id": skeleton.get("revision_id"),
            },
        )
        return skeleton

    async def _enrich_section_knowledge_packages(
        self,
        *,
        course_data: dict[str, Any],
        plan: dict[str, Any],
        artifacts: dict[str, Any],
        on_phase: Callable[..., Awaitable[None] | None] | None,
        on_checkpoint: Callable[[dict[str, Any]], Awaitable[None] | None] | None,
    ) -> dict[str, Any]:
        """Generate independent section packages with bounded concurrency."""
        sections = [
            section
            for chapter in plan.get("chapters") or []
            if isinstance(chapter, dict)
            for section in chapter.get("sections") or []
            if isinstance(section, dict)
        ]
        total = len(sections)
        skeleton = await self._prepare_course_knowledge_skeleton(
            course_data=course_data,
            plan=plan,
            artifacts=artifacts,
            on_phase=on_phase,
            on_checkpoint=on_checkpoint,
        )
        skeleton_by_section = {
            str(item.get("node_id") or ""): item
            for item in skeleton.get("sections") or []
            if isinstance(item, dict)
        }
        stage_artifacts = course_data.setdefault("generation_stage_artifacts", {})
        package_states = stage_artifacts.setdefault("section_knowledge", {})
        strategy_state = stage_artifacts.setdefault(
            "section_knowledge_strategy", {}
        )
        course_scope_contract = (
            course_data.get("course_knowledge_scope_contract")
            or build_course_knowledge_scope_contract(plan)
        )
        state_lock = asyncio.Lock()
        jobs: list[dict[str, Any]] = []
        available_names: list[str] = []
        resumed_count = 0
        prompt_chars = 0
        started_at = time.monotonic()

        for index, section in enumerate(sections, start=1):
            node_id = str(section.get("node_id") or f"section-{index}")
            section_title = str(section.get("title") or node_id)
            identity = skeleton_by_section.get(node_id) or {}
            required_names = list(
                identity.get("owned_knowledge_names") or []
            )
            required_reused_names = list(
                identity.get("reused_knowledge_names") or []
            )
            existing_package = normalize_section_knowledge_node_package({
                "knowledge_structure": section.get("knowledge_structure") or [],
                "reused_knowledge_names": section.get("reused_knowledge_names") or [],
            })
            package_report = validate_section_knowledge_package(
                existing_package,
                section_title=section_title,
                available_knowledge_names=available_names,
                required_knowledge_names=required_names,
                required_reused_knowledge_names=required_reused_names,
                validate_relations=False,
            )
            if package_report.get("passed"):
                resumed_count += 1
                apply_section_knowledge_package(
                    plan, node_id, existing_package
                )
                section["knowledge_quality_report"] = deepcopy(
                    package_report
                )
                package_states[node_id] = {
                    "status": "completed",
                    "schema_version": existing_package.get(
                        "schema_version"
                    ),
                    "item_index": index,
                    "item_total": total,
                    "quality_report": deepcopy(package_report),
                    "resumed": True,
                }
            else:
                scope_slice = build_section_knowledge_scope_slice(
                    course_scope_contract,
                    node_id,
                )
                prompt = self._prompt_composer.build_section_knowledge_prompt(
                    course_title=str(
                        plan.get("course_title")
                        or course_data.get("course_name")
                        or ""
                    ),
                    positioning=str(plan.get("positioning") or ""),
                    section={
                        key: deepcopy(section.get(key))
                        for key in (
                            "node_id",
                            "section_number",
                            "title",
                            "learning_objective",
                            "prerequisite_node_ids",
                            "assessment",
                            "scope_boundary",
                        )
                    },
                    available_knowledge_names=available_names,
                    material_context=(
                        build_section_knowledge_material_context(
                            artifacts,
                            section,
                        )
                    ),
                    course_scope_contract=scope_slice,
                    knowledge_identity_contract=identity,
                )
                prompt_chars += len(prompt)
                jobs.append({
                    "index": index,
                    "section": section,
                    "node_id": node_id,
                    "section_title": section_title,
                    "available_names": list(available_names),
                    "required_names": required_names,
                    "required_reused_names": required_reused_names,
                    "prompt": prompt,
                })
            available_names.extend(required_names)

        progress_state = {"completed": resumed_count}
        strategy_state.update({
            "status": "generating",
            "strategy": "bounded_parallel_by_section",
            "max_concurrency": self._planning_concurrency,
            "total_item_count": total,
            "resumed_item_count": resumed_count,
            "generated_item_count": 0,
            "prompt_chars": prompt_chars,
            "scheduling": "bounded_fair_waves",
            "critical_path_rounds": (
                (len(jobs) + self._planning_concurrency - 1)
                // self._planning_concurrency
            ),
        })

        async def generate_job(job: dict[str, Any]) -> str:
            index = int(job["index"])
            node_id = str(job["node_id"])
            section_title = str(job["section_title"])
            prompt = str(job["prompt"])
            detail = {
                "artifact_type": "section_knowledge_package",
                "item_id": node_id,
                "item_name": section_title,
                "item_index": index,
                "item_total": total,
                "max_concurrency": self._planning_concurrency,
            }
            report: dict[str, Any] = {}
            try:
                await self._notify_phase(
                    on_phase,
                    "section_knowledge_generation",
                    35 + int(
                        progress_state["completed"]
                        / max(1, total)
                        * 13
                    ),
                    (
                        f"正在并行生成第 {index}/{total} 个小节知识包："
                        f"{section_title}"
                    ),
                    phase_progress=int(
                        progress_state["completed"]
                        / max(1, total)
                        * 100
                    ),
                    phase_detail={
                        **detail,
                        "completed_items": progress_state["completed"],
                        "total_items": total,
                    },
                )
                async with self._planning_semaphore:
                    response = await self._call_llm_with_heartbeat(
                        f"为小节「{section_title}」生成独立知识包，只输出 JSON。",
                        prompt,
                        enable_thinking=True,
                        on_phase=on_phase,
                        phase="section_knowledge_generation",
                        base_progress=35 + int(
                            (index - 1) / max(1, total) * 13
                        ),
                        heartbeat_message=(
                            f"仍在等待 AI 生成小节「{section_title}」的知识包"
                        ),
                        phase_detail=detail,
                    )
                package, report = self._validated_section_knowledge(
                    response,
                    section_title=section_title,
                    available_knowledge_names=job["available_names"],
                    required_knowledge_names=job["required_names"],
                    required_reused_knowledge_names=job[
                        "required_reused_names"
                    ],
                )
                if not report.get("passed"):
                    await self._notify_phase(
                        on_phase,
                        "section_knowledge_validation",
                        35 + int(
                            progress_state["completed"]
                            / max(1, total)
                            * 13
                        ),
                        (
                            f"小节「{section_title}」知识包未通过检查，"
                            "正在只修复当前小节"
                        ),
                        phase_progress=int(
                            progress_state["completed"]
                            / max(1, total)
                            * 100
                        ),
                        phase_detail={
                            **detail,
                            "issue_codes": [
                                item.get("code")
                                for item in report.get("issues") or []
                            ],
                        },
                    )
                    correction_prompt = (
                        self._prompt_composer
                        .build_section_knowledge_correction_prompt(
                            original_prompt=prompt,
                            issues=report.get("issues") or [],
                        )
                    )
                    async with self._planning_semaphore:
                        corrected = await self._call_llm_with_heartbeat(
                            (
                                f"修复小节「{section_title}」知识包，"
                                "只输出当前小节 JSON。"
                            ),
                            correction_prompt,
                            enable_thinking=False,
                            on_phase=on_phase,
                            phase="section_knowledge_validation",
                            base_progress=35 + int(
                                (index - 1) / max(1, total) * 13
                            ),
                            heartbeat_message=(
                                f"仍在等待 AI 修复小节「{section_title}」的知识包"
                            ),
                            phase_detail=detail,
                        )
                    package, report = self._validated_section_knowledge(
                        corrected,
                        section_title=section_title,
                        available_knowledge_names=job[
                            "available_names"
                        ],
                        required_knowledge_names=job["required_names"],
                        required_reused_knowledge_names=job[
                            "required_reused_names"
                        ],
                    )
                if package is None or not report.get("passed"):
                    messages = "；".join(
                        str(item.get("message") or "未知知识包错误")
                        for item in report.get("issues") or []
                    )
                    raise AIProviderRequestError(
                        f"小节「{section_title}」知识包未通过验收："
                        f"{messages or '无法解析当前小节 JSON'}"
                    )

                async with state_lock:
                    apply_section_knowledge_package(
                        plan, node_id, package
                    )
                    job["section"]["knowledge_quality_report"] = (
                        deepcopy(report)
                    )
                    plan["knowledge_relations"] = []
                    plan["knowledge_relation_decisions"] = []
                    package_states[node_id] = {
                        "status": "completed",
                        "schema_version": package.get(
                            "schema_version"
                        ),
                        "item_index": index,
                        "item_total": total,
                        "quality_report": deepcopy(report),
                    }
                    progress_state["completed"] += 1
                    strategy_state["generated_item_count"] = (
                        int(
                            strategy_state.get(
                                "generated_item_count", 0
                            )
                        )
                        + 1
                    )
                    course_data.update({
                        "course_plan": deepcopy(plan),
                        "knowledge_relations": [],
                        "nodes": self._merge_generation_nodes(
                            self._convert_plan_to_nodes(
                                plan,
                                str(
                                    course_data.get("course_id") or ""
                                ),
                            ),
                            course_data.get("nodes") or [],
                        ),
                        "course_blueprint": (
                            build_course_blueprint_from_plan(
                                plan, artifacts
                            )
                        ),
                        "generation_status": (
                            "section_knowledge_generation"
                        ),
                    })
                    await self._notify_checkpoint(
                        on_checkpoint, course_data
                    )
                    completed_now = progress_state["completed"]
                await self._notify_phase(
                    on_phase,
                    "section_knowledge_generation",
                    35 + int(completed_now / max(1, total) * 13),
                    (
                        f"已完成 {completed_now}/{total} 个小节知识包："
                        f"{section_title}"
                    ),
                    phase_progress=int(
                        completed_now / max(1, total) * 100
                    ),
                    phase_detail={
                        **detail,
                        "completed_items": completed_now,
                        "total_items": total,
                    },
                )
                return node_id
            except Exception as exc:
                async with state_lock:
                    if (
                        package_states.get(node_id) or {}
                    ).get("status") != "completed":
                        package_states[node_id] = {
                            "status": "failed",
                            "item_index": index,
                            "item_total": total,
                            "issues": deepcopy(
                                report.get("issues") or []
                            ),
                            "error": str(exc),
                        }
                    strategy_state["status"] = "failed"
                    course_data["generation_status"] = (
                        "section_knowledge_failed"
                    )
                    await self._notify_checkpoint(
                        on_checkpoint, course_data
                    )
                raise

        results: list[str | BaseException] = []
        for offset in range(
            0,
            len(jobs),
            self._planning_concurrency,
        ):
            wave_results = await asyncio.gather(
                *(
                    generate_job(job)
                    for job in jobs[
                        offset:offset
                        + self._planning_concurrency
                    ]
                ),
                return_exceptions=True,
            )
            results.extend(wave_results)
            if any(
                isinstance(result, Exception)
                for result in wave_results
            ):
                break
        failures = [
            result
            for result in results
            if isinstance(result, Exception)
        ]
        if failures:
            async with state_lock:
                strategy_state.update({
                    "status": "failed",
                    "duration_ms": int(
                        (time.monotonic() - started_at) * 1000
                    ),
                    "failed_item_count": sum(
                        1
                        for state in package_states.values()
                        if isinstance(state, dict)
                        and state.get("status") == "failed"
                    ),
                })
                course_data["generation_status"] = (
                    "section_knowledge_failed"
                )
                await self._notify_checkpoint(
                    on_checkpoint,
                    course_data,
                )
            first = failures[0]
            if isinstance(first, AIProviderRequestError):
                raise first
            raise AIProviderRequestError(
                f"小节知识包生成失败：{first}"
            ) from first

        final_available_names: list[str] = []
        for index, section in enumerate(sections, start=1):
            node_id = str(section.get("node_id") or f"section-{index}")
            identity = skeleton_by_section.get(node_id) or {}
            package = normalize_section_knowledge_node_package({
                "knowledge_structure": section.get(
                    "knowledge_structure"
                )
                or [],
                "reused_knowledge_names": section.get(
                    "reused_knowledge_names"
                )
                or [],
            })
            final_report = validate_section_knowledge_package(
                package,
                section_title=str(section.get("title") or node_id),
                available_knowledge_names=final_available_names,
                required_knowledge_names=list(
                    identity.get("owned_knowledge_names") or []
                ),
                required_reused_knowledge_names=list(
                    identity.get("reused_knowledge_names") or []
                ),
                validate_relations=False,
            )
            if not final_report.get("passed"):
                raise AIProviderRequestError(
                    f"小节「{section.get('title') or node_id}」"
                    "在确定性合并后未通过知识身份验收"
                )
            final_available_names.extend(
                identity.get("owned_knowledge_names") or []
            )

        strategy_state.update({
            "status": "completed",
            "completed_item_count": total,
            "failed_item_count": 0,
            "duration_ms": int(
                (time.monotonic() - started_at) * 1000
            ),
            "merge_order": [
                str(section.get("node_id") or "")
                for section in sections
            ],
        })
        course_data.update({
            "course_plan": deepcopy(plan),
            "knowledge_relations": [],
            "nodes": self._merge_generation_nodes(
                self._convert_plan_to_nodes(
                    plan,
                    str(course_data.get("course_id") or ""),
                ),
                course_data.get("nodes") or [],
            ),
            "course_blueprint": build_course_blueprint_from_plan(
                plan, artifacts
            ),
            "generation_status": "section_knowledge_compiled",
        })
        await self._notify_checkpoint(on_checkpoint, course_data)
        return plan

    async def _enrich_course_knowledge_relations(
        self,
        *,
        course_data: dict[str, Any],
        plan: dict[str, Any],
        on_phase: Callable[..., Awaitable[None] | None] | None,
        on_checkpoint: Callable[[dict[str, Any]], Awaitable[None] | None] | None,
    ) -> dict[str, Any]:
        """Build validated relation neighborhoods with bounded concurrency."""
        course_id = str(course_data.get("course_id") or "")
        course_data.pop("course_knowledge_base", None)
        course_data.pop("course_knowledge_map", None)
        course_data.pop("course_knowledge_quality_report", None)
        course_data.update({
            "course_plan": deepcopy(plan),
            "knowledge_relations": [],
            "knowledge_relation_decisions": [],
            "nodes": self._merge_generation_nodes(
                self._convert_plan_to_nodes(plan, course_id),
                course_data.get("nodes") or [],
            ),
        })
        registry_source = deepcopy(course_data)
        registry_source.pop("course_knowledge_base", None)
        registry_source.pop("course_knowledge_map", None)
        registry_source["knowledge_relations"] = []
        registry_source["knowledge_relation_decisions"] = []
        registry = compile_course_knowledge_base(registry_source)
        knowledge_points = [
            item
            for item in registry.get("knowledge_points") or []
            if isinstance(item, dict)
            and str(item.get("knowledge_id") or "")
        ]
        if not knowledge_points:
            raise AIProviderRequestError(
                "全课知识节点注册表为空，无法进入关系建网阶段"
            )

        sections = [
            section
            for chapter in plan.get("chapters") or []
            if isinstance(chapter, dict)
            for section in chapter.get("sections") or []
            if isinstance(section, dict)
        ]
        total = len(sections)
        section_by_id = {
            str(section.get("node_id") or ""): section
            for section in sections
        }
        section_title_by_id = {
            section_id: str(section.get("title") or section_id)
            for section_id, section in section_by_id.items()
        }
        primary_points_by_section: dict[str, list[dict[str, Any]]] = {}
        points_by_section: dict[str, list[dict[str, Any]]] = {}
        for point in knowledge_points:
            section_refs = [
                str(item)
                for item in point.get("section_refs") or []
                if str(item)
            ]
            if not section_refs:
                continue
            primary_points_by_section.setdefault(
                section_refs[0], []
            ).append(point)
            for section_id in section_refs:
                points_by_section.setdefault(
                    section_id, []
                ).append(point)

        stage_artifacts = course_data.setdefault(
            "generation_stage_artifacts", {}
        )
        relation_stage = stage_artifacts.setdefault(
            "course_relations", {}
        )
        registry_revision_id = str(registry.get("revision_id") or "")
        if (
            relation_stage.get("knowledge_registry_revision_id")
            != registry_revision_id
        ):
            relation_stage.clear()
            relation_stage.update({
                "status": "generating",
                "schema_version": "course_relation_plan_v1",
                "knowledge_registry_revision_id": (
                    registry_revision_id
                ),
                "batches": {},
            })
        batch_states = relation_stage.setdefault("batches", {})
        section_chapter = {
            str(section.get("node_id") or ""): chapter
            for chapter in plan.get("chapters") or []
            if isinstance(chapter, dict)
            for section in chapter.get("sections") or []
            if isinstance(section, dict)
        }
        active_chapter: Any = object()
        previous_section_id = ""
        chapter_prior_section_ids: list[str] = []
        specs: list[dict[str, Any]] = []
        resumed_count = 0
        prompt_chars = 0
        started_at = time.monotonic()

        for index, section in enumerate(sections, start=1):
            section_id = str(
                section.get("node_id") or f"section-{index}"
            )
            section_title = str(
                section.get("title") or section_id
            )
            chapter = section_chapter.get(section_id)
            if chapter is not active_chapter:
                active_chapter = chapter
                chapter_prior_section_ids = []
            target_points = primary_points_by_section.get(
                section_id, []
            )
            target_ids = [
                str(point.get("knowledge_id") or "")
                for point in target_points
            ]
            if not target_ids:
                batch_states[section_id] = {
                    "status": "completed",
                    "schema_version": "course_relation_batch_v1",
                    "knowledge_registry_revision_id": (
                        registry_revision_id
                    ),
                    "target_knowledge_ids": [],
                    "allowed_knowledge_ids": [],
                    "payload": {
                        "node_decisions": [],
                        "relations": [],
                    },
                }
                resumed_count += 1
                previous_section_id = section_id
                chapter_prior_section_ids.append(section_id)
                continue

            context_section_ids = list(dict.fromkeys([
                section_id,
                *[
                    str(item)
                    for item in section.get(
                        "prerequisite_node_ids"
                    )
                    or []
                    if str(item)
                ],
                *chapter_prior_section_ids,
                *(
                    [previous_section_id]
                    if previous_section_id
                    else []
                ),
            ]))
            context_points_by_id: dict[str, dict[str, Any]] = {}
            for context_section_id in context_section_ids:
                for point in points_by_section.get(
                    context_section_id, []
                ):
                    knowledge_id = str(
                        point.get("knowledge_id") or ""
                    )
                    if knowledge_id:
                        context_points_by_id[knowledge_id] = point
            for point in target_points:
                knowledge_id = str(
                    point.get("knowledge_id") or ""
                )
                if knowledge_id:
                    context_points_by_id[knowledge_id] = point
            context_points = list(context_points_by_id.values())
            allowed_ids = list(context_points_by_id)
            existing_state = batch_states.get(section_id) or {}
            existing_payload = existing_state.get("payload")
            report = validate_course_relation_batch(
                (
                    existing_payload
                    if isinstance(existing_payload, dict)
                    else {}
                ),
                target_knowledge_ids=target_ids,
                allowed_knowledge_ids=allowed_ids,
            )
            can_resume = (
                existing_state.get("status") == "completed"
                and existing_state.get(
                    "knowledge_registry_revision_id"
                )
                == registry_revision_id
                and existing_state.get(
                    "target_knowledge_ids"
                )
                == target_ids
                and report.get("passed")
            )
            prompt = ""
            if can_resume:
                resumed_count += 1
            else:
                prompt = (
                    self._prompt_composer
                    .build_course_relation_batch_prompt(
                        course_title=str(
                            plan.get("course_title")
                            or course_data.get("course_name")
                            or ""
                        ),
                        positioning=str(
                            plan.get("positioning") or ""
                        ),
                        batch_id=f"relation:{section_id}",
                        section={
                            "node_id": section_id,
                            "title": section_title,
                            "learning_objective": section.get(
                                "learning_objective"
                            ),
                            "scope_boundary": section.get(
                                "scope_boundary"
                            ),
                            "prerequisite_node_ids": (
                                section.get(
                                    "prerequisite_node_ids"
                                )
                                or []
                            ),
                        },
                        target_points=[
                            self._relation_prompt_point(
                                point, section_title_by_id
                            )
                            for point in target_points
                        ],
                        context_points=[
                            self._relation_prompt_point(
                                point, section_title_by_id
                            )
                            for point in context_points
                        ],
                    )
                )
                prompt_chars += len(prompt)
            specs.append({
                "index": index,
                "section_id": section_id,
                "section_title": section_title,
                "target_ids": target_ids,
                "allowed_ids": allowed_ids,
                "prompt": prompt,
                "can_resume": can_resume,
            })
            previous_section_id = section_id
            chapter_prior_section_ids.append(section_id)

        jobs = [
            spec for spec in specs if not spec["can_resume"]
        ]
        progress_state = {"completed": resumed_count}
        relation_stage.update({
            "status": "generating",
            "strategy": "bounded_parallel_by_section",
            "max_concurrency": self._planning_concurrency,
            "completed_batch_count": resumed_count,
            "total_batch_count": total,
            "resumed_batch_count": resumed_count,
            "generated_batch_count": 0,
            "prompt_chars": prompt_chars,
            "scheduling": "bounded_fair_waves",
            "critical_path_rounds": (
                (len(jobs) + self._planning_concurrency - 1)
                // self._planning_concurrency
            ),
        })
        state_lock = asyncio.Lock()

        def ordered_payloads() -> list[dict[str, Any]]:
            payloads = []
            for section in sections:
                section_id = str(section.get("node_id") or "")
                state = batch_states.get(section_id) or {}
                payload = state.get("payload")
                if (
                    state.get("status") == "completed"
                    and isinstance(payload, dict)
                ):
                    payloads.append(
                        normalize_course_relation_batch(payload)
                    )
            return payloads

        async def generate_relation_batch(
            spec: dict[str, Any],
        ) -> str:
            index = int(spec["index"])
            section_id = str(spec["section_id"])
            section_title = str(spec["section_title"])
            prompt = str(spec["prompt"])
            detail = {
                "artifact_type": "course_relation_batch",
                "item_id": section_id,
                "item_name": section_title,
                "item_index": index,
                "item_total": total,
                "max_concurrency": self._planning_concurrency,
            }
            report: dict[str, Any] = {}
            try:
                await self._notify_phase(
                    on_phase,
                    "course_relation_generation",
                    48 + int(
                        progress_state["completed"]
                        / max(1, total)
                        * 2
                    ),
                    (
                        f"正在并行建立第 {index}/{total} 个知识关系邻域："
                        f"{section_title}"
                    ),
                    phase_progress=int(
                        progress_state["completed"]
                        / max(1, total)
                        * 100
                    ),
                    phase_detail={
                        **detail,
                        "completed_items": progress_state["completed"],
                        "total_items": total,
                    },
                )
                async with self._planning_semaphore:
                    response = await self._call_llm_with_heartbeat(
                        (
                            f"为小节「{section_title}」建立知识关系邻域，"
                            "只输出 JSON。"
                        ),
                        prompt,
                        enable_thinking=True,
                        on_phase=on_phase,
                        phase="course_relation_generation",
                        base_progress=48 + int(
                            (index - 1) / max(1, total) * 2
                        ),
                        heartbeat_message=(
                            f"仍在等待 AI 建立小节「{section_title}」"
                            "的知识关系邻域"
                        ),
                        phase_detail=detail,
                    )
                parsed = self._extract_json(response) if response else None
                payload = normalize_course_relation_batch(
                    parsed if isinstance(parsed, dict) else {}
                )
                report = validate_course_relation_batch(
                    payload,
                    target_knowledge_ids=spec["target_ids"],
                    allowed_knowledge_ids=spec["allowed_ids"],
                )
                if not report.get("passed"):
                    correction_prompt = (
                        self._prompt_composer
                        .build_course_relation_batch_correction_prompt(
                            original_prompt=prompt,
                            issues=report.get("issues") or [],
                        )
                    )
                    async with self._planning_semaphore:
                        corrected = await self._call_llm_with_heartbeat(
                            (
                                f"修复小节「{section_title}」的关系批次结构，"
                                "只输出 JSON。"
                            ),
                            correction_prompt,
                            enable_thinking=False,
                            on_phase=on_phase,
                            phase="course_relation_validation",
                            base_progress=48 + int(
                                (index - 1) / max(1, total) * 2
                            ),
                            heartbeat_message=(
                                f"仍在等待 AI 修复小节「{section_title}」"
                                "的关系批次结构"
                            ),
                            phase_detail=detail,
                        )
                    parsed = (
                        self._extract_json(corrected)
                        if corrected
                        else None
                    )
                    payload = normalize_course_relation_batch(
                        parsed if isinstance(parsed, dict) else {}
                    )
                    report = validate_course_relation_batch(
                        payload,
                        target_knowledge_ids=spec["target_ids"],
                        allowed_knowledge_ids=spec["allowed_ids"],
                    )
                if not report.get("passed"):
                    repaired = repair_course_relation_batch_decisions(
                        payload,
                        issues=report.get("issues") or [],
                    )
                    if repaired is not None:
                        payload = repaired
                        report = validate_course_relation_batch(
                            payload,
                            target_knowledge_ids=spec["target_ids"],
                            allowed_knowledge_ids=spec["allowed_ids"],
                        )
                if not report.get("passed"):
                    messages = "；".join(
                        str(
                            item.get("message")
                            or "未知关系结构错误"
                        )
                        for item in report.get("issues") or []
                    )
                    raise AIProviderRequestError(
                        f"小节「{section_title}」关系建网未通过结构验收："
                        f"{messages or '关系批次无法解析'}"
                    )

                payload = normalize_course_relation_batch(payload)
                async with state_lock:
                    batch_states[section_id] = {
                        "status": "completed",
                        "schema_version": payload.get(
                            "schema_version"
                        ),
                        "knowledge_registry_revision_id": (
                            registry_revision_id
                        ),
                        "target_knowledge_ids": list(
                            spec["target_ids"]
                        ),
                        "allowed_knowledge_ids": list(
                            spec["allowed_ids"]
                        ),
                        "validation_report": deepcopy(report),
                        "payload": deepcopy(payload),
                    }
                    progress_state["completed"] += 1
                    relation_stage["generated_batch_count"] = (
                        int(
                            relation_stage.get(
                                "generated_batch_count", 0
                            )
                        )
                        + 1
                    )
                    partial_decisions, partial_relations = (
                        merge_course_relation_batches(
                            ordered_payloads()
                        )
                    )
                    relation_stage.update({
                        "status": "generating",
                        "completed_batch_count": (
                            progress_state["completed"]
                        ),
                        "decision_count": len(
                            partial_decisions
                        ),
                        "relation_count": len(
                            partial_relations
                        ),
                    })
                    course_data.update({
                        "knowledge_relations": deepcopy(
                            partial_relations
                        ),
                        "knowledge_relation_decisions": deepcopy(
                            partial_decisions
                        ),
                        "generation_status": (
                            "course_relation_generation"
                        ),
                    })
                    await self._notify_checkpoint(
                        on_checkpoint, course_data
                    )
                return section_id
            except Exception as exc:
                async with state_lock:
                    if (
                        batch_states.get(section_id) or {}
                    ).get("status") != "completed":
                        batch_states[section_id] = {
                            "status": "failed",
                            "schema_version": (
                                "course_relation_batch_v1"
                            ),
                            "knowledge_registry_revision_id": (
                                registry_revision_id
                            ),
                            "target_knowledge_ids": list(
                                spec["target_ids"]
                            ),
                            "issues": (
                                deepcopy(report.get("issues") or [])
                                or [{
                                    "code": (
                                        "course_relations:"
                                        "provider_or_validation_failure"
                                    ),
                                    "message": str(exc),
                                }]
                            ),
                        }
                    relation_stage["status"] = "failed"
                    course_data["generation_status"] = (
                        "course_relation_generation_failed"
                    )
                    await self._notify_checkpoint(
                        on_checkpoint, course_data
                    )
                raise

        results: list[str | BaseException] = []
        for offset in range(
            0,
            len(jobs),
            self._planning_concurrency,
        ):
            wave_results = await asyncio.gather(
                *(
                    generate_relation_batch(spec)
                    for spec in jobs[
                        offset:offset
                        + self._planning_concurrency
                    ]
                ),
                return_exceptions=True,
            )
            results.extend(wave_results)
            if any(
                isinstance(result, Exception)
                for result in wave_results
            ):
                break
        failures = [
            result
            for result in results
            if isinstance(result, Exception)
        ]
        if failures:
            async with state_lock:
                relation_stage.update({
                    "status": "failed",
                    "duration_ms": int(
                        (time.monotonic() - started_at) * 1000
                    ),
                    "failed_batch_count": sum(
                        1
                        for state in batch_states.values()
                        if isinstance(state, dict)
                        and state.get("status") == "failed"
                    ),
                })
                course_data["generation_status"] = (
                    "course_relation_generation_failed"
                )
                await self._notify_checkpoint(
                    on_checkpoint,
                    course_data,
                )
            first = failures[0]
            if isinstance(first, AIProviderRequestError):
                raise first
            raise AIProviderRequestError(
                f"全课知识关系批次生成失败：{first}"
            ) from first

        decisions, relations = merge_course_relation_batches(
            ordered_payloads()
        )
        all_knowledge_ids = [
            str(item.get("knowledge_id") or "")
            for item in knowledge_points
        ]
        global_report = validate_course_relation_batch(
            {
                "node_decisions": decisions,
                "relations": relations,
            },
            target_knowledge_ids=all_knowledge_ids,
            allowed_knowledge_ids=all_knowledge_ids,
        )
        if not global_report.get("passed"):
            relation_stage.update({
                "status": "failed",
                "global_validation_report": deepcopy(
                    global_report
                ),
            })
            course_data["generation_status"] = (
                "course_relation_generation_failed"
            )
            await self._notify_checkpoint(on_checkpoint, course_data)
            messages = "；".join(
                str(item.get("message") or "未知全课关系结构错误")
                for item in global_report.get("issues") or []
            )
            raise AIProviderRequestError(
                "全课知识关系网未通过结构验收："
                f"{messages or '关系图不完整'}"
            )

        plan = attach_course_relation_plan(
            plan,
            knowledge_points=knowledge_points,
            node_decisions=decisions,
            relations=relations,
        )
        relation_stage.update({
            "status": "completed",
            "completed_batch_count": total,
            "total_batch_count": total,
            "failed_batch_count": 0,
            "decision_count": len(decisions),
            "relation_count": len(relations),
            "duration_ms": int(
                (time.monotonic() - started_at) * 1000
            ),
            "merge_order": [
                str(section.get("node_id") or "")
                for section in sections
            ],
            "global_validation_report": deepcopy(global_report),
        })
        course_data.update({
            "course_plan": deepcopy(plan),
            "knowledge_relations": deepcopy(relations),
            "knowledge_relation_decisions": deepcopy(decisions),
            "knowledge_registry_revision_id": registry_revision_id,
            "nodes": self._merge_generation_nodes(
                self._convert_plan_to_nodes(plan, course_id),
                course_data.get("nodes") or [],
            ),
            "generation_status": "course_relations_compiled",
        })
        await self._notify_checkpoint(on_checkpoint, course_data)
        await self._notify_phase(
            on_phase,
            "course_relation_generation",
            50,
            (
                f"全课 {len(knowledge_points)} 个知识点已完成关系规划，"
                f"编译 {len(relations)} 条正式关系"
            ),
            phase_progress=100,
            phase_detail={
                "artifact_type": "course_relation_plan",
                "completed_items": len(decisions),
                "total_items": len(knowledge_points),
                "relation_count": len(relations),
                "knowledge_registry_revision_id": (
                    registry_revision_id
                ),
                "max_concurrency": self._planning_concurrency,
            },
        )
        return plan

    @staticmethod
    def _relation_prompt_point(
        point: dict[str, Any],
        section_title_by_id: dict[str, str],
    ) -> dict[str, Any]:
        section_refs = [
            str(item)
            for item in point.get("section_refs") or []
            if str(item)
        ]
        primary_section_id = section_refs[0] if section_refs else ""
        return {
            "knowledge_id": str(point.get("knowledge_id") or ""),
            "name": str(point.get("name") or ""),
            "statement": str(point.get("statement") or ""),
            "knowledge_type": str(point.get("knowledge_type") or ""),
            "conditions": deepcopy(point.get("conditions") or []),
            "boundaries": deepcopy(point.get("boundaries") or []),
            "primary_section_id": primary_section_id,
            "primary_section_title": section_title_by_id.get(
                primary_section_id,
                primary_section_id,
            ),
        }

    @staticmethod
    def _outline_only_plan(plan: dict[str, Any]) -> dict[str, Any]:
        outline = deepcopy(plan)
        outline["knowledge_relations"] = []
        outline["knowledge_relation_decisions"] = []
        outline.pop("knowledge_relation_schema_version", None)
        for chapter in outline.get("chapters") or []:
            for section in chapter.get("sections") or []:
                section["key_points"] = []
                section["knowledge_structure"] = []
                section["reused_knowledge_names"] = []
                section.pop("knowledge_relations", None)
                section.pop("knowledge_package_status", None)
        return outline

    @staticmethod
    def _merge_outline_node_edits(
        plan: dict[str, Any],
        nodes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        by_id = {
            str(node.get("node_id") or ""): node
            for node in nodes
            if int(node.get("node_level") or 1) == 2
        }
        for chapter in plan.get("chapters") or []:
            for section in chapter.get("sections") or []:
                node = by_id.get(str(section.get("node_id") or ""))
                if not node:
                    continue
                section_number = str(section.get("section_number") or "")
                node_name = str(node.get("node_name") or "").strip()
                prefix = f"{section_number} "
                section["title"] = (
                    node_name[len(prefix):].strip()
                    if section_number and node_name.startswith(prefix)
                    else node_name or section.get("title")
                )
                for field in (
                    "learning_objective",
                    "scope_boundary",
                    "assessment",
                    "prerequisite_node_ids",
                ):
                    if field in node:
                        section[field] = deepcopy(node[field])
        return plan

    @staticmethod
    def _merge_generation_nodes(
        generated_nodes: list[dict[str, Any]],
        existing_nodes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        existing_by_id = {
            str(node.get("node_id") or ""): node
            for node in existing_nodes
        }
        content_fields = {
            "node_content",
            "node_content_draft",
            "content_blocks",
            "course_blocks",
            "generation_status",
            "generated_chars",
            "generation_quality",
            "grounding_annotations",
            "grounding_invalid_refs",
            "needs_manual_review",
            "error_summary",
        }
        merged_nodes: list[dict[str, Any]] = []
        for generated in generated_nodes:
            previous = existing_by_id.get(str(generated.get("node_id") or ""), {})
            merged = {**deepcopy(previous), **deepcopy(generated)}
            for field in content_fields:
                if field in previous and previous.get(field) not in (None, "", []):
                    merged[field] = deepcopy(previous[field])
            merged_nodes.append(merged)
        return merged_nodes

    async def _resolve_course_pedagogy(
        self,
        *,
        subject: str,
        requirements: str,
        materials: list[Any],
        artifacts: dict[str, Any],
        requested_mode: str,
        requested_secondary_mode: str | None,
        requested_intensity: str | None,
    ) -> SubjectPedagogyProfile:
        deterministic = resolve_pedagogy_profile(
            subject=subject,
            requirements=requirements,
            materials=materials,
            requested_mode=requested_mode,
            requested_secondary_mode=requested_secondary_mode,
            requested_intensity=requested_intensity,
        )
        if deterministic.user_locked or deterministic.confidence == "high":
            return deterministic

        material_summary = build_outline_generation_context(artifacts)[-5000:]
        classifier_prompt = self._prompt_composer.build_profile_classifier_prompt(
            subject=subject,
            requirements=requirements,
            deterministic_profile=deterministic,
            material_summary=material_summary,
        )
        response = await self._call_llm(
            "判断课程教学结构，只输出 JSON。",
            classifier_prompt,
            enable_thinking=True,
        )
        candidate = self._extract_json(response) if response else None
        if not isinstance(candidate, dict):
            return deterministic
        primary = parse_mode(candidate.get("primary_mode"))
        secondary = parse_mode(candidate.get("secondary_mode"))
        if not primary or secondary == primary:
            return deterministic
        normalized = resolve_pedagogy_profile(
            subject=subject,
            requirements=requirements,
            materials=materials,
            requested_mode=primary.value,
            requested_secondary_mode=secondary.value if secondary else None,
            requested_intensity=candidate.get("secondary_intensity"),
        )
        evidence = tuple(
            str(item).strip() for item in candidate.get("evidence", [])
            if str(item).strip()
        ) or deterministic.evidence
        return SubjectPedagogyProfile(
            primary_mode=normalized.primary_mode,
            secondary_mode=normalized.secondary_mode,
            secondary_intensity=normalized.secondary_intensity,
            confidence="medium" if deterministic.confidence == "low" else deterministic.confidence,
            evidence=evidence[:12],
            rationale=str(candidate.get("rationale") or normalized.rationale),
            enabled_module_ids=normalized.enabled_module_ids,
            user_locked=False,
        )

    async def _call_llm_with_heartbeat(
        self,
        user_prompt: str,
        system_prompt: str,
        *,
        enable_thinking: bool,
        on_phase: Callable[..., Awaitable[None] | None] | None,
        phase: str,
        base_progress: int,
        heartbeat_seconds: float = 15.0,
        stage_timeout_seconds: float | None = None,
        heartbeat_message: str = "仍在等待 AI 返回当前生成产物",
        phase_detail: dict[str, Any] | None = None,
    ) -> str:
        """Run `_call_llm` while periodically re-announcing the same phase with
        an elapsed-time message, so a slow/degraded AI provider response
        (this call alone can legally take tens of minutes across all model
        candidates' retries — see `ai_base._call_llm`) shows up to the user as
        "still working, Ns elapsed" instead of a progress bar frozen at a flat
        percentage that looks identical to a hang.
        """
        timeout_seconds = max(
            1.0,
            float(
                stage_timeout_seconds
                if stage_timeout_seconds is not None
                else os.getenv("AI_STAGE_TIMEOUT_SECONDS", "300")
            ),
        )
        call = self._call_llm(
            user_prompt,
            system_prompt,
            enable_thinking=enable_thinking,
            raise_on_failure=True,
        )
        if not on_phase:
            try:
                return await asyncio.wait_for(call, timeout=timeout_seconds)
            except asyncio.TimeoutError as exc:
                raise AIProviderRequestError(
                    f"{phase} 阶段超过 {int(timeout_seconds)} 秒仍未返回，"
                    "已停止当前最小生成单元，可从最近检查点继续"
                ) from exc

        done = asyncio.Event()

        async def _heartbeat() -> None:
            elapsed = 0
            while True:
                try:
                    await asyncio.wait_for(done.wait(), timeout=heartbeat_seconds)
                    return
                except asyncio.TimeoutError:
                    elapsed += int(heartbeat_seconds)
                    await self._notify_phase(
                        on_phase,
                        phase,
                        base_progress,
                        f"{heartbeat_message}（已等待约 {elapsed} 秒）",
                        phase_progress=100,
                        phase_detail={
                            **(phase_detail or {}),
                            "heartbeat": True,
                            "elapsed_seconds": elapsed,
                        },
                    )

        heartbeat_task = asyncio.create_task(_heartbeat())
        try:
            return await asyncio.wait_for(call, timeout=timeout_seconds)
        except asyncio.TimeoutError as exc:
            await self._notify_phase(
                on_phase,
                phase,
                base_progress,
                f"{heartbeat_message}超时，已保留最近检查点",
                phase_progress=100,
                phase_detail={
                    **(phase_detail or {}),
                    "timed_out": True,
                    "timeout_seconds": timeout_seconds,
                },
            )
            raise AIProviderRequestError(
                f"{phase} 阶段超过 {int(timeout_seconds)} 秒仍未返回，"
                "已停止当前最小生成单元，可从最近检查点继续"
            ) from exc
        finally:
            done.set()
            await heartbeat_task

    @staticmethod
    async def _notify_phase(
        callback: Callable[..., Awaitable[None] | None] | None,
        phase: str,
        progress: int,
        message: str,
        *,
        phase_progress: int | None = None,
        phase_detail: dict[str, Any] | None = None,
    ) -> None:
        if not callback:
            return
        result = callback(
            phase,
            progress,
            message,
            phase_progress if phase_progress is not None else progress,
            phase_detail or {},
        )
        if inspect.isawaitable(result):
            await result

    @staticmethod
    async def _notify_checkpoint(
        callback: Callable[[dict[str, Any]], Awaitable[None] | None] | None,
        checkpoint: dict[str, Any],
    ) -> None:
        if not callback:
            return
        result = callback(checkpoint)
        if inspect.isawaitable(result):
            await result

    async def generate_course(
        self,
        topic: str,
        target_audience: str = "大学生",
        depth: str = "intermediate",
        **kwargs: Any,
    ) -> dict:
        """兼容直接调用；生产路由由 TaskManager 创建唯一 GenerationJob。"""
        course_id = str(uuid.uuid4())
        return await self.build_course_draft(
            course_id=course_id,
            topic=topic,
            target_audience=target_audience,
            depth=depth,
            style=kwargs.get("style"),
            composition_style=kwargs.get("composition_style"),
            requirements=str(kwargs.get("requirements") or ""),
            materials=kwargs.get("materials") or [],
            material_bindings=kwargs.get("material_bindings") or [],
            grounding_strategy=str(kwargs.get("grounding_strategy") or "material_first"),
            learner_profile_summary=str(kwargs.get("learner_profile_summary") or ""),
            current_readiness=kwargs.get("current_readiness"),
            adaptation_preference=str(
                kwargs.get("adaptation_preference") or "preserve_target_extend"
            ),
            pedagogy_mode=str(kwargs.get("pedagogy_mode") or "auto"),
            secondary_mode=kwargs.get("secondary_mode"),
            secondary_intensity=kwargs.get("secondary_intensity"),
        )

    # ------------------------------------------------------------------
    # 课程规划
    # ------------------------------------------------------------------

    def _validated_course_outline(
        self,
        response: str | None,
        brief: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        parsed = self._extract_json(response) if response else None
        if not isinstance(parsed, dict) or not isinstance(parsed.get("chapters"), list):
            report = validate_course_outline_constraints({}, brief)
            return None, report
        raw_report = validate_course_outline_constraints(parsed, brief)
        malformed_codes = {
            "outline:malformed_chapters",
            "outline:malformed_section_lists",
            "outline:malformed_section",
        }
        if any(
            item.get("code") in malformed_codes
            for item in raw_report.get("issues") or []
        ):
            return None, raw_report
        plan = normalize_course_outline_contract(parsed)
        return plan, validate_course_outline_constraints(plan, brief)

    def _validated_section_knowledge(
        self,
        response: str | None,
        *,
        section_title: str,
        available_knowledge_names: list[str],
        required_knowledge_names: list[str] | None = None,
        required_reused_knowledge_names: list[str] | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        parsed = self._extract_json(response) if response else None
        if not isinstance(parsed, dict):
            empty = normalize_section_knowledge_node_package({})
            return None, validate_section_knowledge_package(
                empty,
                section_title=section_title,
                available_knowledge_names=available_knowledge_names,
                required_knowledge_names=required_knowledge_names,
                required_reused_knowledge_names=(
                    required_reused_knowledge_names
                ),
                validate_relations=False,
            )
        package = normalize_section_knowledge_node_package(parsed)
        report = validate_section_knowledge_package(
            package,
            section_title=section_title,
            available_knowledge_names=available_knowledge_names,
            required_knowledge_names=required_knowledge_names,
            required_reused_knowledge_names=(
                required_reused_knowledge_names
            ),
            validate_relations=False,
        )
        return package, report

    def _validated_course_plan(
        self,
        response: str | None,
        brief: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        parsed = self._extract_json(response) if response else None
        if not isinstance(parsed, dict) or not isinstance(parsed.get("chapters"), list):
            report = validate_course_plan_constraints({}, brief)
            return None, report
        raw_report = validate_course_plan_constraints(parsed, brief)
        malformed_codes = {
            "plan:malformed_chapters",
            "plan:malformed_section_lists",
            "plan:malformed_sections",
        }
        if any(
            item.get("code") in malformed_codes
            for item in raw_report.get("issues") or []
        ):
            return None, raw_report
        plan = normalize_course_plan_contract(parsed)
        return plan, validate_course_plan_constraints(plan, brief)

    def _convert_plan_to_nodes(self, plan: dict, course_id: str) -> list[dict]:
        """将课程规划转换为节点列表。

        Args:
            plan: 课程规划字典
            course_id: 课程 ID

        Returns:
            节点字典列表
        """
        nodes: list[dict] = []

        for chapter in plan.get("chapters", []):
            chapter_num = chapter.get("chapter_number", len(nodes) + 1)

            nodes.append({
                "node_id": f"L1-{chapter_num}",
                "parent_node_id": "root",
                "node_name": f"第{chapter_num}章 {chapter.get('title', '')}",
                "node_level": 1,
                "node_content": "",
                "content_blocks": [],
                "node_type": "original",
                "learning_focus": chapter.get("learning_focus", ""),
                "generation_status": "pending",
                "generated_chars": 0,
                "error_summary": None,
            })

            for section in chapter.get("sections", []):
                section_num = section.get("section_number", f"{chapter_num}.1")
                nodes.append({
                    "node_id": f"L2-{section_num.replace('.', '-')}",
                    "parent_node_id": f"L1-{chapter_num}",
                    "node_name": f"{section_num} {section.get('title', '')}",
                    "node_level": 2,
                    "node_content": "",
                    "content_blocks": [],
                    "node_type": "original",
                    "key_points": section.get("key_points", []),
                    "knowledge_structure": section.get("knowledge_structure", []),
                    "reused_knowledge_names": section.get("reused_knowledge_names", []),
                    "learning_objective": section.get("learning_objective", ""),
                    "prerequisite_node_ids": section.get("prerequisite_node_ids", []),
                    "misconceptions": section.get("misconceptions", []),
                    "assessment": section.get("assessment", []),
                    "scope_boundary": section.get("scope_boundary", ""),
                    "evidence_refs": section.get("evidence_refs", []),
                    "grounding_contract": section.get("grounding_contract", {}),
                    "grounding_annotations": [],
                    "examples_plan": section.get("examples_plan", []),
                    "exercise_plan": section.get("exercise_plan", []),
                    "module_plan": section.get("module_plan", []),
                    "difficulty_contract": section.get("difficulty_contract", {}),
                    "generation_status": "pending",
                    "generated_chars": 0,
                    "error_summary": None,
                })

        return nodes

    # ------------------------------------------------------------------
    # 节点内容生成
    # ------------------------------------------------------------------

    async def generate_node_content_stream(
        self,
        course_id: str,
        node: dict,
        config: NodeGenerationConfig,
        on_chunk: Callable[[str], Awaitable[None]],
        course_data: dict[str, Any] | None = None,
        existing_draft: str = "",
    ) -> str:
        """Stream one node from the persisted blueprint and module plan."""
        node_id: str = node.get("node_id", "")
        node_name: str = node.get("node_name", "")
        persisted = {
            **self._course_generation_artifacts.get(course_id, {}),
            **dict(course_data or {}),
        }
        if not persisted:
            persisted = {
                "course_id": course_id,
                "course_name": node_name,
                **self._course_generation_artifacts.get(course_id, {}),
            }
        pedagogy = coerce_persisted_profile(persisted)
        ensure_course_difficulty_contracts(
            persisted,
            primary_mode=pedagogy.primary_mode,
            secondary_mode=pedagogy.secondary_mode,
        )
        if not node.get("module_plan") or not node.get("difficulty_contract"):
            blueprint_node = self._find_persisted_blueprint_node(persisted, node)
            if blueprint_node:
                node.update({key: value for key, value in blueprint_node.items() if key not in node or not node.get(key)})

        context = self._build_persisted_generation_context(persisted, node)
        if config.custom_instruction:
            context += f"\n\n## 用户自定义指令\n{config.custom_instruction}"
        user_prompt, system_prompt = self._prompt_composer.build_content_prompt(
            course_data=persisted,
            node=node,
            context=context,
            existing_draft=existing_draft,
        )

        continuation = ""
        async for chunk in self._stream_llm(
            prompt=user_prompt,
            system_prompt=system_prompt,
        ):
            normalized = chunk.strip()
            if normalized.startswith("[Error:") or normalized == "AI Service not configured.":
                raise AIProviderRequestError(normalized)
            continuation += chunk
            await on_chunk(chunk)

        full_content = existing_draft + continuation
        if not full_content:
            raise RuntimeError(f"节点 {node_name} 没有生成任何正文")

        raw_content = self.clean_response_text(full_content)
        grounding_contract = node.get("grounding_contract") or {}
        allowed_ids = set(grounding_contract.get("required_evidence_ids") or []) | set(
            grounding_contract.get("optional_evidence_ids") or []
        )
        full_content, annotations, invalid_refs = extract_grounding_annotations(
            raw_content,
            allowed_ids,
        )
        node["grounding_annotations"] = annotations
        node["grounding_invalid_refs"] = invalid_refs
        quality = evaluate_node_content(full_content, node)
        node["generation_quality"] = quality
        node["needs_manual_review"] = any(
            item.get("severity") == "critical"
            for item in quality.get("issues") or []
        )

        self._record_generation_quality(
            output_type="node_content_stream",
            output_text=full_content,
            context_text=context,
            source="course_service.generate_node_content_stream",
            course_id=course_id,
            node_id=node_id,
            node_name=node_name,
            require_markdown_structure=True,
        )

        return full_content

    async def repair_course_coherence(
        self,
        course_data: dict[str, Any],
        report: dict[str, Any] | None = None,
        *,
        max_repairs: int = 2,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Repair blocking cross-section issues without broad course rewrites."""
        working = deepcopy(course_data)
        current_report = report or evaluate_course_coherence(working)
        repairable = [
            item for item in current_report.get("blocking_issues") or []
            if item.get("repairable") and item.get("node_id")
        ][:max_repairs]
        for issue in repairable:
            node_id = str(issue.get("node_id") or "")
            node = next(
                (item for item in working.get("nodes") or [] if item.get("node_id") == node_id),
                None,
            )
            if not node:
                continue
            repair_issue = {
                **issue,
                "suggestion": _coherence_repair_suggestion(issue),
            }
            repair_user, repair_system = self._prompt_composer.build_repair_prompt(
                course_data=working,
                node=node,
                content=str(node.get("node_content") or ""),
                issues=[repair_issue],
            )
            repaired = await self._call_llm(
                repair_user,
                repair_system,
                enable_thinking=True,
            )
            if not repaired:
                continue
            repaired_raw = self.clean_response_text(repaired)
            grounding_contract = node.get("grounding_contract") or {}
            allowed_ids = set(grounding_contract.get("required_evidence_ids") or []) | set(
                grounding_contract.get("optional_evidence_ids") or []
            )
            repaired_content, annotations, invalid_refs = extract_grounding_annotations(
                repaired_raw,
                allowed_ids,
            )
            candidate = deepcopy(working)
            candidate_node = next(
                item for item in candidate.get("nodes") or [] if item.get("node_id") == node_id
            )
            candidate_node["content_blocks"] = []
            set_node_content_blocks(candidate_node, repaired_content)
            candidate_node["grounding_annotations"] = annotations
            candidate_node["grounding_invalid_refs"] = invalid_refs
            candidate_node["generation_quality"] = evaluate_node_content(
                str(candidate_node.get("node_content") or ""),
                candidate_node,
            )
            if not candidate_node["generation_quality"].get("passed"):
                continue
            candidate_report = evaluate_course_coherence(candidate)
            target_remains = any(
                item.get("code") == issue.get("code")
                and item.get("node_id") == node_id
                for item in candidate_report.get("blocking_issues") or []
            )
            if target_remains or int(candidate_report.get("blocking_count") or 0) >= int(
                current_report.get("blocking_count") or 0
            ):
                continue
            working = candidate
            current_report = candidate_report

        working["course_coherence_contract"] = compile_course_coherence_contract(working)
        working["course_coherence_quality_report"] = current_report
        return working, current_report

    @staticmethod
    def _find_persisted_blueprint_node(
        course_data: dict[str, Any], node: dict[str, Any]
    ) -> dict[str, Any]:
        node_id = str(node.get("node_id") or "")
        node_name = str(node.get("node_name") or "")
        for item in (course_data.get("course_blueprint") or {}).get("nodes", []):
            section_number = str(item.get("section_number") or "")
            if item.get("node_id") == node_id or (section_number and section_number in node_name):
                return item
        return {}

    @staticmethod
    def _build_persisted_generation_context(
        course_data: dict[str, Any], node: dict[str, Any]
    ) -> str:
        material_context = build_node_generation_context(course_metadata=course_data, node=node)
        preceding: list[str] = []
        for item in course_data.get("nodes", []):
            if item.get("node_id") == node.get("node_id"):
                break
            content = str(item.get("node_content") or "").strip()
            if item.get("node_level") == 2 and content:
                preceding.append(f"- {item.get('node_name', '')}：{summarize_text(content, 260)}")
        prior_context = "\n".join(preceding[-4:]) or "- 当前节点没有已完成前置正文。"
        return "\n\n".join([
            material_context,
            "## 已完成前置节点摘要\n" + prior_context,
        ])

    def _course_profile(self, course_id: str) -> SubjectPedagogyProfile:
        return coerce_persisted_profile(
            self._course_generation_artifacts.get(course_id) or {}
        )

    def _pedagogy_contract(self, course_id: str, node: dict[str, Any]) -> str:
        metadata = self._course_generation_artifacts.get(course_id) or {}
        profile = coerce_persisted_profile(metadata)
        module_plan = node.get("module_plan") or []
        if not module_plan:
            blueprint_node = self._find_persisted_blueprint_node(metadata, node)
            module_plan = blueprint_node.get("module_plan") or []
        module_lines = [
            f"- {item.get('label') or item.get('module_id')}：{item.get('output_contract') or item.get('prompt_instruction') or ''}"
            for item in module_plan
        ]
        secondary = (
            f"，辅助模式 {profile.secondary_mode.value}"
            if profile.secondary_mode else ""
        )
        return "\n".join([
            f"- 主教学模式：{profile.primary_mode.value}{secondary}",
            "- 当前节点必须履行的教学模块：",
            *(module_lines or ["  - 沿用原文结构和当前小节契约"]),
        ])

    # ------------------------------------------------------------------
    # 局部内容操作
    # ------------------------------------------------------------------

    async def redefine_content(
        self,
        *,
        course_id: str,
        node: dict[str, Any],
        requirement: str,
        original_content: str = "",
        course_context: str = "",
        previous_context: str = "",
        difficulty: Any = None,
        style: Any = None,
        user_id: str = DEFAULT_USER_ID,
    ) -> str:
        """Rewrite a full node using the production course context chain."""
        prompt = self._build_redefine_prompt(
            course_id=course_id,
            node=node,
            requirement=requirement,
            original_content=original_content,
            course_context=course_context,
            previous_context=previous_context,
            difficulty=difficulty,
            style=style,
            user_id=user_id,
        )
        response = await self._call_llm(
            f"请重写「{node.get('node_name', '当前小节')}」。",
            prompt,
            enable_thinking=True,
        )
        text = self.clean_response_text(response) if response else original_content
        text = strip_leading_heading(text, str(node.get("node_name") or ""))
        self._record_generation_quality(
            output_type="node_rewrite",
            output_text=text,
            context_text=prompt,
            source="course_service.redefine_content",
            course_id=course_id,
            node_id=str(node.get("node_id") or ""),
            node_name=str(node.get("node_name") or ""),
            require_markdown_structure=True,
        )
        return text

    async def rewrite_selection(
        self,
        *,
        course_id: str,
        node: dict[str, Any],
        selected_text: str,
        node_content: str = "",
        heading_path: list[str] | None = None,
        before_context: str = "",
        after_context: str = "",
        user_requirement: str = "",
        action_type: str = "rewrite",
        course_context: str = "",
        previous_context: str = "",
        user_id: str = DEFAULT_USER_ID,
    ) -> dict[str, Any]:
        """Generate a replacement candidate for a Markdown text selection.

        The caller owns confirmation and persistence. This keeps Markdown as
        the source of truth and avoids rebuilding the document into backend
        content blocks.
        """
        node_id = str(node.get("node_id", ""))
        heading_path = [str(item).strip() for item in (heading_path or []) if str(item).strip()]
        requirement = user_requirement.strip() or self._default_selection_requirement(action_type)
        ledger = self._ledger_context(course_id, node_id) or course_context
        pedagogy_contract = self._pedagogy_contract(course_id, node)
        ai_learning_context = self._ai_learning_context_prompt(
            course_id=course_id,
            node_id=node_id,
            node_name=str(node.get("node_name") or ""),
            question=requirement,
            request_context=ledger,
            user_id=user_id,
            use_case=classify_generation_use_case(
                requirement=requirement,
                action_type=action_type,
                default=PERSONALIZED_NODE_EXPLANATION,
            ),
        )
        action_instruction = self._selection_action_instruction(action_type)
        prompt = f"""你正在修改一篇课程 Markdown 讲义中的选中文字。

## 课程上下文账本
{ledger or "无额外账本。"}

## 前文上下文
{previous_context or "无"}

## AI Learning Context
{ai_learning_context}

## 当前小节契约
{self._node_contract_text(node)}

## 当前教学结构契约
{pedagogy_contract}

## 当前标题路径
{" > ".join(heading_path) if heading_path else "未定位到标题路径"}

## 选区前文
{before_context or "无"}

## 需要替换的选中文字
{selected_text}

## 选区后文
{after_context or "无"}

## 用户要求
{requirement}

## 动作类型
{action_type}: {action_instruction}

## 输出要求
1. 只输出用于替换选区的 Markdown 片段，不输出解释说明。
2. 不要输出整篇正文，不要重复选区前后文。
3. 保持原课程的学科章法和标题层级，不得套用跨学科固定模板。
4. 若需要补例子或练习，只补在当前选区应替换的位置，避免改写整节结构。
5. 不编造论文、链接、年份、机构报告或不存在的术语。
6. 尽量保留原文中的术语、公式、代码标识和必要 Markdown 格式。"""

        response = await self._call_llm("请生成选区替换文本。", prompt)
        replacement = self.clean_response_text(response) if response else selected_text
        replacement = self._strip_replacement_wrapper(replacement, selected_text)
        self._record_generation_quality(
            output_type="selection_rewrite",
            output_text=replacement,
            context_text=prompt,
            source="course_service.rewrite_selection",
            course_id=course_id,
            node_id=node_id,
            node_name=str(node.get("node_name") or ""),
            metadata={
                "action_type": action_type,
                "heading_path": heading_path,
                "selected_chars": len(selected_text),
            },
            min_chars=10,
        )
        return {
            "replacement_text": replacement,
            "selected_text": selected_text,
            "action_type": action_type,
            "heading_path": heading_path,
            "context_summary": summarize_text("\n".join([before_context, selected_text, after_context]), limit=360),
        }

    async def regenerate_content_block(
        self,
        *,
        course_id: str,
        node: dict[str, Any],
        block_id: str,
        requirement: str = "",
        action_type: str = "rewrite",
        user_id: str = DEFAULT_USER_ID,
    ) -> dict[str, Any]:
        """Regenerate one legacy content block without making blocks the main path."""
        node_id = str(node.get("node_id") or "")
        blocks = normalize_blocks(node_id, node.get("content_blocks"), node.get("node_content", ""))
        target = next((block for block in blocks if block.get("block_id") == block_id), None)
        if not target:
            raise ValueError("Content block not found")

        block_title = str(target.get("title") or "内容块")
        block_type = str(target.get("type") or "custom")
        original_content = str(target.get("content") or "")
        requirement = requirement.strip() or self._default_selection_requirement(action_type)
        ledger = self._ledger_context(course_id, node_id)
        ai_learning_context = self._ai_learning_context_prompt(
            course_id=course_id,
            node_id=node_id,
            node_name=str(node.get("node_name") or ""),
            question=requirement,
            request_context=ledger,
            user_id=user_id,
            use_case=classify_generation_use_case(
                requirement=requirement,
                block_type=block_type,
                action_type=action_type,
                default=PERSONALIZED_NODE_EXPLANATION,
            ),
        )
        action_instruction = self._selection_action_instruction(action_type)
        prompt = f"""你正在改写一个旧版课程内容块。注意：content_blocks 只是兼容层，新课程正文仍以完整 Markdown 为准。

## 课程上下文账本
{ledger or "无额外账本。"}

## AI Learning Context
{ai_learning_context}

## 当前小节契约
{self._node_contract_text(node)}

## 目标内容块
- block_id：{block_id}
- 标题：{block_title}
- 类型：{block_type}

## 原内容
{original_content}

## 用户要求
{requirement}

## 动作类型
{action_type}: {action_instruction}

## 输出要求
1. 只输出该内容块的新 Markdown 正文，不输出整节内容。
2. 不要重复内容块标题，前端会根据 block title 重建 Markdown。
3. 内容必须服务当前小节契约、课程账本和学习者薄弱点，不得扩散成课程结构变更。
4. 不编造论文、链接、年份、机构报告或不存在的术语。"""

        response = await self._call_llm(f"请改写内容块「{block_title}」。", prompt)
        content = self.clean_response_text(response) if response else original_content
        content = strip_leading_heading(content, block_title)
        updated = {
            **target,
            "content": content,
            "summary": summarize_text(content),
            "status": "final",
        }
        self._record_generation_quality(
            output_type="content_block",
            output_text=content,
            context_text=prompt,
            source="course_service.regenerate_content_block",
            course_id=course_id,
            node_id=node_id,
            node_name=str(node.get("node_name") or ""),
            metadata={
                "block_id": block_id,
                "block_type": block_type,
                "action_type": action_type,
            },
        )
        return updated

    async def analyze_section_growth_scenario(
        self,
        *,
        course_id: str,
        document_title: str,
        section: dict[str, Any],
        active_blocks: list[dict[str, Any]],
        instruction: str,
        knowledge_context: str,
        evidence_context: list[dict[str, Any]],
        available_sources: list[dict[str, Any]],
        user_id: str = DEFAULT_USER_ID,
    ) -> dict[str, Any] | None:
        """Understand a learner's growth request without choosing or mutating blocks."""
        del course_id, user_id
        system_prompt = f"""你是课程生长 Workflow 里的一个轻量场景判断节点，不是自主执行 Agent。

你的唯一职责，是理解学习者希望当前小节怎样生长。你不能决定 block_id、INSERT/REPLACE、
应用范围、版本、确认结果，也不能直接生成或修改课程正文；这些由后续确定性流程完成。

## 当前课程位置
- 课程：{document_title}
- 小节：{section.get('title') or section.get('section_id') or '未命名'}
- 学习目标：{section.get('learning_objective') or '未单独声明'}

## 当前真实教学块
{active_blocks}

## 本节知识契约
{knowledge_context}

## 当前学习证据
{evidence_context or '无额外学习证据'}

## 已绑定且可作为事实依据的资料
{available_sources or '无已绑定资料'}

## 学习者要求
{instruction}

只输出一个 JSON 对象，字段必须完整：
{{
  "scene_summary": "用一句人话说明学习者真正想改变什么",
  "rationale": "说明为什么判断为这些教学作用和难度变化",
  "requested_roles": ["reasoning|application|example|checkpoint|concept"],
  "growth_direction": "challenge|remediation|author_directed",
  "difficulty_delta": {{
    "reasoning_depth": -2到2整数,
    "transfer_distance": -2到2整数,
    "task_complexity": -2到2整数,
    "learner_support": -2到2整数
  }},
  "source_requirement": "course_only|verified_materials|verified_current_sources",
  "source_reason": "说明资料要求"
}}

判断规则：
1. 只选真正需要变化的教学作用，不要输出未知 role。
2. “最新、前沿、近期、当前行业、真实行业现状”等时效事实必须选择 verified_current_sources。
3. 需要引用用户资料但不要求时效时选择 verified_materials；仅在本节知识契约内调整则选择 course_only。
4. 不得输出任何 block_id、动作类型、范围、确认或写入指令。"""
        response = await self._call_llm(
            "判断这次小节生长请求的场景，并返回结构化 JSON。",
            system_prompt,
            use_fast_model=True,
            retry_count=1,
            enable_thinking=False,
            raise_on_failure=False,
        )
        parsed = self._extract_json(str(response or ""))
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _section_growth_scene_context(scene_analysis: dict[str, Any] | None) -> str:
        if not scene_analysis:
            return "未提供额外场景判断；按用户原始要求和课程契约生成。"
        source_requirement = str(scene_analysis.get("source_requirement") or "course_only")
        source_status = str(scene_analysis.get("source_status") or "course_grounded")
        source_guard = (
            "当前没有完成时效资料核验。不得把模型记忆写成最新、前沿或当前行业事实；"
            "只能生成不依赖时效事实的教学框架，并明确资料边界。"
            if source_status == "verification_required"
            else "只能使用当前课程知识契约和已绑定资料中的事实。"
        )
        return (
            f"- 场景理解：{scene_analysis.get('scene_summary') or '按用户要求调整'}\n"
            f"- 判断理由：{scene_analysis.get('rationale') or '无额外说明'}\n"
            f"- 生长方向：{scene_analysis.get('growth_direction') or 'author_directed'}\n"
            f"- 资料要求：{source_requirement}（{source_status}）\n"
            f"- 资料边界：{source_guard}"
        )

    async def generate_course_block_candidate(
        self,
        *,
        course_id: str,
        document_title: str,
        section: dict[str, Any],
        target_block: dict[str, Any],
        previous_block: dict[str, Any] | None,
        next_block: dict[str, Any] | None,
        instruction: str,
        action_type: str = "rewrite",
        scene_analysis: dict[str, Any] | None = None,
        quality_feedback: list[str] | None = None,
        user_id: str = DEFAULT_USER_ID,
    ) -> str:
        """Generate one canonical block candidate without mutating the course."""
        block_id = str(target_block.get("block_id") or "")
        section_id = str(target_block.get("section_id") or "")
        payload = target_block.get("payload") if isinstance(target_block.get("payload"), dict) else {}
        block_title = str(payload.get("title") or "内容块")
        original_content = str(payload.get("markdown") or payload.get("text") or "")
        role = str(target_block.get("role") or "concept")
        kind = str(target_block.get("kind") or "rich_text")
        ledger = self._ledger_context(course_id, section_id)
        ai_learning_context = self._ai_learning_context_prompt(
            course_id=course_id,
            node_id=section_id,
            node_name=str(section.get("title") or ""),
            question=instruction,
            request_context=ledger,
            user_id=user_id,
            use_case=classify_generation_use_case(
                requirement=instruction,
                block_type=role,
                action_type=action_type,
                default=PERSONALIZED_NODE_EXPLANATION,
            ),
        )
        action_instruction = self._selection_action_instruction(action_type)
        feedback_text = "\n".join(f"- {item}" for item in quality_feedback or []) or "无，这是首次生成。"

        def neighbor_text(label: str, value: dict[str, Any] | None) -> str:
            if not value:
                return f"- {label}：无"
            return (
                f"- {label}：{value.get('title') or value.get('role') or '相邻内容'}\n"
                f"  {value.get('content_summary') or ''}"
            )

        prompt = f"""你正在为正式课程文档生成一个可供用户确认的局部候选块。你不能修改课程结构，也不能输出整节课程。

## 课程与章节
- 课程：{document_title}
- 章节：{section.get('title') or section_id}
- 学习目标：{section.get('learning_objective') or '未单独声明'}

## 不可改变的块契约
- block_id：{block_id}
- 内容形式 kind：{kind}
- 教学作用 role：{role}
- 标题：{block_title}
- 课程知识引用：{', '.join(target_block.get('concept_refs') or []) or '无'}
- 目标引用：{', '.join(target_block.get('objective_refs') or []) or '无'}
- 证据引用：{', '.join(target_block.get('evidence_refs') or []) or '无'}

## 相邻上下文
{neighbor_text('前一块', previous_block)}
{neighbor_text('后一块', next_block)}

## 课程上下文账本
{ledger or '无额外账本。'}

## AI Learning Context
{ai_learning_context}

## 当前块正文
{original_content}

## 用户要求
{instruction}

## 场景判断与资料边界
{self._section_growth_scene_context(scene_analysis)}

## 动作类型
{action_type}: {action_instruction}

## 上次质量反馈
{feedback_text}

## 输出要求
1. 只输出用于替换当前块正文的 Markdown，不输出标题、解释、前后文或确认话术。
2. 保持当前 kind、role、章节范围和正式引用，不重排课程，不创建新的块。
3. 与前后块自然衔接，避免重复相邻内容；用户未要求时不要改变术语、公式、代码标识和结论。
4. 原文含公式或代码时保留其语义与有效 Markdown 围栏。
5. 不编造来源、论文、链接、年份、数据或不存在的术语。
6. 必须对用户要求作出实质改进，不能原样返回原文。"""

        response = await self._call_llm(f"请生成课程块「{block_title}」的改进候选。", prompt)
        content = self.clean_response_text(response) if response else original_content
        content = strip_leading_heading(content, block_title)
        self._record_generation_quality(
            output_type="canonical_course_block_candidate",
            output_text=content,
            context_text=prompt,
            source="course_service.generate_course_block_candidate",
            course_id=course_id,
            node_id=section_id,
            node_name=str(section.get("title") or ""),
            metadata={
                "block_id": block_id,
                "kind": kind,
                "role": role,
                "action_type": action_type,
                "is_quality_retry": bool(quality_feedback),
            },
            min_chars=12,
        )
        return content

    async def generate_new_course_block_candidate(
        self,
        *,
        course_id: str,
        document_title: str,
        section: dict[str, Any],
        desired_role: str,
        instruction: str,
        previous_block: dict[str, Any] | None,
        next_block: dict[str, Any] | None,
        knowledge_context: str,
        difficulty_delta: dict[str, Any],
        scene_analysis: dict[str, Any] | None = None,
        quality_feedback: list[str] | None = None,
        user_id: str = DEFAULT_USER_ID,
    ) -> str:
        """Generate one missing teaching-role block from the section contract."""
        section_id = str(section.get("section_id") or "")
        role_label = {
            "reasoning": "理论推导",
            "application": "实战应用",
            "example": "例子讲解",
            "checkpoint": "理解检查",
            "concept": "核心概念",
        }.get(desired_role, desired_role)
        ledger = self._ledger_context(course_id, section_id)
        ai_learning_context = self._ai_learning_context_prompt(
            course_id=course_id,
            node_id=section_id,
            node_name=str(section.get("title") or ""),
            question=instruction,
            request_context=ledger,
            user_id=user_id,
            use_case=classify_generation_use_case(
                requirement=instruction,
                block_type=desired_role,
                action_type="expand",
                default=PERSONALIZED_NODE_EXPLANATION,
            ),
        )
        feedback_text = "\n".join(
            f"- {item}" for item in quality_feedback or []
        ) or "无，这是首次生成。"

        def neighbor_text(label: str, value: dict[str, Any] | None) -> str:
            if not value:
                return f"- {label}：无"
            return (
                f"- {label}：{value.get('title') or value.get('role') or '相邻内容'}\n"
                f"  {value.get('content_summary') or ''}"
            )

        prompt = f"""你正在为正式课程文档补齐一个缺失的教学块。当前任务只生成一个“{role_label}”块，不得输出整节课程。

## 课程与小节
- 课程：{document_title}
- 小节：{section.get('title') or section_id}
- 学习目标：{section.get('learning_objective') or '未单独声明'}

## 本节课程知识契约
{knowledge_context or course_knowledge_base_prompt_context({}, section_id)}

## 相邻上下文
{neighbor_text('前一块', previous_block)}
{neighbor_text('后一块', next_block)}

## 课程上下文账本
{ledger or '无额外账本。'}

## AI Learning Context
{ai_learning_context}

## 用户要求
{instruction}

## 场景判断与资料边界
{self._section_growth_scene_context(scene_analysis)}

## 本次难度变化
{difficulty_delta}

## 上次质量反馈
{feedback_text}

## 输出要求
1. 只输出“{role_label}”块的 Markdown 正文，不输出标题、确认话术或整节内容。
2. 所有概念、术语、边界和能力要求必须来自上面的本节课程知识契约，不得另造知识点。
3. 必须真正承担“{role_label}”的教学作用，并与相邻块自然衔接，避免重复。
4. 如果是理论推导，要补足条件、关键步骤和结论之间的因果；如果是实战应用，要给出可迁移的真实任务、决策过程和结果判断。
5. 难度提高不等于堆术语或加篇幅，要提高推理深度、任务复杂度或迁移距离。
6. 不编造来源、论文、链接、年份、数据或不存在的术语。"""
        response = await self._call_llm(
            f"请生成课程小节“{section.get('title') or section_id}”的{role_label}块。",
            prompt,
        )
        content = self.clean_response_text(response) if response else ""
        content = strip_leading_heading(content, role_label)
        self._record_generation_quality(
            output_type="canonical_course_new_block_candidate",
            output_text=content,
            context_text=prompt,
            source="course_service.generate_new_course_block_candidate",
            course_id=course_id,
            node_id=section_id,
            node_name=str(section.get("title") or ""),
            metadata={
                "desired_role": desired_role,
                "difficulty_delta": difficulty_delta,
                "is_quality_retry": bool(quality_feedback),
            },
            min_chars=12,
        )
        return content

    @staticmethod
    def _default_selection_requirement(action_type: str) -> str:
        return {
            "simplify": "把选中文字讲得更清楚、更易懂，但不要降低关键概念准确性。",
            "example": "为选中文字补充一个贴合当前上下文的例子。",
            "exercise": "把选中文字改写成适合当前知识点的小练习或自测提示。",
            "ask": "围绕选中文字给出可直接替换到讲义中的解释。",
            "expand": "在不离题的前提下扩展选中文字。",
            "rewrite": "提升选中文字的表达质量和教学清晰度。",
        }.get(action_type, "提升选中文字的表达质量和教学清晰度。")

    @staticmethod
    def _selection_action_instruction(action_type: str) -> str:
        return {
            "simplify": "降低阅读负担，拆开含混句子，保留必要术语。",
            "example": "增加具体例子，例子应服务当前概念而不是另起话题。",
            "exercise": "生成可练习、可判断的题目或思考任务，必要时附简短提示。",
            "ask": "回答用户对选区的疑问，但输出仍必须是可替换的正文片段。",
            "expand": "补足推理、背景、例子或应用，避免重复前后文。",
            "rewrite": "重写表达，使其更准确、顺畅、有教学递进。",
        }.get(action_type, "重写表达，使其更准确、顺畅、有教学递进。")

    @staticmethod
    def _strip_replacement_wrapper(text: str, selected_text: str) -> str:
        cleaned = text.strip()
        labels = (
            "替换文本：",
            "修改后：",
            "改写后：",
            "答案：",
        )
        for label in labels:
            if cleaned.startswith(label):
                cleaned = cleaned[len(label):].strip()
                break
        if cleaned.startswith("```") and cleaned.endswith("```"):
            lines = cleaned.splitlines()
            if len(lines) >= 3:
                cleaned = "\n".join(lines[1:-1]).strip()
        return cleaned or selected_text

    async def redefine_node_content_stream(
        self,
        *,
        course_id: str,
        node: dict[str, Any],
        requirement: str,
        original_content: str = "",
        course_context: str = "",
        previous_context: str = "",
        difficulty: Any = None,
        style: Any = None,
        user_id: str = DEFAULT_USER_ID,
    ):
        """Stream a full-node rewrite while using the same prompt as non-stream."""
        prompt = self._build_redefine_prompt(
            course_id=course_id,
            node=node,
            requirement=requirement,
            original_content=original_content,
            course_context=course_context,
            previous_context=previous_context,
            difficulty=difficulty,
            style=style,
            user_id=user_id,
        )
        async for chunk in self._stream_llm(
            prompt=f"请重写「{node.get('node_name', '当前小节')}」。",
            system_prompt=prompt,
            enable_thinking=True,
        ):
            yield chunk

    async def extend_content(
        self,
        *,
        course_id: str,
        node: dict[str, Any],
        requirement: str,
        current_content: str = "",
        user_id: str = DEFAULT_USER_ID,
    ) -> str:
        """Generate an extension that stays aligned with the course ledger."""
        node_id = str(node.get("node_id", ""))
        ledger = self._ledger_context(course_id, node_id)
        ai_learning_context = self._ai_learning_context_prompt(
            course_id=course_id,
            node_id=node_id,
            node_name=str(node.get("node_name") or ""),
            question=requirement,
            request_context=ledger,
            user_id=user_id,
            use_case=classify_generation_use_case(
                requirement=requirement,
                default=PERSONALIZED_NODE_EXPLANATION,
            ),
        )
        prompt = f"""你正在为自学课程补充一段延伸内容。

## 课程上下文
{ledger or "无额外账本。"}

## AI Learning Context
{ai_learning_context}

## 当前节点
{self._node_contract_text(node)}

## 当前正文摘要
{summarize_text(current_content or node.get("node_content", ""))}

## 用户希望扩展的方向
{requirement}

## 输出要求
1. 只输出一段可追加到当前节点的 Markdown 内容。
2. 不重复当前正文已有内容。
3. 优先补推理、例子、应用步骤或自测题。
4. 不编造论文、链接、年份、机构报告或伪概念。"""
        response = await self._call_llm(f"请扩展「{node.get('node_name', '当前小节')}」。", prompt)
        text = self.clean_response_text(response) if response else ""
        self._record_generation_quality(
            output_type="node_extension",
            output_text=text,
            context_text=prompt,
            source="course_service.extend_content",
            course_id=course_id,
            node_id=node_id,
            node_name=str(node.get("node_name") or ""),
        )
        return text

    async def summarize_content(
        self,
        node_content: str,
        node_name: str = "",
        user_persona: str | None = None,
        *,
        course_id: str = "",
        node_id: str = "",
        user_id: str = DEFAULT_USER_ID,
    ) -> str:
        """Summarize content with optional learner context."""
        ai_learning_context = self._ai_learning_context_prompt(
            course_id=course_id or None,
            node_id=node_id or None,
            node_name=node_name,
            question="总结当前节点内容",
            request_context=summarize_text(node_content),
            request_persona=user_persona or "",
            user_id=user_id,
            use_case=PERSONALIZED_NODE_EXPLANATION,
        )
        prompt = f"""请为学习者总结以下课程内容。

## 节点
{node_name or "当前内容"}

## AI Learning Context
{ai_learning_context}

## 内容
{node_content[:4000]}

## 输出要求
1. 使用 Markdown。
2. 分成「核心概念」「推理链条」「易错点」「自测提醒」四部分。
3. 简洁但具体，不要写空泛套话。"""
        response = await self._call_llm("请总结课程内容。", prompt)
        text = self.clean_response_text(response) if response else f"### {node_name} 总结\n\n暂无可总结内容。"
        self._record_generation_quality(
            output_type="node_summary",
            output_text=text,
            context_text=prompt,
            source="course_service.summarize_content",
            course_id=course_id or None,
            node_id=node_id or None,
            node_name=node_name,
            min_chars=40,
        )
        return text

    def locate_node(self, keyword: str, all_nodes: list[dict[str, Any]]) -> dict[str, str]:
        """Locate the best matching node with a deterministic local search."""
        normalized = (keyword or "").strip().lower()
        if not normalized:
            return {}

        for node in all_nodes:
            name = str(node.get("node_name", ""))
            if normalized in name.lower():
                return {"match_node_id": node["node_id"], "match_node_name": name}

        for node in all_nodes:
            content = str(node.get("node_content", ""))
            if normalized in content.lower():
                return {"match_node_id": node["node_id"], "match_node_name": node.get("node_name", "")}

        return {}

    def _build_redefine_prompt(
        self,
        *,
        course_id: str,
        node: dict[str, Any],
        requirement: str,
        original_content: str = "",
        course_context: str = "",
        previous_context: str = "",
        difficulty: Any = None,
        style: Any = None,
        user_id: str = DEFAULT_USER_ID,
    ) -> str:
        node_id = str(node.get("node_id", ""))
        style_text = getattr(style, "value", style) or "academic"
        ledger = self._ledger_context(course_id, node_id)
        pedagogy_contract = self._pedagogy_contract(course_id, node)
        metadata = self._course_generation_artifacts.get(course_id) or {}
        pedagogy = coerce_persisted_profile(metadata)
        persisted_node = self._find_persisted_blueprint_node(metadata, node)
        difficulty_contract = (
            node.get("difficulty_contract")
            or persisted_node.get("difficulty_contract")
            or {}
        )
        requested_difficulty = getattr(difficulty, "value", difficulty)
        if requested_difficulty:
            override_profile = compile_difficulty_profile(
                requested_difficulty,
                primary_mode=pedagogy.primary_mode,
                secondary_mode=pedagogy.secondary_mode,
            )
            override_adaptation = decide_adaptation(
                assess_readiness(override_profile),
            )
            override_curve = compile_course_difficulty_curve(
                profile=override_profile,
                nodes=[node],
                adaptation=override_adaptation,
            ).to_dict()
            override_contract = dict(override_curve["node_contracts"][0])
            override_contract.pop("node_id", None)
            override_contract.pop("section_number", None)
            if difficulty_contract.get("node_role"):
                override_contract["node_role"] = difficulty_contract["node_role"]
            difficulty_contract = override_contract
        ai_learning_context = self._ai_learning_context_prompt(
            course_id=course_id,
            node_id=node_id,
            node_name=str(node.get("node_name") or ""),
            question=requirement,
            request_context=ledger or course_context,
            user_id=user_id,
            use_case=classify_generation_use_case(
                requirement=requirement,
                default=PERSONALIZED_NODE_EXPLANATION,
            ),
        )
        return f"""你正在重写一门自学课程的完整小节。

## 课程上下文账本
{ledger or course_context or "无额外账本。"}

## 前文上下文
{previous_context or "无"}

## AI Learning Context
{ai_learning_context}

## 当前小节契约
{self._node_contract_text(node)}

## 原始正文
{original_content or node.get("node_content", "") or "无"}

## 用户重写要求
{requirement or "提升教学质量"}

## 难度契约与风格
{format_node_difficulty_contract(difficulty_contract)}
- 风格：{style_text}

## 输出要求
1. 输出完整小节正文，不输出解释说明。
2. 保持课程蓝图约束，不能跑题或跳过本节边界。
3. 优先沿用原正文结构，并履行以下教学结构契约：
{pedagogy_contract}
4. 不得把本节强行改写成“引入问题 / 核心概念 / 推理过程 / 例子讲解 / 应用场景 / 自测练习 / 小结”的跨学科通用模板。
5. 避免与前文重复，承接已学内容。
6. 不编造论文、链接、年份、机构报告或不存在的术语。"""

    def _ledger_context(self, course_id: str, node_id: str) -> str:
        try:
            return self._context_manager.get_generation_context(course_id, node_id).get("ledger_context", "")
        except Exception:
            return ""

    def _ai_learning_context_prompt(
        self,
        *,
        course_id: str | None,
        node_id: str | None,
        node_name: str = "",
        question: str = "",
        request_context: str = "",
        request_persona: str = "",
        user_id: str = DEFAULT_USER_ID,
        use_case: str = PERSONALIZED_NODE_EXPLANATION,
    ) -> str:
        context = build_ai_learning_context(
            user_id=user_id,
            course_id=course_id,
            node_id=node_id,
            node_name=node_name,
            question=question,
            request_context=request_context,
            request_persona=request_persona,
        )
        if (
            use_case == PERSONALIZED_NODE_EXPLANATION
            and self._context_requests_remediation(context)
        ):
            use_case = WEAKNESS_REMEDIATION_CONTENT
        strategy_prompt = build_course_generation_strategy_prompt(
            use_case,
            ai_learning_context=context,
        )
        return strategy_prompt + "\n\n" + context.to_prompt()

    @staticmethod
    def _context_requests_remediation(context: Any) -> bool:
        data = context.to_dict() if hasattr(context, "to_dict") else dict(context)
        decision = data.get("teaching_guidance") or {}
        return bool(
            decision.get("needs_weakness_practice")
            or decision.get("recommends_review")
            or decision.get("should_review")
        )

    def _record_generation_quality(
        self,
        *,
        output_type: str,
        output_text: str,
        context_text: str,
        source: str,
        course_id: str | None,
        node_id: str | None,
        node_name: str,
        metadata: dict[str, Any] | None = None,
        min_chars: int = 80,
        require_markdown_structure: bool = False,
    ) -> None:
        try:
            assessment = assess_ai_output(
                output_type=output_type,
                output_text=output_text,
                context_text=context_text,
                min_chars=min_chars,
                require_markdown_structure=require_markdown_structure,
            )
            if not assessment.passed:
                logger.warning(
                    "AI output quality check failed source=%s course_id=%s node_id=%s issues=%s metadata=%s",
                    source,
                    course_id,
                    node_id,
                    assessment.issues,
                    metadata or {},
                )
        except Exception:
            logger.debug("Could not assess AI output quality", exc_info=True)

    @staticmethod
    def _node_contract_text(node: dict[str, Any]) -> str:
        parts = [
            f"- 小节：{node.get('node_name', '')}",
            f"- 学习目标：{node.get('learning_objective', '')}",
            f"- 范围边界：{node.get('scope_boundary', '')}",
            "- 关键点：" + "；".join(node.get("key_points", []) or []),
            "- 误区：" + "；".join(node.get("misconceptions", []) or []),
            "- 验收标准：" + "；".join(node.get("assessment", []) or []),
        ]
        return "\n".join(part for part in parts if part and not part.endswith("："))

    # ------------------------------------------------------------------
    # 子节点生成
    # ------------------------------------------------------------------

    async def generate_sub_nodes(
        self,
        node_name: str,
        node_level: int,
        node_id: str,
        course_name: str = "",
        **kwargs: Any,
    ) -> list[dict]:
        """生成子节点。

        Args:
            node_name: 父节点名称
            node_level: 父节点层级
            node_id: 父节点 ID
            course_name: 课程名称
            **kwargs: 额外参数

        Returns:
            子节点字典列表
        """
        chapter_num = self._extract_chapter_number(node_name)
        course_id = str(kwargs.get("course_id") or "")
        metadata = self._course_generation_artifacts.get(course_id) or {}
        profile = self._course_profile(course_id)
        difficulty_profile = compile_difficulty_profile(
            metadata.get("difficulty") or kwargs.get("difficulty") or "intermediate",
            primary_mode=profile.primary_mode,
            secondary_mode=profile.secondary_mode,
        )
        material_context = ""
        if course_id:
            material_context = build_node_generation_context(
                course_metadata=self._course_generation_artifacts.get(course_id),
                node={
                    "node_id": node_id,
                    "node_name": node_name,
                    "node_level": node_level,
                },
            )
        prompt = f"""## 任务
为「{node_name}」设计小节结构。

## 所属课程
{course_name or "未命名课程"}

{material_context}

## 课程难度能力契约
{format_difficulty_profile(difficulty_profile.to_dict())}

## 知识身份边界
本次生成只建立当前课程自己的知识蓝图，不读取、复用或输出其他课程的知识 ID。

## 知识边界
1. `knowledge_structure` 是当前课程自己的知识蓝图，不是小节标题索引。
2. 每个概念组至少拆出两个原子知识点；知识点必须有独立命题、条件或边界、可观察能力和掌握标准。
3. 所有知识名称与关系只在当前课程内去重和复用，不得跨课程继承身份。
4. 不生成提升点；易错点没有可靠内容时允许为空，禁止模板填充。

## 输出格式
```json
[
  {{
    "section_number": "{chapter_num}.1",
    "title": "小节名",
    "key_points": ["要点"],
    "knowledge_structure": [
      {{
        "concept_group": "知识问题域，不得复制小节标题",
        "description": "主题作用与边界",
        "knowledge_points": [
          {{
            "name": "可独立解释和检测的细知识点",
            "statement": "独立知识命题或操作规则",
            "knowledge_type": "definition",
            "conditions": ["成立条件或适用域"],
            "boundaries": ["不适用范围或易混边界"],
            "capability_points": [{{"name": "能力名称", "observable_behavior": "可观察动作"}}],
            "misconceptions": [],
            "mastery_criteria": [{{
              "name": "掌握标准",
              "observable_performance": "独立可验证表现",
              "required_independence": "independent",
              "required_transfer": "variation",
              "verification_method": "验证方法"
            }}],
            "aliases": [],
            "entry_reason": "只有入口知识填写",
            "prerequisite_names": [],
            "relations": []
          }}
        ]
      }}
    ],
    "reused_knowledge_names": [],
    "learning_objective": "学完本节后学习者能完成的具体任务",
    "prerequisite_node_ids": [],
    "misconceptions": ["本节需要澄清的常见误区"],
    "assessment": ["可检验本节是否掌握的标准或题目方向"],
    "scope_boundary": "本节讲到哪里为止"
  }}
]
```"""

        response = await self._call_llm(f"请为「{node_name}」设计小节。", prompt)
        data = self._extract_json(response) if response else None
        items = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
        items = [item for item in items if isinstance(item, dict)]
        if not items:
            items = [
                {"section_number": f"{chapter_num}.1", "title": "基础概念"},
                {"section_number": f"{chapter_num}.2", "title": "核心原理"},
                {"section_number": f"{chapter_num}.3", "title": "实践应用"},
            ]

        mini_plan = attach_module_plans_to_plan(
            {"chapters": [{"sections": items}]},
            profile,
        )
        attach_difficulty_contracts_to_plan(
            mini_plan,
            profile=difficulty_profile,
            adaptation=decide_adaptation(assess_readiness(difficulty_profile)),
        )
        planned_items = mini_plan["chapters"][0]["sections"]
        result: list[dict[str, Any]] = []
        for item in planned_items:
            normalize_knowledge_structure(item)
            section = item.get("section_number", f"{chapter_num}.{len(result) + 1}")
            result.append({
                "node_id": str(uuid.uuid4()),
                "parent_node_id": node_id,
                "node_name": f"{section} {item.get('title', '小节')}",
                "node_level": node_level + 1,
                "node_content": "",
                "content_blocks": [],
                "node_type": "custom",
                "key_points": item.get("key_points", []),
                "knowledge_structure": item.get("knowledge_structure", []),
                "reused_knowledge_names": item.get("reused_knowledge_names", []),
                "learning_objective": item.get("learning_objective", ""),
                "prerequisite_node_ids": item.get("prerequisite_node_ids", []),
                "misconceptions": item.get("misconceptions", []),
                "assessment": item.get("assessment", []),
                "scope_boundary": item.get("scope_boundary", ""),
                "module_plan": item.get("module_plan", []),
                "difficulty_contract": item.get("difficulty_contract", {}),
                "generation_status": "pending",
                "generated_chars": 0,
                "error_summary": None,
            })
        return result


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

_course_service: CourseService | None = None


def get_course_service() -> CourseService:
    """获取 CourseService 单例。

    使用默认依赖创建实例。生产环境中建议通过 FastAPI 依赖注入替代。

    Returns:
        CourseService 实例
    """
    global _course_service
    if _course_service is None:
        _course_service = CourseService()
    return _course_service
