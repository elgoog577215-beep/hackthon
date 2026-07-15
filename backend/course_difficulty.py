"""课程难度领域契约。

难度在这里表示学习者需要完成的能力表现、可获得的支架和
验收时需要的独立性，而不是文本长度、术语数量或公式密度。本模块
只包含确定性规则，不调用大模型。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Iterable


DIFFICULTY_CONTRACT_VERSION = "course_difficulty_v1"


class DifficultyLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class NodeDifficultyRole(str, Enum):
    BRIDGE = "bridge"
    FOUNDATION = "foundation"
    WORKED_EXAMPLE = "worked_example"
    GUIDED_PRACTICE = "guided_practice"
    INDEPENDENT_TASK = "independent_task"
    INTEGRATION = "integration"
    TRANSFER = "transfer"
    CHECKPOINT = "checkpoint"
    CAPSTONE = "capstone"


@dataclass(frozen=True)
class EntryRequirement:
    minimum_readiness: int
    required_capabilities: tuple[str, ...]
    diagnostic_when_unknown: bool = True


@dataclass(frozen=True)
class ChallengeProfile:
    prerequisite_load: int
    abstraction: int
    reasoning_depth: int
    integration_scope: int
    task_complexity: int
    transfer_distance: int


@dataclass(frozen=True)
class SupportProfile:
    scaffold_intensity: int
    pacing_granularity: int
    feedback_frequency: int
    strategies: tuple[str, ...]


@dataclass(frozen=True)
class MasteryContract:
    accuracy: int
    independence: int
    explanation: int
    execution: int
    transfer: int
    required_evidence: tuple[str, ...]


@dataclass(frozen=True)
class DifficultyProfile:
    contract_version: str
    target_level: str
    label: str
    entry_requirement: EntryRequirement
    challenge_profile: ChallengeProfile
    support_profile: SupportProfile
    mastery_contract: MasteryContract
    subject_adapter: dict[str, Any]
    anti_patterns: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DifficultyGapAssessment:
    contract_version: str
    current_readiness: str | None
    readiness_status: str
    entry_requirement: int
    gap: int | None
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AdaptationDecision:
    contract_version: str
    strategy: str
    preserve_target: bool
    actions: tuple[str, ...]
    warnings: tuple[str, ...]
    preference: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExerciseDifficultyContract:
    autonomy: int
    reasoning_steps: int
    transfer_distance: int
    feedback_timing: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class NodeDifficultyContract:
    contract_version: str
    target_level: str
    node_role: str
    challenge: dict[str, int]
    support: dict[str, Any]
    mastery: dict[str, Any]
    subject_task: str
    required_evidence: tuple[str, ...]
    support_actions: tuple[str, ...]
    anti_patterns: tuple[str, ...]
    new_concept_load: int
    exercise_contract: ExerciseDifficultyContract
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CourseDifficultyCurve:
    contract_version: str
    target_level: str
    shape: str
    rules: tuple[str, ...]
    node_contracts: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SubjectDifficultyAdapterSpec:
    label: str
    tasks: dict[str, str]
    evidence_markers: tuple[str, ...]
    high_challenge_markers: tuple[str, ...]
    guardrail: str


ANTI_PATTERNS = (
    "不得只用更长的文本伪装更高难度",
    "不得只增加术语、公式、代码或题量",
    "不得通过删掉必要提示或跳过前置知识制造难度",
    "难度必须体现在推理、整合、独立性或迁移要求上",
)


LEVEL_CONFIG: dict[DifficultyLevel, dict[str, Any]] = {
    DifficultyLevel.BEGINNER: {
        "label": "入门",
        "entry": EntryRequirement(
            minimum_readiness=0,
            required_capabilities=("能读取课程中的基本信息",),
        ),
        "challenge": ChallengeProfile(1, 2, 2, 2, 2, 1),
        "support": SupportProfile(
            5,
            5,
            5,
            ("明确分步示范", "关键处给出提示", "任务后立即反馈"),
        ),
        "mastery": MasteryContract(
            3,
            2,
            2,
            3,
            1,
            ("用自己的话说明核心概念", "在支架下完成一个标准任务"),
        ),
    },
    DifficultyLevel.INTERMEDIATE: {
        "label": "进阶",
        "entry": EntryRequirement(
            minimum_readiness=1,
            required_capabilities=("已掌握课程主题的基础概念或基本操作",),
        ),
        "challenge": ChallengeProfile(3, 3, 3, 3, 3, 3),
        "support": SupportProfile(
            3,
            3,
            3,
            ("在新方法处提供示范", "练习前给出质量标准", "保留结果检查"),
        ),
        "mastery": MasteryContract(
            4,
            4,
            3,
            4,
            3,
            ("独立完成典型任务", "解释关键步骤和选择依据", "能检查并修正常见错误"),
        ),
    },
    DifficultyLevel.ADVANCED: {
        "label": "高阶",
        "entry": EntryRequirement(
            minimum_readiness=2,
            required_capabilities=("能独立处理该主题的典型问题", "能说明常用方法的边界"),
        ),
        "challenge": ChallengeProfile(4, 5, 5, 5, 5, 5),
        "support": SupportProfile(
            2,
            2,
            2,
            ("只在新约束或关键安全边界处提供支架", "用评价标准代替完整步骤", "任务完成后集中反馈"),
        ),
        "mastery": MasteryContract(
            5,
            5,
            5,
            5,
            5,
            ("独立处理开放约束问题", "说明取舍、边界和不确定性", "将能力迁移到非熟悉情境"),
        ),
    },
}


SUBJECT_ADAPTERS: dict[str, SubjectDifficultyAdapterSpec] = {
    "general": SubjectDifficultyAdapterSpec(
        "通用课程",
        {
            "beginner": "借助示例解释核心概念并完成标准应用",
            "intermediate": "独立选择方法解决典型问题并检查结果",
            "advanced": "在新情境中比较方案、处理约束并论证取舍",
        },
        ("解释", "应用", "检查"),
        ("比较", "取舍", "迁移", "边界"),
        "不能退化为百科式介绍",
    ),
    "math_formal": SubjectDifficultyAdapterSpec(
        "数学与形式科学",
        {
            "beginner": "根据定义和完整例题完成标准计算或推理",
            "intermediate": "独立选择定理或方法完成多步求解并检查条件",
            "advanced": "完成带条件的证明、非例构造或形式建模并说明边界",
        },
        ("定义", "步骤", "依据", "检查"),
        ("证明", "反例", "建模", "条件", "推导"),
        "直觉不能代替正式定义与论证",
    ),
    "programming_engineering": SubjectDifficultyAdapterSpec(
        "编程与工程技术",
        {
            "beginner": "按完整示例构建可运行结果并按预期输出验收",
            "intermediate": "独立实现、调试并测试一个典型工程任务",
            "advanced": "在多重约束下设计、定位故障、验证质量并说明架构取舍",
        },
        ("运行", "输出", "调试", "测试"),
        ("约束", "架构", "取舍", "性能", "故障"),
        "必须形成可运行、可验证、可解释的工程闭环",
    ),
    "natural_science": SubjectDifficultyAdapterSpec(
        "自然科学",
        {
            "beginner": "根据现象和已给模型完成标准解释或预测",
            "intermediate": "独立选择模型、使用证据解释典型现象并检查边界",
            "advanced": "设计证据链、比较竞争模型并处理不确定性与外推边界",
        },
        ("现象", "模型", "证据", "边界"),
        ("不确定性", "竞争模型", "实验设计", "外推"),
        "现象、模型、证据和结论必须分开",
    ),
    "life_medical": SubjectDifficultyAdapterSpec(
        "生命科学与医学基础",
        {
            "beginner": "借助结构图式说明位置、功能和基本机制",
            "intermediate": "独立连接结构、功能、调节与典型机制案例",
            "advanced": "在多层级系统中分析机制、证据、异常边界和不确定性",
        },
        ("结构", "功能", "机制", "调节"),
        ("层级", "异常", "证据", "不确定性", "系统"),
        "结构、功能和机制不能混写，不得越界给出个人诊疗建议",
    ),
    "humanities_social": SubjectDifficultyAdapterSpec(
        "人文与社会科学",
        {
            "beginner": "借助明确材料识别核心观点、理由和语境",
            "intermediate": "独立比较典型观点并用材料形成可辩护论证",
            "advanced": "评估材料限制、隐含前提与竞争解释，并回应强异议",
        },
        ("材料", "观点", "证据", "论证"),
        ("隐含前提", "限制", "异议", "竞争解释", "立场"),
        "事实、材料、观点和解释必须分开",
    ),
    "language_learning": SubjectDifficultyAdapterSpec(
        "语言学习",
        {
            "beginner": "借助语块、示范和句型支架完成标准场景表达",
            "intermediate": "在典型场景中独立理解并产出准确、得体的表达",
            "advanced": "在非熟悉场景中调整语域、策略和文化边界并处理歧义",
        },
        ("输入", "语块", "表达", "反馈"),
        ("语域", "歧义", "策略", "文化", "修复"),
        "每个能力波次必须有真实输出，不能停留在词表和语法讲解",
    ),
    "business_career": SubjectDifficultyAdapterSpec(
        "商业与职业技能",
        {
            "beginner": "借助模板和清单完成标准工作场景交付",
            "intermediate": "独立使用框架分析典型场景并交付可评价成果",
            "advanced": "在信息不完整和多重约束下决策、权衡风险并说明指标影响",
        },
        ("场景", "交付", "标准", "指标"),
        ("信息不完整", "风险", "权衡", "决策", "利益相关者"),
        "必须产出可使用、可评价的工作成果",
    ),
}


ROLE_SETTINGS: dict[NodeDifficultyRole, dict[str, Any]] = {
    NodeDifficultyRole.BRIDGE: {"challenge": -1, "support": 1, "concept": 2, "task": -1, "label": "补齐必要前置并完成入口检查"},
    NodeDifficultyRole.FOUNDATION: {"challenge": -1, "support": 1, "concept": 4, "task": -1, "label": "建立新概念或方法的稳定基础"},
    NodeDifficultyRole.WORKED_EXAMPLE: {"challenge": 0, "support": 1, "concept": 2, "task": 0, "label": "通过完整示范显示思考与检查过程"},
    NodeDifficultyRole.GUIDED_PRACTICE: {"challenge": 0, "support": 0, "concept": 2, "task": 0, "label": "在部分支架下练习并获得反馈"},
    NodeDifficultyRole.INDEPENDENT_TASK: {"challenge": 1, "support": -1, "concept": 1, "task": 1, "label": "独立完成典型任务并检查结果"},
    NodeDifficultyRole.INTEGRATION: {"challenge": 1, "support": -1, "concept": 2, "task": 1, "label": "整合多个概念或方法完成复合任务"},
    NodeDifficultyRole.TRANSFER: {"challenge": 1, "support": -1, "concept": 1, "task": 1, "label": "将已学能力迁移到非熟悉情境"},
    NodeDifficultyRole.CHECKPOINT: {"challenge": 0, "support": 0, "concept": 1, "task": 0, "label": "用可观察证据检查掌握并定位缺口"},
    NodeDifficultyRole.CAPSTONE: {"challenge": 1, "support": -1, "concept": 1, "task": 1, "label": "交付综合成果并说明质量、边界与改进"},
}


READINESS_SCORES = {
    "none": 0,
    "beginner": 1,
    "intermediate": 2,
    "advanced": 3,
}


def parse_difficulty_level(value: Any) -> DifficultyLevel:
    raw = str(getattr(value, "value", value) or "").strip().lower()
    aliases = {
        "入门": DifficultyLevel.BEGINNER,
        "初级": DifficultyLevel.BEGINNER,
        "进阶": DifficultyLevel.INTERMEDIATE,
        "中级": DifficultyLevel.INTERMEDIATE,
        "高阶": DifficultyLevel.ADVANCED,
        "高级": DifficultyLevel.ADVANCED,
        "专家": DifficultyLevel.ADVANCED,
    }
    if raw in aliases:
        return aliases[raw]
    try:
        return DifficultyLevel(raw)
    except ValueError:
        return DifficultyLevel.INTERMEDIATE


def compile_difficulty_profile(
    level: Any,
    *,
    primary_mode: Any = "general",
    secondary_mode: Any = None,
) -> DifficultyProfile:
    parsed = parse_difficulty_level(level)
    config = LEVEL_CONFIG[parsed]
    mode = _mode_value(primary_mode)
    secondary = _mode_value(secondary_mode) if secondary_mode else None
    adapter = SUBJECT_ADAPTERS.get(mode, SUBJECT_ADAPTERS["general"])
    adapter_payload = {
        "primary_mode": mode,
        "secondary_mode": secondary,
        "label": adapter.label,
        "performance_task": adapter.tasks[parsed.value],
        "evidence_markers": list(adapter.evidence_markers),
        "high_challenge_markers": list(adapter.high_challenge_markers),
        "guardrail": adapter.guardrail,
    }
    if secondary and secondary in SUBJECT_ADAPTERS and secondary != mode:
        secondary_adapter = SUBJECT_ADAPTERS[secondary]
        adapter_payload["secondary_requirement"] = (
            f"仅在完成主任务必需时注入：{secondary_adapter.tasks[parsed.value]}"
        )

    return DifficultyProfile(
        contract_version=DIFFICULTY_CONTRACT_VERSION,
        target_level=parsed.value,
        label=config["label"],
        entry_requirement=config["entry"],
        challenge_profile=config["challenge"],
        support_profile=config["support"],
        mastery_contract=config["mastery"],
        subject_adapter=adapter_payload,
        anti_patterns=ANTI_PATTERNS,
    )


def assess_readiness(
    profile: DifficultyProfile,
    current_readiness: Any = None,
) -> DifficultyGapAssessment:
    raw = str(getattr(current_readiness, "value", current_readiness) or "").strip().lower()
    if not raw:
        return DifficultyGapAssessment(
            contract_version=DIFFICULTY_CONTRACT_VERSION,
            current_readiness=None,
            readiness_status="unknown",
            entry_requirement=profile.entry_requirement.minimum_readiness,
            gap=None,
            evidence=("请求未提供明确就绪度，不根据动态学习痕迹推测",),
        )
    score = READINESS_SCORES.get(raw)
    if score is None:
        return DifficultyGapAssessment(
            contract_version=DIFFICULTY_CONTRACT_VERSION,
            current_readiness=raw,
            readiness_status="unknown",
            entry_requirement=profile.entry_requirement.minimum_readiness,
            gap=None,
            evidence=(f"无法解释就绪度值 {raw}",),
        )
    gap = profile.entry_requirement.minimum_readiness - score
    return DifficultyGapAssessment(
        contract_version=DIFFICULTY_CONTRACT_VERSION,
        current_readiness=raw,
        readiness_status=("ready" if gap <= 0 else "gap"),
        entry_requirement=profile.entry_requirement.minimum_readiness,
        gap=gap,
        evidence=(f"明确就绪度为 {raw}，与入口要求的级差为 {gap}",),
    )


def decide_adaptation(
    assessment: DifficultyGapAssessment,
    preference: str = "preserve_target_extend",
) -> AdaptationDecision:
    normalized_preference = preference if preference in {
        "preserve_target_extend",
        "split_foundation",
        "fast_track",
        "lower_target",
    } else "preserve_target_extend"

    if assessment.gap is None:
        strategy = "diagnostic_required"
        actions = ("保留目标难度", "在课程入口设置简短前置检查", "对检查中的缺口提供桥接支架")
        warnings = ("当前就绪度未知，不得伪造掌握度结论",)
        preserve_target = True
    elif assessment.gap <= 0:
        strategy = "fast_track_known_basics" if assessment.gap < 0 else "direct_entry"
        actions = (
            ("压缩已知基础并保留检查点",) if assessment.gap < 0
            else ("按目标难度直接进入",)
        )
        warnings = ()
        preserve_target = True
    elif normalized_preference == "lower_target":
        strategy = "lower_target_by_request"
        actions = ("仅根据用户明确选择重编译较低目标",)
        warnings = ("降低目标会改变最终掌握契约",)
        preserve_target = False
    elif normalized_preference == "fast_track":
        strategy = "fast_track_with_risk"
        actions = ("保留目标难度", "保留前置检查点", "允许学习者承担缺口风险")
        warnings = ("可能因前置不足导致中途失败",)
        preserve_target = True
    elif normalized_preference == "split_foundation" or assessment.gap >= 3:
        strategy = "split_foundation_course"
        actions = ("保留目标难度", "将必要基础拆为独立前置课", "目标课保持原掌握契约")
        warnings = ("学习时间将增加",)
        preserve_target = True
    elif assessment.gap == 1:
        strategy = "inline_bridge"
        actions = ("保留目标难度", "在首个能力波次内补齐一级前置缺口")
        warnings = ()
        preserve_target = True
    else:
        strategy = "prerequisite_unit"
        actions = ("保留目标难度", "在目标内容前增加前置单元", "前置单元通过检查后再进入主线")
        warnings = ("课程范围和学习时间将增加",)
        preserve_target = True

    return AdaptationDecision(
        contract_version=DIFFICULTY_CONTRACT_VERSION,
        strategy=strategy,
        preserve_target=preserve_target,
        actions=actions,
        warnings=warnings,
        preference=normalized_preference,
    )


def compile_course_difficulty_curve(
    *,
    profile: DifficultyProfile,
    nodes: Iterable[dict[str, Any]],
    adaptation: AdaptationDecision,
) -> CourseDifficultyCurve:
    node_list = list(nodes)
    roles = _roles_for_count(len(node_list), adaptation.strategy)
    contracts: list[dict[str, Any]] = []
    adapter = profile.subject_adapter

    for index, (node, role) in enumerate(zip(node_list, roles)):
        settings = ROLE_SETTINGS[role]
        challenge = asdict(profile.challenge_profile)
        for key in challenge:
            delta = settings["task"] if key == "task_complexity" else settings["challenge"]
            challenge[key] = _clamp(challenge[key] + delta)
        support = asdict(profile.support_profile)
        for key in ("scaffold_intensity", "pacing_granularity", "feedback_frequency"):
            support[key] = _clamp(int(support[key]) + int(settings["support"]))

        required_evidence = _dedupe([
            *profile.mastery_contract.required_evidence,
            *adapter.get("evidence_markers", []),
        ])
        if profile.target_level == DifficultyLevel.ADVANCED.value:
            required_evidence.extend(
                item for item in adapter.get("high_challenge_markers", [])
                if item not in required_evidence
            )
        exercise = ExerciseDifficultyContract(
            autonomy=profile.mastery_contract.independence,
            reasoning_steps=challenge["reasoning_depth"],
            transfer_distance=challenge["transfer_distance"],
            feedback_timing=("immediate" if support["feedback_frequency"] >= 4 else "after_attempt"),
            evidence=tuple(required_evidence[:6]),
        )
        support_actions = _support_actions(support, role)
        section_number = str(node.get("section_number") or "")
        node_id = str(node.get("node_id") or _node_id_from_section(section_number, index))
        contract = NodeDifficultyContract(
            contract_version=DIFFICULTY_CONTRACT_VERSION,
            target_level=profile.target_level,
            node_role=role.value,
            challenge=challenge,
            support=support,
            mastery=asdict(profile.mastery_contract),
            subject_task=f"{settings['label']}：{adapter.get('performance_task', '')}",
            required_evidence=tuple(required_evidence[:8]),
            support_actions=tuple(support_actions),
            anti_patterns=profile.anti_patterns,
            new_concept_load=int(settings["concept"]),
            exercise_contract=exercise,
            rationale=(
                f"第 {index + 1} 个正文节点承担 {role.value} 角色；"
                f"挑战与支架由 {profile.target_level} 基线经锯齿曲线调整"
            ),
        ).to_dict()
        contracts.append({
            "node_id": node_id,
            "section_number": section_number,
            **contract,
        })

    return CourseDifficultyCurve(
        contract_version=DIFFICULTY_CONTRACT_VERSION,
        target_level=profile.target_level,
        shape="sawtooth",
        rules=(
            "挑战总体上升，新能力波次可重新提高支架",
            "相邻节点挑战级差不超过 2",
            "新概念负荷和任务复杂度不在同一节无支架跃升",
            "课程末尾需要整合、迁移或综合成果证据",
        ),
        node_contracts=tuple(contracts),
    )


def attach_difficulty_contracts_to_plan(
    plan: dict[str, Any],
    *,
    profile: DifficultyProfile,
    adaptation: AdaptationDecision,
) -> dict[str, Any]:
    sections = [
        section
        for chapter in plan.get("chapters") or []
        for section in chapter.get("sections") or []
    ]
    curve = compile_course_difficulty_curve(
        profile=profile,
        nodes=sections,
        adaptation=adaptation,
    )
    by_number = {
        str(item.get("section_number") or ""): item
        for item in curve.node_contracts
    }
    for section in sections:
        section.pop("complexity", None)
        contract = by_number.get(str(section.get("section_number") or ""), {})
        section["difficulty_contract"] = {
            key: value
            for key, value in contract.items()
            if key not in {"node_id", "section_number"}
        }
    plan["difficulty_profile"] = profile.to_dict()
    plan["course_difficulty_curve"] = curve.to_dict()
    return curve.to_dict()


def ensure_course_difficulty_contracts(
    course_data: dict[str, Any],
    *,
    primary_mode: Any = "general",
    secondary_mode: Any = None,
) -> dict[str, Any]:
    """为旧课程恢复最小可执行难度契约。

    这是读取适配器：它只补结构化契约，不恢复旧 prompt，也不把旧
    `complexity` 当成新契约真源。
    """
    level = course_data.get("difficulty") or (course_data.get("generation_request") or {}).get("difficulty")
    profile = compile_difficulty_profile(
        level,
        primary_mode=primary_mode,
        secondary_mode=secondary_mode,
    )
    assessment = assess_readiness(
        profile,
        (course_data.get("generation_request") or {}).get("current_readiness"),
    )
    adaptation = decide_adaptation(
        assessment,
        str((course_data.get("generation_request") or {}).get("adaptation_preference") or "preserve_target_extend"),
    )

    nodes = [node for node in course_data.get("nodes") or [] if node.get("node_level", 1) == 2]
    blueprint = course_data.get("course_blueprint") or {}
    if not nodes:
        nodes = list(blueprint.get("nodes") or [])
    curve = compile_course_difficulty_curve(profile=profile, nodes=nodes, adaptation=adaptation).to_dict()
    contracts = {str(item.get("node_id") or ""): item for item in curve.get("node_contracts", [])}
    contract_by_number = {str(item.get("section_number") or ""): item for item in curve.get("node_contracts", [])}

    for node in course_data.get("nodes") or []:
        if node.get("node_level", 1) != 2:
            continue
        node.pop("complexity", None)
        item = contracts.get(str(node.get("node_id") or "")) or _match_contract_by_name(node, contract_by_number)
        if item and not node.get("difficulty_contract"):
            node["difficulty_contract"] = _strip_contract_identity(item)

    for node in blueprint.get("nodes") or []:
        node.pop("complexity", None)
        item = contracts.get(str(node.get("node_id") or "")) or contract_by_number.get(str(node.get("section_number") or ""))
        if item and not node.get("difficulty_contract"):
            node["difficulty_contract"] = _strip_contract_identity(item)

    course_data["difficulty_profile"] = course_data.get("difficulty_profile") or profile.to_dict()
    course_data["difficulty_gap_assessment"] = course_data.get("difficulty_gap_assessment") or assessment.to_dict()
    course_data["adaptation_decision"] = course_data.get("adaptation_decision") or adaptation.to_dict()
    course_data["course_difficulty_curve"] = course_data.get("course_difficulty_curve") or curve
    if blueprint:
        blueprint["difficulty_profile"] = blueprint.get("difficulty_profile") or course_data["difficulty_profile"]
        blueprint["difficulty_gap_assessment"] = blueprint.get("difficulty_gap_assessment") or course_data["difficulty_gap_assessment"]
        blueprint["adaptation_decision"] = blueprint.get("adaptation_decision") or course_data["adaptation_decision"]
        blueprint["course_difficulty_curve"] = blueprint.get("course_difficulty_curve") or course_data["course_difficulty_curve"]
    return course_data


def format_difficulty_profile(profile: dict[str, Any]) -> str:
    if not profile:
        return "- 尚未编译难度契约。"
    challenge = profile.get("challenge_profile") or {}
    support = profile.get("support_profile") or {}
    mastery = profile.get("mastery_contract") or {}
    adapter = profile.get("subject_adapter") or {}
    return "\n".join([
        f"- 目标等级：{profile.get('label', '')} ({profile.get('target_level', '')})",
        f"- 学科能力任务：{adapter.get('performance_task', '')}",
        f"- 挑战维度：{_format_dimensions(challenge)}",
        f"- 支持维度：{_format_dimensions(support)}",
        f"- 掌握证据：{'；'.join(mastery.get('required_evidence', []))}",
        f"- 学科边界：{adapter.get('guardrail', '')}",
        f"- 伪难度禁止项：{'；'.join(profile.get('anti_patterns', []))}",
    ])


def format_node_difficulty_contract(contract: dict[str, Any]) -> str:
    if not contract:
        return "- 未找到节点难度契约；应先通过读取适配器恢复契约。"
    mastery = contract.get("mastery") or {}
    support = contract.get("support") or {}
    return "\n".join([
        f"- 目标等级：{contract.get('target_level', '')}",
        f"- 节点角色：{contract.get('node_role', '')}",
        f"- 挑战维度：{_format_dimensions(contract.get('challenge') or {})}",
        f"- 支架要求：{'；'.join(contract.get('support_actions', [])) or _format_dimensions(support)}",
        f"- 学科任务：{contract.get('subject_task', '')}",
        f"- 验收证据：{'；'.join(contract.get('required_evidence', []) or mastery.get('required_evidence', []))}",
        f"- 伪难度禁止项：{'；'.join(contract.get('anti_patterns', []))}",
    ])


def _roles_for_count(count: int, strategy: str) -> list[NodeDifficultyRole]:
    if count <= 0:
        return []
    if count == 1:
        return [NodeDifficultyRole.CAPSTONE]
    if count == 2:
        first = NodeDifficultyRole.BRIDGE if strategy in {"inline_bridge", "diagnostic_required"} else NodeDifficultyRole.FOUNDATION
        return [first, NodeDifficultyRole.CAPSTONE]

    first_role = (
        NodeDifficultyRole.BRIDGE
        if strategy in {"inline_bridge", "prerequisite_unit", "split_foundation_course"}
        else NodeDifficultyRole.CHECKPOINT
        if strategy == "diagnostic_required"
        else NodeDifficultyRole.FOUNDATION
    )
    if count <= 8:
        canonical = [
            first_role,
            NodeDifficultyRole.WORKED_EXAMPLE,
            NodeDifficultyRole.GUIDED_PRACTICE,
            NodeDifficultyRole.INDEPENDENT_TASK,
            NodeDifficultyRole.INTEGRATION,
            NodeDifficultyRole.TRANSFER,
            NodeDifficultyRole.CHECKPOINT,
            NodeDifficultyRole.CAPSTONE,
        ]
        indices = [round(index * (len(canonical) - 1) / (count - 1)) for index in range(count)]
        roles = [canonical[index] for index in indices]
        roles[0] = first_role
        roles[-1] = NodeDifficultyRole.CAPSTONE
        return roles

    cycle = [
        NodeDifficultyRole.FOUNDATION,
        NodeDifficultyRole.WORKED_EXAMPLE,
        NodeDifficultyRole.GUIDED_PRACTICE,
        NodeDifficultyRole.INDEPENDENT_TASK,
        NodeDifficultyRole.CHECKPOINT,
    ]
    prefix = [cycle[index % len(cycle)] for index in range(count - 3)]
    prefix[0] = first_role
    return prefix + [NodeDifficultyRole.INTEGRATION, NodeDifficultyRole.TRANSFER, NodeDifficultyRole.CAPSTONE]


def _support_actions(support: dict[str, Any], role: NodeDifficultyRole) -> list[str]:
    intensity = int(support.get("scaffold_intensity") or 3)
    actions = list(support.get("strategies") or [])
    if intensity >= 4:
        actions.extend(["给出可执行步骤或示范", "在关键转折处提供提示"])
    elif intensity <= 2:
        actions.extend(["不提前给出完整解法", "用标准和边界引导独立决策"])
    if role in {NodeDifficultyRole.CHECKPOINT, NodeDifficultyRole.CAPSTONE}:
        actions.append("给出明确的评价标准与反思问题")
    return _dedupe(actions)[:6]


def _mode_value(value: Any) -> str:
    raw = str(getattr(value, "value", value) or "general").strip()
    return raw if raw in SUBJECT_ADAPTERS else "general"


def _clamp(value: int) -> int:
    return max(1, min(5, int(value)))


def _node_id_from_section(section_number: str, index: int) -> str:
    return f"L2-{section_number.replace('.', '-')}" if section_number else f"L2-{index + 1}"


def _match_contract_by_name(
    node: dict[str, Any],
    by_number: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    name = str(node.get("node_name") or "")
    for number, contract in by_number.items():
        if number and number in name:
            return contract
    return None


def _strip_contract_identity(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if key not in {"node_id", "section_number"}}


def _format_dimensions(values: dict[str, Any]) -> str:
    return "、".join(
        f"{key}={value}"
        for key, value in values.items()
        if isinstance(value, (int, float))
    )


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


__all__ = [
    "DIFFICULTY_CONTRACT_VERSION",
    "DifficultyLevel",
    "DifficultyProfile",
    "DifficultyGapAssessment",
    "AdaptationDecision",
    "ExerciseDifficultyContract",
    "NodeDifficultyContract",
    "CourseDifficultyCurve",
    "parse_difficulty_level",
    "compile_difficulty_profile",
    "assess_readiness",
    "decide_adaptation",
    "compile_course_difficulty_curve",
    "attach_difficulty_contracts_to_plan",
    "ensure_course_difficulty_contracts",
    "format_difficulty_profile",
    "format_node_difficulty_contract",
]
