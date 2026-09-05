"""目录调整后的下游失效必须按受影响范围收敛，而不是整段丢弃。"""

from jobs.manager import TaskManager


def _node(node_id: str, name: str, prerequisites=None) -> dict:
    return {
        "node_id": node_id,
        "parent_node_id": "L1-1",
        "node_level": 2,
        "node_name": name,
        "learning_objective": f"{name}的学习目标",
        "scope_boundary": f"只负责{name}",
        "prerequisite_node_ids": prerequisites or [],
        "node_content": f"## {name}\n\n{name}的正文，生成一次代价很高。",
        "content_blocks": [{"block_id": f"{node_id}-b1", "text": name}],
        "key_points": [f"{name}知识"],
        "generation_status": "completed",
    }


def _course() -> dict:
    return {
        "course_id": "scoped-invalidation",
        "course_name": "范围失效课程",
        "nodes": [
            {"node_id": "L1-1", "node_level": 1, "node_name": "第一章"},
            _node("L2-1-1", "1.1 基础"),
            _node("L2-1-2", "1.2 进阶", ["L2-1-1"]),
            _node("L2-1-3", "1.3 应用", ["L2-1-2"]),
        ],
        "course_plan": {"chapters": []},
        "course_teaching_plan": {"schema_version": "course_teaching_plan_v3"},
    }


def _content_of(course: dict, node_id: str) -> str:
    for node in course["nodes"]:
        if node.get("node_id") == node_id:
            return str(node.get("node_content") or "")
    raise AssertionError(node_id)


def test_unaffected_sections_keep_their_generated_body():
    impact = {
        "global_changes": [],
        "affected_node_ids": ["L2-1-2", "L2-1-3"],
        "unchanged_node_ids": ["L2-1-1"],
        "display_only_node_ids": [],
        "added_node_ids": [],
        "removed_node_ids": [],
    }

    result = TaskManager._discard_generation_artifacts_after(
        _course(),
        "outline",
        impact,
    )

    # 未受影响的小节保留正文，不必重跑。
    assert _content_of(result, "L2-1-1")
    assert result["outline_change_preserved_node_ids"] == ["L2-1-1"]
    # 受影响的小节（含依赖闭包传播到的）仍然失效。
    assert not _content_of(result, "L2-1-2")
    assert not _content_of(result, "L2-1-3")
    for node_id in ("L2-1-2", "L2-1-3"):
        node = next(
            item for item in result["nodes"]
            if item.get("node_id") == node_id
        )
        assert node["generation_status"] == "pending"
    # 课程级派生产物仍然丢弃：它们本地重编译，不需要模型调用。
    assert "course_teaching_plan" not in result


def test_display_only_change_keeps_every_body():
    impact = {
        "global_changes": [],
        "affected_node_ids": [],
        "unchanged_node_ids": ["L2-1-2", "L2-1-3"],
        "display_only_node_ids": ["L2-1-1"],
        "added_node_ids": [],
        "removed_node_ids": [],
    }

    result = TaskManager._discard_generation_artifacts_after(
        _course(),
        "outline",
        impact,
    )

    for node_id in ("L2-1-1", "L2-1-2", "L2-1-3"):
        assert _content_of(result, node_id)


def test_global_change_still_discards_everything():
    impact = {
        "global_changes": ["difficulty_profile"],
        "affected_node_ids": ["L2-1-1", "L2-1-2", "L2-1-3"],
        "unchanged_node_ids": [],
        "display_only_node_ids": [],
        "added_node_ids": [],
        "removed_node_ids": [],
    }

    result = TaskManager._discard_generation_artifacts_after(
        _course(),
        "outline",
        impact,
    )

    for node_id in ("L2-1-1", "L2-1-2", "L2-1-3"):
        assert not _content_of(result, node_id)


def test_without_impact_behaviour_is_unchanged_full_discard():
    result = TaskManager._discard_generation_artifacts_after(
        _course(),
        "outline",
    )

    for node_id in ("L2-1-1", "L2-1-2", "L2-1-3"):
        assert not _content_of(result, node_id)
    assert result["outline_change_preserved_node_ids"] == []
