# =============================================================================
# 知识图谱路由
# 知识图谱生成与查询
# =============================================================================

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from storage import storage
from ai_service import ai_service
from dependencies import get_course_or_404

router = APIRouter(prefix="/courses/{course_id}/knowledge_graph", tags=["knowledge_graph"])


@router.post("")
async def generate_knowledge_graph(course_id: str):
    tree_data = await get_course_or_404(course_id)

    if "nodes" not in tree_data:
        raise HTTPException(status_code=404, detail="Course has no nodes")

    course_name = tree_data.get("course_name", "Unknown Course")
    nodes = tree_data.get("nodes", [])

    course_context = f"Course: {course_name}\n"
    for node in nodes[:20]:
        content_preview = node.get("node_content", "")[:100]
        course_context += f"- {node.get('node_name', '')}: {content_preview}\n"

    graph_data = await ai_service.generate_knowledge_graph(
        course_name=course_name,
        course_context=course_context,
        nodes=nodes
    )

    await run_in_threadpool(storage.save_knowledge_graph, course_id, graph_data)

    return {"status": "success", "data": graph_data}


@router.get("")
async def get_knowledge_graph(course_id: str):
    graph_data = await run_in_threadpool(storage.load_knowledge_graph, course_id)
    if graph_data:
        return {"status": "success", "data": graph_data, "cached": True}

    return {"status": "success", "data": {"nodes": [], "edges": []}, "cached": False}
