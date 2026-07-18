"""课程教学画像与模块注册表。

该模块只处理确定性领域规则，不调用大模型。课程主题属于什么院系并不是
这里的判断目标；这里判断的是课程最适合用什么学习行为来组织和验收。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from math import ceil
import re
from typing import Any, Iterable


PROFILE_VERSION = "subject_pedagogy_v1"


class PedagogyMode(str, Enum):
    GENERAL = "general"
    MATH_FORMAL = "math_formal"
    PROGRAMMING_ENGINEERING = "programming_engineering"
    NATURAL_SCIENCE = "natural_science"
    LIFE_MEDICAL = "life_medical"
    HUMANITIES_SOCIAL = "humanities_social"
    LANGUAGE_LEARNING = "language_learning"
    BUSINESS_CAREER = "business_career"


class SecondaryIntensity(str, Enum):
    LIGHT = "light"
    COLLABORATIVE = "collaborative"
    DUAL_CORE = "dual_core"


class ModuleScope(str, Enum):
    COURSE = "course"
    LESSON = "lesson"


class ModuleFrequency(str, Enum):
    COURSE_REQUIRED = "course_required"
    LESSON_REQUIRED = "lesson_required"
    CONDITIONAL = "conditional"


@dataclass(frozen=True)
class TeachingModuleSpec:
    module_id: str
    label: str
    scope: ModuleScope
    frequency: ModuleFrequency
    output_contract: str
    prompt_instruction: str
    signals: tuple[str, ...] = ()

    def to_dict(self, *, source_mode: str, required: bool) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "label": self.label,
            "block_role": module_block_role(self.module_id),
            "scope": self.scope.value,
            "frequency": self.frequency.value,
            "source_mode": source_mode,
            "required": required,
            "output_contract": self.output_contract,
            "prompt_instruction": self.prompt_instruction,
        }


@dataclass(frozen=True)
class PedagogyTemplate:
    mode: PedagogyMode
    label: str
    outcome_signals: tuple[str, ...]
    topic_signals: tuple[str, ...]
    action_signals: tuple[str, ...]
    course_modules: tuple[str, ...]
    lesson_modules: tuple[str, ...]
    conditional_modules: tuple[str, ...]
    quality_guardrails: tuple[str, ...]
    final_assessment: str


@dataclass(frozen=True)
class SubjectPedagogyProfile:
    primary_mode: PedagogyMode
    secondary_mode: PedagogyMode | None
    secondary_intensity: SecondaryIntensity | None
    confidence: str
    evidence: tuple[str, ...]
    rationale: str
    enabled_module_ids: tuple[str, ...]
    user_locked: bool
    profile_version: str = PROFILE_VERSION

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["primary_mode"] = self.primary_mode.value
        data["secondary_mode"] = self.secondary_mode.value if self.secondary_mode else None
        data["secondary_intensity"] = (
            self.secondary_intensity.value if self.secondary_intensity else None
        )
        data["evidence"] = list(self.evidence)
        data["enabled_module_ids"] = list(self.enabled_module_ids)
        return data


def _module(
    module_id: str,
    label: str,
    scope: ModuleScope,
    frequency: ModuleFrequency,
    output_contract: str,
    prompt_instruction: str,
    *signals: str,
) -> TeachingModuleSpec:
    return TeachingModuleSpec(
        module_id=module_id,
        label=label,
        scope=scope,
        frequency=frequency,
        output_contract=output_contract,
        prompt_instruction=prompt_instruction,
        signals=tuple(signals),
    )


MODULES: dict[str, TeachingModuleSpec] = {
    # 通用骨架
    "course_positioning": _module("course_positioning", "课程定位", ModuleScope.COURSE, ModuleFrequency.COURSE_REQUIRED, "说明学习对象、最终成果和边界", "明确这门课面向谁、学完能做什么、哪些内容不在范围内"),
    "learning_path": _module("learning_path", "学习路径", ModuleScope.COURSE, ModuleFrequency.COURSE_REQUIRED, "形成可解释的前置依赖和章节顺序", "章节必须由知识或能力依赖推进，不能只是主题罗列"),
    "integrated_transfer": _module("integrated_transfer", "综合迁移", ModuleScope.COURSE, ModuleFrequency.COURSE_REQUIRED, "安排整合多章能力的最终任务", "课程末尾必须让学习者将多个章节用于一个完整问题"),
    "lesson_goal": _module("lesson_goal", "本节任务", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "给出可观察的本节学习目标", "开头直接说明本节要解决的问题和学会后的可验证行为"),
    "core_explanation": _module("core_explanation", "核心教学", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "讲清当前核心知识或方法", "围绕节点目标解释必要内容，不扩写无关百科背景"),
    "learner_action": _module("learner_action", "学习者行动", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "要求学习者完成主动加工任务", "安排计算、实现、分析、表达或操作，而不是只让学习者阅读"),
    "feedback_check": _module(
        "feedback_check",
        "检查与反馈",
        ModuleScope.LESSON,
        ModuleFrequency.LESSON_REQUIRED,
        "按学习者任务分别提供核对标准、参考结论、推导依据和典型错误",
        "静态课程块不是个性化反馈；每个任务使用三级标题，先说明核对标准，再给参考结论和依据",
    ),

    # 课程编排偏好扩展。它们只负责跨学科的块节奏，不能替代下方学科模块。
    "composition_deep_reasoning": _module(
        "composition_deep_reasoning",
        "深入推演",
        ModuleScope.LESSON,
        ModuleFrequency.CONDITIONAL,
        "把核心结论展开为可检查的因果、推理或推导链",
        "逐步说明关键中间判断及其依据，并指出结论依赖的条件",
    ),
    "composition_case_extension": _module(
        "composition_case_extension",
        "补充案例",
        ModuleScope.LESSON,
        ModuleFrequency.CONDITIONAL,
        "增加一个与本节目标直接对应、可逐步拆解的典型案例",
        "案例必须写清情境、输入、关键判断、过程和结果检查，不得只换名词复述正文",
    ),
    "composition_real_application": _module(
        "composition_real_application",
        "真实场景",
        ModuleScope.LESSON,
        ModuleFrequency.CONDITIONAL,
        "把本节能力用于一个有角色、目标与约束的真实情境",
        "说明情境约束、选择步骤和完成标准；缺少资料依据时使用明确标注的教学情境，不编造行业事实",
    ),
    "composition_project_task": _module(
        "composition_project_task",
        "项目实战",
        ModuleScope.LESSON,
        ModuleFrequency.CONDITIONAL,
        "产出可检查的阶段性项目成果",
        "给出任务背景、输入、交付物、约束、完成条件和自检方式，并与前后课程成果连续",
    ),
    "composition_inquiry": _module(
        "composition_inquiry",
        "问题探究",
        ModuleScope.LESSON,
        ModuleFrequency.CONDITIONAL,
        "围绕一个关键问题提出假设、搜集依据并形成可检验结论",
        "先提出能区分不同解释的问题，再组织假设、依据、推演和检验，不能用连续反问代替教学",
    ),
    "composition_boundary": _module(
        "composition_boundary",
        "边界与反例",
        ModuleScope.LESSON,
        ModuleFrequency.CONDITIONAL,
        "用边界条件或反例检验当前概念、方法或结论",
        "明确哪些条件改变后原结论不再成立，并解释失败原因",
    ),

    # 通用课程
    "general_concept_map": _module("general_concept_map", "概念地图", ModuleScope.COURSE, ModuleFrequency.COURSE_REQUIRED, "连接核心概念和方法", "用清晰关系组织概念，避免百科式堆砌"),
    "general_explained_example": _module("general_explained_example", "解释性例子", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "用具体例子落实抽象说明", "例子必须对应当前概念并解释映射关系"),
    "general_application": _module("general_application", "应用场景", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "说明知识在真实问题中的用法", "给出可执行的应用情境和判断步骤"),
    "general_checklist": _module("general_checklist", "清单或模板", ModuleScope.LESSON, ModuleFrequency.CONDITIONAL, "产出可复用清单或模板", "仅在方法型主题中提供简洁、可直接使用的清单", "步骤", "流程", "方法", "操作"),
    "general_comparison": _module("general_comparison", "案例比较", ModuleScope.LESSON, ModuleFrequency.CONDITIONAL, "比较不同选择的适用条件", "对比至少两种做法及其边界", "比较", "区别", "选择", "方案"),

    # 数学与形式科学
    "math_prerequisite_diagnostic": _module("math_prerequisite_diagnostic", "前置诊断", ModuleScope.COURSE, ModuleFrequency.COURSE_REQUIRED, "列出并检查必要前置知识", "在进入新对象前明确依赖的定义和运算能力"),
    "math_intuition": _module("math_intuition", "直觉入口", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "给出形式化之前的可检验直觉", "用图形、变化或问题建立直觉，但不能替代正式定义"),
    "math_formalization": _module("math_formalization", "正式定义", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "给出符号、对象、条件和边界", "正式写出定义或命题，逐一解释符号和适用条件", "定义", "定理", "公式", "证明"),
    "math_worked_example": _module("math_worked_example", "例题推演", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "展示完整求解或推理过程", "例题必须写出关键步骤、依据和结果检查"),
    "math_variation": _module("math_variation", "变式练习", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "提供需要独立迁移的相邻问题", "改变条件或表示方式，避免照抄例题"),
    "math_error_analysis": _module("math_error_analysis", "错误分析", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "解释常见错误的逻辑原因", "指出错误发生在哪个定义、条件或推理步骤"),
    "math_proof": _module("math_proof", "证明与推导", ModuleScope.LESSON, ModuleFrequency.CONDITIONAL, "给出必要的证明或推导链", "只有节点目标需要时才完整证明，不能每节强制证明", "证明", "推导", "定理", "性质"),
    "math_modeling": _module("math_modeling", "数学建模", ModuleScope.LESSON, ModuleFrequency.CONDITIONAL, "把现实条件转化为形式对象", "说明变量、假设、方程和结果解释", "建模", "应用", "优化", "预测"),

    # 编程与工程技术
    "engineering_artifact_path": _module("engineering_artifact_path", "工程成果路径", ModuleScope.COURSE, ModuleFrequency.COURSE_REQUIRED, "定义最终可运行成果和项目里程碑", "课程顺序围绕逐步构建一个可验收成果组织"),
    "engineering_minimal_run": _module("engineering_minimal_run", "最小可运行示例", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "提供能够直接运行的最小实现", "代码必须完整到可运行，并说明环境或版本前提", "代码", "实现", "运行", "编程"),
    "engineering_output": _module("engineering_output", "运行结果", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "展示或描述正确运行结果", "说明如何运行、预期输出和验收方法"),
    "engineering_mechanism": _module("engineering_mechanism", "机制拆解", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "解释实现为什么工作", "逐段解释关键机制、数据流或控制流"),
    "engineering_modification": _module("engineering_modification", "修改任务", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "要求学习者修改并重新验证实现", "任务必须改变需求或约束，不能只复制代码"),
    "engineering_debugging": _module("engineering_debugging", "调试案例", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "展示错误、定位和修复过程", "给出真实错误现象、原因和验证修复的方法"),
    "engineering_testing": _module("engineering_testing", "测试与质量", ModuleScope.LESSON, ModuleFrequency.CONDITIONAL, "提供自动或手动验证", "对关键行为设计测试和边界条件", "测试", "质量", "边界", "可靠性"),
    "engineering_architecture": _module("engineering_architecture", "架构设计", ModuleScope.LESSON, ModuleFrequency.CONDITIONAL, "解释组件职责和取舍", "只有系统级主题才引入架构，不强制画图", "架构", "系统", "模块", "服务"),

    # 自然科学
    "science_phenomenon_path": _module("science_phenomenon_path", "现象到模型路径", ModuleScope.COURSE, ModuleFrequency.COURSE_REQUIRED, "按现象、模型、证据和应用组织课程", "课程必须从可观察问题进入模型，再回到预测或解释"),
    "science_phenomenon": _module("science_phenomenon", "现象与问题", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "提出可观察现象和待解释问题", "区分观察事实与需要解释的问题"),
    "science_model": _module("science_model", "模型与规律", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "说明对象、变量、假设和规律", "明确模型假设、规律和适用范围"),
    "science_evidence": _module("science_evidence", "实验与证据", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "给出支持结论的实验、数据或观察", "把证据、解释和结论分开写清"),
    "science_boundary": _module("science_boundary", "适用边界", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "说明模型何时成立或失效", "列出关键边界条件和常见误用"),
    "science_prediction": _module("science_prediction", "预测与应用", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "使用模型进行解释或预测", "给出从条件到结论的完整应用"),
    "science_experiment_design": _module("science_experiment_design", "实验设计", ModuleScope.LESSON, ModuleFrequency.CONDITIONAL, "设计变量、对照和观察指标", "说明可操作的实验步骤和安全边界", "实验", "测量", "验证", "观察"),
    "science_data_analysis": _module("science_data_analysis", "数据分析", ModuleScope.LESSON, ModuleFrequency.CONDITIONAL, "分析数据与不确定性", "说明数据如何支持或限制结论", "数据", "统计", "误差", "曲线"),

    # 生命科学与医学基础
    "life_system_levels": _module("life_system_levels", "生命层级", ModuleScope.COURSE, ModuleFrequency.COURSE_REQUIRED, "建立结构层级与系统关系", "从分子、细胞、组织或系统中选择适当层级推进"),
    "life_location_structure": _module("life_location_structure", "定位与结构", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "说明对象位于哪里、由什么组成", "先定位结构层级，再描述关键组成"),
    "life_function": _module("life_function", "功能", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "说明结构承担的功能", "把功能与具体结构联系起来"),
    "life_mechanism": _module("life_mechanism", "机制过程", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "解释过程怎样发生", "按因果顺序解释机制，不把相关性写成因果"),
    "life_regulation": _module("life_regulation", "调节与系统关系", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "连接调节因素和其他系统", "说明反馈、稳态或系统相互作用"),
    "life_case": _module("life_case", "机制案例", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "用案例检验结构功能机制", "案例用于解释知识，不给个人诊断或治疗建议"),
    "life_normal_abnormal": _module("life_normal_abnormal", "正常与异常", ModuleScope.LESSON, ModuleFrequency.CONDITIONAL, "比较正常机制和异常变化", "只解释学习范围内的机制和风险边界", "疾病", "异常", "病理", "风险"),
    "life_evidence": _module("life_evidence", "实验依据", ModuleScope.LESSON, ModuleFrequency.CONDITIONAL, "说明机制的实验或观察依据", "区分已知事实、常见模型和不确定性", "实验", "研究", "证据", "数据"),

    # 人文社科
    "humanities_question_path": _module("humanities_question_path", "问题与观点路径", ModuleScope.COURSE, ModuleFrequency.COURSE_REQUIRED, "围绕核心问题组织背景、理论和争议", "课程不能退化为人物或年代流水账"),
    "humanities_context": _module("humanities_context", "背景与语境", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "提供理解材料所需的历史或社会语境", "只保留与核心问题直接相关的背景"),
    "humanities_source": _module("humanities_source", "材料与证据", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "使用文本、事件、案例或数据支撑分析", "明确事实材料与解释之间的关系"),
    "humanities_claim": _module("humanities_claim", "观点与论证", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "呈现观点、理由和证据链", "不能只给结论，必须说明论证如何成立"),
    "humanities_comparison": _module("humanities_comparison", "观点比较", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "比较不同解释的前提和边界", "避免把争议写成唯一事实，也避免无原则各打五十大板"),
    "humanities_response": _module("humanities_response", "讨论或写作", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "要求学习者形成可辩护回应", "提供问题、证据要求和评价标准"),
    "humanities_source_criticism": _module("humanities_source_criticism", "材料辨析", ModuleScope.LESSON, ModuleFrequency.CONDITIONAL, "分析材料来源、立场和限制", "在涉及原始材料或争议证据时启用", "史料", "文本", "来源", "材料"),
    "humanities_timeline": _module("humanities_timeline", "时间线", ModuleScope.LESSON, ModuleFrequency.CONDITIONAL, "梳理关键变化而非罗列年代", "只保留解释思想或制度变化所需节点", "历史", "演变", "时期", "发展"),

    # 语言学习
    "language_scenario_path": _module("language_scenario_path", "交际场景路径", ModuleScope.COURSE, ModuleFrequency.COURSE_REQUIRED, "按可完成的沟通场景组织课程", "每章服务一个逐步升级的真实沟通目标"),
    "language_input": _module("language_input", "可理解输入", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "提供符合当前水平的对话、文本或听力稿", "输入必须包含本节目标表达并控制生词负担"),
    "language_chunks": _module("language_chunks", "词汇与语块", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "提取可直接使用的表达", "优先教授语块、搭配和使用条件，而非孤立词表"),
    "language_form_use": _module("language_form_use", "形式、意义与使用", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "解释句型或语法如何表达意义", "把形式、意义和语用场景连接起来"),
    "language_controlled_practice": _module("language_controlled_practice", "控制练习", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "让学习者准确模仿和替换", "从低自由度练习开始，并提供答案或反馈"),
    "language_output": _module("language_output", "真实输出", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "要求学习者说、写、读或听后回应", "输出任务必须对应本节场景并可评价"),
    "language_review": _module("language_review", "间隔复习", ModuleScope.COURSE, ModuleFrequency.COURSE_REQUIRED, "安排旧语块在后续场景复现", "新课必须复用先前表达，形成间隔和交错练习"),
    "language_pronunciation": _module("language_pronunciation", "发音与文字系统", ModuleScope.LESSON, ModuleFrequency.CONDITIONAL, "提供发音、重音或文字规则练习", "只在目标语言和节点需要时启用", "发音", "音标", "拼写", "字母"),
    "language_pragmatics": _module("language_pragmatics", "文化与语用", ModuleScope.LESSON, ModuleFrequency.CONDITIONAL, "说明礼貌、语域和文化使用边界", "避免把文化倾向写成绝对规则", "礼貌", "文化", "正式", "语境"),

    # 商业与职业技能
    "business_deliverable_path": _module("business_deliverable_path", "工作成果路径", ModuleScope.COURSE, ModuleFrequency.COURSE_REQUIRED, "围绕真实工作成果组织课程", "最终必须产出方案、分析、文档、决策或可演示成果"),
    "business_scenario": _module("business_scenario", "业务场景", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "给出角色、目标和约束", "使用具体工作场景，不能只讲管理口号"),
    "business_framework": _module("business_framework", "方法框架", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "提供可解释的判断框架", "说明框架解决什么问题、何时不适用"),
    "business_case": _module("business_case", "案例拆解", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "展示从信息到决策的过程", "案例必须包含约束、取舍和结果"),
    "business_tool": _module("business_tool", "工具与模板", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "提供可复用模板、清单或步骤", "工具必须可以直接用于本节实战任务"),
    "business_task": _module("business_task", "实战任务", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "要求产出工作成果", "明确输入、交付物和完成条件"),
    "business_metric": _module("business_metric", "评价指标", ModuleScope.LESSON, ModuleFrequency.LESSON_REQUIRED, "用指标或评分标准检查成果", "指标必须能区分不同质量的交付物"),
    "business_roleplay": _module("business_roleplay", "角色模拟", ModuleScope.LESSON, ModuleFrequency.CONDITIONAL, "模拟沟通、谈判或决策", "给出双方目标、信息差和复盘问题", "谈判", "沟通", "汇报", "面试"),
    "business_data": _module("business_data", "数据分析", ModuleScope.LESSON, ModuleFrequency.CONDITIONAL, "使用数据支持判断", "明确指标定义、计算和决策含义", "数据", "指标", "财务", "分析"),
}


# 教学模块和课程块共享这一套语义角色。生成器、Markdown 拆块器和前端标签
# 都必须消费这里的结果，不能再按“第几个块”猜测角色。
MODULE_BLOCK_ROLES: dict[str, str] = {
    "course_positioning": "orientation",
    "learning_path": "orientation",
    "integrated_transfer": "transfer",
    "lesson_goal": "objective",
    "core_explanation": "concept",
    "learner_action": "activity",
    "feedback_check": "feedback",
    "composition_deep_reasoning": "reasoning",
    "composition_case_extension": "example",
    "composition_real_application": "application",
    "composition_project_task": "activity",
    "composition_inquiry": "reasoning",
    "composition_boundary": "counterexample",
    "general_concept_map": "concept",
    "general_explained_example": "example",
    "general_application": "application",
    "general_checklist": "application",
    "general_comparison": "counterexample",
    "math_prerequisite_diagnostic": "prerequisite",
    "math_intuition": "orientation",
    "math_formalization": "concept",
    "math_worked_example": "example",
    "math_variation": "activity",
    "math_error_analysis": "misconception",
    "math_proof": "reasoning",
    "math_modeling": "application",
    "engineering_artifact_path": "orientation",
    "engineering_minimal_run": "example",
    "engineering_output": "feedback",
    "engineering_mechanism": "reasoning",
    "engineering_modification": "activity",
    "engineering_debugging": "misconception",
    "engineering_testing": "feedback",
    "engineering_architecture": "concept",
    "science_phenomenon_path": "orientation",
    "science_phenomenon": "orientation",
    "science_model": "concept",
    "science_evidence": "reasoning",
    "science_boundary": "concept",
    "science_prediction": "application",
    "science_experiment_design": "activity",
    "science_data_analysis": "reasoning",
    "life_system_levels": "concept",
    "life_location_structure": "concept",
    "life_function": "concept",
    "life_mechanism": "reasoning",
    "life_regulation": "reasoning",
    "life_case": "example",
    "life_normal_abnormal": "counterexample",
    "life_evidence": "reasoning",
    "humanities_question_path": "orientation",
    "humanities_context": "orientation",
    "humanities_source": "example",
    "humanities_claim": "reasoning",
    "humanities_comparison": "counterexample",
    "humanities_response": "activity",
    "humanities_source_criticism": "activity",
    "humanities_timeline": "orientation",
    "language_scenario_path": "orientation",
    "language_input": "example",
    "language_chunks": "concept",
    "language_form_use": "concept",
    "language_controlled_practice": "activity",
    "language_output": "activity",
    "language_review": "remediation",
    "language_pronunciation": "concept",
    "language_pragmatics": "application",
    "business_deliverable_path": "orientation",
    "business_scenario": "orientation",
    "business_framework": "concept",
    "business_case": "example",
    "business_tool": "application",
    "business_task": "activity",
    "business_metric": "feedback",
    "business_roleplay": "activity",
    "business_data": "reasoning",
}


def module_block_role(module_id: str) -> str:
    return MODULE_BLOCK_ROLES.get(str(module_id or ""), "concept")


def module_role_from_heading(title: str) -> str | None:
    """Resolve a generated heading only when it matches a registered module label."""
    normalized = re.sub(r"\s+", "", str(title or "")).strip("：:、。 ").lower()
    if not normalized:
        return None
    matches: list[tuple[int, str]] = []
    for module_id, module in MODULES.items():
        label = re.sub(r"\s+", "", module.label).strip("：:、。 ").lower()
        if normalized == label or normalized.startswith(f"{label}：") or normalized.startswith(f"{label}:"):
            matches.append((len(label), module_block_role(module_id)))
    return max(matches, default=(0, ""))[1] or None


COMMON_COURSE_MODULES = ("course_positioning", "learning_path", "integrated_transfer")
COMMON_LESSON_MODULES = ("lesson_goal", "core_explanation", "learner_action", "feedback_check")


TEMPLATES: dict[PedagogyMode, PedagogyTemplate] = {
    PedagogyMode.GENERAL: PedagogyTemplate(
        PedagogyMode.GENERAL, "通用课程",
        ("理解并应用", "快速入门", "建立系统认识"),
        ("入门", "导论", "基础知识", "概览"),
        ("理解", "认识", "掌握", "应用"),
        ("general_concept_map",),
        ("general_explained_example", "general_application"),
        ("general_checklist", "general_comparison"),
        ("不能退化成百科介绍", "必须让学习者能够解释并实际使用"),
        "解释核心概念并完成一个真实应用任务",
    ),
    PedagogyMode.MATH_FORMAL: PedagogyTemplate(
        PedagogyMode.MATH_FORMAL, "数学与形式科学",
        ("计算", "证明", "推导", "形式化建模", "求解"),
        ("数学", "微积分", "代数", "几何", "概率", "统计", "逻辑", "离散"),
        ("计算", "证明", "推导", "求解", "建模", "公式"),
        ("math_prerequisite_diagnostic",),
        ("math_intuition", "math_formalization", "math_worked_example", "math_variation", "math_error_analysis"),
        ("math_proof", "math_modeling"),
        ("定义、推导和例题必须逻辑一致", "直觉不能替代正式定义"),
        "独立求解、证明或形式化建模",
    ),
    PedagogyMode.PROGRAMMING_ENGINEERING: PedagogyTemplate(
        PedagogyMode.PROGRAMMING_ENGINEERING, "编程与工程技术",
        ("构建可运行项目", "实现系统", "调试程序", "完成工程成果"),
        ("编程", "软件", "算法", "数据库", "网络", "机器学习", "人工智能", "python", "java", "javascript", "react", "vue"),
        ("实现", "编写", "运行", "调试", "部署", "构建", "代码"),
        ("engineering_artifact_path",),
        ("engineering_minimal_run", "engineering_output", "engineering_mechanism", "engineering_modification", "engineering_debugging"),
        ("engineering_testing", "engineering_architecture"),
        ("代码必须形成可运行闭环", "不能只贴代码或只讲概念"),
        "交付一个可运行、可测试、可解释的工程成果",
    ),
    PedagogyMode.NATURAL_SCIENCE: PedagogyTemplate(
        PedagogyMode.NATURAL_SCIENCE, "自然科学",
        ("解释自然现象", "设计实验", "建立模型", "预测结果"),
        ("物理", "化学", "天文", "地质", "气象", "环境科学", "力学", "电磁", "量子"),
        ("观察", "实验", "测量", "解释", "预测", "验证"),
        ("science_phenomenon_path",),
        ("science_phenomenon", "science_model", "science_evidence", "science_boundary", "science_prediction"),
        ("science_experiment_design", "science_data_analysis"),
        ("现象、模型、证据和结论必须分开", "必须说明规律适用边界"),
        "使用模型和证据解释或预测一个自然现象",
    ),
    PedagogyMode.LIFE_MEDICAL: PedagogyTemplate(
        PedagogyMode.LIFE_MEDICAL, "生命科学与医学基础",
        ("解释生命机制", "说明结构功能", "分析生理过程"),
        ("生物", "医学", "生理", "解剖", "细胞", "遗传", "免疫", "神经", "生态"),
        ("解释机制", "分析结构", "比较正常异常", "说明功能"),
        ("life_system_levels",),
        ("life_location_structure", "life_function", "life_mechanism", "life_regulation", "life_case"),
        ("life_normal_abnormal", "life_evidence"),
        ("结构、功能和机制不能混写", "不得给出个人诊断或治疗建议"),
        "用结构、功能和机制解释一个生命过程或基础医学案例",
    ),
    PedagogyMode.HUMANITIES_SOCIAL: PedagogyTemplate(
        PedagogyMode.HUMANITIES_SOCIAL, "人文社科",
        ("分析材料", "比较观点", "形成论证", "解释社会现象"),
        ("哲学", "历史", "文学", "社会学", "心理学", "经济学", "政治", "教育", "传播", "文化"),
        ("分析", "论证", "比较", "讨论", "批判", "写作", "解释"),
        ("humanities_question_path",),
        ("humanities_context", "humanities_source", "humanities_claim", "humanities_comparison", "humanities_response"),
        ("humanities_source_criticism", "humanities_timeline"),
        ("事实、材料、观点和解释必须分开", "不能把争议解释写成唯一事实"),
        "基于材料形成一份有证据、能回应异议的分析或论证",
    ),
    PedagogyMode.LANGUAGE_LEARNING: PedagogyTemplate(
        PedagogyMode.LANGUAGE_LEARNING, "语言学习",
        ("完成真实沟通", "提高听说读写", "使用目标语言表达"),
        ("英语", "日语", "法语", "德语", "西班牙语", "韩语", "俄语", "汉语", "语言学习", "语法", "词汇", "口语", "听力"),
        ("听", "说", "读", "写", "翻译", "会话", "表达", "沟通"),
        ("language_scenario_path", "language_review"),
        ("language_input", "language_chunks", "language_form_use", "language_controlled_practice", "language_output"),
        ("language_pronunciation", "language_pragmatics"),
        ("每章必须有真实输出", "不能长期停留在单词和语法讲解"),
        "在目标场景中完成可理解、得体的真实表达",
    ),
    PedagogyMode.BUSINESS_CAREER: PedagogyTemplate(
        PedagogyMode.BUSINESS_CAREER, "商业与职业技能",
        ("做出业务决策", "完成工作交付", "解决职业场景问题"),
        ("商业", "管理", "市场", "营销", "销售", "产品", "运营", "项目管理", "职业", "面试", "谈判", "财务"),
        ("决策", "交付", "规划", "汇报", "谈判", "分析", "制定方案", "管理"),
        ("business_deliverable_path",),
        ("business_scenario", "business_framework", "business_case", "business_tool", "business_task", "business_metric"),
        ("business_roleplay", "business_data"),
        ("必须产出可使用的工作成果", "不能只讲框架和口号"),
        "交付一个可评价的业务方案、分析、沟通或决策成果",
    ),
}


LEGACY_MODE_ALIASES = {
    "engineering": PedagogyMode.PROGRAMMING_ENGINEERING,
    "humanities": PedagogyMode.HUMANITIES_SOCIAL,
    "social_science": PedagogyMode.HUMANITIES_SOCIAL,
    "applied_skill": PedagogyMode.GENERAL,
    "skill_based": PedagogyMode.GENERAL,
    "communication": PedagogyMode.BUSINESS_CAREER,
}


def parse_mode(value: Any, *, allow_auto: bool = False) -> PedagogyMode | None:
    raw = str(getattr(value, "value", value) or "").strip()
    if not raw or (allow_auto and raw == "auto"):
        return None
    try:
        return PedagogyMode(raw)
    except ValueError:
        return LEGACY_MODE_ALIASES.get(raw)


def _joined_material_text(materials: Iterable[Any]) -> str:
    parts: list[str] = []
    for raw in materials:
        data = raw.model_dump() if hasattr(raw, "model_dump") else dict(raw)
        parts.extend([
            str(data.get("filename") or ""),
            str(data.get("user_description") or ""),
            str(data.get("content") or "")[:3000],
        ])
    return " ".join(parts).lower()


def _signal_score(text: str, signals: Iterable[str], weight: float) -> tuple[float, list[str]]:
    matched = []
    score = 0.0
    for signal in signals:
        if signal.lower() in text:
            matched.append(signal)
            score += weight
    return score, matched


def resolve_pedagogy_profile(
    *,
    subject: str,
    requirements: str = "",
    materials: Iterable[Any] = (),
    requested_mode: Any = "auto",
    requested_secondary_mode: Any = None,
    requested_intensity: Any = None,
) -> SubjectPedagogyProfile:
    """根据学习成果和行为信号构造可解释教学画像。"""
    explicit_primary = parse_mode(requested_mode, allow_auto=True)
    explicit_secondary = parse_mode(requested_secondary_mode, allow_auto=True)
    text = " ".join([subject, requirements, _joined_material_text(materials)]).lower()
    scores: dict[PedagogyMode, float] = {}
    evidence_by_mode: dict[PedagogyMode, list[str]] = {}

    for mode, template in TEMPLATES.items():
        outcome_score, outcomes = _signal_score(text, template.outcome_signals, 4.0)
        action_score, actions = _signal_score(text, template.action_signals, 3.0)
        topic_score, topics = _signal_score(text, template.topic_signals, 2.0)
        scores[mode] = outcome_score + action_score + topic_score
        evidence_by_mode[mode] = _dedupe(outcomes + actions + topics)

    ranked = sorted(scores, key=lambda mode: scores[mode], reverse=True)
    user_locked = explicit_primary is not None
    primary = explicit_primary or ranked[0]
    top_score = scores.get(primary, 0.0)

    if not explicit_primary and top_score < 2.0:
        primary = PedagogyMode.GENERAL
        confidence = "low"
    else:
        second_score = max((scores[m] for m in ranked if m != primary), default=0.0)
        gap = top_score - second_score
        confidence = "high" if top_score >= 7.0 and gap >= 3.0 else "medium"
        if top_score < 4.0:
            confidence = "low"

    secondary: PedagogyMode | None = None
    if explicit_secondary and explicit_secondary != primary:
        secondary = explicit_secondary
    elif not user_locked:
        candidate = next((mode for mode in ranked if mode != primary), None)
        if candidate and scores[candidate] >= max(3.0, scores.get(primary, 0.0) * 0.45):
            secondary = candidate

    intensity: SecondaryIntensity | None = None
    if secondary:
        requested_intensity_raw = str(getattr(requested_intensity, "value", requested_intensity) or "")
        try:
            intensity = SecondaryIntensity(requested_intensity_raw)
        except ValueError:
            ratio = scores.get(secondary, 0.0) / max(scores.get(primary, 1.0), 1.0)
            if ratio >= 0.75:
                intensity = SecondaryIntensity.DUAL_CORE
            elif ratio >= 0.45:
                intensity = SecondaryIntensity.COLLABORATIVE
            else:
                intensity = SecondaryIntensity.LIGHT

    evidence = list(evidence_by_mode.get(primary, []))
    if secondary:
        evidence.extend(evidence_by_mode.get(secondary, []))
    if user_locked:
        evidence.insert(0, "用户明确指定主模式")
    evidence = _dedupe(evidence)[:12]
    if not evidence:
        evidence = ["未发现稳定学科行为信号，使用通用课程兜底"]

    primary_label = TEMPLATES[primary].label
    if secondary:
        rationale = f"以{primary_label}组织课程主线，并按依赖注入{TEMPLATES[secondary].label}模块。"
    else:
        rationale = f"课程的主要学习行为最符合{primary_label}。"

    module_ids = list(COMMON_COURSE_MODULES + COMMON_LESSON_MODULES)
    module_ids.extend(TEMPLATES[primary].course_modules)
    module_ids.extend(TEMPLATES[primary].lesson_modules)
    module_ids.extend(TEMPLATES[primary].conditional_modules)
    if secondary:
        module_ids.extend(TEMPLATES[secondary].course_modules)
        module_ids.extend(TEMPLATES[secondary].lesson_modules)
        module_ids.extend(TEMPLATES[secondary].conditional_modules)

    return SubjectPedagogyProfile(
        primary_mode=primary,
        secondary_mode=secondary,
        secondary_intensity=intensity,
        confidence="high" if user_locked else confidence,
        evidence=tuple(evidence),
        rationale=rationale,
        enabled_module_ids=tuple(_dedupe(module_ids)),
        user_locked=user_locked,
    )


def coerce_persisted_profile(course_data: dict[str, Any]) -> SubjectPedagogyProfile:
    raw = course_data.get("subject_pedagogy_profile") or course_data.get("pedagogy_profile") or {}
    if raw:
        primary = parse_mode(raw.get("primary_mode")) or PedagogyMode.GENERAL
        secondary = parse_mode(raw.get("secondary_mode"))
        if secondary == primary:
            secondary = None
        intensity_raw = str(raw.get("secondary_intensity") or "")
        try:
            intensity = SecondaryIntensity(intensity_raw) if secondary else None
        except ValueError:
            intensity = SecondaryIntensity.LIGHT if secondary else None
        normalized = resolve_pedagogy_profile(
            subject=str(course_data.get("course_name") or ""),
            requirements=str(course_data.get("requirements") or ""),
            requested_mode=primary.value,
            requested_secondary_mode=secondary.value if secondary else None,
            requested_intensity=intensity.value if intensity else None,
        )
        raw_modules = tuple(
            str(module_id) for module_id in raw.get("enabled_module_ids", [])
            if str(module_id) in MODULES
        )
        raw_evidence = tuple(
            str(item).strip() for item in raw.get("evidence", [])
            if str(item).strip()
        )
        return SubjectPedagogyProfile(
            primary_mode=normalized.primary_mode,
            secondary_mode=normalized.secondary_mode,
            secondary_intensity=normalized.secondary_intensity,
            confidence=str(raw.get("confidence") or normalized.confidence),
            evidence=raw_evidence or normalized.evidence,
            rationale=str(raw.get("rationale") or normalized.rationale),
            enabled_module_ids=raw_modules or normalized.enabled_module_ids,
            user_locked=bool(raw.get("user_locked", normalized.user_locked)),
            profile_version=str(raw.get("profile_version") or PROFILE_VERSION),
        )

    legacy = str(course_data.get("discipline") or "")
    subject = str(course_data.get("course_name") or "")
    if legacy == "natural_science":
        lowered = subject.lower()
        if any(word in lowered for word in TEMPLATES[PedagogyMode.MATH_FORMAL].topic_signals):
            legacy_mode = PedagogyMode.MATH_FORMAL
        elif any(word in lowered for word in TEMPLATES[PedagogyMode.LIFE_MEDICAL].topic_signals):
            legacy_mode = PedagogyMode.LIFE_MEDICAL
        else:
            legacy_mode = PedagogyMode.NATURAL_SCIENCE
    elif legacy == "communication" and any(
        word in subject.lower() for word in TEMPLATES[PedagogyMode.LANGUAGE_LEARNING].topic_signals
    ):
        legacy_mode = PedagogyMode.LANGUAGE_LEARNING
    else:
        legacy_mode = parse_mode(legacy) or None

    return resolve_pedagogy_profile(
        subject=subject,
        requirements=str(course_data.get("requirements") or ""),
        requested_mode=legacy_mode.value if legacy_mode else "auto",
    )


def build_course_module_plan(profile: SubjectPedagogyProfile) -> list[dict[str, Any]]:
    module_ids = list(COMMON_COURSE_MODULES)
    module_ids.extend(TEMPLATES[profile.primary_mode].course_modules)
    if profile.secondary_mode and profile.secondary_intensity == SecondaryIntensity.DUAL_CORE:
        module_ids.extend(TEMPLATES[profile.secondary_mode].course_modules)
    result = []
    for module_id in _dedupe(module_ids):
        source = _module_source(module_id, profile)
        result.append(MODULES[module_id].to_dict(source_mode=source, required=True))
    return result


def attach_module_plans_to_plan(
    plan: dict[str, Any], profile: SubjectPedagogyProfile
) -> dict[str, Any]:
    sections = [
        section
        for chapter in plan.get("chapters", [])
        for section in chapter.get("sections", [])
    ]
    secondary_indices = _secondary_injection_indices(sections, profile)

    for index, section in enumerate(sections):
        requested = [
            module_id for module_id in section.get("suggested_module_ids", [])
            if module_id in profile.enabled_module_ids
        ]
        module_ids = list(COMMON_LESSON_MODULES)
        primary_template = TEMPLATES[profile.primary_mode]
        module_ids.extend(primary_template.lesson_modules)
        module_ids.extend(_matching_conditional_modules(section, primary_template))
        module_ids.extend(requested)

        if profile.secondary_mode and index in secondary_indices:
            secondary_template = TEMPLATES[profile.secondary_mode]
            secondary_limit = 2 if profile.secondary_intensity == SecondaryIntensity.DUAL_CORE else 1
            secondary_candidates = list(_matching_conditional_modules(section, secondary_template))
            secondary_candidates.extend(secondary_template.lesson_modules)
            module_ids.extend(_dedupe(secondary_candidates)[:secondary_limit])

        section["module_plan"] = [
            MODULES[module_id].to_dict(
                source_mode=_module_source(module_id, profile),
                required=MODULES[module_id].frequency != ModuleFrequency.CONDITIONAL,
            )
            for module_id in _dedupe(module_ids)
        ]
        section.pop("suggested_module_ids", None)

    plan["subject_pedagogy_profile"] = profile.to_dict()
    plan["course_module_plan"] = build_course_module_plan(profile)
    return plan


def validate_module_registry() -> list[str]:
    issues: list[str] = []
    missing_roles = sorted(set(MODULES) - set(MODULE_BLOCK_ROLES))
    unknown_modules = sorted(set(MODULE_BLOCK_ROLES) - set(MODULES))
    if missing_roles:
        issues.append(f"教学模块缺少课程块角色: {', '.join(missing_roles)}")
    if unknown_modules:
        issues.append(f"课程块角色引用了不存在的教学模块: {', '.join(unknown_modules)}")
    for mode, template in TEMPLATES.items():
        referenced = template.course_modules + template.lesson_modules + template.conditional_modules
        missing = [module_id for module_id in referenced if module_id not in MODULES]
        if missing:
            issues.append(f"{mode.value} 引用了不存在的模块: {', '.join(missing)}")
        if not template.lesson_modules:
            issues.append(f"{mode.value} 缺少课时模块")
    return issues


def _secondary_injection_indices(
    sections: list[dict[str, Any]], profile: SubjectPedagogyProfile
) -> set[int]:
    if not profile.secondary_mode or not sections:
        return set()
    template = TEMPLATES[profile.secondary_mode]
    scored: list[tuple[float, int]] = []
    signals = template.topic_signals + template.action_signals
    for index, section in enumerate(sections):
        text = " ".join([
            str(section.get("title") or ""),
            " ".join(str(item) for item in section.get("key_points", [])),
            str(section.get("learning_objective") or ""),
        ]).lower()
        score = sum(1 for signal in signals if signal.lower() in text)
        scored.append((float(score), index))

    intensity = profile.secondary_intensity or SecondaryIntensity.LIGHT
    ratio = {
        SecondaryIntensity.LIGHT: 0.15,
        SecondaryIntensity.COLLABORATIVE: 0.35,
        SecondaryIntensity.DUAL_CORE: 0.6,
    }[intensity]
    count = max(1, ceil(len(sections) * ratio))
    ranked = sorted(scored, key=lambda item: (item[0], -item[1]), reverse=True)
    return {index for _score, index in ranked[:count]}


def _matching_conditional_modules(
    section: dict[str, Any], template: PedagogyTemplate
) -> list[str]:
    text = " ".join([
        str(section.get("title") or ""),
        " ".join(str(item) for item in section.get("key_points", [])),
        str(section.get("learning_objective") or ""),
    ]).lower()
    result = []
    for module_id in template.conditional_modules:
        spec = MODULES[module_id]
        if any(signal.lower() in text for signal in spec.signals):
            result.append(module_id)
    return result


def _module_source(module_id: str, profile: SubjectPedagogyProfile) -> str:
    if module_id in COMMON_COURSE_MODULES or module_id in COMMON_LESSON_MODULES:
        return "common"
    primary = TEMPLATES[profile.primary_mode]
    if module_id in primary.course_modules + primary.lesson_modules + primary.conditional_modules:
        return profile.primary_mode.value
    return profile.secondary_mode.value if profile.secondary_mode else profile.primary_mode.value


def _dedupe(items: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    return result


__all__ = [
    "PROFILE_VERSION",
    "PedagogyMode",
    "SecondaryIntensity",
    "TeachingModuleSpec",
    "PedagogyTemplate",
    "SubjectPedagogyProfile",
    "MODULES",
    "MODULE_BLOCK_ROLES",
    "TEMPLATES",
    "COMMON_COURSE_MODULES",
    "COMMON_LESSON_MODULES",
    "parse_mode",
    "resolve_pedagogy_profile",
    "coerce_persisted_profile",
    "build_course_module_plan",
    "attach_module_plans_to_plan",
    "module_block_role",
    "module_role_from_heading",
    "validate_module_registry",
]
