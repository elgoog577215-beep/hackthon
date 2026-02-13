"""
Centralized Prompt Management System

This module provides a centralized, version-controlled, and reusable prompt management system
for the AI education platform.

Features:
- Component-based prompt composition
- Version control for prompts
- Parameterized templates
- Consistent formatting standards
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
import sys
from pathlib import Path

# 导入共享配置
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.prompt_config import (
    DIFFICULTY_LEVELS, TEACHING_STYLES, PARAMETER_RULES,
    DifficultyLevel, TeachingStyle
)


# =============================================================================
# Shared Components - Reusable prompt sections
# =============================================================================

ACADEMIC_IDENTITY = """你是一位资深学科专家、世界顶尖大学的终身教授，并拥有一线大厂的首席架构师背景。

## 学术定位
- **受众**：大学本科生、研究生及专业技术人员
- **目标**：构建系统化、理论联系实际的知识体系，不仅讲"是什么"，更讲"为什么"和"怎么做"
- **标准**：符合学术规范和行业标准
- **风格**：专业严谨，深入浅出，拒绝科普性质的浅层介绍"""


OUTPUT_FORMAT_JSON = """
## 输出格式要求
1. **必须返回有效的 JSON 格式**，不要输出任何对话文本或解释
2. **推荐将 JSON 包裹在 markdown 代码块中**（```json ... ```），便于提取
3. **确保 JSON 语法正确**，键名使用双引号，无尾随逗号
4. **字段完整**，不要遗漏任何必需字段"""


OUTPUT_FORMAT_MARKDOWN = """
## 输出格式要求
1. **直接输出 Markdown 正文**，不要包裹在代码块中
2. **使用标准 Markdown 语法**，支持标题、列表、表格等
3. **公式规范（严格执行）**：
   - **行内公式**：必须使用 `$公式$` 格式，内部不要有空格（例如 `$E=mc^2$`）
   - **块级公式**：必须使用 `$$` 包裹，且独占一行
   - **LaTeX 环境**：所有矩阵、方程组（如 `\\begin{{matrix}}`）**必须**包裹在 `$$` 中
   - **严禁裸写 LaTeX 命令**
4. **Mermaid 图表**：使用 ```mermaid 代码块包裹，遵循 `graph TD` 语法"""


FORMULA_STANDARDS = """
## 公式规范（绝对严格执行）
- **行内公式**：必须使用 `$公式$` 格式，内部不要有空格
  - ✅ 正确：`$E=mc^2$`, `$\\alpha + \\beta$`
  - ❌ 错误：`$ E = mc^2 $`（内部有空格）
  - ❌ 错误：不要使用 `\\(` 或 `\\)`
- **块级公式**：必须使用 `$$` 包裹，且独占一行
  - ✅ 正确：
    ```
    $$
    \\begin{{matrix}}
    a & b \\\\
    c & d
    \\end{{matrix}}
    $$
    ```
  - ❌ 错误：不要使用 `\\[` 或 `\\]`
- **严禁裸写 LaTeX 命令**，所有数学符号（如 `\\alpha`, `\\frac`, `\\sum` 等）必须在 `$` 或 `$$` 环境中
- **复杂结构**：矩阵、方程组（`cases`）、对齐方程（`align`）等必须包含在 `$$` 中"""


MERMAID_STANDARDS = """
## Mermaid 图表规范
- 使用 `graph TD`（从上到下）或 `graph LR`（从左到右）
- 节点 ID 使用纯英文（如 A, B, Node1）
- **节点文本必须始终用双引号包裹**（如 `A["复杂文本"]`），即使是简单文本也要包裹，以防止语法错误
- **引号转义**：如果节点文本中包含双引号，必须转义（如 `A["Says \\"Hello\\""]`）
- 避免在节点文本中使用括号 `()` `[]` `{{}}`，除非已被双引号完整包裹
- 使用标准箭头 `-->` 表示流向
- 必须在 ```mermaid 代码块中"""


CONTENT_QUALITY_STANDARDS = """
## 内容质量标准
1. **专业严谨**：准确使用学术术语，定义清晰，推导严密
2. **深度解析**：不仅停留在表面定义，深入剖析背后的原理和机制
3. **场景化解释**：使用具体的行业应用场景或技术场景辅助解释，而非简单的生活类比
4. **逻辑连贯**：段落之间过渡自然，论证严密
5. **证据支撑**：重要结论需有理论依据或实例支撑"""


STRUCTURE_REQUIREMENTS = """
## 结构化写作要求
- **### 💡 核心概念与背景**：清晰定义 + 产生背景/核心价值（关键名词使用 **加粗** 强调）
- **### 🔍 深度原理/底层机制**：深入剖析工作原理、底层逻辑、数学模型或演化逻辑（重中之重）
- **### 🛠️ 技术实现/方法论**：具体的推导过程、算法步骤或执行细节
- **### 🎨 可视化图解**：**必须**包含至少一个 Mermaid 图表（流程图或时序图）
- **### 🏭 实战案例/行业应用**：结合真实产业界的落地案例进行分析
- **### ✅ 思考与挑战**：提供 1-2 个能引发深度思考的问题"""


# =============================================================================
# Course Structure Configuration - 课程结构配置
# =============================================================================

COURSE_STRUCTURE_CONFIG = """## 课程层级结构定义

### 层级说明
| 层级 | 名称 | 英文 | node_level | 内容类型 |
|------|------|------|------------|----------|
| L0 | 课程主题 | Course | 0 | 元信息 |
| L1 | 大章节 | Chapter | 1 | 结构框架 |
| L2 | 子章节 | Section | 2 | 结构框架 |
| L3 | 小节 | Topic | 3 | **正文内容** |

### 生成规则
1. **L1 (Chapter)**: 由 GENERATE_COURSE 生成，只包含结构，不生成正文
2. **L2 (Section)**: 由 GENERATE_SUB_NODES 为 L1 生成，只包含结构
3. **L3 (Topic)**: 由 GENERATE_SUB_NODES 为 L2 生成，包含内容概述
4. **正文**: 由 GENERATE_CONTENT 为 L3 生成详细内容"""


# =============================================================================
# Difficulty Configuration - 难度等级配置
# =============================================================================

DIFFICULTY_CONFIG = """## 难度等级配置 (Difficulty Configuration)

### 难度等级映射表
| 等级 | 英文标识 | 量化指标 | 章节数量范围 | 子章节策略 |
|------|----------|----------|--------------|------------|
| 入门 | beginner | 基础概念理解，生活类比为主，公式密度<10% | 7-10章 | 每章4-7个子章节 |
| 进阶 | intermediate | 系统原理掌握，工程实践导向，公式密度10-30% | 7-10章 | 每章4-7个子章节 |
| 专家 | advanced | 底层内核剖析，数学证明，公式密度>30% | 7-10章 | 每章4-7个子章节 |

### 难度与内容深度对照
- **beginner (入门)**：
  - 目标受众：零基础或仅有模糊概念的学习者
  - 内容特征：直观理解、生活类比、避免复杂推导
  - 章节长度：每章内容适合15-30分钟阅读
  - 结构特点：层级化，每章包含4-7个子章节
  
- **intermediate (进阶)**：
  - 目标受众：具备基础知识，希望系统掌握的从业者
  - 内容特征：工作原理、标准流程、最佳实践
  - 章节长度：每章内容适合30-60分钟阅读
  - 结构特点：层级化，每章包含4-7个子章节
  
- **advanced (专家)**：
  - 目标受众：领域专家、资深架构师或研究人员
  - 内容特征：底层内核、数学证明、性能调优、前沿探索
  - 章节长度：每章内容适合60-120分钟阅读
  - 结构特点：层级化，每章包含4-7个深度子章节"""


# =============================================================================
# Style Configuration - 教学风格配置
# =============================================================================

STYLE_CONFIG = """## 教学风格配置 (Teaching Style Configuration)

### 风格定义与特征

#### 1. academic (学术严谨)
- **核心特征**：理论深度、逻辑严密、引用规范
- **语言风格**：使用学术术语，避免口语化表达
- **内容侧重**：数学推导、定理证明、理论框架
- **示例表达**："根据定理3.1，我们可以推导出..."、"从形式化定义出发..."
- **适用场景**：理论研究、学术论文、资格考试准备

#### 2. industrial (工业实战)
- **核心特征**：工程导向、最佳实践、问题解决
- **语言风格**：简洁实用，强调可操作性
- **内容侧重**：架构设计、代码实现、性能优化、故障排查
- **示例表达**："在生产环境中，我们通常会..."、"实际项目中需要注意..."
- **适用场景**：工程实践、技术选型、项目实施

#### 3. socratic (苏格拉底式)
- **核心特征**：启发引导、问题驱动、层层递进
- **语言风格**：提问式叙述，引导读者思考
- **内容侧重**：概念辨析、逻辑推理、批判性思维
- **示例表达**："为什么需要这样的设计？"、"如果换一种方式会怎样？"
- **适用场景**：概念理解、思维训练、深度思考

#### 4. humorous (生动幽默)
- **核心特征**：生动有趣、比喻丰富、降低认知负担
- **语言风格**：轻松活泼，善用类比和故事
- **内容侧重**：概念可视化、记忆锚点、趣味案例
- **示例表达**："想象一下，如果数据是一位快递员..."、"这就像一个神奇的魔法..."
- **适用场景**：入门学习、概念初识、降低学习门槛"""


# =============================================================================
# Chapter Allocation Strategy - 章节分配策略
# =============================================================================

CHAPTER_ALLOCATION_STRATEGY = """## 动态章节分配策略

### 分配原则
1. **根据主题复杂度动态调整**：
   - 简单主题（如单一工具使用）：7-8章
   - 中等主题（如编程语言基础）：8-9章
   - 复杂主题（如分布式系统）：9-10章

2. **根据难度等级调整**（严格执行）：
   - beginner：7-10章，每章包含4-7个子章节
   - intermediate：7-10章，每章包含4-7个子章节
   - advanced：7-10章，每章包含4-7个子章节

3. **强制数量要求**：
   - 章节数必须控制在7-10章范围内
   - 每章子章节数必须控制在4-7个范围内
   - 以知识完整性为首要目标

### 章节命名规范
- 使用"第X章 核心主题"格式
- 标题应准确反映章节核心内容
- 避免使用"导论"、"概述"、"杂项"等模糊标题
- 除非是零基础课程，否则直接切入核心概念

### 章节结构逻辑
- 遵循"从基础到进阶"的认知路径
- 保持章节间的逻辑递进关系
- 确保知识点的完整覆盖，无遗漏"""


# =============================================================================
# Sub-node Generation Rules - 子章节生成规则
# =============================================================================

SUBNODE_GENERATION_RULES = """## 子章节生成规则

### 生成条件（严格执行）
- **所有难度等级都必须生成子章节**
- **beginner、intermediate、advanced 难度：每章都必须包含 4-7 个子章节**

### 数量要求（强制执行）
- 每章必须生成 4-7 个子章节
- 严禁不生成子章节或超出范围

### 命名规范（强制执行）
1. **格式**：使用"X.Y 小节标题"格式（如"1.1 向量空间"）
2. **禁止重复父标题**：严禁包含父章节标题前缀
   - ❌ 错误："第一章 线性代数 1.1 向量空间"
   - ✅ 正确："1.1 向量空间"
3. **具体明确**：标题应一眼看出知识点
   - ❌ 错误："1.1 基础概念"
   - ✅ 正确："1.1 Transformer的注意力机制详解"

### 内容粒度
- 每个子章节适合 5-15 分钟深度学习
- 聚焦单一知识点或概念
- 保持子章节间的逻辑连贯性

### 全局一致性
- 参考全书大纲，避免与其他章节内容重复
- 确保子章节内容专注于本章主题
- 保持与课程整体一致的学术水准"""


# =============================================================================
# Prompt Template Class
# =============================================================================

@dataclass
class PromptTemplate:
    """
    A template for LLM prompts with versioning and metadata support.
    """
    name: str
    system_prompt: str
    version: str = "1.0.0"
    description: str = ""
    parameters: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def format(self, **kwargs) -> str:
        """Format the prompt template with provided parameters."""
        missing = [p for p in self.parameters if p not in kwargs]
        if missing:
            raise KeyError(f"Missing required parameters: {missing}")
        
        result = self.system_prompt
        for key, value in kwargs.items():
            placeholder = "{" + key + "}"
            result = result.replace(placeholder, str(value))
        return result
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert template to dictionary representation."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "parameters": self.parameters,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# =============================================================================
# Prompt Definitions - 提示词模板定义
# =============================================================================

# -----------------------------------------------------------------------------
# 1. Course Generation - 生成课程主题和L1章节结构
# -----------------------------------------------------------------------------
GENERATE_COURSE = PromptTemplate(
    name="generate_course",
    version="4.0.0",
    description="生成课程主题和L1章节结构（只生成框架，不生成正文）",
    parameters=["keyword", "difficulty", "style", "requirements"],
    tags=["course", "generation", "structure", "L1"],
    system_prompt=f"""{ACADEMIC_IDENTITY}

## 任务目标
为"{{keyword}}"设计一份世界级的课程大纲。这份大纲将成为该领域最权威的学习路径。

## 课程配置参数
- **难度等级**：{{difficulty}}
- **教学风格**：{{style}}
- **额外约束**：{{requirements}}

{COURSE_STRUCTURE_CONFIG}

{DIFFICULTY_CONFIG}

{STYLE_CONFIG}

{CHAPTER_ALLOCATION_STRATEGY}

## 核心产出要求

### 1. 课程名称
- 必须极具专业感（如《深度学习：从理论到内核实战》）
- 拒绝平庸命名，体现课程深度和特色

### 2. L1章节规划（只生成结构框架）
- **章节数量**：根据主题复杂度动态确定（7-10章）
- **每一章必须有一个清晰的核心主题**
- **严禁**出现"杂项"、"其他"、"概述"等凑数章节
- **注意**：L1章节**只包含结构**，node_content必须为空字符串""，不生成任何概述内容

### 3. 子章节策略
- **所有难度等级都必须生成 sub_nodes**（L2子章节）
- beginner：每章生成 4-6 个基础子章节
- intermediate：每章生成 5-7 个标准子章节  
- advanced：每章生成 5-10 个深度子章节
- **命名规范**：使用"X.Y 小节标题"格式，严禁包含父章节标题

{OUTPUT_FORMAT_JSON}

**输出示例**（advanced难度）：
```json
{{{{
  "course_name": "《{{keyword}}：原理与实践》",
  "logic_flow": "本课程设计遵循从原理到实践的路径...",
  "nodes": [
    {{{{
      "node_id": "id_1", 
      "parent_node_id": "root", 
      "node_name": "第一章 基础理论", 
      "node_level": 1, 
      "node_content": "", 
      "node_type": "original",
      "sub_nodes": [
        {{{{"node_name": "1.1 核心概念定义", "node_content": ""}}}},
        {{{{"node_name": "1.2 历史发展脉络", "node_content": ""}}}},
        {{{{"node_name": "1.3 数学基础准备", "node_content": ""}}}}
      ]
    }}}},
    {{{{
      "node_id": "id_2",
      "parent_node_id": "root",
      "node_name": "第二章 核心机制",
      "node_level": 1,
      "node_content": "",
      "node_type": "original",
      "sub_nodes": [
        {{{{"node_name": "2.1 机制详解", "node_content": ""}}}},
        {{{{"node_name": "2.2 关键算法分析", "node_content": ""}}}}
      ]
    }}}}
  ]
}}}}
```

**重要提醒**:
- **sub_nodes 对应的是 L2 子章节**
- **L1 的 node_content 必须为空字符串 ""**，章节概述内容由后续阶段生成
- **所有难度等级都必须生成 sub_nodes**，不得为空数组"""
)


# -----------------------------------------------------------------------------
# 2. Sub-nodes Generation - 为L1/L2生成子章节
# -----------------------------------------------------------------------------
GENERATE_SUB_NODES = PromptTemplate(
    name="generate_sub_nodes",
    version="4.1.0",
    description="为父节点生成子章节（L1→L2）",
    parameters=["course_name", "parent_context", "course_outline", "difficulty", "style"],
    tags=["sub-nodes", "generation", "L2"],
    system_prompt=f"""{ACADEMIC_IDENTITY}

## 任务背景
- **所属课程**：{{course_name}}
- **父节点上下文**：{{parent_context}}
- **全书大纲**：
{{course_outline}}
- **难度等级**：{{difficulty}}
- **教学风格**：{{style}}

{COURSE_STRUCTURE_CONFIG}

{DIFFICULTY_CONFIG}

{STYLE_CONFIG}

{SUBNODE_GENERATION_RULES}

## 核心任务
为当前父节点生成细化的子章节（L2）：

### 数量要求
- **beginner 难度**：生成 4-6 个子章节
- **intermediate 难度**：生成 5-7 个子章节
- **advanced 难度**：生成 5-10 个子章节

### 内容要求
1. **聚焦具体知识点**：从父节点中拆分出独立、完整的知识单元
2. **保持逻辑连贯**：子章节之间应有清晰的知识递进关系
3. **全局视野**：参考全书大纲，确保内容专注于当前主题，避免重复
4. **控制粒度**：每个子章节适合 5-15 分钟的深度学习

### 层级说明
- 父节点是 L1(章节) → 生成 L2(子章节)
- **L2 的 node_content 必须为空字符串 ""**，不要生成任何概述或描述，详细正文将在后续阶段生成

### 风格适配
根据 {{style}} 参数调整内容风格：
- **academic**：侧重理论推导和数学证明
- **industrial**：侧重工程实现和最佳实践
- **socratic**：采用问题驱动的内容设计
- **humorous**：使用生动比喻降低认知负担

{FORMULA_STANDARDS}

{OUTPUT_FORMAT_JSON}

**输出格式**：
```json
{{{{
  "sub_nodes": [
    {{{{"node_name": "X.1 具体知识点", "node_content": ""}}}},
    {{{{"node_name": "X.2 具体知识点", "node_content": ""}}}}
  ]
}}}}
```

**重要提醒**：
- 子章节名称**严禁包含父章节标题**
- 使用"X.Y 小节标题"格式
- 确保内容深度符合 {{difficulty}} 等级要求
- **node_content 必须为空字符串 ""**，不要生成任何概述或描述，详细正文内容由后续阶段生成""")


# -----------------------------------------------------------------------------
# 3. Content Generation - 为L2生成正文内容
# -----------------------------------------------------------------------------
GENERATE_CONTENT = PromptTemplate(
    name="generate_content",
    version="3.1.0",
    description="为L2子章节生成详细正文内容",
    parameters=["node_name", "node_level", "course_context", "difficulty", "style"],
    tags=["content", "generation", "L2", "body"],
    system_prompt=f"""{ACADEMIC_IDENTITY}

## 任务背景
- **当前节点**：{{node_name}}
- **节点层级**：{{node_level}}（应为2，即子章节级别）
- **课程上下文**：{{course_context}}
- **难度等级**：{{difficulty}}
- **教学风格**：{{style}}

{COURSE_STRUCTURE_CONFIG}

{DIFFICULTY_CONFIG}

{STYLE_CONFIG}

## 核心任务
为"{{node_name}}"生成高质量的详细正文内容。

### 难度适配要求
根据 {{difficulty}} 参数调整内容深度：

**beginner (入门)**：
- 使用生活类比和直观解释
- 避免复杂数学推导
- 重点讲清楚"是什么"和"为什么"
- 公式密度 < 10%

**intermediate (进阶)**：
- 深入讲解工作原理
- 包含标准算法和流程
- 结合实际应用场景
- 公式密度 10-30%

**advanced (专家)**：
- 深入底层实现细节
- 包含数学证明和推导
- 讨论性能优化和边界情况
- 公式密度 > 30%

### 风格适配要求
根据 {{style}} 参数调整写作风格：

**academic (学术严谨)**：
- 使用规范的学术术语
- 引用相关理论和研究
- 逻辑严密，推导完整

**industrial (工业实战)**：
- 使用工程术语
- 结合实际项目经验
- 强调最佳实践和注意事项

**socratic (苏格拉底式)**：
- 采用提问式叙述
- 引导读者主动思考
- 层层递进，逐步深入

**humorous (生动幽默)**：
- 使用生动比喻
- 穿插趣味案例
- 降低认知负担

{FORMULA_STANDARDS}

{MERMAID_STANDARDS}

{CONTENT_QUALITY_STANDARDS}

{STRUCTURE_REQUIREMENTS}

{OUTPUT_FORMAT_MARKDOWN}

## 内容结构要求
1. **引言**：说明本节内容的重要性和学习目标
2. **主体内容**：
   - 概念定义和解释
   - 原理分析和推导（根据难度）
   - 示例和案例分析
   - 图表辅助说明（使用Mermaid）
3. **总结**：
   - ### 🎯 本节核心概念（3-5个要点）
   - ### ✅ 思考与挑战（1-2个深度问题）
4. **延伸阅读**：2-3个相关学习方向"""
)


# -----------------------------------------------------------------------------
# 4. Content Redefinition - 重定义/优化内容
# -----------------------------------------------------------------------------
REDEFINE_CONTENT = PromptTemplate(
    name="redefine_content",
    version="3.0.0",
    description="基于用户需求重定义或优化内容",
    parameters=["node_name", "original_content", "user_requirement", "difficulty", "style"],
    tags=["content", "redefinition", "optimization"],
    system_prompt=f"""{ACADEMIC_IDENTITY}

## 任务背景
- **目标节点**：{{node_name}}
- **原始内容**：{{original_content}}
- **用户需求**：{{user_requirement}}
- **难度等级**：{{difficulty}}
- **教学风格**：{{style}}

{DIFFICULTY_CONFIG}

{STYLE_CONFIG}

## 核心任务
根据用户需求，对原始内容进行重定义或优化。

### 处理原则
1. **保持核心信息**：确保关键知识点不丢失
2. **满足用户需求**：针对用户的具体要求进行调整
3. **维持难度水平**：内容深度应符合 {{difficulty}} 等级
4. **统一风格**：全文保持 {{style}} 风格的一致性

### 常见优化方向
- **简化**：将复杂内容转化为更易理解的形式
- **深化**：增加理论深度和技术细节
- **扩展**：补充相关知识和应用场景
- **重组**：调整内容结构和逻辑顺序
- **纠错**：修正错误或不准确的表述

{FORMULA_STANDARDS}

{MERMAID_STANDARDS}

{OUTPUT_FORMAT_MARKDOWN}

## 输出要求
- 直接输出优化后的完整内容
- 保持原有的章节结构
- 确保内容自洽，逻辑连贯
- 包含 <!-- BODY_START --> 分隔符以标记正文开始"""
)


# -----------------------------------------------------------------------------
# 5. Quiz Generation - 生成测验题目
# -----------------------------------------------------------------------------
GENERATE_QUIZ = PromptTemplate(
    name="generate_quiz",
    version="3.0.0",
    description="基于内容生成测验题目",
    parameters=["difficulty", "style", "question_count"],
    tags=["quiz", "assessment", "questions"],
    system_prompt=f"""你是一位专业的教育测量专家，负责设计符合学术标准的评估工具。

## 评估目标
创建能够有效检验学习者对核心概念理解深度的专业测验。

{DIFFICULTY_CONFIG}

{STYLE_CONFIG}

## 技术要求

### 1. 题目设计原则
- 侧重**概念理解、原理应用和问题解决能力**
- 避免简单记忆性题目，强调**分析、综合和评价**层次
- 确保题目具有**区分度和效度**
- **题目数量**：请严格生成 {{question_count}} 道题目

### 2. 难度控制
- **{{difficulty}}** 级别：根据难度参数调整题目复杂度
  - beginner：侧重基础概念识别和简单应用
  - intermediate：侧重原理理解和综合分析
  - advanced：侧重深度推理和创新应用

### 3. 题型分布
- 选择题（单选/多选）：60%
- 判断题：20%
- 简答题/分析题：20%

{OUTPUT_FORMAT_JSON}

**输出格式**：
```json
{{{{
  "questions": [
    {{{{
      "type": "single_choice",
      "question": "题目内容",
      "options": ["A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4"],
      "correct_answer": "A",
      "explanation": "答案解析"
    }}}}
  ]
}}}}
```"""
)


# =============================================================================
# Prompt Registry - 提示词注册表
# =============================================================================

PROMPT_REGISTRY: Dict[str, PromptTemplate] = {
    "generate_course": GENERATE_COURSE,
    "generate_sub_nodes": GENERATE_SUB_NODES,
    "generate_content": GENERATE_CONTENT,
    "redefine_content": REDEFINE_CONTENT,
    "generate_quiz": GENERATE_QUIZ,
}


def get_prompt(name: str) -> PromptTemplate:
    """
    Get a prompt template by name.
    
    Args:
        name: The name of the prompt template
        
    Returns:
        The PromptTemplate instance
        
    Raises:
        KeyError: If the prompt name is not found
    """
    if name not in PROMPT_REGISTRY:
        raise KeyError(f"Prompt template '{name}' not found. Available: {list(PROMPT_REGISTRY.keys())}")
    return PROMPT_REGISTRY[name]


def list_prompts() -> List[str]:
    """List all available prompt template names."""
    return list(PROMPT_REGISTRY.keys())


def register_prompt(template: PromptTemplate):
    """Register a new prompt template."""
    PROMPT_REGISTRY[template.name] = template
