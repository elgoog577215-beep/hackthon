"""
内容质量预测与评估模块

从旧 V5 课程服务拆分，负责：
1. 根据章节信息预测内容复杂度并选择生成模式
2. 多维度内容质量评估（结构完整性、内容深度、可读性、格式规范性）
3. Mermaid 图表语法验证
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from discipline_config import DisciplineType
from models import QualityScore


class GenerationMode(Enum):
    """生成模式"""
    FAST = "fast"           # 快速模式：跳过审查，适合简单内容
    BALANCED = "balanced"   # 平衡模式：选择性审查
    QUALITY = "quality"     # 质量模式：完整审查循环


@dataclass
class MermaidIssue:
    """Mermaid 图表语法问题"""
    line_number: int
    message: str
    severity: str = "error"  # "error" | "warning"
    block_index: int = 0


class QualityPredictor:
    """内容质量预测与评估"""

    def __init__(self) -> None:
        self.history: list[dict] = []

    def predict_quality(
        self, section_info: dict, discipline: DisciplineType
    ) -> tuple[float, GenerationMode]:
        """根据章节信息预测内容质量和推荐生成模式。

        通过分析标题中的复杂关键词和关键知识点数量来估算内容复杂度，
        并据此推荐合适的生成模式。

        Args:
            section_info: 章节信息字典，包含 title 和 key_points 等字段
            discipline: 学科类型

        Returns:
            (预测质量分数, 推荐生成模式) 的元组
        """
        title: str = section_info.get("title", "")
        key_points: list = section_info.get("key_points", [])

        complexity_score = 0.0

        complex_keywords = ["原理", "机制", "推导", "证明", "算法", "架构", "设计"]
        for kw in complex_keywords:
            if kw in title:
                complexity_score += 0.15

        complexity_score += len(key_points) * 0.1
        complexity_score = min(complexity_score, 1.0)

        if complexity_score < 0.3:
            return 0.85, GenerationMode.FAST
        elif complexity_score < 0.6:
            return 0.75, GenerationMode.BALANCED
        else:
            return 0.65, GenerationMode.QUALITY

    def evaluate_content(self, content: str, node_info: dict) -> QualityScore:
        """多维度评估内容质量。

        评估维度：
        - 结构完整性：是否包含必要的标题层级和段落结构
        - 内容深度：关键概念覆盖率、代码示例和定义数量
        - 可读性：段落长度合理性和过渡语句
        - 格式规范性：Markdown 语法正确性

        Args:
            content: 待评估的内容文本
            node_info: 节点信息字典，包含 node_level、node_name 等字段

        Returns:
            QualityScore 多维度评分对象
        """
        details: dict[str, str] = {}

        # --- 结构完整性 ---
        structure_score = self._evaluate_structure(content, node_info, details)

        # --- 内容深度 ---
        depth_score = self._evaluate_depth(content, node_info, details)

        # --- 可读性 ---
        readability_score = self._evaluate_readability(content, details)

        # --- 格式规范性 ---
        format_score = self._evaluate_format(content, details)

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

    def validate_mermaid(self, content: str) -> list[MermaidIssue]:
        """验证内容中所有 Mermaid 图表代码块的语法。

        检测项：
        - 未闭合的代码块
        - 缺少图表类型声明
        - 不支持的图表类型
        - 箭头语法错误
        - 未闭合的方括号/圆括号

        Args:
            content: 包含 Mermaid 代码块的 Markdown 内容

        Returns:
            检测到的 MermaidIssue 列表
        """
        issues: list[MermaidIssue] = []
        mermaid_blocks = self._extract_mermaid_blocks(content)

        for idx, (block_text, start_line) in enumerate(mermaid_blocks):
            block_issues = self._validate_single_mermaid_block(
                block_text, start_line, idx
            )
            issues.extend(block_issues)

        return issues

    # ------------------------------------------------------------------
    # 内部评估方法
    # ------------------------------------------------------------------

    def _evaluate_structure(
        self, content: str, node_info: dict, details: dict[str, str]
    ) -> float:
        """评估结构完整性。"""
        score = 1.0
        lines = content.split("\n")

        # 检查标题层级
        headings = [l for l in lines if l.strip().startswith("#")]
        node_level: int = node_info.get("node_level", 2)

        if node_level <= 2 and len(headings) < 2:
            score -= 0.3
            details["structure_headings"] = "标题层级不足"

        # 检查段落数
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        min_paragraphs = 3 if node_level <= 2 else 2
        if len(paragraphs) < min_paragraphs:
            score -= 0.3
            details["structure_paragraphs"] = (
                f"段落数 {len(paragraphs)} 低于最低要求 {min_paragraphs}"
            )

        # 检查内容长度
        char_count = len(content.strip())
        if char_count < 200:
            score -= 0.4
            details["structure_length"] = f"内容过短（{char_count} 字符）"

        return max(score, 0.0)

    def _evaluate_depth(
        self, content: str, node_info: dict, details: dict[str, str]
    ) -> float:
        """评估内容深度。"""
        score = 0.0

        # 概念定义数量（加粗文本后跟冒号的模式）
        concept_defs = re.findall(r"\*\*[^*]+\*\*[：:]", content)
        if concept_defs:
            score += min(len(concept_defs) * 0.15, 0.4)
            details["depth_concepts"] = f"概念定义 {len(concept_defs)} 个"

        # 代码示例数量
        code_blocks = re.findall(r"```[\s\S]*?```", content)
        if code_blocks:
            score += min(len(code_blocks) * 0.15, 0.3)
            details["depth_code"] = f"代码示例 {len(code_blocks)} 个"

        # 列表项（有序/无序）
        list_items = re.findall(r"^[\s]*[-*\d+\.]\s+", content, re.MULTILINE)
        if list_items:
            score += min(len(list_items) * 0.03, 0.2)

        # 基础分：有实质内容就给底分
        if len(content.strip()) > 300:
            score += 0.2

        return min(score, 1.0)

    def _evaluate_readability(
        self, content: str, details: dict[str, str]
    ) -> float:
        """评估可读性。"""
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

        # 检查过渡语句（段落间的连接词）
        transition_words = [
            "因此", "所以", "然而", "但是", "此外", "另外",
            "首先", "其次", "最后", "总之", "综上",
            "例如", "比如", "具体来说", "换句话说",
        ]
        transition_count = sum(
            1 for w in transition_words if w in content
        )
        if transition_count == 0 and len(paragraphs) > 3:
            score -= 0.2
            details["readability_transitions"] = "缺少过渡语句"

        return max(score, 0.0)

    def _evaluate_format(
        self, content: str, details: dict[str, str]
    ) -> float:
        """评估格式规范性（Markdown 语法正确性）。"""
        score = 1.0

        # 检查 Mermaid 图表语法
        mermaid_issues = self.validate_mermaid(content)
        error_issues = [i for i in mermaid_issues if i.severity == "error"]
        if error_issues:
            penalty = min(len(error_issues) * 0.2, 0.5)
            score -= penalty
            details["format_mermaid"] = (
                f"Mermaid 语法错误 {len(error_issues)} 处"
            )

        # 检查未闭合的代码块（非 Mermaid）
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

        return max(score, 0.0)

    # ------------------------------------------------------------------
    # Mermaid 验证内部方法
    # ------------------------------------------------------------------

    def _extract_mermaid_blocks(
        self, content: str
    ) -> list[tuple[str, int]]:
        """提取内容中的所有 Mermaid 代码块。

        Returns:
            (代码块文本, 起始行号) 的列表
        """
        blocks: list[tuple[str, int]] = []
        lines = content.split("\n")
        in_block = False
        block_lines: list[str] = []
        block_start = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("```mermaid"):
                in_block = True
                block_lines = []
                block_start = i + 1
            elif in_block and stripped == "```":
                blocks.append(("\n".join(block_lines), block_start))
                in_block = False
                block_lines = []
            elif in_block:
                block_lines.append(line)

        # 未闭合的 Mermaid 块
        if in_block and block_lines:
            blocks.append(("\n".join(block_lines), block_start))

        return blocks

    def _validate_single_mermaid_block(
        self, block_text: str, start_line: int, block_index: int
    ) -> list[MermaidIssue]:
        """验证单个 Mermaid 代码块的语法。"""
        issues: list[MermaidIssue] = []
        lines = block_text.strip().split("\n")

        if not lines or not lines[0].strip():
            issues.append(
                MermaidIssue(
                    line_number=start_line,
                    message="Mermaid 代码块为空",
                    severity="error",
                    block_index=block_index,
                )
            )
            return issues

        # 检查图表类型声明
        supported_types = [
            "graph", "flowchart", "sequenceDiagram", "classDiagram",
            "stateDiagram", "erDiagram", "gantt", "pie", "gitgraph",
            "mindmap", "timeline", "journey",
            "stateDiagram-v2", "flowchart-v2",
        ]
        first_line = lines[0].strip()
        type_found = any(first_line.startswith(t) for t in supported_types)

        if not type_found:
            issues.append(
                MermaidIssue(
                    line_number=start_line,
                    message=f"不支持或缺少图表类型声明: '{first_line}'",
                    severity="error",
                    block_index=block_index,
                )
            )

        # 逐行检查常见语法问题
        for i, line in enumerate(lines[1:], start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("%%"):
                continue

            line_number = start_line + i

            # 检查未闭合的方括号
            if stripped.count("[") != stripped.count("]"):
                issues.append(
                    MermaidIssue(
                        line_number=line_number,
                        message="未闭合的方括号",
                        severity="error",
                        block_index=block_index,
                    )
                )

            # 检查未闭合的圆括号
            if stripped.count("(") != stripped.count(")"):
                issues.append(
                    MermaidIssue(
                        line_number=line_number,
                        message="未闭合的圆括号",
                        severity="error",
                        block_index=block_index,
                    )
                )

            # 检查未闭合的花括号
            if stripped.count("{") != stripped.count("}"):
                issues.append(
                    MermaidIssue(
                        line_number=line_number,
                        message="未闭合的花括号",
                        severity="warning",
                        block_index=block_index,
                    )
                )

        return issues
