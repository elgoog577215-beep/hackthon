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
import contextlib
import inspect
import logging
import os
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
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
from course_generation_adaptive import (
    PromptCandidate,
    clip_text,
    compile_fallback_node_content,
    compile_fallback_teaching_batch,
    compile_fallback_teaching_skeleton,
    merge_teaching_skeleton_part,
    prompt_detail_levels_for_source,
    select_budgeted_prompt,
)
from course_generation_budget import (
    CourseGenerationBudget,
    CourseGenerationDeadlineExceeded,
)
from course_generation_strategy import (
    PERSONALIZED_NODE_EXPLANATION,
    WEAKNESS_REMEDIATION_CONTENT,
    build_course_generation_strategy_prompt,
    classify_generation_use_case,
)
from course_generation_workflow import (
    PIPELINE_VERSION,
    _resolve_course_shape_constraints,
    apply_course_teaching_plan,
    attach_difficulty_artifacts,
    attach_generation_artifacts_to_plan,
    attach_pedagogy_profile,
    build_course_blueprint_from_plan,
    build_course_generation_artifacts,
    build_course_knowledge_scope_contract,
    build_node_generation_context,
    build_outline_generation_context,
    build_section_knowledge_skeleton_evidence_hints,
    compile_course_teaching_plan_modules,
    normalize_course_outline_contract,
    normalize_course_plan_contract,
    validate_course_outline_constraints,
    validate_course_plan_constraints,
    validate_course_teaching_plan,
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
from course_outline_planning import (
    CourseOutlinePlanningBudget,
    assemble_course_outline,
    build_outline_batch_specs,
    compile_fallback_outline_batch,
    normalize_outline_batch,
    normalize_outline_skeleton,
    outline_neighbor_chapters,
    outline_request_fingerprint,
    select_chapter_evidence_hints,
    validate_outline_batch,
    validate_outline_skeleton,
)
from course_pedagogy import (
    SubjectPedagogyProfile,
    attach_module_plans_to_plan,
    coerce_persisted_profile,
    resolve_pedagogy_profile,
)
from course_planning_budget import (
    CoursePlanningBudget,
    build_compact_planning_context,
    build_teaching_plan_batches,
    estimate_json_tokens,
    select_batch_knowledge_registry,
)
from course_prompt_composer import (
    PROMPT_CONTRACT_VERSION,
    CoursePromptComposer,
    get_course_prompt_composer,
)
from course_quality import evaluate_node_content, validate_blueprint
from course_teaching_plan_v3 import (
    assemble_course_teaching_plan_v3,
    normalize_teaching_plan_batch_v3,
    normalize_teaching_plan_skeleton_v3,
    promote_course_teaching_plan_v3,
    validate_teaching_plan_batch_v3,
    validate_teaching_plan_skeleton_v3,
)
from course_teaching_guidance import compile_overall_teaching_guidance
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
        generation_budget: CourseGenerationBudget | None = None,
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
        self._generation_budget = (
            generation_budget or CourseGenerationBudget.from_env()
        )
        self._outline_budget = CourseOutlinePlanningBudget.from_env()
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
            "generation_runtime_budget",
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
        generation_mode: str = "review_blueprint",
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
            "course_generation_v10",
            "course_generation_v11",
            "course_generation_v12",
            "course_generation_v13",
            "course_generation_v14",
            "course_generation_v15",
            "course_generation_v16",
        }
        if checkpoint_ready:
            refreshed_brief = deepcopy(existing.get("course_generation_brief") or {})
            refreshed_brief["course_shape_constraints"] = (
                _resolve_course_shape_constraints(requirements)
            )
            refreshed_brief["course_purpose"] = course_purpose
            artifacts = {
                "pipeline_version": PIPELINE_VERSION,
                "material_cards": existing.get("material_cards") or [],
                "course_generation_brief": refreshed_brief,
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
                course_purpose=course_purpose,
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
                profile = resolve_pedagogy_profile(
                    subject=topic,
                    requirements=requirements,
                    materials=artifacts.get("material_cards") or material_inputs,
                    requested_mode=pedagogy_mode,
                    requested_secondary_mode=secondary_mode,
                    requested_intensity=secondary_intensity,
                )
            attach_pedagogy_profile(artifacts, profile)

        artifacts["course_composition_profile"] = composition_profile
        artifacts["generation_runtime_budget"] = {
            **self._generation_budget.to_dict(),
            "outline_batch_max_sections": (
                self._outline_budget.batch_max_sections
            ),
            "outline_inactivity_timeout_seconds": (
                self._outline_budget.batch_timeout_seconds
            ),
            "outline_concurrency": self._planning_concurrency,
            "teaching_plan_max_input_tokens": (
                self._teaching_plan_budget.max_input_tokens
            ),
            "teaching_plan_max_output_tokens": (
                self._teaching_plan_budget.max_output_tokens
            ),
            "teaching_plan_concurrency": (
                self._teaching_plan_budget.concurrency
            ),
            "teaching_plan_inactivity_timeout_seconds": (
                self._teaching_plan_budget.batch_timeout_seconds
            ),
        }

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
            "generation_runtime_budget": artifacts[
                "generation_runtime_budget"
            ],
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

        existing_outline_stage = (
            (existing.get("generation_stage_artifacts") or {}).get("outline")
            or {}
        )
        outline_model_call_count = int(
            existing_outline_stage.get("model_call_count") or 0
        )
        outline_prompt_chars = int(
            existing_outline_stage.get("prompt_chars") or 0
        )
        outline_prompt_tokens = int(
            existing_outline_stage.get("max_prompt_tokens") or 0
        )
        outline_detail_levels = list(
            existing_outline_stage.get("prompt_detail_levels") or []
        )
        outline_was_generated = not plan_constraint_report.get("passed")
        outline_stage_uses_complete_pipeline = (
            existing_outline_stage.get("strategy")
            == "hierarchical_chapter_batches"
        )
        if (
            plan is not None
            and plan_constraint_report.get("passed")
            and not outline_stage_uses_complete_pipeline
        ):
            # V16 removes both course-level compact paths. Old compact
            # checkpoints are intentionally invalidated so resuming or
            # reopening a course cannot preserve a six-section fast-path
            # outline as if it came from the complete pipeline.
            plan = None
            plan_constraint_report = validate_course_outline_constraints(
                {},
                artifacts["course_generation_brief"],
            )
            outline_was_generated = True

        if not plan_constraint_report.get("passed") or plan is None:
            (
                plan,
                plan_constraint_report,
                existing_outline_stage,
            ) = await self._generate_hierarchical_course_outline(
                topic=topic,
                audience=audience,
                artifacts=artifacts,
                profile=profile,
                difficulty_profile=difficulty_profile.to_dict(),
                gap_assessment=gap_assessment.to_dict(),
                adaptation_decision=adaptation_decision.to_dict(),
                existing_stage=existing_outline_stage,
                existing_generation_stages=(
                    existing.get("generation_stage_artifacts") or {}
                ),
                on_phase=on_phase,
                on_checkpoint=on_checkpoint,
            )
            outline_model_call_count = int(
                existing_outline_stage.get("model_call_count") or 0
            )
            outline_prompt_chars = int(
                existing_outline_stage.get("prompt_chars") or 0
            )
            outline_prompt_tokens = int(
                existing_outline_stage.get("max_prompt_tokens") or 0
            )
            outline_detail_levels = list(
                existing_outline_stage.get("prompt_detail_levels") or []
            )
        if not plan_constraint_report.get("passed") or plan is None:
            messages = "；".join(
                str(item.get("message") or "未知目录错误")
                for item in plan_constraint_report.get("issues") or []
            )
            raise AIProviderRequestError(
                f"完整课程目录未通过结构验收：{messages or '无法解析完整 JSON'}"
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
            "generation_runtime_budget": deepcopy(
                artifacts["generation_runtime_budget"]
            ),
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
                    **deepcopy(existing_outline_stage),
                    "status": (
                        "completed_with_warnings"
                        if existing_outline_stage.get("fallback_units")
                        else "completed"
                    ),
                    "schema_version": "course_outline_v1",
                    "actual": deepcopy(plan_constraint_report.get("actual") or {}),
                    "prompt_chars": outline_prompt_chars,
                    "max_prompt_tokens": outline_prompt_tokens,
                    "prompt_detail_levels": outline_detail_levels,
                    "adaptive_compaction_count": sum(
                        level != "full"
                        for level in outline_detail_levels
                    ),
                    "max_input_tokens": (
                        self._generation_budget.max_input_tokens
                    ),
                    "max_input_chars": (
                        self._generation_budget.max_input_chars
                    ),
                    "max_output_tokens": (
                        self._generation_budget.outline_max_output_tokens
                    ),
                    "provider_max_attempts": (
                        self._generation_budget.provider_max_attempts
                    ),
                    "inactivity_timeout_seconds": (
                        self._generation_budget.call_timeout_seconds
                    ),
                    "model_call_count": outline_model_call_count,
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
            "schema_version": (
                course_data.get("course_teaching_plan") or {}
            ).get("schema_version"),
            "revision_id": (
                course_data.get("course_teaching_plan") or {}
            ).get("revision_id"),
            "knowledge_revision_id": course_knowledge_base.get(
                "revision_id"
            ),
            "compiled_from": "official_course_teaching_plan",
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
        semantic_retry_count: int = 0,
    ) -> dict[str, Any]:
        """Build one official plan through the complete 1-N-1 path."""
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
        teaching_stage["runtime_budget"] = {
            "max_input_tokens": (
                self._teaching_plan_budget.max_input_tokens
            ),
            "max_input_chars": (
                self._generation_budget.max_input_chars
            ),
            "max_output_tokens": (
                self._teaching_plan_budget.max_output_tokens
            ),
            "provider_max_attempts": (
                self._generation_budget.provider_max_attempts
            ),
            "inactivity_timeout_seconds": (
                self._teaching_plan_budget.batch_timeout_seconds
            ),
            "completion_policy": "all_units_settled",
            "max_concurrency": self._teaching_plan_budget.concurrency,
        }

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
        if (
            existing_report.get("passed")
            and teaching_stage.get("semantic_status") != "retry_required"
            and not teaching_stage.get("degraded")
            and teaching_stage.get("strategy") != "compact_single_call"
        ):
            official_plan = promote_course_teaching_plan_v3(
                existing_plan,
                outline_revision_id=outline_revision_id,
            )
            official_plan = compile_course_teaching_plan_modules(
                official_plan,
                sections=sections,
            )
            official_report = validate_course_teaching_plan(
                official_plan,
                sections=sections,
                expected_outline_revision_id=outline_revision_id,
            )
            planned_course = apply_course_teaching_plan(plan, official_plan)
            teaching_stage.update({
                "status": "completed",
                "semantic_status": "ai_complete",
                "schema_version": official_plan.get("schema_version"),
                "revision_id": official_plan.get("revision_id"),
                "source_outline_revision_id": outline_revision_id,
                "validation_report": deepcopy(official_report),
                "strategy": str(
                    teaching_stage.get("strategy") or "restored_official_plan"
                ),
                "model_call_count": 0,
                "resumed": True,
            })
            course_data.update({
                "course_teaching_plan": official_plan,
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
        overall_teaching_guidance = compile_overall_teaching_guidance(
            course_data,
            plan=plan,
        )
        planning_mode = "hierarchical"
        strategy = "adaptive_skeleton_batches"
        started_at = time.monotonic()
        previous_duration_ms = int(
            teaching_stage.get("duration_ms") or 0
        )
        counter = {
            "calls": int(teaching_stage.get("model_call_count") or 0),
            "prompt_chars": int(teaching_stage.get("prompt_chars") or 0),
            "prompt_tokens": int(
                teaching_stage.get("prompt_tokens") or 0
            ),
            "max_prompt_tokens": int(
                teaching_stage.get("max_prompt_tokens") or 0
            ),
        }
        prompt_detail_levels: list[str] = list(
            teaching_stage.get("prompt_detail_levels") or []
        )
        previous_fallback_units = list(
            teaching_stage.get("fallback_units") or []
        )
        # A retry starts with a clean degradation ledger. Successfully frozen
        # model batches are reused below; local semantic fallbacks are retried.
        fallback_units: list[dict[str, Any]] = []
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
            input_tokens = self.estimate_request_tokens(
                user_prompt,
                system_prompt,
            )
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
                        max_input_tokens=(
                            self._teaching_plan_budget.max_input_tokens
                        ),
                        max_input_chars=(
                            self._generation_budget.max_input_chars
                        ),
                        max_output_tokens=(
                            self._teaching_plan_budget.max_output_tokens
                        ),
                        max_attempts=(
                            self._generation_budget.provider_max_attempts
                        ),
                    )
            finally:
                async with counter_lock:
                    counter["calls"] += 1
                    counter["prompt_chars"] += (
                        len(user_prompt) + len(system_prompt)
                    )
                    counter["prompt_tokens"] += input_tokens
                    counter["max_prompt_tokens"] = max(
                        counter["max_prompt_tokens"],
                        input_tokens,
                    )
                    teaching_stage.update({
                        "model_call_count": counter["calls"],
                        "prompt_chars": counter["prompt_chars"],
                        "prompt_tokens": counter["prompt_tokens"],
                        "max_prompt_tokens": (
                            counter["max_prompt_tokens"]
                        ),
                    })

        async def generate_chunked_skeleton(
        ) -> tuple[dict[str, Any], dict[str, Any], int]:
            """Freeze large-course identities in bounded sequential shards."""
            chunk_size = self._teaching_plan_budget.skeleton_max_sections
            chunks = [
                planning_sections[index:index + chunk_size]
                for index in range(0, len(planning_sections), chunk_size)
            ]
            accumulated: dict[str, Any] = {
                "schema_version": "course_teaching_plan_skeleton_v3",
                "source_outline_revision_id": outline_revision_id,
                "knowledge_registry": [],
                "sections": [],
            }
            processed_sections: list[dict[str, Any]] = []
            resumed_chunk_count = 0
            checkpoint_chunk_count = int(
                teaching_stage.get("completed_skeleton_chunk_count") or 0
            )
            checkpoint_skeleton = teaching_stage.get("skeleton")
            if (
                checkpoint_chunk_count > 0
                and checkpoint_chunk_count < len(chunks)
                and isinstance(checkpoint_skeleton, dict)
                and checkpoint_skeleton.get("source_outline_revision_id")
                == outline_revision_id
            ):
                checkpoint_section_count = sum(
                    len(chunk)
                    for chunk in chunks[:checkpoint_chunk_count]
                )
                checkpoint_sections = planning_sections[
                    :checkpoint_section_count
                ]
                normalized_checkpoint = (
                    normalize_teaching_plan_skeleton_v3(
                        checkpoint_skeleton,
                        outline_revision_id=outline_revision_id,
                    )
                )
                checkpoint_ids = [
                    str(item.get("node_id") or "")
                    for item in normalized_checkpoint.get("sections") or []
                ]
                expected_ids = [
                    str(item.get("node_id") or "")
                    for item in checkpoint_sections
                ]
                checkpoint_report = validate_teaching_plan_skeleton_v3(
                    normalized_checkpoint,
                    sections=checkpoint_sections,
                )
                if (
                    checkpoint_ids == expected_ids
                    and checkpoint_report.get("passed")
                ):
                    accumulated = normalized_checkpoint
                    processed_sections = list(checkpoint_sections)
                    resumed_chunk_count = checkpoint_chunk_count
            for chunk_index, chunk_sections in enumerate(chunks, start=1):
                if chunk_index <= resumed_chunk_count:
                    continue
                chunk_context = build_compact_planning_context(
                    chunk_sections,
                    composition_style=str(
                        (
                            course_data.get("course_composition_profile")
                            or {}
                        ).get("style")
                        or ""
                    ),
                )
                prior_registry = list(
                    accumulated.get("knowledge_registry") or []
                )
                chunk_context["new_knowledge_key_start"] = (
                    len(prior_registry) + 1
                )
                if prior_registry:
                    direct_prerequisite_nodes = {
                        str(node_id)
                        for item in chunk_sections
                        for node_id in (
                            item.get("prerequisite_node_ids") or []
                        )
                    }
                    direct = [
                        item
                        for item in prior_registry
                        if str(item.get("owner_node_id") or "")
                        in direct_prerequisite_nodes
                    ]
                    recent = prior_registry[-32:]
                    prior_by_key = {
                        str(item.get("knowledge_key") or ""): item
                        for item in [*direct, *recent]
                    }
                    chunk_context["prior_knowledge_registry"] = list(
                        prior_by_key.values()
                    )
                chunk_levels = prompt_detail_levels_for_source(
                    {
                        "course_title": course_title,
                        "positioning": positioning,
                        "learning_objectives": (
                            plan.get("learning_objectives") or []
                        ),
                        "planning_context": chunk_context,
                    },
                    max_input_chars=(
                        self._generation_budget.max_input_chars
                    ),
                )
                prompts = {
                    detail_level: (
                        self._prompt_composer
                        .build_teaching_plan_skeleton_v3_prompt(
                            course_title=course_title,
                            positioning=positioning,
                            learning_objectives=list(
                                plan.get("learning_objectives") or []
                            ),
                            planning_context=chunk_context,
                            detail_level=detail_level,
                        )
                    )
                    for detail_level in chunk_levels
                }
                user_prompt = (
                    "规划全课知识职责骨架 V3 分片 "
                    f"{chunk_index}/{len(chunks)}，只输出 JSON。"
                )
                selected = select_budgeted_prompt(
                    (
                        PromptCandidate(
                            detail_level=detail_level,
                            user_prompt=user_prompt,
                            system_prompt=prompts[detail_level],
                        )
                        for detail_level in chunk_levels
                    ),
                    max_input_chars=self._generation_budget.max_input_chars,
                    max_input_tokens=self._teaching_plan_budget.max_input_tokens,
                    token_estimator=self.estimate_request_tokens,
                )
                failure_reason = ""
                part: dict[str, Any] = {}
                if selected is not None:
                    prompt_detail_levels.append(selected.detail_level)
                    await self._notify_phase(
                        on_phase,
                        "course_teaching_plan_skeleton",
                        35 + int(3 * (chunk_index - 1) / max(1, len(chunks))),
                        (
                            "正在冻结全课知识职责分片 "
                            f"{chunk_index}/{len(chunks)}"
                        ),
                        phase_progress=int(
                            100 * (chunk_index - 1) / max(1, len(chunks))
                        ),
                        phase_detail={
                            "artifact_type": "course_teaching_plan_skeleton",
                            "chunk_index": chunk_index,
                            "chunk_count": len(chunks),
                            "completed_sections": len(processed_sections),
                            "total_sections": len(planning_sections),
                        },
                    )
                    try:
                        response = await request_model(
                            user_prompt=selected.user_prompt,
                            system_prompt=selected.system_prompt,
                            enable_thinking=False,
                            phase="course_teaching_plan_skeleton",
                            progress=35,
                            heartbeat_message=(
                                "仍在等待 AI 冻结知识职责分片 "
                                f"{chunk_index}/{len(chunks)}"
                            ),
                            phase_detail={
                                "artifact_type": (
                                    "course_teaching_plan_skeleton"
                                ),
                                "chunk_index": chunk_index,
                                "chunk_count": len(chunks),
                            },
                        )
                    except (
                        AIProviderRequestError,
                        CourseGenerationDeadlineExceeded,
                    ) as exc:
                        response = ""
                        failure_reason = (
                            f"provider_error:{type(exc).__name__}"
                        )
                    parsed = self._extract_json(response) if response else None
                    part = normalize_teaching_plan_skeleton_v3(
                        parsed if isinstance(parsed, dict) else {},
                        outline_revision_id=outline_revision_id,
                    )
                else:
                    failure_reason = "chunk_prompt_did_not_fit"

                candidate = merge_teaching_skeleton_part(
                    accumulated,
                    part,
                    outline_revision_id=outline_revision_id,
                )
                candidate_sections = [*processed_sections, *chunk_sections]
                candidate_report = validate_teaching_plan_skeleton_v3(
                    candidate,
                    sections=candidate_sections,
                )
                if (
                    not candidate_report.get("passed")
                    and not failure_reason
                ):
                    correction_user = (
                        "只修复知识职责骨架分片 "
                        f"{chunk_index}/{len(chunks)}，输出完整 JSON。"
                    )
                    correction = select_budgeted_prompt(
                        (
                            PromptCandidate(
                                detail_level=detail_level,
                                user_prompt=correction_user,
                                system_prompt=(
                                    self._prompt_composer
                                    .build_teaching_plan_skeleton_v3_correction_prompt(
                                        original_prompt=prompts[detail_level],
                                        issues=(
                                            candidate_report.get(
                                                "blocking_issues"
                                            )
                                            or []
                                        ),
                                    )
                                ),
                            )
                            for detail_level in chunk_levels
                        ),
                        max_input_chars=(
                            self._generation_budget.max_input_chars
                        ),
                        max_input_tokens=(
                            self._teaching_plan_budget.max_input_tokens
                        ),
                        token_estimator=self.estimate_request_tokens,
                    )
                    if correction is not None:
                        prompt_detail_levels.append(
                            correction.detail_level
                        )
                        try:
                            corrected = await request_model(
                                user_prompt=correction.user_prompt,
                                system_prompt=correction.system_prompt,
                                enable_thinking=False,
                                phase=(
                                    "course_teaching_plan_skeleton_validation"
                                ),
                                progress=38,
                                heartbeat_message=(
                                    "仍在等待 AI 修复知识职责分片 "
                                    f"{chunk_index}/{len(chunks)}"
                                ),
                                phase_detail={
                                    "artifact_type": (
                                        "course_teaching_plan_skeleton"
                                    ),
                                    "chunk_index": chunk_index,
                                    "chunk_count": len(chunks),
                                },
                            )
                        except (
                            AIProviderRequestError,
                            CourseGenerationDeadlineExceeded,
                        ) as exc:
                            corrected = ""
                            failure_reason = (
                                "correction_provider_error:"
                                f"{type(exc).__name__}"
                            )
                        parsed = (
                            self._extract_json(corrected)
                            if corrected else None
                        )
                        part = normalize_teaching_plan_skeleton_v3(
                            parsed if isinstance(parsed, dict) else {},
                            outline_revision_id=outline_revision_id,
                        )
                        candidate = merge_teaching_skeleton_part(
                            accumulated,
                            part,
                            outline_revision_id=outline_revision_id,
                        )
                        candidate_report = validate_teaching_plan_skeleton_v3(
                            candidate,
                            sections=candidate_sections,
                        )
                    else:
                        failure_reason = "chunk_correction_did_not_fit"

                if not candidate_report.get("passed"):
                    accumulated = compile_fallback_teaching_skeleton(
                        chunk_sections,
                        outline_revision_id=outline_revision_id,
                        prior_skeleton=accumulated,
                    )
                    fallback_units.append({
                        "unit": f"skeleton_chunk_{chunk_index}",
                        "reason": (
                            failure_reason
                            or "model_output_failed_validation"
                        ),
                        "section_ids": [
                            str(item.get("node_id") or "")
                            for item in chunk_sections
                        ],
                    })
                else:
                    accumulated = candidate
                processed_sections.extend(chunk_sections)
                current_report = validate_teaching_plan_skeleton_v3(
                    accumulated,
                    sections=processed_sections,
                )
                if not current_report.get("passed"):
                    raise AIProviderRequestError(
                        "本地知识骨架分片汇编失败；这是生成编排器错误"
                    )
                course_data["course_teaching_plan_skeleton"] = deepcopy(
                    accumulated
                )
                teaching_stage.update({
                    "status": "in_progress",
                    "skeleton": deepcopy(accumulated),
                    "skeleton_revision_id": accumulated.get("revision_id"),
                    "skeleton_chunk_count": len(chunks),
                    "completed_skeleton_chunk_count": chunk_index,
                    "completed_skeleton_section_count": len(
                        processed_sections
                    ),
                    "resumed_skeleton_chunk_count": resumed_chunk_count,
                    "prompt_detail_levels": list(prompt_detail_levels),
                    "fallback_units": deepcopy(fallback_units),
                })
                await self._notify_checkpoint(on_checkpoint, course_data)
            final_report = validate_teaching_plan_skeleton_v3(
                accumulated,
                sections=planning_sections,
            )
            return accumulated, final_report, len(chunks)

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
            and not any(
                str(item.get("unit") or "").startswith("skeleton_chunk_")
                for item in previous_fallback_units
                if isinstance(item, dict)
            )
        )
        if not skeleton_is_current:
            (
                skeleton,
                skeleton_report,
                skeleton_chunk_count,
            ) = await generate_chunked_skeleton()
            skeleton_is_current = bool(skeleton_report.get("passed"))
            teaching_stage.update({
                "skeleton_chunk_count": skeleton_chunk_count,
                "completed_skeleton_chunk_count": (
                    skeleton_chunk_count if skeleton_is_current else 0
                ),
                "skeleton_strategy": "bounded_sequential_chunks",
            })
        if not skeleton_is_current:
            raise AIProviderRequestError(
                "有界知识职责骨架汇编失败；这是生成编排器错误"
            )

        course_data["course_teaching_plan_skeleton"] = skeleton
        compact_by_id = {
            str(item.get("node_id") or ""): item
            for item in planning_context.get("sections") or []
            if isinstance(item, dict)
        }
        identity_by_id = {
            str(item.get("node_id") or ""): item
            for item in skeleton.get("sections") or []
            if isinstance(item, dict)
        }
        module_catalog = list(
            planning_context.get("module_catalog") or []
        )

        def build_batch_prompt_options(
            spec: dict[str, Any],
        ) -> tuple[Any, dict[str, str]]:
            batch_id = str(spec.get("batch_id") or "")
            section_ids = list(spec.get("section_ids") or [])
            user_prompt = (
                f"生成详细小节教案批次 {batch_id}，只输出 JSON。"
            )
            batch_levels = prompt_detail_levels_for_source(
                {
                    "course_title": course_title,
                    "positioning": positioning,
                    "batch_spec": spec,
                    "batch_sections": [
                        compact_by_id[item] for item in section_ids
                    ],
                    "knowledge_registry": select_batch_knowledge_registry(
                        skeleton,
                        section_ids,
                    ),
                    "section_identities": [
                        identity_by_id[item] for item in section_ids
                    ],
                    "module_catalog": module_catalog,
                    "overall_guidance": overall_teaching_guidance,
                },
                max_input_chars=self._generation_budget.max_input_chars,
            )
            prompts = {
                detail_level: (
                    self._prompt_composer
                    .build_teaching_plan_batch_v3_prompt(
                        course_title=course_title,
                        positioning=positioning,
                        batch_spec=spec,
                        batch_sections=[
                            compact_by_id[item]
                            for item in section_ids
                        ],
                        knowledge_registry=(
                            select_batch_knowledge_registry(
                                skeleton,
                                section_ids,
                            )
                        ),
                        section_identities=[
                            identity_by_id[item]
                            for item in section_ids
                        ],
                        module_catalog=module_catalog,
                        skeleton_revision_id=str(
                            skeleton.get("revision_id") or ""
                        ),
                        overall_guidance=overall_teaching_guidance,
                        detail_level=detail_level,
                    )
                )
                for detail_level in batch_levels
            }
            selected = select_budgeted_prompt(
                (
                    PromptCandidate(
                        detail_level=detail_level,
                        user_prompt=user_prompt,
                        system_prompt=prompts[detail_level],
                    )
                    for detail_level in batch_levels
                ),
                max_input_chars=self._generation_budget.max_input_chars,
                max_input_tokens=self._teaching_plan_budget.max_input_tokens,
                token_estimator=self.estimate_request_tokens,
            )
            return selected, prompts

        initial_batch_specs = build_teaching_plan_batches(
            list(planning_context.get("sections") or []),
            skeleton,
            self._teaching_plan_budget,
        )
        adaptive_specs: list[dict[str, Any]] = []

        def add_fitted_spec(spec: dict[str, Any]) -> None:
            section_ids = list(spec.get("section_ids") or [])
            selected, _prompts = build_batch_prompt_options(spec)
            if selected is None and len(section_ids) > 1:
                midpoint = max(1, len(section_ids) // 2)
                for split_ids in (
                    section_ids[:midpoint],
                    section_ids[midpoint:],
                ):
                    identities = [identity_by_id[item] for item in split_ids]
                    knowledge_count = sum(
                        len(item.get("owned_knowledge_keys") or [])
                        for item in identities
                    )
                    add_fitted_spec({
                        "batch_id": str(spec.get("batch_id") or ""),
                        "section_ids": split_ids,
                        "knowledge_count": knowledge_count,
                        "estimated_input_tokens": estimate_json_tokens({
                            "sections": [
                                compact_by_id[item]
                                for item in split_ids
                            ],
                            "section_identities": identities,
                            "knowledge_registry": (
                                select_batch_knowledge_registry(
                                    skeleton,
                                    split_ids,
                                )
                            ),
                        }) + 1400,
                        "estimated_output_tokens": (
                            len(split_ids) * 400
                            + knowledge_count * 650
                        ),
                        "split_from_final_payload": True,
                    })
                return
            fitted = deepcopy(spec)
            fitted["preflight_detail_level"] = (
                selected.detail_level if selected is not None else "local"
            )
            fitted["force_local_fallback"] = selected is None
            adaptive_specs.append(fitted)

        for initial_spec in initial_batch_specs:
            add_fitted_spec(initial_spec)
        batch_specs = []
        for index, spec in enumerate(adaptive_specs, start=1):
            normalized_spec = deepcopy(spec)
            normalized_spec["batch_id"] = f"TP-B{index:02d}"
            batch_specs.append(normalized_spec)
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
                and stored.get("generation_source") == "model"
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
            "prompt_detail_levels": list(prompt_detail_levels),
            "adaptive_compaction_count": sum(
                level != "full" for level in prompt_detail_levels
            ),
            "fallback_units": deepcopy(fallback_units),
            "final_payload_split_count": sum(
                bool(spec.get("split_from_final_payload"))
                for spec in batch_specs
            ),
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
            selected_batch_prompt, batch_prompts = (
                build_batch_prompt_options(spec)
            )
            previous = stored_batches.get(batch_id)
            attempt_count = int(
                (previous or {}).get("attempt_count", 0)
                if isinstance(previous, dict) else 0
            )
            try:
                async with state_lock:
                    completed_before = len(results)
                fallback_reason = ""
                generation_source = "model"
                batch: dict[str, Any] = {}
                batch_report: dict[str, Any] = {"passed": False}
                if (
                    selected_batch_prompt is None
                    or spec.get("force_local_fallback")
                ):
                    fallback_reason = "final_prompt_did_not_fit"
                else:
                    prompt_detail_levels.append(
                        selected_batch_prompt.detail_level
                    )
                    await self._notify_phase(
                        on_phase,
                        "course_teaching_plan_batch",
                        39 + int(
                            7 * completed_before / max(1, len(batch_specs))
                        ),
                        f"正在生成第 {int(batch_id[-2:])} 批详细教案（已完成 {completed_before}/{len(batch_specs)} 批）",
                        phase_progress=int(
                            100 * completed_before / max(1, len(batch_specs))
                        ),
                        phase_detail={
                            "artifact_type": "course_teaching_plan_batch",
                            "batch_id": batch_id,
                            "completed_batches": completed_before,
                            "total_batches": len(batch_specs),
                            "completed_sections": teaching_stage.get(
                                "completed_section_count", 0
                            ),
                            "total_sections": len(sections),
                        },
                    )
                    attempt_count += 1
                    try:
                        response = await request_model(
                            user_prompt=selected_batch_prompt.user_prompt,
                            system_prompt=selected_batch_prompt.system_prompt,
                            enable_thinking=False,
                            phase="course_teaching_plan_batch",
                            progress=40,
                            heartbeat_message=(
                                f"仍在等待 AI 完成教案批次 {batch_id}"
                            ),
                            phase_detail=batch_progress_detail,
                        )
                    except (
                        AIProviderRequestError,
                        CourseGenerationDeadlineExceeded,
                    ) as exc:
                        response = ""
                        fallback_reason = (
                            f"provider_error:{type(exc).__name__}"
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
                    if (
                        not batch_report.get("passed")
                        and not fallback_reason
                    ):
                        correction_user = (
                            f"只修复详细教案批次 {batch_id}，输出完整 JSON。"
                        )
                        selected_correction = select_budgeted_prompt(
                            (
                                PromptCandidate(
                                    detail_level=detail_level,
                                    user_prompt=correction_user,
                                    system_prompt=(
                                        self._prompt_composer
                                        .build_teaching_plan_batch_v3_correction_prompt(
                                            original_prompt=batch_prompts[
                                                detail_level
                                            ],
                                            issues=(
                                                batch_report.get(
                                                    "blocking_issues"
                                                )
                                                or []
                                            ),
                                        )
                                    ),
                                )
                                for detail_level in batch_prompts
                            ),
                            max_input_chars=(
                                self._generation_budget.max_input_chars
                            ),
                            max_input_tokens=(
                                self._teaching_plan_budget.max_input_tokens
                            ),
                            token_estimator=self.estimate_request_tokens,
                        )
                        if selected_correction is None:
                            fallback_reason = (
                                "correction_prompt_did_not_fit"
                            )
                        else:
                            prompt_detail_levels.append(
                                selected_correction.detail_level
                            )
                            attempt_count += 1
                            await self._notify_phase(
                                on_phase,
                                "course_teaching_plan_batch_validation",
                                44,
                                f"正在请求 AI 修复教案批次 {batch_id}",
                                phase_progress=0,
                                phase_detail={
                                    **batch_progress_detail,
                                    "batch_id": batch_id,
                                },
                            )
                            try:
                                corrected = await request_model(
                                    user_prompt=(
                                        selected_correction.user_prompt
                                    ),
                                    system_prompt=(
                                        selected_correction.system_prompt
                                    ),
                                    enable_thinking=False,
                                    phase=(
                                        "course_teaching_plan_batch_validation"
                                    ),
                                    progress=44,
                                    heartbeat_message=(
                                        "仍在等待 AI 修复教案批次 "
                                        f"{batch_id}"
                                    ),
                                    phase_detail=batch_progress_detail,
                                )
                            except (
                                AIProviderRequestError,
                                CourseGenerationDeadlineExceeded,
                            ) as exc:
                                corrected = ""
                                fallback_reason = (
                                    "correction_provider_error:"
                                    f"{type(exc).__name__}"
                                )
                            parsed = (
                                self._extract_json(corrected)
                                if corrected else None
                            )
                            batch = normalize_teaching_plan_batch_v3(
                                parsed if isinstance(parsed, dict) else {},
                                batch_id=batch_id,
                                skeleton_revision_id=str(
                                    skeleton.get("revision_id") or ""
                                ),
                            )
                            batch_report = validate_teaching_plan_batch_v3(
                                batch,
                                batch_spec=spec,
                                skeleton=skeleton,
                                sections=planning_sections,
                            )
                if not batch_report.get("passed"):
                    generation_source = "deterministic_local_fallback"
                    fallback_reason = (
                        fallback_reason or "model_output_failed_validation"
                    )
                    batch = compile_fallback_teaching_batch(
                        batch_spec=spec,
                        skeleton=skeleton,
                        sections=planning_sections,
                    )
                    batch_report = validate_teaching_plan_batch_v3(
                        batch,
                        batch_spec=spec,
                        skeleton=skeleton,
                        sections=planning_sections,
                    )
                    if not batch_report.get("passed"):
                        raise AIProviderRequestError(
                            f"本地教案批次 {batch_id} 编译失败；"
                            "这是生成编排器错误"
                        )
                async with state_lock:
                    if generation_source != "model":
                        fallback_units.append({
                            "unit": batch_id,
                            "reason": fallback_reason,
                            "section_ids": list(section_ids),
                        })
                    results[batch_id] = batch
                    stored_batches[batch_id] = {
                        "status": "completed",
                        "section_ids": section_ids,
                        "skeleton_revision_id": skeleton.get("revision_id"),
                        "revision_id": batch.get("revision_id"),
                        "attempt_count": attempt_count,
                        "validation_report": deepcopy(batch_report),
                        "payload": deepcopy(batch),
                        "generation_source": generation_source,
                        "fallback_reason": fallback_reason or None,
                        "prompt_detail_level": (
                            selected_batch_prompt.detail_level
                            if selected_batch_prompt is not None
                            else "local"
                        ),
                    }
                    teaching_stage["completed_batch_count"] = len(results)
                    teaching_stage["completed_section_count"] = sum(
                        len(item.get("section_ids") or [])
                        for key, item in stored_batches.items()
                        if key in results and isinstance(item, dict)
                    )
                    teaching_stage["model_call_count"] = counter["calls"]
                    teaching_stage["prompt_chars"] = counter["prompt_chars"]
                    teaching_stage["prompt_detail_levels"] = list(
                        prompt_detail_levels
                    )
                    teaching_stage["fallback_units"] = deepcopy(
                        fallback_units
                    )
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
                    teaching_stage["model_call_count"] = counter["calls"]
                    teaching_stage["prompt_chars"] = counter["prompt_chars"]
                    await self._notify_checkpoint(on_checkpoint, course_data)
                raise

        generated = await asyncio.gather(
            *(generate_batch(spec) for spec in pending_specs),
            return_exceptions=True,
        )
        # Batches run concurrently, so completion order is not deterministic.
        # Report the failure that comes first in batch order and make the
        # checkpoint name the same batch the raised error names.
        batch_order = {
            str(spec.get("batch_id") or ""): index
            for index, spec in enumerate(batch_specs)
        }
        failures_by_batch = sorted(
            (
                (batch_order.get(str(spec.get("batch_id") or "")), str(spec.get("batch_id") or ""), item)
                for spec, item in zip(pending_specs, generated)
                if isinstance(item, BaseException)
            ),
            key=lambda entry: (entry[0] is None, entry[0]),
        )
        failures = [entry[2] for entry in failures_by_batch]
        if failures:
            teaching_stage["failed_batch_id"] = failures_by_batch[0][1]
            teaching_stage["failed_batch_ids"] = [
                entry[1] for entry in failures_by_batch
            ]
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
        duration_ms = previous_duration_ms + int(
            (time.monotonic() - started_at) * 1000
        )
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
        semantic_status = (
            "retry_required" if fallback_units else "ai_complete"
        )
        teaching_stage.update({
            "status": (
                "retry_required" if fallback_units else "completed"
            ),
            "schema_version": course_teaching_plan.get("schema_version"),
            "revision_id": course_teaching_plan.get("revision_id"),
            "source_outline_revision_id": outline_revision_id,
            "validation_report": deepcopy(report),
            "duration_ms": duration_ms,
            "model_call_count": counter["calls"],
            "prompt_chars": counter["prompt_chars"],
            "prompt_tokens": counter["prompt_tokens"],
            "max_prompt_tokens": counter["max_prompt_tokens"],
            "prompt_detail_levels": list(prompt_detail_levels),
            "adaptive_compaction_count": sum(
                level != "full" for level in prompt_detail_levels
            ),
            "fallback_units": deepcopy(fallback_units),
            "degraded": bool(fallback_units),
            "semantic_status": semantic_status,
            "semantic_retry_count": semantic_retry_count,
            "ai_section_count": (
                0
                if any(
                    str(item.get("unit") or "").startswith("skeleton_chunk_")
                    for item in fallback_units
                )
                else sum(
                    len(spec.get("section_ids") or [])
                    for spec in batch_specs
                    if (
                        stored_batches.get(str(spec.get("batch_id") or ""), {})
                        .get("generation_source") == "model"
                    )
                )
            ),
            "provider_capacity": self.provider_capacity_snapshot(),
            "final_payload_split_count": sum(
                bool(spec.get("split_from_final_payload"))
                for spec in batch_specs
            ),
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
        teaching_stage.pop("failed_batch_ids", None)
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
        if fallback_units:
            if semantic_retry_count < 1:
                teaching_stage["semantic_retry_count"] = (
                    semantic_retry_count + 1
                )
                await self._notify_phase(
                    on_phase,
                    "course_teaching_plan_retry",
                    47,
                    "正在从检查点自动重试未通过的教案单元",
                    phase_progress=0,
                    phase_detail={
                        "artifact_type": "course_teaching_plan",
                        "retry_units": [
                            str(item.get("unit") or "")
                            for item in fallback_units
                        ],
                        "preserved_ai_sections": int(
                            teaching_stage.get("ai_section_count") or 0
                        ),
                    },
                )
                await self._notify_checkpoint(on_checkpoint, course_data)
                return await self._prepare_course_teaching_plan(
                    course_data=course_data,
                    plan=plan,
                    artifacts=artifacts,
                    on_phase=on_phase,
                    on_checkpoint=on_checkpoint,
                    semantic_retry_count=semantic_retry_count + 1,
                )
            raise AIProviderRequestError(
                "全课教案仍有非 AI 语义单元，已保留成功批次并停止在正文之前；"
                "请从检查点重试剩余教案单元"
            )
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

    async def _compile_fallback_course_teaching_plan(
        self,
        *,
        course_data: dict[str, Any],
        plan: dict[str, Any],
        sections: list[dict[str, Any]],
        outline_revision_id: str,
        on_checkpoint: Callable[[dict[str, Any]], Awaitable[None] | None] | None,
        reason: str,
        existing_skeleton: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Complete missing units locally without replacing valid checkpoints."""
        teaching_stage = course_data.setdefault(
            "generation_stage_artifacts", {}
        ).setdefault("course_teaching_plan", {})
        section_by_id = {
            str(item.get("node_id") or ""): item
            for item in sections
            if isinstance(item, dict)
        }
        preserved_skeleton_sections: list[dict[str, Any]] = []
        skeleton: dict[str, Any]
        if isinstance(existing_skeleton, dict):
            normalized_existing = normalize_teaching_plan_skeleton_v3(
                existing_skeleton,
                outline_revision_id=outline_revision_id,
            )
            existing_ids = [
                str(item.get("node_id") or "")
                for item in normalized_existing.get("sections") or []
                if str(item.get("node_id") or "") in section_by_id
            ]
            preserved_skeleton_sections = [
                section_by_id[node_id] for node_id in existing_ids
            ]
            partial_report = validate_teaching_plan_skeleton_v3(
                normalized_existing,
                sections=preserved_skeleton_sections,
            )
            if not partial_report.get("passed"):
                preserved_skeleton_sections = []
                normalized_existing = {}
        else:
            normalized_existing = {}
        if preserved_skeleton_sections:
            preserved_ids = {
                str(item.get("node_id") or "")
                for item in preserved_skeleton_sections
            }
            missing_sections = [
                item
                for item in sections
                if str(item.get("node_id") or "") not in preserved_ids
            ]
            skeleton = compile_fallback_teaching_skeleton(
                missing_sections,
                outline_revision_id=outline_revision_id,
                prior_skeleton=normalized_existing,
            )
        else:
            skeleton = compile_fallback_teaching_skeleton(
                sections,
                outline_revision_id=outline_revision_id,
            )
        skeleton_report = validate_teaching_plan_skeleton_v3(
            skeleton,
            sections=sections,
        )
        if not skeleton_report.get("passed"):
            raise AIProviderRequestError(
                "本地教案骨架编译失败；这是生成编排器错误"
            )
        batch_specs = build_teaching_plan_batches(
            sections,
            skeleton,
            self._teaching_plan_budget,
        )
        stored_batches = (
            teaching_stage.get("batches")
            if isinstance(teaching_stage.get("batches"), dict)
            else {}
        )
        fallback_units: list[dict[str, Any]] = list(
            teaching_stage.get("fallback_units") or []
        )
        batches: list[dict[str, Any]] = []
        preserved_batch_count = 0
        finalized_batches: dict[str, dict[str, Any]] = {}
        for spec in batch_specs:
            batch_id = str(spec.get("batch_id") or "")
            stored = (
                stored_batches.get(batch_id)
                if isinstance(stored_batches, dict)
                else None
            )
            stored_payload = (
                stored.get("payload")
                if isinstance(stored, dict)
                and stored.get("status") == "completed"
                and list(stored.get("section_ids") or [])
                == list(spec.get("section_ids") or [])
                else {}
            )
            batch = normalize_teaching_plan_batch_v3(
                stored_payload if isinstance(stored_payload, dict) else {},
                batch_id=batch_id,
                skeleton_revision_id=str(skeleton.get("revision_id") or ""),
            )
            batch_report = validate_teaching_plan_batch_v3(
                batch,
                batch_spec=spec,
                skeleton=skeleton,
                sections=sections,
            )
            generation_source = str(
                (stored or {}).get("generation_source") or "model"
            )
            if batch_report.get("passed"):
                preserved_batch_count += 1
            else:
                generation_source = "deterministic_local_fallback"
                batch = compile_fallback_teaching_batch(
                    batch_spec=spec,
                    skeleton=skeleton,
                    sections=sections,
                )
                batch_report = validate_teaching_plan_batch_v3(
                    batch,
                    batch_spec=spec,
                    skeleton=skeleton,
                    sections=sections,
                )
                fallback_units.append({
                    "unit": batch_id,
                    "reason": reason,
                    "section_ids": list(spec.get("section_ids") or []),
                })
            if not batch_report.get("passed"):
                raise AIProviderRequestError(
                    "本地详细教案编译失败；这是生成编排器错误"
                )
            batches.append(batch)
            finalized_batches[batch_id] = {
                "status": "completed",
                "section_ids": list(spec.get("section_ids") or []),
                "skeleton_revision_id": skeleton.get("revision_id"),
                "revision_id": batch.get("revision_id"),
                "validation_report": deepcopy(batch_report),
                "payload": deepcopy(batch),
                "generation_source": generation_source,
                "fallback_reason": (
                    reason
                    if generation_source == "deterministic_local_fallback"
                    else (stored or {}).get("fallback_reason")
                ),
            }
        assembled = assemble_course_teaching_plan_v3(
            skeleton=skeleton,
            batches=batches,
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
        if not report.get("passed"):
            raise AIProviderRequestError(
                "本地全课教案编译失败；这是生成编排器错误"
            )
        planned_course = apply_course_teaching_plan(
            plan,
            course_teaching_plan,
        )
        teaching_stage.update({
            "status": "retry_required",
            "semantic_status": "retry_required",
            "degraded": True,
            "schema_version": course_teaching_plan.get("schema_version"),
            "revision_id": course_teaching_plan.get("revision_id"),
            "source_outline_revision_id": outline_revision_id,
            "validation_report": deepcopy(report),
            "skeleton": deepcopy(skeleton),
            "skeleton_revision_id": skeleton.get("revision_id"),
            "skeleton_validation_report": deepcopy(skeleton_report),
            "strategy": (
                "adaptive_timeout_completion"
                if preserved_skeleton_sections or preserved_batch_count
                else "deterministic_local_fallback"
            ),
            "fallback_reason": reason,
            "fallback_units": fallback_units,
            "batches": finalized_batches,
            "section_count": len(sections),
            "completed_section_count": len(sections),
            "batch_count": len(batch_specs),
            "completed_batch_count": len(batch_specs),
            "preserved_skeleton_section_count": len(
                preserved_skeleton_sections
            ),
            "preserved_batch_count": preserved_batch_count,
            "knowledge_point_count": (report.get("actual") or {}).get(
                "knowledge_point_count", 0
            ),
            "knowledge_compilation_model_call_count": 0,
            "graph_compilation_model_call_count": 0,
        })
        course_data.update({
            "course_teaching_plan_skeleton": skeleton,
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
        await self._notify_checkpoint(on_checkpoint, course_data)
        return planned_course

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
        max_input_tokens: int | None = None,
        max_input_chars: int | None = None,
        max_output_tokens: int | None = None,
        max_attempts: int | None = None,
    ) -> str:
        """Run one model unit until it completes or stops producing chunks."""
        inactivity_timeout_seconds = max(
            1.0,
            float(
                stage_timeout_seconds
                if stage_timeout_seconds is not None
                else self._generation_budget.call_timeout_seconds
            ),
        )
        activity_event = asyncio.Event()
        last_activity = time.monotonic()

        def _mark_activity() -> None:
            nonlocal last_activity
            last_activity = time.monotonic()
            activity_event.set()

        call_task = asyncio.create_task(self._call_llm(
            user_prompt,
            system_prompt,
            retry_count=1,
            enable_thinking=enable_thinking,
            max_tokens=max_output_tokens,
            max_input_tokens=max_input_tokens,
            max_input_chars=max_input_chars,
            max_attempts=max_attempts,
            reject_truncated=True,
            raise_on_failure=True,
            json_mode=True,
            on_stream_activity=_mark_activity,
        ))
        started_at = time.monotonic()
        last_heartbeat = started_at
        try:
            while not call_task.done():
                now = time.monotonic()
                inactive_for = now - last_activity
                remaining = max(
                    0.01,
                    inactivity_timeout_seconds - inactive_for,
                )
                wait_for = min(
                    remaining,
                    max(0.05, heartbeat_seconds),
                )
                activity_task = asyncio.create_task(activity_event.wait())
                done, _pending = await asyncio.wait(
                    {call_task, activity_task},
                    timeout=wait_for,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if call_task in done:
                    activity_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await activity_task
                    break
                if activity_task in done:
                    activity_event.clear()
                    continue
                activity_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await activity_task

                now = time.monotonic()
                inactive_for = now - last_activity
                if inactive_for >= inactivity_timeout_seconds:
                    call_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await call_task
                    if on_phase:
                        await self._notify_phase(
                            on_phase,
                            phase,
                            base_progress,
                            f"{heartbeat_message}长时间没有新输出，已保留最近检查点",
                            phase_progress=100,
                            phase_detail={
                                **(phase_detail or {}),
                                "timed_out": True,
                                "timeout_policy": "stream_inactivity",
                                "inactivity_timeout_seconds": (
                                    inactivity_timeout_seconds
                                ),
                            },
                        )
                    raise CourseGenerationDeadlineExceeded(
                        f"{phase} 阶段连续 {int(inactivity_timeout_seconds)} "
                        "秒没有新内容，已停止当前最小生成单元，可从最近检查点继续"
                    )

                if on_phase and now - last_heartbeat >= heartbeat_seconds:
                    last_heartbeat = now
                    await self._notify_phase(
                        on_phase,
                        phase,
                        base_progress,
                        f"{heartbeat_message}（已等待约 {int(now - started_at)} 秒）",
                        phase_progress=100,
                        phase_detail={
                            **(phase_detail or {}),
                            "heartbeat": True,
                            "elapsed_seconds": int(now - started_at),
                            "inactive_seconds": int(inactive_for),
                            "timeout_policy": "stream_inactivity",
                        },
                    )
            try:
                return call_task.result()
            except asyncio.TimeoutError as exc:
                # Some provider adapters surface their own inactivity timeout
                # as asyncio.TimeoutError; keep the same resumable contract.
                raise CourseGenerationDeadlineExceeded(
                    f"{phase} 阶段连续 {int(inactivity_timeout_seconds)} "
                    "秒没有新内容，已停止当前最小生成单元，可从最近检查点继续"
                ) from exc
        except asyncio.CancelledError:
            call_task.cancel()
            raise
        finally:
            if not call_task.done():
                call_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await call_task

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

    async def _generate_hierarchical_course_outline(
        self,
        *,
        topic: str,
        audience: str,
        artifacts: dict[str, Any],
        profile: SubjectPedagogyProfile,
        difficulty_profile: dict[str, Any],
        gap_assessment: dict[str, Any],
        adaptation_decision: dict[str, Any],
        existing_stage: dict[str, Any],
        existing_generation_stages: dict[str, Any],
        on_phase: Callable[..., Awaitable[None] | None] | None,
        on_checkpoint: (
            Callable[[dict[str, Any]], Awaitable[None] | None] | None
        ),
    ) -> tuple[
        dict[str, Any] | None,
        dict[str, Any],
        dict[str, Any],
    ]:
        """Build every outline as chapter skeleton -> batches -> local assembly."""
        brief = artifacts.get("course_generation_brief") or {}
        shape_constraints = brief.get("course_shape_constraints") or {}
        request_fingerprint = outline_request_fingerprint(
            topic=topic,
            audience=audience,
            brief=brief,
            difficulty_profile=difficulty_profile,
        )
        stage = (
            deepcopy(existing_stage)
            if existing_stage.get("request_fingerprint")
            == request_fingerprint
            else {}
        )
        started_at = time.monotonic()
        counter = {
            "calls": int(stage.get("model_call_count") or 0),
            "prompt_chars": int(stage.get("prompt_chars") or 0),
            "prompt_tokens": int(stage.get("prompt_tokens") or 0),
            "max_prompt_tokens": int(stage.get("max_prompt_tokens") or 0),
        }
        prompt_detail_levels = list(stage.get("prompt_detail_levels") or [])
        fallback_units = [
            deepcopy(item)
            for item in stage.get("fallback_units") or []
            if isinstance(item, dict)
        ]
        counter_lock = asyncio.Lock()
        state_lock = asyncio.Lock()
        stage.update({
            "status": "in_progress",
            "schema_version": "course_outline_execution_v2",
            "strategy": "hierarchical_chapter_batches",
            "request_fingerprint": request_fingerprint,
            "batch_max_sections": self._outline_budget.batch_max_sections,
            "max_concurrency": self._planning_concurrency,
            "inactivity_timeout_seconds": (
                self._outline_budget.batch_timeout_seconds
            ),
            "completion_policy": "all_units_settled",
        })

        def add_fallback(
            *,
            unit: str,
            reason: str,
            section_ids: list[str] | None = None,
        ) -> None:
            if any(
                str(item.get("unit") or "") == unit
                for item in fallback_units
            ):
                return
            fallback_units.append({
                "unit": unit,
                "reason": reason,
                "section_ids": list(section_ids or []),
            })

        async def persist_stage() -> None:
            stage.update({
                "model_call_count": counter["calls"],
                "prompt_chars": counter["prompt_chars"],
                "prompt_tokens": counter["prompt_tokens"],
                "max_prompt_tokens": counter["max_prompt_tokens"],
                "prompt_detail_levels": list(prompt_detail_levels),
                "adaptive_compaction_count": sum(
                    level != "full"
                    for level in prompt_detail_levels
                ),
                "fallback_units": deepcopy(fallback_units),
            })
            await self._notify_checkpoint(on_checkpoint, {
                "generation_pipeline_version": PIPELINE_VERSION,
                "generation_schema_version": PIPELINE_VERSION,
                "prompt_contract_version": PROMPT_CONTRACT_VERSION,
                "generation_status": "outline_generation",
                "generation_stage_artifacts": {
                    **deepcopy(existing_generation_stages),
                    "outline": deepcopy(stage),
                },
            })

        async def request_model(
            *,
            user_prompt: str,
            system_prompt: str,
            phase: str,
            message: str,
            phase_detail: dict[str, Any],
            enable_thinking: bool = False,
        ) -> str:
            input_tokens = self.estimate_request_tokens(
                user_prompt,
                system_prompt,
            )
            try:
                async with self._planning_semaphore:
                    return await self._call_llm_with_heartbeat(
                        user_prompt,
                        system_prompt,
                        enable_thinking=enable_thinking,
                        on_phase=on_phase,
                        phase=phase,
                        base_progress=33,
                        stage_timeout_seconds=(
                            self._outline_budget.batch_timeout_seconds
                        ),
                        heartbeat_message=message,
                        phase_detail=phase_detail,
                        max_input_tokens=(
                            self._generation_budget.max_input_tokens
                        ),
                        max_input_chars=(
                            self._generation_budget.max_input_chars
                        ),
                        max_output_tokens=(
                            self._generation_budget.outline_max_output_tokens
                        ),
                        max_attempts=(
                            self._generation_budget.provider_max_attempts
                        ),
                    )
            finally:
                async with counter_lock:
                    counter["calls"] += 1
                    counter["prompt_chars"] += (
                        len(user_prompt) + len(system_prompt)
                    )
                    counter["prompt_tokens"] += input_tokens
                    counter["max_prompt_tokens"] = max(
                        counter["max_prompt_tokens"],
                        input_tokens,
                    )

        raw_skeleton = stage.get("skeleton")
        skeleton = normalize_outline_skeleton(
            raw_skeleton if isinstance(raw_skeleton, dict) else {},
            topic=topic,
            request_fingerprint=request_fingerprint,
        )
        skeleton_report = validate_outline_skeleton(
            skeleton,
            shape_constraints=shape_constraints,
            request_fingerprint=request_fingerprint,
        )
        skeleton_is_current = bool(
            isinstance(raw_skeleton, dict)
            and skeleton_report.get("passed")
        )
        skeleton_error: Exception | None = None
        skeleton_failure_reason = ""
        if not skeleton_is_current:
            skeleton_levels = prompt_detail_levels_for_source(
                {
                    "topic": topic,
                    "audience": audience,
                    "brief": brief,
                    "difficulty_profile": difficulty_profile,
                    "material_cards": artifacts.get("material_cards") or [],
                },
                max_input_chars=self._generation_budget.max_input_chars,
            )
            skeleton_prompts = {
                detail_level: (
                    self._prompt_composer.build_outline_skeleton_v2_prompt(
                        subject=topic,
                        audience=audience,
                        brief=brief,
                        profile=profile,
                        difficulty_profile=difficulty_profile,
                        gap_assessment=gap_assessment,
                        adaptation_decision=adaptation_decision,
                        material_context=build_outline_generation_context(
                            artifacts,
                            detail_level=detail_level,
                        ),
                        detail_level=detail_level,
                    )
                )
                for detail_level in skeleton_levels
            }
            skeleton_user = (
                f"为「{clip_text(topic, 160)}」规划全课章节骨架，只输出 JSON。"
            )
            selected_skeleton = select_budgeted_prompt(
                (
                    PromptCandidate(
                        detail_level=detail_level,
                        user_prompt=skeleton_user,
                        system_prompt=skeleton_prompts[detail_level],
                    )
                    for detail_level in skeleton_levels
                ),
                max_input_chars=self._generation_budget.max_input_chars,
                max_input_tokens=self._generation_budget.max_input_tokens,
                token_estimator=self.estimate_request_tokens,
            )
            failure_reason = ""
            parsed: dict[str, Any] | None = None
            if selected_skeleton is None:
                failure_reason = "skeleton_prompt_did_not_fit"
            else:
                prompt_detail_levels.append(
                    selected_skeleton.detail_level
                )
                await self._notify_phase(
                    on_phase,
                    "outline_generation",
                    32,
                    "正在生成轻量章节骨架",
                    phase_progress=0,
                    phase_detail={
                        "artifact_type": "course_outline_skeleton",
                    },
                )
                try:
                    response = await request_model(
                        user_prompt=selected_skeleton.user_prompt,
                        system_prompt=selected_skeleton.system_prompt,
                        phase="outline_generation",
                        message="仍在等待 AI 生成轻量章节骨架",
                        phase_detail={
                            "artifact_type": "course_outline_skeleton",
                        },
                        enable_thinking=True,
                    )
                except (
                    AIProviderRequestError,
                    CourseGenerationDeadlineExceeded,
                ) as exc:
                    response = ""
                    skeleton_error = exc
                    failure_reason = (
                        f"provider_error:{type(exc).__name__}"
                    )
                candidate = (
                    self._extract_json(response)
                    if response
                    else None
                )
                parsed = candidate if isinstance(candidate, dict) else None
            skeleton = normalize_outline_skeleton(
                parsed or {},
                topic=topic,
                request_fingerprint=request_fingerprint,
            )
            skeleton_report = validate_outline_skeleton(
                skeleton,
                shape_constraints=shape_constraints,
                request_fingerprint=request_fingerprint,
            )
            if (
                not skeleton_report.get("passed")
                and not failure_reason
                and selected_skeleton is not None
            ):
                correction_user = (
                    "只修复全课章节骨架，重新输出完整 JSON。"
                )
                correction_prompt = (
                    self._prompt_composer
                    .build_outline_skeleton_v2_correction_prompt(
                        original_prompt=(
                            selected_skeleton.system_prompt
                        ),
                        issues=skeleton_report.get("issues") or [],
                    )
                )
                selected_correction = select_budgeted_prompt(
                    [
                        PromptCandidate(
                            detail_level=(
                                selected_skeleton.detail_level
                            ),
                            user_prompt=correction_user,
                            system_prompt=correction_prompt,
                        ),
                    ],
                    max_input_chars=(
                        self._generation_budget.max_input_chars
                    ),
                    max_input_tokens=(
                        self._generation_budget.max_input_tokens
                    ),
                    token_estimator=self.estimate_request_tokens,
                )
                if selected_correction is None:
                    failure_reason = (
                        "skeleton_correction_prompt_did_not_fit"
                    )
                else:
                    prompt_detail_levels.append(
                        selected_correction.detail_level
                    )
                    try:
                        corrected = await request_model(
                            user_prompt=(
                                selected_correction.user_prompt
                            ),
                            system_prompt=(
                                selected_correction.system_prompt
                            ),
                            phase="outline_validation",
                            message=(
                                "仍在等待 AI 修复轻量章节骨架"
                            ),
                            phase_detail={
                                "artifact_type": (
                                    "course_outline_skeleton"
                                ),
                            },
                        )
                    except (
                        AIProviderRequestError,
                        CourseGenerationDeadlineExceeded,
                    ) as exc:
                        corrected = ""
                        skeleton_error = exc
                        failure_reason = (
                            "correction_provider_error:"
                            f"{type(exc).__name__}"
                        )
                    candidate = (
                        self._extract_json(corrected)
                        if corrected
                        else None
                    )
                    skeleton = normalize_outline_skeleton(
                        candidate if isinstance(candidate, dict) else {},
                        topic=topic,
                        request_fingerprint=request_fingerprint,
                    )
                    skeleton_report = validate_outline_skeleton(
                        skeleton,
                        shape_constraints=shape_constraints,
                        request_fingerprint=request_fingerprint,
                    )
            skeleton_failure_reason = (
                failure_reason
                or "model_output_failed_validation"
            )
        stage.update({
            "skeleton": deepcopy(skeleton),
            "skeleton_revision_id": skeleton.get("revision_id"),
            "skeleton_validation_report": deepcopy(skeleton_report),
            "chapter_count": len(skeleton.get("chapters") or []),
            "section_count": sum(
                int(item.get("section_count") or 0)
                for item in skeleton.get("chapters") or []
                if isinstance(item, dict)
            ),
        })
        await persist_stage()
        if not skeleton_report.get("passed"):
            failed_report = validate_course_outline_constraints({}, brief)
            failed_report.setdefault("issues", []).extend(
                deepcopy(skeleton_report.get("issues") or [])
            )
            failed_report["passed"] = False
            stage["status"] = "failed"
            stage["failure_reason"] = skeleton_failure_reason
            await persist_stage()
            if skeleton_error is not None:
                raise skeleton_error
            return None, failed_report, stage

        batch_specs = build_outline_batch_specs(
            skeleton,
            self._outline_budget,
        )
        chapter_by_number = {
            int(item.get("chapter_number") or 0): item
            for item in skeleton.get("chapters") or []
            if isinstance(item, dict)
        }
        stored_batches = stage.get("batches")
        if not isinstance(stored_batches, dict):
            stored_batches = {}
            stage["batches"] = stored_batches
        results: dict[str, dict[str, Any]] = {}
        for spec in batch_specs:
            batch_id = str(spec.get("batch_id") or "")
            stored = stored_batches.get(batch_id)
            payload = (
                stored.get("payload")
                if isinstance(stored, dict)
                else {}
            )
            candidate = normalize_outline_batch(
                payload if isinstance(payload, dict) else {},
                spec=spec,
                skeleton_revision_id=str(
                    skeleton.get("revision_id") or ""
                ),
            )
            report = validate_outline_batch(
                candidate,
                spec=spec,
                skeleton_revision_id=str(
                    skeleton.get("revision_id") or ""
                ),
            )
            if (
                isinstance(stored, dict)
                and stored.get("status") == "completed"
                and stored.get("skeleton_revision_id")
                == skeleton.get("revision_id")
                and report.get("passed")
            ):
                results[batch_id] = candidate

        def outline_growth_detail(
            *,
            active_spec: dict[str, Any] | None = None,
            state: str = "growing",
        ) -> dict[str, Any]:
            """Project persisted outline checkpoints into a user-safe live tree."""
            completed_sections = 0
            chapters: list[dict[str, Any]] = []
            for chapter in skeleton.get("chapters") or []:
                if not isinstance(chapter, dict):
                    continue
                chapter_number = int(chapter.get("chapter_number") or 0)
                sections: list[dict[str, Any]] = []
                for spec in sorted(
                    (
                        item
                        for item in batch_specs
                        if int(item.get("chapter_number") or 0)
                        == chapter_number
                    ),
                    key=lambda item: int(
                        item.get("start_section_index") or 0
                    ),
                ):
                    batch = results.get(str(spec.get("batch_id") or "")) or {}
                    sections.extend(
                        {
                            "node_id": str(item.get("node_id") or ""),
                            "section_number": str(
                                item.get("section_number") or ""
                            ),
                            "title": str(item.get("title") or ""),
                            "learning_objective": str(
                                item.get("learning_objective") or ""
                            ),
                        }
                        for item in batch.get("sections") or []
                        if isinstance(item, dict)
                    )
                completed_sections += len(sections)
                section_count = int(chapter.get("section_count") or 0)
                is_active = bool(
                    active_spec
                    and int(active_spec.get("chapter_number") or 0)
                    == chapter_number
                )
                chapters.append({
                    "chapter_number": chapter_number,
                    "title": str(chapter.get("title") or ""),
                    "learning_focus": str(
                        chapter.get("learning_focus") or ""
                    ),
                    "section_count": section_count,
                    "completed_section_count": len(sections),
                    "status": (
                        "completed"
                        if section_count > 0 and len(sections) >= section_count
                        else "growing"
                        if is_active
                        else "waiting"
                    ),
                    "sections": sections,
                })
            return {
                "schema_version": "course_outline_growth_v1",
                "state": state,
                "course_title": str(skeleton.get("course_title") or topic),
                "positioning": str(skeleton.get("positioning") or ""),
                "active_batch_id": str(
                    (active_spec or {}).get("batch_id") or ""
                ),
                "active_chapter_number": int(
                    (active_spec or {}).get("chapter_number") or 0
                ),
                "completed_batches": len(results),
                "total_batches": len(batch_specs),
                "completed_sections": completed_sections,
                "total_sections": sum(
                    int(item.get("section_count") or 0)
                    for item in skeleton.get("chapters") or []
                    if isinstance(item, dict)
                ),
                "chapters": chapters,
            }

        await self._notify_phase(
            on_phase,
            "outline_generation",
            32,
            "课程章节主干已形成，正在展开各章小节",
            phase_progress=int(
                100 * len(results) / max(1, len(batch_specs))
            ),
            phase_detail={
                "artifact_type": "course_outline_growth",
                "outline_growth": outline_growth_detail(state="skeleton_ready"),
            },
        )

        specs_by_chapter: dict[int, list[dict[str, Any]]] = {}
        for spec in batch_specs:
            specs_by_chapter.setdefault(
                int(spec.get("chapter_number") or 0),
                [],
            ).append(spec)
        for specs in specs_by_chapter.values():
            specs.sort(
                key=lambda item: int(
                    item.get("start_section_index") or 0
                ),
            )

        def previous_chapter_sections(
            spec: dict[str, Any],
        ) -> list[dict[str, Any]]:
            chapter_number = int(spec.get("chapter_number") or 0)
            start = int(spec.get("start_section_index") or 0)
            previous: list[dict[str, Any]] = []
            for item in specs_by_chapter.get(chapter_number, []):
                if int(item.get("end_section_index") or 0) >= start:
                    continue
                payload = results.get(str(item.get("batch_id") or "")) or {}
                previous.extend(
                    deepcopy(section)
                    for section in payload.get("sections") or []
                    if isinstance(section, dict)
                )
            return previous

        def build_batch_prompt_options(
            spec: dict[str, Any],
        ) -> tuple[
            Any,
            dict[str, str],
        ]:
            chapter_number = int(spec.get("chapter_number") or 0)
            chapter = chapter_by_number.get(chapter_number) or {}
            previous = previous_chapter_sections(spec)
            evidence_hints = select_chapter_evidence_hints(
                artifacts,
                chapter,
            )
            levels = prompt_detail_levels_for_source(
                {
                    "course_title": skeleton.get("course_title"),
                    "positioning": skeleton.get("positioning"),
                    "learning_objectives": (
                        skeleton.get("learning_objectives") or []
                    ),
                    "chapter": chapter,
                    "neighbor_chapters": outline_neighbor_chapters(
                        skeleton,
                        chapter_number,
                    ),
                    "batch_spec": spec,
                    "previous_sections": previous,
                    "evidence_hints": evidence_hints,
                },
                max_input_chars=self._generation_budget.max_input_chars,
            )
            prompts = {
                detail_level: (
                    self._prompt_composer
                    .build_outline_batch_v2_prompt(
                        course_title=str(
                            skeleton.get("course_title") or topic
                        ),
                        positioning=str(
                            skeleton.get("positioning") or ""
                        ),
                        learning_objectives=list(
                            skeleton.get("learning_objectives") or []
                        ),
                        chapter=chapter,
                        neighbor_chapters=outline_neighbor_chapters(
                            skeleton,
                            chapter_number,
                        ),
                        batch_spec=spec,
                        previous_sections=previous,
                        evidence_hints=evidence_hints,
                        skeleton_revision_id=str(
                            skeleton.get("revision_id") or ""
                        ),
                        detail_level=detail_level,
                    )
                )
                for detail_level in levels
            }
            user_prompt = (
                f"生成目录批次 {spec.get('batch_id')}，只输出 JSON。"
            )
            selected = select_budgeted_prompt(
                (
                    PromptCandidate(
                        detail_level=detail_level,
                        user_prompt=user_prompt,
                        system_prompt=prompts[detail_level],
                    )
                    for detail_level in levels
                ),
                max_input_chars=self._generation_budget.max_input_chars,
                max_input_tokens=self._generation_budget.max_input_tokens,
                token_estimator=self.estimate_request_tokens,
            )
            return selected, prompts

        async def generate_batch(
            spec: dict[str, Any],
        ) -> dict[str, Any]:
            batch_id = str(spec.get("batch_id") or "")
            chapter_number = int(spec.get("chapter_number") or 0)
            chapter = chapter_by_number.get(chapter_number) or {}
            selected, prompts = build_batch_prompt_options(spec)
            failure_reason = ""
            parsed: dict[str, Any] | None = None
            if selected is None:
                failure_reason = "batch_prompt_did_not_fit"
            else:
                prompt_detail_levels.append(selected.detail_level)
                await self._notify_phase(
                    on_phase,
                    "outline_generation",
                    33,
                    (
                        f"正在生成第 {chapter_number} 章小节目录"
                        f"（批次 {spec.get('chapter_batch_index')}/"
                        f"{spec.get('chapter_batch_count')}）"
                    ),
                    phase_progress=int(
                        100 * len(results) / max(1, len(batch_specs))
                    ),
                    phase_detail={
                        "artifact_type": "course_outline_batch",
                        "batch_id": batch_id,
                        "completed_batches": len(results),
                        "total_batches": len(batch_specs),
                        "outline_growth": outline_growth_detail(
                            active_spec=spec,
                        ),
                    },
                )
                try:
                    response = await request_model(
                        user_prompt=selected.user_prompt,
                        system_prompt=selected.system_prompt,
                        phase="outline_generation",
                        message=(
                            f"仍在等待 AI 生成目录批次 {batch_id}"
                        ),
                        phase_detail={
                            "artifact_type": "course_outline_batch",
                            "batch_id": batch_id,
                        },
                    )
                except (
                    AIProviderRequestError,
                    CourseGenerationDeadlineExceeded,
                ) as exc:
                    response = ""
                    failure_reason = (
                        f"provider_error:{type(exc).__name__}"
                    )
                candidate = (
                    self._extract_json(response)
                    if response
                    else None
                )
                parsed = candidate if isinstance(candidate, dict) else None
            batch = normalize_outline_batch(
                parsed or {},
                spec=spec,
                skeleton_revision_id=str(
                    skeleton.get("revision_id") or ""
                ),
            )
            report = validate_outline_batch(
                batch,
                spec=spec,
                skeleton_revision_id=str(
                    skeleton.get("revision_id") or ""
                ),
            )
            if (
                not report.get("passed")
                and not failure_reason
                and selected is not None
            ):
                correction_prompt = (
                    self._prompt_composer
                    .build_outline_batch_v2_correction_prompt(
                        original_prompt=prompts[selected.detail_level],
                        issues=report.get("issues") or [],
                    )
                )
                selected_correction = select_budgeted_prompt(
                    [
                        PromptCandidate(
                            detail_level=selected.detail_level,
                            user_prompt=(
                                f"修复目录批次 {batch_id}，"
                                "只输出完整 JSON。"
                            ),
                            system_prompt=correction_prompt,
                        ),
                    ],
                    max_input_chars=(
                        self._generation_budget.max_input_chars
                    ),
                    max_input_tokens=(
                        self._generation_budget.max_input_tokens
                    ),
                    token_estimator=self.estimate_request_tokens,
                )
                if selected_correction is None:
                    failure_reason = (
                        "batch_correction_prompt_did_not_fit"
                    )
                else:
                    prompt_detail_levels.append(
                        selected_correction.detail_level
                    )
                    try:
                        corrected = await request_model(
                            user_prompt=(
                                selected_correction.user_prompt
                            ),
                            system_prompt=(
                                selected_correction.system_prompt
                            ),
                            phase="outline_validation",
                            message=(
                                f"仍在等待 AI 修复目录批次 {batch_id}"
                            ),
                            phase_detail={
                                "artifact_type": (
                                    "course_outline_batch"
                                ),
                                "batch_id": batch_id,
                            },
                        )
                    except (
                        AIProviderRequestError,
                        CourseGenerationDeadlineExceeded,
                    ) as exc:
                        corrected = ""
                        failure_reason = (
                            "correction_provider_error:"
                            f"{type(exc).__name__}"
                        )
                    candidate = (
                        self._extract_json(corrected)
                        if corrected
                        else None
                    )
                    batch = normalize_outline_batch(
                        (
                            candidate
                            if isinstance(candidate, dict)
                            else {}
                        ),
                        spec=spec,
                        skeleton_revision_id=str(
                            skeleton.get("revision_id") or ""
                        ),
                    )
                    report = validate_outline_batch(
                        batch,
                        spec=spec,
                        skeleton_revision_id=str(
                            skeleton.get("revision_id") or ""
                        ),
                    )
            generation_source = "model"
            if not report.get("passed"):
                generation_source = "deterministic_local_fallback"
                failure_reason = (
                    failure_reason
                    or "model_output_failed_validation"
                )
                batch = compile_fallback_outline_batch(
                    spec=spec,
                    chapter=chapter,
                    skeleton_revision_id=str(
                        skeleton.get("revision_id") or ""
                    ),
                )
                report = validate_outline_batch(
                    batch,
                    spec=spec,
                    skeleton_revision_id=str(
                        skeleton.get("revision_id") or ""
                    ),
                )
                if not report.get("passed"):
                    raise AIProviderRequestError(
                        f"本地目录批次 {batch_id} 汇编失败；"
                        "这是生成编排器错误"
                    )
            async with state_lock:
                results[batch_id] = batch
                if generation_source != "model":
                    add_fallback(
                        unit=batch_id,
                        reason=failure_reason,
                        section_ids=list(
                            spec.get("expected_node_ids") or []
                        ),
                    )
                stored_batches[batch_id] = {
                    "status": "completed",
                    "skeleton_revision_id": (
                        skeleton.get("revision_id")
                    ),
                    "section_ids": list(
                        spec.get("expected_node_ids") or []
                    ),
                    "payload": deepcopy(batch),
                    "validation_report": deepcopy(report),
                    "generation_source": generation_source,
                    "fallback_reason": failure_reason or None,
                    "prompt_detail_level": (
                        selected.detail_level
                        if selected is not None
                        else "local"
                    ),
                }
                stage.update({
                    "batch_count": len(batch_specs),
                    "completed_batch_count": len(results),
                    "completed_section_count": sum(
                        len(item.get("sections") or [])
                        for item in results.values()
                    ),
                    "batches": stored_batches,
                })
                await persist_stage()
                growth_detail = outline_growth_detail(active_spec=spec)
            await self._notify_phase(
                on_phase,
                "outline_generation",
                33,
                (
                    f"第 {chapter_number} 章已形成 "
                    f"{growth_detail['completed_sections']}/"
                    f"{growth_detail['total_sections']} 个小节"
                ),
                phase_progress=int(
                    100
                    * int(growth_detail["completed_batches"])
                    / max(1, int(growth_detail["total_batches"]))
                ),
                phase_detail={
                    "artifact_type": "course_outline_growth",
                    "batch_id": batch_id,
                    "outline_growth": growth_detail,
                },
            )
            return batch

        async def generate_chapter(
            specs: list[dict[str, Any]],
        ) -> None:
            for spec in specs:
                if str(spec.get("batch_id") or "") in results:
                    continue
                await generate_batch(spec)

        chapter_tasks = [
            asyncio.create_task(generate_chapter(specs))
            for _chapter_number, specs in sorted(
                specs_by_chapter.items(),
            )
            if any(
                str(spec.get("batch_id") or "") not in results
                for spec in specs
            )
        ]
        if chapter_tasks:
            await asyncio.gather(
                *chapter_tasks,
                return_exceptions=False,
            )

        for spec in batch_specs:
            batch_id = str(spec.get("batch_id") or "")
            if batch_id in results:
                continue
            chapter = chapter_by_number.get(
                int(spec.get("chapter_number") or 0),
            ) or {}
            batch = compile_fallback_outline_batch(
                spec=spec,
                chapter=chapter,
                skeleton_revision_id=str(
                    skeleton.get("revision_id") or ""
                ),
            )
            report = validate_outline_batch(
                batch,
                spec=spec,
                skeleton_revision_id=str(
                    skeleton.get("revision_id") or ""
                ),
            )
            if not report.get("passed"):
                raise AIProviderRequestError(
                    f"本地目录批次 {batch_id} 汇编失败；"
                    "这是生成编排器错误"
                )
            results[batch_id] = batch
            add_fallback(
                unit=batch_id,
                reason=(
                    "unfinished_batch"
                ),
                section_ids=list(
                    spec.get("expected_node_ids") or []
                ),
            )
            stored_batches[batch_id] = {
                "status": "completed",
                "skeleton_revision_id": skeleton.get("revision_id"),
                "section_ids": list(
                    spec.get("expected_node_ids") or []
                ),
                "payload": deepcopy(batch),
                "validation_report": deepcopy(report),
                "generation_source": "deterministic_local_fallback",
                "fallback_reason": "unfinished_batch",
                "prompt_detail_level": "local",
            }

        plan = assemble_course_outline(
            skeleton=skeleton,
            batch_specs=batch_specs,
            batches=results,
        )
        plan = normalize_course_outline_contract(plan)
        plan_report = validate_course_outline_constraints(plan, brief)
        stage.update({
            "status": (
                "completed_with_warnings"
                if fallback_units
                else "completed"
            ),
            "timed_out": False,
            "skeleton": deepcopy(skeleton),
            "skeleton_revision_id": skeleton.get("revision_id"),
            "batches": stored_batches,
            "batch_count": len(batch_specs),
            "completed_batch_count": len(results),
            "chapter_count": len(plan.get("chapters") or []),
            "section_count": (
                plan_report.get("actual") or {}
            ).get("section_count", 0),
            "completed_section_count": (
                plan_report.get("actual") or {}
            ).get("section_count", 0),
            "duration_ms": int(
                (time.monotonic() - started_at) * 1000
            ),
            "needs_manual_review": bool(fallback_units),
        })
        await persist_stage()
        await self._notify_phase(
            on_phase,
            "outline_generation",
            34,
            "课程目录已完整形成，正在准备确认",
            phase_progress=100,
            phase_detail={
                "artifact_type": "course_outline_growth",
                "outline_growth": outline_growth_detail(state="completed"),
            },
        )
        return plan, plan_report, stage

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
                    "lesson_archetype": section.get(
                        "lesson_archetype", {}
                    ),
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
        on_activity: Callable[[], None] | None = None,
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
        content_levels = prompt_detail_levels_for_source(
            {
                "course_name": persisted.get("course_name") or "",
                "target_audience": persisted.get("target_audience") or "",
                "subject_pedagogy_profile": (
                    persisted.get("subject_pedagogy_profile") or {}
                ),
                "difficulty_profile": persisted.get("difficulty_profile") or {},
                "course_composition_profile": (
                    persisted.get("course_composition_profile") or {}
                ),
                "node": node,
                "context": context,
                "existing_draft": existing_draft,
            },
            max_input_chars=self._generation_budget.max_input_chars,
        )
        selected_content_prompt = select_budgeted_prompt(
            (
                PromptCandidate(
                    detail_level=detail_level,
                    user_prompt=user_prompt,
                    system_prompt=system_prompt,
                )
                for detail_level in content_levels
                for user_prompt, system_prompt in [
                    self._prompt_composer.build_content_prompt(
                        course_data=persisted,
                        node=node,
                        context=context,
                        existing_draft=existing_draft,
                        detail_level=detail_level,
                    )
                ]
            ),
            max_input_chars=self._generation_budget.max_input_chars,
            max_input_tokens=self._generation_budget.max_input_tokens,
            token_estimator=self.estimate_request_tokens,
        )

        continuation = ""
        generation_source = "model"
        fallback_reason = ""
        started_at = time.monotonic()
        if selected_content_prompt is None:
            user_prompt = ""
            system_prompt = ""
            input_tokens = 0
            generation_source = "deterministic_local_fallback"
            fallback_reason = "minimal_content_prompt_did_not_fit"
            continuation = compile_fallback_node_content(node)
            await on_chunk(continuation)
        else:
            user_prompt = selected_content_prompt.user_prompt
            system_prompt = selected_content_prompt.system_prompt
            input_tokens = selected_content_prompt.estimated_input_tokens
        try:
            if selected_content_prompt is not None:
                try:
                    async for chunk in self._stream_llm(
                        prompt=user_prompt,
                        system_prompt=system_prompt,
                        max_tokens=(
                            self._generation_budget.content_max_output_tokens
                        ),
                        max_input_tokens=(
                            self._generation_budget.max_input_tokens
                        ),
                        max_input_chars=(
                            self._generation_budget.max_input_chars
                        ),
                        max_attempts=(
                            self._generation_budget.provider_max_attempts
                        ),
                        on_stream_activity=on_activity,
                    ):
                        normalized = chunk.strip()
                        if (
                            normalized.startswith("[Error:")
                            or normalized == "AI Service not configured."
                        ):
                            raise AIProviderRequestError(normalized)
                        continuation += chunk
                        await on_chunk(chunk)
                except AIProviderRequestError as exc:
                    # A provider failure before any streamed content is a local
                    # unit failure, not a reason to discard the whole course.
                    if continuation or existing_draft:
                        raise
                    generation_source = "deterministic_local_fallback"
                    fallback_reason = f"provider_error:{type(exc).__name__}"
                    continuation = compile_fallback_node_content(node)
                    await on_chunk(continuation)
        finally:
            node["generation_runtime"] = {
                "prompt_chars": len(user_prompt) + len(system_prompt),
                "estimated_input_tokens": input_tokens,
                "prompt_detail_level": (
                    selected_content_prompt.detail_level
                    if selected_content_prompt is not None
                    else "local"
                ),
                "adaptive_compaction": bool(
                    selected_content_prompt is not None
                    and selected_content_prompt.detail_level != "full"
                ),
                "generation_source": generation_source,
                "fallback_reason": fallback_reason or None,
                "max_input_tokens": self._generation_budget.max_input_tokens,
                "max_input_chars": self._generation_budget.max_input_chars,
                "max_output_tokens": (
                    self._generation_budget.content_max_output_tokens
                ),
                "provider_max_attempts": (
                    self._generation_budget.provider_max_attempts
                ),
                "duration_ms": int(
                    (time.monotonic() - started_at) * 1000
                ),
                "output_chars": len(continuation),
                "continued_from_chars": len(existing_draft),
            }

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
        node["needs_manual_review"] = (
            generation_source != "model"
            or any(
                item.get("severity") == "critical"
                for item in quality.get("issues") or []
            )
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
            if int(item.get("node_level") or 1) != 2:
                continue
            key_points = [
                str(point.get("name") if isinstance(point, dict) else point)
                for point in item.get("key_points") or []
            ]
            responsibility = (
                str(item.get("learning_objective") or "").strip()
                or str(item.get("scope_boundary") or "").strip()
                or "按已冻结教案完成本节独立教学责任"
            )
            suffix = (
                f"；知识：{'、'.join(key_points[:4])}"
                if key_points
                else ""
            )
            preceding.append(
                f"- {item.get('node_name', '')}：{responsibility}{suffix}"
            )
        prior_context = (
            "\n".join(preceding[-4:])
            or "- 当前节点之前没有已冻结的小节教学责任。"
        )
        return "\n\n".join([
            material_context,
            "## 已冻结前序教学责任\n" + prior_context,
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
    ) -> AsyncIterator[str]:
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
