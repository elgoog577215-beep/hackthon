from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import ApiResponse
from common.models.operation_log import FeatureType
from infra.db import User, get_db
from service.auth import get_current_teacher
from service.course import (
    CourseCreateParams,
    CourseDeleteParams,
    CourseDetail,
    CourseOperationParams,
    CourseService,
    CourseUpdateParams,
    UnitCreateParams,
    UnitDeleteParams,
    UnitNode,
    UnitOperationParams,
    UnitReorderParams,
    UnitService,
    UnitUpdateParams,
)
from service.operation_log import log_operation


router = APIRouter()


# ---------- 依赖注入 ----------

async def get_course_service(db: AsyncSession = Depends(get_db)) -> CourseService:
    return CourseService(db)

async def get_unit_service(db: AsyncSession = Depends(get_db)) -> UnitService:
    return UnitService(db)


# ---------- API 接口 ----------

@router.get(
    "",
    summary="按 ID 查询课程",
    response_model=ApiResponse[CourseDetail | None],
)
async def query_course_by_id(
    id: str,
    service: CourseService = Depends(get_course_service),
    current_user: User = Depends(get_current_teacher),
) -> ApiResponse[CourseDetail | None]:
    """根据课程 ID 返回课程详情，不存在时返回空数据。"""
    course = await service.get_course_by_id(id, current_user)
    return ApiResponse.success_response(course)


@router.get(
    "/list",
    summary="按条件筛选课程列表",
    response_model=ApiResponse[list[CourseDetail]],
)
async def list_courses(
    keyword: str | None = None,
    service: CourseService = Depends(get_course_service),
    current_user: User = Depends(get_current_teacher),
) -> ApiResponse[list[CourseDetail]]:
    """按关键词筛选当前用户可见课程，未传关键词时返回全部可见课程。"""
    courses = await service.list_courses(keyword, current_user)
    return ApiResponse.success_response(courses)


@router.post(
    "/operation",
    summary="执行课程操作",
    response_model=ApiResponse[str | None],
)
async def operate_course(
    params: CourseOperationParams,
    service: CourseService = Depends(get_course_service),
    current_user: User = Depends(get_current_teacher),
) -> ApiResponse[str | None]:
    """对课程执行增删改等操作，具体行为由 operation 字段决定。"""
    match params:
        case CourseCreateParams():
            id = await service.create_course(params, current_user)
            return ApiResponse.success_response(id)
        case CourseUpdateParams():
            await service.update_course(params, current_user)
            return ApiResponse.success_response(None)
        case CourseDeleteParams():
            await service.delete_course(params, current_user)
            return ApiResponse.success_response(None)


@router.get(
    "/unit/list",
    summary="查询课程单元树",
    response_model=ApiResponse[list[UnitNode]],
)
async def list_units(
    course_id: str,
    service: UnitService = Depends(get_unit_service),
    current_user: User = Depends(get_current_teacher),
) -> ApiResponse[list[UnitNode]]:
    """根据课程 ID 返回课程单元层级结构。"""
    units = await service.list_units(course_id, current_user)
    return ApiResponse.success_response(units)


@router.post(
    "/unit/operation",
    summary="执行单元操作",
    response_model=ApiResponse[str | None],
)
async def operate_unit(
    params: UnitOperationParams,
    service: UnitService = Depends(get_unit_service),
    current_user: User = Depends(get_current_teacher),
) -> ApiResponse[str | None]:
    """对课程单元执行增删改等操作，具体行为由 operation 字段决定。"""
    match params:
        case UnitCreateParams():
            id = await service.create_unit(params, current_user)
            return ApiResponse.success_response(id)
        case UnitUpdateParams():
            await service.update_unit(params, current_user)
            return ApiResponse.success_response(None)
        case UnitDeleteParams():
            await service.delete_unit(params, current_user)
            return ApiResponse.success_response(None)
        case UnitReorderParams():
            await service.reorder_unit(params, current_user)
            return ApiResponse.success_response(None)


@router.post(
    "/visit",
    summary="记录我的课程页面访问（埋点专用）",
    response_model=ApiResponse[None],
)
async def visit_my_courses(
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    """前端 fire-and-forget 调用，用户进入 /my-courses 页面时记录一次访问。"""
    await log_operation(
        db,
        user_id=current_user.id,
        feature_type=FeatureType.COURSE,
        action="visit",
    )
    return ApiResponse.success_response(None)
