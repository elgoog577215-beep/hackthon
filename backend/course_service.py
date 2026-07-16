"""
课程生成服务。

核心职责：
- 将生成需求、参考资料和教学画像编译为课程蓝图
- 使用持久化的节点模块契约流式生成正文
- 对蓝图和正文执行分层质量检查与一次定向修复
- 为用户主动发起的局部重写保留课程与学习上下文
"""

from __future__ import annotations

import asyncio
import inspect
import logging
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
    attach_difficulty_artifacts,
    attach_generation_artifacts_to_plan,
    attach_pedagogy_profile,
    build_course_blueprint_from_plan,
    build_course_generation_artifacts,
    build_node_generation_context,
    build_outline_generation_context,
    normalize_course_plan_contract,
    validate_course_plan_constraints,
)
from course_knowledge_base import (
    bind_course_knowledge_base_to_map,
    compile_course_knowledge_base,
)
from course_knowledge_map import compile_course_knowledge_map, normalize_knowledge_structure
from course_pedagogy import (
    SubjectPedagogyProfile,
    attach_module_plans_to_plan,
    coerce_persisted_profile,
    parse_mode,
    resolve_pedagogy_profile,
)
from course_prompt_composer import (
    PROMPT_CONTRACT_VERSION,
    CoursePromptComposer,
    get_course_prompt_composer,
)
from course_quality import evaluate_node_content, validate_blueprint
from learner_context import DEFAULT_USER_ID
from material_evidence import attach_evidence_to_plan, extract_grounding_annotations
from material_pipeline import prepare_course_materials
from material_storage import MaterialRepository, material_repository
from models import NodeGenerationConfig
from subject_knowledge import knowledge_library_prompt_context

logger = logging.getLogger(__name__)

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
    ) -> None:
        super().__init__()
        self._context_manager = context_manager or get_context_manager()
        self._prompt_composer = prompt_composer or get_course_prompt_composer()
        self._material_repository = materials or material_repository
        self._course_generation_artifacts: dict[str, dict] = {}


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
        style: str = "academic",
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
        existing_course_data: dict[str, Any] | None = None,
        on_phase: Callable[..., Awaitable[None] | None] | None = None,
        on_checkpoint: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
    ) -> dict[str, Any]:
        """Build and validate the persisted course blueprint for one GenerationJob."""
        difficulty = self._parse_difficulty(depth)
        audience = self._parse_audience(target_audience)
        material_inputs = materials or []
        existing = existing_course_data or {}

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
        }
        if checkpoint_ready:
            artifacts = {
                "pipeline_version": existing.get("generation_pipeline_version") or "course_generation_v4",
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
            "generation_status": "difficulty_compiled",
        })

        await self._notify_phase(
            on_phase,
            "pedagogy_resolution",
            32,
            "教学画像与难度契约已确定",
            phase_progress=100,
        )
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
            f"为「{topic}」生成课程蓝图，只输出 JSON。",
            prompt,
            enable_thinking=True,
            on_phase=on_phase,
            phase="pedagogy_resolution",
            base_progress=32,
        )
        plan, plan_constraint_report = self._validated_course_plan(
            response,
            artifacts["course_generation_brief"],
        )
        if not plan_constraint_report.get("passed"):
            await self._notify_phase(
                on_phase,
                "blueprint_generation",
                38,
                "蓝图未通过格式或硬约束检查，正在重新规划",
                phase_progress=40,
                phase_detail={
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
            corrected_response = await self._call_llm(
                f"重新生成「{topic}」课程蓝图，修复上一次的验收问题。",
                correction_prompt,
                enable_thinking=False,
            )
            plan, plan_constraint_report = self._validated_course_plan(
                corrected_response,
                artifacts["course_generation_brief"],
            )
        if not plan_constraint_report.get("passed") or plan is None:
            messages = "；".join(
                str(item.get("message") or "未知蓝图错误")
                for item in plan_constraint_report.get("issues") or []
            )
            raise AIProviderRequestError(
                f"课程蓝图两次未通过结构验收：{messages or '无法解析完整 JSON'}"
            )

        await self._notify_phase(
            on_phase,
            "blueprint_generation",
            42,
            "课程蓝图初稿已生成",
            phase_progress=75,
        )
        plan, evidence_coverage_plan = attach_evidence_to_plan(
            plan,
            evidence=artifacts.get("evidence_catalog") or [],
            bindings=artifacts.get("material_bindings") or [],
            strategy=grounding_strategy,
        )
        artifacts["evidence_coverage_plan"] = evidence_coverage_plan
        plan = attach_generation_artifacts_to_plan(plan, artifacts)
        plan = attach_module_plans_to_plan(plan, profile)
        course_difficulty_curve = attach_difficulty_contracts_to_plan(
            plan,
            profile=difficulty_profile,
            adaptation=adaptation_decision,
        )
        blueprint = build_course_blueprint_from_plan(plan, artifacts)
        blueprint["course_plan_constraint_report"] = plan_constraint_report
        blueprint_report = validate_blueprint(blueprint)
        nodes = self._convert_plan_to_nodes(plan, course_id)

        await self._notify_phase(
            on_phase,
            "blueprint_validation",
            50,
            "课程蓝图和证据覆盖检查完成",
            phase_progress=100,
        )
        course_data = {
            "course_id": course_id,
            "course_name": plan.get("course_title", topic),
            "generation_schema_version": artifacts["pipeline_version"],
            "prompt_contract_version": PROMPT_CONTRACT_VERSION,
            "generation_pipeline_version": artifacts["pipeline_version"],
            "generation_request": {
                "subject": topic,
                "difficulty": difficulty,
                "style": style,
                "requirements": requirements,
                "target_audience": audience,
                "learner_profile_summary": learner_profile_summary,
                "current_readiness": current_readiness,
                "adaptation_preference": adaptation_preference,
                "pedagogy_mode": pedagogy_mode,
                "secondary_mode": secondary_mode,
                "secondary_intensity": secondary_intensity,
                "material_bindings": artifacts.get("material_bindings", []),
                "grounding_strategy": grounding_strategy,
            },
            "difficulty": difficulty,
            "style": style,
            "requirements": requirements,
            "target_audience": audience,
            "subject_pedagogy_profile": profile.to_dict(),
            "difficulty_profile": difficulty_profile.to_dict(),
            "difficulty_gap_assessment": gap_assessment.to_dict(),
            "adaptation_decision": adaptation_decision.to_dict(),
            "course_difficulty_curve": course_difficulty_curve,
            "nodes": nodes,
            "course_plan": plan,
            "knowledge_relations": deepcopy(plan.get("knowledge_relations") or []),
            "material_cards": artifacts["material_cards"],
            "course_generation_brief": artifacts["course_generation_brief"],
            "material_assets": artifacts.get("material_assets", []),
            "material_bindings": artifacts.get("material_bindings", []),
            "parsed_documents": artifacts.get("parsed_documents", []),
            "evidence_index": _compact_evidence_index(artifacts.get("evidence_catalog", [])),
            "evidence_coverage_plan": evidence_coverage_plan,
            "course_blueprint": blueprint,
            "course_plan_constraint_report": plan_constraint_report,
            "blueprint_validation_report": blueprint_report,
            "generation_quality_report": None,
        }
        course_knowledge_map = compile_course_knowledge_map(course_data)
        course_knowledge_base = compile_course_knowledge_base(
            course_data,
            course_map=course_knowledge_map,
        )
        course_knowledge_map = bind_course_knowledge_base_to_map(
            course_knowledge_map,
            course_knowledge_base,
        )
        course_knowledge_base = compile_course_knowledge_base(
            course_data,
            course_map=course_knowledge_map,
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
        self.register_course_generation_metadata(course_id, course_data)
        return course_data

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
    ) -> str | None:
        """Run `_call_llm` while periodically re-announcing the same phase with
        an elapsed-time message, so a slow/degraded AI provider response
        (this call alone can legally take tens of minutes across all model
        candidates' retries — see `ai_base._call_llm`) shows up to the user as
        "still working, Ns elapsed" instead of a progress bar frozen at a flat
        percentage that looks identical to a hang.
        """
        if not on_phase:
            return await self._call_llm(user_prompt, system_prompt, enable_thinking=enable_thinking)

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
                        f"仍在等待 AI 生成课程大纲（已等待约 {elapsed} 秒），AI 服务响应较慢时可能需要几分钟...",
                        phase_progress=100,
                    )

        heartbeat_task = asyncio.create_task(_heartbeat())
        try:
            return await self._call_llm(user_prompt, system_prompt, enable_thinking=enable_thinking)
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
            style=str(kwargs.get("style") or "academic"),
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
        if not quality["passed"]:
            repair_user, repair_system = self._prompt_composer.build_repair_prompt(
                course_data=persisted,
                node=node,
                content=raw_content,
                issues=quality["issues"],
            )
            repaired = await self._call_llm(repair_user, repair_system, enable_thinking=True)
            if repaired:
                repaired_raw = self.clean_response_text(repaired)
                repaired_content, repaired_annotations, repaired_invalid_refs = extract_grounding_annotations(
                    repaired_raw,
                    allowed_ids,
                )
                node["grounding_annotations"] = repaired_annotations
                node["grounding_invalid_refs"] = repaired_invalid_refs
                repaired_quality = evaluate_node_content(repaired_content, node)
                if (
                    repaired_quality.get("passed")
                    or float(repaired_quality.get("score") or 0) > float(quality.get("score") or 0)
                ):
                    raw_content = repaired_raw
                    full_content = repaired_content
                    annotations = repaired_annotations
                    invalid_refs = repaired_invalid_refs
                else:
                    node["grounding_annotations"] = annotations
                    node["grounding_invalid_refs"] = invalid_refs

            # Bug fix: a single repair retry is attempted above, but the fixed
            # content was never re-validated — the node was unconditionally
            # treated as passing afterwards. Re-run the same quality/grounding
            # check on the (possibly) repaired content. If it still fails,
            # do NOT retry again (bounded to one repair attempt) and do NOT
            # silently mark it clean — flag it using the existing weak-node
            # mechanism (`generation_quality.passed == False`) so it surfaces
            # in `build_final_course_quality_report`'s `weak_nodes` list,
            # which is part of the API-visible final quality report.
            quality = evaluate_node_content(full_content, node)
            if not quality["passed"]:
                logger.warning(
                    "Node %s (%s) still fails quality/grounding check after repair; "
                    "flagging for manual review instead of silently completing it.",
                    node_id,
                    node_name,
                )
        node["generation_quality"] = quality
        node["needs_manual_review"] = not quality["passed"]

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
        subject_knowledge_context = knowledge_library_prompt_context(course_name or node_name)

        prompt = f"""## 任务
为「{node_name}」设计小节结构。

## 所属课程
{course_name or "未命名课程"}

{material_context}

## 课程难度能力契约
{format_difficulty_profile(difficulty_profile.to_dict())}

## 可选术语参照
{subject_knowledge_context}

## 知识边界
1. `knowledge_structure` 是当前课程自己的知识蓝图，不是小节标题索引。
2. 每个概念组至少拆出两个原子知识点；知识点必须有独立命题、条件或边界、可观察能力和掌握标准。
3. 可选术语参照只帮助命名，缺失或冲突时不得阻断当前课程，也不得输出外部知识 ID。
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
