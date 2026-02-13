"""
智能课程生成系统 - 共享提示词配置 (Python版本)

此文件用于前后端共享提示词系统的配置和常量
确保前后端使用一致的参数、版本和验证规则

@version 1.0.0
"""

from typing import Dict, List, Set, Any, TypedDict, Optional
from enum import Enum

# =============================================================================
# 枚举类型定义
# =============================================================================

class DifficultyLevel(str, Enum):
    """难度等级"""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class TeachingStyle(str, Enum):
    """教学风格"""
    ACADEMIC = "academic"
    INDUSTRIAL = "industrial"
    SOCRATIC = "socratic"
    HUMOROUS = "humorous"


class NodeLevel(int, Enum):
    """节点层级"""
    CHAPTER = 1      # L1: 章节
    SECTION = 2      # L2: 小节
    SUBSECTION = 3   # L3: 子节（内容）


class NodeType(str, Enum):
    """节点类型"""
    ORIGINAL = "original"
    EXPANDED = "expanded"
    REDEFINED = "redefined"


class PromptTemplateName(str, Enum):
    """提示词模板名称"""
    GENERATE_COURSE = "generate_course"
    GENERATE_SUB_NODES = "generate_sub_nodes"
    GENERATE_CONTENT = "generate_content"
    REDEFINE_CONTENT = "redefine_content"
    GENERATE_QUIZ = "generate_quiz"


# =============================================================================
# 常量定义
# =============================================================================

# 难度等级常量
DIFFICULTY_LEVELS = {
    "BEGINNER": "beginner",
    "INTERMEDIATE": "intermediate",
    "ADVANCED": "advanced"
}

# 教学风格常量
TEACHING_STYLES = {
    "ACADEMIC": "academic",
    "INDUSTRIAL": "industrial",
    "SOCRATIC": "socratic",
    "HUMOROUS": "humorous"
}

# 提示词版本号
PROMPT_VERSIONS: Dict[str, str] = {
    "generate_course": "4.0.0",
    "generate_sub_nodes": "4.0.0",
    "generate_content": "3.0.0",
    "redefine_content": "3.0.0",
    "generate_quiz": "3.0.0"
}

# 节点层级常量
NODE_LEVELS = {
    "CHAPTER": 1,      # L1: 章节
    "SECTION": 2,      # L2: 小节
    "SUBSECTION": 3    # L3: 子节（内容）
}

# 节点类型常量
NODE_TYPES = {
    "ORIGINAL": "original",
    "EXPANDED": "expanded",
    "REDEFINED": "redefined"
}

# =============================================================================
# 参数规则
# =============================================================================

# 参数范围规则
PARAMETER_RULES = {
    # 章节数量
    "chapter_count": {"min": 7, "max": 10},
    
    # 每章子章节数量
    "sub_chapter_count": {
        "beginner": {"min": 4, "max": 6},
        "intermediate": {"min": 5, "max": 7},
        "advanced": {"min": 5, "max": 10}
    },
    
    # 测验题目数量
    "question_count": {"min": 5, "max": 20},
    
    # 内容长度限制
    "content_length": {
        "min": 100,      # 最少字符数
        "max": 10000     # 最多字符数
    },
    
    # 公式密度 (百分比)
    "formula_density": {
        "beginner": {"min": 0, "max": 10},
        "intermediate": {"min": 10, "max": 30},
        "advanced": {"min": 30, "max": 100}
    }
}

# 有效的难度等级列表
VALID_DIFFICULTY_LEVELS: List[str] = ["beginner", "intermediate", "advanced"]

# 有效的教学风格列表
VALID_TEACHING_STYLES: List[str] = ["academic", "industrial", "socratic", "humorous"]

# 有效的节点类型列表
VALID_NODE_TYPES: List[str] = ["original", "expanded", "redefined"]

# =============================================================================
# 验证函数
# =============================================================================

def validate_difficulty(difficulty: str) -> bool:
    """验证难度等级"""
    return difficulty in VALID_DIFFICULTY_LEVELS


def validate_style(style: str) -> bool:
    """验证教学风格"""
    return style in VALID_TEACHING_STYLES


def validate_node_type(node_type: str) -> bool:
    """验证节点类型"""
    return node_type in VALID_NODE_TYPES


def validate_question_count(count: int, difficulty: str = "intermediate") -> bool:
    """验证测验题目数量"""
    rules = PARAMETER_RULES["question_count"]
    return rules["min"] <= count <= rules["max"]


def validate_chapter_count(count: int) -> bool:
    """验证章节数量"""
    rules = PARAMETER_RULES["chapter_count"]
    return rules["min"] <= count <= rules["max"]


def validate_sub_chapter_count(count: int, difficulty: str) -> bool:
    """验证子章节数量"""
    rules = PARAMETER_RULES["sub_chapter_count"].get(difficulty, {"min": 4, "max": 7})
    return rules["min"] <= count <= rules["max"]


class ValidationResult:
    """验证结果类"""
    def __init__(self, valid: bool = True, errors: Optional[List[str]] = None):
        self.valid = valid
        self.errors = errors or []
    
    def add_error(self, error: str):
        self.errors.append(error)
        self.valid = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": self.errors
        }


def validate_all_params(
    difficulty: str,
    style: str,
    question_count: Optional[int] = None,
    chapter_count: Optional[int] = None
) -> ValidationResult:
    """验证所有参数"""
    result = ValidationResult()
    
    if not validate_difficulty(difficulty):
        result.add_error(f"无效的难度等级: {difficulty}，必须是 {VALID_DIFFICULTY_LEVELS}")
    
    if not validate_style(style):
        result.add_error(f"无效的教学风格: {style}，必须是 {VALID_TEACHING_STYLES}")
    
    if question_count is not None and not validate_question_count(question_count, difficulty):
        rules = PARAMETER_RULES["question_count"]
        result.add_error(f"无效的测验题目数量: {question_count}，必须在 {rules['min']}-{rules['max']} 之间")
    
    if chapter_count is not None and not validate_chapter_count(chapter_count):
        rules = PARAMETER_RULES["chapter_count"]
        result.add_error(f"无效的章节数量: {chapter_count}，必须在 {rules['min']}-{rules['max']} 之间")
    
    return result


# =============================================================================
# 智能建议配置
# =============================================================================

# 通用智能建议
SMART_SUGGESTIONS = {
    "general": [
        {"text": "请帮我总结一下本章的核心概念", "type": "summary"},
        {"text": "这个概念在实际项目中如何应用？", "type": "application"},
        {"text": "能否用更通俗的方式解释一下？", "type": "explanation"},
        {"text": "给我一些相关的练习题", "type": "practice"},
        {"text": "这部分内容与其他章节有什么联系？", "type": "connection"}
    ],
    "context": {
        "max_suggestions": 3,
        "patterns": [
            {
                "keywords": ["算法", "algorithm", "复杂度", "complexity"],
                "template": "请详细讲解{nodeName}的时间复杂度分析",
                "type": "technical"
            },
            {
                "keywords": ["公式", "formula", "推导", "proof"],
                "template": "能否给出{nodeName}的完整推导过程？",
                "type": "technical"
            },
            {
                "keywords": ["代码", "code", "实现", "implementation"],
                "template": "请展示{nodeName}的代码实现示例",
                "type": "practical"
            },
            {
                "keywords": ["架构", "architecture", "设计", "design"],
                "template": "{nodeName}的架构设计有哪些关键点？",
                "type": "conceptual"
            },
            {
                "keywords": ["优化", "optimization", "性能", "performance"],
                "template": "如何优化{nodeName}的性能？",
                "type": "practical"
            }
        ]
    }
}

# 上下文建议模式
CONTEXT_SUGGESTION_PATTERNS = SMART_SUGGESTIONS["context"]["patterns"]


# =============================================================================
# 导出
# =============================================================================

__all__ = [
    # 枚举类型
    "DifficultyLevel",
    "TeachingStyle",
    "NodeLevel",
    "NodeType",
    "PromptTemplateName",
    # 常量
    "DIFFICULTY_LEVELS",
    "TEACHING_STYLES",
    "PROMPT_VERSIONS",
    "NODE_LEVELS",
    "NODE_TYPES",
    "PARAMETER_RULES",
    "VALID_DIFFICULTY_LEVELS",
    "VALID_TEACHING_STYLES",
    "VALID_NODE_TYPES",
    # 验证函数
    "validate_difficulty",
    "validate_style",
    "validate_node_type",
    "validate_question_count",
    "validate_chapter_count",
    "validate_sub_chapter_count",
    "ValidationResult",
    "validate_all_params",
    # 智能建议
    "SMART_SUGGESTIONS",
    "CONTEXT_SUGGESTION_PATTERNS",
]
