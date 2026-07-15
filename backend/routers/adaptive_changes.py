# =============================================================================
# 个体化课程演化路由（Phase 2：变更侧）
# 待确认变更（PendingChangeOverlay）查询、接受/拒绝/重新生成
#
# 对应 docs/requirements/灵知AI课程智能体_开发规格文档.md §4
#   "AI 变更 MUST 以待确认形式呈现" Requirement 的"学生处理待确认变更" Scenario。
# =============================================================================

import logging
import sys
import os
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from adaptation_service import generate_change_set
from adaptive_models import AdaptationHypothesis, ChangeItem, CourseChangeSet, PendingChangeOverlay
from change_set_state import (
    InvalidChangeSetTransition,
    accept_change_set,
    reject_change_set,
    regenerate_change_set,
)
from content_blocks import set_node_content_blocks
from dependencies import get_course_or_404, get_node_or_404
from routers.knowledge_graph import apply_kg_node_update
from storage import storage

logger = logging.getLogger(__name__)

router = APIRouter(tags=["adaptive-changes"])


# =============================================================================
# 请求体
# =============================================================================

class AcceptChangeSetRequest(BaseModel):
    """接受变更集请求体。node_ids 为空/未提供时接受该变更集中的全部条目。"""
    node_ids: Optional[List[str]] = None


class RejectChangeSetRequest(BaseModel):
    """拒绝变更集请求体。"""
    reason: Optional[str] = None
    node_ids: Optional[List[str]] = None


class RegenerateChangeSetRequest(BaseModel):
    """重新生成变更集请求体。"""
    extra_instruction: Optional[str] = None


# =============================================================================
# 辅助函数
# =============================================================================

def _load_change_set_or_404(course_id: str, change_set_id: str) -> CourseChangeSet:
    """从存储中加载指定 CourseChangeSet，找不到抛 404。"""
    raw_list = storage.load_change_sets(course_id)
    raw = next((cs for cs in raw_list if cs.get("id") == change_set_id), None)
    if raw is None:
        raise HTTPException(status_code=404, detail="Change set not found")
    return CourseChangeSet.model_validate(raw)


def _load_hypothesis_or_none(course_id: str, hypothesis_id: Optional[str]) -> Optional[AdaptationHypothesis]:
    """AdaptationHypothesis 目前没有独立持久化存储（Phase 1/2 仅落盘 EvidenceItem 与
    CourseChangeSet），regenerate 时退化为从原 change_set 反推一个"重建的" hypothesis，
    并在 generate_change_set 的 prompt 中通过 extra_instruction 补足上下文。
    """
    return None


def _collect_descendants(nodes: List[dict], root_id: str) -> set:
    """收集 root_id 节点自身及其所有后代节点 id（与 routers/nodes.py delete_node 的
    级联删除逻辑保持一致，避免课程树中留下悬空的 parent_node_id 引用）。
    """
    to_delete = {root_id}
    changed = True
    while changed:
        changed = False
        for node in nodes:
            if node.get("parent_node_id") in to_delete and node["node_id"] not in to_delete:
                to_delete.add(node["node_id"])
                changed = True
    return to_delete


def _apply_delete(tree_data: dict, target_node_id: str, course_id: str) -> bool:
    """delete 操作：级联删除 target_node_id 对应节点及其所有子孙节点。

    复用 routers/nodes.py::delete_node 的同一套级联删除算法，只是直接操作已加载的
    tree_data（因为 accept 路由需要在一个事务里处理一个 change_set 内的多条 change_item，
    不能对每条都单独 load/save 一次课程）。

    Returns:
        是否实际删除了节点（False 表示 target_node_id 不存在，调用方应跳过并告警）。
    """
    nodes = tree_data.get("nodes", [])
    if not any(n.get("node_id") == target_node_id for n in nodes):
        logger.warning(
            "accept_change_set(delete): target_node_id=%s 在课程 %s 中不存在，跳过删除",
            target_node_id, course_id,
        )
        return False

    to_delete = _collect_descendants(nodes, target_node_id)
    tree_data["nodes"] = [n for n in nodes if n.get("node_id") not in to_delete]
    return True


def _apply_move(tree_data: dict, item: ChangeItem, course_id: str) -> bool:
    """move 操作：把 target_node_id 对应节点移动到新的 parent_node_id / 兄弟顺序下。

    目标位置的表达约定（见 adaptive_models.ChangeItem.move_target 字段注释）：
        after 字段仍是字符串摘要，不适合承载结构化数据，因此约定改用
        change_item.move_target = {"new_parent_node_id": str, "new_order": Optional[int]}。

    课程树里节点没有独立的 order 字段（models.py::Node），兄弟节点间的展示顺序由它们在
    tree_data["nodes"] 列表中的相对位置决定（与 add_custom_node 追加到列表末尾的写法一致），
    所以"移动顺序"通过重新排列列表位置实现，而不是写一个新字段。

    Returns:
        是否实际执行了移动（False 表示校验失败，调用方应跳过并告警，不抛错拖垮整体接受流程）。
    """
    nodes = tree_data.get("nodes", [])
    node = next((n for n in nodes if n.get("node_id") == item.target_node_id), None)
    if node is None:
        logger.warning(
            "accept_change_set(move): target_node_id=%s 在课程 %s 中不存在，跳过移动",
            item.target_node_id, course_id,
        )
        return False

    move_target = item.move_target or {}
    new_parent_id = move_target.get("new_parent_node_id")
    if not new_parent_id:
        logger.warning(
            "accept_change_set(move): change_item %s 缺少 move_target.new_parent_node_id，跳过移动",
            item.id,
        )
        return False

    if new_parent_id != "root" and not any(n.get("node_id") == new_parent_id for n in nodes):
        logger.warning(
            "accept_change_set(move): new_parent_node_id=%s 在课程 %s 中不存在，跳过移动",
            new_parent_id, course_id,
        )
        return False

    # 禁止把节点移动到自己或自己的后代下面，否则会在树里造成环。
    descendants = _collect_descendants(nodes, item.target_node_id)
    if new_parent_id in descendants:
        logger.warning(
            "accept_change_set(move): new_parent_node_id=%s 是 target_node_id=%s 的自身或后代，跳过移动（会成环）",
            new_parent_id, item.target_node_id,
        )
        return False

    node["parent_node_id"] = new_parent_id
    if new_parent_id != "root":
        new_parent_node = next(n for n in nodes if n.get("node_id") == new_parent_id)
        node["node_level"] = new_parent_node.get("node_level", 1) + 1
    else:
        node["node_level"] = 1

    # 先把节点从原位置摘出来，再按 new_order 插回新父节点的子节点区间。
    nodes.remove(node)
    siblings_idx = [i for i, n in enumerate(nodes) if n.get("parent_node_id") == new_parent_id]

    new_order = move_target.get("new_order")
    if new_order is None or not siblings_idx or new_order >= len(siblings_idx):
        insert_at = (siblings_idx[-1] + 1) if siblings_idx else len(nodes)
    else:
        insert_at = siblings_idx[max(0, new_order)]

    nodes.insert(insert_at, node)
    tree_data["nodes"] = nodes
    return True


async def _apply_accepted_items(course_id: str, change_set: CourseChangeSet, node_ids: Optional[List[str]]) -> List[str]:
    """把被接受的 change_item 写入正式课程节点。

    - add / modify / replace / difficulty_adjust：复用 content_blocks.set_node_content_blocks
      （与 routers/nodes.py 更新节点内容的方式一致）写入 content_blocks。
    - delete：级联删除 target_node_id 对应节点及其子孙节点（_apply_delete）。
    - move：把节点移动到新的 parent_node_id / 兄弟顺序下（_apply_move）。

    所有分支最终都落到同一次 storage.save_course，保持与既有持久化路径一致，不绕开覆盖内存。

    Returns:
        实际被结构性应用（写入内容 / 删除 / 移动）的 target_node_id 列表。
    """
    tree_data = await get_course_or_404(course_id)
    nodes = tree_data.get("nodes", [])
    node_map = {n.get("node_id"): n for n in nodes}

    applied_node_ids: List[str] = []
    for item in change_set.change_items:
        if node_ids is not None and item.target_node_id not in node_ids:
            continue

        if item.target_kind == "kg_node":
            # kg_node 条目不写课程树，由 _apply_kg_node_change_items 单独处理。
            continue

        if item.operation == "delete":
            if _apply_delete(tree_data, item.target_node_id, course_id):
                applied_node_ids.append(item.target_node_id)
            continue

        if item.operation == "move":
            if _apply_move(tree_data, item, course_id):
                applied_node_ids.append(item.target_node_id)
            continue

        node = node_map.get(item.target_node_id)
        if node is None:
            logger.warning(
                "accept_change_set: target_node_id=%s 在课程 %s 中不存在，跳过写入",
                item.target_node_id, course_id,
            )
            continue

        if item.operation in ("add", "modify", "replace", "difficulty_adjust") and item.after:
            existing_content = node.get("node_content", "") or ""
            if item.operation == "replace":
                new_content = item.after
            else:
                # add / modify / difficulty_adjust：在现有内容后追加，保留原有正文，
                # 避免"静默覆盖正式课程"（规格文档 §6 反模式）。
                new_content = f"{existing_content}\n\n{item.after}".strip() if existing_content else item.after
            set_node_content_blocks(node, new_content)
            applied_node_ids.append(item.target_node_id)

    if applied_node_ids:
        await storage.save_course(course_id, tree_data)

    return applied_node_ids


async def _apply_kg_node_change_items(
    course_id: str, change_set: CourseChangeSet, node_ids: Optional[List[str]]
) -> List[str]:
    """把被接受的、target_kind == 'kg_node' 的 change_item 写入知识图谱节点。

    复用 routers/knowledge_graph.py::apply_kg_node_update（update_kg_node 路由的同一套
    核心逻辑），不建立第二条"写 KG"的旁路。目前仅支持 add/modify/replace/difficulty_adjust
    四种 operation（写 description 字段），delete/move 对 kg_node 暂不支持。

    Returns:
        实际成功更新的 KG target_node_id 列表。
    """
    applied: List[str] = []
    for item in change_set.change_items:
        if item.target_kind != "kg_node":
            continue
        if node_ids is not None and item.target_node_id not in node_ids:
            continue
        if item.operation not in ("add", "modify", "replace", "difficulty_adjust") or not item.after:
            continue

        updated = await apply_kg_node_update(course_id, item.target_node_id, {"description": item.after})
        if updated is None:
            logger.warning(
                "accept_change_set(kg_node): target_node_id=%s 在课程 %s 的知识图谱中不存在，跳过写入",
                item.target_node_id, course_id,
            )
            continue
        applied.append(item.target_node_id)

    return applied


def _match_kg_concepts_in_text(graph_data: Optional[dict], text: str) -> List[dict]:
    """在知识图谱节点中查找 text 里提到的概念（按 label 子串匹配）。

    与 routers/knowledge_graph.py::_generate_kb_to_content_linkage 里 KB -> 内容方向
    使用的判定方式保持一致（同样是子串匹配，避免两个方向用两套不一致的算法）。
    """
    if not graph_data or not text:
        return []
    matches = []
    for node in graph_data.get("nodes", []):
        label = (node.get("label") or "").strip()
        if label and label in text:
            matches.append(node)
    return matches


async def _generate_content_to_kb_linkage(
    course_id: str, change_set: CourseChangeSet, applied_node_ids: List[str]
) -> Optional[CourseChangeSet]:
    """课程内容变更被接受后，为其中引用了已知知识图谱概念的条目生成一条
    pending 的 content_to_kb_link 联动提案（不自动写入知识图谱，需再走一次 accept）。
    """
    graph_data = await run_in_threadpool(storage.load_knowledge_graph, course_id)
    if not graph_data:
        return None

    kg_change_items: List[ChangeItem] = []
    scope_node_ids: List[str] = []
    for item in change_set.change_items:
        if item.target_kind != "course_node":
            continue
        if item.target_node_id not in applied_node_ids:
            continue
        if item.operation not in ("add", "modify", "replace") or not item.after:
            continue

        matched_nodes = _match_kg_concepts_in_text(graph_data, item.after)
        for kg_node in matched_nodes:
            kg_change_items.append(
                ChangeItem(
                    target_node_id=kg_node["id"],
                    target_kind="kg_node",
                    operation="modify",
                    before=kg_node.get("description", ""),
                    after=(
                        f"[课程内容联动提示] 课程节点 {item.target_node_id} 的内容变更提及概念"
                        f"「{kg_node.get('label')}」，变更内容：{item.after}\n"
                        f"建议同步检查/修订该知识图谱节点的描述，使其与最新课程内容保持一致。"
                    ),
                    reason=(
                        f"源自已接受的内容变更（change_item {item.id}，课程节点 {item.target_node_id}），"
                        f"建议同步更新知识图谱节点「{kg_node.get('label')}」。"
                    ),
                )
            )
            scope_node_ids.append(kg_node["id"])

    if not kg_change_items:
        return None

    linkage_change_set = CourseChangeSet(
        course_id=course_id,
        scope="sections" if len(kg_change_items) > 1 else "block",
        scope_node_ids=scope_node_ids,
        change_items=kg_change_items,
        source="content_to_kb_link",
        status="pending",
    )
    await storage.save_change_set(course_id, linkage_change_set.model_dump(mode="json"))
    return linkage_change_set


# =============================================================================
# 路由
# =============================================================================

@router.get("/courses/{course_id}/pending_changes")
async def get_pending_changes(course_id: str):
    """获取课程当前所有待确认变更（PendingChangeOverlay）。"""
    await get_course_or_404(course_id)
    raw_list = await run_in_threadpool(storage.load_change_sets, course_id)
    change_sets = [CourseChangeSet.model_validate(raw) for raw in raw_list]
    overlay = PendingChangeOverlay.from_change_sets(course_id, change_sets)
    return overlay.model_dump()


@router.post("/courses/{course_id}/change_sets/{change_set_id}/accept")
async def accept_course_change_set(course_id: str, change_set_id: str, body: AcceptChangeSetRequest = AcceptChangeSetRequest()):
    """接受一条待确认变更集（可指定 node_ids 只接受其中部分条目）。"""
    await get_course_or_404(course_id)
    change_set = _load_change_set_or_404(course_id, change_set_id)

    try:
        result = accept_change_set(change_set)
    except InvalidChangeSetTransition as e:
        raise HTTPException(status_code=409, detail=str(e))

    applied_node_ids = await _apply_accepted_items(course_id, result.change_set, body.node_ids)
    applied_kg_node_ids = await _apply_kg_node_change_items(course_id, result.change_set, body.node_ids)

    await storage.save_change_set(course_id, result.change_set.model_dump(mode="json"))

    # 联动提案：仅当本次 accept 的是原生（非联动生成的）内容变更时才继续派生新的联动提案，
    # 避免 content_to_kb_link / kb_to_content_link 互相触发形成无限链条。
    if result.change_set.source == "evidence_driven" and applied_node_ids:
        try:
            await _generate_content_to_kb_linkage(course_id, result.change_set, applied_node_ids)
        except Exception:
            logger.warning(
                "accept_change_set: 生成 content_to_kb_link 联动提案失败（不影响本次接受结果）",
                exc_info=True,
            )

    response = result.change_set.model_dump()
    response["applied_node_ids"] = applied_node_ids
    response["applied_kg_node_ids"] = applied_kg_node_ids
    return response


@router.post("/courses/{course_id}/change_sets/{change_set_id}/reject")
async def reject_course_change_set(course_id: str, change_set_id: str, body: RejectChangeSetRequest = RejectChangeSetRequest()):
    """拒绝一条待确认变更集，拒绝理由回流为新的 EvidenceItem。"""
    await get_course_or_404(course_id)
    change_set = _load_change_set_or_404(course_id, change_set_id)

    try:
        updated_change_set, evidence = reject_change_set(change_set, reason=body.reason)
    except InvalidChangeSetTransition as e:
        raise HTTPException(status_code=409, detail=str(e))

    await storage.save_change_set(course_id, updated_change_set.model_dump(mode="json"))
    await storage.save_evidence_item(course_id, evidence.model_dump(mode="json"))

    return updated_change_set.model_dump()


@router.post("/courses/{course_id}/change_sets/{change_set_id}/regenerate")
async def regenerate_course_change_set(course_id: str, change_set_id: str, body: RegenerateChangeSetRequest = RegenerateChangeSetRequest()):
    """将原变更集标记为 regenerated，并基于原假设 + 补充意见重新调用生成服务产出新变更集。"""
    tree_data = await get_course_or_404(course_id)
    change_set = _load_change_set_or_404(course_id, change_set_id)

    try:
        # 状态机负责：把原 change_set 标记为 regenerated，并给出一个 skeleton（after=None）。
        # 我们不直接使用 skeleton 作为最终结果，而是把它的 change_items 结构（target_node_id/
        # operation/reason）当作"重新生成"的锚点，去调用真正的 LLM 生成服务产出新内容。
        skeleton = regenerate_change_set(change_set, extra_instruction=body.extra_instruction)
    except InvalidChangeSetTransition as e:
        raise HTTPException(status_code=409, detail=str(e))

    await storage.save_change_set(course_id, change_set.model_dump(mode="json"))

    # 反推一个 AdaptationHypothesis：Phase 2 未落盘 AdaptationHypothesis 存储，
    # 因此从原 change_set 的 source_hypothesis_id 与首个 change_item 的 reason 重建
    # 足够 generate_change_set 使用的上下文（详见 _load_hypothesis_or_none 的说明）。
    anchor_node_id = skeleton.change_items[0].target_node_id if skeleton.change_items else (
        change_set.scope_node_ids[0] if change_set.scope_node_ids else ""
    )
    anchor_reason = change_set.change_items[0].reason if change_set.change_items else ""
    hypothesis = AdaptationHypothesis(
        id=change_set.source_hypothesis_id or "",
        node_id=anchor_node_id,
        course_id=course_id,
        hypothesis=anchor_reason or "学生请求重新生成该条变更集",
        supporting_evidence_ids=[],
        confidence=0.6,
    )

    node = next((n for n in tree_data.get("nodes", []) if n.get("node_id") == anchor_node_id), None)
    node_content = node.get("node_content", "") if node else ""

    new_change_set = await generate_change_set(
        hypothesis, node_content=node_content, extra_instruction=body.extra_instruction
    )
    if new_change_set is None:
        raise HTTPException(status_code=502, detail="重新生成失败：AI 未能产出通过校验的变更内容，请稍后重试")

    # 不得复用完全相同的输出（规格文档 MUST）：generate_change_set 是全新的一次 LLM 调用，
    # 天然不会和原 change_set 完全一致；这里再做一次显式保护，避免极端情况下模型原样复读。
    if new_change_set.change_items and change_set.change_items and (
        new_change_set.change_items[0].after == change_set.change_items[0].after
    ):
        logger.warning("regenerate_change_set: 新生成内容与原内容相同，标记提示")
        new_change_set.generation_meta["warning"] = "新生成内容与原内容相同，建议重新生成或人工核查"

    await storage.save_change_set(course_id, new_change_set.model_dump(mode="json"))

    return new_change_set.model_dump()
