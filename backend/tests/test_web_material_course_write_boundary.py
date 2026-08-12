"""验证 AGENTS.md 第 5 节对联网资料的约束在课程调整路径上成立。

第 5 节要求：AI 对正式课程的修改必须经过白名单领域命令、用户确认、
幂等回执和可恢复路径。联网资料进入正式课程正文同样受此约束。

这里验证的不是"联网资料好不好"，而是**边界**：
联网资料只能停在生成期的资料链与 AI 问答上下文，
不能绕过白名单命令直接改已发布课程正文。
"""

from __future__ import annotations

import inspect

import pytest

import ai_teacher_actions
import course_evolution


# ---------------------------------------------------------------- 白名单本身


def test_ai_teacher_action_whitelist_has_no_course_body_mutation():
    """AI 老师的白名单动作里不得出现改课程正文的动作。

    ACTION_TYPES 目前只有笔记/问题/复习任务/书签/运行时动作，
    若有人后续往里加 "replace_block" 这类动作，本用例会失败。
    """
    forbidden_markers = ("block", "course_content", "rewrite", "replace", "section")
    for action in ai_teacher_actions.ACTION_TYPES:
        lowered = action.lower()
        assert not any(marker in lowered for marker in forbidden_markers), (
            f"AI 老师白名单出现疑似改正文的动作：{action}"
        )


def test_unregistered_action_is_forbidden_at_execution():
    """未登记的动作类型必须在执行期被拒。"""
    source = inspect.getsource(ai_teacher_actions.execute_proposal)
    assert "not in ACTION_TYPES" in source
    assert "ActionForbidden" in source


def test_course_evolution_operation_types_are_a_closed_set():
    """课程生长的操作类型是 Literal 闭集，模型不能自造操作。"""
    annotation = course_evolution.CourseEvolutionOperation.model_fields[
        "operation_type"
    ].annotation
    allowed = set(getattr(annotation, "__args__", ()))
    assert allowed, "operation_type 必须是封闭的 Literal 集合"
    # 抽样确认关键写入操作在集合内，且集合不是空壳。
    assert "REPLACE_COURSE_BLOCK" in allowed
    assert "INSERT_COURSE_BLOCK" in allowed


def test_course_evolution_rejects_unknown_operation_type():
    """自造的操作类型必须被 schema 拒绝，而不是静默通过。"""
    with pytest.raises(Exception):
        course_evolution.CourseEvolutionOperation.model_validate({
            "operation_id": "op-1",
            "operation_type": "INJECT_WEB_MATERIAL",  # 不在白名单里
            "scope": "current",
            "payload": {},
        })


# -------------------------------------------------- 联网资料与正文写入的边界


def test_course_evolution_does_not_consume_web_material():
    """课程生长模块不读取联网资料真源。

    course_evolution 里的 evidence 指的是**学习证据**（学习者行为），
    与联网资料的 evidence_catalog 是两回事。若有人把联网资料接进
    生长链而绕过资料链，本用例会失败。
    """
    source = inspect.getsource(course_evolution)
    for marker in ("web_search", "evidence_catalog", "material_bindings", "retrieval_package"):
        assert marker not in source, (
            f"course_evolution 出现联网资料标识 {marker}，"
            "联网资料不应绕过资料链直接进入课程生长"
        )


def test_ai_teacher_actions_does_not_consume_web_material():
    """AI 老师动作执行链不读取联网资料真源。"""
    source = inspect.getsource(ai_teacher_actions)
    for marker in ("web_search", "evidence_catalog", "material_bindings", "retrieval_package"):
        assert marker not in source, (
            f"ai_teacher_actions 出现联网资料标识 {marker}"
        )


def test_ai_teacher_retrieval_only_feeds_answer_context():
    """AI 老师的联网检索只并入问答上下文，不写课程文档。

    merge_ai_teacher_retrieval 负责把已准入来源挂到上下文包上；
    它不得触碰 CourseDocument 仓库或领域命令。
    """
    import ai_teacher_retrieval

    source = inspect.getsource(ai_teacher_retrieval)
    for marker in (
        "CourseCommandService",
        "CourseDocumentRepository",
        "replace_block",
        "insert_block",
        "apply_block_operation_group",
    ):
        assert marker not in source, (
            f"ai_teacher_retrieval 触碰了课程写入路径：{marker}"
        )


# ------------------------------------------------ 写入必须带确认与幂等回执


def test_block_writes_go_through_command_service_only():
    """课程正文写入集中在 CourseCommandService，不散落在别处。"""
    import course_commands

    service_source = inspect.getsource(course_commands.CourseCommandService)
    # 每个写入方法都必须落到仓库的事务性 mutation 上。
    for method in ("replace_block", "insert_block", "delete_block"):
        assert f"async def {method}" in service_source


def test_accept_change_set_requires_user_selection_and_is_idempotent():
    """课程生长的接受动作要求用户显式选择范围，且重复接受幂等。"""
    source = inspect.getsource(course_evolution.accept_change_set)
    # 用户确认：范围必须在允许集合内
    assert "selected_scope not in change_set.allowed_scopes" in source
    # 幂等：已应用且选择相同则直接返回原状态，不重复写入
    assert 'change_set.status == "applied"' in source
    assert "return state" in source


def test_applied_change_set_records_receipt_and_undo_path():
    """应用后必须留下幂等回执与可恢复路径。"""
    source = inspect.getsource(course_evolution)
    assert "application_receipt" in source
    assert "undo_receipt" in source
