"""
专业级提示词模板系统 V5

核心设计原则：
1. 难度适配：根据难度级别调整内容深度
2. 受众适配：根据目标受众调整表达方式
3. 智能篇幅：根据内容类型动态控制篇幅
4. 质量优先：限制是指导而非硬性约束
5. 学科定制：不同学科有不同的内容结构
"""

from typing import Dict, Optional, List
from dataclasses import dataclass
from enum import Enum

from discipline_config import DisciplineType, get_discipline_config, DisciplineConfig

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.prompt_config import DifficultyLevel


class TargetAudience(Enum):
    """目标受众"""
    HIGH_SCHOOL = "高中生"       # 高中生：通俗化，生活化案例
    UNDERGRADUATE = "大学生"     # 大学生：学术化，专业案例
    GRADUATE = "研究生"          # 研究生：研究导向，前沿案例
    PROFESSIONAL = "从业者"      # 从业者：实战导向，行业案例


@dataclass
class ContentGuidelines:
    """内容指导方针"""
    min_words: int
    max_words: int
    recommended_words: int
    example_count: int
    depth_level: str
    terminology_level: str
    case_study_type: str


class PromptEngineV5:
    """提示词引擎 V5"""

    DIFFICULTY_GUIDELINES = {
        DifficultyLevel.BEGINNER: {
            "depth": "基础概念为主，避免复杂推导",
            "terminology": "通俗解释专业术语，必要时用类比",
            "structure": "概念→例子→简单应用",
            "emphasis": "理解为主，建立直观认知"
        },
        DifficultyLevel.INTERMEDIATE: {
            "depth": "深入原理，适度推导证明",
            "terminology": "使用专业术语，首次出现时解释",
            "structure": "原理→推导→应用→拓展",
            "emphasis": "理解原理，掌握方法"
        },
        DifficultyLevel.ADVANCED: {
            "depth": "深入理论，完整推导证明",
            "terminology": "专业术语，可引用原始文献",
            "structure": "理论基础→严格推导→前沿应用→研究展望",
            "emphasis": "深入理解，能够创新应用"
        }
    }

    AUDIENCE_GUIDELINES = {
        TargetAudience.HIGH_SCHOOL: {
            "tone": "亲切友好，鼓励探索",
            "examples": "生活化案例，贴近日常经验",
            "complexity": "避免过于抽象，多用直观图示",
            "engagement": "设置思考问题，激发兴趣"
        },
        TargetAudience.UNDERGRADUATE: {
            "tone": "严谨专业，逻辑清晰",
            "examples": "专业案例，结合实际应用",
            "complexity": "适度抽象，培养专业思维",
            "engagement": "设置练习题，巩固知识"
        },
        TargetAudience.GRADUATE: {
            "tone": "学术严谨，深入分析",
            "examples": "研究案例，前沿应用",
            "complexity": "高度抽象，理论深度",
            "engagement": "设置研究问题，引导探索"
        },
        TargetAudience.PROFESSIONAL: {
            "tone": "实用导向，直接有效",
            "examples": "行业案例，最佳实践",
            "complexity": "聚焦实战，解决实际问题",
            "engagement": "设置实战任务，学以致用"
        }
    }

    DISCIPLINE_LENGTH_GUIDELINES = {
        DisciplineType.NATURAL_SCIENCE: {
            "base_words": 1000,
            "formula_weight": 1.3,
            "reason": "需要完整的推导过程"
        },
        DisciplineType.ENGINEERING: {
            "base_words": 1200,
            "formula_weight": 1.2,
            "reason": "需要代码示例和架构说明"
        },
        DisciplineType.HUMANITIES: {
            "base_words": 1500,
            "formula_weight": 1.0,
            "reason": "需要充分的论述和引用"
        },
        DisciplineType.SOCIAL_SCIENCE: {
            "base_words": 1300,
            "formula_weight": 1.0,
            "reason": "需要案例分析和理论框架"
        },
        DisciplineType.APPLIED_SKILL: {
            "base_words": 1000,
            "formula_weight": 1.0,
            "reason": "需要步骤说明和操作指导"
        },
        DisciplineType.COMMUNICATION: {
            "base_words": 1100,
            "formula_weight": 1.0,
            "reason": "需要场景模拟和技巧说明"
        }
    }

    def __init__(self):
        pass

    COGNITIVE_RHYTHM_TEMPLATE = """
## 🎵 四拍认知节奏结构（严格执行）

**核心理念**：好的教学不是信息罗列，而是有节奏的认知引导

### 第一拍：直观感知（约 150-200 字）
**目标**：让学习者感受到"为什么需要这个概念"
- ✅ 必须：用一个**具体问题**或**真实场景**引入
- ✅ 必须：展示该概念能解决什么实际困难
- ❌ 禁止：直接抛出抽象定义
- ❌ 禁止：使用"XX 是指..."的词典式开头

### 第二拍：抽象提炼（约 200-300 字）
**目标**：形式化定义和核心性质
- ✅ 必须：给出精确的数学定义或形式化描述
- ✅ 必须：解释定义中每个符号/术语的含义
- ✅ 必须：说明核心性质/定理（至少 2-3 个）

### 第三拍：操作演练（约 300-400 字）
**目标**：详细计算/推导步骤，让学习者掌握"怎么做"
- ✅ 必须：展示完整的计算/推导过程
- ✅ 必须：每一步都说明**理由**（为什么可以这样做）
- ✅ 必须：指出**常见错误**及原因分析
- ✅ 必须：提供**决策口诀**（"看到 X 特征，就用 Y 方法"）

### 第四拍：迁移应用（约 200-300 字）
**目标**：解决实际问题，展示从"知道"到"学会"
- ✅ 必须：案例**直接使用**本节方法论解决具体问题
- ✅ 必须：完整展示全链路：识别问题→选择方法→计算/推导→结果解读
"""

    DIFFICULTY_STRATEGY_BEGINNER = """
## 📚 入门级展开策略
**目标受众**：初学者，第一次接触该概念
**核心原则**：直观优先，减少抽象，建立信心
**四拍时间分配**：第一拍30%、第二拍20%、第三拍40%、第四拍10%
**公式密度**：0-10%
"""

    DIFFICULTY_STRATEGY_INTERMEDIATE = """
## 📖 进阶级展开策略
**目标受众**：有一定基础，想系统掌握该概念
**核心原则**：四拍完整，平衡理论与应用
**四拍时间分配**：第一拍20%、第二拍30%、第三拍30%、第四拍20%
**公式密度**：10-30%
"""

    DIFFICULTY_STRATEGY_ADVANCED = """
## 📕 高级展开策略
**目标受众**：有扎实基础，追求深度理解
**核心原则**：抽象主导，强调证明和复杂应用
**四拍时间分配**：第一拍10%、第二拍30%、第三拍20%、第四拍40%
**公式密度**：30-50%
"""

    VISUALIZATION_REQUIREMENTS = """
## ⚠️ 可视化强制要求
### 绝对禁止
- ❌ "图注：..." 或 "（此处应有图）" 等占位符
- ❌ 留空不写
- ❌ 用纯文字替代图表

### 必须包含
1. **Mermaid 流程图**：展示判断逻辑/依赖关系/流程分支
2. **Markdown 表格**：概念对比表、参数说明表、案例对照表

### 决策口诀（必须提供）
"看到 X 特征，就用 Y 方法"

### 反面案例（必须提供）
常见错误及原因分析
"""

    def get_content_guidelines(
        self,
        discipline: DisciplineType,
        difficulty: DifficultyLevel,
        audience: TargetAudience,
        section_complexity: str = "medium"
    ) -> ContentGuidelines:
        """获取内容指导方针"""
        base = self.DISCIPLINE_LENGTH_GUIDELINES.get(discipline, self.DISCIPLINE_LENGTH_GUIDELINES[DisciplineType.NATURAL_SCIENCE])
        
        base_words = base["base_words"]
        
        difficulty_multiplier = {
            DifficultyLevel.BEGINNER: 0.8,
            DifficultyLevel.INTERMEDIATE: 1.0,
            DifficultyLevel.ADVANCED: 1.3
        }
        
        complexity_multiplier = {
            "simple": 0.7,
            "medium": 1.0,
            "complex": 1.4
        }
        
        final_words = int(base_words * difficulty_multiplier[difficulty] * complexity_multiplier.get(section_complexity, 1.0))
        
        example_count = {
            DifficultyLevel.BEGINNER: 3,
            DifficultyLevel.INTERMEDIATE: 2,
            DifficultyLevel.ADVANCED: 2
        }
        
        return ContentGuidelines(
            min_words=int(final_words * 0.7),
            max_words=int(final_words * 1.5),
            recommended_words=final_words,
            example_count=example_count[difficulty],
            depth_level=self.DIFFICULTY_GUIDELINES[difficulty]["depth"],
            terminology_level=self.DIFFICULTY_GUIDELINES[difficulty]["terminology"],
            case_study_type=self.AUDIENCE_GUIDELINES[audience]["examples"]
        )

    def build_outline_prompt(
        self,
        topic: str,
        discipline: DisciplineType,
        difficulty: DifficultyLevel,
        audience: TargetAudience,
        config: DisciplineConfig
    ) -> str:
        """构建课程大纲生成提示词"""
        
        difficulty_guide = self.DIFFICULTY_GUIDELINES[difficulty]
        audience_guide = self.AUDIENCE_GUIDELINES[audience]
        
        chapter_count = {
            DifficultyLevel.BEGINNER: "5-7",
            DifficultyLevel.INTERMEDIATE: "6-8",
            DifficultyLevel.ADVANCED: "7-10"
        }
        
        section_count = {
            DifficultyLevel.BEGINNER: "2-3",
            DifficultyLevel.INTERMEDIATE: "3-4",
            DifficultyLevel.ADVANCED: "3-5"
        }
        
        return f"""## 角色
你是一位专业的{config.name_cn}教育专家，擅长为{audience.value}设计课程。

## 任务
为「{topic}」设计完整的课程大纲。

## 目标受众
{audience.value}
- 表达风格：{audience_guide["tone"]}
- 案例类型：{audience_guide["examples"]}
- 复杂度：{audience_guide["complexity"]}

## 难度定位
{difficulty.value}级别
- 内容深度：{difficulty_guide["depth"]}
- 术语使用：{difficulty_guide["terminology"]}
- 内容结构：{difficulty_guide["structure"]}
- 学习重点：{difficulty_guide["emphasis"]}

## 学科特点
{config.prompt_hint}

## 设计要求
1. 生成 {chapter_count[difficulty]} 个章节
2. 每章 {section_count[difficulty]} 个小节
3. 章节标题要体现知识递进
4. 小节标题要具体、有层次
5. 为每个小节标注复杂度（simple/medium/complex）
6. 为每个小节列出 2-3 个关键点

## 输出格式
```json
{{
  "course_title": "课程名称",
  "learning_objectives": ["目标1", "目标2", "目标3"],
  "prerequisites": ["前置知识1", "前置知识2"],
  "chapters": [
    {{
      "chapter_number": 1,
      "title": "章节名",
      "learning_focus": "本章学习重点",
      "sections": [
        {{
          "section_number": "1.1", 
          "title": "小节名", 
          "key_points": ["要点1", "要点2"],
          "complexity": "simple/medium/complex"
        }}
      ]
    }}
  ]
}}
```

请输出完整的课程大纲JSON："""

    def build_content_prompt(
        self,
        section_title: str,
        section_number: str,
        key_points: List[str],
        course_topic: str,
        discipline: DisciplineType,
        difficulty: DifficultyLevel,
        audience: TargetAudience,
        knowledge_context: str,
        guidelines: ContentGuidelines,
        config: DisciplineConfig,
        prerequisite_context: str = "无",
        learner_weakness: str = "无"
    ) -> str:
        """构建内容生成提示词（P0 升级版：四拍认知节奏）"""

        difficulty_guide = self.DIFFICULTY_GUIDELINES[difficulty]
        audience_guide = self.AUDIENCE_GUIDELINES[audience]

        difficulty_strategy = {
            DifficultyLevel.BEGINNER: self.DIFFICULTY_STRATEGY_BEGINNER,
            DifficultyLevel.INTERMEDIATE: self.DIFFICULTY_STRATEGY_INTERMEDIATE,
            DifficultyLevel.ADVANCED: self.DIFFICULTY_STRATEGY_ADVANCED
        }.get(difficulty, self.DIFFICULTY_STRATEGY_INTERMEDIATE)

        length_guide = f"""## 篇幅指导
- 建议字数：{guidelines.recommended_words}字左右
- 可接受范围：{guidelines.min_words}-{guidelines.max_words}字
- 注意：内容质量优先于字数，如有必要可超出范围"""

        return f"""## 角色
你是一位专业的{config.name_cn}教育内容撰写专家。

## 任务
为「{section_number} {section_title}」撰写详细教学内容。

## 课程背景
- 课程主题：{course_topic}
- 本节重点：{', '.join(key_points)}

## 目标受众
{audience.value}
- 表达风格：{audience_guide["tone"]}
- 案例类型：{audience_guide["examples"]}

## 难度定位
{difficulty.value}级别
- 内容深度：{difficulty_guide["depth"]}
- 术语使用：{difficulty_guide["terminology"]}

## 学科要求
{config.prompt_hint}

## 前置知识上下文
{prerequisite_context}

## 学习者薄弱点
{learner_weakness}

{length_guide}

## 🎵 核心要求：四拍认知节奏结构
{difficulty_strategy}

{COGNITIVE_RHYTHM_TEMPLATE}

## ⚠️ 可视化强制要求
{self.VISUALIZATION_REQUIREMENTS}

## 撰写要求
1. **必须使用四拍认知节奏结构**组织内容
2. **必须包含决策口诀**（"看到 X 特征，就用 Y 方法"）
3. **必须包含反面案例**（常见错误及原因分析）
4. 概念首次出现时用 **概念名**：定义 格式给出明确定义
5. 提供 {guidelines.example_count} 个以上的新案例（禁止重复已用案例）
6. 数学公式用 $...$ 包裹，独立公式用 $$...$$
7. 代码块指定语言类型
8. 使用清晰的标题层级（##、###）
9. **必须包含 Mermaid 图表**，禁止留空或使用占位符

## 质量优先原则
- 如果内容需要更多篇幅才能讲清楚，请毫不犹豫地扩展
- 如果某个概念需要更多解释，请详细展开
- 质量永远优先于篇幅限制

请开始撰写：「{section_number} {section_title}」"""

    def _get_structure_guide(self, discipline: DisciplineType, difficulty: DifficultyLevel) -> str:
        """获取内容结构指导"""
        
        structures = {
            DisciplineType.NATURAL_SCIENCE: {
                DifficultyLevel.BEGINNER: """建议结构：
1. 引入：生活实例或直观现象
2. 概念定义：用通俗语言解释
3. 简单应用：基础计算或判断
4. 小结：关键要点回顾""",
                DifficultyLevel.INTERMEDIATE: """建议结构：
1. 问题引入：从已知引出未知
2. 概念定义：严谨的数学定义
3. 原理推导：逻辑推理过程
4. 典型例题：应用方法演示
5. 拓展思考：延伸问题""",
                DifficultyLevel.ADVANCED: """建议结构：
1. 理论背景：问题的历史与意义
2. 严格定义：数学语言表述
3. 定理证明：完整的证明过程
4. 应用分析：复杂问题求解
5. 研究前沿：开放性问题"""
            },
            DisciplineType.ENGINEERING: {
                DifficultyLevel.BEGINNER: """建议结构：
1. 应用场景：技术解决什么问题
2. 基本概念：核心术语解释
3. 简单示例：入门级代码
4. 实践练习：动手尝试""",
                DifficultyLevel.INTERMEDIATE: """建议结构：
1. 技术背景：问题与动机
2. 核心原理：工作原理详解
3. 代码实现：完整代码示例
4. 最佳实践：注意事项
5. 性能分析：效率与优化""",
                DifficultyLevel.ADVANCED: """建议结构：
1. 技术演进：历史与发展
2. 理论基础：算法/架构原理
3. 高级实现：生产级代码
4. 性能优化：深度优化技巧
5. 前沿进展：最新研究方向"""
            },
            DisciplineType.HUMANITIES: {
                DifficultyLevel.BEGINNER: """建议结构：
1. 引入：故事或现象
2. 核心观点：主要思想
3. 生活关联：现实意义
4. 思考问题：引发反思""",
                DifficultyLevel.INTERMEDIATE: """建议结构：
1. 问题提出：核心议题
2. 理论框架：主要理论
3. 案例分析：具体实例
4. 批判思考：不同观点
5. 现实意义：当代价值""",
                DifficultyLevel.ADVANCED: """建议结构：
1. 学术背景：研究脉络
2. 理论深度：核心理论详述
3. 文献综述：主要学者观点
4. 方法论：研究方法
5. 学术前沿：最新研究"""
            },
            DisciplineType.SOCIAL_SCIENCE: {
                DifficultyLevel.BEGINNER: """建议结构：
1. 现象引入：社会现象
2. 基本概念：核心术语
3. 简单案例：典型例子
4. 生活应用：实际意义""",
                DifficultyLevel.INTERMEDIATE: """建议结构：
1. 研究问题：核心问题
2. 理论基础：主要理论
3. 研究方法：方法论
4. 实证分析：数据与案例
5. 政策启示：实践意义""",
                DifficultyLevel.ADVANCED: """建议结构：
1. 研究背景：学术脉络
2. 理论框架：理论构建
3. 方法设计：研究设计
4. 深度分析：研究发现
5. 理论贡献：学术价值"""
            },
            DisciplineType.APPLIED_SKILL: {
                DifficultyLevel.BEGINNER: """建议结构：
1. 技能介绍：能做什么
2. 基础操作：入门步骤
3. 简单练习：动手实践
4. 常见问题：新手注意""",
                DifficultyLevel.INTERMEDIATE: """建议结构：
1. 技能背景：应用场景
2. 操作步骤：详细流程
3. 进阶技巧：提升方法
4. 实战案例：综合应用
5. 问题解决：故障排除""",
                DifficultyLevel.ADVANCED: """建议结构：
1. 专业背景：行业标准
2. 高级技巧：专业方法
3. 复杂案例：综合项目
4. 创新应用：创意实践
5. 行业趋势：发展方向"""
            },
            DisciplineType.COMMUNICATION: {
                DifficultyLevel.BEGINNER: """建议结构：
1. 场景引入：典型情境
2. 核心原则：基本原则
3. 简单技巧：入门方法
4. 练习建议：实践指导""",
                DifficultyLevel.INTERMEDIATE: """建议结构：
1. 场景分析：情境拆解
2. 核心技巧：方法详解
3. 案例示范：优秀范例
4. 实战演练：模拟练习
5. 反馈改进：优化建议""",
                DifficultyLevel.ADVANCED: """建议结构：
1. 专业背景：理论依据
2. 高级策略：专业方法
3. 复杂场景：高难度情境
4. 即兴应对：临场发挥
5. 持续提升：精进路径"""
            }
        }
        
        return structures.get(discipline, structures[DisciplineType.NATURAL_SCIENCE]).get(difficulty, "")

    def build_review_prompt(
        self,
        content: str,
        section_title: str,
        discipline: DisciplineType,
        difficulty: DifficultyLevel,
        audience: TargetAudience,
        guidelines: ContentGuidelines
    ) -> str:
        """构建审查提示词"""
        
        return f"""## 角色
你是一位专业的教育内容审查专家。

## 任务
审查以下教学内容的质量。

## 小节标题
{section_title}

## 内容
{content[:2000]}...

## 审查维度
1. 准确性：概念定义是否准确，原理阐述是否正确
2. 完整性：是否覆盖了该主题的核心内容
3. 深度适宜：内容深度是否符合{difficulty.value}级别要求
4. 受众适配：表达方式是否适合{audience.value}
5. 逻辑性：内容组织是否合理，层次是否清晰
6. 案例质量：案例是否恰当，数量是否充足（建议{guidelines.example_count}个以上）

## 输出格式
```json
{{
  "overall_score": 85,
  "dimension_scores": {{
    "accuracy": 90,
    "completeness": 80,
    "depth": 85,
    "audience_fit": 90,
    "logic": 85,
    "examples": 75
  }},
  "issues": [
    {{
      "type": "案例不足",
      "severity": "major",
      "description": "案例数量偏少，建议增加一个实际应用案例",
      "location": "第三段",
      "suggestion": "可以补充一个行业应用的具体案例"
    }}
  ],
  "strengths": ["概念定义清晰", "逻辑结构合理"],
  "recommendation": "通过/需要修改"
}}
```

请输出审查结果JSON："""

    def build_fix_prompt(
        self,
        content: str,
        issues: List[Dict],
        section_title: str,
        discipline: DisciplineType,
        difficulty: DifficultyLevel,
        audience: TargetAudience
    ) -> str:
        """构建修正提示词"""
        
        config = get_discipline_config(discipline)
        issues_text = "\n".join([
            f"- [{i.get('severity', 'minor')}] {i.get('type', '')}: {i.get('description', '')}\n  建议: {i.get('suggestion', '')}"
            for i in issues
        ])
        
        return f"""## 角色
你是一位专业的{config.name_cn}教育内容编辑专家。

## 任务
根据审查意见修正以下教学内容。

## 小节标题
{section_title}

## 原始内容
{content}

## 需要修正的问题
{issues_text}

## 难度定位
{difficulty.value}级别

## 目标受众
{audience.value}

## 修正要求
1. 只修正指出的问题，保持其他内容不变
2. 保持原有的写作风格和格式
3. 确保修正后的内容更加准确和完整
4. 新增内容要与原文风格一致

## 质量优先原则
- 如果需要大幅扩展才能解决问题，请毫不犹豫地扩展
- 质量永远优先于篇幅限制

请输出修正后的完整内容："""


_prompt_engine: Optional[PromptEngineV5] = None


def get_prompt_engine() -> PromptEngineV5:
    """获取提示词引擎实例"""
    global _prompt_engine
    if _prompt_engine is None:
        _prompt_engine = PromptEngineV5()
    return _prompt_engine
