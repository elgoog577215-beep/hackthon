"""Deterministic course-type routing and generation contracts.

Course type controls how a course is organized. Subject pedagogy still controls
how the content is taught, while the learner starting profile controls where an
individual path expands, compresses, or remains provisional.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any


COURSE_TYPE_SYSTEMATIC = "systematic"
COURSE_TYPE_PROJECT = "project"
COURSE_TYPE_INQUIRY = "inquiry"
COURSE_TYPE_EXAM = "exam"

COURSE_TYPES = {
    COURSE_TYPE_SYSTEMATIC,
    COURSE_TYPE_PROJECT,
    COURSE_TYPE_INQUIRY,
    COURSE_TYPE_EXAM,
}
ENABLED_COURSE_TYPES = {
    COURSE_TYPE_SYSTEMATIC,
    COURSE_TYPE_PROJECT,
    COURSE_TYPE_INQUIRY,
    COURSE_TYPE_EXAM,
}


class CourseTypeNotEnabled(ValueError):
    def __init__(self, course_type: str) -> None:
        self.course_type = course_type
        self.code = "course_type_not_enabled"
        super().__init__(f"课程类型尚未开放：{course_type}")


def ensure_course_type_enabled(course_type: str) -> None:
    if course_type not in ENABLED_COURSE_TYPES:
        raise CourseTypeNotEnabled(course_type)


COURSE_TYPE_CONTRACTS: dict[str, dict[str, Any]] = {
    COURSE_TYPE_SYSTEMATIC: {
        "label": "系统学习",
        "organizing_question": "学习者要系统掌握哪个知识领域？",
        "planning_sequence": ["知识地图", "先修关系", "基础到进阶", "综合应用"],
        "outline_requirements": [
            "覆盖目标领域的必要知识结构",
            "按先修关系从基础推进到综合应用",
            "不得只围绕零散问题或单一项目罗列内容",
        ],
        "completion_evidence": "学习者能够解释、迁移并综合应用核心知识",
    },
    COURSE_TYPE_PROJECT: {
        "label": "项目实战",
        "organizing_question": "学习者要完成什么项目，以及为了完成它需要补齐什么？",
        "planning_sequence": ["项目目标", "交付物", "项目里程碑", "能力缺口", "学习与验证"],
        "outline_requirements": [
            "章节围绕可检查的项目里程碑组织，而不是写成普通学科目录",
            "把学习者已有经验、重点补充和待验证内容显式映射到学习路径",
            "每个阶段必须同时包含必要知识、实践动作和可检查产出",
            "最终路径必须能够完成约定交付物",
        ],
        "completion_evidence": "学习者完成约定交付物，并能说明关键决策与验证依据",
    },
    COURSE_TYPE_INQUIRY: {
        "label": "问题探究",
        "organizing_question": "学习者要回答什么核心问题？",
        "planning_sequence": ["界定问题", "拆解子问题", "组织证据", "检验解释", "形成结论"],
        "required_planning_stages": [
            {"id": "define_question", "label": "界定核心问题"},
            {"id": "decompose_questions", "label": "拆解子问题与假设"},
            {"id": "gather_evidence", "label": "组织证据"},
            {"id": "test_explanations", "label": "检验解释与反例"},
            {"id": "form_conclusion", "label": "形成有边界的结论"},
        ],
        "outline_requirements": [
            "目录由核心问题和子问题推进，不得伪装成带问号的普通章节目录",
            "区分已有认识、待验证假设、证据需求和阶段性结论",
            "最终形成有证据边界的回答或判断",
        ],
        "completion_evidence": "学习者形成可追溯证据、能说明边界的结论",
    },
    COURSE_TYPE_EXAM: {
        "label": "考试冲刺",
        "organizing_question": "在限定时间内，哪些考纲能力最需要优先补齐？",
        "planning_sequence": ["考试范围", "当前准备度", "薄弱点", "复习优先级", "模拟验证"],
        "required_planning_stages": [
            {"id": "scope_diagnosis", "label": "考纲与准备度诊断"},
            {"id": "priority_review", "label": "高优先级复习"},
            {"id": "targeted_practice", "label": "薄弱点专项练习"},
            {"id": "mock_assessment", "label": "限时模拟与反馈"},
            {"id": "final_consolidation", "label": "考前巩固与策略"},
        ],
        "outline_requirements": [
            "按考纲覆盖、剩余时间和薄弱程度确定优先级",
            "每个阶段包含复习目标、典型任务和检查方式",
            "不得为了形式完整平均分配学习时间",
        ],
        "completion_evidence": "学习者通过分阶段检查与模拟任务达到目标准备度",
    },
}


COURSE_SCALE_MICRO = "micro"
COURSE_SCALE_UNIT = "unit"
COURSE_SCALE_FULL_TERM = "full_term"

COURSE_SCALES = (
    COURSE_SCALE_MICRO,
    COURSE_SCALE_UNIT,
    COURSE_SCALE_FULL_TERM,
)

# Capacity is expressed in learnable sections, not in wall-clock hours. One
# section is the smallest unit that can carry a topic together with its worked
# example and check, so it is also the honest unit for "how much fits".
SECTIONS_PER_CLASS_HOUR = 1.0

COURSE_SCALE_SPECS: dict[str, dict[str, Any]] = {
    COURSE_SCALE_MICRO: {
        "label": "微型课",
        "min_class_hours": 1,
        "max_class_hours": 8,
        "may_claim_complete_subject": False,
        "coverage_promise": "只覆盖一个可检查的核心切面，不承担学科完整覆盖",
        "positioning_template": "{subject}核心概览课",
        "honest_naming": [
            "标题与定位必须体现“核心/入门/概览/专题”，不得自称完整课程",
            "必须显式列出本次不覆盖的知识点",
        ],
    },
    COURSE_SCALE_UNIT: {
        "label": "单元课",
        "min_class_hours": 9,
        "max_class_hours": 24,
        "may_claim_complete_subject": False,
        "coverage_promise": "完整覆盖一个单元或模块，不承担整门学科的完整覆盖",
        "positioning_template": "{subject}单元课",
        "honest_naming": [
            "标题与定位限定到所覆盖的单元或模块，不得自称完整学科课程",
            "必须显式列出本单元之外不覆盖的知识点",
        ],
    },
    COURSE_SCALE_FULL_TERM: {
        "label": "完整学期课",
        "min_class_hours": 25,
        "max_class_hours": None,
        "may_claim_complete_subject": True,
        "coverage_promise": "覆盖学科主干知识结构，可按学期课标准组织",
        "positioning_template": "{subject}完整学期课",
        "honest_naming": [
            "仍需列出确实不覆盖的进阶或选修知识点",
        ],
    },
}


COVERAGE_STATUS_COMPLETE = "complete"
COVERAGE_STATUS_PARTIAL = "partial"
COVERAGE_STATUS_UNDECIDABLE = "undecidable"


# Canonical subject scope baselines. These describe what a subject is normally
# expected to contain, so that a short course can be told apart from a complete
# one before any content is generated. A subject that is absent here is not
# assumed complete; it is reported as ``undecidable`` and still may not claim
# full coverage below full-term scale.
_SUBJECT_SCOPE_BASELINES: tuple[dict[str, Any], ...] = (
    {
        "scope_id": "math.calculus.core_v1",
        "canonical_name": "微积分",
        "aliases": ("微积分", "高等数学", "calculus"),
        "core_topics": (
            ("函数、极限与连续", ("极限", "连续性", "连续函数", "limit")),
            ("导数定义与求导法则", ("导数", "求导法则", "微商", "derivative")),
            ("隐函数求导与相关变化率", ("隐函数", "相关变化率", "隐式求导")),
            ("微分与线性近似", ("线性近似", "微分近似", "全微分", "切线近似")),
            ("中值定理", ("中值定理", "拉格朗日中值", "罗尔定理", "泰勒展开")),
            ("洛必达法则与未定式", ("洛必达", "未定式", "lhopital")),
            (
                "导数应用：单调性、极值与凹凸性",
                ("极值", "单调性", "凹凸", "最优化", "曲线作图"),
            ),
            ("不定积分与基本积分表", ("不定积分", "原函数", "基本积分")),
            (
                "积分技巧：换元与分部积分",
                ("换元积分", "分部积分", "积分技巧", "有理函数积分"),
            ),
            ("定积分与微积分基本定理", ("定积分", "微积分基本定理", "牛顿莱布尼茨")),
            (
                "定积分的几何与物理应用",
                ("面积计算", "体积计算", "弧长", "旋转体", "积分应用"),
            ),
            ("反常积分", ("反常积分", "广义积分", "无穷积分")),
            ("微分方程入门", ("微分方程", "可分离变量", "一阶线性方程")),
        ),
        "extended_topics": (
            "无穷级数与幂级数",
            "多元函数微分学",
            "重积分",
        ),
    },
    {
        "scope_id": "math.linear_algebra.core_v1",
        "canonical_name": "线性代数",
        "aliases": ("线性代数", "linearalgebra"),
        "core_topics": (
            ("向量与线性组合", ("向量", "线性组合", "张成")),
            ("线性相关与线性无关", ("线性相关", "线性无关")),
            ("矩阵运算", ("矩阵运算", "矩阵乘法", "矩阵加法")),
            ("初等行变换与高斯消元", ("高斯消元", "行变换", "阶梯形")),
            ("线性方程组的解结构", ("线性方程组", "解结构", "通解")),
            ("矩阵的秩", ("矩阵的秩", "rank")),
            ("行列式", ("行列式", "determinant")),
            ("逆矩阵", ("逆矩阵", "可逆矩阵")),
            ("向量空间与子空间", ("向量空间", "子空间")),
            ("基、维数与坐标", ("基与维数", "维数", "坐标变换", "基底")),
            ("线性变换", ("线性变换", "线性映射")),
            ("特征值与特征向量", ("特征值", "特征向量")),
            ("矩阵对角化", ("对角化", "相似矩阵")),
        ),
        "extended_topics": (
            "内积空间与正交化",
            "二次型",
            "奇异值分解",
        ),
    },
)


_LEGACY_PURPOSE_TO_TYPE = {
    "systematic": COURSE_TYPE_SYSTEMATIC,
    "exam_sprint": COURSE_TYPE_EXAM,
    "material_organization": COURSE_TYPE_SYSTEMATIC,
    "personalized_remedial": COURSE_TYPE_SYSTEMATIC,
}

_LEGACY_COMPOSITION_TO_TYPE = {
    "project_driven": COURSE_TYPE_PROJECT,
    "inquiry_driven": COURSE_TYPE_INQUIRY,
}

_TYPE_TO_PURPOSE = {
    COURSE_TYPE_SYSTEMATIC: "systematic",
    COURSE_TYPE_PROJECT: "systematic",
    COURSE_TYPE_INQUIRY: "systematic",
    COURSE_TYPE_EXAM: "exam_sprint",
}

_TYPE_TO_COMPOSITION = {
    COURSE_TYPE_SYSTEMATIC: "balanced",
    COURSE_TYPE_PROJECT: "project_driven",
    COURSE_TYPE_INQUIRY: "inquiry_driven",
    COURSE_TYPE_EXAM: "example_driven",
}


def resolve_course_type(
    course_type: Any = None,
    *,
    course_purpose: Any = None,
    composition_style: Any = None,
) -> tuple[str, str]:
    """Resolve the new type without breaking old requests.

    The explicit new field always wins. Legacy purpose is stronger than legacy
    composition because it historically represented a user-selected goal.
    """
    explicit = _string_value(course_type)
    if explicit in COURSE_TYPES:
        return explicit, "course_type"
    legacy_purpose = _string_value(course_purpose)
    if legacy_purpose in _LEGACY_PURPOSE_TO_TYPE and legacy_purpose != "systematic":
        return _LEGACY_PURPOSE_TO_TYPE[legacy_purpose], "course_purpose"
    legacy_style = _string_value(composition_style)
    if legacy_style in _LEGACY_COMPOSITION_TO_TYPE:
        return _LEGACY_COMPOSITION_TO_TYPE[legacy_style], "composition_style"
    if legacy_purpose == "systematic":
        return COURSE_TYPE_SYSTEMATIC, "course_purpose"
    return COURSE_TYPE_SYSTEMATIC, "default"


def compatible_course_purpose(course_type: str, course_purpose: Any = None) -> str:
    legacy = _string_value(course_purpose)
    if legacy in _LEGACY_PURPOSE_TO_TYPE:
        return legacy
    return _TYPE_TO_PURPOSE.get(course_type, "systematic")


def course_purpose_for_type(course_type: str) -> str:
    return _TYPE_TO_PURPOSE.get(course_type, "systematic")


def default_composition_style(course_type: str) -> str:
    return _TYPE_TO_COMPOSITION.get(course_type, "balanced")


def compile_course_type_brief(
    *,
    course_type: Any,
    course_intent: Any,
    learner_starting_profile: Any,
    topic: str,
    requirements: str = "",
    learner_profile_summary: str = "",
    course_purpose: Any = None,
    composition_style: Any = None,
) -> dict[str, Any]:
    """Compile type-specific request data into the brief used by the LLM chain."""
    resolved_type, resolved_from = resolve_course_type(
        course_type,
        course_purpose=course_purpose,
        composition_style=composition_style,
    )
    intent = _model_dict(course_intent)
    intent["type"] = resolved_type
    intent = _fill_intent_defaults(resolved_type, intent, topic, requirements)
    starting_profile = _compile_starting_profile(
        learner_starting_profile,
        course_type=resolved_type,
        course_intent=intent,
        learner_profile_summary=learner_profile_summary,
    )
    contract = deepcopy(COURSE_TYPE_CONTRACTS[resolved_type])
    return {
        "course_type": resolved_type,
        "course_type_label": contract["label"],
        "course_type_resolved_from": resolved_from,
        "course_type_contract": contract,
        "course_intent": intent,
        "learner_starting_profile": starting_profile,
        "personalization_rationale": _personalization_rationale(
            resolved_type,
            intent,
            starting_profile,
        ),
    }


def apply_course_type_brief(
    brief: dict[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    brief.update(compile_course_type_brief(**kwargs))
    contract = brief["course_type_contract"]
    hard_constraints = list(brief.get("hard_constraints") or [])
    for item in contract.get("outline_requirements") or []:
        if item not in hard_constraints:
            hard_constraints.append(item)
    brief["hard_constraints"] = hard_constraints
    expected_deliverable = str(
        (brief.get("course_intent") or {}).get("expected_deliverable") or ""
    ).strip()
    if expected_deliverable:
        deliverables = list(brief.get("expected_deliverables") or [])
        if expected_deliverable not in deliverables:
            deliverables.insert(0, expected_deliverable)
        brief["expected_deliverables"] = deliverables
    return brief


def _fill_intent_defaults(
    course_type: str,
    intent: dict[str, Any],
    topic: str,
    requirements: str,
) -> dict[str, Any]:
    result = deepcopy(intent)
    result["schema_version"] = "course_intent_v1"
    if course_type == COURSE_TYPE_PROJECT:
        if not str(result.get("project_goal") or "").strip():
            result["project_goal"] = topic
        if not str(result.get("expected_deliverable") or "").strip():
            result["expected_deliverable"] = "完成可展示、可检查的项目成果"
        result.setdefault("prior_experience", "")
        result.setdefault("current_uncertainty", "")
        result.setdefault("project_constraints", requirements)
    elif course_type == COURSE_TYPE_INQUIRY:
        if not str(result.get("core_question") or "").strip():
            result["core_question"] = topic
        result.setdefault("existing_understanding", "")
        result.setdefault("evidence_scope", "")
        result.setdefault("desired_output", "形成有证据边界的回答")
    elif course_type == COURSE_TYPE_EXAM:
        if not str(result.get("exam_name") or "").strip():
            result["exam_name"] = topic
        result.setdefault("exam_date", "")
        result.setdefault("exam_scope", requirements)
        result.setdefault("current_preparation", "")
    else:
        if not str(result.get("learning_goal") or "").strip():
            result["learning_goal"] = topic
        result.setdefault("desired_outcome", requirements)
        result.setdefault("existing_foundation", "")
    return result


def _compile_starting_profile(
    raw_profile: Any,
    *,
    course_type: str,
    course_intent: dict[str, Any],
    learner_profile_summary: str,
) -> dict[str, Any]:
    profile = _model_dict(raw_profile)
    strengths = _string_list(profile.get("self_reported_strengths"))
    focus_areas = _string_list(profile.get("focus_areas"))
    needs_validation = _string_list(profile.get("needs_validation"))
    if course_type == COURSE_TYPE_PROJECT:
        prior = str(course_intent.get("prior_experience") or "").strip()
        uncertainty = str(course_intent.get("current_uncertainty") or "").strip()
        if prior and prior not in strengths:
            strengths.append(prior)
        if uncertainty and uncertainty not in focus_areas:
            focus_areas.append(uncertainty)
        for item in strengths:
            marker = f"待在项目任务中验证：{item}"
            if marker not in needs_validation:
                needs_validation.append(marker)
    elif course_type == COURSE_TYPE_INQUIRY:
        understanding = str(
            course_intent.get("existing_understanding") or ""
        ).strip()
        if understanding:
            summary = str(profile.get("summary") or "").strip()
            profile["summary"] = summary or understanding
            marker = f"待通过证据检验的已有认识：{understanding}"
            if marker not in needs_validation:
                needs_validation.append(marker)
    elif course_type == COURSE_TYPE_EXAM:
        preparation = str(
            course_intent.get("current_preparation") or ""
        ).strip()
        if preparation:
            summary = str(profile.get("summary") or "").strip()
            profile["summary"] = summary or preparation
            marker = f"待通过诊断题或模拟任务验证的当前准备度：{preparation}"
            if marker not in needs_validation:
                needs_validation.append(marker)
    summary = str(profile.get("summary") or learner_profile_summary or "").strip()
    evidence_basis = str(profile.get("evidence_basis") or "self_reported").strip()
    if evidence_basis not in {"self_reported", "interview", "observed", "mixed"}:
        evidence_basis = "self_reported"
    if course_type == COURSE_TYPE_PROJECT:
        has_starting_evidence = bool(strengths or focus_areas)
    else:
        has_starting_evidence = bool(strengths or focus_areas or summary)
    default_status = "tentative" if has_starting_evidence else "insufficient"
    status = str(profile.get("status") or default_status).strip()
    if status not in {"insufficient", "tentative", "confirmed"}:
        status = default_status
    if evidence_basis == "self_reported" and status == "confirmed":
        status = "tentative"
    return {
        "summary": summary,
        "self_reported_strengths": strengths,
        "focus_areas": focus_areas,
        "needs_validation": needs_validation,
        "evidence_basis": evidence_basis,
        "status": status,
    }


def _personalization_rationale(
    course_type: str,
    intent: dict[str, Any],
    profile: dict[str, Any],
) -> list[str]:
    result = [
        "学习起点仅作为暂定规划依据，未经学习行为验证的自述不得写成已掌握事实。"
    ]
    if course_type == COURSE_TYPE_PROJECT:
        if profile.get("status") == "insufficient":
            result.append(
                "起点信息不足；不得压缩任何内容，未证实能力必须标为 verify_in_project。"
            )
        if profile.get("self_reported_strengths"):
            result.append(
                "自述已有经验只能暂定压缩，对应能力必须标为 verify_in_project 并保留验证节点。"
            )
        if profile.get("focus_areas"):
            result.append("当前不确定项需要展开为重点知识、实践动作和检查产出。")
        result.append(
            f"所有个性化调整必须服务项目交付物：{intent.get('expected_deliverable')}"
        )
    elif course_type == COURSE_TYPE_INQUIRY:
        result.append(
            "已有认识只能作为待检验假设；目录必须保留证据搜集、反例检验和结论边界。"
        )
        evidence_scope = str(intent.get("evidence_scope") or "").strip()
        if evidence_scope:
            result.append(f"探究证据必须优先覆盖用户指定范围：{evidence_scope}")
    elif course_type == COURSE_TYPE_EXAM:
        result.append(
            "当前准备度只用于安排首轮优先级，必须通过诊断题或模拟任务校准。"
        )
        exam_date = str(intent.get("exam_date") or "").strip()
        if exam_date:
            result.append(f"复习节奏必须在考试日期 {exam_date} 前完成模拟与考前巩固。")
    return result


def resolve_course_scale(
    *,
    class_hours: Any = None,
    section_count: Any = None,
) -> dict[str, Any]:
    """Classify requested course size into 微型课 / 单元课 / 完整学期课.

    Class hours are the user-facing size signal. When they are absent the
    planned section count stands in, because one section is roughly one
    teachable hour of material.
    """
    hours = _positive_number(class_hours)
    sections = _positive_number(section_count)
    effective = hours or sections
    if effective is None:
        scale_id = COURSE_SCALE_FULL_TERM
        basis = "unspecified"
    else:
        scale_id = COURSE_SCALE_MICRO
        for candidate in COURSE_SCALES:
            spec = COURSE_SCALE_SPECS[candidate]
            maximum = spec["max_class_hours"]
            if maximum is None or effective <= maximum:
                scale_id = candidate
                break
        basis = "class_hours" if hours else "section_count"
    spec = COURSE_SCALE_SPECS[scale_id]
    return {
        "schema_version": "course_scale_v1",
        "scale": scale_id,
        "scale_label": spec["label"],
        "resolved_from": basis,
        "class_hours": hours,
        "section_count": sections,
        "may_claim_complete_subject": spec["may_claim_complete_subject"],
        "coverage_promise": spec["coverage_promise"],
    }


def resolve_subject_scope_baseline(subject: Any) -> dict[str, Any] | None:
    """Look up the canonical topic baseline for a subject, if one is known.

    This baseline exists only so a short course can name what it leaves out.
    It is never a content source and never grants the course an identity — the
    outline still comes entirely from the course's own planning chain.
    """
    normalized = _normalize_subject(subject)
    if not normalized:
        return None
    for baseline in _SUBJECT_SCOPE_BASELINES:
        for alias in baseline["aliases"]:
            if _normalize_subject(alias) and _normalize_subject(alias) in normalized:
                return {
                    "scope_id": baseline["scope_id"],
                    "canonical_name": baseline["canonical_name"],
                    "core_topics": [
                        label for label, _terms in baseline["core_topics"]
                    ],
                    "core_topic_terms": {
                        label: list(terms)
                        for label, terms in baseline["core_topics"]
                    },
                    "extended_topics": list(baseline["extended_topics"]),
                }
    return None


def judge_course_coverage(
    *,
    subject: Any,
    class_hours: Any = None,
    section_count: Any = None,
    planned_topics: Any = None,
) -> dict[str, Any]:
    """Decide, before generation, whether the requested size can cover the subject.

    ``planned_topics`` is optional. Without it the verdict answers "can this
    size cover the subject at all"; with it (chapter titles and focuses from a
    freshly planned skeleton) the verdict also reports which canonical topics
    the plan actually reaches and which it must declare out of scope.
    """
    scale = resolve_course_scale(
        class_hours=class_hours,
        section_count=section_count,
    )
    baseline = resolve_subject_scope_baseline(subject)
    spec = COURSE_SCALE_SPECS[scale["scale"]]
    subject_text = str(subject or "").strip() or "本课程"
    verdict: dict[str, Any] = {
        "schema_version": "course_coverage_verdict_v1",
        "subject": subject_text,
        "scale": scale["scale"],
        "scale_label": scale["scale_label"],
        "class_hours": scale["class_hours"],
        "section_count": scale["section_count"],
        "may_claim_complete_subject": scale["may_claim_complete_subject"],
        "coverage_promise": spec["coverage_promise"],
        "honest_naming": list(spec["honest_naming"]),
        "scope_id": (baseline or {}).get("scope_id", ""),
        "core_topics": list((baseline or {}).get("core_topics") or []),
        "covered_topics": [],
        "uncovered_topics": [],
        "advisories": [],
    }
    # Class hours are the real ceiling. A section count may be a product floor
    # (the "complete course" baseline), and treating a floor as capacity is
    # exactly how a short course used to pass as a complete one.
    capacity = _positive_number(scale["class_hours"]) or _positive_number(
        scale["section_count"]
    )
    if capacity is not None:
        capacity = int(capacity * SECTIONS_PER_CLASS_HOUR)
    if baseline is None:
        verdict["status"] = (
            COVERAGE_STATUS_COMPLETE
            if scale["may_claim_complete_subject"]
            else COVERAGE_STATUS_UNDECIDABLE
        )
        if not scale["may_claim_complete_subject"]:
            verdict["advisories"].append(
                f"没有 {subject_text} 的权威知识范围基线，无法判定是否完整覆盖；"
                f"按{scale['scale_label']}规格生成，不得自称完整课程。"
            )
        verdict["required_positioning"] = _required_positioning(spec, subject_text)
        return verdict

    core_topics = verdict["core_topics"]
    if planned_topics is None:
        # Pre-planning judgment: only capacity is known.
        if capacity is not None and capacity < len(core_topics):
            verdict["status"] = COVERAGE_STATUS_PARTIAL
            verdict["uncovered_topics"] = []
            verdict["advisories"].extend(
                _capacity_advisories(
                    subject_text=subject_text,
                    scale=scale,
                    capacity=capacity,
                    required=len(core_topics),
                )
            )
        else:
            verdict["status"] = (
                COVERAGE_STATUS_COMPLETE
                if scale["may_claim_complete_subject"]
                else COVERAGE_STATUS_PARTIAL
            )
            if verdict["status"] == COVERAGE_STATUS_PARTIAL:
                verdict["advisories"].append(
                    f"{scale['scale_label']}规格不承担 {subject_text} 的完整覆盖，"
                    "必须显式列出本次不覆盖的知识点。"
                )
        verdict["required_positioning"] = _required_positioning(spec, subject_text)
        return verdict

    covered, uncovered = _match_planned_topics(
        core_topics,
        baseline.get("core_topic_terms") or {},
        planned_topics,
    )
    verdict["covered_topics"] = covered
    verdict["uncovered_topics"] = uncovered
    if uncovered:
        verdict["status"] = COVERAGE_STATUS_PARTIAL
        verdict["advisories"].append(
            f"本次不覆盖：{'、'.join(uncovered)}；必须在课程定位中明确列出，"
            "不得默认学习者已经学过或暗示课程已完整覆盖。"
        )
        if capacity is not None and capacity < len(core_topics):
            verdict["advisories"].extend(
                _capacity_advisories(
                    subject_text=subject_text,
                    scale=scale,
                    capacity=capacity,
                    required=len(core_topics),
                )
            )
    elif scale["may_claim_complete_subject"]:
        verdict["status"] = COVERAGE_STATUS_COMPLETE
    else:
        verdict["status"] = COVERAGE_STATUS_PARTIAL
        verdict["advisories"].append(
            f"章节已覆盖 {subject_text} 的核心主题，但{scale['scale_label']}规格"
            "仍不足以按完整学期课深度展开，定位不得自称完整课程。"
        )
    verdict["required_positioning"] = _required_positioning(spec, subject_text)
    return verdict


def _capacity_advisories(
    *,
    subject_text: str,
    scale: dict[str, Any],
    capacity: int,
    required: int,
) -> list[str]:
    """Say plainly which of the two honest ways out the user can take."""
    return [
        f"{scale['scale_label']}（约 {capacity} 节可用容量）无法覆盖"
        f"{subject_text}的 {required} 个核心主题。",
        f"建议一：压缩为核心课，只保留最关键的 {capacity} 个主题，"
        "并把其余主题明确列为本次不覆盖。",
        f"建议二：增加课时至约 {required} 学时以上，方可按完整课程组织。",
    ]


def _required_positioning(spec: dict[str, Any], subject_text: str) -> str:
    return spec["positioning_template"].format(subject=subject_text)


def _match_planned_topics(
    core_topics: list[str],
    topic_terms: dict[str, list[str]],
    planned_topics: Any,
) -> tuple[list[str], list[str]]:
    """Split canonical topics into those a plan reaches and those it misses."""
    haystack = _normalize_subject(
        planned_topics
        if isinstance(planned_topics, str)
        else " ".join(_string_list(planned_topics))
    )
    covered: list[str] = []
    uncovered: list[str] = []
    for topic in core_topics:
        terms = topic_terms.get(topic) or [topic]
        if haystack and any(
            _normalize_subject(term) in haystack
            for term in terms
            if _normalize_subject(term)
        ):
            covered.append(topic)
        else:
            uncovered.append(topic)
    return covered, uncovered


def _normalize_subject(value: Any) -> str:
    return re.sub(r"[\s\-_·・]+", "", str(value or "")).strip().lower()


def _positive_number(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _model_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", exclude_none=True)
    if not isinstance(value, dict):
        return {}
    return {key: deepcopy(item) for key, item in value.items() if item is not None}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, (list, tuple, set)):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result[:20]


def _string_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


__all__ = [
    "COURSE_SCALE_FULL_TERM",
    "COURSE_SCALE_MICRO",
    "COURSE_SCALE_SPECS",
    "COURSE_SCALE_UNIT",
    "COURSE_SCALES",
    "COURSE_TYPES",
    "COURSE_TYPE_CONTRACTS",
    "COVERAGE_STATUS_COMPLETE",
    "COVERAGE_STATUS_PARTIAL",
    "COVERAGE_STATUS_UNDECIDABLE",
    "ENABLED_COURSE_TYPES",
    "CourseTypeNotEnabled",
    "apply_course_type_brief",
    "compatible_course_purpose",
    "compile_course_type_brief",
    "course_purpose_for_type",
    "default_composition_style",
    "ensure_course_type_enabled",
    "judge_course_coverage",
    "resolve_course_scale",
    "resolve_course_type",
    "resolve_subject_scope_baseline",
]
