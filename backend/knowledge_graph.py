"""
全局知识图谱模块

从 ai_course_service_v5.py 拆分，维护跨节点的概念、示例和公式注册表，
用于课程级别的一致性追踪和上下文增强。
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass, field

from models import SimilarExample


@dataclass
class TermSource:
    """术语定义来源"""
    term: str
    definition: str
    node_id: str
    context: str


@dataclass
class GlobalKnowledgeGraph:
    """全局知识图谱，维护跨节点的概念、示例和公式注册表"""

    concepts: dict[str, dict[str, str]] = field(default_factory=dict)
    examples: dict[str, dict[str, str]] = field(default_factory=dict)
    formulas: dict[str, dict[str, str]] = field(default_factory=dict)
    theorems: dict[str, dict[str, str]] = field(default_factory=dict)
    references: set[str] = field(default_factory=set)

    concept_occurrences: dict[str, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )

    def register_concept(
        self, name: str, definition: str, node_id: str, context: str = ""
    ) -> None:
        """注册概念到知识图谱。

        如果概念尚未注册，记录其定义、首次出现的节点和上下文。
        无论是否已注册，都会追加该概念在当前节点的出现记录。

        Args:
            name: 概念名称
            definition: 概念定义
            node_id: 所属节点 ID
            context: 概念出现的上下文（可选）
        """
        if name not in self.concepts:
            self.concepts[name] = {
                "definition": definition,
                "first_occurrence": node_id,
                "context": context,
            }
        self.concept_occurrences[name].append(node_id)

    def register_example(
        self, title: str, summary: str, node_id: str
    ) -> None:
        """注册案例到知识图谱。

        使用 MD5 哈希前缀作为键，存储案例标题、摘要和所属节点。

        Args:
            title: 案例标题
            summary: 案例摘要（建议不少于 50 字）
            node_id: 所属节点 ID
        """
        key = hashlib.md5(title.encode()).hexdigest()[:8]
        self.examples[key] = {
            "title": title,
            "summary": summary,
            "node_id": node_id,
        }

    def register_formula(
        self, formula: str, description: str, node_id: str
    ) -> None:
        """注册公式到知识图谱。

        使用 MD5 哈希前缀作为键，避免重复注册相同公式。

        Args:
            formula: 公式文本
            description: 公式描述
            node_id: 所属节点 ID
        """
        key = hashlib.md5(formula.encode()).hexdigest()[:8]
        if key not in self.formulas:
            self.formulas[key] = {
                "formula": formula,
                "description": description,
                "node_id": node_id,
            }

    def get_context_for_node(self, node_id: str, max_items: int = 10) -> str:
        """获取指定节点的上下文信息。

        返回其他节点已定义的概念和已使用的案例，供 LLM 生成时参考，
        避免重复定义和重复案例。

        Args:
            node_id: 目标节点 ID
            max_items: 返回的最大概念数量

        Returns:
            格式化的上下文字符串
        """
        parts: list[str] = []

        # 获取当前节点尚未涉及的概念
        relevant_concepts = [
            (name, info)
            for name, info in self.concepts.items()
            if node_id not in self.concept_occurrences.get(name, [])
        ][:max_items]

        if relevant_concepts:
            parts.append("## 已定义概念（可引用，勿重复定义）")
            for name, info in relevant_concepts:
                parts.append(f"- **{name}**: {info['definition'][:60]}")

        if self.examples:
            parts.append("\n## 已使用案例（请使用新案例）")
            for ex_info in list(self.examples.values())[:5]:
                parts.append(f"- {ex_info['title']}...")

        return "\n".join(parts) if parts else ""

    def get_used_example_titles(self) -> list[str]:
        """获取所有已使用的案例标题列表。

        Returns:
            案例标题列表
        """
        return [info["title"] for info in self.examples.values()]

    def check_example_similarity(
        self, new_example: str, threshold: float = 0.8
    ) -> list[SimilarExample]:
        """检查新案例与已注册案例的相似度。

        使用字符级 n-gram 余弦相似度算法，无需外部依赖。

        Args:
            new_example: 新案例文本
            threshold: 相似度阈值（默认 0.8）

        Returns:
            超过阈值的相似案例列表
        """
        similar: list[SimilarExample] = []
        new_ngrams = _char_ngram_vector(new_example)

        for info in self.examples.values():
            existing_text = info["summary"] if info["summary"] else info["title"]
            existing_ngrams = _char_ngram_vector(existing_text)
            score = _cosine_similarity(new_ngrams, existing_ngrams)

            if score >= threshold:
                similar.append(
                    SimilarExample(
                        existing_title=info["title"],
                        existing_node_id=info["node_id"],
                        similarity_score=score,
                        summary=info["summary"],
                    )
                )

        return similar

    def get_term_definition_source(self, term: str) -> TermSource | None:
        """查找术语的原始定义来源。

        Args:
            term: 要查找的术语名称

        Returns:
            术语来源信息，如果未找到则返回 None
        """
        if term not in self.concepts:
            return None

        info = self.concepts[term]
        return TermSource(
            term=term,
            definition=info["definition"],
            node_id=info["first_occurrence"],
            context=info.get("context", ""),
        )

    def check_consistency(self, node_id: str, content: str) -> list[dict[str, str]]:
        """检查内容一致性（保留原有接口兼容）。

        检测内容中的概念定义是否与已注册的定义矛盾。

        Args:
            node_id: 节点 ID
            content: 节点内容文本

        Returns:
            一致性问题列表
        """
        import re

        issues: list[dict[str, str]] = []

        bold_matches = re.findall(
            r"\*\*([^*]{2,20})\*\*[：:]\s*([^。\n]{10,100})", content
        )

        for name, definition in bold_matches:
            if name in self.concepts:
                existing_def = self.concepts[name]["definition"]
                if definition.strip() != existing_def.strip():
                    existing_ngrams = _char_ngram_vector(existing_def)
                    new_ngrams = _char_ngram_vector(definition)
                    similarity = _cosine_similarity(existing_ngrams, new_ngrams)
                    if similarity < 0.7:
                        issues.append(
                            {
                                "type": "概念不一致",
                                "concept": name,
                                "existing": existing_def[:50],
                                "new": definition[:50],
                                "severity": "major",
                            }
                        )

        return issues


def _char_ngram_vector(text: str, n: int = 2) -> dict[str, int]:
    """将文本转换为字符级 n-gram 频率向量。

    Args:
        text: 输入文本
        n: n-gram 的长度（默认 2，即 bigram）

    Returns:
        n-gram 到频率的映射
    """
    vector: dict[str, int] = defaultdict(int)
    text = text.strip().lower()
    for i in range(len(text) - n + 1):
        gram = text[i : i + n]
        vector[gram] += 1
    return dict(vector)


def _cosine_similarity(vec_a: dict[str, int], vec_b: dict[str, int]) -> float:
    """计算两个稀疏向量的余弦相似度。

    Args:
        vec_a: 向量 A（n-gram 频率映射）
        vec_b: 向量 B（n-gram 频率映射）

    Returns:
        余弦相似度值（0.0 ~ 1.0）
    """
    if not vec_a or not vec_b:
        return 0.0

    common_keys = set(vec_a.keys()) & set(vec_b.keys())
    dot_product = sum(vec_a[k] * vec_b[k] for k in common_keys)

    magnitude_a = math.sqrt(sum(v * v for v in vec_a.values()))
    magnitude_b = math.sqrt(sum(v * v for v in vec_b.values()))

    if magnitude_a == 0.0 or magnitude_b == 0.0:
        return 0.0

    return dot_product / (magnitude_a * magnitude_b)
