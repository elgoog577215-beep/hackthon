"""
Bug 5 Preservation Property Test — Valid chapter_id Values Unchanged

**Validates: Requirements 3.9, 3.10**

Preservation Property: When a graph node's chapter_id is already in valid_chapter_ids,
_validate_and_fix_knowledge_graph does NOT modify it.

This test should PASS on unfixed code, confirming baseline behavior to preserve.
"""

import sys
import os
import uuid
import copy

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Ensure backend is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from ai_graph_service import AIGraphService


def make_course_node(node_name: str, node_id: str = None, node_level: int = 1) -> dict:
    """创建一个课程节点"""
    return {
        "node_id": node_id or str(uuid.uuid4()),
        "node_name": node_name,
        "node_level": node_level,
    }


def make_graph_node(label: str, node_id: str = None, chapter_id: str = None, node_type: str = "concept") -> dict:
    """创建一个知识图谱节点"""
    return {
        "id": node_id or f"graph_{uuid.uuid4().hex[:8]}",
        "label": label,
        "chapter_id": chapter_id,
        "type": node_type,
    }


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

@st.composite
def valid_chapter_id_scenario(draw):
    """
    生成一个 chapter_id 已经有效的场景。

    构造：
    - 2-5 个课程节点，每个有唯一 node_id
    - 1 个知识图谱节点，其 chapter_id 是某个课程节点的 node_id（即有效）
    - 1 个 root 节点（确保图谱结构有效）
    - 连接边确保节点不被过滤为孤立节点

    期望：_validate_and_fix_knowledge_graph 不修改该 chapter_id
    """
    # Generate 2-5 course nodes with unique IDs
    num_nodes = draw(st.integers(min_value=2, max_value=5))
    course_nodes = []
    for i in range(num_nodes):
        name = draw(st.text(
            alphabet=st.characters(whitelist_categories=('L',)),
            min_size=2, max_size=10
        ))
        course_nodes.append(make_course_node(
            node_name=name,
            node_id=f"course_{i}_{uuid.uuid4().hex[:6]}",
            node_level=i + 1,
        ))

    # Pick a random valid chapter_id from the course nodes
    chosen_index = draw(st.integers(min_value=0, max_value=len(course_nodes) - 1))
    valid_chapter_id = course_nodes[chosen_index]["node_id"]

    # Create graph node with valid chapter_id
    graph_label = draw(st.text(
        alphabet=st.characters(whitelist_categories=('L',)),
        min_size=1, max_size=15
    ))
    test_node = make_graph_node(
        label=graph_label,
        node_id="test_node",
        chapter_id=valid_chapter_id,
        node_type="concept",
    )

    # Create a root node with a valid chapter_id too
    root_node = make_graph_node(
        label="root",
        node_id="root_node",
        chapter_id=course_nodes[0]["node_id"],
        node_type="root",
    )

    return {
        "course_nodes": course_nodes,
        "test_node": test_node,
        "root_node": root_node,
        "valid_chapter_id": valid_chapter_id,
    }


# ---------------------------------------------------------------------------
# Property Test
# ---------------------------------------------------------------------------

class TestChapterIdPreservation:
    """
    **Validates: Requirements 3.9, 3.10**

    Preservation Property: When chapter_id is already in valid_chapter_ids,
    the validation function does NOT modify it.
    """

    @given(scenario=valid_chapter_id_scenario())
    @settings(max_examples=50, deadline=None)
    def test_valid_chapter_id_remains_unchanged(self, scenario):
        """
        Property 2: Preservation — Valid chapter_ids are not modified.

        **Validates: Requirements 3.9, 3.10**

        Given a graph node whose chapter_id is already a valid course node ID,
        after running _validate_and_fix_knowledge_graph, the chapter_id should
        remain exactly the same.
        """
        course_nodes = scenario["course_nodes"]
        test_node = scenario["test_node"]
        root_node = scenario["root_node"]
        valid_chapter_id = scenario["valid_chapter_id"]

        graph_data = {
            "nodes": [root_node, test_node],
            "edges": [
                {
                    "source": "root_node",
                    "target": "test_node",
                    "relation": "contains",
                }
            ],
        }

        # Deep copy to verify no mutation of the original chapter_id
        original_chapter_id = test_node["chapter_id"]

        service = AIGraphService.__new__(AIGraphService)
        result = service._validate_and_fix_knowledge_graph(graph_data, course_nodes)

        # Find the test node in the result
        result_node = None
        for n in result["nodes"]:
            if n["id"] == "test_node":
                result_node = n
                break

        assert result_node is not None, "Test node was unexpectedly removed from graph"

        assert result_node["chapter_id"] == valid_chapter_id, (
            f"Valid chapter_id was modified! "
            f"original='{original_chapter_id}', "
            f"after_validation='{result_node['chapter_id']}', "
            f"valid_ids={[cn['node_id'] for cn in course_nodes]}"
        )
