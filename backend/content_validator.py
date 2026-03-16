"""
内容验证器模块

为不同学科类型提供多维度内容质量验证。
使用结构化评分规则替代简单的字符数阈值，
评估维度包括：结构完整性、内容深度、可读性、格式规范性。
"""

import re
from dataclasses import dataclass, field
from enum import Enum

from discipline_config import DisciplineConfig, DisciplineType, get_discipline_config
from models import QualityScore


class ValidationSeverity(str, Enum):
    """验证问题严重程度"""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    """验证问题"""
    section: str
    message: str
    severity: ValidationSeverity
    suggestion: str = ""


@dataclass
class ValidationResult:
    """验证结果"""
    valid: bool
    score: float
    issues: list[ValidationIssue] = field(default_factory=list)
    metrics: dict[str, any] = field(default_factory=dict)

    def add_issue(self, section: str, message: str, severity: ValidationSeverity, suggestion: str = "") -> None:
        """添加验证问题"""
        self.issues.append(ValidationIssue(section, message, severity, suggestion))
        if severity == ValidationSeverity.ERROR:
            self.valid = False

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "valid": self.valid,
            "score": self.score,
            "issues": [
                {
                    "section": i.section,
                    "message": i.message,
                    "severity": i.severity.value,
                    "suggestion": i.suggestion
                }
                for i in self.issues
            ],
            "metrics": self.metrics
        }


class ContentValidator:
    """内容验证器

    使用结构化评分规则进行多维度内容质量评估，
    替代简单的字符数阈值检查。
    """

    def __init__(self) -> None:
        self.section_patterns: dict[str, str] = {
            "💡": r"###\s*💡\s*(.+?)(?=###|$)",
            "🔍": r"###\s*🔍\s*(.+?)(?=###|$)",
            "🛠️": r"###\s*🛠️\s*(.+?)(?=###|$)",
            "🎨": r"###\s*🎨\s*(.+?)(?=###|$)",
            "🏭": r"###\s*🏭\s*(.+?)(?=###|$)",
            "✅": r"###\s*✅\s*(.+?)(?=###|$)",
        }

    # ------------------------------------------------------------------
    # 新增：多维度质量评估方法
    # ------------------------------------------------------------------

    def evaluate_quality(self, content: str, node_info: dict) -> QualityScore:
        """多维度评估内容质量。

        使用结构化评分规则替代简单字符数阈值，从四个维度独立评分：
        - 结构完整性：必要章节标题、段落数量是否足够
        - 内容深度：关键概念覆盖率、代码示例数量、概念定义数量
        - 可读性：段落长度适中、有过渡语句
        - 格式规范性：Markdown 语法正确性、标题层级合理

        Args:
            content: 待评估的内容文本
            node_info: 节点信息字典，包含 node_level、node_name 等字段

        Returns:
            QualityScore 多维度评分对象

        **Validates: Requirements 5.1, 5.2**
        """
        details: dict[str, str] = {}

        structure_score = self._eval_structure_completeness(content, node_info, details)
        depth_score = self._eval_content_depth(content, node_info, details)
        readability_score = self._eval_readability(content, details)
        format_score = self._eval_format_correctness(content, details)

        overall = (
            structure_score * 0.25
            + depth_score * 0.30
            + readability_score * 0.25
            + format_score * 0.20
        )

        return QualityScore(
            overall=round(overall, 3),
            structure_completeness=round(structure_score, 3),
            content_depth=round(depth_score, 3),
            readability=round(readability_score, 3),
            format_correctness=round(format_score, 3),
            details=details,
        )

    # ------------------------------------------------------------------
    # 结构完整性评估
    # ------------------------------------------------------------------

    def _eval_structure_completeness(
        self, content: str, node_info: dict, details: dict[str, str]
    ) -> float:
        """评估结构完整性。

        检查项：
        - 标题层级数量是否足够
        - 段落数量是否达到最低要求
        - 内容长度是否充足

        Args:
            content: 内容文本
            node_info: 节点信息
            details: 用于记录评估细节的字典

        Returns:
            0.0 ~ 1.0 的结构完整性分数
        """
        score = 1.0
        lines = content.split("\n")
        node_level: int = node_info.get("node_level", 2)

        # 检查标题层级
        headings = [line for line in lines if line.strip().startswith("#")]
        min_headings = 2 if node_level <= 2 else 1
        if len(headings) < min_headings:
            score -= 0.3
            details["structure_headings"] = (
                f"标题数 {len(headings)} 低于最低要求 {min_headings}"
            )

        # 检查段落数（结构化评分规则：最小段落数）
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        min_paragraphs = 3 if node_level <= 2 else 2
        if len(paragraphs) < min_paragraphs:
            score -= 0.3
            details["structure_paragraphs"] = (
                f"段落数 {len(paragraphs)} 低于最低要求 {min_paragraphs}"
            )

        # 检查内容长度（替代简单 600 字符阈值，使用分级评估）
        char_count = len(content.strip())
        if char_count < 200:
            score -= 0.4
            details["structure_length"] = f"内容过短（{char_count} 字符）"
        elif char_count < 500:
            score -= 0.15
            details["structure_length"] = f"内容偏短（{char_count} 字符）"

        return max(score, 0.0)

    # ------------------------------------------------------------------
    # 内容深度评估
    # ------------------------------------------------------------------

    def _eval_content_depth(
        self, content: str, node_info: dict, details: dict[str, str]
    ) -> float:
        """评估内容深度。

        结构化评分规则：
        - 概念定义数量（加粗文本后跟冒号的模式）
        - 代码示例数量（代码块）
        - 列表项数量（有序/无序列表）
        - 内容实质性（最低字符数）

        Args:
            content: 内容文本
            node_info: 节点信息
            details: 用于记录评估细节的字典

        Returns:
            0.0 ~ 1.0 的内容深度分数
        """
        score = 0.0

        # 概念定义数量（加粗文本后跟冒号）
        concept_defs = re.findall(r"\*\*[^*]+\*\*[：:]", content)
        concept_count = len(concept_defs)
        if concept_count > 0:
            score += min(concept_count * 0.15, 0.4)
        details["depth_concepts"] = f"概念定义 {concept_count} 个"

        # 代码示例数量
        code_blocks = re.findall(r"```[\s\S]*?```", content)
        code_count = len(code_blocks)
        if code_count > 0:
            score += min(code_count * 0.15, 0.3)
        details["depth_code"] = f"代码示例 {code_count} 个"

        # 列表项（有序/无序）
        list_items = re.findall(r"^[\s]*[-*\d+\.]\s+", content, re.MULTILINE)
        if list_items:
            score += min(len(list_items) * 0.03, 0.2)

        # 基础分：有实质内容就给底分
        if len(content.strip()) > 300:
            score += 0.2

        return min(score, 1.0)

    # ------------------------------------------------------------------
    # 可读性评估
    # ------------------------------------------------------------------

    def _eval_readability(
        self, content: str, details: dict[str, str]
    ) -> float:
        """评估可读性。

        检查项：
        - 段落长度是否适中（超长段落扣分）
        - 是否有过渡语句连接段落

        Args:
            content: 内容文本
            details: 用于记录评估细节的字典

        Returns:
            0.0 ~ 1.0 的可读性分数
        """
        score = 1.0

        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]

        # 检查超长段落
        long_paragraphs = [p for p in paragraphs if len(p) > 500]
        if long_paragraphs:
            penalty = min(len(long_paragraphs) * 0.15, 0.4)
            score -= penalty
            details["readability_long_para"] = (
                f"{len(long_paragraphs)} 个段落超过 500 字符"
            )

        # 检查过渡语句
        transition_words = [
            "因此", "所以", "然而", "但是", "此外", "另外",
            "首先", "其次", "最后", "总之", "综上",
            "例如", "比如", "具体来说", "换句话说",
        ]
        transition_count = sum(1 for w in transition_words if w in content)
        if transition_count == 0 and len(paragraphs) > 3:
            score -= 0.2
            details["readability_transitions"] = "缺少过渡语句"

        return max(score, 0.0)

    # ------------------------------------------------------------------
    # 格式规范性评估
    # ------------------------------------------------------------------

    def _eval_format_correctness(
        self, content: str, details: dict[str, str]
    ) -> float:
        """评估格式规范性。

        检查项：
        - Mermaid 图表语法（未闭合代码块）
        - 代码块闭合性
        - 标题格式（# 后应有空格）
        - 标题层级合理性

        Args:
            content: 内容文本
            details: 用于记录评估细节的字典

        Returns:
            0.0 ~ 1.0 的格式规范性分数
        """
        score = 1.0

        # 检查未闭合的代码块
        backtick_count = content.count("```")
        if backtick_count % 2 != 0:
            score -= 0.3
            details["format_code_block"] = "存在未闭合的代码块"

        # 检查标题格式（# 后应有空格）
        bad_headings = re.findall(r"^#{1,6}[^\s#]", content, re.MULTILINE)
        if bad_headings:
            score -= 0.1
            details["format_headings"] = (
                f"{len(bad_headings)} 个标题缺少空格"
            )

        # 检查标题层级跳跃（如 # 直接到 ###，跳过 ##）
        heading_levels = []
        for line in content.split("\n"):
            match = re.match(r"^(#{1,6})\s", line)
            if match:
                heading_levels.append(len(match.group(1)))
        if len(heading_levels) >= 2:
            for i in range(1, len(heading_levels)):
                if heading_levels[i] - heading_levels[i - 1] > 1:
                    score -= 0.1
                    details["format_heading_levels"] = "标题层级存在跳跃"
                    break

        return max(score, 0.0)

    # ------------------------------------------------------------------
    # 原有公共方法（保持向后兼容）
    # ------------------------------------------------------------------

    def validate_node(
        self,
        node: dict,
        discipline_type: DisciplineType,
        parent_chapter: str = None
    ) -> ValidationResult:
        """验证节点内容。

        Args:
            node: 节点数据
            discipline_type: 学科类型
            parent_chapter: 父章节编号（用于验证子章节编号）

        Returns:
            验证结果
        """
        result = ValidationResult(valid=True, score=0.0)
        config = get_discipline_config(discipline_type)

        node_level = node.get("node_level", 1)
        content = node.get("node_content", "")

        if node_level == 1:
            self._validate_l1_node(node, result)
        elif node_level == 2:
            self._validate_l2_node(node, parent_chapter, config, result)

        result.metrics["content_length"] = len(content)
        result.metrics["node_level"] = node_level

        # 使用结构化评分替代旧的简单扣分逻辑
        quality = self.evaluate_quality(content, node)
        result.score = quality.overall * 100.0
        result.metrics["quality_score"] = quality.model_dump()

        return result

    def extract_sections(self, content: str) -> dict[str, str]:
        """提取内容板块。

        Args:
            content: Markdown 内容文本

        Returns:
            emoji -> 板块内容 的字典
        """
        sections: dict[str, str] = {}

        for emoji, pattern in self.section_patterns.items():
            match = re.search(pattern, content, re.DOTALL)
            if match:
                sections[emoji] = match.group(1).strip()

        return sections

    def check_content_completeness(self, content: str, min_length: int = 600) -> tuple[bool, dict]:
        """检查内容完整性。

        使用结构化评分规则增强原有的简单字符数阈值检查。

        Args:
            content: 内容文本
            min_length: 最小字符数阈值（保留参数以向后兼容）

        Returns:
            (是否完整, 详细信息)
        """
        sections = self.extract_sections(content)
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        code_blocks = re.findall(r"```[\s\S]*?```", content)
        concept_defs = re.findall(r"\*\*[^*]+\*\*[：:]", content)

        metrics = {
            "length": len(content),
            "has_body_start": "<!-- BODY_START -->" in content,
            "has_mermaid": "```mermaid" in content,
            "has_table": "|" in content and "---" in content,
            "has_formula": bool(re.search(r'\$[^$]+\$', content)),
            "section_count": len(sections),
            "paragraph_count": len(paragraphs),
            "code_block_count": len(code_blocks),
            "concept_def_count": len(concept_defs),
        }

        # 结构化完整性判断：综合多个维度
        is_complete = (
            metrics["length"] >= min_length
            and metrics["paragraph_count"] >= 3
            and metrics["section_count"] >= 4
            and (metrics["has_mermaid"] or metrics["has_table"])
        )

        return is_complete, metrics

    # ------------------------------------------------------------------
    # 内部验证方法（保持向后兼容）
    # ------------------------------------------------------------------

    def _validate_l1_node(self, node: dict, result: ValidationResult) -> None:
        """验证 L1 章节节点。"""
        content = node.get("node_content", "")
        node_name = node.get("node_name", "")

        if content and len(content.strip()) > 50:
            result.add_issue(
                "node_content",
                f"L1 章节的 node_content 应为空，当前有 {len(content)} 字符",
                ValidationSeverity.ERROR,
                "L1 章节只包含结构，不生成概述内容"
            )

        if not re.match(r"^第[一二三四五六七八九十]+章\s+.+", node_name):
            result.add_issue(
                "node_name",
                f"L1 章节命名不符合规范：{node_name}",
                ValidationSeverity.WARNING,
                '应使用"第X章 章节名"格式'
            )

    def _validate_l2_node(
        self,
        node: dict,
        parent_chapter: str | None,
        config: DisciplineConfig,
        result: ValidationResult
    ) -> None:
        """验证 L2 子章节节点。"""
        content = node.get("node_content", "")
        node_name = node.get("node_name", "")

        if parent_chapter:
            self._validate_chapter_numbering(node_name, parent_chapter, result)

        if not content or len(content.strip()) < 100:
            result.add_issue(
                "node_content",
                f"内容过短：{len(content)} 字符",
                ValidationSeverity.ERROR,
                "内容应至少 100 字符"
            )
            return

        self._validate_sections(content, config, result)
        self._validate_quality_criteria(content, config, result)

    def _validate_chapter_numbering(
        self, node_name: str, parent_chapter: str, result: ValidationResult
    ) -> None:
        """验证章节编号。"""
        expected_prefix = f"{parent_chapter}."

        if not node_name.startswith(expected_prefix):
            result.add_issue(
                "node_name",
                f"章节编号错误：{node_name}，应以 {expected_prefix} 开头",
                ValidationSeverity.ERROR,
                f"正确格式：{expected_prefix}X 小节名"
            )

    def _validate_sections(
        self, content: str, config: DisciplineConfig, result: ValidationResult
    ) -> None:
        """验证内容板块。"""
        found_sections: dict[str, str] = {}

        for emoji, pattern in self.section_patterns.items():
            match = re.search(pattern, content, re.DOTALL)
            if match:
                found_sections[emoji] = match.group(1).strip()

        for section in config.content_sections:
            section_emoji = section.emoji.strip()

            if section_emoji not in found_sections:
                if section.required:
                    result.add_issue(
                        section.name,
                        f"缺失必填板块：{section.emoji} {section.name}",
                        ValidationSeverity.ERROR,
                        f"请添加 {section.emoji} {section.name} 板块"
                    )
            else:
                section_content = found_sections[section_emoji]
                if len(section_content) < section.min_length:
                    result.add_issue(
                        section.name,
                        f"板块内容过短：{len(section_content)} < {section.min_length}",
                        ValidationSeverity.WARNING,
                        f"建议扩充 {section.name} 内容"
                    )

                for hint in section.validation_hints:
                    if not self._check_validation_hint(section_content, hint):
                        result.add_issue(
                            section.name,
                            f"未满足要求：{hint}",
                            ValidationSeverity.WARNING,
                            hint
                        )

    def _check_validation_hint(self, content: str, hint: str) -> bool:
        """检查验证提示。"""
        hint_checks = {
            "必须包含完整证明或推导过程": lambda c: bool(
                re.search(r"(证明|推导|证|∵|∴|Q\.E\.D)", c)
            ),
            "必须包含Mermaid图或数学图表": lambda c: bool(
                "```mermaid" in c or re.search(r"\$\$.+?\$\$", c, re.DOTALL)
            ),
            "必须包含代码示例或架构图": lambda c: bool(
                "```" in c or "```mermaid" in c
            ),
            "必须呈现观点→论据→反驳→回应的完整链条": lambda c: bool(
                re.search(r"(观点|论据|反驳|回应|批判)", c)
            ),
            "必须包含具体操作步骤和练习任务": lambda c: bool(
                re.search(r"(步骤|练习|任务|操作)", c)
            ),
            "必须包含示范材料": lambda c: bool(
                re.search(r"(示范|示例|范例|模板)", c)
            ),
        }

        for key, check in hint_checks.items():
            if key in hint:
                return check(content)

        return True

    def _validate_quality_criteria(
        self, content: str, config: DisciplineConfig, result: ValidationResult
    ) -> None:
        """验证质量标准。"""
        criteria = config.quality_criteria

        if criteria.get("formula_density"):
            density = self._calculate_formula_density(content)
            expected = criteria["formula_density"]
            if density < expected["min"]:
                result.add_issue(
                    "quality",
                    f"公式密度过低：{density:.2%} < {expected['min']:.0%}",
                    ValidationSeverity.INFO,
                    "自然科学类内容应包含足够的公式"
                )

        if criteria.get("code_required"):
            if not re.search(r"```(?:python|java|javascript|cpp|c|go|rust)", content):
                result.add_issue(
                    "quality",
                    "工程技术类内容应包含代码示例",
                    ValidationSeverity.WARNING,
                    "添加代码示例以增强实用性"
                )

        if criteria.get("visualization_required"):
            if "```mermaid" not in content and "|" not in content:
                result.add_issue(
                    "quality",
                    "缺少可视化元素",
                    ValidationSeverity.WARNING,
                    "添加 Mermaid 图或表格"
                )

        if criteria.get("demo_material"):
            if not re.search(r"(示范|示例|范例|演讲稿|辩论稿)", content):
                result.add_issue(
                    "quality",
                    "表达沟通类内容应包含示范材料",
                    ValidationSeverity.WARNING,
                    "添加示范材料（如演讲稿片段、辩论论点展开）"
                )

    def _calculate_formula_density(self, content: str) -> float:
        """计算公式密度。"""
        formula_chars = len(re.findall(r'\$[^$]+\$', content))
        formula_chars += len(re.findall(r'\$\$.+?\$\$', content, re.DOTALL))
        total_chars = len(content)
        return formula_chars / max(total_chars, 1)


__all__ = [
    "ContentValidator",
    "ValidationResult",
    "ValidationIssue",
    "ValidationSeverity",
    "QualityScore",
]
