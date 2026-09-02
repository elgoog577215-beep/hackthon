"""版本化学科标准包。

它是统一教学语义编译器的数据注册表，不是第二条生成链。学科大类提供稳定
底座，具体专业画像只收窄专业行动、证据、产物和安全边界。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SUBJECT_STANDARD_PACK_VERSION = "subject_standard_pack_v1"

ARTIFACT_LANGUAGE = {
    "outline": "使用课程标准常见的目标—内容—证据语言；目标可观察，章节名指向真实学习责任，不写宣传口号。",
    "lesson_plan": "写教师可执行的课堂设计，明确教师动作、学生行动、学习证据、反馈和时间，不写系统流程说明。",
    "script": "使用教师在课堂上会自然说出口的专业语言；讲清条件、推理和边界，不写论文摘要、教材腔或机械调度标签。",
    "question_bank": "题干条件充分、任务明确、答案可判定；难度来自专业推理和迁移，不来自晦涩措辞。",
    "ppt": "一页承担一个清楚的教学任务和主要结论；标题可直接读懂，正文服务讲解而不是复制讲义。",
}

SUBJECT_ARTIFACT_LANGUAGE: dict[str, dict[str, str]] = {
    "general": {
        "outline": "用清楚的目标、任务和成果组织章节，避免百科式铺陈。",
        "lesson_plan": "写明教师怎样组织任务、学生怎样完成、用什么结果判断学会。",
        "script": "像教师面对学生解释和追问，少下定义，多结合任务说明怎么做、为什么。",
        "question_bank": "题目使用学生能理解的真实任务，条件完整，答案能够据此判断。",
        "ppt": "标题直接说明本页任务或结论，正文只保留讲解和行动所需信息。",
    },
    "math_formal": {
        "outline": "章节名称体现定义、方法、推理与应用的先后关系，不把相近概念并列堆放。",
        "lesson_plan": "写清表征转换、定义建立、推导示范、变式练习和错误诊断怎样衔接。",
        "script": "使用数学课堂常用表达，先说明条件和对象，再逐步推导；直观解释不能替代定义和证明。",
        "question_bank": "符号、条件和问题目标完整；参考答案给出必要步骤并覆盖等价写法。",
        "ppt": "公式与图像围绕同一个数学判断，标题不使用公式碎片，关键条件与结论就近呈现。",
    },
    "programming_engineering": {
        "outline": "按能运行、能解释、能调试、能测试和能作工程取舍的能力推进。",
        "lesson_plan": "写清环境、输入、操作、运行结果、调试过程和验收标准，避免只讲概念或只贴代码。",
        "script": "像教师现场演示工程任务：先交代目标和环境，再边运行边解释关键选择和失败原因。",
        "question_bank": "提供必要代码、版本和输入条件；答案包含可验证结果、测试或调试依据。",
        "ppt": "代码、运行结果和工程取舍分区呈现，一页只解释一个关键机制或操作判断。",
    },
    "natural_science": {
        "outline": "按现象、问题、模型、实验或数据、解释边界组织学习责任。",
        "lesson_plan": "区分观察与解释，写明变量控制、记录方法、数据处理、误差分析和安全要求。",
        "script": "使用科学课堂常用的证据语言，明确哪些是观察、哪些是推断、结论在什么条件下成立。",
        "question_bank": "给出足以判断的实验或数据条件，要求学生解释证据而不只是套用公式。",
        "ppt": "图表、实验条件与结论对应呈现，注明变量、单位、不确定性和适用范围。",
    },
    "life_medical": {
        "outline": "按尺度、结构、功能、机制、调节和案例推理组织内容，避免把名词清单当成知识结构。",
        "lesson_plan": "写清观察对象、机制链、证据强度、案例判断和安全边界，不提供个人诊疗建议。",
        "script": "使用基础医学和生命科学课堂的谨慎表达，区分结构、功能、机制、相关和因果。",
        "question_bank": "案例信息充分，问题只要求课程范围内可以判断的机制或证据，不暗示真实诊断。",
        "ppt": "结构图、机制链和案例证据分层呈现，避免用一张复杂图代替逐步解释。",
    },
    "humanities_social": {
        "outline": "按问题、材料、概念、解释、异议和判断推进，不把年代、人物或理论简单罗列。",
        "lesson_plan": "写清共同材料、讨论问题、论证标准、异议回应和观点修订怎样发生。",
        "script": "区分史实、材料、观点和解释；使用有依据但不装腔的课堂语言，争议处说明不同看法。",
        "question_bank": "材料出处和情境充分，要求形成有证据的解释或论证，评分标准允许合理的不同答案。",
        "ppt": "材料摘录、观点和证据关系清楚，一页推动一个论证步骤，不用口号替代分析。",
    },
    "language_learning": {
        "outline": "围绕真实沟通对象、目的和情境安排输入、练习、输出与再次表现。",
        "lesson_plan": "写清语言输入、注意形式、受控练习、真实表达和反馈后重做的任务。",
        "script": "使用目标语课堂中自然、可理解的指令和示范；语法说明服务表达，不长期停留在术语讲解。",
        "question_bank": "给出明确语境、对象和表达目的，同时检查准确、得体和可理解性。",
        "ppt": "示例、语言形式和沟通任务就近呈现，避免大段双语对照挤满页面。",
    },
    "business_career": {
        "outline": "按角色、目标、约束、分析、决策、交付和复盘组织课程，不先套框架再找问题。",
        "lesson_plan": "写清场景信息、相关方、可用数据、决策标准、交付物和复盘指标。",
        "script": "像教师带学生分析真实工作任务，直接说明约束、选择和代价，不堆砌商业术语。",
        "question_bank": "场景与数据足够，要求作出可执行判断并说明取舍；评分依据对应交付质量。",
        "ppt": "问题、数据、方案和取舍分层表达，图表必须服务当前决策而不是装饰。",
    },
}


def _standard(
    epistemic_method: str,
    actions: list[str],
    artifacts: list[str],
    evidence: list[str],
    misconceptions: list[str],
    source_policy: list[str],
    safety: list[str],
    quality: list[str],
    recipes: dict[str, dict[str, str]],
) -> dict[str, Any]:
    return {
        "epistemic_method": epistemic_method,
        "professional_actions": actions,
        "canonical_artifacts": artifacts,
        "evidence_patterns": evidence,
        "common_misconceptions": misconceptions,
        "source_policy": source_policy,
        "safety_boundaries": safety,
        "artifact_language": deepcopy(ARTIFACT_LANGUAGE),
        "quality_rules": quality,
        "block_recipes": recipes,
    }


SUBJECT_STANDARD_PACKS: dict[str, dict[str, Any]] = {
    "general": {
        "label": "通用课程",
        "base": _standard(
            "通过清楚界定概念、示范方法、完成真实任务并迁移来建立可信理解。",
            ["界定对象", "比较边界", "示范方法", "完成任务", "解释迁移"],
            ["概念图", "操作清单", "案例分析", "综合任务"],
            ["准确解释", "方法应用", "成果核对", "条件变化后的再次表现"],
            ["把术语复述当成理解", "活动完成但没有可检查成果"],
            ["教师指定资料优先", "资料不足时区分通识与教学情境"],
            ["不编造资料来源、数据或制度要求"],
            ["每个目标都有对应行动和证据", "例子、活动与评价指向同一学习责任"],
            {
                "concept": {"teacher_activity": "用定义、边界和例反例建立概念", "student_activity": "解释概念并判断相邻实例", "expected_output": "概念解释与边界判断"},
                "application": {"teacher_activity": "给出真实任务、条件和成功标准", "student_activity": "选择方法完成任务并说明理由", "expected_output": "可核对的任务成果"},
            },
        ),
        "profiles": {
            "general": {"label": "通用课程", "keywords": []},
            "education": {"label": "教育与教师发展", "keywords": ["教育学", "课程论", "教学论", "教师教育", "班级管理"], "professional_actions": ["分析学习者", "设计目标证据", "组织活动", "观察学习", "反思改进"], "canonical_artifacts": ["教学设计", "观察记录", "评价量规", "反思报告"]},
        },
    },
    "math_formal": {
        "label": "数学与形式科学",
        "base": _standard(
            "以定义、条件、表征、推理和可检验的形式结果建立结论。",
            ["识别对象与条件", "转换表征", "提出猜想", "推导或证明", "用反例和计算核验"],
            ["定义与性质表", "推导链", "证明", "反例", "形式模型", "完整解题过程"],
            ["符号与图像互译", "关键步骤完整的推导", "独立证明或求解", "变式与反例判断"],
            ["用直觉替代定义", "忽略成立条件", "只记公式不理解对象", "跳过关键推理步骤"],
            ["教材定义与课程约定优先", "定理必须交代前提", "数值结论用代入、图像或量纲核验"],
            ["不得伪造定理、证明或计算结果", "未证明结论明确标为猜想或直观解释"],
            ["定义、符号和条件前后一致", "例题给出条件、思路、步骤、结果与核验", "直观解释不能代替形式论证"],
            {
                "concept": {"teacher_activity": "从对象和反例进入正式定义，并连接符号、图像与语言", "student_activity": "转换表征并判断例与反例", "expected_output": "定义复述、表征转换与边界判断"},
                "reasoning": {"teacher_activity": "显化每一步依据、成立条件和容易跳步的位置", "student_activity": "补全推导并解释关键等价或蕴含", "expected_output": "条件完整的推导或证明链"},
                "example": {"teacher_activity": "示范审题、选法、计算和结果核验", "student_activity": "预测步骤、完成计算并用第二种表征核验", "expected_output": "可复查的完整解答"},
                "counterexample": {"teacher_activity": "用最小反例暴露条件和结论的边界", "student_activity": "定位失效条件并修正命题", "expected_output": "反例与修正后的条件"},
            },
        ),
        "profiles": {
            "higher_mathematics": {"label": "高等数学与分析", "keywords": ["微积分", "数学分析", "高等数学", "极限", "导数", "积分"], "canonical_artifacts": ["极限论证", "局部—整体关系", "几何解释", "计算核验"]},
            "linear_algebra": {"label": "线性代数", "keywords": ["线性代数", "矩阵", "向量空间", "特征值"], "canonical_artifacts": ["矩阵计算", "线性变换图景", "空间解释", "秩与解空间关系"]},
            "probability_statistics": {"label": "概率与统计", "keywords": ["概率", "统计", "随机", "回归", "假设检验"], "professional_actions": ["定义随机对象", "选择概率模型", "估计参数", "量化不确定性", "解释统计结论"], "safety_boundaries": ["相关不能直接写成因果", "样本、假设和不确定性必须说明"]},
            "logic_discrete": {"label": "逻辑与离散数学", "keywords": ["离散数学", "数理逻辑", "图论", "组合数学"], "canonical_artifacts": ["形式命题", "归纳证明", "构造", "反例", "算法复杂度说明"]},
        },
    },
    "programming_engineering": {
        "label": "编程与工程技术",
        "base": _standard(
            "以需求、可运行实现、测试证据和工程取舍证明方案有效。",
            ["澄清需求", "建立最小实现", "解释机制", "调试测试", "比较取舍", "交付复盘"],
            ["需求与约束", "代码或模型", "测试用例", "故障记录", "工程设计", "验收报告"],
            ["可运行结果", "失败复现", "测试通过", "约束下的设计理由", "独立迁移实现"],
            ["只贴代码不解释机制", "只讲概念不形成实现", "用单次运行代替测试", "忽略环境和版本"],
            ["明确工具、环境、版本和接口约束", "官方文档与可复现实验优先"],
            ["高风险操作给出隔离与恢复方式", "不得暴露密钥、真实个人数据或未经授权系统"],
            ["示例可以运行或明确标注伪代码", "任务有输入、输出、约束和验收", "错误案例包含复现、定位、修复和回归"],
            {
                "example": {"teacher_activity": "从最小可运行例子解释执行过程和关键取舍", "student_activity": "预测输出、运行验证并解释差异", "expected_output": "可运行示例与机制说明"},
                "activity": {"teacher_activity": "确认需求、接口、约束和验收用例", "student_activity": "实现、测试、记录失败并迭代", "expected_output": "可测试的工程增量"},
                "feedback": {"teacher_activity": "依据日志、测试和交付标准定位缺口", "student_activity": "复现问题、修复并完成回归测试", "expected_output": "故障原因、修复结果与测试证据"},
            },
        ),
        "profiles": {
            "software_programming": {"label": "软件与程序设计", "keywords": ["程序设计", "软件工程", "java", "python", "前端", "后端", "算法"], "canonical_artifacts": ["可运行代码", "单元测试", "接口契约", "代码评审记录"]},
            "data_ai": {"label": "数据科学与人工智能", "keywords": ["人工智能", "机器学习", "深度学习", "数据科学", "大模型", "神经网络"], "professional_actions": ["定义任务与指标", "检查数据", "建立基线", "训练评估", "误差分析", "部署监测"], "safety_boundaries": ["训练数据、评估集和现实效果分开", "说明偏差、泄漏、幻觉和适用边界"]},
            "electrical_automation": {"label": "电气、电子与自动化", "keywords": ["电路", "电子", "电气", "自动化", "控制系统", "信号"], "canonical_artifacts": ["电路图", "信号波形", "控制模型", "测量记录", "故障诊断"]},
            "mechanical_civil": {"label": "机械、土木与制造", "keywords": ["机械", "土木", "制造", "工程制图", "材料力学", "结构工程"], "professional_actions": ["识别载荷与约束", "建立模型", "计算校核", "设计制造", "测试失效"], "canonical_artifacts": ["工程图", "计算书", "模型或样机", "安全系数与测试报告"]},
        },
    },
    "natural_science": {
        "label": "自然科学",
        "base": _standard(
            "以观察、假设、模型、实验或数据和受证据约束的解释建立结论。",
            ["区分观察与解释", "提出可检验问题", "建立模型", "控制变量", "分析数据与误差", "限定结论"],
            ["实验方案", "观察记录", "数据表与图", "模型", "误差分析", "证据结论"],
            ["可重复观察", "变量控制", "数据处理", "模型预测", "对替代解释的比较"],
            ["把相关当因果", "把一次观察当普遍规律", "忽略误差与尺度", "先有结论再挑数据"],
            ["原始数据、实验条件和文献结论分开", "说明测量范围与不确定性"],
            ["实验安全与废弃物处理是硬约束", "不能编造实验数据或把模拟结果冒充实测"],
            ["现象、模型和数据相互对应", "结论强度不超过证据", "异常数据和替代解释得到处理"],
            {
                "orientation": {"teacher_activity": "呈现可观察现象并提出可检验问题", "student_activity": "描述观察、提出假设并区分二者", "expected_output": "观察记录与可检验假设"},
                "activity": {"teacher_activity": "明确变量、操作、安全和记录规范", "student_activity": "实施实验、记录数据并标记异常", "expected_output": "可追溯实验或调查记录"},
                "reasoning": {"teacher_activity": "连接数据、模型、误差与结论强度", "student_activity": "分析证据并比较替代解释", "expected_output": "有边界的证据结论"},
            },
        ),
        "profiles": {
            "physics": {"label": "物理学", "keywords": ["物理", "力学", "电磁学", "光学", "热学"], "canonical_artifacts": ["受力图", "物理模型", "量纲分析", "实验曲线", "极限情况核验"]},
            "chemistry": {"label": "化学", "keywords": ["化学", "有机", "无机", "分析化学", "物理化学"], "canonical_artifacts": ["反应式", "结构—性质关系", "实验流程", "光谱或滴定数据", "安全处置"]},
            "earth_environment": {"label": "地球与环境科学", "keywords": ["地质", "地理", "环境", "气象", "海洋"], "professional_actions": ["识别空间尺度", "读取观测资料", "建立过程模型", "比较多源证据", "评估不确定性"]},
        },
    },
    "life_medical": {
        "label": "生命科学与医学基础",
        "base": _standard(
            "连接结构、功能、机制、尺度、个体差异和证据强度来解释生命过程。",
            ["定位尺度", "连接结构与功能", "建立机制链", "分析调节与失衡", "用案例和数据推理", "说明证据等级"],
            ["结构图", "机制链", "实验数据", "病例时间线", "鉴别表", "风险与边界说明"],
            ["机制解释", "数据判读", "案例中的证据权重", "对替代解释的比较"],
            ["把结构、功能和机制混写", "从单一症状直接下结论", "忽略时间过程与个体差异"],
            ["教材、指南、系统综述和原始研究按证据等级使用", "教学案例与真实临床数据明确区分"],
            ["不提供个人诊断、处方或治疗建议", "高风险结论必须有明确来源与适用范围", "病例去标识化"],
            ["机制链条的方向和尺度一致", "病例推理说明支持证据、反证和待补信息", "基础教学不越过专业权限"],
            {
                "concept": {"teacher_activity": "沿尺度连接结构、功能、机制和调节", "student_activity": "解释机制链并预测环节改变的后果", "expected_output": "尺度一致的机制解释"},
                "example": {"teacher_activity": "提供去标识化案例、证据和限制", "student_activity": "整理时间线、权衡证据并提出待补信息", "expected_output": "有边界的案例推理"},
                "feedback": {"teacher_activity": "指出过度推断、证据遗漏和权限边界", "student_activity": "降低结论强度并补充证据需求", "expected_output": "修订后的证据判断"},
            },
        ),
        "profiles": {
            "life_science": {"label": "生命科学", "keywords": ["生物学", "生命科学", "遗传", "细胞", "生态"], "canonical_artifacts": ["结构功能图", "机制模型", "实验设计", "进化或生态证据链"]},
            "clinical_medicine": {"label": "临床医学教学", "keywords": ["临床", "诊断学", "内科学", "外科学", "病例"], "professional_actions": ["采集信息", "形成问题表征", "提出鉴别", "权衡证据", "识别红旗与转诊边界"], "safety_boundaries": ["教学推理不能替代真实诊疗", "不编造患者信息、检查结果或治疗结论"]},
            "nursing": {"label": "护理学", "keywords": ["护理", "基础护理", "护理评估"], "professional_actions": ["整体评估", "识别护理问题", "制定目标", "实施与沟通", "观察反应", "记录评价"], "canonical_artifacts": ["护理评估", "护理计划", "操作核对单", "交接与健康教育记录"]},
            "pharmacy": {"label": "药学", "keywords": ["药学", "药理", "药剂", "药物化学"], "professional_actions": ["连接结构与作用", "解释药代药效", "识别相互作用", "评价证据", "进行用药安全教育"], "safety_boundaries": ["不面向个人给出具体用药调整", "剂量与适应证必须有权威依据"]},
        },
    },
    "humanities_social": {
        "label": "人文社科",
        "base": _standard(
            "在材料、语境、概念、因果和不同解释之间形成可辩护判断。",
            ["界定问题", "辨析材料", "还原语境", "比较解释", "形成论证", "回应异议"],
            ["文本细读", "史料辨析", "概念分析", "论证图", "案例比较", "研究短文"],
            ["准确引用材料", "概念使用一致", "因果链有证据", "能够回应反例和异议"],
            ["把观点写成事实", "脱离语境引用", "只列立场不形成论证", "用单一原因解释复杂现象"],
            ["一手材料与二手解释分开", "争议问题呈现主要证据与代表性解释"],
            ["不伪造引文、史料、判例或统计", "敏感议题保持事实、观点和推断边界"],
            ["主张、证据、推理和限定语完整", "异议推动判断修订", "材料引用可以追溯"],
            {
                "example": {"teacher_activity": "提供共同材料、语境和辨析问题", "student_activity": "标注材料、比较解释并提出初步主张", "expected_output": "材料依据与可辩护初判"},
                "reasoning": {"teacher_activity": "追问主张、证据、前提和因果链", "student_activity": "形成论证并说明限定条件", "expected_output": "完整论证链"},
                "counterexample": {"teacher_activity": "引入异议、反例或另一语境", "student_activity": "回应异议并修正原判断", "expected_output": "修订后的判断与边界"},
            },
        ),
        "profiles": {
            "history_textual": {"label": "历史与文献", "keywords": ["历史", "古代史", "近代史", "史学", "文献学", "古典文献"], "professional_actions": ["辨析史料", "还原语境", "建立时序", "比较解释", "形成有限结论"]},
            "literature_language": {"label": "文学与文化研究", "keywords": ["文学", "汉语言", "文化研究", "写作"], "canonical_artifacts": ["文本细读", "修辞分析", "作品比较", "有材料依据的阐释"]},
            "philosophy_law": {"label": "哲学与法学", "keywords": ["哲学", "伦理学", "法学", "法律", "法理"], "professional_actions": ["澄清概念", "重构论证", "识别规范前提", "适用规则", "处理反例与冲突"]},
            "social_science": {"label": "社会科学", "keywords": ["社会学", "政治学", "公共管理", "心理学", "传播学"], "professional_actions": ["操作化概念", "比较理论", "分析资料", "评估因果", "解释机制与边界"], "safety_boundaries": ["群体统计不直接推断个人", "相关、机制和因果证据分开"]},
        },
    },
    "language_learning": {
        "label": "语言学习",
        "base": _standard(
            "在明确对象、目的和语境中，通过输入、注意、输出、反馈与再次表现形成沟通能力。",
            ["理解输入", "注意形式与功能", "受控练习", "真实表达", "互动协商", "反馈后再次表现"],
            ["听读任务", "语料观察", "口头或书面产出", "互动记录", "修改稿", "表现量规"],
            ["理解关键信息", "表达准确且得体", "完成真实交际目的", "反馈后明显改进"],
            ["把背词表当沟通能力", "只讲语法不产生输出", "纠错后没有再次表现"],
            ["真实或教学化语料标明语境和难度", "语言规则与具体语料用法相互验证"],
            ["不虚构文化事实或把单一用法写成唯一规范", "涉及身份与文化差异时避免刻板印象"],
            ["每讲必须有真实输出", "输入、目标表达和反馈标准一致", "纠错具体且保留表达意图"],
            {
                "concept": {"teacher_activity": "从语料引导学习者注意形式、意义和语用条件", "student_activity": "比较语料并归纳使用规律", "expected_output": "带语境的语言规律"},
                "activity": {"teacher_activity": "给出对象、目的、情境和成功标准", "student_activity": "完成真实口头、书面或互动表达", "expected_output": "可理解、准确、得体的语言产出"},
                "feedback": {"teacher_activity": "针对意义、组织、准确性和得体性给反馈", "student_activity": "修改并再次完成同类沟通", "expected_output": "反馈后的改进表现"},
            },
        ),
        "profiles": {
            "general_language": {"label": "通用语言能力", "keywords": ["大学英语", "英语", "日语", "法语", "德语", "汉语国际教育"]},
            "academic_language": {"label": "学术语言", "keywords": ["学术英语", "论文写作", "学术写作", "学术交流"], "canonical_artifacts": ["摘要", "论证段落", "文献综合", "学术汇报", "同行反馈"]},
            "professional_language": {"label": "专门用途语言", "keywords": ["商务英语", "医学英语", "法律英语", "科技英语"], "professional_actions": ["分析职业情境", "提取体裁结构", "选择专业表达", "完成职业沟通", "按标准修订"]},
        },
    },
    "business_career": {
        "label": "商业与职业技能",
        "base": _standard(
            "在角色、目标、约束、数据和相关方中作出可执行、可复盘的判断。",
            ["诊断场景", "识别目标与约束", "选择工具", "形成方案", "沟通决策", "用指标复盘"],
            ["问题定义", "分析模型", "决策备忘录", "方案或原型", "汇报", "复盘记录"],
            ["假设透明", "数据与判断对应", "方案可执行", "能回应相关方异议", "结果可衡量"],
            ["先套框架再找问题", "把活动完成当成果合格", "忽略利益相关方和执行约束"],
            ["企业事实、案例设定和教学假设分开", "数据口径、时间和来源明确"],
            ["不把教学案例写成真实公司事实", "财务、法律与人事建议说明适用边界"],
            ["问题、证据、方案和指标相互对应", "取舍与风险显式", "成果满足真实角色和格式要求"],
            {
                "orientation": {"teacher_activity": "明确角色、目标、相关方、约束和待决问题", "student_activity": "形成问题定义并识别缺失信息", "expected_output": "可行动的问题表述"},
                "application": {"teacher_activity": "提供数据、工具边界和决策标准", "student_activity": "分析选项、作出取舍并提交方案", "expected_output": "有依据的决策或工作成果"},
                "feedback": {"teacher_activity": "从可行性、证据、风险和沟通效果评审", "student_activity": "回应质疑、修改方案并更新指标", "expected_output": "可执行的修订方案"},
            },
        ),
        "profiles": {
            "management_strategy": {"label": "管理与战略", "keywords": ["管理学", "战略管理", "组织行为", "创新创业"], "canonical_artifacts": ["战略诊断", "组织方案", "决策备忘录", "实施路线图"]},
            "marketing": {"label": "市场营销", "keywords": ["市场营销", "品牌", "消费者行为", "电商"], "professional_actions": ["识别市场问题", "分析用户与竞争", "形成定位", "设计行动", "验证指标"]},
            "finance_accounting": {"label": "金融与会计", "keywords": ["金融", "会计", "财务管理", "投资", "审计"], "professional_actions": ["核对口径", "分析报表或现金流", "建立估值或决策模型", "检验敏感性", "说明风险"], "safety_boundaries": ["教学分析不是投资建议", "数字、期间、币种与会计口径必须一致"]},
            "career_practice": {"label": "职业实践", "keywords": ["职业规划", "就业", "沟通", "谈判", "领导力"], "canonical_artifacts": ["岗位任务", "沟通脚本", "作品集", "情境演练", "行动复盘"]},
        },
    },
}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if key in {"label", "keywords"}:
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = {**deepcopy(result[key]), **deepcopy(value)}
        elif isinstance(value, list) and isinstance(result.get(key), list):
            result[key] = list(dict.fromkeys([*result[key], *deepcopy(value)]))
        else:
            result[key] = deepcopy(value)
    return result


def _score(text: str, keywords: list[str]) -> int:
    normalized = str(text or "").lower().replace(" ", "")
    return sum(max(1, len(word)) for word in keywords if word.lower().replace(" ", "") in normalized)


def resolve_subject_standard_pack(
    subject_type: str,
    *,
    discipline_hint: str = "",
    discipline_profile: str = "",
) -> dict[str, Any]:
    requested = str(subject_type or "auto").strip().lower()
    family_id = requested if requested in SUBJECT_STANDARD_PACKS else ""
    profile_id = ""
    if discipline_profile:
        for candidate_family, family in SUBJECT_STANDARD_PACKS.items():
            if discipline_profile in family["profiles"]:
                family_id, profile_id = candidate_family, discipline_profile
                break
    if not family_id:
        family_scores = [
            (
                max((_score(discipline_hint, profile.get("keywords") or []) for profile in family["profiles"].values()), default=0),
                candidate_family,
            )
            for candidate_family, family in SUBJECT_STANDARD_PACKS.items()
        ]
        best_score, family_id = max(family_scores)
        if best_score <= 0:
            family_id = "general"
    family = SUBJECT_STANDARD_PACKS[family_id]
    if not profile_id:
        profile_scores = [
            (_score(discipline_hint, profile.get("keywords") or []), candidate)
            for candidate, profile in family["profiles"].items()
        ]
        best_score, candidate = max(profile_scores)
        profile_id = candidate if best_score > 0 else next(iter(family["profiles"]))
    profile = family["profiles"][profile_id]
    resolved = _merge(family["base"], profile)
    resolved["artifact_language"] = {
        **ARTIFACT_LANGUAGE,
        **SUBJECT_ARTIFACT_LANGUAGE[family_id],
        **deepcopy(profile.get("artifact_language") or {}),
    }
    resolved.update({
        "schema_version": SUBJECT_STANDARD_PACK_VERSION,
        "subject_type": family_id,
        "subject_type_label": family["label"],
        "discipline_profile_id": profile_id,
        "discipline_profile_label": profile["label"],
        "resolved_from": "discipline_profile" if discipline_profile else "discipline_hint" if _score(discipline_hint, profile.get("keywords") or []) else "subject_type_default",
    })
    return resolved


def validate_subject_standard_registry() -> list[str]:
    required = {
        "epistemic_method", "professional_actions", "canonical_artifacts",
        "evidence_patterns", "common_misconceptions", "source_policy",
        "safety_boundaries", "artifact_language", "quality_rules", "block_recipes",
    }
    issues: list[str] = []
    ids: set[str] = set()
    for family_id, family in SUBJECT_STANDARD_PACKS.items():
        missing = required.difference(family.get("base") or {})
        if missing:
            issues.append(f"{family_id}:missing:{','.join(sorted(missing))}")
        for profile_id, profile in (family.get("profiles") or {}).items():
            if profile_id in ids:
                issues.append(f"duplicate_profile:{profile_id}")
            ids.add(profile_id)
            if not str(profile.get("label") or "").strip():
                issues.append(f"{family_id}:{profile_id}:label_missing")
    return issues


__all__ = [
    "SUBJECT_ARTIFACT_LANGUAGE",
    "SUBJECT_STANDARD_PACKS",
    "SUBJECT_STANDARD_PACK_VERSION",
    "resolve_subject_standard_pack",
    "validate_subject_standard_registry",
]
