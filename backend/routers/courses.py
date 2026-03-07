# =============================================================================
# 课程管理路由
# 课程 CRUD、课程生成
# =============================================================================

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
import uuid
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from models import GenerateCourseRequest, LocateNodeRequest
from storage import storage
from ai_service import ai_service
from dependencies import get_course_or_404

router = APIRouter(tags=["courses"])


@router.get("/courses")
async def list_courses():
    return await run_in_threadpool(storage.list_courses)


@router.get("/courses/{course_id}")
async def get_course(course_id: str):
    return await get_course_or_404(course_id)


@router.delete("/courses/{course_id}")
async def delete_course(course_id: str):
    await run_in_threadpool(storage.delete_course, course_id)
    return {"status": "success"}


@router.post("/generate_course")
async def generate_course(req: GenerateCourseRequest):
    data = await ai_service.generate_course(
        req.keyword,
        difficulty=req.difficulty,
        style=req.style,
        requirements=req.requirements
    )

    course_id = str(uuid.uuid4())
    data["course_id"] = course_id
    data["difficulty"] = req.difficulty
    data["style"] = req.style
    data["requirements"] = req.requirements

    await run_in_threadpool(storage.save_course, course_id, data)
    return data


@router.post("/courses/{course_id}/locate")
async def locate_node(course_id: str, req: LocateNodeRequest):
    tree_data = await get_course_or_404(course_id)
    if "nodes" not in tree_data:
        return {}
    return await ai_service.locate_node(req.keyword, tree_data["nodes"])
