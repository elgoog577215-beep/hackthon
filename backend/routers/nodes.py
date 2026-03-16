# =============================================================================
# 节点操作路由
# 节点 CRUD、子节点生成、内容重定义/扩展/摘要
# =============================================================================

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from fastapi.concurrency import run_in_threadpool
import uuid
import logging
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from models import (
    AddNodeRequest, GenerateSubNodesRequest, RedefineContentRequest,
    ExtendContentRequest, SummarizeNodeRequest, GenerateQuizRequest,
    UpdateNodeRequest, LocateNodeRequest
)
from storage import storage
from ai_service import ai_service
from dependencies import get_course_or_404, get_node_or_404, build_course_outline, get_node_content

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/courses/{course_id}/nodes", tags=["nodes"])


@router.post("")
async def add_custom_node(course_id: str, req: AddNodeRequest):
    tree_data = await get_course_or_404(course_id)

    level = 1
    if req.parent_node_id and req.parent_node_id != "root":
        parent = get_node_or_404(tree_data, req.parent_node_id)
        level = parent.get("node_level", 1) + 1

    new_node = {
        "node_id": str(uuid.uuid4()),
        "parent_node_id": req.parent_node_id,
        "node_name": req.node_name,
        "node_level": level,
        "node_content": "",
        "node_type": "custom",
        "generation_status": "pending",
        "generated_chars": 0,
        "error_summary": None,
    }

    if "nodes" not in tree_data:
        tree_data["nodes"] = []

    tree_data["nodes"].append(new_node)
    await run_in_threadpool(storage.save_course, course_id, tree_data)
    return new_node


@router.post("/{node_id}/subnodes")
async def generate_subnodes(course_id: str, node_id: str, req: GenerateSubNodesRequest):
    tree_data = await get_course_or_404(course_id)

    existing_children = [n for n in tree_data.get("nodes", []) if n.get("parent_node_id") == node_id]
    if existing_children:
        return existing_children

    course_name = tree_data.get("course_name", "")
    course_outline = build_course_outline(tree_data, max_content_length=50)
    parent_context = get_node_content(tree_data, node_id)

    new_nodes = await ai_service.generate_sub_nodes(
        req.node_name, req.node_level, node_id, course_name,
        parent_context, course_outline, req.difficulty, req.style
    )

    if "nodes" not in tree_data:
        tree_data["nodes"] = []

    for node in new_nodes:
        tree_data["nodes"].append(node)
    await run_in_threadpool(storage.save_course, course_id, tree_data)
    return new_nodes


@router.post("/{node_id}/redefine_stream")
async def redefine_node_stream(course_id: str, node_id: str, req: RedefineContentRequest):
    await get_course_or_404(course_id)

    async def stream_generator():
        full_content = ""
        try:
            async for chunk in ai_service.redefine_node_content(
                node_name=req.node_name,
                original_content=req.original_content,
                requirement=req.user_requirement,
                course_context=req.course_context,
                previous_context=req.previous_context,
                difficulty=req.difficulty,
                style=req.style
            ):
                full_content += chunk
                yield chunk
        except Exception as e:
            logger.error(f"Error in stream generation: {e}")
            yield f"\n[Error: {e}]"

        try:
            current_data = await run_in_threadpool(storage.load_course, course_id)
            if "nodes" in current_data:
                for node in current_data["nodes"]:
                    if node["node_id"] == node_id:
                        node["node_content"] = ai_service.clean_response_text(full_content)
                        node["node_type"] = "custom"
                        break
                await run_in_threadpool(storage.save_course, course_id, current_data)
        except Exception as e:
            logger.error(f"Error saving stream result: {e}")

    return StreamingResponse(stream_generator(), media_type="text/plain")


@router.post("/{node_id}/redefine")
async def redefine_node(course_id: str, node_id: str, req: RedefineContentRequest):
    tree_data = await get_course_or_404(course_id)
    node = get_node_or_404(tree_data, node_id)

    new_content = await ai_service.redefine_content(
        node_name=req.node_name,
        requirement=req.user_requirement,
        original_content=req.original_content,
        course_context=req.course_context,
        previous_context=req.previous_context,
        difficulty=req.difficulty,
        style=req.style
    )

    node["node_content"] = new_content
    node["node_type"] = "custom"
    await run_in_threadpool(storage.save_course, course_id, tree_data)
    return {"node_content": new_content}


@router.post("/{node_id}/quiz")
async def generate_node_quiz(course_id: str, node_id: str, req: GenerateQuizRequest):
    return await ai_service.generate_quiz(
        req.node_content,
        node_name=req.node_name,
        difficulty=req.difficulty,
        style=req.style,
        user_persona=req.user_persona,
        question_count=req.question_count,
        discipline_type=req.discipline_type
    )



@router.post("/{node_id}/extend")
async def extend_node_content(course_id: str, node_id: str, req: ExtendContentRequest):
    content = await ai_service.extend_content(req.node_name, req.user_requirement)
    return {"content": content}


@router.post("/{node_id}/summarize")
async def summarize_node(course_id: str, node_id: str, req: SummarizeNodeRequest):
    summary = await ai_service.summarize_content(
        req.node_content,
        node_name=req.node_name,
        user_persona=req.user_persona
    )
    return {"summary": summary}


@router.delete("/{node_id}")
async def delete_node(course_id: str, node_id: str):
    tree_data = await get_course_or_404(course_id)

    if "nodes" not in tree_data:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Course has no nodes")

    original_len = len(tree_data["nodes"])

    to_delete = {node_id}
    changed = True
    while changed:
        changed = False
        for node in tree_data["nodes"]:
            if node.get("parent_node_id") in to_delete and node["node_id"] not in to_delete:
                to_delete.add(node["node_id"])
                changed = True

    tree_data["nodes"] = [n for n in tree_data["nodes"] if n["node_id"] not in to_delete]

    if len(tree_data["nodes"]) < original_len:
        await run_in_threadpool(storage.save_course, course_id, tree_data)
        return {"status": "success"}

    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Node not found")


@router.put("/{node_id}")
async def update_node(course_id: str, node_id: str, node_update: UpdateNodeRequest):
    tree_data = await get_course_or_404(course_id)

    if "nodes" not in tree_data:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Course has no nodes")

    node = get_node_or_404(tree_data, node_id)

    if node_update.node_name is not None:
        node["node_name"] = node_update.node_name
    if node_update.node_content is not None:
        node["node_content"] = node_update.node_content
    if node_update.is_read is not None:
        node["is_read"] = node_update.is_read

    await run_in_threadpool(storage.save_course, course_id, tree_data)
    return {"status": "success", "node": node}


