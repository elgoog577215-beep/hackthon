"""Material-backed course generation workflow helpers.

This module is deliberately deterministic. It does not call an LLM; it turns
raw user input into stable intermediate objects that CourseService can pass to
LLM stages and save with the course.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from course_difficulty import (
    AdaptationDecision,
    DifficultyGapAssessment,
    DifficultyProfile,
    format_difficulty_profile,
    format_node_difficulty_contract,
)
from course_pedagogy import SubjectPedagogyProfile
from course_knowledge_map import normalize_knowledge_structure
from material_evidence import build_evidence_catalog_summary, evidence_bundle_for_node


PIPELINE_VERSION = "course_generation_v4"

MATERIAL_USAGE_LABELS = {
    "content_source": "正文依据",
    "style_reference": "讲法参考",
    "question_source": "题目来源",
    "supplement": "补充材料",
    "weak_context": "弱背景",
}

MATERIAL_IMPORTANCE_LABELS = {
    "core": "核心资料",
    "supporting": "辅助资料",
    "weak": "弱参考",
}


def build_course_generation_artifacts(
    *,
    course_id: str,
    topic: str,
    difficulty: str,
    style: str,
    requirements: str = "",
    target_audience: str = "大学生",
    materials: list[Any] | None = None,
    learner_profile_summary: str = "",
    prepared_materials: dict[str, Any] | None = None,
    grounding_strategy: str = "material_first",
) -> dict[str, Any]:
    """Build persisted brief and material artifacts without a second task."""
    prepared = prepared_materials or {}
    cards = prepared.get("material_cards") or [
        _build_material_card(index, raw) for index, raw in enumerate(materials or [], start=1)
    ]
    brief = _build_brief(
        topic=topic,
        difficulty=difficulty,
        style=style,
        requirements=requirements,
        target_audience=target_audience,
        material_cards=cards,
        learner_profile_summary=learner_profile_summary,
    )
    artifacts = {
        "pipeline_version": PIPELINE_VERSION,
        "material_cards": cards,
        "course_generation_brief": brief,
        "material_assets": prepared.get("material_assets") or [],
        "material_bindings": prepared.get("material_bindings") or [],
        "parsed_documents": prepared.get("parsed_documents") or [],
        "evidence_catalog": prepared.get("evidence_catalog") or [],
        "evidence_coverage_plan": {
            "plan_version": "evidence_coverage_v1",
            "strategy": grounding_strategy,
            "evidence_count": len(prepared.get("evidence_catalog") or []),
            "asset_coverage": [],
            "conflicts": [],
            "gaps": [],
            "node_contracts": {},
        },
        "artifact_created_at": _utc_now(),
    }
    return artifacts


def attach_pedagogy_profile(
    artifacts: dict[str, Any], profile: SubjectPedagogyProfile
) -> dict[str, Any]:
    artifacts["subject_pedagogy_profile"] = profile.to_dict()
    return artifacts


def attach_difficulty_artifacts(
    artifacts: dict[str, Any],
    *,
    profile: DifficultyProfile,
    gap_assessment: DifficultyGapAssessment,
    adaptation_decision: AdaptationDecision,
) -> dict[str, Any]:
    """将难度编译结果放入同一份持久化生成上下文。"""
    artifacts["difficulty_profile"] = profile.to_dict()
    artifacts["difficulty_gap_assessment"] = gap_assessment.to_dict()
    artifacts["adaptation_decision"] = adaptation_decision.to_dict()
    return artifacts


def normalize_course_plan_contract(plan: dict[str, Any]) -> dict[str, Any]:
    """Deterministically normalize model-produced section IDs and contracts."""
    section_records: list[tuple[dict[str, Any], str, str, int]] = []
    aliases: dict[str, str] = {}
    for chapter_index, chapter in enumerate(plan.get("chapters") or [], start=1):
        chapter["chapter_number"] = chapter_index
        chapter.setdefault("title", f"第{chapter_index}章")
        chapter.setdefault("learning_focus", chapter.get("title", ""))
        for section_index, section in enumerate(chapter.get("sections") or [], start=1):
            raw_number = str(section.get("section_number") or "").strip()
            raw_id = str(section.get("id") or section.get("node_id") or "").strip()
            section_number = f"{chapter_index}.{section_index}"
            canonical = f"L2-{chapter_index}-{section_index}"
            section["section_number"] = section_number
            section["node_id"] = canonical
            section_records.append((section, canonical, section_number, len(section_records)))
            for alias in (
                canonical,
                raw_number,
                raw_id,
                section_number,
                f"L{chapter_index}-{section_index}",
            ):
                if alias:
                    aliases[alias] = canonical

    earlier_ids: set[str] = set()
    for section, canonical, section_number, _index in section_records:
        normalized_dependencies: list[str] = []
        for dependency in section.get("prerequisite_node_ids") or []:
            mapped = aliases.get(str(dependency).strip())
            if mapped and mapped in earlier_ids and mapped not in normalized_dependencies:
                normalized_dependencies.append(mapped)
        section["prerequisite_node_ids"] = normalized_dependencies
        section.setdefault("title", f"小节 {section_number}")
        section["learning_objective"] = str(
            section.get("learning_objective")
            or f"能解释并应用「{section.get('title')}」的核心内容"
        )
        section["assessment"] = section.get("assessment") or [
            f"完成一项可检查的「{section.get('title')}」学习任务"
        ]
        section.setdefault("key_points", [])
        normalize_knowledge_structure(section)
        section.setdefault("misconceptions", [])
        section.setdefault("scope_boundary", f"只覆盖「{section.get('title')}」必需的知识与行动")
        section.pop("complexity", None)
        earlier_ids.add(canonical)
    return plan


def validate_course_plan_constraints(
    plan: dict[str, Any],
    brief: dict[str, Any],
) -> dict[str, Any]:
    """Validate explicit user-owned course shape before content generation."""
    chapters = plan.get("chapters") if isinstance(plan, dict) else None
    chapters = chapters if isinstance(chapters, list) else []
    malformed_chapter_indexes = [
        index
        for index, chapter in enumerate(chapters, start=1)
        if not isinstance(chapter, dict)
    ]
    malformed_section_chapters = [
        index
        for index, chapter in enumerate(chapters, start=1)
        if isinstance(chapter, dict) and not isinstance(chapter.get("sections"), list)
    ]
    malformed_sections = [
        f"{chapter_index}.{section_index}"
        for chapter_index, chapter in enumerate(chapters, start=1)
        if isinstance(chapter, dict) and isinstance(chapter.get("sections"), list)
        for section_index, section in enumerate(chapter.get("sections") or [], start=1)
        if not isinstance(section, dict)
    ]
    section_count = sum(
        len(chapter.get("sections") or [])
        for chapter in chapters
        if isinstance(chapter, dict) and isinstance(chapter.get("sections"), list)
    )
    constraints = brief.get("course_shape_constraints") or {}
    issues: list[dict[str, Any]] = []
    if not chapters:
        issues.append({
            "code": "plan:missing_chapters",
            "message": "模型没有返回可用的课程章节 JSON",
            "blocking": True,
        })
    if malformed_chapter_indexes:
        issues.append({
            "code": "plan:malformed_chapters",
            "message": f"课程蓝图第 {malformed_chapter_indexes} 章不是合法对象",
            "blocking": True,
        })
    if malformed_section_chapters:
        issues.append({
            "code": "plan:malformed_section_lists",
            "message": f"课程蓝图第 {malformed_section_chapters} 章缺少合法小节列表",
            "blocking": True,
        })
    if malformed_sections:
        issues.append({
            "code": "plan:malformed_sections",
            "message": f"课程蓝图小节 {malformed_sections} 不是合法对象",
            "blocking": True,
        })
    if chapters and not section_count:
        issues.append({
            "code": "plan:missing_sections",
            "message": "课程蓝图没有可生成的小节",
            "blocking": True,
        })
    expected_chapters = constraints.get("chapter_count")
    if expected_chapters and len(chapters) != int(expected_chapters):
        issues.append({
            "code": "plan:chapter_count_mismatch",
            "message": f"用户明确要求 {expected_chapters} 章，蓝图实际为 {len(chapters)} 章",
            "blocking": True,
        })
    expected_sections = constraints.get("section_count")
    if expected_sections and section_count != int(expected_sections):
        issues.append({
            "code": "plan:section_count_mismatch",
            "message": f"用户明确要求 {expected_sections} 个小节，蓝图实际为 {section_count} 个",
            "blocking": True,
        })
    return {
        "schema_version": "course_plan_constraints_v1",
        "passed": not issues,
        "expected": constraints,
        "actual": {
            "chapter_count": len(chapters),
            "section_count": section_count,
        },
        "issues": issues,
    }


def build_course_blueprint_from_plan(plan: dict[str, Any], artifacts: dict[str, Any]) -> dict[str, Any]:
    """Wrap an LLM outline plan as a CourseBlueprint contract."""
    nodes = []
    for chapter in plan.get("chapters", []):
        chapter_number = chapter.get("chapter_number", len(nodes) + 1)
        for section in chapter.get("sections", []):
            section_number = section.get("section_number", f"{chapter_number}.1")
            nodes.append({
                "node_id": f"L2-{str(section_number).replace('.', '-')}",
                "section_number": section_number,
                "title": section.get("title", ""),
                "learning_objective": section.get("learning_objective", ""),
                "evidence_refs": section.get("evidence_refs", []),
                "grounding_contract": section.get("grounding_contract", {}),
                "knowledge_points": section.get("key_points", []),
                "knowledge_structure": section.get("knowledge_structure", []),
                "example_plan": section.get("examples_plan") or _example_plan_for_refs(section.get("evidence_refs", []), artifacts),
                "exercise_plan": section.get("exercise_plan") or _exercise_plan_for_refs(section.get("evidence_refs", []), artifacts),
                "misconceptions": section.get("misconceptions", []),
                "scope_boundary": section.get("scope_boundary", ""),
                "assessment": section.get("assessment", []),
                "prerequisite_node_ids": section.get("prerequisite_node_ids", []),
                "module_plan": section.get("module_plan", []),
                "difficulty_contract": section.get("difficulty_contract", {}),
            })

    return {
        "blueprint_id": f"cbp-{uuid.uuid4()}",
        "schema_version": PIPELINE_VERSION,
        "course_title": plan.get("course_title") or artifacts.get("course_generation_brief", {}).get("subject", ""),
        "positioning": plan.get("positioning") or artifacts.get("course_generation_brief", {}).get("goal", "电子课程资料"),
        "learning_objectives": plan.get("learning_objectives", []),
        "prerequisites": plan.get("prerequisites", []),
        "subject_pedagogy_profile": artifacts.get("subject_pedagogy_profile") or plan.get("subject_pedagogy_profile") or {},
        "difficulty_profile": artifacts.get("difficulty_profile") or plan.get("difficulty_profile") or {},
        "difficulty_gap_assessment": artifacts.get("difficulty_gap_assessment") or {},
        "adaptation_decision": artifacts.get("adaptation_decision") or {},
        "course_difficulty_curve": plan.get("course_difficulty_curve") or {},
        "course_module_plan": plan.get("course_module_plan", []),
        "sections": plan.get("chapters", []),
        "nodes": nodes,
        "appendices_plan": [
            "核心概念与方法总览",
            "实践与练习索引",
            "易错点与边界总表",
            "学习检查清单",
        ],
        "coverage_plan": artifacts.get("evidence_coverage_plan") or {},
    }


def build_outline_generation_context(artifacts: dict[str, Any]) -> str:
    """Prompt section injected into outline generation."""
    brief = artifacts.get("course_generation_brief", {})
    cards = artifacts.get("material_cards", [])
    profile = artifacts.get("subject_pedagogy_profile", {})
    return "\n".join([
        "## 资料增强课程生成 brief",
        _format_brief(brief),
        "",
        "## 上传资料卡",
        _format_material_cards(cards),
        "",
        "## 可用证据目录",
        build_evidence_catalog_summary(artifacts.get("evidence_catalog") or []),
        "",
        "## 证据使用策略",
        f"- {(artifacts.get('evidence_coverage_plan') or {}).get('strategy', 'material_first')}",
        "",
        "## 教学画像",
        _format_pedagogy_profile(profile),
        "",
        "## 难度能力契约",
        format_difficulty_profile(artifacts.get("difficulty_profile") or {}),
        "",
        "## 入口差距与适配决策",
        _format_adaptation(
            artifacts.get("difficulty_gap_assessment") or {},
            artifacts.get("adaptation_decision") or {},
        ),
        "",
        "## 电子课程资料硬标准",
        "- 统一产物是一本适合自学的电子课程资料，不拆考试导向或普通学习方向。",
        "- 必须覆盖完整、结构清晰、少废话、适合自学。",
        "- 必须遵守教学画像和模块计划，不能把所有学科压成同一正文结构。",
        "- 关键知识点要规划学习者行动、反馈、误区和验收标准。",
        "- 未上传资料不得伪装成已读依据。",
    ])


def build_node_generation_context(
    *,
    course_metadata: dict[str, Any] | None,
    node: dict[str, Any],
) -> str:
    """Prompt section for node-level content generation."""
    metadata = course_metadata or {}
    brief = metadata.get("course_generation_brief") or {}
    blueprint = metadata.get("course_blueprint") or {}
    node_blueprint = _find_blueprint_node(blueprint, node)
    evidence_bundle = evidence_bundle_for_node(metadata, {**node_blueprint, **node})

    parts = [
        "## 资料增强生成上下文",
        f"- 生成目标：{brief.get('goal', '电子课程资料')}",
        f"- 讲法要求：{'；'.join(brief.get('style_requirements', [])) or '少废话、适合自学、讲清底层原理'}",
        f"- 避免风格：{'；'.join(brief.get('avoid_styles', [])) or '晦涩堆定义；空泛打比方'}",
        "",
        "## 当前节点蓝图",
        _format_node_blueprint(node_blueprint),
    ]
    if evidence_bundle:
        parts.extend([
            "",
            "## 当前节点限定证据包",
            _format_evidence_bundle(evidence_bundle),
            "",
            "资料事实后必须追加对应的 `[[evidence:ev-id]]` 标记；只能使用上面列出的证据 ID。",
        ])
    else:
        parts.extend(["", "## 当前节点资料依据", "- 当前节点没有可引用的资料证据，不得伪装引用资料。"])
    parts.extend(["", "## 当前节点模块要求", _format_module_plan(node_blueprint.get("module_plan", []))])
    parts.extend([
        "",
        "## 当前节点难度契约",
        format_node_difficulty_contract(
            node.get("difficulty_contract")
            or node_blueprint.get("difficulty_contract")
            or {}
        ),
    ])
    return "\n".join(parts)


def attach_generation_artifacts_to_plan(
    plan: dict[str, Any],
    artifacts: dict[str, Any],
) -> dict[str, Any]:
    """Add evidence-backed generation contracts to the outline plan."""
    for chapter in plan.get("chapters", []):
        for section in chapter.get("sections", []):
            refs = section.get("evidence_refs", [])
            section.setdefault("examples_plan", _example_plan_for_refs(refs, artifacts))
            section.setdefault("exercise_plan", _exercise_plan_for_refs(refs, artifacts))
    plan["generation_pipeline_version"] = PIPELINE_VERSION
    return plan


def _build_material_card(index: int, raw: Any) -> dict[str, Any]:
    data = _as_dict(raw)
    filename = str(data.get("filename") or data.get("name") or f"资料 {index}").strip()
    user_description = str(data.get("user_description") or data.get("description") or "").strip()
    usage = _normalize_choice(
        str(data.get("usage") or "content_source"),
        set(MATERIAL_USAGE_LABELS),
        "content_source",
    )
    importance = _normalize_choice(
        str(data.get("importance") or "core"),
        set(MATERIAL_IMPORTANCE_LABELS),
        "core",
    )
    file_type = str(data.get("file_type") or _infer_file_type(filename)).strip().lower()
    return {
        "material_id": str(data.get("material_id") or f"mat-{index}-{uuid.uuid4().hex[:8]}"),
        "filename": filename,
        "file_type": file_type,
        "user_description": user_description,
        "source_label": str(data.get("source_label") or "").strip(),
        "usage": usage,
        "usage_label": MATERIAL_USAGE_LABELS[usage],
        "importance": importance,
        "importance_label": MATERIAL_IMPORTANCE_LABELS[importance],
        "parse_status": "metadata_only",
        "evidence_state": "legacy_unverified",
    }


def _build_brief(
    *,
    topic: str,
    difficulty: str,
    style: str,
    requirements: str,
    target_audience: str,
    material_cards: list[dict[str, Any]],
    learner_profile_summary: str,
) -> dict[str, Any]:
    lowered = requirements.lower()
    shape_constraints = _extract_course_shape_constraints(requirements)
    unprovided = _extract_unprovided_references(requirements, material_cards)
    style_requirements = [
        "覆盖完整",
        "少废话",
        "适合自学",
        "讲清底层原理",
        "关键知识点配例题和练习",
    ]
    if style:
        style_requirements.append(f"前端教学风格：{style}")
    hard_constraints = [
        "用户上传资料优先于模型常识",
        "用户未上传资料不得作为强依据",
        "生成正文前必须先形成课程蓝图",
    ]
    if "不要" in requirements or "不能" in requirements or "avoid" in lowered:
        hard_constraints.append("遵守用户备注中的禁止项")
    if shape_constraints.get("chapter_count"):
        hard_constraints.append(
            f"课程必须恰好包含 {shape_constraints['chapter_count']} 章"
        )
    if shape_constraints.get("section_count"):
        hard_constraints.append(
            f"课程必须恰好包含 {shape_constraints['section_count']} 个小节"
        )
    return {
        "brief_id": f"brief-{uuid.uuid4().hex[:10]}",
        "goal": "生成一本高质量电子课程资料",
        "subject": topic,
        "audience": target_audience,
        "scope": "以用户上传资料和主题要求为主；无资料时按通用自学资料降级",
        "style_requirements": style_requirements,
        "difficulty": difficulty,
        "length": "章节完整、节点适中，优先保证可学性而不是堆长文",
        "example_density": "每个关键知识点至少规划例题或检查题",
        "material_usage_strategy": _material_usage_strategy(material_cards),
        "avoid_styles": [
            "晦涩教材式堆定义",
            "低质量入门式空泛比喻",
            "没有依据地伪装参考了未上传资料",
        ],
        "output_format": ["软件内课程", "Markdown 正文", "可导出 PDF 的结构"],
        "learner_profile_summary": learner_profile_summary,
        "hard_constraints": hard_constraints,
        "course_shape_constraints": shape_constraints,
        "unprovided_references": unprovided,
        "raw_requirement": requirements,
        "desired_outcomes": _extract_desired_outcomes(requirements, topic),
        "dominant_learning_actions": _extract_learning_actions(requirements),
        "expected_deliverables": _extract_deliverables(requirements),
    }


def _extract_desired_outcomes(requirements: str, topic: str) -> list[str]:
    text = str(requirements or "").strip()
    if not text:
        return [f"理解并能够应用{topic}"]
    sentences = [item.strip() for item in re.split(r"[。；;\n]", text) if item.strip()]
    markers = ("能够", "掌握", "完成", "实现", "学会", "理解", "用于")
    outcomes = [item for item in sentences if any(marker in item for marker in markers)]
    return outcomes[:6] or [f"按用户要求学习{topic}"]


def _extract_learning_actions(requirements: str) -> list[str]:
    text = str(requirements or "")
    return _dedupe([
        action for action in (
            "计算", "证明", "推导", "编写", "实现", "运行", "调试", "实验", "观察",
            "分析", "比较", "论证", "听", "说", "读", "写", "决策", "交付",
        )
        if action in text
    ])[:8]


def _extract_deliverables(requirements: str) -> list[str]:
    text = str(requirements or "")
    return _dedupe([
        item for item in (
            "项目", "程序", "证明", "实验报告", "论文", "演讲", "方案", "分析报告", "作品",
        )
        if item in text
    ])[:6]


def _extract_course_shape_constraints(requirements: str) -> dict[str, int]:
    text = str(requirements or "")
    chapter_match = re.search(
        r"(?<!第)([0-9一二两三四五六七八九十]+)\s*(?:个\s*)?章(?:节)?",
        text,
    )
    section_match = re.search(
        r"(?<!第)([0-9一二两三四五六七八九十]+)\s*(?:个\s*)?(?:递进\s*)?(?:小节|节)",
        text,
    )
    result: dict[str, int] = {}
    if chapter_match:
        value = _parse_count(chapter_match.group(1))
        if value:
            result["chapter_count"] = value
    if section_match:
        value = _parse_count(section_match.group(1))
        if value:
            result["section_count"] = value
    return result


def _parse_count(value: str) -> int | None:
    if value.isdigit():
        number = int(value)
        return number if 0 < number <= 100 else None
    digits = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if value == "十":
        return 10
    if "十" in value:
        left, right = value.split("十", 1)
        tens = digits.get(left, 1) if left else 1
        ones = digits.get(right, 0) if right else 0
        return (tens * 10) + ones
    return digits.get(value)


def _format_brief(brief: dict[str, Any]) -> str:
    shape = brief.get("course_shape_constraints") or {}
    shape_text = "；".join(
        item for item in (
            f"章数：{shape.get('chapter_count')}" if shape.get("chapter_count") else "",
            f"小节数：{shape.get('section_count')}" if shape.get("section_count") else "",
        )
        if item
    ) or "未指定，由教学设计决定"
    return "\n".join([
        f"- 生成目标：{brief.get('goal', '')}",
        f"- 学科/主题：{brief.get('subject', '')}",
        f"- 学习对象：{brief.get('audience', '')}",
        f"- 难度：{brief.get('difficulty', '')}",
        f"- 讲法要求：{'；'.join(brief.get('style_requirements', []))}",
        f"- 资料使用策略：{brief.get('material_usage_strategy', '')}",
        f"- 必须避免：{'；'.join(brief.get('avoid_styles', []))}",
        f"- 用户原始备注：{brief.get('raw_requirement', '') or '无'}",
        f"- 用户明确课程形状：{shape_text}",
        f"- 期望学习成果：{'；'.join(brief.get('desired_outcomes', [])) or '理解并应用课程主题'}",
        f"- 主要学习行为：{'；'.join(brief.get('dominant_learning_actions', [])) or '由教学画像决定'}",
        f"- 预期交付物：{'；'.join(brief.get('expected_deliverables', [])) or '课程综合任务'}",
    ])


def _format_material_cards(cards: list[dict[str, Any]]) -> str:
    if not cards:
        return "- 未上传资料；本次只能按通用自学资料策略生成，并在报告中说明依据不足。"
    lines = []
    for card in cards:
        lines.append(
            f"- [{card.get('material_id')}] {card.get('filename')} "
            f"({card.get('file_type')}, {card.get('usage_label')}, {card.get('importance_label')}, {card.get('parse_status')})"
        )
        desc = card.get("user_description")
        if desc:
            lines.append(f"  - 用户说明：{desc}")
    return "\n".join(lines)


def _format_evidence_bundle(evidence: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in evidence:
        locator = item.get("locator") or {}
        if locator.get("page"):
            location = f"第 {locator['page']} 页"
        elif locator.get("slide"):
            location = f"第 {locator['slide']} 张幻灯片"
        else:
            location = " / ".join(locator.get("section_path") or []) or "位置未提供"
        lines.append(
            f"- [{item.get('evidence_id')}] {item.get('kind')}，{location}，"
            f"权威={item.get('authority')}：{_clip(str(item.get('source_text') or ''), 900)}"
        )
    return "\n".join(lines)


def _format_node_blueprint(node_blueprint: dict[str, Any]) -> str:
    if not node_blueprint:
        return "- 未找到节点级蓝图；按课程账本和节点字段生成。"
    return "\n".join([
        f"- 小节：{node_blueprint.get('section_number', '')} {node_blueprint.get('title', '')}",
        f"- 学习目标：{node_blueprint.get('learning_objective', '')}",
        f"- 核心知识点：{'；'.join(node_blueprint.get('knowledge_points', []))}",
        f"- 易错点：{'；'.join(node_blueprint.get('misconceptions', []))}",
        f"- 范围边界：{node_blueprint.get('scope_boundary', '')}",
        f"- 例题计划：{'；'.join(node_blueprint.get('example_plan', []))}",
        f"- 练习计划：{'；'.join(node_blueprint.get('exercise_plan', []))}",
        f"- 验收标准：{'；'.join(node_blueprint.get('assessment', []))}",
        f"- 教学模块：{'；'.join(item.get('label', '') for item in node_blueprint.get('module_plan', []))}",
        f"- 难度角色：{(node_blueprint.get('difficulty_contract') or {}).get('node_role', '')}",
    ])


def _format_pedagogy_profile(profile: dict[str, Any]) -> str:
    if not profile:
        return "- 尚未形成教学画像。"
    return "\n".join([
        f"- 主模式：{profile.get('primary_mode', '')}",
        f"- 辅模式：{profile.get('secondary_mode') or '无'}",
        f"- 辅助强度：{profile.get('secondary_intensity') or '无'}",
        f"- 置信度：{profile.get('confidence', '')}",
        f"- 判断依据：{'；'.join(profile.get('evidence', []))}",
        f"- 组合理由：{profile.get('rationale', '')}",
    ])


def _format_module_plan(modules: list[dict[str, Any]]) -> str:
    if not modules:
        return "- 使用通用本节任务、核心教学、学习者行动和反馈检查。"
    return "\n".join(
        f"- [{item.get('module_id')}] {item.get('label')}：{item.get('output_contract')}"
        for item in modules
    )


def _format_adaptation(
    assessment: dict[str, Any],
    decision: dict[str, Any],
) -> str:
    if not assessment or not decision:
        return "- 尚未形成入口适配决策。"
    return "\n".join([
        f"- 当前就绪度：{assessment.get('current_readiness') or '未知'}",
        f"- 差距：{assessment.get('gap') if assessment.get('gap') is not None else '待诊断'}",
        f"- 适配策略：{decision.get('strategy', '')}",
        f"- 保留目标难度：{'是' if decision.get('preserve_target', True) else '否'}",
        f"- 必要动作：{'；'.join(decision.get('actions', []))}",
    ])


def _find_blueprint_node(blueprint: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    node_id = str(node.get("node_id") or "")
    node_name = str(node.get("node_name") or "")
    for item in blueprint.get("nodes", []):
        section_number = str(item.get("section_number") or "")
        if item.get("node_id") == node_id or (section_number and section_number in node_name):
            return item
    return {}


def _example_plan_for_refs(refs: list[str], artifacts: dict[str, Any]) -> list[str]:
    evidence = artifacts.get("evidence_catalog", [])
    has_questions = any(
        item.get("purpose") == "question_source" or item.get("kind") == "question"
        for item in evidence if item.get("evidence_id") in refs
    )
    if has_questions:
        return ["从题目资料中抽取典型题", "为核心概念补一题同类练习"]
    return ["为核心知识点配置典型例题", "必要时补一个反例或边界例子"]


def _exercise_plan_for_refs(refs: list[str], artifacts: dict[str, Any]) -> list[str]:
    evidence = artifacts.get("evidence_catalog", [])
    if any(
        item.get("purpose") == "question_source" or item.get("kind") == "question"
        for item in evidence if item.get("evidence_id") in refs
    ):
        return ["把题目资料中的同类题改写为检查题", "给出关键步骤解析"]
    return ["设置 1-2 个自测问题", "用简短解析检查是否真正理解"]


def _material_usage_strategy(cards: list[dict[str, Any]]) -> str:
    if not cards:
        return "无上传资料；使用通用电子课程资料模板，并明确说明依据不足。"
    grouped: dict[str, list[str]] = {}
    for card in cards:
        grouped.setdefault(card.get("usage_label", "资料"), []).append(card.get("filename", "未命名资料"))
    return "；".join(f"{usage}：{', '.join(names[:4])}" for usage, names in grouped.items())


def _extract_unprovided_references(requirements: str, cards: list[dict[str, Any]]) -> list[str]:
    if not requirements:
        return []
    uploaded_text = " ".join([card.get("filename", "") + " " + card.get("user_description", "") for card in cards])
    candidates = []
    patterns = [
        r"([^，。；\n]{1,20}(?:老师|教材|课本|讲义|资料|PPT|试卷|真题))",
        r"参考([^，。；\n]{1,24})",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, requirements):
            text = _normalize_reference_candidate(str(match))
            if text and not _reference_is_covered(text, uploaded_text) and text not in candidates:
                candidates.append(text)
    return candidates[:8]


def _normalize_reference_candidate(text: str) -> str:
    text = re.sub(r"\s+", "", text.strip(" ：:，。；;"))
    text = re.sub(r"^(参考|根据|依据|按照|按|结合|使用|用|把|将|拿)", "", text)
    text = re.sub(r"(但未上传|没有上传|未上传|来生成|作为依据|当参考)$", "", text)
    return text.strip(" ：:，。；;")


def _reference_is_covered(reference: str, uploaded_text: str) -> bool:
    if not reference:
        return True
    uploaded = re.sub(r"\s+", "", uploaded_text)
    if reference in uploaded:
        return True
    markers = ["真题", "试卷", "题库", "PPT", "ppt", "课件", "教材", "课本", "讲义", "资料"]
    return any(marker in reference and marker in uploaded for marker in markers)


def _infer_file_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    return suffix or "text"


def _normalize_choice(value: str, allowed: set[str], fallback: str) -> str:
    value = value.strip()
    if value in allowed:
        return value
    reverse_usage = {label: key for key, label in MATERIAL_USAGE_LABELS.items()}
    reverse_importance = {label: key for key, label in MATERIAL_IMPORTANCE_LABELS.items()}
    return reverse_usage.get(value) or reverse_importance.get(value) or fallback


def _clip(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _dedupe(items: list[str]) -> list[str]:
    result = []
    seen = set()
    for item in items:
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    return result


def _as_dict(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if hasattr(raw, "model_dump"):
        return raw.model_dump()
    if hasattr(raw, "dict"):
        return raw.dict()
    return {"description": str(raw)}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
