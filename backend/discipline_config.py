"""
Discipline Configuration System - 学科配置系统

基于布鲁姆教育目标分类学和UNESCO国际教育标准分类，
为不同学科类型提供差异化的内容生成策略。

核心设计原则：
1. 每个学科类型有独特的内容结构模板
2. 质量验证标准因学科而异
3. 提示词策略动态适配
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
from enum import Enum
import re


class DisciplineType(str, Enum):
    """学科类型枚举"""
    NATURAL_SCIENCE = "natural_science"
    ENGINEERING = "engineering"
    HUMANITIES = "humanities"
    SOCIAL_SCIENCE = "social_science"
    APPLIED_SKILL = "applied_skill"
    COMMUNICATION = "communication"


@dataclass
class ContentSection:
    """内容板块定义"""
    name: str
    emoji: str
    required: bool = True
    min_length: int = 50
    validation_hints: List[str] = field(default_factory=list)


@dataclass
class DisciplineConfig:
    """学科配置"""
    name: str
    name_cn: str
    keywords: List[str]
    core_features: List[str]
    content_sections: List[ContentSection]
    quality_criteria: Dict[str, any]
    prompt_hint: str


DISCIPLINE_CONFIGS: Dict[DisciplineType, DisciplineConfig] = {
    DisciplineType.NATURAL_SCIENCE: DisciplineConfig(
        name="Natural Science",
        name_cn="自然科学",
        keywords=[
            "数学", "物理", "化学", "生物", "天文", "地理", "地质",
            "mathematics", "physics", "chemistry", "biology", "astronomy",
            "微积分", "代数", "几何", "力学", "热力学", "电磁学", "量子",
            "定理", "证明", "推导", "公式", "实验"
        ],
        core_features=[
            "公理化体系",
            "演绎推理",
            "实验验证",
            "数学建模"
        ],
        content_sections=[
            ContentSection("核心定义与物理意义", "💡", min_length=100),
            ContentSection("定理陈述与证明推导", "🔍", min_length=200, 
                          validation_hints=["必须包含完整证明或推导过程"]),
            ContentSection("算法步骤与计算方法", "🛠️", min_length=100),
            ContentSection("可视化图解", "🎨", min_length=50,
                          validation_hints=["必须包含Mermaid图或数学图表"]),
            ContentSection("工程与科研应用", "🏭", min_length=100),
            ContentSection("推导题与证明题", "✅", min_length=50)
        ],
        quality_criteria={
            "formula_density": {"min": 0.1, "max": 0.5},
            "proof_required": True,
            "visualization_required": True,
            "min_derivation_steps": 3
        },
        prompt_hint="侧重：定理证明、公式推导、数学建模、实验验证"
    ),
    
    DisciplineType.ENGINEERING: DisciplineConfig(
        name="Engineering & Technology",
        name_cn="工程技术",
        keywords=[
            "计算机", "编程", "软件", "算法", "数据结构", "网络", "数据库",
            "电子", "机械", "土木", "建筑", "化工", "材料",
            "computer", "programming", "software", "algorithm", "data structure",
            "java", "python", "javascript", "react", "vue", "node",
            "机器学习", "深度学习", "人工智能", "AI", "ML",
            "架构", "设计模式", "系统", "工程"
        ],
        core_features=[
            "理论实践结合",
            "设计导向",
            "工程思维",
            "最佳实践"
        ],
        content_sections=[
            ContentSection("核心概念与技术背景", "💡", min_length=100),
            ContentSection("技术原理与底层机制", "🔍", min_length=150),
            ContentSection("代码实现与架构设计", "🛠️", min_length=200,
                          validation_hints=["必须包含代码示例或架构图"]),
            ContentSection("可视化图解", "🎨", min_length=50),
            ContentSection("工程实践与最佳实践", "🏭", min_length=100),
            ContentSection("思考与实战挑战", "✅", min_length=50)
        ],
        quality_criteria={
            "code_required": True,
            "architecture_diagram": True,
            "best_practices": True,
            "min_code_lines": 5
        },
        prompt_hint="侧重：架构设计、代码实现、工程实践、性能优化"
    ),
    
    DisciplineType.HUMANITIES: DisciplineConfig(
        name="Humanities",
        name_cn="人文科学",
        keywords=[
            "哲学", "历史", "文学", "艺术", "语言", "宗教", "文化",
            "philosophy", "history", "literature", "art", "language", "religion",
            "存在主义", "现象学", "辩证法", "形而上学", "美学",
            "诠释", "文本", "批判", "思想",
            # 语言学习类
            "语法", "grammar", "英语", "english", "日语", "japanese", "法语", "french",
            "德语", "german", "西班牙语", "spanish", "韩语", "korean", "俄语", "russian",
            "词汇", "vocabulary", "写作", "writing", "阅读", "reading", "口语", "speaking",
            "听力", "listening", "翻译", "translation", "语言学", "linguistics",
            "句法", "syntax", "语义", "semantics", "语用", "pragmatics", "修辞", "rhetoric"
        ],
        core_features=[
            "诠释学方法",
            "批判性思维",
            "文本分析",
            "思想演进",
            "语言规则系统",
            "文化语境理解"
        ],
        content_sections=[
            ContentSection("核心概念与定义", "💡", min_length=100),
            ContentSection("规则解析与用法说明", "🔍", min_length=200,
                          validation_hints=["必须包含清晰的规则说明和具体用法"]),
            ContentSection("实例分析与案例展示", "🛠️", min_length=150,
                          validation_hints=["必须包含具体的例子和应用场景"]),
            ContentSection("常见错误与注意事项", "⚠️", min_length=100),
            ContentSection("练习与应用", "✏️", min_length=100),
            ContentSection("拓展与深化", "🌟", min_length=50)
        ],
        quality_criteria={
            "argument_chain": True,
            "critical_thinking": True,
            "historical_context": False,
            "avoid_over_formalization": True,
            "examples_required": True,
            "practical_application": True
        },
        prompt_hint="侧重：概念清晰、规则明确、实例丰富、应用导向。语言类课程需包含具体例句和用法说明"
    ),
    
    DisciplineType.SOCIAL_SCIENCE: DisciplineConfig(
        name="Social Science",
        name_cn="社会科学",
        keywords=[
            "社会学", "心理学", "经济学", "政治", "人类学", "传播", "教育",
            "sociology", "psychology", "economics", "politics", "anthropology",
            "社会", "行为", "认知", "市场", "政策", "组织", "管理",
            "统计", "调查", "实验", "案例研究"
        ],
        core_features=[
            "实证研究",
            "统计分析",
            "理论模型",
            "案例研究"
        ],
        content_sections=[
            ContentSection("核心概念与理论框架", "💡", min_length=100),
            ContentSection("理论机制与实证证据", "🔍", min_length=150),
            ContentSection("研究方法与数据分析", "🛠️", min_length=100),
            ContentSection("可视化图解", "🎨", min_length=50),
            ContentSection("现实应用与案例研究", "🏭", min_length=100),
            ContentSection("思考与研究设计", "✅", min_length=50)
        ],
        quality_criteria={
            "empirical_evidence": True,
            "statistical_analysis": False,
            "case_study": True,
            "theoretical_framework": True
        },
        prompt_hint="侧重：理论模型、实证证据、研究方法、案例分析"
    ),
    
    DisciplineType.APPLIED_SKILL: DisciplineConfig(
        name="Applied Skill",
        name_cn="应用技能",
        keywords=[
            "摄影", "调音", "烹饪", "驾驶", "乐器", "绘画", "书法",
            "photography", "cooking", "driving", "instrument", "painting",
            "操作", "练习", "技巧", "手法", "步骤", "流程",
            "剪辑", "设计", "制作", "手工"
        ],
        core_features=[
            "操作性强",
            "肌肉记忆",
            "实践导向",
            "可量化评估"
        ],
        content_sections=[
            ContentSection("技能定义与学习价值", "💡", min_length=80),
            ContentSection("技能原理与底层机制", "🔍", min_length=100),
            ContentSection("操作步骤与练习任务", "🛠️", min_length=200,
                          validation_hints=["必须包含具体操作步骤和练习任务"]),
            ContentSection("流程图与评分标准", "🎨", min_length=50),
            ContentSection("实战案例与经验分享", "🏭", min_length=100),
            ContentSection("自我评估与进阶路径", "✅", min_length=50)
        ],
        quality_criteria={
            "step_by_step": True,
            "practice_task": True,
            "assessment_criteria": True,
            "min_steps": 3
        },
        prompt_hint="侧重：操作步骤、练习任务、评估标准、经验技巧"
    ),
    
    DisciplineType.COMMUNICATION: DisciplineConfig(
        name="Communication & Expression",
        name_cn="表达沟通",
        keywords=[
            "演讲", "辩论", "写作", "谈判", "沟通", "表达", "口才",
            "public speaking", "debate", "writing", "negotiation", "communication",
            "presentation", "汇报", "演示", "说服", "论证",
            "赛制", "规则", "技巧", "策略"
        ],
        core_features=[
            "互动性强",
            "情境依赖",
            "软技能",
            "示范导向"
        ],
        content_sections=[
            ContentSection("技能定义与应用场景", "💡", min_length=80),
            ContentSection("核心原理与心理机制", "🔍", min_length=100),
            ContentSection("示范材料与情境模拟", "🛠️", min_length=200,
                          validation_hints=["必须包含示范材料（如演讲稿片段、辩论论点展开）"]),
            ContentSection("流程图与评分维度", "🎨", min_length=50),
            ContentSection("真实案例与高水平示范", "🏭", min_length=100),
            ContentSection("实践任务与自我评估", "✅", min_length=50)
        ],
        quality_criteria={
            "demo_material": True,
            "scenario_simulation": True,
            "scoring_rubric": True,
            "real_case": True
        },
        prompt_hint="侧重：示范材料、情境模拟、评分标准、实战案例"
    )
}


def detect_discipline_type(course_name: str, keyword: str = "") -> DisciplineType:
    """
    智能检测学科类型（加权评分机制）
    
    Args:
        course_name: 课程名称
        keyword: 额外关键词
        
    Returns:
        检测到的学科类型
    """
    text = f"{course_name} {keyword}".lower()
    
    scores = {}
    for dtype, config in DISCIPLINE_CONFIGS.items():
        score = sum(1 for kw in config.keywords if kw.lower() in text)
        scores[dtype] = score
    
    if all(s == 0 for s in scores.values()):
        return DisciplineType.NATURAL_SCIENCE
    
    return max(scores, key=scores.get)


def get_discipline_config(discipline_type: DisciplineType) -> DisciplineConfig:
    """获取学科配置"""
    return DISCIPLINE_CONFIGS.get(discipline_type, DISCIPLINE_CONFIGS[DisciplineType.NATURAL_SCIENCE])


def get_content_structure_prompt(discipline_type: DisciplineType) -> str:
    """生成内容结构提示词"""
    config = get_discipline_config(discipline_type)
    
    sections_str = "\n".join([
        f"- ### {section.emoji} {section.name}" + 
        (f"（{'必填' if section.required else '选填'}，最少{section.min_length}字）" if section.required else "")
        for section in config.content_sections
    ])
    
    return f"""## 内容结构（{config.name_cn}）

{sections_str}

{config.prompt_hint}"""


def get_quality_criteria_prompt(discipline_type: DisciplineType) -> str:
    """生成质量标准提示词"""
    config = get_discipline_config(discipline_type)
    
    criteria_list = []
    for key, value in config.quality_criteria.items():
        if isinstance(value, bool) and value:
            criteria_list.append(f"- {key.replace('_', ' ').title()}: Required")
        elif isinstance(value, dict):
            criteria_list.append(f"- {key}: {value}")
    
    if criteria_list:
        return f"""## 质量标准\n{chr(10).join(criteria_list)}"""
    return ""


__all__ = [
    "DisciplineType",
    "DisciplineConfig",
    "ContentSection",
    "DISCIPLINE_CONFIGS",
    "detect_discipline_type",
    "get_discipline_config",
    "get_content_structure_prompt",
    "get_quality_criteria_prompt"
]
