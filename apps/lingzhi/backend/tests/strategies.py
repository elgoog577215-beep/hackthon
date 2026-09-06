"""Hypothesis custom strategies for course-generation-optimization tests.

Provides composite strategies for generating valid domain objects:
nodes, course data, content, knowledge entries, and generation configs.

Requirements: 16.1, 16.2, 16.3
"""
from __future__ import annotations

import uuid

from hypothesis import strategies as st

from models import NodeStatus


# ---------------------------------------------------------------------------
# node_strategy
# ---------------------------------------------------------------------------

@st.composite
def node_strategy(draw: st.DrawFn) -> dict:
    """Generate a valid node dict.

    Fields: node_id, node_name, node_level (1 or 2), node_content,
    generation_status, parent_node_id.
    """
    node_level = draw(st.sampled_from([1, 2]))
    node_id = draw(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
            min_size=3,
            max_size=20,
        ).map(lambda s: f"L{node_level}-{s}")
    )
    node_name = draw(
        st.text(min_size=1, max_size=60).filter(lambda s: s.strip() != "")
    )
    node_content = draw(st.text(max_size=500))
    generation_status = draw(
        st.sampled_from([s.value for s in NodeStatus])
    )
    parent_node_id = (
        "root"
        if node_level == 1
        else draw(
            st.text(
                alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
                min_size=3,
                max_size=20,
            ).map(lambda s: f"L1-{s}")
        )
    )

    return {
        "node_id": node_id,
        "node_name": node_name,
        "node_level": node_level,
        "node_content": node_content,
        "generation_status": generation_status,
        "parent_node_id": parent_node_id,
    }


# ---------------------------------------------------------------------------
# course_data_strategy
# ---------------------------------------------------------------------------

@st.composite
def course_data_strategy(draw: st.DrawFn) -> dict:
    """Generate a valid course data dict.

    Fields: course_id, course_name, nodes (list of node dicts), discipline.
    """
    course_id = draw(
        st.uuids().map(str)
    )
    course_name = draw(
        st.text(min_size=1, max_size=80).filter(lambda s: s.strip() != "")
    )
    discipline = draw(
        st.sampled_from(["natural_science", "humanities", "skill_based"])
    )

    # Generate 1-3 L1 nodes, each with 0-3 L2 children
    l1_count = draw(st.integers(min_value=1, max_value=3))
    nodes: list[dict] = []

    for i in range(1, l1_count + 1):
        l1_id = f"L1-{i}"
        nodes.append({
            "node_id": l1_id,
            "parent_node_id": "root",
            "node_name": f"第{i}章 {draw(st.text(min_size=1, max_size=30).filter(lambda s: s.strip() != ''))}",
            "node_level": 1,
            "node_content": "",
            "node_type": "original",
            "generation_status": NodeStatus.PENDING.value,
            "generated_chars": 0,
            "error_summary": None,
        })

        l2_count = draw(st.integers(min_value=0, max_value=3))
        for j in range(1, l2_count + 1):
            nodes.append({
                "node_id": f"L2-{i}-{j}",
                "parent_node_id": l1_id,
                "node_name": f"{i}.{j} {draw(st.text(min_size=1, max_size=30).filter(lambda s: s.strip() != ''))}",
                "node_level": 2,
                "node_content": "",
                "node_type": "original",
                "generation_status": NodeStatus.PENDING.value,
                "generated_chars": 0,
                "error_summary": None,
            })

    return {
        "course_id": course_id,
        "course_name": course_name,
        "discipline": discipline,
        "nodes": nodes,
    }


# ---------------------------------------------------------------------------
# content_strategy
# ---------------------------------------------------------------------------

@st.composite
def content_strategy(draw: st.DrawFn) -> str:
    """Generate valid markdown content with headings and paragraphs."""
    heading = draw(
        st.text(min_size=1, max_size=40).filter(lambda s: s.strip() != "")
    )
    num_paragraphs = draw(st.integers(min_value=1, max_value=5))

    parts = [f"## {heading}\n"]
    for _ in range(num_paragraphs):
        para = draw(
            st.text(min_size=10, max_size=200).filter(lambda s: s.strip() != "")
        )
        parts.append(f"\n{para}\n")

    # Optionally add a sub-heading with more content
    if draw(st.booleans()):
        sub_heading = draw(
            st.text(min_size=1, max_size=30).filter(lambda s: s.strip() != "")
        )
        sub_para = draw(
            st.text(min_size=10, max_size=150).filter(lambda s: s.strip() != "")
        )
        parts.append(f"\n### {sub_heading}\n\n{sub_para}\n")

    return "".join(parts)


# ---------------------------------------------------------------------------
# knowledge_entry_strategy
# ---------------------------------------------------------------------------

@st.composite
def knowledge_entry_strategy(draw: st.DrawFn) -> dict:
    """Generate a knowledge graph entry (concept + example + formula)."""
    concept_name = draw(
        st.text(min_size=2, max_size=30).filter(lambda s: s.strip() != "")
    )
    definition = draw(
        st.text(min_size=5, max_size=100).filter(lambda s: s.strip() != "")
    )
    node_id = draw(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
            min_size=3,
            max_size=15,
        ).map(lambda s: f"L2-{s}")
    )
    example_title = draw(
        st.text(min_size=2, max_size=40).filter(lambda s: s.strip() != "")
    )
    # Ensure summary is at least 50 chars as required by the spec
    example_summary = draw(
        st.text(min_size=50, max_size=200).filter(lambda s: s.strip() != "")
    )
    formula = draw(
        st.text(min_size=3, max_size=50).filter(lambda s: s.strip() != "")
    )
    formula_desc = draw(
        st.text(min_size=3, max_size=60).filter(lambda s: s.strip() != "")
    )

    return {
        "concept_name": concept_name,
        "definition": definition,
        "node_id": node_id,
        "example_title": example_title,
        "example_summary": example_summary,
        "formula": formula,
        "formula_description": formula_desc,
    }


# ---------------------------------------------------------------------------
# generation_config_strategy
# ---------------------------------------------------------------------------

@st.composite
def generation_config_strategy(draw: st.DrawFn) -> dict:
    """Generate a NodeGenerationConfig-compatible dict."""
    difficulty = draw(
        st.sampled_from(["beginner", "intermediate", "advanced"])
    )
    style = draw(
        st.sampled_from(["academic", "industrial", "socratic", "humorous"])
    )
    min_words = draw(st.integers(min_value=200, max_value=1000))
    max_words = draw(st.integers(min_value=min_words, max_value=5000))
    include_code = draw(st.booleans())
    include_exercises = draw(st.booleans())
    custom_instruction = draw(
        st.one_of(
            st.none(),
            st.text(min_size=1, max_size=100).filter(lambda s: s.strip() != ""),
        )
    )

    return {
        "difficulty": difficulty,
        "style": style,
        "target_word_range": (min_words, max_words),
        "include_code_examples": include_code,
        "include_exercises": include_exercises,
        "custom_instruction": custom_instruction,
    }
