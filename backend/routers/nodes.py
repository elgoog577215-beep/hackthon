# =============================================================================
# 节点操作路由
# 节点 CRUD、子节点生成、内容重定义/扩展/摘要
# =============================================================================

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.concurrency import run_in_threadpool
import uuid
import logging
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from models import (
    AddNodeRequest, GenerateSubNodesRequest, RedefineContentRequest,
    ExtendContentRequest, SummarizeNodeRequest,
    UpdateNodeRequest, LocateNodeRequest, SelectionRewriteRequest,
    SelectionRewriteResponse, RegenerateContentBlockRequest
)
from storage import storage
from ai_service import ai_service
from course_service import get_course_service
from content_blocks import blocks_to_markdown, normalize_blocks
from dependencies import get_course_document_repository, get_course_or_404, get_node_or_404
from learner_context import require_user_id
from learning_events import record_learning_event, summarize_text
from storage_utils import save_course_compat

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
    await save_course_compat(storage, course_id, tree_data)
    return new_node


@router.post("/{node_id}/subnodes")
async def generate_subnodes(course_id: str, node_id: str, req: GenerateSubNodesRequest):
    tree_data = await get_course_or_404(course_id)

    existing_children = [n for n in tree_data.get("nodes", []) if n.get("parent_node_id") == node_id]
    if existing_children:
        return existing_children

    course_name = tree_data.get("course_name", "")
    course_service = get_course_service()
    course_service.register_course_generation_metadata(course_id, tree_data)

    new_nodes = await course_service.generate_sub_nodes(
        req.node_name,
        req.node_level,
        node_id,
        course_name,
        course_id=course_id,
        difficulty=req.difficulty,
        style=req.style,
    )

    if "nodes" not in tree_data:
        tree_data["nodes"] = []

    for node in new_nodes:
        tree_data["nodes"].append(node)
    await save_course_compat(storage, course_id, tree_data)
    return new_nodes


@router.post("/{node_id}/redefine_stream")
async def redefine_node_stream(course_id: str, node_id: str, req: RedefineContentRequest, request: Request):
    tree_data = await get_course_or_404(course_id)
    node = get_node_or_404(tree_data, node_id)
    course_service = get_course_service()
    course_service.register_course_generation_metadata(course_id, tree_data)
    user_id = require_user_id(request.headers.get("X-User-Id"))

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
                style=req.style,
                user_id=user_id,
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
                        node["content_blocks"] = []
                        node["node_type"] = "custom"
                        break
                await save_course_compat(storage, course_id, current_data)
        except Exception as e:
            logger.error(f"Error saving stream result: {e}")

    return StreamingResponse(stream_generator(), media_type="text/plain")


@router.post("/{node_id}/redefine")
async def redefine_node(course_id: str, node_id: str, req: RedefineContentRequest, request: Request):
    tree_data = await get_course_or_404(course_id)
    node = get_node_or_404(tree_data, node_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))

    course_service = get_course_service()
    course_service.register_course_generation_metadata(course_id, tree_data)
    new_content = await course_service.redefine_content(
        course_id=course_id,
        node=node,
        requirement=req.user_requirement,
        original_content=req.original_content,
        course_context=req.course_context,
        previous_context=req.previous_context,
        difficulty=req.difficulty,
        style=req.style,
        user_id=user_id,
    )

    node["node_content"] = new_content
    node["content_blocks"] = []
    node["node_type"] = "custom"
    await save_course_compat(storage, course_id, tree_data)
    return {"node_content": new_content}


@router.post("/{node_id}/selection-rewrite", response_model=SelectionRewriteResponse)
async def rewrite_node_selection(course_id: str, node_id: str, req: SelectionRewriteRequest, request: Request):
    tree_data = await get_course_or_404(course_id)
    node = get_node_or_404(tree_data, node_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    course_service = get_course_service()
    course_service.register_course_generation_metadata(course_id, tree_data)
    result = await course_service.rewrite_selection(
        course_id=course_id,
        node=node,
        selected_text=req.selected_text,
        node_content=req.node_content or node.get("node_content", ""),
        heading_path=req.heading_path,
        before_context=req.before_context or "",
        after_context=req.after_context or "",
        user_requirement=req.user_requirement or "",
        action_type=req.action_type,
        course_context=req.course_context or "",
        previous_context=req.previous_context or "",
        user_id=user_id,
    )

    record_learning_event(
        event_type="markdown_selection_rewrite_requested",
        actor="user",
        source="nodes.selection-rewrite",
        user_id=user_id,
        course_id=course_id,
        node_id=node_id,
        node_name=node.get("node_name", ""),
        evidence={
            "action_type": req.action_type,
            "heading_path": req.heading_path,
            "selected_summary": summarize_text(req.selected_text, limit=360),
            "before_summary": summarize_text(req.before_context or "", limit=180),
            "after_summary": summarize_text(req.after_context or "", limit=180),
            "requirement": summarize_text(req.user_requirement or "", limit=300),
        },
        result={
            "status": "candidate_generated",
            "replacement_summary": summarize_text(result.get("replacement_text", ""), limit=360),
            "replacement_chars": len(result.get("replacement_text", "")),
        },
        metadata={
            "node_content_chars": len(req.node_content or node.get("node_content", "") or ""),
        },
    )
    return SelectionRewriteResponse(**result)


@router.post("/{node_id}/blocks/{block_id}/regenerate")
async def regenerate_node_content_block(
    course_id: str,
    node_id: str,
    block_id: str,
    req: RegenerateContentBlockRequest,
    request: Request,
):
    repository = get_course_document_repository()
    raw_course = await run_in_threadpool(repository.load_raw, course_id)
    if repository.is_canonical(raw_course):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "canonical_block_regeneration_required",
                "message": "Canonical course blocks must use regeneration candidates",
                "endpoint": f"/api/courses/{course_id}/blocks/{block_id}/regeneration-candidates",
            },
        )
    tree_data = await get_course_or_404(course_id)
    node = get_node_or_404(tree_data, node_id)
    blocks = normalize_blocks(node_id, node.get("content_blocks"), node.get("node_content", ""))
    target_index = next((idx for idx, block in enumerate(blocks) if block.get("block_id") == block_id), None)
    if target_index is None:
        raise HTTPException(status_code=404, detail="Content block not found")
    user_id = require_user_id(request.headers.get("X-User-Id"))

    try:
        course_service = get_course_service()
        course_service.register_course_generation_metadata(course_id, tree_data)
        updated_block = await course_service.regenerate_content_block(
            course_id=course_id,
            node={**node, "content_blocks": blocks},
            block_id=block_id,
            requirement=req.requirement or "",
            action_type=req.action_type,
            user_id=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    blocks[target_index] = {**blocks[target_index], **updated_block, "block_id": block_id}
    node["content_blocks"] = blocks
    node["node_content"] = blocks_to_markdown(blocks)
    node["node_type"] = "custom"
    await save_course_compat(storage, course_id, tree_data)

    record_learning_event(
        event_type="content_block_regenerated",
        actor="user",
        source="nodes.block-regenerate",
        user_id=user_id,
        course_id=course_id,
        node_id=node_id,
        node_name=node.get("node_name", ""),
        evidence={
            "block_id": block_id,
            "block_title": blocks[target_index].get("title", ""),
            "block_type": blocks[target_index].get("type", ""),
            "action_type": req.action_type,
            "requirement": summarize_text(req.requirement or "", limit=300),
        },
        result={
            "status": "regenerated",
            "content_summary": summarize_text(blocks[target_index].get("content", ""), limit=360),
        },
    )
    return {"block": blocks[target_index], "node_content": node["node_content"]}


@router.post("/{node_id}/extend")
async def extend_node_content(course_id: str, node_id: str, req: ExtendContentRequest, request: Request):
    tree_data = await get_course_or_404(course_id)
    node = get_node_or_404(tree_data, node_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    course_service = get_course_service()
    course_service.register_course_generation_metadata(course_id, tree_data)
    content = await course_service.extend_content(
        course_id=course_id,
        node=node,
        requirement=req.user_requirement,
        current_content=req.current_content,
        user_id=user_id,
    )
    return {"content": content}


@router.post("/{node_id}/summarize")
async def summarize_node(course_id: str, node_id: str, req: SummarizeNodeRequest, request: Request):
    user_id = require_user_id(request.headers.get("X-User-Id"))
    summary = await get_course_service().summarize_content(
        req.node_content,
        node_name=req.node_name,
        user_persona=req.user_persona,
        course_id=course_id,
        node_id=node_id,
        user_id=user_id,
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
        await save_course_compat(storage, course_id, tree_data)
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
        node["node_content"] = node_update.node_content
        node["content_blocks"] = []
    if node_update.is_read is not None:
        node["is_read"] = node_update.is_read

    await save_course_compat(storage, course_id, tree_data)
    return {"status": "success", "node": node}
