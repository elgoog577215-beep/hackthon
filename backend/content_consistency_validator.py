"""
内容一致性验证器

检测生成内容与课程主题、学科类型是否匹配，
并通过 GlobalKnowledgeGraph 进行跨节点一致性检查：
- 重复案例检测（余弦相似度 ≥ 0.8）
- 矛盾定义检测
- 断裂引用检测
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from discipline_config import DisciplineType, get_discipline_config
from knowledge_graph import GlobalKnowledgeGraph, _char_ngram_vector, _cosine_similarity
from models import ConsistencyIssue


class ContentMismatchType(Enum):
    """内容不匹配类型"""
    DISCIPLINE_MISMATCH = "discipline_mismatch"
    TOPIC_MISMATCH = "topic_mismatch"
    TEMPLATE_MISMATCH = "template_mismatch"
    KEYWORD_MISMATCH = "keyword_mismatch"


@dataclass
class ContentMismatch:
    """内容不匹配检测结果"""
    type: ContentMismatchType
    severity: str  # "warning", "error", "critical"
    message: str
    expected: str
    actual: str
    suggestions: list[str]


class ContentConsistencyValidator:
    """内容一致性验证器

    支持两种检查模式：
    1. 单节点内容一致性检查（学科、主题、模板匹配）
    2. 跨节点全局一致性检查（重复案例、矛盾定义、断裂引用）
    """

    def __init__(self, knowledge_graph: GlobalKnowledgeGraph | None = None) -> None:
        """初始化一致性验证器。

        Args:
            knowledge_graph: 全局知识图谱实例，用于跨节点一致性检查。
                           如果为 None，跨节点检查功能将不可用。
        """
        self.knowledge_graph = knowledge_graph

        # 各学科的典型关键词
        self.discipline_keywords: dict[DisciplineType, list[str]] = {
            DisciplineType.NATURAL_SCIENCE: [
                "定理", "证明", "推导", "公式", "方程", "定律", "原理",
                "实验", "数据", "测量", "计算", "模型", "假设",
                "数学", "物理", "化学", "生物", "天文", "地质",
                "theorem", "proof", "derivation", "formula", "equation", "law", "principle",
                "experiment", "data", "measurement", "calculation", "model", "hypothesis"
            ],
            DisciplineType.ENGINEERING: [
                "算法", "代码", "编程", "架构", "设计", "实现",
                "系统", "软件", "硬件", "网络", "数据库", "接口",
                "性能", "优化", "调试", "测试", "部署", "维护",
                "algorithm", "code", "programming", "architecture", "design", "implementation",
                "system", "software", "hardware", "network", "database", "interface"
            ],
            DisciplineType.HUMANITIES: [
                "文本", "语言", "语法", "词汇", "句子", "篇章",
                "文学", "诗歌", "小说", "散文", "戏剧", "批评",
                "哲学", "思想", "存在", "意识", "价值", "意义",
                "历史", "文化", "传统", "习俗", "信仰", "艺术",
                "text", "language", "grammar", "vocabulary", "sentence", "discourse",
                "literature", "poetry", "novel", "essay", "drama", "criticism",
                "philosophy", "thought", "existence", "consciousness", "value", "meaning"
            ],
            DisciplineType.SOCIAL_SCIENCE: [
                "社会", "行为", "心理", "认知", "态度", "动机",
                "经济", "市场", "政策", "管理", "组织", "制度",
                "统计", "调查", "问卷", "访谈", "案例", "分析",
                "society", "behavior", "psychology", "cognition", "attitude", "motivation",
                "economy", "market", "policy", "management", "organization", "institution",
                "statistics", "survey", "questionnaire", "interview", "case", "analysis"
            ],
            DisciplineType.APPLIED_SKILL: [
                "技巧", "手法", "步骤", "流程", "操作", "练习",
                "工具", "设备", "材料", "配方", "比例", "时间",
                "摄影", "烹饪", "绘画", "书法", "乐器", "运动",
                "technique", "method", "step", "process", "operation", "practice",
                "tool", "equipment", "material", "recipe", "ratio", "time",
                "photography", "cooking", "painting", "calligraphy", "instrument", "sports"
            ],
            DisciplineType.COMMUNICATION: [
                "传播", "媒体", "新闻", "广告", "公关", "营销",
                "沟通", "表达", "演讲", "写作", "报道", "编辑",
                "网络", "社交", "平台", "内容", "受众", "效果",
                "communication", "media", "news", "advertising", "public relations", "marketing",
                "communication", "expression", "speech", "writing", "reporting", "editing",
                "network", "social", "platform", "content", "audience", "effect"
            ]
        }

        # 各学科的典型不匹配关键词
        self.mismatch_indicators: dict[DisciplineType, list[str]] = {
            DisciplineType.HUMANITIES: [
                "麦克斯韦", "电磁", "电场", "磁场", "波动方程", "量子", "相对论",
                "微积分", "导数", "积分", "矩阵", "向量", "复数",
                "化学反应", "分子式", "原子结构", "元素周期表"
            ],
            DisciplineType.NATURAL_SCIENCE: [
                "语法规则", "句法结构", "词性分类", "修辞手法", "文学批评", "文本分析",
                "社会调查", "心理测试", "经济模型", "政策分析",
                "编程语言", "算法设计", "软件开发", "系统架构"
            ]
        }

    def validate_content_consistency(
        self,
        course_name: str,
        course_topic: str,
        discipline_type: DisciplineType,
        generated_content: str,
        node_name: str = ""
    ) -> list[ContentMismatch]:
        """验证单节点内容一致性。

        检查生成内容与课程主题、学科类型是否匹配。

        Args:
            course_name: 课程名称
            course_topic: 课程主题
            discipline_type: 学科类型
            generated_content: 生成的内容
            node_name: 节点名称

        Returns:
            不匹配问题列表
        """
        mismatches: list[ContentMismatch] = []

        # 1. 学科类型一致性检查
        discipline_mismatches = self._check_discipline_consistency(
            discipline_type, generated_content, course_name
        )
        mismatches.extend(discipline_mismatches)

        # 2. 主题相关性检查
        topic_mismatches = self._check_topic_relevance(
            course_topic, course_name, generated_content
        )
        mismatches.extend(topic_mismatches)

        # 3. 模板结构检查
        template_mismatches = self._check_template_structure(
            discipline_type, generated_content
        )
        mismatches.extend(template_mismatches)

        return mismatches

    def check_cross_node_consistency(
        self,
        nodes: list[dict[str, str]],
        section_titles: list[str] | None = None,
    ) -> list[ConsistencyIssue]:
        """执行跨节点全局一致性检查。

        检测重复案例、矛盾定义和断裂引用。

        Args:
            nodes: 节点列表，每个节点包含 ``node_id``、``node_name``、``node_content`` 字段。
            section_titles: 课程中所有有效的章节标题列表，用于断裂引用检测。
                          如果为 None，将从 nodes 中提取。

        Returns:
            一致性问题列表，每个问题标注 severity 和 auto_fixable
        """
        issues: list[ConsistencyIssue] = []

        # 1. 重复案例检测
        duplicate_issues = self._detect_duplicate_examples(nodes)
        issues.extend(duplicate_issues)

        # 2. 矛盾定义检测
        contradiction_issues = self._detect_contradicting_definitions(nodes)
        issues.extend(contradiction_issues)

        # 3. 断裂引用检测
        if section_titles is None:
            section_titles = [n["node_name"] for n in nodes if n.get("node_name")]
        broken_ref_issues = self._detect_broken_references(nodes, section_titles)
        issues.extend(broken_ref_issues)

        return issues

    # ------------------------------------------------------------------
    # 跨节点检测：重复案例
    # ------------------------------------------------------------------

    def _detect_duplicate_examples(
        self, nodes: list[dict[str, str]], threshold: float = 0.8
    ) -> list[ConsistencyIssue]:
        """检测跨节点的重复案例。

        从每个节点内容中提取案例文本，使用字符级 n-gram 余弦相似度
        进行两两比较，相似度 ≥ threshold 的案例对标记为重复。

        如果已配置 GlobalKnowledgeGraph，也会利用其已注册案例进行检测。

        Args:
            nodes: 节点列表
            threshold: 余弦相似度阈值（默认 0.8）

        Returns:
            重复案例的 ConsistencyIssue 列表
        """
        issues: list[ConsistencyIssue] = []

        # 提取每个节点的案例
        node_examples: list[dict[str, str]] = []
        for node in nodes:
            node_id = node.get("node_id", "")
            content = node.get("node_content", "")
            examples = self._extract_examples(content)
            for ex in examples:
                node_examples.append({
                    "node_id": node_id,
                    "text": ex,
                })

        # 两两比较
        for i in range(len(node_examples)):
            for j in range(i + 1, len(node_examples)):
                ex_a = node_examples[i]
                ex_b = node_examples[j]

                # 跳过同一节点内的案例
                if ex_a["node_id"] == ex_b["node_id"]:
                    continue

                vec_a = _char_ngram_vector(ex_a["text"])
                vec_b = _char_ngram_vector(ex_b["text"])
                similarity = _cosine_similarity(vec_a, vec_b)

                if similarity >= threshold:
                    issues.append(ConsistencyIssue(
                        severity="warning",
                        issue_type="duplicate_example",
                        node_ids=[ex_a["node_id"], ex_b["node_id"]],
                        description=(
                            f"检测到重复案例（相似度 {similarity:.2f}）：\n"
                            f"  节点 {ex_a['node_id']}: {ex_a['text'][:80]}...\n"
                            f"  节点 {ex_b['node_id']}: {ex_b['text'][:80]}..."
                        ),
                        auto_fixable=True,
                    ))

        # 如果有知识图谱，也检查新案例与已注册案例的重复
        if self.knowledge_graph is not None:
            for ex in node_examples:
                similar = self.knowledge_graph.check_example_similarity(
                    ex["text"], threshold=threshold
                )
                for sim in similar:
                    # 避免与自身节点重复报告
                    if sim.existing_node_id != ex["node_id"]:
                        # 避免重复报告已在上面检测到的对
                        pair_key = tuple(sorted([ex["node_id"], sim.existing_node_id]))
                        already_reported = any(
                            tuple(sorted(iss.node_ids)) == pair_key
                            and iss.issue_type == "duplicate_example"
                            for iss in issues
                        )
                        if not already_reported:
                            issues.append(ConsistencyIssue(
                                severity="warning",
                                issue_type="duplicate_example",
                                node_ids=[ex["node_id"], sim.existing_node_id],
                                description=(
                                    f"案例与知识图谱中已注册案例重复"
                                    f"（相似度 {sim.similarity_score:.2f}）：\n"
                                    f"  新案例: {ex['text'][:80]}...\n"
                                    f"  已有案例: {sim.existing_title}"
                                ),
                                auto_fixable=True,
                            ))

        return issues

    # ------------------------------------------------------------------
    # 跨节点检测：矛盾定义
    # ------------------------------------------------------------------

    def _detect_contradicting_definitions(
        self, nodes: list[dict[str, str]]
    ) -> list[ConsistencyIssue]:
        """检测跨节点的矛盾定义。

        提取每个节点中的术语定义（**术语**：定义 格式），
        检查同一术语在不同节点是否有不同定义。

        如果已配置 GlobalKnowledgeGraph，也会与已注册概念进行比对。

        Args:
            nodes: 节点列表

        Returns:
            矛盾定义的 ConsistencyIssue 列表
        """
        issues: list[ConsistencyIssue] = []

        # 收集所有节点的术语定义
        term_definitions: dict[str, list[dict[str, str]]] = {}
        for node in nodes:
            node_id = node.get("node_id", "")
            content = node.get("node_content", "")
            definitions = self._extract_definitions(content)
            for term, definition in definitions:
                if term not in term_definitions:
                    term_definitions[term] = []
                term_definitions[term].append({
                    "node_id": node_id,
                    "definition": definition,
                })

        # 检查同一术语在不同节点的定义是否矛盾
        for term, defs in term_definitions.items():
            if len(defs) < 2:
                continue

            for i in range(len(defs)):
                for j in range(i + 1, len(defs)):
                    if defs[i]["node_id"] == defs[j]["node_id"]:
                        continue

                    vec_a = _char_ngram_vector(defs[i]["definition"])
                    vec_b = _char_ngram_vector(defs[j]["definition"])
                    similarity = _cosine_similarity(vec_a, vec_b)

                    # 相似度低于 0.7 认为定义矛盾
                    if similarity < 0.7:
                        issues.append(ConsistencyIssue(
                            severity="critical",
                            issue_type="contradicting_definition",
                            node_ids=[defs[i]["node_id"], defs[j]["node_id"]],
                            description=(
                                f"术语「{term}」在不同节点有矛盾定义"
                                f"（相似度 {similarity:.2f}）：\n"
                                f"  节点 {defs[i]['node_id']}: {defs[i]['definition'][:80]}\n"
                                f"  节点 {defs[j]['node_id']}: {defs[j]['definition'][:80]}"
                            ),
                            auto_fixable=False,
                        ))

        # 如果有知识图谱，也与已注册概念比对
        if self.knowledge_graph is not None:
            for term, defs in term_definitions.items():
                source = self.knowledge_graph.get_term_definition_source(term)
                if source is None:
                    continue
                for d in defs:
                    if d["node_id"] == source.node_id:
                        continue
                    vec_existing = _char_ngram_vector(source.definition)
                    vec_new = _char_ngram_vector(d["definition"])
                    similarity = _cosine_similarity(vec_existing, vec_new)
                    if similarity < 0.7:
                        pair_key = tuple(sorted([d["node_id"], source.node_id]))
                        already_reported = any(
                            tuple(sorted(iss.node_ids)) == pair_key
                            and iss.issue_type == "contradicting_definition"
                            for iss in issues
                        )
                        if not already_reported:
                            issues.append(ConsistencyIssue(
                                severity="critical",
                                issue_type="contradicting_definition",
                                node_ids=[d["node_id"], source.node_id],
                                description=(
                                    f"术语「{term}」的定义与知识图谱中已注册定义矛盾"
                                    f"（相似度 {similarity:.2f}）：\n"
                                    f"  当前: {d['definition'][:80]}\n"
                                    f"  已注册: {source.definition[:80]}"
                                ),
                                auto_fixable=False,
                            ))

        return issues

    # ------------------------------------------------------------------
    # 跨节点检测：断裂引用
    # ------------------------------------------------------------------

    def _detect_broken_references(
        self, nodes: list[dict[str, str]], valid_titles: list[str]
    ) -> list[ConsistencyIssue]:
        """检测断裂引用。

        扫描节点内容中的章节引用（如「参见第X章」「详见《XXX》」等），
        检查引用的章节或概念是否存在于课程中。

        Args:
            nodes: 节点列表
            valid_titles: 课程中所有有效的章节标题列表

        Returns:
            断裂引用的 ConsistencyIssue 列表
        """
        issues: list[ConsistencyIssue] = []

        # 构建有效标题集合（小写化用于模糊匹配）
        valid_titles_lower = {t.lower().strip() for t in valid_titles if t}

        # 如果有知识图谱，也将已注册概念加入有效引用集合
        valid_concepts: set[str] = set()
        if self.knowledge_graph is not None:
            valid_concepts = {name.lower() for name in self.knowledge_graph.concepts}

        for node in nodes:
            node_id = node.get("node_id", "")
            content = node.get("node_content", "")

            references = self._extract_references(content)
            for ref_text in references:
                ref_lower = ref_text.lower().strip()

                # 检查引用是否匹配任何有效标题或概念
                found = (
                    ref_lower in valid_titles_lower
                    or ref_lower in valid_concepts
                    or any(ref_lower in t for t in valid_titles_lower)
                    or any(t in ref_lower for t in valid_titles_lower if len(t) > 2)
                )

                if not found:
                    issues.append(ConsistencyIssue(
                        severity="warning",
                        issue_type="broken_reference",
                        node_ids=[node_id],
                        description=(
                            f"节点 {node_id} 中引用了不存在的章节或概念：「{ref_text}」"
                        ),
                        auto_fixable=True,
                    ))

        return issues

    # ------------------------------------------------------------------
    # 文本提取辅助方法
    # ------------------------------------------------------------------

    def _extract_examples(self, content: str) -> list[str]:
        """从内容中提取案例文本。

        识别以下格式的案例：
        - 「例如：...」「例：...」
        - 「**案例**：...」「**示例**：...」
        - 「> 案例：...」引用块格式

        Args:
            content: 节点内容文本

        Returns:
            提取的案例文本列表
        """
        examples: list[str] = []

        # 匹配 **案例/示例/例子** 格式
        pattern_bold = re.compile(
            r"\*\*(?:案例|示例|例子|Example)[^*]*\*\*[：:]\s*(.+?)(?=\n\n|\n##|\n\*\*|$)",
            re.DOTALL,
        )
        for match in pattern_bold.finditer(content):
            text = match.group(1).strip()
            if len(text) >= 20:
                examples.append(text)

        # 匹配 「例如：」「例：」格式
        pattern_inline = re.compile(
            r"(?:例如|例)[：:]\s*(.+?)(?=\n\n|\n##|$)",
            re.DOTALL,
        )
        for match in pattern_inline.finditer(content):
            text = match.group(1).strip()
            if len(text) >= 20:
                examples.append(text)

        # 匹配引用块案例
        pattern_quote = re.compile(
            r">\s*(?:案例|示例|例子)[：:]\s*(.+?)(?=\n[^>]|\n\n|$)",
            re.DOTALL,
        )
        for match in pattern_quote.finditer(content):
            text = match.group(1).strip()
            if len(text) >= 20:
                examples.append(text)

        return examples

    def _extract_definitions(self, content: str) -> list[tuple[str, str]]:
        """从内容中提取术语定义。

        识别 **术语**：定义 格式的术语定义。

        Args:
            content: 节点内容文本

        Returns:
            (术语, 定义) 元组列表
        """
        definitions: list[tuple[str, str]] = []

        pattern = re.compile(
            r"\*\*([^*]{2,20})\*\*[：:]\s*([^。\n]{10,200})"
        )
        for match in pattern.finditer(content):
            term = match.group(1).strip()
            definition = match.group(2).strip()
            # 过滤掉非定义性的加粗文本
            skip_keywords = ["案例", "示例", "例子", "注意", "提示", "总结", "小结"]
            if not any(kw in term for kw in skip_keywords):
                definitions.append((term, definition))

        return definitions

    def _extract_references(self, content: str) -> list[str]:
        """从内容中提取章节引用。

        识别以下引用格式：
        - 「参见XXX」「详见XXX」「见XXX」
        - 「在XXX中」「在XXX一节中」
        - 「参考XXX章」

        Args:
            content: 节点内容文本

        Returns:
            引用的章节/概念名称列表
        """
        references: list[str] = []

        # 匹配「参见/详见/见 + 《...》或「...」」
        pattern_see = re.compile(
            r"(?:参见|详见|见)[《「]([^》」]+)[》」]"
        )
        for match in pattern_see.finditer(content):
            references.append(match.group(1).strip())

        # 匹配「参见/详见 + 引号内容」
        pattern_see_quote = re.compile(
            r'(?:参见|详见|见)["\u201c]([^"\u201d]+)["\u201d]'
        )
        for match in pattern_see_quote.finditer(content):
            references.append(match.group(1).strip())

        # 匹配「在《...》中/一节中/章节中」
        pattern_in_section = re.compile(
            r"在[《「]([^》」]+)[》」](?:中|一节中|章节中|部分中)"
        )
        for match in pattern_in_section.finditer(content):
            references.append(match.group(1).strip())

        return references

    # ------------------------------------------------------------------
    # 原有单节点检查方法（保持 API 兼容）
    # ------------------------------------------------------------------

    def _check_discipline_consistency(
        self,
        expected_discipline: DisciplineType,
        content: str,
        course_name: str
    ) -> list[ContentMismatch]:
        """检查学科类型一致性。

        Args:
            expected_discipline: 期望的学科类型
            content: 生成的内容
            course_name: 课程名称

        Returns:
            学科不匹配问题列表
        """
        mismatches: list[ContentMismatch] = []
        content_lower = content.lower()

        expected_keywords = self.discipline_keywords.get(expected_discipline, [])
        discipline_score = sum(1 for kw in expected_keywords if kw.lower() in content_lower)

        mismatch_keywords = self.mismatch_indicators.get(expected_discipline, [])
        mismatch_score = sum(1 for kw in mismatch_keywords if kw.lower() in content_lower)

        if mismatch_score > 2:
            mismatches.append(ContentMismatch(
                type=ContentMismatchType.DISCIPLINE_MISMATCH,
                severity="critical",
                message=f"内容包含与{expected_discipline.value}学科不符的关键词",
                expected=f"{expected_discipline.value} 相关内容",
                actual=f"检测到 {mismatch_score} 个不匹配关键词",
                suggestions=[
                    "检查是否使用了正确的学科模板",
                    f"确认提示词是否针对{expected_discipline.value}学科",
                    "重新生成内容，确保学科一致性"
                ]
            ))

        if discipline_score < 1 and len(content) > 200:
            mismatches.append(ContentMismatch(
                type=ContentMismatchType.DISCIPLINE_MISMATCH,
                severity="warning",
                message=f"内容缺乏{expected_discipline.value}学科的典型特征",
                expected=f"包含{expected_discipline.value}学科关键词",
                actual=f"检测到 {discipline_score} 个相关关键词",
                suggestions=[
                    f"增加{expected_discipline.value}学科的专业术语",
                    "使用更具体的学科表达",
                    "参考该学科的典型表达方式"
                ]
            ))

        return mismatches

    def _check_topic_relevance(
        self,
        course_topic: str,
        course_name: str,
        content: str
    ) -> list[ContentMismatch]:
        """检查主题相关性。

        Args:
            course_topic: 课程主题
            course_name: 课程名称
            content: 生成的内容

        Returns:
            主题不匹配问题列表
        """
        mismatches: list[ContentMismatch] = []
        content_lower = content.lower()

        topic_keywords: list[str] = []
        if course_topic:
            topic_keywords.extend(course_topic.lower().split())
        if course_name:
            topic_keywords.extend(course_name.lower().split())

        stop_words = {"的", "与", "及", "和", "或", "在", "是", "有", "the", "and", "or", "in", "is", "are"}
        topic_keywords = [kw for kw in topic_keywords if kw not in stop_words and len(kw) > 1]

        if not topic_keywords:
            return mismatches

        relevant_keywords = [kw for kw in topic_keywords if kw in content_lower]
        relevance_ratio = len(relevant_keywords) / len(topic_keywords) if topic_keywords else 0

        if relevance_ratio < 0.3 and len(content) > 200:
            mismatches.append(ContentMismatch(
                type=ContentMismatchType.TOPIC_MISMATCH,
                severity="error",
                message="内容与课程主题相关性较低",
                expected=f"包含主题关键词: {', '.join(topic_keywords[:5])}",
                actual=f"相关度: {relevance_ratio:.1%}",
                suggestions=[
                    f"确保内容围绕'{course_topic or course_name}'展开",
                    "增加与主题相关的具体例子和解释",
                    "使用更贴近主题的专业术语"
                ]
            ))

        return mismatches

    def _check_template_structure(
        self,
        discipline_type: DisciplineType,
        content: str
    ) -> list[ContentMismatch]:
        """检查模板结构是否符合学科要求。

        Args:
            discipline_type: 学科类型
            content: 生成的内容

        Returns:
            模板不匹配问题列表
        """
        mismatches: list[ContentMismatch] = []
        config = get_discipline_config(discipline_type)

        required_sections = [s for s in config.content_sections if s.required]
        missing_sections: list[str] = []

        for section in required_sections:
            if section.name not in content and section.emoji not in content:
                missing_sections.append(section.name)

        if missing_sections:
            mismatches.append(ContentMismatch(
                type=ContentMismatchType.TEMPLATE_MISMATCH,
                severity="warning",
                message="缺少必需的学科内容板块",
                expected=f"包含板块: {', '.join([s.name for s in required_sections])}",
                actual=f"缺少: {', '.join(missing_sections)}",
                suggestions=[
                    f"按照{discipline_type.value}学科要求添加缺失的板块",
                    "参考该学科的内容结构模板",
                    "确保每个必需板块都有足够的内容"
                ]
            ))

        return mismatches

    # ------------------------------------------------------------------
    # 报告生成
    # ------------------------------------------------------------------

    def generate_validation_report(
        self,
        mismatches: list[ContentMismatch]
    ) -> dict:
        """生成验证报告。

        Args:
            mismatches: 不匹配问题列表

        Returns:
            包含 status、message、summary、issues 的报告字典
        """
        if not mismatches:
            return {
                "status": "pass",
                "message": "内容一致性验证通过",
                "issues": []
            }

        critical_issues = [m for m in mismatches if m.severity == "critical"]
        error_issues = [m for m in mismatches if m.severity == "error"]
        warning_issues = [m for m in mismatches if m.severity == "warning"]

        if critical_issues:
            status = "fail"
            message = f"发现 {len(critical_issues)} 个严重问题，需要重新生成"
        elif error_issues:
            status = "warning"
            message = f"发现 {len(error_issues)} 个错误，建议修正"
        else:
            status = "info"
            message = f"发现 {len(warning_issues)} 个建议改进的问题"

        return {
            "status": status,
            "message": message,
            "summary": {
                "critical": len(critical_issues),
                "error": len(error_issues),
                "warning": len(warning_issues),
                "total": len(mismatches)
            },
            "issues": [
                {
                    "type": issue.type.value,
                    "severity": issue.severity,
                    "message": issue.message,
                    "expected": issue.expected,
                    "actual": issue.actual,
                    "suggestions": issue.suggestions
                }
                for issue in mismatches
            ]
        }


# 全局验证器实例（无知识图谱，保持向后兼容）
content_validator = ContentConsistencyValidator()
