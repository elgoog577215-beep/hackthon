"""
Bug 5 探索性测试: chapter_id 子串匹配产生不正确的结果

**Validates: Requirements 2.9, 2.10**

Bug Condition: chapter_id 无效 AND 无精确标签匹配 → 进入 Priority 2 子串匹配
当前代码 Priority 2 逻辑:
    for n in course_nodes:
        if node_label in n.node_name or n.node_name in node_label:
            best_match_id = n.node_id
            break  # ← 取第一个匹配，不考虑相关性

此测试在未修复代码上应当 FAIL，确认 bug 存在。
"""

import sys
import os
import uuid

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# 确保 backend 在 sys.path 中
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from ai_graph_service import AIGraphService


def make_course_node(node_name: str, node_id: str = None, node_level: int = 1) -> dict:
    """创建一个课程节点"""
    return {
        "node_id": node_id or str(uuid.uuid4()),
        "node_name": node_name,
        "node_level": node_level,
    }


def make_graph_node(label: str, node_id: str = None, chapter_id: str = "invalid_id") -> dict:
    """创建一个知识图谱节点，chapter_id 默认无效以触发匹配逻辑"""
    return {
        "id": node_id or f"graph_{uuid.uuid4().hex[:8]}",
        "label": label,
        "chapter_id": chapter_id,
        "type": "concept",
    }


def char_overlap_ratio(a: str, b: str) -> float:
    """计算两个字符串的字符重叠比率（用于确定最佳匹配）"""
    if not a or not b:
        return 0.0
    common = sum(1 for c in a if c in b)
    return common / max(len(a), len(b))


def best_match_by_similarity(label: str, course_nodes: list) -> str:
    """根据相似度评分找到最佳匹配的课程节点 ID"""
    best_id = None
    best_score = -1.0
    for cn in course_nodes:
        name = cn.get("node_name", "")
        score = char_overlap_ratio(label, name)
        if score > best_score:
            best_score = score
            best_id = cn["node_id"]
    return best_id


def passes_substring_check(label: str, node_name: str) -> bool:
    """模拟当前代码的 Priority 2 子串检查"""
    return label in node_name or node_name in label


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

@st.composite
def ambiguous_matching_scenario(draw):
    """
    生成一个会触发 bug condition 的场景：

    核心思路：graph_label 是一个较长的字符串，包含多个课程节点名作为子串。
    例如：
      graph_label = "量子力学基础概念与应用"
      course_nodes = [
        "基础概念"        (子串匹配 ✓, 但相关性低 — distractor, 排在前面)
        "量子力学基础概念"  (子串匹配 ✓, 相关性高 — best match, 排在后面)
      ]

    Priority 2 的 `node_name in node_label` 对两者都成立。
    当前代码取第一个匹配（distractor），而非最相关的（best_match）。
    """
    # (graph_label, best_match_name, distractor_names)
    # 设计原则：
    #   - best_match_name 是 graph_label 的子串（触发 Priority 2）
    #   - distractor_name 也是 graph_label 的子串（也触发 Priority 2）
    #   - best_match_name 与 graph_label 的相似度更高
    #   - distractor 排在 best_match 前面
    scenarios = [
        {
            "label": "量子力学基础概念与应用",
            "best": "量子力学基础概念",
            "distractors": ["基础概念", "概念与应用"],
        },
        {
            "label": "数据结构与算法分析方法",
            "best": "数据结构与算法分析",
            "distractors": ["算法分析", "分析方法"],
        },
        {
            "label": "机器学习模型训练与优化",
            "best": "机器学习模型训练",
            "distractors": ["模型训练", "训练与优化"],
        },
        {
            "label": "计算机网络协议设计原理",
            "best": "计算机网络协议设计",
            "distractors": ["协议设计", "设计原理"],
        },
        {
            "label": "操作系统内存管理机制",
            "best": "操作系统内存管理",
            "distractors": ["内存管理", "管理机制"],
        },
        {
            "label": "编译原理语法分析技术",
            "best": "编译原理语法分析",
            "distractors": ["语法分析", "分析技术"],
        },
        {
            "label": "数据库查询优化策略",
            "best": "数据库查询优化",
            "distractors": ["查询优化", "优化策略"],
        },
        {
            "label": "人工智能搜索算法实现",
            "best": "人工智能搜索算法",
            "distractors": ["搜索算法", "算法实现"],
        },
    ]

    s = draw(st.sampled_from(scenarios))
    graph_label = s["label"]
    best_match_name = s["best"]

    # 从 distractors 中选 1-2 个
    num_distractors = draw(st.integers(min_value=1, max_value=len(s["distractors"])))
    chosen_distractors = draw(
        st.lists(
            st.sampled_from(s["distractors"]),
            min_size=num_distractors,
            max_size=num_distractors,
            unique=True,
        )
    )

    # 验证子串关系确实成立
    for d in chosen_distractors:
        assert passes_substring_check(graph_label, d), \
            f"Distractor '{d}' 不是 label '{graph_label}' 的子串匹配"
    assert passes_substring_check(graph_label, best_match_name), \
        f"Best match '{best_match_name}' 不是 label '{graph_label}' 的子串匹配"

    # 确保 label 不精确匹配任何 node_name
    all_names = chosen_distractors + [best_match_name]
    assume(graph_label not in all_names)

    # 构建课程节点列表：distractors 在前，best_match 在后
    course_nodes = []
    for i, name in enumerate(chosen_distractors):
        course_nodes.append(make_course_node(name, node_id=f"distractor_{i}"))
    course_nodes.append(make_course_node(best_match_name, node_id="best_match"))

    # 验证 best_match 确实有最高相似度
    best_id = best_match_by_similarity(graph_label, course_nodes)
    assume(best_id == "best_match")

    return {
        "graph_label": graph_label,
        "course_nodes": course_nodes,
        "best_match_id": "best_match",
        "best_match_name": best_match_name,
        "distractor_names": chosen_distractors,
    }


# ---------------------------------------------------------------------------
# Property Test
# ---------------------------------------------------------------------------

class TestChapterIdSubstringMatchingBug:
    """
    **Validates: Requirements 2.9, 2.10**

    Bug Condition Property: 当 chapter_id 无效且无精确标签匹配时，
    子串匹配应选择最相关（最高相似度）的课程节点，
    而非任意的第一个子串匹配结果。

    在未修复代码上，此测试应当 FAIL：
    当前代码使用 for + break 取第一个子串匹配，
    结果取决于课程节点的遍历顺序而非相关性。
    """

    @given(scenario=ambiguous_matching_scenario())
    @settings(max_examples=50, deadline=None)
    def test_substring_match_selects_most_similar_node(self, scenario):
        """
        Property 1: Bug Condition — Substring Matching Produces Incorrect chapter_id

        给定：
        - graph_label 较长（如 "量子力学基础概念与应用"）
        - best_match 是 label 的长子串（如 "量子力学基础概念"）
        - distractor 是 label 的短子串（如 "基础概念"），排在列表前面

        期望：匹配结果是相似度最高的 best_match
        实际（bug）：匹配结果是列表中第一个子串匹配的 distractor
        """
        graph_label = scenario["graph_label"]
        course_nodes = scenario["course_nodes"]
        best_match_id = scenario["best_match_id"]

        graph_node = make_graph_node(
            label=graph_label,
            node_id="test_node_1",
            chapter_id="invalid_chapter_id",
        )
        dummy_node = {
            "id": "test_node_2",
            "label": "dummy",
            "chapter_id": course_nodes[0]["node_id"],
            "type": "root",
        }
        graph_data = {
            "nodes": [graph_node, dummy_node],
            "edges": [
                {"source": "test_node_2", "target": "test_node_1",
                 "relation": "contains"}
            ],
        }

        service = AIGraphService.__new__(AIGraphService)
        result = service._validate_and_fix_knowledge_graph(
            graph_data, course_nodes
        )

        result_node = None
        for n in result["nodes"]:
            if n["id"] == "test_node_1":
                result_node = n
                break

        assert result_node is not None, "测试节点被意外移除"

        assert result_node["chapter_id"] == best_match_id, (
            f"chapter_id 匹配不准确: "
            f"label='{graph_label}', "
            f"got='{result_node['chapter_id']}', "
            f"expected='{best_match_id}' (最高相似度). "
            f"课程节点: {[cn['node_name'] for cn in course_nodes]}"
        )
