# =============================================================================
# 节点操作路由
# 节点 CRUD、子节点生成、内容重定义/扩展/摘要
# =============================================================================

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.concurrency import run_in_threadpool
import uuid
import logging
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from models import (
    AddNodeRequest, GenerateSubNodesRequest, RedefineContentRequest,
    ExtendContentRequest, SummarizeNodeRequest, GenerateQuizRequest,
    UpdateNodeRequest, LocateNodeRequest, RegenerateBlockRequest
)
from storage import storage
from ai_service import ai_service
from course_service import get_course_service
from content_blocks import blocks_to_markdown, normalize_blocks, set_node_content_blocks
from dependencies import get_course_or_404, get_node_or_404

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
        "content_blocks": [],
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

    new_nodes = await get_course_service().generate_sub_nodes(
        req.node_name,
        req.node_level,
        node_id,
        course_name,
        difficulty=req.difficulty,
        style=req.style,
    )

    if "nodes" not in tree_data:
        tree_data["nodes"] = []

    for node in new_nodes:
        tree_data["nodes"].append(node)
    await run_in_threadpool(storage.save_course, course_id, tree_data)
    return new_nodes


@router.post("/{node_id}/redefine_stream")
async def redefine_node_stream(course_id: str, node_id: str, req: RedefineContentRequest):
    tree_data = await get_course_or_404(course_id)
    node = get_node_or_404(tree_data, node_id)
    course_service = get_course_service()

    async def stream_generator():
        full_content = ""
        try:
            async for chunk in course_service.redefine_node_content_stream(
                course_id=course_id,
                node=node,
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
                        set_node_content_blocks(node, ai_service.clean_response_text(full_content))
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

    new_content = await get_course_service().redefine_content(
        course_id=course_id,
        node=node,
        requirement=req.user_requirement,
        original_content=req.original_content,
        course_context=req.course_context,
        previous_context=req.previous_context,
        difficulty=req.difficulty,
        style=req.style
    )

    set_node_content_blocks(node, new_content)
    node["node_type"] = "custom"
    await run_in_threadpool(storage.save_course, course_id, tree_data)
    return {"node_content": new_content}


@router.post("/{node_id}/blocks/{block_id}/regenerate")
async def regenerate_content_block(
    course_id: str,
    node_id: str,
    block_id: str,
    req: RegenerateBlockRequest,
):
    tree_data = await get_course_or_404(course_id)
    node = get_node_or_404(tree_data, node_id)
    blocks = normalize_blocks(node_id, node.get("content_blocks"), node.get("node_content", ""))
    target_index = next(
        (idx for idx, block in enumerate(blocks) if block.get("block_id") == block_id),
        None,
    )
    if target_index is None:
        raise HTTPException(status_code=404, detail="Content block not found")

    node["content_blocks"] = blocks
    course_service = get_course_service()
    try:
        from discipline_config import detect_discipline_type
        if hasattr(course_service, "_context_manager"):
            course_service._context_manager.ensure_context_from_nodes(
                course_id=course_id,
                course_name=tree_data.get("course_name", ""),
                nodes=tree_data.get("nodes", []),
                discipline=detect_discipline_type(tree_data.get("course_name", "")),
            )
    except Exception:
        logger.debug("Could not rebuild context before block regeneration", exc_info=True)

    try:
        updated_block = await course_service.regenerate_content_block(
            course_id=course_id,
            node=node,
            block_id=block_id,
            requirement=req.requirement,
            difficulty=req.difficulty,
            style=req.style,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Content block not found")

    blocks[target_index] = updated_block
    node["content_blocks"] = blocks
    node["node_content"] = blocks_to_markdown(blocks)
    node["node_type"] = "custom"
    await run_in_threadpool(storage.save_course, course_id, tree_data)
    return {
        "block": updated_block,
        "content_blocks": blocks,
        "node_content": node["node_content"],
    }


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
    tree_data = await get_course_or_404(course_id)
    node = get_node_or_404(tree_data, node_id)
    content = await get_course_service().extend_content(
        course_id=course_id,
        node=node,
        requirement=req.user_requirement,
        current_content=req.current_content,
    )
    return {"content": content}


@router.post("/{node_id}/summarize")
async def summarize_node(course_id: str, node_id: str, req: SummarizeNodeRequest):
    summary = await get_course_service().summarize_content(
        req.node_content,
        node_name=req.node_name,
        user_persona=req.user_persona,
        course_id=course_id,
        node_id=node_id,
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
    if node_update.content_blocks is not None:
        raw_blocks = [
            block.model_dump() if hasattr(block, "model_dump") else block.dict()
            for block in node_update.content_blocks
        ]
        blocks = normalize_blocks(
            node_id,
            raw_blocks,
            node.get("node_content", ""),
        )
        node["content_blocks"] = blocks
        node["node_content"] = blocks_to_markdown(blocks)
    if node_update.node_content is not None:
        set_node_content_blocks(node, node_update.node_content)
    if node_update.is_read is not None:
        node["is_read"] = node_update.is_read

    await run_in_threadpool(storage.save_course, course_id, tree_data)
    return {"status": "success", "node": node}
