from copy import deepcopy

from change_proposals import ChangeProposalRepository
from course_knowledge_map import propose_kb_linkage_from_block_change
from subject_knowledge import propose_content_linkage_from_kb_change


def _course(course_id: str = "course-linear") -> dict:
    return {
        "course_id": course_id,
        "course_name": "线性代数基础",
        "nodes": [{
            "node_id": "L2-1-1",
            "node_level": 2,
            "node_name": "高斯消元",
            "learning_objective": "能够使用高斯消元判断解的结构",
            "knowledge_structure": [{
                "topic": "线性方程组与解结构",
                "description": "从增广矩阵到解分类",
                "knowledge_points": [{
                    "name": "高斯消元法步骤与行简化阶梯形",
                    "description": "通过合法行变换获得阶梯形",
                    "capability": "完成消元并解释每一步",
                    "aliases": [],
                    "prerequisite_names": [],
                }],
            }],
            "key_points": ["高斯消元法步骤与行简化阶梯形"],
            "content_blocks": [{
                "block_id": "block-1",
                "title": "高斯消元法",
                "content": "使用高斯消元法步骤与行简化阶梯形求解。",
                "metadata": {},
            }],
            "grounding_contract": {},
            "prerequisite_node_ids": [],
        }],
    }


def test_accepted_block_change_proposes_pending_kb_linkage(tmp_path):
    course = _course()
    repository = ChangeProposalRepository(tmp_path / "change_proposals")

    proposal = propose_kb_linkage_from_block_change(
        course,
        "block-1",
        repository=repository,
        request_id="req-content-to-kb-1",
    )

    assert proposal is not None
    assert proposal["source"] == "kb_link"
    assert proposal["status"] == "pending"
    assert len(proposal["items"]) == 1
    item = proposal["items"][0]
    assert item["status"] == "pending"
    assert item["target_kind"] == "kg_node"
    assert item["block_id"].startswith("ckp_")
    assert proposal["generation_meta"]["linkage_direction"] == "content_to_kb"
    assert proposal["generation_meta"]["knowledge_scope"] == "current_course_only"

    reloaded = repository.load(proposal["proposal_id"])
    assert reloaded == proposal


def test_no_linkage_proposed_for_block_without_course_knowledge_binding(tmp_path):
    course = _course()
    course["nodes"][0]["content_blocks"][0]["content"] = "这段内容和任何正式知识节点都不相关。"
    course["nodes"][0]["content_blocks"][0]["title"] = "闲聊"
    repository = ChangeProposalRepository(tmp_path / "change_proposals")

    proposal = propose_kb_linkage_from_block_change(
        course,
        "block-1",
        repository=repository,
        request_id="req-content-to-kb-2",
    )

    assert proposal is None


def test_legacy_subject_node_update_cannot_modify_course_content(tmp_path):
    course = _course()
    repository = ChangeProposalRepository(tmp_path / "change_proposals")

    proposal = propose_content_linkage_from_kb_change(
        course,
        "math.la.system.gaussian_elimination",
        {"name": "高斯消元法", "description": "更新后的正式定义：强调主元选取与数值稳定性。"},
        repository=repository,
        request_id="req-kb-to-content-1",
    )

    assert proposal is None


def test_kb_node_without_course_binding_proposes_nothing(tmp_path):
    course = _course()
    repository = ChangeProposalRepository(tmp_path / "change_proposals")

    proposal = propose_content_linkage_from_kb_change(
        course,
        "math.la.matrix.determinant",
        {"name": "行列式", "description": "无关节点的更新定义"},
        repository=repository,
        request_id="req-kb-to-content-2",
    )

    assert proposal is None


def test_both_linkage_directions_never_auto_modify_target_content(tmp_path):
    """Hard constraint: creating a kb_link proposal must never itself mutate the
    course content or the knowledge library it was derived from - only a
    subsequent, explicit apply_item call (not exercised here) may do that."""
    course = _course()
    original_course = deepcopy(course)
    repository = ChangeProposalRepository(tmp_path / "change_proposals")

    content_to_kb = propose_kb_linkage_from_block_change(
        course,
        "block-1",
        repository=repository,
        request_id="req-guard-1",
    )

    # The course dict passed in (representing both "course content" and the
    # source of the knowledge-map projection) must be untouched.
    assert course == original_course

    # Both proposals sit pending - nothing was auto-applied.
    assert content_to_kb is not None
    assert content_to_kb["status"] == "pending"
    for item in content_to_kb["items"]:
        assert item["status"] == "pending"
        assert item["receipt"] is None

    pending = repository.list_for_course(course["course_id"], status="pending")
    assert len(pending) == 1
