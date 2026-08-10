from __future__ import annotations

import pytest

from content_blocks import set_node_content_blocks
import course_service as course_service_module
from course_retrieval import (
    build_course_retrieval_queries,
    build_course_source_context,
    build_knowledge_gap_retrieval_queries,
    build_outline_research_instruction,
    build_outline_research_proposal,
    build_topic_retrieval_queries,
    merge_course_retrieval_packages,
)
from course_versioning import build_blueprint_draft
from course_service import CourseService
from web_retrieval import PURPOSE_LIMITS


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


def test_topic_retrieval_can_start_before_outline_without_private_fields():
    queries = build_topic_retrieval_queries({
        "subject": "牛顿运动定律",
        "difficulty": "intermediate",
        "course_intent": {
            "type": "inquiry",
            "core_question": "力如何改变运动？",
            "existing_understanding": "PRIVATE_PROFILE_SENTINEL student@example.com",
        },
        "requirements": "PRIVATE_REQUIREMENT_SENTINEL",
        "learner_profile_summary": "PRIVATE_PROFILE_SENTINEL",
    })

    assert queries
    joined = " ".join(queries)
    assert "牛顿运动定律" in joined
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


def test_course_research_samples_the_outline_without_bursting_upstream_engines():
    course = {
        "course_name": "Unity systems",
        "course_intent": {"learning_goal": "Build a complete game"},
        "nodes": [
            {
                "node_level": 2,
                "node_name": f"Topic {index}",
                "learning_objective": f"Practice API{index}",
            }
            for index in range(9)
        ],
    }

    queries = build_course_retrieval_queries(
        course,
        {"subject": "Unity systems", "course_intent": course["course_intent"]},
    )

    assert len(queries) == 4
    assert "Topic 0" in " ".join(queries)
    assert "Topic 4" in " ".join(queries)
    assert "Topic 8" in " ".join(queries)
    assert PURPOSE_LIMITS["course"]["concurrency"] == 2


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


def test_outline_research_proposal_accepts_source_backed_no_change_result():
    course = _course()
    base = build_blueprint_draft(course)

    proposal = build_outline_research_proposal(
        course=course,
        base_draft=base,
        model_result={
            "summary": "The sources support the existing course sequence.",
            "operations": [],
        },
        retrieval_package=_package(),
    )

    assert proposal["operations"] == []
    assert proposal["candidate_draft"]["nodes"] == base["nodes"]
    assert proposal["diff"]["added"] == []
    assert proposal["diff"]["removed"] == []
    assert proposal["reason"] == "The sources support the existing course sequence."


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


def test_knowledge_gap_queries_only_include_public_graph_terms():
    course = _course()
    course["generation_request"] = {
        "subject": "Linear algebra",
        "requirements": "PRIVATE_REQUIREMENT_SENTINEL",
    }
    graph = {
        "nodes": [
            {
                "knowledge_key": "kp-eigenvalue",
                "name": "Eigenvalue boundary",
                "statement": "Explain repeated eigenvalues",
                "detail_status": "skeleton",
                "source_refs": [],
                "counterexamples": [],
                "private_note": "PRIVATE_PROFILE_SENTINEL student@example.com",
            },
        ],
    }

    queries = build_knowledge_gap_retrieval_queries(course, graph)

    assert queries
    joined = " ".join(queries)
    assert "Eigenvalue" in joined
    assert "PRIVATE_PROFILE_SENTINEL" not in joined
    assert "PRIVATE_REQUIREMENT_SENTINEL" not in joined
    assert "student@example.com" not in joined


def test_retrieval_package_merge_creates_new_immutable_revision_and_deduplicates():
    base = _package()
    base["queries"] = ["base query"]
    base["receipt"] = {
        "status": "completed",
        "query_count": 1,
        "duration_ms": 20,
        "cache_hit_count": 0,
    }
    supplement = {
        "schema_version": "retrieval_package_v1",
        "status": "completed",
        "revision": 2,
        "queries": ["gap query"],
        "sources": [
            dict(base["sources"][0]),
            {
                "source_id": "src_c",
                "url": "https://example.edu/eigenvalue-boundary",
                "title": "Eigenvalue boundary",
                "excerpt": "A boundary case.",
                "trust_tier": "tier_a",
            },
        ],
        "receipt": {
            "status": "completed",
            "query_count": 1,
            "duration_ms": 30,
            "cache_hit_count": 1,
        },
    }

    merged = merge_course_retrieval_packages(base, supplement)

    assert [item["source_id"] for item in base["sources"]] == ["src_a", "src_b"]
    assert [item["source_id"] for item in merged["sources"]] == ["src_a", "src_b", "src_c"]
    assert merged["revision"] == 2
    assert merged["coverage"]["stages"] == ["outline", "knowledge_gap"]
    assert merged["receipt"]["duration_ms"] == 50
    assert merged["stage_receipts"]["outline"]["query_count"] == 1
    assert merged["stage_receipts"]["knowledge_gap"]["query_count"] == 1
    assert len(merged["package_hash"]) == 64


@pytest.mark.asyncio
async def test_course_service_runs_gap_retrieval_after_graph_revision(monkeypatch):
    supplement = {
        "schema_version": "retrieval_package_v1",
        "status": "completed",
        "revision": 2,
        "queries": ["Linear algebra Eigenvalue official"],
        "sources": [{
            "source_id": "src_gap",
            "url": "https://example.edu/eigenvalue",
            "title": "Eigenvalue definition",
            "excerpt": "An eigenvalue is defined by Av = lambda v.",
            "trust_tier": "tier_a",
            "matched_query": "Linear algebra Eigenvalue official",
            "accepted_for_generation": True,
        }],
        "receipt": {"status": "completed", "query_count": 1},
    }

    class FakeGateway:
        async def retrieve(self, request):
            assert request.purpose == "course"
            assert request.revision >= 2
            assert request.max_queries == 8
            return supplement

    monkeypatch.setattr(
        course_service_module,
        "configured_retrieval_gateway",
        lambda actor_id: (FakeGateway(), {"enabled_for_user": True, "actor_id": actor_id}),
    )
    course = {
        "course_name": "Linear algebra",
        "retrieval_package": _package(),
        "retrieval_acceptance": {
            "accepted_source_ids": ["src_a"],
            "package_revision": 1,
        },
        "generation_stage_artifacts": {"web_retrieval": {}},
    }
    graph = {
        "revision_id": "kg-rev-2",
        "nodes": [{
            "knowledge_key": "kp-eigenvalue",
            "name": "Eigenvalue",
            "statement": "Define eigenvalue",
            "detail_status": "skeleton",
            "source_refs": [],
            "counterexamples": [],
        }],
    }
    phases: list[str] = []
    checkpoints: list[dict] = []

    async def on_phase(phase, *_args):
        phases.append(phase)

    async def on_checkpoint(snapshot):
        checkpoints.append(snapshot)

    service = object.__new__(CourseService)
    context = await service._prepare_knowledge_gap_retrieval(
        course_data=course,
        graph_draft=graph,
        retrieval_context={"enabled": True, "actor_id": "teacher-1"},
        on_phase=on_phase,
        on_checkpoint=on_checkpoint,
    )

    assert course["retrieval_package"]["revision"] == 2
    assert course["generation_stage_artifacts"]["web_retrieval"]["knowledge_gap"]["status"] == "completed"
    assert course["generation_stage_artifacts"]["web_retrieval"]["knowledge_gap"]["source_bindings"] == {
        "kp-eigenvalue": ["src_gap"]
    }
    assert phases == ["knowledge_gap_retrieval", "knowledge_gap_retrieval"]
    assert checkpoints
    assert "已确认联网资料" in context
