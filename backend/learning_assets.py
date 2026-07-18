"""Deterministic learning-asset planning, compilation, and quality gates."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from course_knowledge_base import (
    bind_course_knowledge_base_to_map,
    build_course_knowledge_library_view,
    compile_course_knowledge_base,
    knowledge_binding_for_section,
    validate_course_knowledge_base,
)
from course_knowledge_map import (
    compile_course_knowledge_map,
    validate_course_knowledge_map,
)
from course_pedagogy import coerce_persisted_profile
from course_versioning import stable_hash
from learning_progress import learning_objective_identity
from practice_contracts import enrich_question_contract
from question_bank import (
    approved_formal_tasks,
    build_question_bank,
    is_generic_generated_prompt,
)
from question_generation import generate_question_contract

ASSET_SCHEMA = "learning_assets_v2"
QUALITY_SCHEMA = "asset_quality_v1"

PURPOSE_ASSETS: dict[str, tuple[str, ...]] = {
    "systematic": (
        "overview", "knowledge_library", "course_knowledge_base", "course_knowledge_map",
        "mastery_criteria", "questions",
        "misconceptions", "checklist", "final_assessment", "chapter_progression_contracts",
    ),
    "exam_sprint": (
        "overview", "knowledge_library", "course_knowledge_base", "course_knowledge_map",
        "mastery_criteria", "questions", "misconceptions",
        "checklist", "final_assessment", "chapter_progression_contracts",
    ),
    "material_organization": (
        "overview", "knowledge_library", "course_knowledge_base", "course_knowledge_map",
        "mastery_criteria", "checklist", "chapter_progression_contracts",
    ),
    "personalized_remedial": (
        "overview", "knowledge_library", "course_knowledge_base", "course_knowledge_map",
        "mastery_criteria", "questions",
        "misconceptions", "checklist", "chapter_progression_contracts",
    ),
}

KNOWLEDGE_INFRASTRUCTURE_ASSETS = {
    "knowledge_library",
    "course_knowledge_base",
    "course_knowledge_map",
}

QUESTION_TYPES = {
    "math_formal": "worked_solution",
    "programming_engineering": "implementation_task",
    "natural_science": "evidence_analysis",
    "life_medical": "mechanism_explanation",
    "humanities_social": "source_argument",
    "language_learning": "language_production",
    "business_career": "scenario_deliverable",
    "general": "short_answer",
}


def compile_learning_asset_plan(course_data: dict[str, Any]) -> dict[str, Any]:
    profile = coerce_persisted_profile(course_data)
    purpose = str(course_data.get("course_purpose") or "systematic")
    requested = list(PURPOSE_ASSETS.get(purpose, PURPOSE_ASSETS["systematic"]))
    preferences = (
        (course_data.get("generation_request") or {}).get("asset_preferences") or {}
    )
    enabled = [
        asset_type for asset_type in requested
        if asset_type in KNOWLEDGE_INFRASTRUCTURE_ASSETS or preferences.get(asset_type, True)
    ]
    contracts = []
    for asset_type in requested:
        required = (
            asset_type in {"overview", "mastery_criteria", "checklist", "chapter_progression_contracts"}
            or asset_type in KNOWLEDGE_INFRASTRUCTURE_ASSETS
            or (purpose != "material_organization" and asset_type == "questions")
            or (purpose != "material_organization" and asset_type == "misconceptions")
            or (purpose in {"systematic", "exam_sprint"} and asset_type == "final_assessment")
        )
        contracts.append({
            "asset_type": asset_type,
            "scope": "course" if asset_type in {"overview", *KNOWLEDGE_INFRASTRUCTURE_ASSETS, "final_assessment"} else "node",
            "required": required,
            "enabled": asset_type in enabled,
            "generation_method": "deterministic_projection" if asset_type in {"overview", "checklist", *KNOWLEDGE_INFRASTRUCTURE_ASSETS} else "contract_compilation",
            "evidence_policy": "source_evidence_required",
            "difficulty_policy": "inherit_node_contract",
            "quality_gates": ["structure", "grounding_difficulty", "discipline", "semantic", "coverage"],
        })
    return {
        "schema_version": "learning_asset_plan_v1",
        "course_purpose": purpose,
        "primary_mode": profile.primary_mode.value,
        "secondary_mode": profile.secondary_mode.value if profile.secondary_mode else None,
        "secondary_intensity": profile.secondary_intensity.value if profile.secondary_intensity else None,
        "enabled_asset_types": enabled,
        "contracts": contracts,
        "reading_only_degraded": "questions" not in enabled,
    }


def compile_learning_assets(
    course_data: dict[str, Any],
    *,
    question_bank_bundle: dict[str, Any] | None = None,
    legacy_tasks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    plan = compile_learning_asset_plan(course_data)
    enabled = set(plan["enabled_asset_types"])
    course_id = str(course_data.get("course_id") or "")
    nodes = [node for node in course_data.get("nodes") or [] if int(node.get("node_level") or 1) == 2]
    profile = coerce_persisted_profile(course_data)
    question_type = QUESTION_TYPES[profile.primary_mode.value]
    for node in nodes:
        objective = learning_objective_identity(course_id, node)
        node["objective_id"] = objective["objective_id"]
        node["objective_revision_id"] = objective["objective_revision_id"]
    # The knowledge identity boundary is the current course.  No shared subject
    # catalog may participate in generation, binding, display, or validation.
    course_map = compile_course_knowledge_map(course_data)
    course_knowledge_base = compile_course_knowledge_base(
        course_data,
        course_map=course_map,
    )
    course_map = bind_course_knowledge_base_to_map(course_map, course_knowledge_base)
    point_by_id = {
        str(item.get("knowledge_id") or ""): item
        for item in course_knowledge_base.get("knowledge_points") or []
    }
    skill_by_id = {
        str(item.get("skill_id") or ""): item
        for item in course_knowledge_base.get("skill_units") or []
    }

    for node in nodes:
        local_binding = knowledge_binding_for_section(
            course_knowledge_base,
            str(node.get("node_id") or ""),
        )
        node["course_knowledge_refs"] = list(local_binding["course_knowledge_refs"])
        node["course_skill_refs"] = list(local_binding["course_skill_refs"])
        node["course_misconception_refs"] = list(local_binding["course_misconception_refs"])
        node["course_mastery_refs"] = list(local_binding["course_mastery_refs"])
    question_bank_course = {
        **deepcopy(course_data),
        "nodes": deepcopy(nodes),
        "subject_pedagogy_profile": profile.to_dict(),
    }
    if question_bank_bundle is None:
        question_bank_bundle = build_question_bank(
            question_bank_course,
            legacy_tasks=legacy_tasks or (),
        )
    else:
        question_bank_bundle = deepcopy(question_bank_bundle)
        if str(question_bank_bundle.get("course_id") or "") != course_id:
            raise ValueError(
                "question bank course scope does not match learning assets"
            )
    bank_practice_items = {
        (
            str(item.get("node_id") or ""),
            str(item.get("practice_level") or ""),
        ): item
        for item in approved_formal_tasks(
            question_bank_bundle,
            assessment_role="practice",
        )
    }

    questions: list[dict[str, Any]] = []
    criteria: list[dict[str, Any]] = []
    misconceptions: list[dict[str, Any]] = []
    diagnostic_templates: list[dict[str, Any]] = []
    remediation_units: list[dict[str, Any]] = []
    validation_questions: list[dict[str, Any]] = []

    for node in nodes:
        node_id = str(node.get("node_id") or "")
        node_name = str(node.get("node_name") or node_id)
        objective = learning_objective_identity(course_id, node)
        local_binding = knowledge_binding_for_section(course_knowledge_base, node_id)
        local_point_ids = local_binding["course_knowledge_refs"]
        key_points = [
            str(point_by_id[point_id].get("name") or "")
            for point_id in local_point_ids
            if point_id in point_by_id
        ]
        evidence_ids = _node_evidence_ids(node)
        concept_ids = list(local_point_ids)
        skill_unit_ids = list(local_binding["course_skill_refs"])
        candidate_mistake_ids = list(local_binding["course_misconception_refs"])
        improvement_point_ids: list[str] = []
        node_questions: list[dict[str, Any]] = []
        for practice_level in ("concept_check", "objective_practice", "mastery_check"):
            bank_item = bank_practice_items.get((node_id, practice_level))
            question_point_ids = _question_knowledge_scope(local_point_ids, practice_level)
            question_point_names = [
                str(point_by_id[point_id].get("name") or "")
                for point_id in question_point_ids
                if point_id in point_by_id
            ]
            question_skill_ids = _unique([
                skill_id
                for skill_id, skill in skill_by_id.items()
                if skill.get("primary_knowledge_id") in question_point_ids
            ])
            question_mistake_ids = _unique([
                item.get("misconception_id")
                for item in course_knowledge_base.get("misconceptions") or []
                if item.get("primary_knowledge_id") in question_point_ids
            ])
            level_question_type = "short_answer" if practice_level == "concept_check" else question_type
            question_id = stable_hash(
                {"course": course_id, "node": node_id, "kind": practice_level},
                prefix="q_",
            )
            question = {
                "asset_id": question_id,
                "question_id": question_id,
                "node_id": node_id,
                "learning_objective": objective["statement"],
                "objective_id": objective["objective_id"],
                "objective_revision_id": objective["objective_revision_id"],
                "concept_ids": question_point_ids,
                "skill_unit_ids": question_skill_ids,
                "misconception_ids": question_mistake_ids,
                "mistake_point_ids": question_mistake_ids,
                "improvement_point_ids": improvement_point_ids,
                "course_knowledge_refs": question_point_ids,
                "course_skill_refs": question_skill_ids,
                "course_misconception_refs": question_mistake_ids,
                "knowledge_binding_scope": (
                    "integrated_section_mastery" if practice_level == "mastery_check"
                    else "focused_knowledge_check"
                ),
                "question_type": level_question_type,
                "prompt": (
                    str(bank_item.get("prompt") or "")
                    if bank_item
                    else _practice_prompt(
                        practice_level,
                        level_question_type,
                        node_name,
                        node,
                        question_point_names,
                    )
                ),
                "answer_spec": (
                    deepcopy(bank_item.get("answer_spec") or {})
                    if bank_item
                    else _practice_answer_spec(
                        practice_level,
                        node_name,
                        node,
                        question_point_names,
                    )
                ),
                "difficulty_contract": deepcopy(node.get("difficulty_contract") or {}),
                "evidence_ids": evidence_ids,
                "source_status": "grounded" if evidence_ids else "course_structure",
                "status": "active",
                "question_bank_item_revision_id": (
                    (
                        bank_item.get(
                            "question_bank_item_revision_id"
                        )
                        or bank_item.get("revision_id")
                    )
                    if bank_item
                    else None
                ),
                "source_type": bank_item.get("source_type") if bank_item else "generated",
                "source_records": deepcopy(bank_item.get("source_records") or []) if bank_item else [],
            }
            if bank_item:
                question["hint_contract"] = deepcopy(bank_item.get("hint_contract") or {})
                question.update({
                    "deliverable": str(bank_item.get("deliverable") or ""),
                    "input_materials": deepcopy(bank_item.get("input_materials") or []),
                    "constraints": deepcopy(bank_item.get("constraints") or []),
                    "result_checks": deepcopy(bank_item.get("result_checks") or []),
                    "question_spec": deepcopy(bank_item.get("question_spec") or {}),
                    "domain_validation": deepcopy(bank_item.get("domain_validation") or {}),
                    "quality_report": deepcopy(bank_item.get("quality_report") or {}),
                    "quality_status": str(
                        (bank_item.get("quality_report") or {}).get("status")
                        or bank_item.get("quality_status")
                        or ""
                    ),
                })
            question = enrich_question_contract(question, practice_level=practice_level)
            question["revision_id"] = _revision_id(question, "qr_")
            node_questions.append(question)
        if "questions" in enabled:
            questions.extend(node_questions)
        mastery_question = node_questions[-1]

        diagnostic_templates.append(_build_diagnostic_template(
            course_data, course_id, node, objective, key_points, concept_ids, skill_unit_ids,
            candidate_mistake_ids, question_type,
        ))
        remediation_units.append(_build_remediation_unit(
            course_data, course_id, node, objective, key_points, concept_ids, skill_unit_ids,
            candidate_mistake_ids, improvement_point_ids,
        ))
        validation_questions.extend([
            _build_validation_question(
                course_data, course_id, node, objective, key_points, concept_ids, skill_unit_ids,
                candidate_mistake_ids, question_type, variant=index,
            )
            for index in (1, 2)
        ])

        criterion_id = stable_hash({"course": course_id, "node": node_id, "criterion": 1}, prefix="mc_")
        criterion = {
            "asset_id": criterion_id,
            "criterion_id": criterion_id,
            "node_id": node_id,
            "learning_objective": mastery_question["learning_objective"],
            "objective_id": objective["objective_id"],
            "objective_revision_id": objective["objective_revision_id"],
            "concept_ids": concept_ids,
            "skill_unit_ids": skill_unit_ids,
            "mistake_point_ids": candidate_mistake_ids,
            "course_knowledge_refs": concept_ids,
            "course_skill_refs": skill_unit_ids,
            "course_misconception_refs": candidate_mistake_ids,
            "course_mastery_refs": list(local_binding["course_mastery_refs"]),
            "observable_performance": _assessment_items(node)[0],
            "subject_task": question_type,
            "pass_threshold": 70,
            "scaffold_condition": (node.get("difficulty_contract") or {}).get("support") or {},
            "assessment_bindings": [mastery_question["revision_id"]] if "questions" in enabled else [],
            "verification_status": "not_started" if "questions" in enabled else "unverified",
        }
        criterion["revision_id"] = _revision_id(criterion, "mcr_")
        if "mastery_criteria" in enabled:
            criteria.append(criterion)

        local_misconceptions = [
            item for item in course_knowledge_base.get("misconceptions") or []
            if item.get("primary_knowledge_id") in local_point_ids
        ]
        for index, raw in enumerate(local_misconceptions):
            misconception_id = str(raw.get("misconception_id") or "")
            item = {
                "asset_id": misconception_id,
                "misconception_id": misconception_id,
                "node_id": node_id,
                "objective_id": objective["objective_id"],
                "objective_revision_id": objective["objective_revision_id"],
                "concept_ids": [raw.get("primary_knowledge_id")],
                "skill_unit_ids": deepcopy(raw.get("skill_ids") or []),
                "mistake_point_ids": [misconception_id],
                "course_knowledge_refs": [raw.get("primary_knowledge_id")],
                "course_skill_refs": deepcopy(raw.get("skill_ids") or []),
                "course_misconception_refs": [misconception_id],
                "error_pattern": raw.get("observable_error_pattern"),
                "trigger": raw.get("confused_with"),
                "cause": raw.get("confused_with"),
                "example": raw.get("observable_error_pattern"),
                "discrimination": raw.get("discrimination"),
                "repair_strategy": raw.get("repair_strategy"),
                "assessment_bindings": [mastery_question["revision_id"]] if "questions" in enabled else [],
                "evidence_ids": evidence_ids,
                "status": "course_common",
                "order": index,
            }
            item["standard_fit"] = "hit"
            item["mistake_point_id"] = misconception_id
            item["revision_id"] = _revision_id(item, "misr_")
            misconceptions.append(item)

    overview = {
        "asset_id": stable_hash({"course": course_id, "kind": "overview"}, prefix="overview_"),
        "course_id": course_id,
        "title": str(course_data.get("course_name") or "课程总览"),
        "purpose": plan["course_purpose"],
        "learning_outcomes": [str(node.get("learning_objective") or node.get("node_name") or "") for node in nodes],
        "chapter_count": len([node for node in course_data.get("nodes") or [] if int(node.get("node_level") or 1) == 1]),
        "node_count": len(nodes),
        "final_task": _final_task(profile.primary_mode.value, course_data),
    }
    overview["revision_id"] = _revision_id(overview, "ovr_")

    checklist = []
    for criterion in criteria:
        item = {
            "asset_id": stable_hash({"criterion": criterion["criterion_id"], "kind": "checklist"}, prefix="check_"),
            "criterion_id": criterion["criterion_id"],
            "criterion_revision_id": criterion["revision_id"],
            "node_id": criterion["node_id"],
            "objective_id": criterion.get("objective_id"),
            "objective_revision_id": criterion.get("objective_revision_id"),
            "label": criterion["observable_performance"],
            "status": criterion["verification_status"],
        }
        item["revision_id"] = _revision_id(item, "checkr_")
        checklist.append(item)

    chapter_progression_contracts = _build_chapter_progression_contracts(course_data, nodes)

    assets = {
        "overview": [overview] if "overview" in enabled else [],
        "questions": questions,
        "course_knowledge_base": [],
        "course_knowledge_map": [course_map] if "course_knowledge_map" in enabled else [],
        "knowledge_library": [],
        "mastery_criteria": criteria,
        "misconceptions": misconceptions if "misconceptions" in enabled else [],
        "checklist": checklist if "checklist" in enabled else [],
        "final_assessment": [
            deepcopy(item["formal_task"])
            for item in question_bank_bundle.get("items") or []
            if item.get("assessment_role") in {
                "coverage_task",
                "cross_chapter_transfer",
            }
            and isinstance(item.get("formal_task"), dict)
        ] if "final_assessment" in enabled else [],
        "diagnostic_templates": diagnostic_templates if "questions" in enabled else [],
        "remediation_units": remediation_units if "questions" in enabled else [],
        "validation_questions": validation_questions if "questions" in enabled else [],
        "chapter_progression_contracts": (
            chapter_progression_contracts if "chapter_progression_contracts" in enabled else []
        ),
    }
    course_knowledge_base = compile_course_knowledge_base(
        course_data,
        course_map=course_map,
        assets=assets,
    )
    _attach_course_knowledge_refs_to_blocks(course_data, course_knowledge_base)
    _attach_course_knowledge_refs(assets, course_knowledge_base)
    if "course_knowledge_base" in enabled:
        assets["course_knowledge_base"] = [course_knowledge_base]
    knowledge_view = build_course_knowledge_library_view(
        course_knowledge_base,
        course_map,
        assets,
        course_data,
    )
    if "knowledge_library" in enabled:
        assets["knowledge_library"] = [knowledge_view]
    quality = evaluate_learning_asset_quality(course_data, plan, assets)
    return {
        "schema_version": ASSET_SCHEMA,
        "plan": plan,
        "assets": assets,
        "quality_report": quality,
        "question_bank_bundle": question_bank_bundle,
        "compiled_at": datetime.now().isoformat(),
    }


def evaluate_learning_asset_quality(
    course_data: dict[str, Any],
    plan: dict[str, Any],
    assets: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    required = {
        item["asset_type"] for item in plan.get("contracts") or []
        if item.get("required") and item.get("enabled")
    }
    for asset_type in required:
        if not assets.get(asset_type):
            issues.append(_asset_issue("structure", "critical", asset_type, "必选资产为空"))

    course_map = next(iter(assets.get("course_knowledge_map") or []), None)
    if course_map:
        for map_issue in validate_course_knowledge_map(course_map, course_data, assets):
            if (
                assets.get("course_knowledge_base")
                and map_issue.get("severity") != "critical"
                and "课程局部知识待归一" in str(map_issue.get("message") or "")
            ):
                continue
            issues.append(_asset_issue(
                map_issue["gate"],
                map_issue["severity"],
                "course_knowledge_map",
                map_issue["message"],
                course_map,
            ))

    course_knowledge_base = next(iter(assets.get("course_knowledge_base") or []), None)
    if course_knowledge_base:
        knowledge_report = validate_course_knowledge_base(
            course_knowledge_base,
            course_data=course_data,
            library={},
        )
        for issue in knowledge_report.get("issues") or []:
            issues.append(_asset_issue(
                str(issue.get("gate") or "structure"),
                str(issue.get("severity") or "major"),
                "course_knowledge_base",
                str(issue.get("message") or "课程知识库质量问题"),
                course_knowledge_base,
            ))

    knowledge_view = next(iter(assets.get("knowledge_library") or []), None)
    if knowledge_view:
        valid_refs = {
            "concept_ids": {str(item.get("knowledge_id")) for item in knowledge_view.get("nodes") or []},
            "skill_unit_ids": {str(item.get("skill_unit_id")) for item in knowledge_view.get("skill_units") or []},
            "mistake_point_ids": {str(item.get("mistake_point_id")) for item in knowledge_view.get("mistake_points") or []},
            "improvement_point_ids": {str(item.get("improvement_point_id")) for item in knowledge_view.get("improvement_points") or []},
        }
        for asset_type, items in assets.items():
            if asset_type in {"knowledge_library", "course_knowledge_base", "course_knowledge_map"}:
                continue
            for item in items or []:
                if not isinstance(item, dict):
                    continue
                for field, allowed in valid_refs.items():
                    unknown = {str(value) for value in item.get(field) or []} - allowed
                    if unknown:
                        issues.append(_asset_issue(
                            "structure",
                            "critical",
                            asset_type,
                            f"资产引用了不存在的统一知识库条目：{field}={sorted(unknown)}",
                            item,
                        ))

    if course_knowledge_base:
        local_refs = {
            "course_knowledge_refs": {
                str(item.get("knowledge_id") or "")
                for item in course_knowledge_base.get("knowledge_points") or []
            },
            "course_skill_refs": {
                str(item.get("skill_id") or "")
                for item in course_knowledge_base.get("skill_units") or []
            },
            "course_misconception_refs": {
                str(item.get("misconception_id") or "")
                for item in course_knowledge_base.get("misconceptions") or []
            },
            "course_mastery_refs": {
                str(item.get("criterion_id") or "")
                for item in course_knowledge_base.get("mastery_criteria") or []
            },
        }
        for asset_type, items in assets.items():
            if asset_type in {"knowledge_library", "course_knowledge_base", "course_knowledge_map"}:
                continue
            for item in items or []:
                if not isinstance(item, dict):
                    continue
                for field, allowed in local_refs.items():
                    unknown = {str(value) for value in item.get(field) or []} - allowed
                    if unknown:
                        issues.append(_asset_issue(
                            "structure",
                            "critical",
                            asset_type,
                            f"资产引用了不存在的课程知识条目：{field}={sorted(unknown)}",
                            item,
                        ))

    allowed_evidence = {
        str(item.get("evidence_id") or "")
        for item in (course_data.get("evidence_catalog") or course_data.get("evidence_index") or [])
    }
    for question in assets.get("questions") or []:
        if not question.get("revision_id") or not question.get("node_id") or not question.get("answer_spec"):
            issues.append(_asset_issue("structure", "critical", "questions", "题目缺少稳定修订、节点或答案量规", question))
        invalid = set(question.get("evidence_ids") or []) - allowed_evidence
        if invalid:
            issues.append(_asset_issue("grounding_difficulty", "critical", "questions", f"题目引用无效证据：{sorted(invalid)}", question))
        if not question.get("difficulty_contract"):
            issues.append(_asset_issue("grounding_difficulty", "major", "questions", "题目缺少节点难度契约", question))
        if not question.get("practice_contract_revision_id") or not question.get("input_contract"):
            issues.append(_asset_issue("structure", "critical", "questions", "题目缺少正式练习契约", question))
        hint_levels = ((question.get("hint_contract") or {}).get("levels") or [])
        if [item.get("level") for item in hint_levels] != [1, 2, 3]:
            issues.append(_asset_issue("discipline", "major", "questions", "题目必须提供顺序明确的三级提示", question))
        answer_spec = question.get("answer_spec") or {}
        if not answer_spec.get("criteria") or not answer_spec.get("expected_keywords"):
            issues.append(_asset_issue("discipline", "major", "questions", "答案量规不可执行", question))
        criteria_text = " ".join(str(item) for item in answer_spec.get("criteria") or [])
        if question.get("practice_level") == "concept_check":
            focus = str(next(iter(answer_spec.get("expected_keywords") or []), ""))
            if focus and focus not in criteria_text:
                issues.append(_asset_issue("semantic", "critical", "questions", "理解检查量规与题目焦点不一致", question))
        if question.get("practice_level") == "objective_practice" and not all(
            marker in criteria_text for marker in ("依据", "过程", "检查")
        ):
            issues.append(_asset_issue("semantic", "critical", "questions", "目标练习量规缺少依据、过程或结果检查", question))
        prompt = str(question.get("prompt") or "")
        if (
            question.get("source_type") in {"generated", "variant"}
            and is_generic_generated_prompt(prompt)
        ):
            issues.append(_asset_issue(
                "semantic",
                "critical",
                "questions",
                "生成题仍是缺少具体输入、约束或结果检查的宽泛模板",
                question,
            ))
        if question.get("practice_level") == "mastery_check":
            question_spec = question.get("question_spec") or {}
            target = question_spec.get("target") or {}
            task = question_spec.get("task") or {}
            if (
                not target.get("assessment_actions")
                or not str(task.get("rendered_text") or "").strip()
                or not str(task.get("deliverable") or "").strip()
            ):
                issues.append(_asset_issue(
                    "semantic",
                    "critical",
                    "questions",
                    "掌握题缺少内部评测目标或明确任务产物",
                    question,
                ))
        if len(prompt) < 12 or any(marker in prompt for marker in ("以下哪项", "随便谈谈", "待补充")):
            issues.append(_asset_issue("semantic", "major", "questions", "题目语义过弱或含占位表达", question))

    required_objectives = {
        str(node.get("objective_id") or "")
        for node in course_data.get("nodes") or []
        if int(node.get("node_level") or 1) == 2 and node.get("objective_id")
    }
    final_objectives: set[str] = set()
    for task in assets.get("final_assessment") or []:
        final_objectives.update(
            str(value)
            for value in [
                task.get("objective_id"),
                *(task.get("course_objective_refs") or []),
            ]
            if value
        )
        has_private_solution_ref = bool(
            (task.get("question_spec") or {}).get(
                "schema_version"
            )
            == "question_spec_v2"
            and task.get("solution_revision_id")
        )
        if (
            not task.get("revision_id")
            or (
                not task.get("answer_spec")
                and not has_private_solution_ref
            )
            or not task.get("practice_contract_revision_id")
            or not task.get("input_contract")
        ):
            issues.append(_asset_issue(
                "structure",
                "critical",
                "final_assessment",
                "综合测评任务缺少稳定修订、答案量规或正式练习契约",
                task,
            ))
        if not task.get("deliverable") or not task.get("input_materials") or not task.get("constraints"):
            issues.append(_asset_issue(
                "semantic",
                "critical",
                "final_assessment",
                "综合测评任务必须包含最终产物、输入材料和限制条件",
                task,
            ))
        if task.get("assessment_role") not in {"coverage_task", "cross_chapter_transfer"}:
            issues.append(_asset_issue(
                "structure",
                "major",
                "final_assessment",
                "综合测评任务缺少覆盖或跨章节角色",
                task,
            ))
        if not (task.get("quality_report") or {}).get("passed"):
            issues.append(_asset_issue(
                "semantic",
                "critical",
                "final_assessment",
                "综合测评任务未通过与普通题一致的质量检查",
                task,
            ))
        if task.get("review_status") != "approved":
            issues.append(_asset_issue(
                "discipline",
                "review_required",
                "final_assessment",
                "综合测评任务等待教师确认，确认前不会对学生开放",
                task,
            ))
    if assets.get("final_assessment") and required_objectives - final_objectives:
        issues.append(_asset_issue(
            "coverage",
            "critical",
            "final_assessment",
            f"综合测评未覆盖必需目标：{sorted(required_objectives - final_objectives)}",
        ))

    learning_nodes = [
        node for node in course_data.get("nodes") or []
        if int(node.get("node_level") or 1) == 2
    ]
    for node in learning_nodes:
        blocks = node.get("content_blocks") or []
        if not blocks:
            issues.append(_asset_issue(
                "structure",
                "critical",
                "content_blocks",
                f"节点 {node.get('node_id') or ''} 没有持久内容块",
                node,
            ))
            continue
        if any(
            not block.get("block_id")
            or not block.get("content_fingerprint")
            or not block.get("block_revision_id")
            for block in blocks
        ):
            issues.append(_asset_issue(
                "structure",
                "critical",
                "content_blocks",
                f"节点 {node.get('node_id') or ''} 的内容块缺少稳定修订",
                node,
            ))

    chapter_groups = _chapter_groups(course_data, learning_nodes)
    progression_contracts = assets.get("chapter_progression_contracts") or []
    progression_by_chapter = {
        str(item.get("chapter_id") or ""): item
        for item in progression_contracts
        if item.get("chapter_id")
    }
    objective_ids = {
        str(node.get("objective_id") or "") for node in learning_nodes if node.get("objective_id")
    }
    for chapter in chapter_groups:
        chapter_id = chapter["chapter_id"]
        contract = progression_by_chapter.get(chapter_id)
        if not contract:
            issues.append(_asset_issue(
                "coverage",
                "critical",
                "chapter_progression_contracts",
                f"章节 {chapter_id} 缺少推进契约",
            ))
            continue
        required_objectives = {
            str(item) for item in contract.get("required_objective_ids") or [] if item
        }
        expected_objectives = {
            str(node.get("objective_id") or "")
            for node in chapter["nodes"]
            if node.get("objective_id")
        }
        if (
            not contract.get("revision_id")
            or not contract.get("prerequisite_policy")
            or not contract.get("completion_policy")
            or not required_objectives
            or not required_objectives <= objective_ids
            or required_objectives != expected_objectives
        ):
            issues.append(_asset_issue(
                "structure",
                "critical",
                "chapter_progression_contracts",
                f"章节 {chapter_id} 的推进契约缺少修订、策略或有效目标引用",
                contract,
            ))

    formal_prompts = {" ".join(str(item.get("prompt") or "").split()) for item in assets.get("questions") or []}
    for task in [*(assets.get("diagnostic_templates") or []), *(assets.get("validation_questions") or [])]:
        if not task.get("revision_id") or not task.get("practice_contract_revision_id"):
            issues.append(_asset_issue("structure", "critical", "diagnostic_remediation", "诊断或验证任务缺少稳定契约", task))
        prompt = " ".join(str(task.get("prompt") or "").split())
        if task.get("practice_level") == "remediation_validation" and prompt in formal_prompts:
            issues.append(_asset_issue("semantic", "critical", "diagnostic_remediation", "保留验证题不得复用已展示正式题目", task))
        if task.get("quality_status") != "passed":
            issues.append(_asset_issue("semantic", "major", "diagnostic_remediation", "诊断或验证任务未通过质量门", task))
    for unit in assets.get("remediation_units") or []:
        if not unit.get("revision_id") or not unit.get("remediation_objective") or not unit.get("guided_task"):
            issues.append(_asset_issue("structure", "critical", "remediation_units", "补救单元缺少目标、任务或修订", unit))

    node_ids = {str(node.get("node_id") or "") for node in course_data.get("nodes") or [] if int(node.get("node_level") or 1) == 2}
    covered = {str(item.get("node_id") or "") for item in assets.get("mastery_criteria") or []}
    if "mastery_criteria" in required and node_ids - covered:
        issues.append(_asset_issue("coverage", "critical", "mastery_criteria", f"未覆盖节点：{sorted(node_ids - covered)}"))
    question_nodes = {str(item.get("node_id") or "") for item in assets.get("questions") or []}
    if "questions" in required and node_ids - question_nodes:
        issues.append(_asset_issue("coverage", "critical", "questions", f"未覆盖节点：{sorted(node_ids - question_nodes)}"))

    report = {
        "schema_version": QUALITY_SCHEMA,
        "passed": False,
        "gates": [],
        "issues": issues,
        "blocking_issues": [],
        "warnings": [],
        "semantic_repair_attempts": 0,
        "asset_counts": {key: len(value) for key, value in assets.items()},
    }
    _refresh_quality_status(report)
    return report


def _practice_prompt(
    practice_level: str,
    question_type: str,
    node_name: str,
    node: dict[str, Any],
    knowledge_names: list[str] | None = None,
) -> str:
    knowledge_names = knowledge_names or []
    if practice_level == "concept_check":
        key_point = next(iter(knowledge_names), node_name)
        return f"用自己的话说明“{key_point}”的含义，并指出它在“{node_name}”中成立或适用的关键条件。"
    if practice_level == "objective_practice":
        focus = "、".join(knowledge_names) or node_name
        return f"在一个不同于正文示例的新情境中应用“{focus}”，说明选择方法的依据、执行过程和结果检查。"
    return _question_prompt(question_type, node_name, node)


def _practice_answer_spec(
    practice_level: str,
    node_name: str,
    node: dict[str, Any],
    key_points: list[str],
) -> dict[str, Any]:
    focus = key_points[0] if key_points else node_name
    if practice_level == "concept_check":
        criteria = [
            f"准确说明“{focus}”的核心含义",
            "指出成立条件、适用边界或关键前提",
            "表达清楚且不混淆相近概念",
        ]
        expected = [focus, *key_points[1:3]]
    elif practice_level == "objective_practice":
        criteria = [
            f"在新情境中正确应用“{node_name}”并说明方法依据",
            "给出可检查的执行过程或推理过程",
            "检查结果并说明条件或局限",
        ]
        expected = key_points[:6]
    else:
        criteria = _assessment_items(node)
        expected = key_points[:6]
    return {
        "type": "rubric",
        "expected_keywords": list(dict.fromkeys(expected)),
        "criteria": criteria,
        "max_score": 100,
        "pass_score": 70,
    }


def _question_knowledge_scope(
    point_ids: list[str],
    practice_level: str,
) -> list[str]:
    """Keep checks narrow unless the contract explicitly asks for integration."""
    if practice_level == "concept_check":
        return point_ids[:1]
    if practice_level == "objective_practice":
        return point_ids[:2]
    return list(point_ids)


def _question_prompt(question_type: str, node_name: str, node: dict[str, Any]) -> str:
    tasks = _assessment_items(node)
    task = tasks[0] if len(tasks) == 1 else "；".join(
        f"（{index}）{item}" for index, item in enumerate(tasks, start=1)
    )
    templates = {
        "worked_solution": f"围绕“{node_name}”完成推导或求解，并逐步说明依据、条件和结果检查。任务：{task}",
        "implementation_task": f"围绕“{node_name}”完成一个可运行实现，说明输入、输出、关键机制和验证方法。任务：{task}",
        "evidence_analysis": f"围绕“{node_name}”区分观察、模型与结论，并用证据说明适用边界。任务：{task}",
        "mechanism_explanation": f"围绕“{node_name}”按结构、功能和机制解释过程，并指出正常边界。任务：{task}",
        "source_argument": f"围绕“{node_name}”形成一个有材料依据的论证，说明观点、证据和可能异议。任务：{task}",
        "language_production": f"在“{node_name}”对应的真实语境中完成表达，确保意义准确、用法得体。任务：{task}",
        "scenario_deliverable": f"在“{node_name}”对应的工作场景中提交可检查成果，说明约束、取舍和指标。任务：{task}",
        "short_answer": f"解释“{node_name}”的核心概念，并用一个新情境说明如何判断或应用。任务：{task}",
    }
    return templates[question_type]


def _assessment_items(node: dict[str, Any]) -> list[str]:
    values = [str(item).strip() for item in node.get("assessment") or [] if str(item).strip()]
    return values or [str(node.get("learning_objective") or f"能够解释并应用 {node.get('node_name') or '本节内容'}")]


def _node_evidence_ids(node: dict[str, Any]) -> list[str]:
    contract = node.get("grounding_contract") or {}
    return list(dict.fromkeys([
        *[str(item) for item in contract.get("required_evidence_ids") or []],
        *[str(item) for item in contract.get("optional_evidence_ids") or []],
    ]))


def _final_task(mode: str, course_data: dict[str, Any]) -> str:
    title = str(course_data.get("course_name") or "本课程")
    labels = {
        "math_formal": "完成一组需要推导、证明或建模的综合问题",
        "programming_engineering": "交付一个可运行、可测试并能解释取舍的工程成果",
        "natural_science": "用模型和证据解释或预测一个综合现象",
        "life_medical": "用结构、功能和机制分析一个基础案例",
        "humanities_social": "基于材料形成可回应异议的完整论证",
        "language_learning": "在目标场景中完成真实、得体的综合表达",
        "business_career": "提交一份满足约束和评价指标的工作成果",
        "general": "解释核心概念并完成跨章节应用任务",
    }
    return f"{title}：{labels[mode]}"


def _build_final_assessment(
    course_id: str,
    mode: str,
    nodes: list[dict[str, Any]],
    questions: list[dict[str, Any]],
    concept_ids: list[str],
    skill_unit_ids: list[str],
    mistake_point_ids: list[str],
    improvement_point_ids: list[str],
) -> dict[str, Any]:
    item = {
        "asset_id": stable_hash({"course": course_id, "kind": "final_assessment"}, prefix="final_"),
        "question_type": QUESTION_TYPES[mode],
        "prompt": "综合运用全部章节完成最终任务，并明确说明跨章节连接、证据和自检过程。",
        "node_ids": [str(node.get("node_id") or "") for node in nodes],
        "concept_ids": concept_ids,
        "skill_unit_ids": skill_unit_ids,
        "mistake_point_ids": mistake_point_ids,
        "improvement_point_ids": improvement_point_ids,
        "question_revision_ids": [item["revision_id"] for item in questions],
        "answer_spec": {"type": "rubric", "criteria": ["跨章节整合", "证据或依据", "结果验证"], "pass_score": 70},
    }
    item = enrich_question_contract(item, practice_level="final_assessment")
    item["revision_id"] = _revision_id(item, "finalr_")
    return item


def _build_diagnostic_template(
    course_data: dict[str, Any],
    course_id: str,
    node: dict[str, Any],
    objective: dict[str, Any],
    key_points: list[str],
    concept_ids: list[str],
    skill_unit_ids: list[str],
    mistake_point_ids: list[str],
    question_type: str,
) -> dict[str, Any]:
    contract = generate_question_contract(
        course_data,
        node,
        "concept_check",
        6,
    )
    item = {
        "asset_id": stable_hash({"course": course_id, "node": node.get("node_id"), "kind": "diagnostic_template"}, prefix="dt_"),
        "node_id": node.get("node_id"),
        "learning_objective": objective["statement"],
        "objective_id": objective["objective_id"],
        "objective_revision_id": objective["objective_revision_id"],
        "concept_ids": concept_ids,
        "skill_unit_ids": skill_unit_ids,
        "mistake_point_ids": mistake_point_ids,
        "question_type": contract["question_type"],
        "prompt": contract["prompt"],
        "answer_spec": deepcopy(contract["answer_spec"]),
        "practice_level": "diagnostic_probe",
        "source_status": "course_structure",
        "source_type": "generated",
        "source_records": deepcopy(contract.get("source_records") or []),
        "deliverable": contract["deliverable"],
        "input_materials": deepcopy(contract["input_materials"]),
        "constraints": deepcopy(contract["constraints"]),
        "result_checks": deepcopy(contract["result_checks"]),
        "question_spec": deepcopy(contract["question_spec"]),
        "domain_validation": deepcopy(contract["domain_validation"]),
    }
    item = enrich_question_contract(item, practice_level="diagnostic_probe")
    item["quality_report"] = _evaluate_generated_task_quality(item)
    item["quality_status"] = item["quality_report"]["status"]
    item["revision_id"] = _revision_id(item, "dtr_")
    return item


def _build_remediation_unit(
    course_data: dict[str, Any],
    course_id: str,
    node: dict[str, Any],
    objective: dict[str, Any],
    key_points: list[str],
    concept_ids: list[str],
    skill_unit_ids: list[str],
    mistake_point_ids: list[str],
    improvement_point_ids: list[str],
) -> dict[str, Any]:
    focus = key_points[0] if key_points else str(node.get("node_name") or "当前概念")
    misconception = next(iter(node.get("misconceptions") or []), "混淆适用条件或关键步骤")
    contract = generate_question_contract(
        course_data,
        node,
        "objective_practice",
        7,
    )
    guided = {
        "node_id": node.get("node_id"),
        "learning_objective": objective["statement"],
        "objective_id": objective["objective_id"],
        "objective_revision_id": objective["objective_revision_id"],
        "concept_ids": concept_ids,
        "skill_unit_ids": skill_unit_ids,
        "mistake_point_ids": mistake_point_ids,
        "improvement_point_ids": improvement_point_ids,
        "question_type": contract["question_type"],
        "prompt": contract["prompt"],
        "answer_spec": deepcopy(contract["answer_spec"]),
        "practice_level": "remediation_guided",
        "source_type": "generated",
        "source_records": deepcopy(contract.get("source_records") or []),
        "deliverable": contract["deliverable"],
        "input_materials": deepcopy(contract["input_materials"]),
        "constraints": deepcopy(contract["constraints"]),
        "result_checks": deepcopy(contract["result_checks"]),
        "question_spec": deepcopy(contract["question_spec"]),
        "domain_validation": deepcopy(contract["domain_validation"]),
    }
    guided = enrich_question_contract(guided, practice_level="remediation_guided")
    guided["revision_id"] = _revision_id(guided, "rgtr_")
    item = {
        "asset_id": stable_hash({"course": course_id, "node": node.get("node_id"), "kind": "remediation_unit"}, prefix="ru_"),
        "node_id": node.get("node_id"),
        "objective_id": objective["objective_id"],
        "objective_revision_id": objective["objective_revision_id"],
        "concept_ids": concept_ids,
        "skill_unit_ids": skill_unit_ids,
        "mistake_point_ids": mistake_point_ids,
        "improvement_point_ids": improvement_point_ids,
        "category": "boundary_confusion" if node.get("misconceptions") else "concept_gap",
        "remediation_objective": f"澄清“{focus}”的必要条件与适用边界",
        "micro_explanation": f"围绕“{focus}”只检查定义、必要条件和容易混淆的边界。",
        "worked_contrast": f"对比正确使用条件与常见误区：{misconception}",
        "content_block_ids": [str(item.get("block_id")) for item in node.get("content_blocks") or [] if item.get("block_id")][:3],
        "guided_task": guided,
        "source_status": "course_structure",
    }
    item["revision_id"] = _revision_id(item, "rur_")
    return item


def _build_validation_question(
    course_data: dict[str, Any],
    course_id: str,
    node: dict[str, Any],
    objective: dict[str, Any],
    key_points: list[str],
    concept_ids: list[str],
    skill_unit_ids: list[str],
    mistake_point_ids: list[str],
    question_type: str,
    *,
    variant: int,
) -> dict[str, Any]:
    contract = generate_question_contract(
        course_data,
        node,
        "mastery_check",
        10 + variant,
    )
    item = {
        "asset_id": stable_hash({"course": course_id, "node": node.get("node_id"), "kind": "validation", "variant": variant}, prefix="rvq_"),
        "node_id": node.get("node_id"),
        "learning_objective": objective["statement"],
        "objective_id": objective["objective_id"],
        "objective_revision_id": objective["objective_revision_id"],
        "concept_ids": concept_ids,
        "skill_unit_ids": skill_unit_ids,
        "mistake_point_ids": mistake_point_ids,
        "question_type": contract["question_type"],
        "prompt": contract["prompt"],
        "answer_spec": deepcopy(contract["answer_spec"]),
        "practice_level": "remediation_validation",
        "validation_variant": variant,
        "source_status": "course_structure",
        "source_type": "generated",
        "source_records": deepcopy(contract.get("source_records") or []),
        "deliverable": contract["deliverable"],
        "input_materials": deepcopy(contract["input_materials"]),
        "constraints": deepcopy(contract["constraints"]),
        "result_checks": deepcopy(contract["result_checks"]),
        "question_spec": deepcopy(contract["question_spec"]),
        "domain_validation": deepcopy(contract["domain_validation"]),
        "validation_policy": {
            "mastery_eligible": True,
            "max_support_level_for_mastery": 0,
            "requires_unseen_validation_after_solution": True,
        },
    }
    item = enrich_question_contract(item, practice_level="remediation_validation")
    item["quality_report"] = _evaluate_generated_task_quality(item)
    item["quality_status"] = item["quality_report"]["status"]
    item["revision_id"] = _revision_id(item, "rvtr_")
    return item


def _build_chapter_progression_contracts(
    course_data: dict[str, Any],
    learning_nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    purpose = str(course_data.get("course_purpose") or "systematic")
    mastery_required = purpose in {"systematic", "exam_sprint", "personalized_remedial"}
    contracts: list[dict[str, Any]] = []
    for chapter in _chapter_groups(course_data, learning_nodes):
        children = chapter["nodes"]
        required_objective_ids = [
            str(node.get("objective_id") or "") for node in children if node.get("objective_id")
        ]
        has_prerequisites = any(node.get("prerequisite_node_ids") for node in children)
        item = {
            "asset_id": stable_hash(
                {"course": course_data.get("course_id"), "chapter": chapter["chapter_id"], "kind": "progression"},
                prefix="cpc_",
            ),
            "chapter_id": chapter["chapter_id"],
            "chapter_name": chapter["chapter_name"],
            "required_objective_ids": required_objective_ids,
            "mastery_required": mastery_required,
            "prerequisite_policy": "required" if has_prerequisites else "advisory",
            "completion_policy": "reading_and_mastery" if mastery_required else "reading_covered",
            "status": "active",
        }
        item["revision_id"] = _revision_id(item, "cpcr_")
        contracts.append(item)
    return contracts


def _chapter_groups(
    course_data: dict[str, Any],
    learning_nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    chapters = [
        node for node in course_data.get("nodes") or []
        if int(node.get("node_level") or 1) == 1
    ]
    groups: list[dict[str, Any]] = []
    assigned: set[str] = set()
    for chapter in chapters:
        chapter_id = str(chapter.get("node_id") or "")
        children = [
            node for node in learning_nodes
            if str(node.get("parent_node_id") or "") == chapter_id
        ]
        if not chapter_id or not children:
            continue
        assigned.update(str(node.get("node_id") or "") for node in children)
        groups.append({
            "chapter_id": chapter_id,
            "chapter_name": str(chapter.get("node_name") or chapter_id),
            "nodes": children,
        })
    for node in learning_nodes:
        node_id = str(node.get("node_id") or "")
        if not node_id or node_id in assigned:
            continue
        groups.append({
            "chapter_id": node_id,
            "chapter_name": str(node.get("node_name") or node_id),
            "nodes": [node],
        })
    return groups


def _evaluate_generated_task_quality(
    task: dict[str, Any],
    *,
    previously_shown_prompts: set[str] | None = None,
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    prompt = " ".join(str(task.get("prompt") or "").split())
    answer_spec = task.get("answer_spec") or {}
    if len(prompt) < 12:
        issues.append({"code": "task:prompt_too_short", "severity": "critical"})
    if not answer_spec.get("criteria") and answer_spec.get("correct_answer") is None:
        issues.append({"code": "task:answer_not_executable", "severity": "critical"})
    if not task.get("practice_contract_revision_id") or not task.get("input_contract"):
        issues.append({"code": "task:practice_contract_missing", "severity": "critical"})
    levels = (task.get("hint_contract") or {}).get("levels") or []
    if [level.get("level") for level in levels] != [1, 2, 3]:
        issues.append({"code": "task:hint_levels_invalid", "severity": "major"})
    if not (task.get("hint_contract") or {}).get("leakage_check", {}).get("passed", True):
        issues.append({"code": "task:hint_leaks_answer", "severity": "critical"})
    if previously_shown_prompts and prompt in previously_shown_prompts:
        issues.append({"code": "task:not_unseen", "severity": "critical"})
    if (
        task.get("source_type") in {"generated", "variant"}
        and is_generic_generated_prompt(prompt)
    ):
        issues.append({"code": "task:generic_prompt", "severity": "critical"})
    if task.get("source_type") in {"generated", "variant"}:
        question_spec = task.get("question_spec") or {}
        domain_validation = task.get("domain_validation") or {}
        if question_spec.get("schema_version") != "question_spec_v1":
            issues.append({"code": "task:question_spec_missing", "severity": "critical"})
        if not domain_validation.get("passed"):
            issues.append({"code": "task:domain_validation_failed", "severity": "critical"})
    critical = [item for item in issues if item["severity"] == "critical"]
    return {
        "schema_version": "generated_task_quality_v1",
        "passed": not critical,
        "status": "failed" if critical else ("needs_review" if issues else "passed"),
        "issues": issues,
    }


def _refresh_quality_status(report: dict[str, Any]) -> None:
    issues = list(report.get("issues") or [])
    warnings = [
        item for item in issues
        if (
            item.get("severity") in {"warning", "review_required"}
            or (
                item.get("asset_type") in KNOWLEDGE_INFRASTRUCTURE_ASSETS
                and item.get("severity") != "critical"
            )
        )
    ]
    warning_ids = {str(item.get("issue_id") or "") for item in warnings}
    blocking = [
        item for item in issues
        if str(item.get("issue_id") or "") not in warning_ids
    ]
    gate_order = ["structure", "grounding_difficulty", "discipline", "semantic", "coverage"]
    report["passed"] = not blocking
    report["blocking_issues"] = blocking
    report["warnings"] = warnings
    report["gates"] = [{
        "gate": gate,
        "passed": not any(item.get("gate") == gate for item in blocking),
        "issues": [item for item in issues if item.get("gate") == gate],
    } for gate in gate_order]


def _attach_course_knowledge_refs(
    assets: dict[str, list[dict[str, Any]]],
    course_knowledge_base: dict[str, Any],
) -> None:
    for asset_type, items in assets.items():
        if asset_type in KNOWLEDGE_INFRASTRUCTURE_ASSETS:
            continue
        for item in items or []:
            if not isinstance(item, dict):
                continue
            section_ids = _unique([
                item.get("node_id"),
                *(item.get("node_ids") or []),
            ])
            bindings = [
                knowledge_binding_for_section(course_knowledge_base, section_id)
                for section_id in section_ids
            ]
            for field in (
                "course_knowledge_refs",
                "course_skill_refs",
                "course_misconception_refs",
                "course_mastery_refs",
            ):
                explicit = _unique(item.get(field) or [])
                item[field] = explicit or _unique([
                    ref for binding in bindings for ref in binding.get(field) or []
                ])
            # Read aliases remain during the consumer migration, but no new
            # improvement-point identity is written.
            item["course_capability_refs"] = list(item["course_skill_refs"])
            item["course_mistake_refs"] = list(item["course_misconception_refs"])
            item["course_improvement_refs"] = []
            item["course_knowledge_base_revision_id"] = course_knowledge_base.get("revision_id")


def _attach_course_knowledge_refs_to_blocks(
    course_data: dict[str, Any],
    course_knowledge_base: dict[str, Any],
) -> None:
    """Make course-local knowledge IDs the canonical identity on content blocks."""
    bindings_by_block: dict[str, list[dict[str, Any]]] = {}
    for binding in course_knowledge_base.get("bindings") or []:
        if binding.get("target_type") != "course_block":
            continue
        block_id = str(binding.get("target_id") or "")
        if block_id:
            bindings_by_block.setdefault(block_id, []).append(binding)

    for node in course_data.get("nodes") or []:
        for block in node.get("content_blocks") or []:
            block_id = str(block.get("block_id") or block.get("content_block_id") or "")
            bindings = bindings_by_block.get(block_id, [])
            if not bindings:
                continue
            metadata = block.get("metadata") if isinstance(block.get("metadata"), dict) else {}
            previous_refs = _unique(metadata.get("concept_refs") or [])
            knowledge_refs = _unique([
                knowledge_id
                for binding in bindings
                for knowledge_id in binding.get("knowledge_ids") or []
            ])
            skill_refs = _unique([
                skill_id
                for binding in bindings
                for skill_id in binding.get("skill_ids") or []
            ])
            reference_refs = [item for item in previous_refs if item not in set(knowledge_refs)]
            if reference_refs:
                metadata["reference_concept_refs"] = reference_refs
            metadata["concept_refs"] = knowledge_refs
            metadata["course_knowledge_refs"] = knowledge_refs
            metadata["course_skill_refs"] = skill_refs
            metadata["course_knowledge_binding_ids"] = _unique([
                binding.get("binding_id") for binding in bindings
            ])
            metadata["course_knowledge_base_revision_id"] = course_knowledge_base.get("revision_id")
            block["metadata"] = metadata


def _unique(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _revision_id(item: dict[str, Any], prefix: str) -> str:
    payload = {key: value for key, value in item.items() if key != "revision_id"}
    return stable_hash(payload, prefix=prefix)


def _asset_issue(
    gate: str,
    severity: str,
    asset_type: str,
    message: str,
    asset: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "issue_id": stable_hash({"gate": gate, "type": asset_type, "message": message, "asset": (asset or {}).get("asset_id")}, prefix="aqi_"),
        "gate": gate,
        "severity": severity,
        "asset_type": asset_type,
        "asset_id": (asset or {}).get("asset_id"),
        "message": message,
    }


__all__ = [
    "compile_learning_asset_plan",
    "compile_learning_assets",
    "evaluate_learning_asset_quality",
]
