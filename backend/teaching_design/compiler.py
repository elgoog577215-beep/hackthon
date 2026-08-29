"""灵知统一教学语义与两级编排规则。

课程级先确定学习目的、学科类型和课程教学类型；讲次级再结合本讲目标、
课堂条件与学习证据确定本讲课型并编排教学块。教学理论只进入版本化合同，
不继续形成教师要理解的平行分类，也不留给 Prompt 临时发明。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .standards import (
    SUBJECT_STANDARD_PACK_VERSION,
    resolve_subject_standard_pack,
)

SCHEMA_VERSION = "teaching_semantics_v3"

TEACHING_DEFINITION: dict[str, Any] = {
    "definition": (
        "教学是教师在真实条件下，围绕可观察成果，组织学习者经历理解、行动、"
        "反馈与迁移，并依据学习证据持续调整支持，使学习者从当前起点走向独立完成。"
    ),
    "product_meaning": "灵知编排的不是一组内容，而是一条可实施、可观察、可调整的学习发生路径。",
    "teacher_role": "教师是课程共同设计者、课堂决策者和适应性专家，拥有最终判断与正式确认权。",
    "learner_role": "学习者通过解释、求解、操作、讨论、创作和反思形成可观察表现，并逐步获得自主性。",
    "ai_role": "AI把教师意图和教学标准编译为候选结构与内容，解释依据并接受教师修改，不替代教师作正式判断。",
}

UNIVERSAL_TEACHING_PRINCIPLES: tuple[dict[str, str], ...] = (
    {"id": "alignment", "label": "目标—证据—活动对齐", "meaning": "先确定学习者最终要做出什么表现和怎样判定，再安排活动、讲解与表达。"},
    {"id": "disciplinary_authenticity", "label": "学科方法成立", "meaning": "解释、证据、专业行动和评价方式遵守当前学科的知识生产方式。"},
    {"id": "cognitive_engagement", "label": "可观察的认知投入", "meaning": "课堂让学习者产生选择、解释、推导、作品或协作判断，而不是只保持表面忙碌。"},
    {"id": "evidence_adaptation", "label": "证据驱动调整", "meaning": "检查不是教学结尾，而是决定继续、补支架、重教、变式或提高挑战的控制信号。"},
    {"id": "scaffold_to_agency", "label": "支架走向自主", "meaning": "支持随学习表现逐步撤除，最终要求学习者独立选择、执行、自检和迁移。"},
    {"id": "inclusive_access", "label": "多路径进入、同标准达成", "meaning": "通过多种表征、参与和表达方式减少无关障碍，同时保持核心目标与评价标准。"},
    {"id": "teacher_agency", "label": "教师最终控制", "meaning": "AI建议必须可解释、可修改、可拒绝、可撤销，教师决定真实课堂怎样实施。"},
)

LEARNING_PURPOSES: dict[str, dict[str, Any]] = {
    "systematic": {
        "label": "系统学习",
        "result": "形成完整、可迁移的知识与能力结构",
        "organizing_question": "学习者最终要建立怎样的知识结构，并能在什么新情境中使用？",
        "learning_arc": ["定位全貌", "建立先修", "形成关系", "综合应用", "延迟迁移"],
        "evidence_strategy": "用阶段整合、跨章任务和延迟复验共同证明结构已经形成。",
    },
    "project": {
        "label": "项目实战",
        "result": "完成可展示、可评价的真实成果",
        "organizing_question": "学习者要交付什么成果，并用什么标准证明它真实可用？",
        "learning_arc": ["明确成果", "诊断缺口", "分段制作", "评审修订", "交付复盘"],
        "evidence_strategy": "用里程碑产物、关键决策、测试结果和最终交付共同证明能力。",
    },
    "exam": {
        "label": "期末冲刺",
        "result": "在限定时间内补齐重点并通过测评验证",
        "organizing_question": "距离目标还差什么，有限时间应优先修复哪些可诊断差距？",
        "learning_arc": ["范围诊断", "确定优先级", "专项补救", "限时模拟", "策略巩固"],
        "evidence_strategy": "用前测、专项复测、限时模拟和错误复盘校正准备度判断。",
    },
}

SUBJECT_TYPES: dict[str, str] = {
    "auto": "自动判断",
    "general": "通用课程",
    "math_formal": "数学与形式科学",
    "programming_engineering": "编程与工程技术",
    "natural_science": "自然科学",
    "life_medical": "生命科学与医学基础",
    "humanities_social": "人文社科",
    "language_learning": "语言学习",
    "business_career": "商业与职业技能",
}

SUBJECT_TYPE_CONTRACTS: dict[str, dict[str, Any]] = {
    "auto": {
        "epistemic_question": "当前内容主要通过什么方式建立可信知识与专业判断？",
        "professional_moves": ["识别核心对象", "识别证据方式", "识别最终专业表现"],
        "evidence": "输出学科推荐、依据和仍需教师确认的歧义。",
        "guardrails": ["自动判断不是正式学科类型", "歧义必须允许教师修正"],
    },
    "general": {
        "epistemic_question": "概念或方法怎样被清楚解释并用于真实任务？",
        "professional_moves": ["建立概念边界", "示范方法", "案例应用", "综合迁移"],
        "evidence": "能解释核心概念，并把方法用于条件变化后的任务。",
        "guardrails": ["不能退化成百科介绍", "活动必须产生可检查结果"],
    },
    "math_formal": {
        "epistemic_question": "定义、条件、推理和形式结果怎样严格成立？",
        "professional_moves": ["多重表征", "正式定义", "完整推理", "变式求解", "错误诊断"],
        "evidence": "能独立求解、证明或建立并检验形式模型。",
        "guardrails": ["直觉不能替代定义", "推导、例题和答案必须逻辑一致"],
    },
    "programming_engineering": {
        "epistemic_question": "实现怎样运行、怎样验证，并为何采用当前工程取舍？",
        "professional_moves": ["最小运行", "机制解释", "增量实现", "调试测试", "工程取舍"],
        "evidence": "形成可运行、可测试、可解释取舍的工程交付物。",
        "guardrails": ["不能只贴代码或只讲概念", "环境、版本与验收条件必须明确"],
    },
    "natural_science": {
        "epistemic_question": "现象、模型、实验或数据怎样共同支持一个有边界的解释？",
        "professional_moves": ["观察现象", "提出假设", "建立模型", "实验或数据检验", "解释边界"],
        "evidence": "能用模型和证据解释、预测或设计可执行调查。",
        "guardrails": ["观察与解释分开", "说明不确定性、替代解释和适用范围"],
    },
    "life_medical": {
        "epistemic_question": "结构、功能、机制、尺度和证据怎样连接成生命过程解释？",
        "professional_moves": ["定位尺度", "结构功能", "机制链", "系统调节", "案例与数据推理"],
        "evidence": "能解释生命过程或基础医学案例，并说明证据强度。",
        "guardrails": ["结构、功能和机制不能混写", "不得给个人诊断或治疗建议"],
    },
    "humanities_social": {
        "epistemic_question": "材料、语境、概念、因果和观点怎样支持可辩护的解释？",
        "professional_moves": ["界定问题", "辨析材料", "比较解释", "形成论证", "回应异议"],
        "evidence": "形成有材料依据、能回应异议并承认边界的分析或论证。",
        "guardrails": ["事实、材料、观点和解释分开", "争议不能写成唯一事实"],
    },
    "language_learning": {
        "epistemic_question": "学习者怎样在具体对象、目的和语境中完成真实沟通？",
        "professional_moves": ["可理解输入", "注意形式", "受控练习", "真实输出", "反馈后再次表现"],
        "evidence": "能在目标情境中完成可理解、准确、得体的表达或互动。",
        "guardrails": ["不能长期停留在词汇语法讲解", "必须出现真实输出和再次表现"],
    },
    "business_career": {
        "epistemic_question": "在角色、目标、约束和相关方中怎样作出可执行判断？",
        "professional_moves": ["场景诊断", "工具分析", "方案决策", "成果交付", "指标复盘"],
        "evidence": "形成可评价的方案、分析、沟通、决策或工作成果。",
        "guardrails": ["不能先套框架再找问题", "完成活动不等于成果合格"],
    },
}

COURSE_TEACHING_TYPES: dict[str, dict[str, Any]] = {
    "theory": {
        "label": "理论课",
        "organizing_principle": "以概念、原理、模型和推理为主线，持续用解释与迁移证明理解。",
        "teacher_role": "把复杂关系讲清、示范思考并用问题暴露理解差距。",
        "learner_role": "解释关系、完成推理、比较边界并迁移到新情境。",
        "evidence_pattern": ["解释", "推理过程", "变式应用", "延迟提取"],
        "lesson_type_mix": {"theory": 55, "theory_practice": 30, "review_assessment": 15},
        "default_arc": ["theory", "theory_practice", "review_assessment"],
        "required_block_roles": ["concept", "reasoning", "example", "checkpoint"],
    },
    "laboratory": {
        "label": "实验课",
        "organizing_principle": "以问题、实验、观察、数据和受证据约束的结论为主线。",
        "teacher_role": "守住安全和变量控制，追问证据质量并帮助学生解释异常。",
        "learner_role": "设计或执行实验、记录数据、分析误差并修正结论。",
        "evidence_pattern": ["实验记录", "数据分析", "误差说明", "证据结论"],
        "lesson_type_mix": {"theory": 15, "experiment_inquiry": 65, "review_assessment": 20},
        "default_arc": ["theory", "experiment_inquiry", "review_assessment"],
        "required_block_roles": ["orientation", "activity", "reasoning", "feedback"],
    },
    "practice": {
        "label": "实践课",
        "organizing_principle": "以示范、带支架练习、即时反馈和独立完成为主线。",
        "teacher_role": "示范关键判断，观察过程并给出可执行的就近反馈。",
        "learner_role": "实际操作、解释选择、根据反馈修正并独立复现。",
        "evidence_pattern": ["操作过程", "工作结果", "修订记录", "独立表现"],
        "lesson_type_mix": {"theory_practice": 25, "practice": 60, "review_assessment": 15},
        "default_arc": ["theory_practice", "practice", "review_assessment"],
        "required_block_roles": ["example", "application", "activity", "feedback"],
    },
    "seminar": {
        "label": "研讨课",
        "organizing_principle": "以问题、材料、观点比较和有依据的判断为主线。",
        "teacher_role": "提供共同问题和材料标准，推动论证、异议与观点修订。",
        "learner_role": "辨析材料、提出主张、回应异议并修正判断。",
        "evidence_pattern": ["材料引用", "论证链", "异议回应", "判断修订"],
        "lesson_type_mix": {"theory": 15, "case_discussion": 70, "review_assessment": 15},
        "default_arc": ["theory", "case_discussion", "review_assessment"],
        "required_block_roles": ["orientation", "example", "reasoning", "counterexample", "feedback"],
    },
    "project": {
        "label": "项目课",
        "organizing_principle": "以真实成果、里程碑、制作、评审和迭代为主线。",
        "teacher_role": "确认成果标准，诊断当前瓶颈并组织评审与下一轮迭代。",
        "learner_role": "分解任务、制作成果、说明决策、接受评审并迭代。",
        "evidence_pattern": ["里程碑产物", "决策依据", "测试结果", "迭代记录"],
        "lesson_type_mix": {"theory_practice": 20, "project_workshop": 65, "review_assessment": 15},
        "default_arc": ["theory_practice", "project_workshop", "review_assessment"],
        "required_block_roles": ["orientation", "application", "activity", "feedback", "transfer"],
    },
    "comprehensive": {
        "label": "综合课",
        "organizing_principle": "围绕同一目标组合讲解、行动、证据和迁移，按内容选择最小充分课型。",
        "teacher_role": "根据内容和学习证据切换讲解、示范、讨论、探究与反馈。",
        "learner_role": "在理解、行动、表达与反思之间形成连贯表现。",
        "evidence_pattern": ["过程检查", "任务表现", "综合成果", "迁移复验"],
        "lesson_type_mix": {
            "theory": 20, "theory_practice": 25, "practice": 15,
            "case_discussion": 10, "experiment_inquiry": 10,
            "project_workshop": 10, "review_assessment": 10,
        },
        "default_arc": ["theory", "theory_practice", "practice", "review_assessment"],
        "required_block_roles": ["orientation", "concept", "application", "activity", "feedback"],
    },
}

LESSON_TYPE_CONTRACTS: dict[str, dict[str, Any]] = {
    "theory": {
        "label": "理论讲授", "purpose": "建立概念、原理、关系与适用边界，并现场取得理解证据。",
        "learning_cycle": ["唤起经验或问题", "形成解释", "例证或推理", "学习者解释", "检查与迁移"],
        "learner_performance": "用自己的话解释为什么成立、何时适用，并处理一个相邻情境。",
        "evidence": "解释、推理步骤、例反例判断或短迁移任务。",
        "feedback_decisions": ["澄清概念边界", "补充表征或例子", "进入变式迁移"],
        "minimum_engagement": "constructive",
    },
    "theory_practice": {
        "label": "讲练结合", "purpose": "把原理讲解、示范、练习和反馈组织成一条连续学习弧。",
        "learning_cycle": ["提出任务", "解释原理", "示范思路", "学习者练习", "反馈后变式"],
        "learner_performance": "完成任务并解释采用当前方法的理由、条件和边界。",
        "evidence": "练习过程、结果、自我解释和反馈后的再次表现。",
        "feedback_decisions": ["补关键提示", "回看示范步骤", "撤除支架进入变式"],
        "minimum_engagement": "constructive",
    },
    "practice": {
        "label": "实践操作", "purpose": "通过示范、操作、反馈和独立复现形成可执行能力。",
        "learning_cycle": ["明确任务标准", "关键示范", "带支架操作", "就近反馈", "独立复现"],
        "learner_performance": "按标准独立完成操作、表达或工作任务并进行自检。",
        "evidence": "操作轨迹、作品、结果核对和独立复现。",
        "feedback_decisions": ["纠正关键步骤", "降低一次任务复杂度", "提高独立程度"],
        "minimum_engagement": "active",
    },
    "case_discussion": {
        "label": "案例研讨", "purpose": "围绕具体材料比较证据、观点和取舍，形成可辩护判断。",
        "learning_cycle": ["进入案例", "独立取证", "形成初判", "互动质疑", "修订与迁移"],
        "learner_performance": "用共同标准和具体材料作出判断、回应异议并修正观点。",
        "evidence": "材料标注、论证、异议回应和判断修订。",
        "feedback_decisions": ["补充关键材料", "追问证据与前提", "引入反例或新约束"],
        "minimum_engagement": "interactive",
    },
    "experiment_inquiry": {
        "label": "实验探究", "purpose": "通过问题、假设、实验或数据形成受证据约束的结论。",
        "learning_cycle": ["提出可检验问题", "形成假设", "设计并实施", "分析证据", "修正结论"],
        "learner_performance": "区分观察与解释，用数据支持、限制或反驳一个结论。",
        "evidence": "方案、观察记录、数据分析、误差与结论。",
        "feedback_decisions": ["修正变量控制", "补充数据或对照", "降低结论强度"],
        "minimum_engagement": "constructive",
    },
    "project_workshop": {
        "label": "项目工作坊", "purpose": "围绕阶段成果组织制作、协作、评审与迭代。",
        "learning_cycle": ["确认里程碑", "计划分工", "制作测试", "展示评审", "迭代提交"],
        "learner_performance": "交付阶段成果，说明关键决策，并依据评审完成修订。",
        "evidence": "阶段产物、决策记录、测试结果、评审与迭代差异。",
        "feedback_decisions": ["聚焦当前瓶颈", "补充专业支架", "调整分工或迭代目标"],
        "minimum_engagement": "interactive",
    },
    "review_assessment": {
        "label": "复习测评", "purpose": "通过提取、诊断、补救和再次表现巩固长期掌握。",
        "learning_cycle": ["无提示提取", "暴露差距", "针对补救", "变式复测", "策略复盘"],
        "learner_performance": "在减少提示、改变情境或延迟后再次完成目标任务。",
        "evidence": "提取结果、错误类型、补救后的变式表现和复习策略。",
        "feedback_decisions": ["回到前置知识", "针对错误补救", "进入延迟或综合复验"],
        "minimum_engagement": "active",
    },
}

LESSON_TYPE_LABELS = {key: value["label"] for key, value in LESSON_TYPE_CONTRACTS.items()}

CLASSROOM_CONSTRAINT_CONTRACT: dict[str, dict[str, str]] = {
    "lesson_duration_minutes": {"question": "本讲有多少可用时间？", "effect": "控制目标容量、块数与每块时长。"},
    "class_size": {"question": "有多少学习者？", "effect": "控制讨论、展示、巡视与反馈方式。"},
    "delivery_mode": {"question": "线上、线下还是混合？", "effect": "控制互动渠道、材料呈现和现场证据采集。"},
    "grouping": {"question": "个人、同伴还是小组完成？", "effect": "控制参与结构、责任分配与成果归属。"},
    "equipment": {"question": "有哪些设备、工具、网络和材料？", "effect": "决定活动可实施性与替代方案。"},
    "safety_and_access": {"question": "有哪些安全、无障碍和个体支持要求？", "effect": "决定硬性护栏、进入路径与表达选择。"},
    "assessment_pressure": {"question": "有哪些考试、提交和制度时限？", "effect": "控制优先级、练习密度与复验节奏。"},
}

BLOCK_ROLE_CONTRACTS: dict[str, dict[str, Any]] = {
    "orientation": {"engagement": "active", "teacher_move": "建立问题、价值与任务边界", "learner_move": "调取经验并作出初始判断", "evidence": "初始回答或经验表征"},
    "objective": {"engagement": "active", "teacher_move": "说明目标、成果与评价标准", "learner_move": "复述目标并识别完成条件", "evidence": "目标理解或成功标准复述"},
    "prerequisite": {"engagement": "active", "teacher_move": "提取并诊断必要前置", "learner_move": "无提示回忆或完成前置任务", "evidence": "前置提取结果"},
    "concept": {"engagement": "constructive", "teacher_move": "用定义、表征、例反例建立边界", "learner_move": "解释、转换表征并自行举例", "evidence": "解释、表征转换或例反例"},
    "reasoning": {"engagement": "constructive", "teacher_move": "显化推理链与关键条件", "learner_move": "补全、解释或比较推理", "evidence": "可检查的推理过程"},
    "example": {"engagement": "constructive", "teacher_move": "示范选择、过程与自检", "learner_move": "预测步骤并解释关键选择", "evidence": "预测、解释或完整示例分析"},
    "counterexample": {"engagement": "constructive", "teacher_move": "用反例暴露边界和误区", "learner_move": "判断失效条件并修正认识", "evidence": "边界判断或错误诊断"},
    "application": {"engagement": "constructive", "teacher_move": "设置条件变化的应用任务", "learner_move": "选择并使用所学方法", "evidence": "应用结果与选法解释"},
    "activity": {"engagement": "active", "teacher_move": "组织真实任务并观察过程", "learner_move": "操作、讨论、制作或协作解决", "evidence": "过程记录、作品或协作结论"},
    "checkpoint": {"engagement": "active", "teacher_move": "用最短任务取得目标证据", "learner_move": "独立作答、演示或解释", "evidence": "就近达成证据"},
    "feedback": {"engagement": "constructive", "teacher_move": "依据表现指出差距和下一步", "learner_move": "解释错误、修正并再次表现", "evidence": "修订差异与再次表现"},
    "misconception": {"engagement": "constructive", "teacher_move": "呈现可信错误并追问根因", "learner_move": "定位、解释和修复错误", "evidence": "错误诊断与修正"},
    "remediation": {"engagement": "active", "teacher_move": "缩小任务、补前置或增加支架", "learner_move": "在支架下重新完成关键步骤", "evidence": "补救后的关键表现"},
    "summary": {"engagement": "constructive", "teacher_move": "组织关系和使用条件", "learner_move": "自行归纳并连接前后内容", "evidence": "结构化总结或关系图"},
    "transfer": {"engagement": "constructive", "teacher_move": "改变条件、情境或独立程度", "learner_move": "选择、迁移并自检", "evidence": "新情境中的独立表现"},
}

_LEGACY_COURSE_TYPE_TO_PURPOSE = {"systematic": "systematic", "project": "project", "inquiry": "systematic", "exam": "exam"}
_LEGACY_COMPOSITION_TO_TEACHING_TYPE = {
    "theory_driven": "theory", "project_driven": "project", "inquiry_driven": "seminar",
    "example_driven": "comprehensive", "case_driven": "seminar",
    "practice_driven": "practice", "balanced": "comprehensive",
}
_DEFAULT_TEACHING_TYPE_BY_PURPOSE = {"systematic": "comprehensive", "project": "project", "exam": "comprehensive"}

_BLOCK_ROLE_ORDER: dict[str, tuple[str, ...]] = {
    "theory": ("orientation", "objective", "prerequisite", "concept", "reasoning", "counterexample", "example", "application", "checkpoint", "feedback", "transfer", "remediation"),
    "theory_practice": ("orientation", "objective", "concept", "example", "application", "activity", "checkpoint", "feedback", "reasoning", "transfer", "remediation"),
    "practice": ("orientation", "objective", "example", "application", "activity", "checkpoint", "feedback", "transfer", "remediation"),
    "case_discussion": ("orientation", "objective", "example", "reasoning", "counterexample", "activity", "checkpoint", "feedback", "transfer"),
    "experiment_inquiry": ("orientation", "objective", "concept", "activity", "reasoning", "counterexample", "checkpoint", "feedback", "transfer"),
    "project_workshop": ("orientation", "objective", "application", "activity", "checkpoint", "feedback", "reasoning", "transfer"),
    "review_assessment": ("orientation", "objective", "checkpoint", "feedback", "remediation", "application", "transfer", "concept"),
}


def _value(raw: Any) -> str:
    return str(getattr(raw, "value", raw) or "").strip().lower()


def resolve_learning_purpose(raw: Any = None, *, legacy_course_type: Any = None) -> str:
    explicit = _value(raw)
    if explicit in LEARNING_PURPOSES:
        return explicit
    return _LEGACY_COURSE_TYPE_TO_PURPOSE.get(_value(legacy_course_type), "systematic")


def resolve_course_teaching_type(
    raw: Any = None,
    *,
    learning_purpose: Any = None,
    legacy_course_type: Any = None,
    composition_style: Any = None,
) -> tuple[str, str]:
    explicit = _value(raw)
    if explicit in COURSE_TEACHING_TYPES:
        return explicit, "course_teaching_type"
    if _value(legacy_course_type) == "inquiry":
        return "seminar", "legacy_course_type"
    legacy_style = _value(composition_style)
    if legacy_style in _LEGACY_COMPOSITION_TO_TEACHING_TYPE:
        return _LEGACY_COMPOSITION_TO_TEACHING_TYPE[legacy_style], "composition_style"
    purpose = resolve_learning_purpose(learning_purpose, legacy_course_type=legacy_course_type)
    return _DEFAULT_TEACHING_TYPE_BY_PURPOSE[purpose], "learning_purpose_default"


def compile_course_semantics(
    *,
    learning_purpose: Any = None,
    legacy_course_type: Any = None,
    subject_type: Any = None,
    course_teaching_type: Any = None,
    composition_style: Any = None,
    discipline_hint: str = "",
    discipline_profile: str = "",
) -> dict[str, Any]:
    purpose = resolve_learning_purpose(learning_purpose, legacy_course_type=legacy_course_type)
    teaching_type, resolved_from = resolve_course_teaching_type(
        course_teaching_type,
        learning_purpose=purpose,
        legacy_course_type=legacy_course_type,
        composition_style=composition_style,
    )
    subject = _value(subject_type) or "auto"
    if subject not in SUBJECT_TYPES:
        subject = "auto"
    purpose_contract = deepcopy(LEARNING_PURPOSES[purpose])
    subject_contract = deepcopy(SUBJECT_TYPE_CONTRACTS[subject])
    subject_standard_pack = resolve_subject_standard_pack(
        subject,
        discipline_hint=discipline_hint,
        discipline_profile=discipline_profile,
    )
    if subject == "auto":
        subject = str(subject_standard_pack.get("subject_type") or "general")
        subject_contract = deepcopy(SUBJECT_TYPE_CONTRACTS[subject])
    teaching_contract = deepcopy(COURSE_TEACHING_TYPES[teaching_type])
    strategies = ["problem_inquiry"] if _value(legacy_course_type) == "inquiry" else []
    return {
        "teaching_semantics_version": SCHEMA_VERSION,
        "teaching_definition": deepcopy(TEACHING_DEFINITION),
        "universal_teaching_principles": deepcopy(list(UNIVERSAL_TEACHING_PRINCIPLES)),
        "learning_purpose": purpose,
        "learning_purpose_label": purpose_contract["label"],
        "learning_purpose_result": purpose_contract["result"],
        "learning_purpose_contract": purpose_contract,
        "subject_type": subject,
        "subject_type_label": SUBJECT_TYPES[subject],
        "subject_type_contract": subject_contract,
        "subject_standard_pack_version": SUBJECT_STANDARD_PACK_VERSION,
        "subject_standard_pack": subject_standard_pack,
        "course_teaching_type": teaching_type,
        "course_teaching_type_label": teaching_contract["label"],
        "course_teaching_type_resolved_from": resolved_from,
        "course_teaching_type_contract": teaching_contract,
        "course_lesson_type_distribution": deepcopy(teaching_contract["lesson_type_mix"]),
        "classroom_constraint_contract": deepcopy(CLASSROOM_CONSTRAINT_CONTRACT),
        "internal_teaching_strategies": strategies,
    }


def lesson_phase(index: int, total: int) -> str:
    if total <= 1:
        return "single"
    ratio = max(0, index) / max(1, total - 1)
    if ratio <= 0.2:
        return "opening"
    if ratio >= 0.8:
        return "closing"
    return "development"


def recommend_lesson_type(course_teaching_type: Any, *, phase: str, legacy_candidate: str = "theory") -> str:
    teaching_type, _ = resolve_course_teaching_type(course_teaching_type)
    candidate = legacy_candidate if legacy_candidate in LESSON_TYPE_LABELS else "theory"
    # 课程收束会提高复习测评的优先级，但不能只因“最后一讲”就覆盖本讲真实目标。
    if phase == "closing" and candidate == "review_assessment":
        return "review_assessment"
    if teaching_type == "comprehensive":
        return candidate
    if teaching_type == "theory":
        return candidate if candidate in {"theory", "theory_practice", "review_assessment"} else "theory_practice"
    if teaching_type == "laboratory":
        return "theory" if phase == "opening" else "experiment_inquiry"
    if teaching_type == "practice":
        return "theory_practice" if phase == "opening" else "practice"
    if teaching_type == "seminar":
        return "theory" if phase == "opening" else "case_discussion"
    if teaching_type == "project":
        return "theory_practice" if phase == "opening" else "project_workshop"
    return candidate


def compile_lesson_semantics(
    *,
    learning_purpose: Any = None,
    subject_type: Any = None,
    course_teaching_type: Any = None,
    lesson_type: Any = None,
    phase: str = "development",
    lesson_goal: str = "",
    classroom_constraints: dict[str, Any] | None = None,
    legacy_candidate: str = "theory",
    discipline_hint: str = "",
    discipline_profile: str = "",
) -> dict[str, Any]:
    course_semantics = compile_course_semantics(
        learning_purpose=learning_purpose,
        subject_type=subject_type,
        course_teaching_type=course_teaching_type,
        discipline_hint=discipline_hint,
        discipline_profile=discipline_profile,
    )
    explicit_lesson_type = _value(lesson_type)
    resolved_lesson_type = (
        explicit_lesson_type
        if explicit_lesson_type in LESSON_TYPE_CONTRACTS
        else recommend_lesson_type(
            course_semantics["course_teaching_type"], phase=phase, legacy_candidate=legacy_candidate
        )
    )
    lesson_contract = deepcopy(LESSON_TYPE_CONTRACTS[resolved_lesson_type])
    phase_reason = {
        "opening": "当前位于课程开端，优先建立共同基础和任务入口",
        "development": "当前位于课程发展阶段，优先形成主导学习表现",
        "closing": "当前位于课程收束阶段，需要整合与复验，但仍服从本讲真实目标",
        "single": "单讲课程需要在一讲内完成目标、练习和结果检查",
    }.get(phase, "依据当前讲目标安排必要的学习活动和结果检查")
    reason = (
        f"{course_semantics['course_teaching_type_label']}以“"
        f"{course_semantics['course_teaching_type_contract']['organizing_principle']}”组织整课；"
        f"{phase_reason}，因此本讲采用{lesson_contract['label']}。"
    )
    if lesson_goal.strip():
        reason += f" 本讲围绕“{lesson_goal.strip()}”取得可观察证据。"
    constraints = {
        key: deepcopy(value)
        for key, value in (classroom_constraints or {}).items()
        if key in CLASSROOM_CONSTRAINT_CONTRACT and value not in (None, "", [], {})
    }
    return {
        "teaching_semantics_version": SCHEMA_VERSION,
        "lesson_type": resolved_lesson_type,
        "lesson_type_label": lesson_contract["label"],
        "lesson_type_resolved_from": "lesson_type" if explicit_lesson_type in LESSON_TYPE_CONTRACTS else "course_semantics",
        "lesson_type_recommendation_reason": reason,
        "lesson_type_contract": lesson_contract,
        "required_learning_cycle": deepcopy(lesson_contract["learning_cycle"]),
        "required_block_roles": list(_BLOCK_ROLE_ORDER[resolved_lesson_type]),
        "classroom_constraints": constraints,
        "classroom_constraint_contract": deepcopy(CLASSROOM_CONSTRAINT_CONTRACT),
        "teaching_block_contract_fields": [
            "purpose", "planned_minutes", "teacher_activity", "student_activity",
            "expected_output", "check_method", "feedback_strategy", "adaptation_options",
            "engagement_mode", "access_support", "grouping", "transition",
        ],
        "quality_rules": [
            "每个关键目标都有学习者可观察行动和就近证据",
            "每次检查都明确达到、部分达到和未达到时怎样处理",
            "支架服务当前障碍并可逐步撤除，不降低核心成果标准",
            "课堂时长、班额、环境、设备和安全要求与活动相容",
            *course_semantics["subject_standard_pack"].get("quality_rules", []),
        ],
        "course_semantics": course_semantics,
    }


def compile_teaching_block_contract(
    block: dict[str, Any],
    *,
    lesson_type: str,
    subject_standard_pack: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """把旧模块投影为可实施、可检查、可调整的教学块合同。"""
    result = deepcopy(block)
    role = _value(result.get("role")) or "concept"
    role_contract = deepcopy(BLOCK_ROLE_CONTRACTS.get(role, BLOCK_ROLE_CONTRACTS["concept"]))
    discipline_recipe = deepcopy(
        ((subject_standard_pack or {}).get("block_recipes") or {}).get(role) or {}
    )
    lesson_contract = LESSON_TYPE_CONTRACTS.get(lesson_type, LESSON_TYPE_CONTRACTS["theory"])
    subject_evidence = [
        str(item).strip()
        for item in (subject_standard_pack or {}).get("evidence_patterns") or []
        if str(item).strip()
    ]
    subject_misconceptions = [
        str(item).strip()
        for item in (subject_standard_pack or {}).get("common_misconceptions") or []
        if str(item).strip()
    ]
    subject_actions = [
        str(item).strip()
        for item in (subject_standard_pack or {}).get("professional_actions") or []
        if str(item).strip()
    ]
    subject_safety = [
        str(item).strip()
        for item in (subject_standard_pack or {}).get("safety_boundaries") or []
        if str(item).strip()
    ]
    evidence_focus = subject_evidence[0] if subject_evidence else result.get("expected_output") or role_contract["evidence"]
    misconception_focus = subject_misconceptions[0] if subject_misconceptions else "把活动完成当成目标达成"
    prerequisite_focus = subject_actions[0] if subject_actions else "识别核心对象"
    transfer_focus = subject_actions[-1] if subject_actions else "解释迁移"
    engagement = (
        _value(result.get("engagement_mode"))
        or _value(discipline_recipe.get("engagement_mode"))
        or role_contract["engagement"]
    )
    if role == "activity" and not _value(result.get("engagement_mode")):
        if lesson_type in {"case_discussion", "project_workshop"}:
            engagement = "interactive"
        elif lesson_type == "experiment_inquiry":
            engagement = "constructive"
    result["engagement_mode"] = engagement
    result["teacher_activity"] = str(
        result.get("teacher_activity")
        or discipline_recipe.get("teacher_activity")
        or role_contract["teacher_move"]
    ).strip()
    result["student_activity"] = str(
        result.get("student_activity")
        or discipline_recipe.get("student_activity")
        or role_contract["learner_move"]
    ).strip()
    result["expected_output"] = str(
        result.get("expected_output")
        or discipline_recipe.get("expected_output")
        or role_contract["evidence"]
    ).strip()
    result["check_method"] = str(
        result.get("check_method")
        or discipline_recipe.get("check_method")
        or f"核对“{result['expected_output']}”，重点检查{evidence_focus}是否真实出现"
    ).strip()
    result["feedback_strategy"] = str(
        result.get("feedback_strategy")
        or discipline_recipe.get("feedback_strategy")
        or f"先判断是否出现“{misconception_focus}”，再指出当前表现与成功标准的具体差距，并安排修正后的再次表现"
    ).strip()
    result["adaptation_options"] = deepcopy(
        result.get("adaptation_options")
        or discipline_recipe.get("adaptation_options")
        or [
            f"达到标准：撤除当前支架，增加要求学习者独立完成“{transfer_focus}”的迁移挑战",
            f"部分达到：保留原目标，针对“{misconception_focus}”补充提示、表征或范例后再次检查",
            f"未达到：缩小任务，回到“{prerequisite_focus}”所需前置并重新取得同类证据",
        ]
    )
    result["access_support"] = str(
        result.get("access_support")
        or discipline_recipe.get("access_support")
        or "提供适合当前学科的文字、图示、口头或操作入口；核心成果标准保持一致"
    ).strip()
    result["grouping"] = str(
        result.get("grouping")
        or discipline_recipe.get("grouping")
        or "根据班额与任务采用个人、同伴或小组"
    ).strip()
    result["transition"] = str(
        result.get("transition")
        or discipline_recipe.get("transition")
        or f"用本块证据衔接{lesson_contract['learning_cycle'][-1]}或下一教学责任"
    ).strip()
    if subject_safety:
        result["safety_boundary"] = str(
            result.get("safety_boundary")
            or discipline_recipe.get("safety_boundary")
            or subject_safety[0]
        ).strip()
    result["block_contract_version"] = SCHEMA_VERSION
    if subject_standard_pack:
        result["subject_standard_pack_version"] = str(
            subject_standard_pack.get("schema_version")
            or SUBJECT_STANDARD_PACK_VERSION
        )
        result["discipline_profile_id"] = str(
            subject_standard_pack.get("discipline_profile_id") or ""
        )
    return result


def order_teaching_blocks(blocks: list[dict[str, Any]], lesson_type: str) -> list[dict[str, Any]]:
    """在每个小节内部按本讲课型排序，保持小节次序与块身份不变。"""
    order = _BLOCK_ROLE_ORDER.get(lesson_type, _BLOCK_ROLE_ORDER["theory"])
    priority = {role: index for index, role in enumerate(order)}
    section_order: dict[str, int] = {}
    for block in blocks:
        section_id = _value(block.get("section_node_id"))
        section_order.setdefault(section_id, len(section_order))
    indexed = list(enumerate(blocks))
    indexed.sort(key=lambda pair: (
        section_order.get(_value(pair[1].get("section_node_id")), len(section_order)),
        priority.get(_value(pair[1].get("role")), len(priority)), pair[0],
    ))
    return [deepcopy(block) for _, block in indexed]


__all__ = [
    "BLOCK_ROLE_CONTRACTS", "CLASSROOM_CONSTRAINT_CONTRACT", "COURSE_TEACHING_TYPES",
    "LEARNING_PURPOSES", "LESSON_TYPE_CONTRACTS", "LESSON_TYPE_LABELS", "SCHEMA_VERSION",
    "SUBJECT_TYPES", "SUBJECT_TYPE_CONTRACTS", "TEACHING_DEFINITION",
    "UNIVERSAL_TEACHING_PRINCIPLES", "compile_course_semantics", "compile_lesson_semantics",
    "compile_teaching_block_contract", "lesson_phase", "order_teaching_blocks",
    "recommend_lesson_type", "resolve_course_teaching_type", "resolve_learning_purpose",
    "resolve_subject_standard_pack",
]
