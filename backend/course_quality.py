"""课程生成的确定性结构诊断与发布门禁。"""

from __future__ import annotations

import re
from typing import Any

from course_coherence import evaluate_course_coherence
from course_knowledge_base import (
    compile_course_knowledge_base,
    validate_course_knowledge_base,
)
from course_pedagogy import MODULES, coerce_persisted_profile

QUALITY_CONTRACT_VERSION = "course_quality_v10"


MODULE_SIGNAL_RULES: dict[str, tuple[tuple[str, ...], str]] = {
    "general_explained_example": (("例如", "例子", "案例", "示例"), "缺少与概念对应的具体例子"),
    "general_application": (("应用", "场景", "实际", "任务"), "缺少真实应用场景"),
    "math_formalization": (("定义", "命题", "定理", "$"), "缺少正式定义、命题或数学表达"),
    "math_worked_example": (("例题", "示例", "解：", "求解"), "缺少完整例题推演"),
    "math_variation": (("练习", "变式", "尝试", "证明"), "缺少独立变式练习"),
    "math_error_analysis": (("误区", "错误", "易错", "注意"), "缺少错误原因分析"),
    "engineering_minimal_run": (("```",), "缺少可运行代码块"),
    "engineering_output": (("运行", "输出", "结果", "验证"), "缺少运行方式或预期结果"),
    "engineering_modification": (("修改", "扩展", "尝试", "任务"), "缺少代码修改任务"),
    "engineering_debugging": (("错误", "调试", "排查", "修复"), "缺少调试案例"),
    "science_evidence": (("实验", "观察", "数据", "证据"), "缺少实验、观察或数据证据"),
    "science_boundary": (("边界", "条件", "适用", "失效"), "缺少模型适用边界"),
    "life_location_structure": (("结构", "组成", "位于", "层级"), "缺少对象定位和结构"),
    "life_function": (("功能", "作用"), "缺少结构功能说明"),
    "life_mechanism": (("机制", "过程", "导致", "调节"), "缺少机制过程"),
    "humanities_source": (("材料", "文本", "事件", "案例", "数据", "证据"), "缺少材料或证据"),
    "humanities_comparison": (("比较", "不同", "另一种", "争议", "但是", "然而"), "缺少不同观点比较"),
    "humanities_response": (("讨论", "写作", "论证", "回应", "问题"), "缺少学习者论证或讨论任务"),
    "language_input": (("对话", "短文", "例句", "听力", "阅读"), "缺少可理解输入"),
    "language_controlled_practice": (("替换", "填空", "模仿", "练习"), "缺少控制练习"),
    "language_output": (("表达", "口语", "写作", "对话", "任务"), "缺少真实语言输出任务"),
    "business_scenario": (("场景", "背景", "角色", "目标", "约束"), "缺少具体业务场景"),
    "business_tool": (("模板", "清单", "步骤", "工具"), "缺少可复用工具或模板"),
    "business_task": (("任务", "交付", "完成", "产出"), "缺少实战交付任务"),
    "business_metric": (("指标", "标准", "评分", "检查"), "缺少成果评价标准"),
}


def validate_blueprint(blueprint: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    nodes = blueprint.get("nodes") or []
    profile = blueprint.get("subject_pedagogy_profile") or blueprint.get("pedagogy_profile")
    if not profile:
        issues.append(_issue("missing_pedagogy_profile", "critical", "蓝图缺少教学画像", "重新解析教学画像"))
    if not nodes:
        issues.append(_issue("missing_nodes", "critical", "蓝图没有正文节点", "重新生成课程蓝图"))
    plan_constraints = blueprint.get("course_plan_constraint_report") or {}
    if plan_constraints and not plan_constraints.get("passed"):
        for constraint_issue in plan_constraints.get("issues") or []:
            issues.append(_issue(
                str(constraint_issue.get("code") or "plan:constraint"),
                "critical",
                str(constraint_issue.get("message") or "课程蓝图违背用户硬约束"),
                "根据用户原始备注重新规划课程结构",
            ))

    difficulty_report = validate_difficulty_blueprint(blueprint)
    issues.extend(difficulty_report["issues"])
    evidence_count = int((blueprint.get("coverage_plan") or {}).get("evidence_count") or 0)

    order = {str(node.get("node_id") or ""): index for index, node in enumerate(nodes)}
    for index, node in enumerate(nodes):
        node_id = str(node.get("node_id") or "")
        if not node.get("learning_objective"):
            issues.append(_issue("missing_objective", "major", f"{node_id} 缺少学习目标", "补充可观察学习目标", node_id))
        if not node.get("assessment"):
            issues.append(_issue("missing_assessment", "major", f"{node_id} 缺少验收标准", "补充可检查任务或标准", node_id))
        if evidence_count and not node.get("grounding_contract"):
            issues.append(_issue(
                "grounding:missing_contract",
                "critical",
                f"{node_id} 缺少资料证据契约",
                "根据 EvidenceCoveragePlan 重新编译节点证据",
                node_id,
            ))
        module_plan = node.get("module_plan") or []
        if not module_plan:
            issues.append(_issue("missing_module_plan", "critical", f"{node_id} 缺少教学模块计划", "按教学画像重新编译模块", node_id))
        for item in module_plan:
            module_id = str(item.get("module_id") or "")
            if module_id not in MODULES:
                issues.append(_issue("unknown_module", "major", f"{node_id} 使用未知模块 {module_id}", "删除或替换未知模块", node_id))
        for dependency in node.get("prerequisite_node_ids") or []:
            if dependency not in order:
                issues.append(_issue("unknown_dependency", "major", f"{node_id} 引用了不存在的前置节点 {dependency}", "删除无效依赖", node_id))
            elif order[dependency] >= index:
                issues.append(_issue("forward_dependency", "critical", f"{node_id} 的前置依赖 {dependency} 没有位于更早节点", "调整节点顺序或依赖", node_id))

    score = _score_from_issues(issues)
    return {
        "contract_version": QUALITY_CONTRACT_VERSION,
        "stage": "blueprint",
        "passed": score >= 0.75 and not _has_critical(issues),
        "score": score,
        "issues": issues,
        "node_count": len(nodes),
        "difficulty_check": difficulty_report,
    }


def evaluate_node_content(content: str, node: dict[str, Any]) -> dict[str, Any]:
    text = str(content or "").strip()
    node_id = str(node.get("node_id") or "")
    issues: list[dict[str, Any]] = []
    if not text:
        issues.append(_issue("empty_content", "critical", "正文为空", "重新生成当前节点", node_id))
    elif len(text) < 240:
        issues.append(_issue("content_too_short", "major", f"正文仅 {len(text)} 字符，难以履行节点契约", "补足必要解释、行动和反馈", node_id))

    lowered_prefix = text[:160].lower()
    if any(marker in lowered_prefix for marker in ("好的，", "遵照您的", "我将", "以下是", "下面是")):
        issues.append(_issue("meta_preamble", "major", "正文包含模型寒暄或任务复述", "直接从课程正文开始", node_id))
    if text.count("```") % 2:
        issues.append(_issue("unclosed_code_fence", "critical", "代码块没有闭合", "闭合 Markdown 代码块", node_id))
    if re.search(r"(?m)^[ \t]*\$[ \t]*$", text):
        issues.append(_issue(
            "legacy_math_delimiter",
            "critical",
            "正文使用了单美元独占行的旧版块级公式分隔符",
            "将块级公式统一改为 $$...$$，并移除外层重复分隔符",
            node_id,
        ))
    if text.count("$$") % 2:
        issues.append(_issue(
            "unclosed_math_fence",
            "critical",
            "块级公式 $$ 分隔符没有闭合",
            "闭合 Markdown 块级公式分隔符",
            node_id,
        ))
    if "生成中..." in text or "[待补充" in text:
        issues.append(_issue("placeholder_content", "critical", "正文包含兜底或待补充占位符", "生成完整正文", node_id))
    if re.search(
        r"我的(?:计算|答案|判断|推导)(?:有误|错了)"
        r"|等待[，,:：]?\s*(?:更正|重新)"
        r"|请重新检查任务"
        r"|(?:前面|前文|上述|刚才|这里)(?:的)?(?:计算|答案|判断|推导|结论)"
        r".{0,40}(?:需要)?(?:更正|修正)[：:]"
        r"|[（(，,。；;！？!?]\s*(?:更正|修正)[：:]"
        r"|(?m:^[ \t]*(?:更正|修正)[：:])",
        text,
    ):
        issues.append(_issue(
            "model_self_correction",
            "major",
            "正文保留了模型自我纠错痕迹，题干、过程或答案可能互相矛盾",
            "重新核对题干、计算、答案和量规，只保留一致的最终版本",
            node_id,
        ))
    if re.search(r"\$(?:#{1,6}\s|\d+\.\s{2,}|[*+-]\s{2,})", text):
        issues.append(_issue(
            "markdown_block_join",
            "major",
            "公式与后续标题或列表粘连，正文排版可能无法正确分块",
            "在公式、标题和列表之间补齐空行，并重新检查 Markdown 渲染",
            node_id,
        ))

    level_two_headings = [
        item.strip()
        for item in re.findall(r"(?m)^##\s+(.+?)\s*$", text)
        if item.strip()
    ]
    node_title = str(node.get("node_name") or "").strip()
    if node_title and any(_same_heading(item, node_title) for item in level_two_headings):
        issues.append(_issue(
            "duplicate_section_heading",
            "major",
            "正文重复使用了页面已经展示的节点标题，生成后会形成空引入块或重复标题",
            "删除节点同名标题，直接从本节任务或真实引入模块开始",
            node_id,
        ))
    required_module_labels = [
        str(module.get("label") or "").strip()
        for module in node.get("module_plan") or []
        if module.get("required", True) and str(module.get("label") or "").strip()
    ]
    missing_module_headings = [
        label
        for label in required_module_labels
        if not any(_module_heading_matches(item, label) for item in level_two_headings)
    ]
    if missing_module_headings:
        issues.append(_issue(
            "missing_module_headings",
            "major",
            f"必需教学模块缺少稳定的二级标题：{'、'.join(missing_module_headings[:6])}",
            "按模块契约使用原始标签作为二级标题，内部层次改用三级标题",
            node_id,
        ))

    issues.extend(_feedback_structure_issues(text, node_id))

    if not _contains_any(text, ("练习", "任务", "请", "尝试", "思考", "完成", "写出", "计算", "实现", "分析", "表达")):
        issues.append(_issue("missing_learner_action", "major", "缺少学习者主动任务", "加入与学习目标一致的计算、实现、分析、表达或操作", node_id))
    if not _contains_any(text, ("答案", "检查", "标准", "提示", "验证", "参考", "自测", "反馈")):
        issues.append(_issue("missing_feedback", "major", "缺少验收或反馈", "说明怎样检查任务以及典型错误", node_id))

    for module in node.get("module_plan") or []:
        if not module.get("required", True):
            continue
        module_id = str(module.get("module_id") or "")
        rule = MODULE_SIGNAL_RULES.get(module_id)
        if rule and not _contains_any(text, rule[0]):
            issues.append(_issue(f"module:{module_id}", "major", rule[1], str(module.get("output_contract") or "补齐模块产出"), node_id))

    key_points = [str(item) for item in node.get("key_points") or [] if str(item).strip()]
    missing_key_points = [point for point in key_points if not _key_point_covered(point, text)]
    if key_points and len(missing_key_points) == len(key_points):
        issues.append(_issue("missing_key_points", "major", "正文没有覆盖节点核心知识点", "围绕节点知识点重写核心解释", node_id))
    elif key_points and len(missing_key_points) / len(key_points) > 0.5:
        issues.append(_issue(
            "partial_key_points",
            "warning",
            f"正文只覆盖了部分核心知识点，待补：{'、'.join(missing_key_points[:4])}",
            "补齐缺失知识点，或收窄蓝图范围以保持目标与正文一致",
            node_id,
        ))

    difficulty_alignment = evaluate_difficulty_alignment(text, node)
    issues.extend(difficulty_alignment["issues"])
    grounding_check = evaluate_node_grounding(node)
    issues.extend(grounding_check["issues"])

    score = _score_from_issues(issues)
    has_content_integrity_failure = any(
        item.get("code") in {
            "model_self_correction",
            "markdown_block_join",
            "duplicate_section_heading",
            "missing_module_headings",
            "feedback_structure_flat",
            "feedback_math_as_code",
        }
        for item in issues
    )
    return {
        "contract_version": QUALITY_CONTRACT_VERSION,
        "stage": "node",
        "node_id": node_id,
        "passed": (
            score >= 0.7
            and not _has_critical(issues)
            and not has_content_integrity_failure
            and difficulty_alignment.get("passed", False)
            and grounding_check.get("passed", False)
        ),
        "score": score,
        "issues": issues,
        "content_chars": len(text),
        "difficulty_alignment": difficulty_alignment,
        "grounding_check": grounding_check,
    }


def evaluate_node_grounding(node: dict[str, Any]) -> dict[str, Any]:
    node_id = str(node.get("node_id") or "")
    contract = node.get("grounding_contract") or {}
    required = set(contract.get("required_evidence_ids") or [])
    optional = set(contract.get("optional_evidence_ids") or [])
    allowed = required | optional
    annotations = node.get("grounding_annotations") or []
    used = {str(item.get("evidence_id") or "") for item in annotations if item.get("evidence_id")}
    invalid = set(node.get("grounding_invalid_refs") or []) | (used - allowed)
    missing = required - used
    issues: list[dict[str, Any]] = []
    if invalid:
        issues.append(_issue(
            "grounding:invalid_reference",
            "critical",
            f"正文使用了未授权证据：{'、'.join(sorted(invalid))}",
            "删除无效标记或改用当前节点证据包中的 ID",
            node_id,
        ))
    if missing:
        issues.append(_issue(
            "grounding:missing_required_evidence",
            "major",
            f"正文未使用必用证据：{'、'.join(sorted(missing))}",
            "在对应资料事实后补充有效证据标记",
            node_id,
        ))
    return {
        "contract_version": QUALITY_CONTRACT_VERSION,
        "stage": "grounding_node",
        "node_id": node_id,
        "passed": not issues,
        "required_count": len(required),
        "used_count": len(used & allowed),
        "used_evidence_ids": sorted(used & allowed),
        "missing_required_evidence_ids": sorted(missing),
        "invalid_evidence_ids": sorted(invalid),
        "issues": issues,
    }


def build_grounding_quality_report(course_data: dict[str, Any]) -> dict[str, Any]:
    nodes = [node for node in course_data.get("nodes") or [] if node.get("node_level", 1) == 2]
    evidence_items = course_data.get("evidence_catalog") or course_data.get("evidence_index") or []
    evidence = {str(item.get("evidence_id")): item for item in evidence_items}
    coverage_plan = course_data.get("evidence_coverage_plan") or {}
    node_reports = [evaluate_node_grounding(node) for node in nodes]
    used_ids = {
        evidence_id
        for report in node_reports
        for evidence_id in report.get("used_evidence_ids") or []
    }
    invalid_catalog_ids = sorted(evidence_id for evidence_id in used_ids if evidence_id not in evidence)
    asset_used: dict[str, set[str]] = {}
    for evidence_id in used_ids:
        item = evidence.get(evidence_id) or {}
        asset_id = str(item.get("asset_id") or "")
        if asset_id:
            asset_used.setdefault(asset_id, set()).add(evidence_id)

    material_coverage = []
    bindings = {str(item.get("asset_id")): item for item in course_data.get("material_bindings") or []}
    assets = {str(item.get("asset_id")): item for item in course_data.get("material_assets") or []}
    for asset_id, binding in bindings.items():
        asset = assets.get(asset_id) or {}
        assigned = next(
            (item for item in coverage_plan.get("asset_coverage") or [] if item.get("asset_id") == asset_id),
            {},
        )
        used = sorted(asset_used.get(asset_id, set()))
        status = str(asset.get("status") or "metadata_only")
        material_coverage.append({
            "asset_id": asset_id,
            "filename": asset.get("filename", ""),
            "parse_status": status,
            "purpose": binding.get("purpose"),
            "usage_policy": binding.get("usage_policy"),
            "assigned_nodes": assigned.get("assigned_nodes", []),
            "used_evidence_ids": used,
            "coverage_level": (
                "used" if used else (
                    "parse_failed" if status in {"failed", "metadata_only"} else "unused"
                )
            ),
        })

    failed_nodes = [report for report in node_reports if not report.get("passed")]
    conflicts = coverage_plan.get("conflicts") or []
    gaps = coverage_plan.get("gaps") or []
    must_use_uncovered = [
        item for item in material_coverage
        if item.get("usage_policy") == "must_use" and item.get("parse_status") in {"parsed", "degraded"}
        and item.get("coverage_level") != "used"
    ]
    return {
        "contract_version": QUALITY_CONTRACT_VERSION,
        "stage": "grounding_final",
        "passed": not failed_nodes and not invalid_catalog_ids and not must_use_uncovered,
        "node_reports": node_reports,
        "material_coverage": material_coverage,
        "used_evidence_count": len(used_ids),
        "available_evidence_count": len(evidence),
        "invalid_catalog_evidence_ids": invalid_catalog_ids,
        "must_use_uncovered": must_use_uncovered,
        "conflicts": conflicts,
        "gaps": gaps,
    }


def validate_difficulty_blueprint(blueprint: dict[str, Any]) -> dict[str, Any]:
    """检查难度画像、锯齿曲线和节点契约的硬约束。"""
    issues: list[dict[str, Any]] = []
    profile = blueprint.get("difficulty_profile") or {}
    curve = blueprint.get("course_difficulty_curve") or {}
    nodes = blueprint.get("nodes") or []
    if not profile:
        issues.append(_issue(
            "difficulty:missing_profile",
            "critical",
            "蓝图缺少结构化难度画像",
            "使用 DifficultyCompiler 编译入口、挑战、支持和掌握契约",
        ))
    if not curve:
        issues.append(_issue(
            "difficulty:missing_curve",
            "critical",
            "蓝图缺少课程难度曲线",
            "根据节点顺序编译锯齿型曲线",
        ))
    target_level = str(profile.get("target_level") or "")
    if profile and target_level not in {"beginner", "intermediate", "advanced"}:
        issues.append(_issue(
            "difficulty:invalid_level",
            "critical",
            f"无效目标难度 {target_level}",
            "使用 beginner/intermediate/advanced 之一",
        ))

    previous_contract: dict[str, Any] | None = None
    for node in nodes:
        node_id = str(node.get("node_id") or "")
        contract = node.get("difficulty_contract") or {}
        if not contract:
            issues.append(_issue(
                "difficulty:missing_node_contract",
                "critical",
                f"{node_id} 缺少节点难度契约",
                "根据课程曲线重新编译该节点",
                node_id,
            ))
            continue
        for group_name in ("challenge", "support", "mastery"):
            group = contract.get(group_name) or {}
            numeric_values = [value for value in group.values() if isinstance(value, (int, float))]
            if not numeric_values or any(value < 1 or value > 5 for value in numeric_values):
                issues.append(_issue(
                    f"difficulty:invalid_{group_name}",
                    "critical",
                    f"{node_id} 的 {group_name} 维度缺失或超出 1-5",
                    "重新编译节点契约",
                    node_id,
                ))
        if not contract.get("subject_task"):
            issues.append(_issue(
                "difficulty:missing_subject_task",
                "major",
                f"{node_id} 没有学科化能力任务",
                "通过主教学模式翻译难度要求",
                node_id,
            ))
        if previous_contract:
            current_challenge = _dimension_average(contract.get("challenge") or {})
            previous_challenge = _dimension_average(previous_contract.get("challenge") or {})
            if abs(current_challenge - previous_challenge) > 2:
                issues.append(_issue(
                    "difficulty:challenge_jump",
                    "critical",
                    f"{node_id} 与前一节的挑战级差超过 2",
                    "在中间加入示范、引导练习或桥接节点",
                    node_id,
                ))
            concept_increase = int(contract.get("new_concept_load") or 0) - int(previous_contract.get("new_concept_load") or 0)
            task_increase = int((contract.get("challenge") or {}).get("task_complexity") or 0) - int((previous_contract.get("challenge") or {}).get("task_complexity") or 0)
            support_level = int((contract.get("support") or {}).get("scaffold_intensity") or 0)
            if concept_increase > 0 and task_increase > 0 and support_level < 3:
                issues.append(_issue(
                    "difficulty:double_spike",
                    "critical",
                    f"{node_id} 同时提高新概念负荷和任务复杂度，且支架不足",
                    "降低其中一项负荷或增加支架",
                    node_id,
                ))
        previous_contract = contract

    curve_contracts = curve.get("node_contracts") or []
    if curve and len(curve_contracts) != len(nodes):
        issues.append(_issue(
            "difficulty:curve_node_mismatch",
            "critical",
            "曲线契约数与正文节点数不一致",
            "在蓝图节点确定后重新编译难度曲线",
        ))

    score = _score_from_issues(issues)
    return {
        "contract_version": QUALITY_CONTRACT_VERSION,
        "stage": "difficulty_blueprint",
        "passed": score >= 0.75 and not _has_critical(issues),
        "score": score,
        "issues": issues,
        "target_level": target_level,
        "node_count": len(nodes),
    }


def evaluate_difficulty_alignment(
    content: str,
    node: dict[str, Any],
) -> dict[str, Any]:
    """评估正文是否履行节点难度契约。"""
    text = str(content or "")
    node_id = str(node.get("node_id") or "")
    contract = node.get("difficulty_contract") or {}
    issues: list[dict[str, Any]] = []
    if not contract:
        issues.append(_issue(
            "difficulty:missing_node_contract",
            "critical",
            "正文无法验证难度，因为节点契约缺失",
            "先从课程难度曲线恢复节点契约",
            node_id,
        ))
        return {
            "contract_version": QUALITY_CONTRACT_VERSION,
            "stage": "difficulty_node",
            "node_id": node_id,
            "passed": False,
            "score": 0.0,
            "dimensions": {},
            "issues": issues,
            "pseudo_difficulty_risk": False,
        }

    challenge = contract.get("challenge") or {}
    support = contract.get("support") or {}
    mastery = contract.get("mastery") or {}
    target_level = str(contract.get("target_level") or "intermediate")

    has_action = _contains_any(text, ("请", "尝试", "完成", "计算", "实现", "分析", "证明", "设计", "表达", "交付"))
    has_reasoning = _contains_any(text, ("因为", "因此", "依据", "推导", "论证", "机制", "假设", "权衡", "原因"))
    has_transfer = _contains_any(text, (
        "迁移", "新情境", "不同场景", "适用场景", "边界", "反例", "扩展",
        "改变条件", "变式", "退化条件", "局限性", "现实约束", "取舍判断",
        "更换数据", "不同输入", "跨领域", "综合情境", "稠密或稀疏",
        "算法选择", "什么场景", "数据规模", "硬件限制", "稳定性要求",
    ))
    has_independence = _contains_any(text, ("独立", "自行", "请完成", "尝试", "设计", "选择", "写出", "实现", "证明"))
    has_support = _contains_any(text, ("步骤", "示例", "例题", "提示", "检查", "反馈", "参考答案"))
    evidence_terms = [
        str(item) for item in contract.get("required_evidence") or []
        if 1 < len(str(item)) <= 8
    ]
    evidence_hits = sum(1 for item in evidence_terms if item.lower() in text.lower())
    evidence_ratio = min(1.0, evidence_hits / max(1, min(3, len(evidence_terms))))

    if int(mastery.get("independence") or 0) >= 4 and not has_independence:
        issues.append(_issue(
            "difficulty:missing_independence",
            "major",
            "节点没有要求学习者独立做出选择或完成任务",
            "加入与学科任务一致的独立产出",
            node_id,
        ))
    if int(challenge.get("reasoning_depth") or 0) >= 4 and not has_reasoning:
        issues.append(_issue(
            "difficulty:missing_reasoning",
            "major",
            "高推理要求没有在正文中体现",
            "要求说明依据、假设、推导、机制或取舍",
            node_id,
        ))
    if int(challenge.get("transfer_distance") or 0) >= 4 and not has_transfer:
        issues.append(_issue(
            "difficulty:missing_transfer",
            "major",
            "高迁移要求没有在正文中体现",
            "加入变换条件、非熟悉情境、反例或边界任务",
            node_id,
        ))
    if int(support.get("scaffold_intensity") or 0) >= 4 and not has_support:
        issues.append(_issue(
            "difficulty:missing_scaffold",
            "major",
            "入门或新能力节点缺少必要支架",
            "加入步骤、示例、提示和即时检查",
            node_id,
        ))

    high_challenge_signals = sum((has_reasoning, has_transfer, has_independence))
    pseudo_risk = target_level == "advanced" and len(text) >= 600 and high_challenge_signals < 2
    if pseudo_risk:
        issues.append(_issue(
            "difficulty:pseudo_difficulty",
            "major",
            "正文篇幅已较长，但没有足够的推理、独立决策或迁移证据",
            "删减无效堆叠，补充开放约束、取舍、边界或远迁移任务",
            node_id,
        ))

    dimensions = {
        "challenge": round((int(has_reasoning) + int(has_transfer) + int(has_action)) / 3, 3),
        "support": 1.0 if int(support.get("scaffold_intensity") or 0) < 4 or has_support else 0.0,
        "independence": 1.0 if int(mastery.get("independence") or 0) < 4 or has_independence else 0.0,
        "mastery_evidence": round(max(evidence_ratio, 0.5 if has_action else 0.0), 3),
        "subject_task": round(evidence_ratio, 3),
        "transfer": 1.0 if int(challenge.get("transfer_distance") or 0) < 4 or has_transfer else 0.0,
    }
    score = round(sum(dimensions.values()) / len(dimensions), 3)
    return {
        "contract_version": QUALITY_CONTRACT_VERSION,
        "stage": "difficulty_node",
        "node_id": node_id,
        "passed": score >= 0.65 and not _has_critical(issues) and not any(item["severity"] == "major" for item in issues),
        "score": score,
        "dimensions": dimensions,
        "issues": issues,
        "pseudo_difficulty_risk": pseudo_risk,
    }


def build_difficulty_alignment_report(course_data: dict[str, Any]) -> dict[str, Any]:
    nodes = [node for node in course_data.get("nodes") or [] if node.get("node_level", 1) == 2]
    reports = [
        (_current_node_quality(node).get("difficulty_alignment") or {})
        or evaluate_difficulty_alignment(str(node.get("node_content") or ""), node)
        for node in nodes
    ]
    failed = [report for report in reports if not report.get("passed")]
    dimension_names = ("challenge", "support", "independence", "mastery_evidence", "subject_task", "transfer")
    dimensions = {
        name: round(
            sum(float((report.get("dimensions") or {}).get(name) or 0) for report in reports) / max(1, len(reports)),
            3,
        )
        for name in dimension_names
    }
    blueprint = course_data.get("course_blueprint") or {}
    blueprint_check = validate_difficulty_blueprint(blueprint)
    return {
        "contract_version": QUALITY_CONTRACT_VERSION,
        "stage": "difficulty_final",
        "target_level": (course_data.get("difficulty_profile") or {}).get("target_level"),
        "passed": blueprint_check.get("passed", False) and not failed,
        "blueprint_check": blueprint_check,
        "dimensions": dimensions,
        "total_nodes": len(reports),
        "passed_nodes": len(reports) - len(failed),
        "failed_nodes": failed,
        "pseudo_difficulty_nodes": [
            report.get("node_id") for report in reports if report.get("pseudo_difficulty_risk")
        ],
    }


def build_final_course_quality_report(
    course_data: dict[str, Any], *, job_id: str
) -> dict[str, Any]:
    nodes = [node for node in course_data.get("nodes", []) if node.get("node_level", 1) == 2]
    node_reports = []
    for node in nodes:
        report = dict(_current_node_quality(node))
        if node.get("needs_manual_review"):
            report["needs_manual_review"] = True
        node_reports.append(report)
    weak_nodes = [report for report in node_reports if not report.get("passed") or report.get("needs_manual_review")]
    manual_review_nodes = [
        report.get("node_id") for report in node_reports if report.get("needs_manual_review")
    ]
    teaching_stage = (
        course_data.get("generation_stage_artifacts") or {}
    ).get("course_teaching_plan") or {}
    teaching_fallback_units = [
        item
        for item in teaching_stage.get("fallback_units") or []
        if isinstance(item, dict)
    ]
    teaching_review_nodes = [
        str(node_id)
        for item in teaching_fallback_units
        for node_id in item.get("section_ids") or []
        if str(node_id)
    ]
    manual_review_nodes = list(dict.fromkeys([
        *manual_review_nodes,
        *teaching_review_nodes,
    ]))
    quality_warnings: list[dict[str, Any]] = []
    if teaching_stage.get("degraded"):
        quality_warnings.append(_issue(
            "teaching_plan:local_fallback",
            "major",
            "部分教案单元使用了本地确定性保底，需要人工复核教学语义",
            "重点复核标记小节的知识陈述、边界、易错和教学模块",
        ))
    profile = coerce_persisted_profile(course_data)
    blueprint_report = course_data.get("blueprint_validation_report") or validate_blueprint(course_data.get("course_blueprint") or {})
    difficulty_alignment = build_difficulty_alignment_report(course_data)
    grounding_quality = build_grounding_quality_report(course_data)
    course_knowledge_base = course_data.get("course_knowledge_base") or compile_course_knowledge_base(
        course_data
    )
    knowledge_quality = course_knowledge_base.get("quality_report") or validate_course_knowledge_base(
        course_knowledge_base,
        course_data=course_data,
    )
    coherence_quality = evaluate_course_coherence(course_data)
    blocking_issues: list[dict[str, Any]] = []
    if not nodes:
        blocking_issues.append(_issue(
            "course:no_learning_nodes",
            "critical",
            "课程没有可发布的学习节点",
            "重新生成课程蓝图和正文",
        ))
    for issue in blueprint_report.get("issues") or []:
        if issue.get("severity") == "critical":
            blocking_issues.append(issue)
    for issue in (difficulty_alignment.get("blueprint_check") or {}).get("issues") or []:
        if issue.get("severity") == "critical":
            blocking_issues.append(issue)
    for report in node_reports:
        for issue in report.get("issues") or []:
            if issue.get("severity") == "critical":
                blocking_issues.append(issue)
    if grounding_quality.get("invalid_catalog_evidence_ids"):
        blocking_issues.append(_issue(
            "grounding:invalid_catalog",
            "critical",
            "课程包含无效资料证据引用",
            "修复证据目录和正文引用后再发布",
        ))
    if grounding_quality.get("must_use_uncovered"):
        blocking_issues.append(_issue(
            "grounding:must_use_uncovered",
            "critical",
            "用户指定的必用资料没有进入课程正文",
            "补齐必用资料覆盖后再发布",
        ))
    for issue in knowledge_quality.get("issues") or []:
        if issue.get("severity") == "critical":
            blocking_issues.append(_issue(
                f"knowledge:{issue.get('gate') or 'quality'}",
                "critical",
                str(issue.get("message") or "课程知识库存在阻断问题"),
                "修复课程知识、能力、易错、提升和课程位置之间的引用后再发布",
            ))
    structural_coherence_codes = {
        "coherence:no_sections",
        "coherence:invalid_section_identity",
        "coherence:section_order_mismatch",
        "coherence:unknown_prerequisite",
        "coherence:forward_prerequisite",
        "coherence:missing_objective",
        "coherence:missing_responsibility",
    }
    for issue in coherence_quality.get("blocking_issues") or []:
        if str(issue.get("code") or "") not in structural_coherence_codes:
            continue
        blocking_issues.append(_issue(
            str(issue.get("code") or "coherence:quality"),
            "critical" if issue.get("severity") == "critical" else "major",
            str(issue.get("message") or "课程跨章节一致性存在阻断问题"),
            "按全课总编契约定点修复目标小节，保持其他章节不变",
            str(issue.get("node_id") or ""),
        ))
    final_status = (
        "passed"
        if blueprint_report.get("passed") and difficulty_alignment.get("passed")
        and grounding_quality.get("passed") and knowledge_quality.get("strict_passed")
        and coherence_quality.get("strict_passed") and not weak_nodes
        and not quality_warnings
        else "completed_with_warnings"
    )
    return {
        "contract_version": QUALITY_CONTRACT_VERSION,
        "course_id": course_data.get("course_id"),
        "job_id": job_id,
        "stage": "final",
        "pedagogy_check": {
            "primary_mode": profile.primary_mode.value,
            "secondary_mode": profile.secondary_mode.value if profile.secondary_mode else None,
            "confidence": profile.confidence,
            "passed": True,
        },
        "blueprint_check": blueprint_report,
        "difficulty_alignment": difficulty_alignment,
        "grounding_quality": grounding_quality,
        "knowledge_quality": knowledge_quality,
        "course_knowledge_base_revision_id": course_knowledge_base.get("revision_id"),
        "coherence_quality": coherence_quality,
        "course_coherence_revision_id": coherence_quality.get("contract_revision_id"),
        "node_quality_summary": {
            "total": len(node_reports),
            "passed": len(node_reports) - len(weak_nodes),
            "weak": len(weak_nodes),
            "average_score": round(sum(float(report.get("score") or 0) for report in node_reports) / max(1, len(node_reports)), 3),
        },
        "weak_nodes": weak_nodes,
        "manual_review_required_nodes": manual_review_nodes,
        "publication_allowed": not blocking_issues,
        "blocking_issues": blocking_issues,
        "warnings": quality_warnings,
        "material_coverage": grounding_quality["material_coverage"],
        "brief_satisfaction": {
            "subject": (course_data.get("course_generation_brief") or {}).get("subject"),
            "hard_constraints": (course_data.get("course_generation_brief") or {}).get("hard_constraints", []),
            "course_shape": course_data.get("course_plan_constraint_report") or {},
            "status": "checked_after_content",
        },
        "final_status": final_status,
    }


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


def _feedback_structure_issues(text: str, node_id: str) -> list[dict[str, Any]]:
    body = _feedback_module_body(text)
    if not body:
        return []

    issues: list[dict[str, Any]] = []
    task_numbers = {
        match.group(1)
        for match in re.finditer(
            r"(?im)^(?:###\s+|\*\*)?任务\s*([0-9一二三四五六七八九十]+)",
            body,
        )
    }
    internal_headings = re.findall(r"(?m)^###\s+\S.+$", body)
    required_heading_count = len(task_numbers) if len(task_numbers) >= 2 else 1
    if (len(body) >= 700 or len(task_numbers) >= 2) and len(internal_headings) < required_heading_count:
        issues.append(_issue(
            "feedback_structure_flat",
            "major",
            "检查与反馈包含多个任务或长答案，但缺少任务级三级标题，渲染后会形成答案墙",
            "按 `### 任务 N：名称` 拆分每个任务，并在任务内区分核对标准、参考结论、依据和典型错误",
            node_id,
        ))

    inline_code = re.findall(r"(?<!`)`([^`\n]+)`(?!`)", body)
    math_code_count = sum(1 for value in inline_code if _looks_like_math_code(value))
    if math_code_count >= 4:
        issues.append(_issue(
            "feedback_math_as_code",
            "major",
            f"检查与反馈中有 {math_code_count} 处数学表达使用行内代码，公式语义和阅读排版会退化",
            "将幂、上下标、分式、复杂度和数学关系改用 `$...$` 或 `$$...$$`，反引号只保留给程序代码",
            node_id,
        ))
    return issues


def _feedback_module_body(text: str) -> str:
    matches = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", text))
    for index, match in enumerate(matches):
        heading = _normalized_heading(match.group(1))
        if not any(marker in heading for marker in ("检查与反馈", "答案与评价标准", "评价标准", "运行结果", "测试与质量")):
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        return text[match.end():end].strip()
    return ""


def _looks_like_math_code(value: str) -> bool:
    text = str(value or "").strip()
    return bool(re.search(
        r"[ΘΩε≈≤≥∞]"
        r"|[A-Za-z0-9)\]]\^[({A-Za-z0-9+\-]"
        r"|(?:log|ln)_[A-Za-z0-9(]"
        r"|\bN\s*/\s*log\b"
        r"|(?:T|f)\s*\([^)]*\)\s*=",
        text,
        flags=re.IGNORECASE,
    ))


def _normalized_heading(value: str) -> str:
    text = re.sub(r"^[#\s]+", "", str(value or ""))
    return re.sub(r"[\s　]+", "", text).strip("：:、。 ").lower()


def _same_heading(left: str, right: str) -> bool:
    return bool(right) and _normalized_heading(left) == _normalized_heading(right)


def _module_heading_matches(heading: str, label: str) -> bool:
    normalized_heading = _normalized_heading(heading)
    normalized_label = _normalized_heading(label)
    return bool(normalized_label) and (
        normalized_heading == normalized_label
        or normalized_heading.startswith(f"{normalized_label}：")
        or normalized_heading.startswith(f"{normalized_label}:")
    )


def _current_node_quality(node: dict[str, Any]) -> dict[str, Any]:
    report = node.get("generation_quality") or {}
    if report.get("contract_version") == QUALITY_CONTRACT_VERSION:
        return report
    return evaluate_node_content(str(node.get("node_content") or ""), node)


def _key_point_covered(point: str, text: str) -> bool:
    lowered = text.lower()
    normalized = re.sub(r"\s+", "", point.lower())
    if normalized and normalized in re.sub(r"\s+", "", lowered):
        return True
    fragments = [
        fragment.strip().lower()
        for fragment in re.split(r"[与和及、，,:：;；/（）()\[\]\s]+", point)
        if len(fragment.strip()) >= 2
    ]
    generic = {"概念", "原理", "方法", "步骤", "应用", "分析", "实现", "特点", "问题", "基础"}
    meaningful = [fragment for fragment in fragments if fragment not in generic]
    if not meaningful:
        return False
    hits = sum(fragment in lowered for fragment in meaningful)
    return hits >= max(1, (len(meaningful) + 1) // 2)


def _dimension_average(values: dict[str, Any]) -> float:
    numeric = [float(value) for value in values.values() if isinstance(value, (int, float))]
    return sum(numeric) / max(1, len(numeric))


def _issue(
    code: str,
    severity: str,
    message: str,
    suggestion: str,
    node_id: str = "",
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "suggestion": suggestion,
        "node_id": node_id,
    }


def _score_from_issues(issues: list[dict[str, Any]]) -> float:
    penalties = {"critical": 0.35, "major": 0.12, "warning": 0.05, "info": 0.02}
    return round(max(0.0, 1.0 - sum(penalties.get(str(item.get("severity")), 0.05) for item in issues)), 3)


def _has_critical(issues: list[dict[str, Any]]) -> bool:
    return any(item.get("severity") == "critical" for item in issues)


__all__ = [
    "QUALITY_CONTRACT_VERSION",
    "validate_blueprint",
    "validate_difficulty_blueprint",
    "evaluate_node_content",
    "evaluate_difficulty_alignment",
    "build_difficulty_alignment_report",
    "build_final_course_quality_report",
]
