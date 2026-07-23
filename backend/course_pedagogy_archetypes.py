"""学科课型与必要分型。

一级学科模式回答“这门课主要用什么学习行为组织”，课型回答“当前小节具体怎样教”。
所有选择都由确定性规则完成，不增加模型调用，也不改变目录和知识身份。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class LessonArchetypeSpec:
    archetype_id: str
    mode: str
    label: str
    purpose: str
    module_ids: tuple[str, ...]
    signals: tuple[str, ...]
    preferred_stages: tuple[str, ...]
    evidence_contract: str
    guardrails: tuple[str, ...]

    def to_dict(self, *, stage: str) -> dict[str, Any]:
        data = asdict(self)
        data["module_ids"] = list(self.module_ids)
        data["signals"] = list(self.signals)
        data["preferred_stages"] = list(self.preferred_stages)
        data["guardrails"] = list(self.guardrails)
        data["course_stage"] = stage
        return data


@dataclass(frozen=True)
class SubjectVariantSpec:
    variant_id: str
    mode: str
    label: str
    signals: tuple[str, ...]
    preferred_archetype_ids: tuple[str, ...]


def _archetype(
    archetype_id: str,
    mode: str,
    label: str,
    purpose: str,
    modules: tuple[str, ...],
    signals: tuple[str, ...],
    stages: tuple[str, ...],
    evidence: str,
    *guardrails: str,
) -> LessonArchetypeSpec:
    return LessonArchetypeSpec(
        archetype_id=archetype_id,
        mode=mode,
        label=label,
        purpose=purpose,
        module_ids=modules,
        signals=signals,
        preferred_stages=stages,
        evidence_contract=evidence,
        guardrails=guardrails,
    )


LESSON_ARCHETYPES: dict[str, LessonArchetypeSpec] = {
    # 通用课程：从概念建构逐渐进入方法、判断、应用和综合迁移。
    "general_concept_building": _archetype(
        "general_concept_building", "general", "概念建构",
        "建立核心概念、关系和边界，而不是罗列背景知识。",
        ("general_concept_model", "general_explained_example"),
        ("概念", "原理", "认识", "理解", "基础", "入门"),
        ("opening", "foundation"),
        "学习者能够用自己的话解释概念，并用一个例子与反例划清边界。",
        "概念必须围绕当前问题组织", "例子不能代替概念边界",
    ),
    "general_method_workshop": _archetype(
        "general_method_workshop", "general", "方法工作坊",
        "把一个方法拆成可执行步骤，并让学习者独立完成相邻任务。",
        ("general_explained_example", "general_checklist", "general_procedure"),
        ("方法", "步骤", "流程", "操作", "技巧", "实践"),
        ("foundation", "development"),
        "学习者能够脱离示范，按条件选择并执行方法。",
        "清单必须服务判断而不是替代判断", "步骤必须包含结果检查",
    ),
    "general_comparison_decision": _archetype(
        "general_comparison_decision", "general", "比较与判断",
        "比较多个对象或方案的条件、证据和取舍。",
        ("general_comparison", "general_application"),
        ("比较", "区别", "选择", "判断", "方案", "优缺点"),
        ("development", "integration"),
        "学习者能够依据明确标准作出选择并解释理由。",
        "不得无原则地各打五十大板", "结论必须回到使用条件",
    ),
    "general_case_application": _archetype(
        "general_case_application", "general", "案例应用",
        "把概念或方法用于一个有约束的具体案例。",
        ("general_application", "general_explained_example"),
        ("案例", "场景", "应用", "解决", "实战", "情境"),
        ("development", "integration"),
        "学习者能够完成案例判断，并说明概念与案例事实的映射。",
        "案例不能只是故事", "缺少依据时必须标明为教学情境",
    ),
    "general_transfer_synthesis": _archetype(
        "general_transfer_synthesis", "general", "综合迁移",
        "整合前序概念和方法，解决条件发生变化的新问题。",
        ("general_transfer", "general_application", "general_comparison"),
        ("综合", "迁移", "总结", "设计", "解决问题", "成果"),
        ("integration", "culmination"),
        "学习者能够独立完成综合成果并解释选择、边界和自检结果。",
        "不得把章节摘要冒充迁移", "必须改变情境或约束",
    ),

    # 数学与形式科学：强调表征、推理、问题解决和建模之间的往返。
    "math_intuition_representation": _archetype(
        "math_intuition_representation", "math_formal", "直觉与多重表征",
        "从问题或表征建立直觉，再连接正式定义、符号和条件。",
        ("math_intuition", "math_representation", "math_formalization"),
        ("直觉", "图像", "表示", "定义", "概念", "认识"),
        ("opening", "foundation"),
        "学习者能够在文字、图形、符号或数值表征之间转换并说明不变量。",
        "直觉不能替代定义", "每种表征必须指向同一数学对象",
    ),
    "math_worked_strategy": _archetype(
        "math_worked_strategy", "math_formal", "解题策略",
        "用完整例题呈现策略选择、关键推理和结果检查。",
        ("math_worked_example", "math_problem_strategy", "math_variation"),
        ("计算", "求解", "例题", "算法", "方法", "应用"),
        ("foundation", "development"),
        "学习者能够独立求解条件变化后的相邻问题，并解释策略选择。",
        "不得只展示步骤不解释依据", "变式不能只替换数字",
    ),
    "math_proof_reasoning": _archetype(
        "math_proof_reasoning", "math_formal", "证明与论证",
        "围绕命题条件建立推导链，并比较不同证明思路。",
        ("math_formalization", "math_proof", "math_reasoning_discourse"),
        ("证明", "推导", "定理", "性质", "充要", "逻辑"),
        ("development", "integration"),
        "学习者能够补全或独立构造证明，并指出每一步使用的条件。",
        "不能隐藏关键跳步", "必须区分例证与证明",
    ),
    "math_error_diagnosis": _archetype(
        "math_error_diagnosis", "math_formal", "错误诊断",
        "通过典型错误定位被误用的定义、条件或推理步骤。",
        ("math_error_analysis", "math_variation", "math_reasoning_discourse"),
        ("易错", "辨析", "错误", "陷阱", "判断", "反例"),
        ("development", "integration"),
        "学习者能够诊断错误、修复推理并构造一个能暴露误区的反例。",
        "不得只公布正确答案", "错误必须可信且能定位原因",
    ),
    "math_modeling_inquiry": _archetype(
        "math_modeling_inquiry", "math_formal", "建模探究",
        "把现实条件转化为变量、假设和数学关系，再解释结果边界。",
        ("math_modeling", "math_representation", "math_problem_strategy"),
        ("建模", "优化", "预测", "数据", "现实", "应用"),
        ("integration", "culmination"),
        "学习者能够建立、求解、检验模型，并解释假设改变后的影响。",
        "必须说明变量和假设", "结果必须返回现实语境解释",
    ),

    # 编程与工程：以可运行成果为载体，但区分入门、实现、调试、质量和系统设计。
    "engineering_runnable_intro": _archetype(
        "engineering_runnable_intro", "programming_engineering", "最小运行闭环",
        "先获得可运行反馈，再解释关键机制和环境前提。",
        ("engineering_minimal_run", "engineering_output", "engineering_mechanism"),
        ("入门", "第一个", "运行", "基础", "语法", "开始"),
        ("opening", "foundation"),
        "学习者能够独立运行最小实现，核对输出并解释关键语句。",
        "代码必须能直接运行", "环境与版本前提必须明确",
    ),
    "engineering_guided_build": _archetype(
        "engineering_guided_build", "programming_engineering", "引导式实现",
        "从需求和分解进入实现，再通过修改任务检验理解。",
        ("engineering_design", "engineering_minimal_run", "engineering_modification"),
        ("实现", "构建", "功能", "模块", "接口", "项目"),
        ("foundation", "development"),
        "学习者能够完成一个功能增量，并用验收条件证明它满足需求。",
        "不得只复制完整答案", "任务必须包含需求与完成条件",
    ),
    "engineering_debugging_lab": _archetype(
        "engineering_debugging_lab", "programming_engineering", "调试实验",
        "从可观察故障出发，形成复现、假设、定位、修复和回归验证闭环。",
        ("engineering_debugging", "engineering_mechanism", "engineering_output"),
        ("调试", "错误", "异常", "故障", "排查", "修复"),
        ("development", "integration"),
        "学习者能够复现故障、缩小范围、解释根因并验证修复没有引入回归。",
        "不得把报错信息直接等同于根因", "修复后必须重新验证",
    ),
    "engineering_test_refactor": _archetype(
        "engineering_test_refactor", "programming_engineering", "测试与重构",
        "用测试保护行为，在不改变外部契约的前提下改善实现质量。",
        ("engineering_testing", "engineering_refactoring", "engineering_review"),
        ("测试", "质量", "重构", "边界", "可靠", "评审"),
        ("integration", "culmination"),
        "学习者能够设计正常、边界和失败用例，并用测试证明重构保持行为。",
        "测试必须对应行为而非实现细节", "重构前后必须有可比较证据",
    ),
    "engineering_project_architecture": _archetype(
        "engineering_project_architecture", "programming_engineering", "项目与架构",
        "围绕系统目标分解组件、接口和取舍，形成可验收阶段成果。",
        ("engineering_design", "engineering_architecture", "engineering_testing"),
        ("架构", "系统", "服务", "部署", "综合项目", "交付"),
        ("integration", "culmination"),
        "学习者能够交付一个可运行、可测试、可解释取舍的工程成果。",
        "架构必须服务当前规模和约束", "不得用名词堆砌代替设计理由",
    ),

    # 自然科学：从现象进入问题、模型、调查、证据论证与设计应用。
    "science_phenomenon_inquiry": _archetype(
        "science_phenomenon_inquiry", "natural_science", "现象探究",
        "从可观察现象提出可检验问题与假设。",
        ("science_phenomenon", "science_question_hypothesis", "science_model"),
        ("现象", "观察", "为什么", "问题", "假设", "导入"),
        ("opening", "foundation"),
        "学习者能够区分观察与解释，并提出可由证据检验的问题。",
        "不得先给结论再伪装探究", "假设必须可被证据支持或反驳",
    ),
    "science_model_explanation": _archetype(
        "science_model_explanation", "natural_science", "模型解释",
        "用变量、关系和假设构造模型，解释现象并说明适用边界。",
        ("science_model", "science_evidence", "science_boundary"),
        ("模型", "规律", "定律", "机制", "解释", "原理"),
        ("foundation", "development"),
        "学习者能够使用模型解释或预测，并指出模型成立所需条件。",
        "模型不是现实本身", "证据与解释必须分开",
    ),
    "science_investigation": _archetype(
        "science_investigation", "natural_science", "实验调查",
        "设计变量、对照、测量和数据分析来检验问题。",
        ("science_experiment_design", "science_evidence", "science_data_analysis"),
        ("实验", "测量", "验证", "数据", "调查", "探究"),
        ("development", "integration"),
        "学习者能够设计可执行调查，分析数据并陈述不确定性。",
        "必须控制关键变量", "数据不足时不得给出过强结论",
    ),
    "science_evidence_argument": _archetype(
        "science_evidence_argument", "natural_science", "证据论证",
        "建立主张、证据和推理之间的可检查关系。",
        ("science_evidence", "science_argument", "science_boundary"),
        ("证据", "论证", "结论", "争议", "评价", "解释"),
        ("development", "integration"),
        "学习者能够比较解释，并根据证据质量修正主张。",
        "相关性不能直接写成因果", "必须说明替代解释",
    ),
    "science_design_application": _archetype(
        "science_design_application", "natural_science", "设计与应用",
        "使用科学模型设计解决方案，并依据约束评价结果。",
        ("science_prediction", "science_engineering_design", "science_boundary"),
        ("设计", "应用", "工程", "方案", "预测", "解决"),
        ("integration", "culmination"),
        "学习者能够提出方案、说明科学依据并按标准比较取舍。",
        "方案必须服从科学边界", "评价标准必须在设计前明确",
    ),

    # 生命科学与医学基础：连接尺度、结构功能、机制系统、证据和案例推理。
    "life_structure_function": _archetype(
        "life_structure_function", "life_medical", "结构与功能",
        "在正确尺度上定位结构，并解释结构如何支持功能。",
        ("life_location_structure", "life_function", "life_scale_connection"),
        ("结构", "组成", "位置", "功能", "器官", "细胞"),
        ("opening", "foundation"),
        "学习者能够从尺度、结构特征推断功能，并说明证据边界。",
        "不能把位置描述当作功能解释", "必须标明讨论尺度",
    ),
    "life_mechanism_system": _archetype(
        "life_mechanism_system", "life_medical", "机制与系统",
        "沿因果链解释过程，并连接调节、反馈和系统关系。",
        ("life_mechanism", "life_regulation", "life_scale_connection"),
        ("机制", "过程", "调节", "反馈", "稳态", "通路"),
        ("foundation", "development"),
        "学习者能够按因果顺序解释过程，并预测关键环节变化的影响。",
        "相关性不能冒充机制", "不得跳过关键中介环节",
    ),
    "life_evidence_quantitative": _archetype(
        "life_evidence_quantitative", "life_medical", "生物证据与数据",
        "使用实验、数据、模型或统计证据评价生命科学主张。",
        ("life_evidence", "life_quantitative", "life_mechanism"),
        ("实验", "数据", "研究", "统计", "证据", "测量"),
        ("development", "integration"),
        "学习者能够解释数据支持什么、不支持什么，并识别不确定性。",
        "不得根据单一研究下绝对结论", "必须区分观察、模型与推断",
    ),
    "life_comparative_variation": _archetype(
        "life_comparative_variation", "life_medical", "比较与变异",
        "比较不同结构、物种、状态或条件，解释共同机制与差异来源。",
        ("life_normal_abnormal", "life_case", "life_scale_connection"),
        ("比较", "进化", "适应", "差异", "异常", "变异"),
        ("development", "integration"),
        "学习者能够基于机制解释相同与差异，而不是只列特征。",
        "正常与异常不能价值化", "差异必须回到尺度和机制",
    ),
    "life_case_reasoning": _archetype(
        "life_case_reasoning", "life_medical", "案例推理",
        "用结构、功能和机制解释教学案例，并明确不能越过的诊断边界。",
        ("life_case", "life_mechanism", "life_normal_abnormal"),
        ("案例", "疾病", "症状", "健康", "临床", "综合"),
        ("integration", "culmination"),
        "学习者能够提出机制解释、列出所需证据并说明不确定性。",
        "不得给出个人诊断或治疗建议", "案例结论必须与证据强度相称",
    ),

    # 人文社科：区分提问、材料解释、因果变化、观点论证和综合表达。
    "humanities_inquiry_context": _archetype(
        "humanities_inquiry_context", "humanities_social", "问题与语境",
        "建立值得追问的核心问题，只补充回答问题所需语境。",
        ("humanities_question", "humanities_context", "humanities_source"),
        ("问题", "导论", "背景", "语境", "社会现象", "为什么"),
        ("opening", "foundation"),
        "学习者能够提出支持性问题，并说明哪些材料能帮助回答。",
        "背景不能退化为年代或人物流水账", "问题必须允许证据改变答案",
    ),
    "humanities_source_interpretation": _archetype(
        "humanities_source_interpretation", "humanities_social", "材料解释",
        "辨析材料来源、语境、表述和限制，再形成可证成解释。",
        ("humanities_source", "humanities_source_criticism", "humanities_interpretation"),
        ("史料", "文本", "材料", "原著", "作品", "来源"),
        ("foundation", "development"),
        "学习者能够引用具体材料形成解释，并评价材料的立场和限制。",
        "材料内容不能自动等同于历史事实", "解释必须指出文本依据",
    ),
    "humanities_causal_change": _archetype(
        "humanities_causal_change", "humanities_social", "因果与变化",
        "分析事件、制度或观念随时间变化的多重原因、机制和结果。",
        ("humanities_timeline", "humanities_causation", "humanities_source"),
        ("历史", "演变", "原因", "影响", "变化", "时期"),
        ("development", "integration"),
        "学习者能够构造多因素因果解释，并区分触发、条件和长期结构。",
        "先后发生不能直接证明因果", "时间线只保留解释所需节点",
    ),
    "humanities_argument_debate": _archetype(
        "humanities_argument_debate", "humanities_social", "观点论证",
        "比较不同观点的概念、前提、证据和解释力。",
        ("humanities_claim", "humanities_comparison", "humanities_interpretation"),
        ("观点", "论证", "争议", "哲学", "理论", "批判"),
        ("development", "integration"),
        "学习者能够提出可辩护主张、回应异议并承认论证边界。",
        "争议不能写成唯一事实", "比较必须使用共同问题或标准",
    ),
    "humanities_synthesis_response": _archetype(
        "humanities_synthesis_response", "humanities_social", "综合表达",
        "整合多份材料和观点，形成面向问题的写作、讨论或公共表达。",
        ("humanities_response", "humanities_synthesis", "humanities_claim"),
        ("写作", "讨论", "综合", "评论", "报告", "表达"),
        ("integration", "culmination"),
        "学习者能够提交有主张、证据、推理和回应异议的完整作品。",
        "不得把材料摘要拼接成论证", "评价标准必须覆盖证据与推理",
    ),

    # 语言学习：以真实行动为目标，区分理解、注意、练习、互动、调解和修正。
    "language_input_comprehension": _archetype(
        "language_input_comprehension", "language_learning", "可理解输入",
        "通过可理解文本或话语获得意义，并提取可复用语块。",
        ("language_input", "language_chunks", "language_noticing"),
        ("听力", "阅读", "输入", "对话", "文本", "理解"),
        ("opening", "foundation"),
        "学习者能够理解目标信息，并在新输入中识别目标语块。",
        "输入难度必须可控", "不能把逐词翻译当作理解",
    ),
    "language_form_accuracy": _archetype(
        "language_form_accuracy", "language_learning", "形式与准确性",
        "从意义和使用中注意语言形式，再通过受控练习建立准确性。",
        ("language_noticing", "language_form_use", "language_controlled_practice"),
        ("语法", "句型", "词汇", "拼写", "形式", "准确"),
        ("foundation", "development"),
        "学习者能够在给定语境中准确选择和变换目标形式。",
        "形式讲解必须回到意义和语用", "练习不能长期停留在机械替换",
    ),
    "language_interaction_task": _archetype(
        "language_interaction_task", "language_learning", "互动任务",
        "围绕角色、目的和信息差完成真实互动。",
        ("language_input", "language_interaction", "language_output"),
        ("会话", "口语", "交流", "互动", "角色", "沟通"),
        ("development", "integration"),
        "学习者能够理解对方、作出回应并协商意义以完成任务。",
        "互动必须有真实信息差或选择", "不能把背诵脚本当作自由互动",
    ),
    "language_mediation_task": _archetype(
        "language_mediation_task", "language_learning", "调解与转述",
        "为特定对象重组、解释或转述信息，而不是逐句翻译。",
        ("language_input", "language_mediation", "language_output"),
        ("翻译", "转述", "总结", "解释", "调解", "跨文化"),
        ("development", "integration"),
        "学习者能够按对象和目的准确重组信息并处理文化语用差异。",
        "调解不是逐字替换", "必须保留关键信息与交际目的",
    ),
    "language_performance_feedback": _archetype(
        "language_performance_feedback", "language_learning", "表现与修正",
        "完成综合语言行动，依据标准获得反馈、修正并再次表现。",
        ("language_output", "language_feedback_repair", "language_interaction"),
        ("演讲", "写作", "展示", "综合", "复习", "反馈"),
        ("integration", "culmination"),
        "学习者能够完成真实输出，并根据反馈进行可观察修订。",
        "评价不能只数语法错误", "修订后必须再次验证交际效果",
    ),

    # 商业与职业：从场景诊断进入决策、工具、模拟与交付复盘。
    "business_scenario_diagnosis": _archetype(
        "business_scenario_diagnosis", "business_career", "场景诊断",
        "明确角色、目标、约束和利益相关者，再界定真正问题。",
        ("business_scenario", "business_problem_diagnosis", "business_framework"),
        ("场景", "问题", "诊断", "目标", "约束", "需求"),
        ("opening", "foundation"),
        "学习者能够提交结构化问题定义，并区分症状、原因和约束。",
        "不得套框架后再找问题", "必须说明信息缺口",
    ),
    "business_case_decision": _archetype(
        "business_case_decision", "business_career", "案例决策",
        "从不完整信息中形成选项、比较取舍并作出可解释决策。",
        ("business_case", "business_decision", "business_metric"),
        ("案例", "决策", "选择", "取舍", "战略", "方案"),
        ("development", "integration"),
        "学习者能够提交决策备忘录，说明依据、风险和替代方案。",
        "案例不得只有标准答案", "指标不能替代判断",
    ),
    "business_tool_workshop": _archetype(
        "business_tool_workshop", "business_career", "工具工作坊",
        "理解工具适用条件，并用它完成当前工作成果。",
        ("business_framework", "business_tool", "business_task"),
        ("工具", "模板", "方法", "流程", "分析", "规划"),
        ("foundation", "development"),
        "学习者能够正确填写或使用工具，并解释关键判断。",
        "工具必须有适用边界", "不能把填表当作完成分析",
    ),
    "business_role_simulation": _archetype(
        "business_role_simulation", "business_career", "角色模拟",
        "在目标冲突、信息差和时间约束下练习沟通与协商。",
        ("business_scenario", "business_roleplay", "business_metric"),
        ("谈判", "销售", "沟通", "汇报", "面试", "角色"),
        ("development", "integration"),
        "学习者能够完成一次角色表现，并依据行为标准复盘。",
        "角色双方必须有不同目标", "复盘必须基于具体行为证据",
    ),
    "business_deliverable_review": _archetype(
        "business_deliverable_review", "business_career", "成果交付与复盘",
        "产出可使用的工作成果，并依据指标、风险和利益相关者影响迭代。",
        ("business_task", "business_metric", "business_reflection", "business_ethics"),
        ("交付", "方案", "报告", "项目", "综合", "复盘"),
        ("integration", "culmination"),
        "学习者能够交付成果、接受评审并说明修订和影响。",
        "必须区分活动完成与成果质量", "不得忽略伦理与利益相关者影响",
    ),
}


SUBJECT_VARIANTS: dict[str, SubjectVariantSpec] = {
    "general_conceptual": SubjectVariantSpec(
        "general_conceptual", "general", "概念理解型",
        ("概念", "原理", "导论", "认识"),
        ("general_concept_building", "general_comparison_decision"),
    ),
    "general_procedural": SubjectVariantSpec(
        "general_procedural", "general", "方法应用型",
        ("方法", "技能", "操作", "流程"),
        ("general_method_workshop", "general_case_application"),
    ),
    "math_theoretical": SubjectVariantSpec(
        "math_theoretical", "math_formal", "理论与证明",
        ("证明", "定理", "逻辑", "代数", "几何"),
        ("math_intuition_representation", "math_proof_reasoning"),
    ),
    "math_quantitative": SubjectVariantSpec(
        "math_quantitative", "math_formal", "计算与建模",
        ("计算", "概率", "统计", "优化", "建模", "数据"),
        ("math_worked_strategy", "math_modeling_inquiry"),
    ),
    "engineering_programming_fundamentals": SubjectVariantSpec(
        "engineering_programming_fundamentals", "programming_engineering", "编程基础",
        ("编程入门", "语法", "算法基础", "python基础", "java基础"),
        ("engineering_runnable_intro", "engineering_guided_build"),
    ),
    "engineering_software_systems": SubjectVariantSpec(
        "engineering_software_systems", "programming_engineering", "软件工程与系统",
        ("软件工程", "系统", "架构", "服务", "数据库", "网络", "部署"),
        ("engineering_guided_build", "engineering_test_refactor", "engineering_project_architecture"),
    ),
    "engineering_data_ai": SubjectVariantSpec(
        "engineering_data_ai", "programming_engineering", "数据与人工智能工程",
        ("机器学习", "人工智能", "数据科学", "模型训练", "推理"),
        ("engineering_guided_build", "engineering_debugging_lab", "engineering_test_refactor"),
    ),
    "science_physical_modeling": SubjectVariantSpec(
        "science_physical_modeling", "natural_science", "物理模型型",
        ("物理", "力学", "电磁", "天文", "气象", "模型"),
        ("science_phenomenon_inquiry", "science_model_explanation", "science_evidence_argument"),
    ),
    "science_experimental": SubjectVariantSpec(
        "science_experimental", "natural_science", "实验探究型",
        ("化学", "实验", "测量", "验证", "材料"),
        ("science_phenomenon_inquiry", "science_investigation"),
    ),
    "science_environment_design": SubjectVariantSpec(
        "science_environment_design", "natural_science", "环境与工程应用",
        ("环境", "地质", "能源", "工程", "生态环境"),
        ("science_investigation", "science_design_application"),
    ),
    "life_biological_systems": SubjectVariantSpec(
        "life_biological_systems", "life_medical", "生命系统",
        ("生物", "细胞", "遗传", "进化", "生态", "植物", "动物"),
        ("life_structure_function", "life_mechanism_system", "life_comparative_variation"),
    ),
    "life_medical_foundations": SubjectVariantSpec(
        "life_medical_foundations", "life_medical", "医学基础",
        ("医学", "生理", "解剖", "免疫", "神经", "病理", "健康"),
        ("life_structure_function", "life_mechanism_system", "life_case_reasoning"),
    ),
    "humanities_historical": SubjectVariantSpec(
        "humanities_historical", "humanities_social", "历史探究",
        (
            "历史", "古代史", "近代史", "现代史",
            "时期", "朝代", "战争", "革命", "演变",
        ),
        ("humanities_inquiry_context", "humanities_source_interpretation", "humanities_causal_change"),
    ),
    "humanities_textual_cultural": SubjectVariantSpec(
        "humanities_textual_cultural", "humanities_social", "文本与文化解释",
        ("文学", "文本", "小说", "诗歌", "艺术", "文化"),
        ("humanities_source_interpretation", "humanities_argument_debate", "humanities_synthesis_response"),
    ),
    "humanities_philosophical": SubjectVariantSpec(
        "humanities_philosophical", "humanities_social", "哲学与规范论证",
        ("哲学", "伦理", "逻辑论证", "思想", "价值", "认识论"),
        ("humanities_inquiry_context", "humanities_argument_debate"),
    ),
    "humanities_social_inquiry": SubjectVariantSpec(
        "humanities_social_inquiry", "humanities_social", "社会科学探究",
        ("社会学", "心理学", "经济学", "政治", "教育", "传播", "公共"),
        ("humanities_inquiry_context", "humanities_source_interpretation", "humanities_argument_debate"),
    ),
    "language_general_communication": SubjectVariantSpec(
        "language_general_communication", "language_learning", "日常交际",
        ("口语", "会话", "日常", "旅行", "沟通"),
        ("language_input_comprehension", "language_interaction_task"),
    ),
    "language_academic_professional": SubjectVariantSpec(
        "language_academic_professional", "language_learning", "学术与职业沟通",
        ("学术", "商务", "专业", "写作", "演讲", "考试"),
        ("language_mediation_task", "language_performance_feedback"),
    ),
    "business_strategy_operations": SubjectVariantSpec(
        "business_strategy_operations", "business_career", "战略与运营",
        ("战略", "运营", "产品", "项目管理", "供应链"),
        ("business_scenario_diagnosis", "business_case_decision", "business_deliverable_review"),
    ),
    "business_market_communication": SubjectVariantSpec(
        "business_market_communication", "business_career", "市场与沟通",
        ("营销", "销售", "谈判", "品牌", "客户", "面试"),
        ("business_scenario_diagnosis", "business_role_simulation"),
    ),
    "business_analytics_finance": SubjectVariantSpec(
        "business_analytics_finance", "business_career", "分析与财务决策",
        ("财务", "数据分析", "指标", "投资", "会计", "商业分析"),
        ("business_tool_workshop", "business_case_decision"),
    ),
}


MODE_ARCHETYPE_IDS: dict[str, tuple[str, ...]] = {
    mode: tuple(
        item.archetype_id
        for item in LESSON_ARCHETYPES.values()
        if item.mode == mode
    )
    for mode in {
        "general",
        "math_formal",
        "programming_engineering",
        "natural_science",
        "life_medical",
        "humanities_social",
        "language_learning",
        "business_career",
    }
}

DEFAULT_VARIANT_IDS: dict[str, str] = {
    "general": "general_conceptual",
    "math_formal": "math_theoretical",
    "programming_engineering": "engineering_programming_fundamentals",
    "natural_science": "science_physical_modeling",
    "life_medical": "life_biological_systems",
    "humanities_social": "humanities_social_inquiry",
    "language_learning": "language_general_communication",
    "business_career": "business_strategy_operations",
}


def course_stage(index: int, count: int) -> str:
    if count <= 1:
        return "foundation"
    if index >= count - 1:
        return "culmination"
    progress = index / max(count - 1, 1)
    if progress <= 0.12:
        return "opening"
    if progress <= 0.34:
        return "foundation"
    if progress <= 0.72:
        return "development"
    return "integration"


def resolve_subject_variant(mode: str, text: str) -> SubjectVariantSpec:
    lowered = str(text or "").lower()
    candidates = [
        item
        for item in SUBJECT_VARIANTS.values()
        if item.mode == mode
    ]
    scored = [
        (
            sum(
                1
                for signal in item.signals
                if signal.lower() in lowered
            ),
            -index,
            item,
        )
        for index, item in enumerate(candidates)
    ]
    best = max(scored, default=(0, 0, None), key=lambda item: (item[0], item[1]))
    if best[0] > 0 and best[2] is not None:
        return best[2]
    fallback = SUBJECT_VARIANTS.get(DEFAULT_VARIANT_IDS[mode])
    if fallback is None:
        raise ValueError(f"Missing default subject variant for {mode}")
    return fallback


def select_lesson_archetype(
    *,
    mode: str,
    variant_id: str,
    section: dict[str, Any],
    index: int,
    count: int,
) -> LessonArchetypeSpec:
    stage = course_stage(index, count)
    text = " ".join([
        str(section.get("title") or ""),
        str(section.get("learning_objective") or ""),
        str(section.get("scope_boundary") or ""),
        " ".join(str(item) for item in section.get("key_points") or []),
        " ".join(str(item) for item in section.get("assessment") or []),
    ]).lower()
    variant = SUBJECT_VARIANTS.get(variant_id)
    preferred = (
        variant.preferred_archetype_ids
        if variant and variant.mode == mode
        else ()
    )
    candidates = [
        LESSON_ARCHETYPES[item]
        for item in MODE_ARCHETYPE_IDS.get(mode, ())
    ]
    ranked: list[tuple[float, int, LessonArchetypeSpec]] = []
    for position, archetype in enumerate(candidates):
        signal_score = sum(
            4.0
            for signal in archetype.signals
            if signal.lower() in text
        )
        stage_score = 3.0 if stage in archetype.preferred_stages else 0.0
        variant_score = (
            max(0.5, 2.5 - preferred.index(archetype.archetype_id) * 0.5)
            if archetype.archetype_id in preferred
            else 0.0
        )
        ranked.append((
            signal_score + stage_score + variant_score,
            -position,
            archetype,
        ))
    if not ranked:
        raise ValueError(f"Missing lesson archetypes for {mode}")
    return max(ranked, key=lambda item: (item[0], item[1]))[2]


def validate_archetype_registry(
    *,
    known_module_ids: Iterable[str],
) -> list[str]:
    known = set(known_module_ids)
    issues: list[str] = []
    for mode, archetype_ids in MODE_ARCHETYPE_IDS.items():
        if len(archetype_ids) < 4:
            issues.append(f"{mode} 的课型少于 4 个")
    for archetype in LESSON_ARCHETYPES.values():
        missing = [
            module_id
            for module_id in archetype.module_ids
            if module_id not in known
        ]
        if missing:
            issues.append(
                f"{archetype.archetype_id} 引用了不存在的模块: {', '.join(missing)}"
            )
        if not archetype.evidence_contract:
            issues.append(f"{archetype.archetype_id} 缺少成果证据")
    for mode, default_id in DEFAULT_VARIANT_IDS.items():
        variant = SUBJECT_VARIANTS.get(default_id)
        if variant is None or variant.mode != mode:
            issues.append(f"{mode} 缺少有效默认分型")
    return issues


__all__ = [
    "LessonArchetypeSpec",
    "SubjectVariantSpec",
    "LESSON_ARCHETYPES",
    "SUBJECT_VARIANTS",
    "MODE_ARCHETYPE_IDS",
    "course_stage",
    "resolve_subject_variant",
    "select_lesson_archetype",
    "validate_archetype_registry",
]
