from __future__ import annotations

from course_retrieval import (
    build_course_source_context,
    build_course_retrieval_queries,
    build_outline_research_instruction,
    build_outline_research_proposal,
)
from content_blocks import set_node_content_blocks
from course_versioning import build_blueprint_draft


def _course() -> dict:
    return {
        "course_id": "course-research",
        "course_name": "Linear algebra",
        "difficulty": "intermediate",
        "course_intent": {
            "type": "systematic",
            "learning_goal": "Understand eigenvalues",
        },
        "learner_starting_profile": {
            "summary": "PRIVATE_PROFILE_SENTINEL student@example.com",
        },
        "nodes": [
            {
                "node_id": "chapter-1",
                "parent_node_id": "root",
                "node_level": 1,
                "node_name": "Matrices",
                "learning_objective": "Understand matrices",
            },
            {
                "node_id": "section-1",
                "parent_node_id": "chapter-1",
                "node_level": 2,
                "node_name": "Eigenvalues",
                "learning_objective": "Compute eigenvalues",
                "prerequisite_node_ids": [],
            },
        ],
    }


def _package() -> dict:
    return {
        "schema_version": "retrieval_package_v1",
        "status": "completed",
        "revision": 1,
        "sources": [
            {
                "source_id": "src_a",
                "title": "Open linear algebra",
                "url": "https://example.edu/linear-algebra",
                "domain": "example.edu",
                "excerpt": "Eigenvalues should follow matrix transformations.",
                "trust_tier": "tier_a",
            },
            {
                "source_id": "src_b",
                "title": "Practice sequence",
                "url": "https://example.com/practice",
                "domain": "example.com",
                "excerpt": "Introduce diagonalization after eigenvectors.",
                "trust_tier": "tier_b",
            },
        ],
        "receipt": {"status": "completed"},
    }


def test_course_queries_only_use_public_course_contract():
    course = _course()
    request = {
        "subject": "Linear algebra",
        "difficulty": "intermediate",
        "requirements": "PRIVATE_REQUIREMENT_SENTINEL",
        "learner_profile_summary": "PRIVATE_PROFILE_SENTINEL",
        "course_intent": course["course_intent"],
    }

    queries = build_course_retrieval_queries(course, request)

    assert 1 <= len(queries) <= 12
    joined = " ".join(queries)
    assert "Linear algebra" in joined
    assert "Compute eigenvalues" in joined
    assert "PRIVATE_PROFILE_SENTINEL" not in joined
    assert "PRIVATE_REQUIREMENT_SENTINEL" not in joined
    assert "student@example.com" not in joined


def test_programming_course_queries_are_concise_and_do_not_add_academic_boilerplate():
    course = {
        "course_name": "Unity 游戏编程系统实战",
        "difficulty": "intermediate",
        "course_intent": {
            "type": "systematic",
            "learning_goal": "掌握 Unity 游戏开发工作流",
        },
        "nodes": [
            {
                "node_level": 2,
                "node_name": "C# 脚本类创建与挂载机制",
                "learning_objective": (
                    "能够使用 Visual Studio 创建自定义 MonoBehaviour 子类并将其正确拖拽"
                    "挂载到 GameObject 上"
                ),
            },
        ],
    }

    queries = build_course_retrieval_queries(
        course,
        {
            "subject": "Unity 游戏编程系统实战",
            "difficulty": "intermediate",
            "course_intent": course["course_intent"],
        },
    )

    assert queries
    assert max(map(len, queries)) <= 120
    assert all("course prerequisite learning objective open education" not in query for query in queries)
    assert any("MonoBehaviour" in query or "GameObject" in query for query in queries)


def test_research_instruction_labels_sources_and_does_not_copy_full_pages():
    instruction = build_outline_research_instruction(_package())
    assert "[src_a]" in instruction
    assert "[src_b]" in instruction
    assert "https://" not in instruction
    assert len(instruction) < 5000


def test_outline_research_proposal_preserves_base_candidate_diff_and_sources():
    course = _course()
    base = build_blueprint_draft(course)
    proposal = build_outline_research_proposal(
        course=course,
        base_draft=base,
        model_result={
            "summary": "Add a prerequisite section.",
            "operations": [
                {
                    "op": "add_node",
                    "temp_ref": "tmp-vectors",
                    "node_level": 2,
                    "parent_ref": "chapter-1",
                    "after_ref": None,
                    "node_name": "Eigenvectors",
                    "learning_objective": "Compute eigenvectors",
                    "prerequisite_refs": [],
                }
            ],
        },
        retrieval_package=_package(),
    )

    assert proposal["status"] == "waiting_for_confirmation"
    assert proposal["base_draft"]["nodes"] == base["nodes"]
    assert proposal["candidate_draft"]["nodes"] != base["nodes"]
    assert proposal["diff"]["added"]
    assert proposal["reason"] == "Add a prerequisite section."
    assert proposal["source_ids"] == ["src_a", "src_b"]
    assert proposal["tier_b_source_ids"] == ["src_b"]


def test_confirmed_sources_get_stable_inline_citations_and_block_metadata():
    package = _package()
    course = {
        "retrieval_package": package,
        "retrieval_acceptance": {"accepted_source_ids": ["src_b"]},
    }
    context, citation_map, source_cards = build_course_source_context(course)

    assert "〔S1〕" in context
    assert "〔S2〕" in context
    assert citation_map == {"S1": "src_a", "S2": "src_b"}
    assert [item["source_id"] for item in source_cards] == ["src_a", "src_b"]

    node = {
        "node_id": "section-1",
        "node_name": "Eigenvalues",
        "citation_map": citation_map,
        "source_cards": source_cards,
    }
    blocks = set_node_content_blocks(
        node,
        "## Concept\n\nDiagonalization follows eigenvectors.〔S2〕",
    )
    assert blocks[0]["metadata"]["citations"] == {"S2": "src_b"}
    assert blocks[0]["metadata"]["source_ids"] == ["src_b"]
