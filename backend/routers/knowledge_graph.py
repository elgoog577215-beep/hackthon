# =============================================================================
# 知识图谱路由
# 完整 CRUD：图谱整体、节点、关系
# =============================================================================

import uuid
import time
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from storage import storage
from ai_service import ai_service
from dependencies import get_course_or_404
from models import (
    KGNodeCreate, KGNodeUpdate,
    KGEdgeCreate, KGEdgeUpdate,
    KGBatchPositionUpdate,
)

router = APIRouter(prefix="/courses/{course_id}/knowledge_graph", tags=["knowledge_graph"])


# ---------------------------------------------------------------------------
# 图谱整体
# ---------------------------------------------------------------------------

@router.get("")
async def get_knowledge_graph(course_id: str):
    """获取知识图谱"""
    graph_data = await run_in_threadpool(storage.load_knowledge_graph, course_id)
    if graph_data:
        if _normalize_graph(graph_data):
            # 旧数据补全了字段，持久化回去保证 id 稳定
            await run_in_threadpool(storage.save_knowledge_graph, course_id, graph_data)
        return {"status": "success", "data": graph_data, "cached": True}
    return {"status": "success", "data": {"nodes": [], "edges": [], "updated_at": 0}, "cached": False}



@router.post("/generate")
async def generate_knowledge_graph(course_id: str):
    """AI 生成知识图谱（替换旧 AI 节点，保留用户节点）"""
    tree_data = await get_course_or_404(course_id)
    if "nodes" not in tree_data:
        raise HTTPException(status_code=404, detail="Course has no nodes")

    course_name = tree_data.get("course_name", "Unknown Course")
    nodes = tree_data.get("nodes", [])

    course_context = f"Course: {course_name}\n"
    for node in nodes[:20]:
        content_preview = node.get("node_content", "")[:100]
        course_context += f"- {node.get('node_name', '')}: {content_preview}\n"

    ai_graph = await ai_service.generate_knowledge_graph(
        course_name=course_name,
        course_context=course_context,
        nodes=nodes
    )

    # 合并：保留用户手动创建的节点和边，AI 生成的去重后追加
    existing = await run_in_threadpool(storage.load_knowledge_graph, course_id)
    merged = _merge_ai_graph(existing, ai_graph)
    _normalize_graph(merged)

    await run_in_threadpool(storage.save_knowledge_graph, course_id, merged)
    return {"status": "success", "data": merged}


@router.put("")
async def batch_update_positions(course_id: str, req: KGBatchPositionUpdate):
    """批量更新节点坐标（拖拽后持久化）"""
    graph_data = await run_in_threadpool(storage.load_knowledge_graph, course_id)
    if not graph_data:
        raise HTTPException(status_code=404, detail="Knowledge graph not found")

    node_map = {n["id"]: n for n in graph_data.get("nodes", [])}
    for node_id, pos in req.positions.items():
        if node_id in node_map:
            if isinstance(pos, dict):
                if "x" in pos:
                    node_map[node_id]["x"] = pos["x"]
                if "y" in pos:
                    node_map[node_id]["y"] = pos["y"]

    graph_data["updated_at"] = time.time()
    await run_in_threadpool(storage.save_knowledge_graph, course_id, graph_data)
    return {"status": "success"}


# ---------------------------------------------------------------------------
# 节点 CRUD
# ---------------------------------------------------------------------------

@router.post("/nodes")
async def create_node(course_id: str, req: KGNodeCreate):
    """创建知识图谱节点"""
    graph_data = await _get_or_init_graph(course_id)

    now = time.time()
    new_node = {
        "id": str(uuid.uuid4())[:8],
        "label": req.label,
        "type": req.type,
        "description": req.description,
        "chapter_id": req.chapter_id,
        "x": req.x if req.x is not None else 0,
        "y": req.y if req.y is not None else 0,
        "color": req.color,
        "created_by": "user",
        "created_at": now,
        "updated_at": now,
    }
    graph_data["nodes"].append(new_node)
    graph_data["updated_at"] = now

    await run_in_threadpool(storage.save_knowledge_graph, course_id, graph_data)
    return {"status": "success", "data": new_node}


@router.put("/nodes/{node_id}")
async def update_node(course_id: str, node_id: str, req: KGNodeUpdate):
    """更新知识图谱节点"""
    graph_data = await run_in_threadpool(storage.load_knowledge_graph, course_id)
    if not graph_data:
        raise HTTPException(status_code=404, detail="Knowledge graph not found")

    node = _find_node(graph_data, node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

    update_data = req.model_dump(exclude_none=True)
    for key, value in update_data.items():
        node[key] = value
    node["updated_at"] = time.time()
    graph_data["updated_at"] = time.time()

    await run_in_threadpool(storage.save_knowledge_graph, course_id, graph_data)
    return {"status": "success", "data": node}


@router.delete("/nodes/{node_id}")
async def delete_node(course_id: str, node_id: str):
    """删除知识图谱节点及其关联边"""
    graph_data = await run_in_threadpool(storage.load_knowledge_graph, course_id)
    if not graph_data:
        raise HTTPException(status_code=404, detail="Knowledge graph not found")

    original_count = len(graph_data["nodes"])
    graph_data["nodes"] = [n for n in graph_data["nodes"] if n["id"] != node_id]
    if len(graph_data["nodes"]) == original_count:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

    # 同时删除关联的边
    graph_data["edges"] = [
        e for e in graph_data.get("edges", [])
        if e.get("source") != node_id and e.get("target") != node_id
    ]
    graph_data["updated_at"] = time.time()

    await run_in_threadpool(storage.save_knowledge_graph, course_id, graph_data)
    return {"status": "success"}


# ---------------------------------------------------------------------------
# 关系（边）CRUD
# ---------------------------------------------------------------------------

@router.post("/edges")
async def create_edge(course_id: str, req: KGEdgeCreate):
    """创建知识图谱关系"""
    graph_data = await _get_or_init_graph(course_id)

    node_ids = {n["id"] for n in graph_data["nodes"]}
    if req.source not in node_ids:
        raise HTTPException(status_code=400, detail=f"Source node {req.source} not found")
    if req.target not in node_ids:
        raise HTTPException(status_code=400, detail=f"Target node {req.target} not found")
    if req.source == req.target:
        raise HTTPException(status_code=400, detail="Cannot create self-loop")

    new_edge = {
        "id": str(uuid.uuid4())[:8],
        "source": req.source,
        "target": req.target,
        "relation": req.relation,
        "weight": req.weight,
        "label": req.label,
        "created_by": "user",
    }
    graph_data["edges"].append(new_edge)
    graph_data["updated_at"] = time.time()

    await run_in_threadpool(storage.save_knowledge_graph, course_id, graph_data)
    return {"status": "success", "data": new_edge}


@router.put("/edges/{edge_id}")
async def update_edge(course_id: str, edge_id: str, req: KGEdgeUpdate):
    """更新知识图谱关系"""
    graph_data = await run_in_threadpool(storage.load_knowledge_graph, course_id)
    if not graph_data:
        raise HTTPException(status_code=404, detail="Knowledge graph not found")

    edge = _find_edge(graph_data, edge_id)
    if not edge:
        raise HTTPException(status_code=404, detail=f"Edge {edge_id} not found")

    update_data = req.model_dump(exclude_none=True)
    for key, value in update_data.items():
        edge[key] = value
    graph_data["updated_at"] = time.time()

    await run_in_threadpool(storage.save_knowledge_graph, course_id, graph_data)
    return {"status": "success", "data": edge}


@router.delete("/edges/{edge_id}")
async def delete_edge(course_id: str, edge_id: str):
    """删除知识图谱关系"""
    graph_data = await run_in_threadpool(storage.load_knowledge_graph, course_id)
    if not graph_data:
        raise HTTPException(status_code=404, detail="Knowledge graph not found")

    original_count = len(graph_data.get("edges", []))
    graph_data["edges"] = [e for e in graph_data.get("edges", []) if e.get("id") != edge_id]
    if len(graph_data["edges"]) == original_count:
        raise HTTPException(status_code=404, detail=f"Edge {edge_id} not found")

    graph_data["updated_at"] = time.time()
    await run_in_threadpool(storage.save_knowledge_graph, course_id, graph_data)
    return {"status": "success"}


# ---------------------------------------------------------------------------
# 内部工具函数
# ---------------------------------------------------------------------------

def _normalize_graph(graph_data: dict):
    """确保所有边都有 id 和 weight 字段（兼容旧数据）"""
    dirty = False
    for edge in graph_data.get("edges", []):
        if not edge.get("id"):
            edge["id"] = str(uuid.uuid4())[:8]
            dirty = True
        if edge.get("weight") is None:
            edge["weight"] = 5
            dirty = True
    return dirty


async def _get_or_init_graph(course_id: str) -> dict:
    """获取图谱，不存在则初始化空图谱"""
    graph_data = await run_in_threadpool(storage.load_knowledge_graph, course_id)
    if not graph_data:
        graph_data = {"nodes": [], "edges": [], "updated_at": time.time()}
    if "edges" not in graph_data:
        graph_data["edges"] = []
    if "nodes" not in graph_data:
        graph_data["nodes"] = []
    return graph_data


def _find_node(graph_data: dict, node_id: str):
    for n in graph_data.get("nodes", []):
        if n["id"] == node_id:
            return n
    return None


def _find_edge(graph_data: dict, edge_id: str):
    for e in graph_data.get("edges", []):
        if e.get("id") == edge_id:
            return e
    return None


def _merge_ai_graph(existing: dict | None, ai_graph: dict) -> dict:
    """
    将 AI 生成的图谱合并到已有图谱。
    - 保留所有用户手动创建的节点和边
    - 删除旧的 AI 生成节点和边，用新生成的替换
    - AI 节点按 label 与用户节点去重（已存在同名用户节点则跳过）
    - AI 边按 source+target 去重
    - 为 AI 节点/边补充新字段
    """
    import time as _time

    now = _time.time()

    # 根据关系类型推断默认权重
    _relation_weights = {
        "prerequisite": 8, "derives": 7, "implements": 7,
        "applies_to": 6, "extends": 6, "contrasts_with": 5,
        "contains": 7, "leads_to": 5, "related": 3,
    }

    def _ensure_edge_weight(edge):
        """确保边有合理的 weight 值，优先保留 AI 生成的原始权重"""
        w = edge.get("weight")
        if w is not None and isinstance(w, (int, float)) and 1 <= w <= 10:
            return  # 已有合理权重，保留
        edge["weight"] = _relation_weights.get(edge.get("relation", ""), 5)

    if not existing or not existing.get("nodes"):
        # 没有已有图谱，直接标记 AI 节点并返回
        for node in ai_graph.get("nodes", []):
            node.setdefault("created_by", "ai")
            node.setdefault("created_at", now)
            node.setdefault("updated_at", now)
            node.setdefault("x", 0)
            node.setdefault("y", 0)
        for edge in ai_graph.get("edges", []):
            edge.setdefault("id", str(uuid.uuid4())[:8])
            edge.setdefault("created_by", "ai")
            _ensure_edge_weight(edge)
        ai_graph["updated_at"] = now
        return ai_graph

    # 保留用户手动创建的节点，丢弃旧的 AI 生成节点（重新生成会替换）
    merged_nodes = [n for n in existing.get("nodes", []) if n.get("created_by") == "user"]

    # 保留用户手动创建的边，丢弃旧的 AI 生成边（重新生成会替换）
    user_node_ids = {n["id"] for n in merged_nodes}
    merged_edges = [
        e for e in existing.get("edges", [])
        if e.get("created_by") == "user"
        and e.get("source") in user_node_ids
        and e.get("target") in user_node_ids
    ]

    # 补全已有边缺失的 id 和 weight
    for edge in merged_edges:
        if not edge.get("id"):
            edge["id"] = str(uuid.uuid4())[:8]
        _ensure_edge_weight(edge)

    existing_labels = {n.get("label", "").lower() for n in merged_nodes}
    existing_edge_keys = {
        (e.get("source"), e.get("target")) for e in merged_edges
    }

    for node in ai_graph.get("nodes", []):
        label = node.get("label", "")
        if label.lower() in existing_labels:
            continue
        node.setdefault("created_by", "ai")
        node.setdefault("created_at", now)
        node.setdefault("updated_at", now)
        node.setdefault("x", 0)
        node.setdefault("y", 0)
        merged_nodes.append(node)
        existing_labels.add(label.lower())

    merged_node_ids = {n["id"] for n in merged_nodes}

    for edge in ai_graph.get("edges", []):
        src, tgt = edge.get("source"), edge.get("target")
        if src not in merged_node_ids or tgt not in merged_node_ids:
            continue
        if (src, tgt) in existing_edge_keys:
            continue
        edge.setdefault("id", str(uuid.uuid4())[:8])
        edge.setdefault("created_by", "ai")
        _ensure_edge_weight(edge)
        merged_edges.append(edge)
        existing_edge_keys.add((src, tgt))

    return {
        "nodes": merged_nodes,
        "edges": merged_edges,
        "updated_at": now,
    }
