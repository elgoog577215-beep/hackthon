from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from common.models import SystemException
from infra.db import Course, Resource, User
from service.course.converters import course_to_detail
from service.course.models import (
    CourseCreateParams,
    CourseDeleteParams,
    CourseDetail,
    CourseUpdateParams,
)
from common.utils.logger import get_logger

logger = get_logger(__name__)


class CourseService:
    """
    课程服务
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------- 公共方法 ----------

    async def get_course_by_id(self, id: str, current_user: User) -> CourseDetail | None:
        """根据 id 查询课程详情"""
        db_course = (await self.db.execute(
            select(Course)
            .where(
                Course.id == id,
                Course.managers.any(User.id == current_user.id),
            )
            .options(selectinload(Course.managers))
        )).scalars().first()
        if not db_course:
            return None
        return course_to_detail(db_course)

    async def list_courses(self, keyword: str | None, current_user: User) -> list[CourseDetail]:
        """条件查询课程"""
        return [course_to_detail(course) for course in (await self.db.execute(
            select(Course)
            .where(
                Course.managers.any(User.id == current_user.id),
                or_(
                    Course.name.contains(keyword),
                    func.array_to_string(Course.labels, ",").contains(keyword),
                ) if keyword else True,
            )
            .order_by(Course.create_time.desc())
            .options(selectinload(Course.managers))
        )).unique().scalars().all()]

    async def create_course(self, params: CourseCreateParams, current_user: User) -> str:
        """创建课程"""
        managers = []
        # manager_id 列表按"存在即添加"处理；不存在用户会被忽略
        for manager_id in params.manager_ids:
            manager = (await self.db.execute(select(User).where(User.id == manager_id))).scalars().first()
            if manager:
                managers.append(manager)

        db_course = Course(
            name=params.name,
            lesson_count=params.lesson_count,
            description=params.description,
            labels=params.labels,
            extra_info=params.extra_info,
            creator_id=current_user.id,
            managers=managers,
        )
        self.db.add(db_course)
        await self.db.commit()
        return db_course.id

    async def update_course(self, params: CourseUpdateParams, current_user: User) -> None:
        """更新课程"""
        db_course = await self._get_course_or_raise(params.id, current_user.id)

        # 这里是"增量追加负责人"，不会替换已有 managers
        if params.manager_ids:
            for manager_id in params.manager_ids:
                manager = (await self.db.execute(select(User).where(User.id == manager_id))).scalars().first()
                if not manager:
                    logger.error(f"[service.py] 负责人不存在: {manager_id}")
                    raise SystemException(f"负责人不存在: {manager_id}")
                db_course.managers.append(manager)

        if params.name is not None:
            db_course.name = params.name
        if params.lesson_count is not None:
            db_course.lesson_count = params.lesson_count
        if params.description is not None:
            db_course.description = params.description
        if params.labels is not None:
            db_course.labels = params.labels
        if params.extra_info is not None:
            db_course.extra_info = params.extra_info
        await self.db.commit()

    async def delete_course(self, params: CourseDeleteParams, current_user: User) -> None:
        """删除课程及其关联数据（单元、资源）。

        resources.related_course_id 是 ON DELETE SET NULL：课程删除后，其下的根级资源会
        变为"无课程归属"。若对应创建者在该作用域下已存在同类型同版本号的资源，会撞上
        uq_resources_root_scope_version 唯一索引导致整个删除失败——这里提前把即将脱离
        课程的根级资源重新编号，避免与已有的无课程归属资源冲突。
        """
        db_course = await self._get_course_or_raise(params.id, current_user.id)
        await self._renumber_detaching_resources(params.id)

        await self.db.delete(db_course)
        await self.db.commit()

    async def _renumber_detaching_resources(self, course_id: str) -> None:
        """课程删除前，把即将因 SET NULL 脱离课程的根级资源按 (创建者, 类型) 重新编号。"""
        detaching = (await self.db.execute(
            select(Resource).where(
                Resource.related_course_id == course_id,
                Resource.parent_resource_id.is_(None),
            )
        )).scalars().all()
        if not detaching:
            return

        by_scope: dict[tuple[str, str], list[Resource]] = {}
        for r in detaching:
            by_scope.setdefault((r.creator_id, r.resource_type), []).append(r)

        for (creator_id, resource_type), items in by_scope.items():
            unscoped_max_version = (await self.db.execute(
                select(func.max(Resource.version_number)).where(
                    Resource.creator_id == creator_id,
                    Resource.related_course_id.is_(None),
                    Resource.resource_type == resource_type,
                    Resource.parent_resource_id.is_(None),
                )
            )).scalar() or 0
            current_max_version = max((r.version_number for r in items), default=0)
            next_version = max(unscoped_max_version, current_max_version)
            for r in sorted(items, key=lambda x: x.version_number):
                next_version += 1
                r.version_number = next_version


    # ---------- 私有方法 ----------

    async def _get_course_or_raise(self, id: str, user_id: str) -> Course:
        """按 ID 查询课程，不存在或无权限时抛出 SystemException。"""
        db_course = (await self.db.execute(
            select(Course)
            .where(
                Course.id == id,
                Course.managers.any(User.id == user_id),
            )
            .options(selectinload(Course.managers))
        )).scalars().first()
        if not db_course:
            logger.error(f"[service.py] 课程不存在或无权限: {id}")
            raise SystemException(f"课程不存在或无权限: {id}")
        return db_course
