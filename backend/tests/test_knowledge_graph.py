"""
GlobalKnowledgeGraph 单元测试。
覆盖 task 4.1 的所有功能点。
"""

import os
import sys

import pytest

# 将 backend 目录和项目根目录加入 sys.path
_backend_dir = os.path.join(os.path.dirname(__file__), "..")
_project_root = os.path.join(_backend_dir, "..")
sys.path.insert(0, _backend_dir)
sys.path.insert(0, _project_root)

from knowledge_graph import GlobalKnowledgeGraph, TermSource, _char_ngram_vector, _cosine_similarity
from models import SimilarExample


# ---------------------------------------------------------------------------
# register_concept 测试
# ---------------------------------------------------------------------------

class TestRegisterConcept:
    """测试概念注册功能。"""

    def test_register_new_concept(self):
        """注册新概念应记录定义和首次出现节点。"""
        g = GlobalKnowledgeGraph()
        g.register_concept("机器学习", "一种人工智能方法", "node_1", "第一章")

        assert "机器学习" in g.concepts
        assert g.concepts["机器学习"]["definition"] == "一种人工智能方法"
        assert g.concepts["机器学习"]["first_occurrence"] == "node_1"
        assert g.concepts["机器学习"]["context"] == "第一章"

    def test_register_duplicate_concept_keeps_first(self):
        """重复注册同一概念应保留首次定义。"""
        g = GlobalKnowledgeGraph()
        g.register_concept("机器学习", "定义A", "node_1")
        g.register_concept("机器学习", "定义B", "node_2")

        assert g.concepts["机器学习"]["definition"] == "定义A"
        assert g.concepts["机器学习"]["first_occurrence"] == "node_1"

    def test_register_concept_tracks_occurrences(self):
        """注册概念应追踪所有出现的节点。"""
        g = GlobalKnowledgeGraph()
        g.register_concept("机器学习", "定义A", "node_1")
        g.register_concept("机器学习", "定义B", "node_2")

        assert g.concept_occurrences["机器学习"] == ["node_1", "node_2"]

    def test_register_concept_default_context(self):
        """不提供 context 时应默认为空字符串。"""
        g = GlobalKnowledgeGraph()
        g.register_concept("测试", "测试定义", "node_1")

        assert g.concepts["测试"]["context"] == ""


# ---------------------------------------------------------------------------
# register_example 测试
# ---------------------------------------------------------------------------

class TestRegisterExample:
    """测试案例注册功能。"""

    def test_register_example(self):
        """注册案例应存储标题、摘要和节点 ID。"""
        g = GlobalKnowledgeGraph()
        g.register_example("电商推荐系统", "某电商平台使用协同过滤算法实现个性化推荐", "node_1")

        assert len(g.examples) == 1
        info = list(g.examples.values())[0]
        assert info["title"] == "电商推荐系统"
        assert info["summary"] == "某电商平台使用协同过滤算法实现个性化推荐"
        assert info["node_id"] == "node_1"

    def test_register_multiple_examples(self):
        """注册多个不同案例应全部保存。"""
        g = GlobalKnowledgeGraph()
        g.register_example("案例A", "摘要A", "node_1")
        g.register_example("案例B", "摘要B", "node_2")

        assert len(g.examples) == 2

    def test_register_same_title_overwrites(self):
        """注册相同标题的案例应覆盖（相同 MD5 键）。"""
        g = GlobalKnowledgeGraph()
        g.register_example("相同标题", "摘要1", "node_1")
        g.register_example("相同标题", "摘要2", "node_2")

        assert len(g.examples) == 1
        info = list(g.examples.values())[0]
        assert info["summary"] == "摘要2"


# ---------------------------------------------------------------------------
# register_formula 测试
# ---------------------------------------------------------------------------

class TestRegisterFormula:
    """测试公式注册功能。"""

    def test_register_formula(self):
        """注册公式应存储公式文本、描述和节点 ID。"""
        g = GlobalKnowledgeGraph()
        g.register_formula("E=mc^2", "质能方程", "node_1")

        assert len(g.formulas) == 1
        info = list(g.formulas.values())[0]
        assert info["formula"] == "E=mc^2"
        assert info["description"] == "质能方程"
        assert info["node_id"] == "node_1"

    def test_register_duplicate_formula_keeps_first(self):
        """重复注册相同公式应保留首次记录。"""
        g = GlobalKnowledgeGraph()
        g.register_formula("E=mc^2", "描述1", "node_1")
        g.register_formula("E=mc^2", "描述2", "node_2")

        assert len(g.formulas) == 1
        info = list(g.formulas.values())[0]
        assert info["description"] == "描述1"


# ---------------------------------------------------------------------------
# get_context_for_node 测试
# ---------------------------------------------------------------------------

class TestGetContextForNode:
    """测试节点上下文获取功能。"""

    def test_empty_graph_returns_empty(self):
        """空图谱应返回空字符串。"""
        g = GlobalKnowledgeGraph()
        assert g.get_context_for_node("node_1") == ""

    def test_excludes_own_concepts(self):
        """应排除当前节点已涉及的概念。"""
        g = GlobalKnowledgeGraph()
        g.register_concept("概念A", "定义A", "node_1")
        g.register_concept("概念B", "定义B", "node_2")

        context = g.get_context_for_node("node_1")
        assert "概念B" in context
        assert "概念A" not in context

    def test_includes_examples(self):
        """上下文应包含已使用的案例。"""
        g = GlobalKnowledgeGraph()
        g.register_example("电商案例", "某电商平台的推荐系统", "node_1")

        context = g.get_context_for_node("node_2")
        assert "电商案例" in context

    def test_max_items_limits_concepts(self):
        """max_items 应限制返回的概念数量。"""
        g = GlobalKnowledgeGraph()
        for i in range(20):
            g.register_concept(f"概念{i}", f"定义{i}", "node_other")

        context = g.get_context_for_node("node_1", max_items=5)
        # 应最多包含 5 个概念
        concept_count = context.count("- **")
        assert concept_count <= 5


# ---------------------------------------------------------------------------
# get_used_example_titles 测试
# ---------------------------------------------------------------------------

class TestGetUsedExampleTitles:
    """测试获取已使用案例标题列表。"""

    def test_empty_graph(self):
        """空图谱应返回空列表。"""
        g = GlobalKnowledgeGraph()
        assert g.get_used_example_titles() == []

    def test_returns_all_titles(self):
        """应返回所有已注册案例的标题。"""
        g = GlobalKnowledgeGraph()
        g.register_example("案例A", "摘要A", "node_1")
        g.register_example("案例B", "摘要B", "node_2")

        titles = g.get_used_example_titles()
        assert "案例A" in titles
        assert "案例B" in titles
        assert len(titles) == 2


# ---------------------------------------------------------------------------
# check_example_similarity 测试
# ---------------------------------------------------------------------------

class TestCheckExampleSimilarity:
    """测试案例相似度检测功能。"""

    def test_identical_text_returns_high_similarity(self):
        """完全相同的文本应返回高相似度。"""
        g = GlobalKnowledgeGraph()
        g.register_example("电商推荐", "某电商平台使用协同过滤算法实现个性化推荐系统", "node_1")

        results = g.check_example_similarity("某电商平台使用协同过滤算法实现个性化推荐系统")
        assert len(results) == 1
        assert results[0].similarity_score >= 0.99
        assert results[0].existing_title == "电商推荐"

    def test_different_text_returns_empty(self):
        """完全不同的文本应返回空列表。"""
        g = GlobalKnowledgeGraph()
        g.register_example("电商推荐", "某电商平台使用协同过滤算法实现个性化推荐系统", "node_1")

        results = g.check_example_similarity("量子力学中的薛定谔方程描述了微观粒子的波函数演化")
        assert len(results) == 0

    def test_custom_threshold(self):
        """自定义阈值应影响结果。"""
        g = GlobalKnowledgeGraph()
        g.register_example("案例", "这是一个关于机器学习的案例说明文本", "node_1")

        # 低阈值应更容易匹配
        results_low = g.check_example_similarity("这是一个关于深度学习的案例说明文本", threshold=0.5)
        results_high = g.check_example_similarity("这是一个关于深度学习的案例说明文本", threshold=0.99)

        assert len(results_low) >= len(results_high)

    def test_returns_similar_example_model(self):
        """返回结果应为 SimilarExample 模型。"""
        g = GlobalKnowledgeGraph()
        g.register_example("测试案例", "这是一段完全相同的测试文本用于验证相似度检测功能", "node_1")

        results = g.check_example_similarity("这是一段完全相同的测试文本用于验证相似度检测功能")
        assert len(results) == 1
        assert isinstance(results[0], SimilarExample)
        assert results[0].existing_node_id == "node_1"

    def test_empty_graph_returns_empty(self):
        """空图谱应返回空列表。"""
        g = GlobalKnowledgeGraph()
        results = g.check_example_similarity("任意文本")
        assert results == []


# ---------------------------------------------------------------------------
# get_term_definition_source 测试
# ---------------------------------------------------------------------------

class TestGetTermDefinitionSource:
    """测试术语定义来源查找。"""

    def test_existing_term(self):
        """已注册的术语应返回 TermSource。"""
        g = GlobalKnowledgeGraph()
        g.register_concept("机器学习", "一种AI方法", "node_1", "第一章")

        source = g.get_term_definition_source("机器学习")
        assert source is not None
        assert isinstance(source, TermSource)
        assert source.term == "机器学习"
        assert source.definition == "一种AI方法"
        assert source.node_id == "node_1"
        assert source.context == "第一章"

    def test_nonexistent_term(self):
        """未注册的术语应返回 None。"""
        g = GlobalKnowledgeGraph()
        assert g.get_term_definition_source("不存在的术语") is None


# ---------------------------------------------------------------------------
# check_consistency 测试（保留兼容性）
# ---------------------------------------------------------------------------

class TestCheckConsistency:
    """测试内容一致性检查（保留原有接口兼容）。"""

    def test_no_issues_for_consistent_content(self):
        """一致的内容不应产生问题。"""
        g = GlobalKnowledgeGraph()
        g.register_concept("机器学习", "一种人工智能方法", "node_1")

        content = "**机器学习**：一种人工智能方法。"
        issues = g.check_consistency("node_2", content)
        assert len(issues) == 0

    def test_detects_inconsistent_definition(self):
        """不一致的定义应被检测到。"""
        g = GlobalKnowledgeGraph()
        g.register_concept("机器学习", "一种人工智能方法，通过数据学习模式", "node_1")

        content = "**机器学习**：一种完全不同的概念，与统计学无关的方法论"
        issues = g.check_consistency("node_2", content)
        assert len(issues) >= 1
        assert issues[0]["type"] == "概念不一致"


# ---------------------------------------------------------------------------
# 辅助函数测试
# ---------------------------------------------------------------------------

class TestHelperFunctions:
    """测试 n-gram 和余弦相似度辅助函数。"""

    def test_char_ngram_vector(self):
        """字符 n-gram 向量应正确生成。"""
        vec = _char_ngram_vector("abc")
        assert "ab" in vec
        assert "bc" in vec
        assert len(vec) == 2

    def test_char_ngram_empty_string(self):
        """空字符串应返回空向量。"""
        vec = _char_ngram_vector("")
        assert vec == {}

    def test_cosine_similarity_identical(self):
        """相同向量的余弦相似度应为 1.0。"""
        vec = {"ab": 2, "bc": 1}
        assert abs(_cosine_similarity(vec, vec) - 1.0) < 1e-9

    def test_cosine_similarity_orthogonal(self):
        """无交集向量的余弦相似度应为 0.0。"""
        vec_a = {"ab": 1}
        vec_b = {"cd": 1}
        assert _cosine_similarity(vec_a, vec_b) == 0.0

    def test_cosine_similarity_empty(self):
        """空向量的余弦相似度应为 0.0。"""
        assert _cosine_similarity({}, {"ab": 1}) == 0.0
        assert _cosine_similarity({"ab": 1}, {}) == 0.0
        assert _cosine_similarity({}, {}) == 0.0
