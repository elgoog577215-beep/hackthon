"""Versioned product contract shared by every course-generation stage.

The subject template, course type, difficulty and grounding rules are existing
sources of truth.  This module only compiles their immutable projection for one
generation job so bounded parallel calls cannot silently design different
courses.  Stage projections keep prompts focused without losing the shared
product intent.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from course_versioning import stable_hash


COURSE_DESIGN_CONTRACT_VERSION = "course_design_contract_v1"

COURSE_DESIGN_STAGE_KEYS = (
    "outline",
    "outline_expansion",
    "knowledge_identity",
    "knowledge_enrichment",
    "teaching",
    "content",
    "assessment",
)


def compile_course_design_contract(
    *,
    brief: dict[str, Any],
    subject_template: dict[str, Any],
    difficulty_profile: dict[str, Any],
    gap_assessment: dict[str, Any] | None = None,
    adaptation_decision: dict[str, Any] | None = None,
    grounding_strategy: str = "material_first",
) -> dict[str, Any]:
    """Compile one immutable design contract before outline generation."""
    course_type_contract = deepcopy(brief.get("course_type_contract") or {})
    course_intent = deepcopy(brief.get("course_intent") or {})
    learner_starting_profile = deepcopy(
        brief.get("learner_starting_profile") or {}
    )
    architecture_contract = deepcopy(
        subject_template.get("course_architecture_contract") or {}
    )
    knowledge_contract = deepcopy(
        subject_template.get("knowledge_contract") or {}
    )
    lesson_plan_contract = deepcopy(
        subject_template.get("lesson_plan_contract") or {}
    )
    content_contract = deepcopy(
        subject_template.get("content_contract") or {}
    )
    assessment_contract = deepcopy(
        subject_template.get("assessment_contract") or {}
    )

    shared = {
        "course_type": str(brief.get("course_type") or "systematic"),
        "course_type_label": str(
            brief.get("course_type_label") or "系统学习"
        ),
        "audience": str(brief.get("audience") or ""),
        "course_intent": course_intent,
        "learner_starting_profile": learner_starting_profile,
        "course_shape_constraints": deepcopy(
            brief.get("course_shape_constraints") or {}
        ),
        "hard_constraints": list(brief.get("hard_constraints") or []),
        "expected_deliverables": list(
            brief.get("expected_deliverables") or []
        ),
        "difficulty_profile": deepcopy(difficulty_profile),
        "difficulty_gap_assessment": deepcopy(gap_assessment or {}),
        "adaptation_decision": deepcopy(adaptation_decision or {}),
        "grounding_policy": {
            "strategy": grounding_strategy,
            "source_rule": (
                "资料事实只能引用当前证据包中的稳定证据 ID；无证据时明确降低置信度，"
                "不得伪造书名、链接、作者、页码或资料标识"
            ),
            "conflict_rule": (
                "用户资料、准入联网来源与模型常识冲突时保留冲突并等待正式质量门处理，"
                "不得静默覆盖来源"
            ),
        },
    }
    template_ref = {
        "template_id": str(subject_template.get("template_id") or ""),
        "template_version": str(
            subject_template.get("template_version")
            or subject_template.get("schema_version")
            or ""
        ),
        "primary_mode": str(subject_template.get("primary_mode") or ""),
        "subject_variant": deepcopy(
            subject_template.get("subject_variant") or {}
        ),
    }
    stage_contracts = {
        "outline": {
            "responsibility": (
                "确定整门课程的最终成果、章节推进、规模与边界；不生成小节详情、知识、"
                "教案、正文或题目"
            ),
            "course_type_contract": course_type_contract,
            "course_intent": course_intent,
            "learner_starting_profile": learner_starting_profile,
            "subject_architecture_contract": architecture_contract,
            "quality_invariants": [
                "每章只承担一个不重复的能力推进范围",
                "章节顺序同时服从课程类型逻辑、学科依赖和最终成果",
                "用户明确指定的章数与小节总数必须精确满足",
            ],
        },
        "outline_expansion": {
            "responsibility": (
                "在冻结章节边界内展开互不重复、可观察、可验收的小节责任；不修改全课定位"
            ),
            "course_type_contract": course_type_contract,
            "course_intent": course_intent,
            "learner_starting_profile": learner_starting_profile,
            "subject_architecture_contract": architecture_contract,
            "quality_invariants": [
                "每节目标、范围和验收任务必须共同指向同一责任",
                "不得把课程类型退化成通用学科目录",
                "不得提前承担后续小节或相邻章节的核心责任",
            ],
        },
        "knowledge_identity": {
            "responsibility": (
                "为全课建立原子知识身份、唯一所有者、复用与前置关系；不设计课堂或正文"
            ),
            "subject_architecture_contract": architecture_contract,
            "subject_knowledge_contract": knowledge_contract,
            "quality_invariants": [
                "一个知识身份必须能被独立解释、练习、诊断和引用",
                "知识名称不得复制章节标题或写成教学动作",
                "每个知识只允许一个正式负责小节",
            ],
        },
        "knowledge_enrichment": {
            "responsibility": (
                "补全已冻结知识身份的陈述、条件、边界、能力、易错、掌握、来源与正式关系；"
                "不新增知识身份或设计课堂"
            ),
            "subject_knowledge_contract": knowledge_contract,
            "grounding_policy": deepcopy(shared["grounding_policy"]),
            "quality_invariants": [
                "易错必须是可观察的可信错误模式，不能使用模板占位",
                "掌握标准必须描述独立表现、迁移与验证方法",
                "关系必须有语义理由和成立条件，不能用课程先后冒充知识关系",
            ],
        },
        "teaching": {
            "responsibility": (
                "只读消费冻结知识，形成课堂可执行的目标、模块、师生活动、检查与作业；"
                "不新增或改写知识"
            ),
            "course_type_completion_evidence": str(
                course_type_contract.get("completion_evidence") or ""
            ),
            "course_intent": course_intent,
            "subject_lesson_plan_contract": lesson_plan_contract,
            "quality_invariants": [
                "每个模块必须绑定冻结知识和可观察掌握证据",
                "不同课型不得机械复制相同课堂流程",
                "课堂活动必须在课时预算内真实可执行",
            ],
        },
        "content": {
            "responsibility": (
                "把当前小节的冻结知识与正式教案写成可学习正文；不改目录、知识身份或教案"
            ),
            "course_type_organizing_question": str(
                course_type_contract.get("organizing_question") or ""
            ),
            "course_type_completion_evidence": str(
                course_type_contract.get("completion_evidence") or ""
            ),
            "course_intent": course_intent,
            "expected_deliverables": list(
                brief.get("expected_deliverables") or []
            ),
            "subject_content_contract": content_contract,
            "grounding_policy": deepcopy(shared["grounding_policy"]),
            "quality_invariants": [
                "解释、例子、练习与反馈必须共享同一知识口径",
                "正文必须体现当前课型与前后小节的真实差异",
                "来源、事实、推导、示例与教学假设必须清楚区分",
            ],
        },
        "assessment": {
            "responsibility": (
                "依据冻结掌握标准生成可判定、可诊断、可迁移的正式任务；不以术语回忆代替表现"
            ),
            "course_type_completion_evidence": str(
                course_type_contract.get("completion_evidence") or ""
            ),
            "course_intent": course_intent,
            "subject_assessment_contract": assessment_contract,
            "quality_invariants": [
                "每项任务必须说明目标知识、能力、易错与为什么存在",
                "题干、答案、评分标准和输入材料必须相互一致",
                "关键任务必须验证独立表现或变化条件下的迁移",
            ],
        },
    }
    contract = {
        "schema_version": COURSE_DESIGN_CONTRACT_VERSION,
        "contract_version": COURSE_DESIGN_CONTRACT_VERSION,
        "template_ref": template_ref,
        "product_circuit": {
            "sequence": [
                "requirements",
                "outline",
                "knowledge_identity",
                "knowledge_enrichment",
                "knowledge_freeze",
                "teaching",
                "content",
                "assessment_and_quality",
                "release",
            ],
            "user_confirmation_gates": ["outline", "release"],
            "automatic_quality_gates": [
                "knowledge_freeze",
                "teaching_quality",
                "content_quality",
                "assessment_quality",
            ],
        },
        "shared": shared,
        "stage_contracts": stage_contracts,
        "source_revisions": {
            "brief_revision": stable_hash(brief, prefix="brief_"),
            "subject_template_id": template_ref["template_id"],
            "subject_template_version": template_ref["template_version"],
            "difficulty_revision": stable_hash(
                difficulty_profile,
                prefix="difficulty_",
            ),
        },
    }
    contract["revision_id"] = stable_hash(contract, prefix="design_")
    return contract


def project_course_design_contract(
    contract: dict[str, Any] | None,
    stage: str,
) -> dict[str, Any]:
    """Return the one stage projection allowed into a model prompt."""
    source = contract or {}
    if stage not in COURSE_DESIGN_STAGE_KEYS:
        raise ValueError(f"Unknown course design stage: {stage}")
    stage_contract = (
        (source.get("stage_contracts") or {}).get(stage) or {}
    )
    if not stage_contract:
        return {}
    shared_keys_by_stage = {
        "outline": (
            "course_type", "course_type_label", "audience",
            "course_shape_constraints", "hard_constraints",
            "difficulty_profile", "adaptation_decision",
        ),
        "outline_expansion": (
            "course_type", "course_type_label", "audience",
            "hard_constraints", "difficulty_profile",
            "adaptation_decision",
        ),
        "knowledge_identity": (
            "course_type", "course_type_label", "hard_constraints",
        ),
        "knowledge_enrichment": (
            "course_type", "course_type_label", "hard_constraints",
        ),
        "teaching": (
            "course_type", "course_type_label", "audience",
            "hard_constraints", "difficulty_profile",
            "adaptation_decision",
        ),
        "content": (
            "course_type", "course_type_label", "audience",
            "hard_constraints", "difficulty_profile",
            "adaptation_decision",
        ),
        "assessment": (
            "course_type", "course_type_label", "audience",
            "hard_constraints", "difficulty_profile",
        ),
    }
    return {
        "schema_version": str(
            source.get("schema_version") or COURSE_DESIGN_CONTRACT_VERSION
        ),
        "revision_id": str(source.get("revision_id") or ""),
        "template_ref": deepcopy(source.get("template_ref") or {}),
        "shared_constraints": {
            key: deepcopy((source.get("shared") or {}).get(key))
            for key in shared_keys_by_stage[stage]
            if (source.get("shared") or {}).get(key) not in (None, "", [], {})
        },
        "stage": stage,
        "stage_contract": deepcopy(stage_contract),
    }


def course_design_contract_from_course(
    course_data: dict[str, Any],
) -> dict[str, Any]:
    """Read a persisted contract or compile the same projection for old jobs."""
    persisted = course_data.get("course_design_contract")
    if (
        isinstance(persisted, dict)
        and persisted.get("schema_version") == COURSE_DESIGN_CONTRACT_VERSION
        and persisted.get("revision_id")
    ):
        return deepcopy(persisted)
    return compile_course_design_contract(
        brief=deepcopy(course_data.get("course_generation_brief") or {}),
        subject_template=deepcopy(
            course_data.get("subject_generation_template") or {}
        ),
        difficulty_profile=deepcopy(
            course_data.get("difficulty_profile") or {}
        ),
        gap_assessment=deepcopy(
            course_data.get("difficulty_gap_assessment") or {}
        ),
        adaptation_decision=deepcopy(
            course_data.get("adaptation_decision") or {}
        ),
        grounding_strategy=str(
            (course_data.get("course_generation_brief") or {}).get(
                "grounding_strategy"
            )
            or (course_data.get("generation_request") or {}).get(
                "grounding_strategy"
            )
            or "material_first"
        ),
    )


__all__ = [
    "COURSE_DESIGN_CONTRACT_VERSION",
    "COURSE_DESIGN_STAGE_KEYS",
    "compile_course_design_contract",
    "course_design_contract_from_course",
    "project_course_design_contract",
]
