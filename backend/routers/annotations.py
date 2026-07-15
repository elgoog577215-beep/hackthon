# =============================================================================
# 标注与笔记路由
# Annotations CRUD、课程级批注查询
# =============================================================================

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
import uuid
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from models import SaveAnnotationRequest, UpdateAnnotationRequest
from storage import storage
from ai_service import ai_service
from dependencies import get_course_or_404
from adaptive_models import EvidenceItem

router = APIRouter(tags=["annotations"])


@router.get("/nodes/{node_id}/annotations")
async def get_annotations(node_id: str):
    return await run_in_threadpool(storage.get_annotations_by_node, node_id)


@router.post("/annotations")
async def save_annotation(req: SaveAnnotationRequest):
    data = req.dict()
    if not data.get("anno_id"):
        data["anno_id"] = f"anno_{uuid.uuid4()}"

    if len(data.get("answer", "")) > 50:
        current_summary = data.get("anno_summary", "")
        answer_start = data.get("answer", "")[:20]
        if not current_summary or current_summary.startswith(answer_start) or current_summary == "Note":
            try:
                generated_summary = await ai_service.summarize_note(data["answer"])
                if generated_summary:
                    data["anno_summary"] = generated_summary
            except Exception as e:
                print(f"Failed to generate AI summary for note: {e}")

    await run_in_threadpool(storage.save_annotation, data)

    # 学习证据采集钩子：课程内笔记回流为 EvidenceItem（规格文档 §4 "学习证据 MUST
    # 驱动个体化课程演化" Requirement）。仅在 course_id 存在时落盘，不阻塞主流程。
    if data.get("course_id") and data.get("node_id"):
        try:
            evidence = EvidenceItem(
                node_id=data["node_id"],
                evidence_type="note",
                strength=0.4,
                strength_label="medium",
                content=(data.get("answer") or data.get("anno_summary") or "")[:500],
                course_id=data["course_id"],
                metadata={"anno_id": data.get("anno_id"), "source_type": data.get("source_type")},
            )
            await storage.save_evidence_item(data["course_id"], evidence.model_dump(mode="json"))
        except Exception as e:
            print(f"Failed to record note evidence: {e}")

    return data


@router.delete("/annotations/{anno_id}")
async def delete_annotation(anno_id: str):
    await run_in_threadpool(storage.delete_annotation, anno_id)
    return {"status": "success"}


@router.put("/annotations/{anno_id}")
async def update_annotation(anno_id: str, req: UpdateAnnotationRequest):
    await run_in_threadpool(storage.update_annotation, anno_id, req.content)
    return {"status": "success"}


@router.put("/annotations/{anno_id}/tags")
async def update_annotation_tags(anno_id: str, req: dict):
    tags = req.get("tags", [])
    updated = await run_in_threadpool(storage.update_annotation_field, anno_id, "tags", tags)
    if not updated:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"status": "success"}


@router.put("/annotations/{anno_id}/category")
async def update_annotation_category(anno_id: str, req: dict):
    category = req.get("category", "")
    updated = await run_in_threadpool(storage.update_annotation_field, anno_id, "category", category)
    if not updated:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"status": "success"}


@router.put("/annotations/{anno_id}/priority")
async def update_annotation_priority(anno_id: str, req: dict):
    priority = req.get("priority", "medium")
    updated = await run_in_threadpool(storage.update_annotation_field, anno_id, "priority", priority)
    if not updated:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"status": "success"}


@router.get("/courses/{course_id}/annotations")
async def get_course_annotations(course_id: str):
    """返回课程的所有批注"""
    course_data = await get_course_or_404(course_id)

    if "nodes" not in course_data:
        return []

    node_ids = set(n["node_id"] for n in course_data["nodes"])

    all_annos = await run_in_threadpool(storage.load_annotations)
    results = []
    for a in all_annos:
        if a.get("course_id"):
            if a.get("course_id") == course_id:
                results.append(a)
        elif a.get("node_id") in node_ids:
            if len(a.get("node_id", "")) > 10:
                results.append(a)

    return results
