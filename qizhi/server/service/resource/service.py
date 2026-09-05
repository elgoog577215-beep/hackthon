import os

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, joinedload, selectinload

from common.models import BizException, SystemException
from agents.llm import complete_chat
from common.utils.file import convert_file_to_markdown, count_text_words
from infra.db import Course, CourseUnit, Resource, User
from service.resource.converters import resource_to_detail, resource_to_summary
from service.resource.models import (
    RESOURCE_PARENT_TYPES,
    ResourceBindingParams,
    ResourceCopyParams,
    ResourceCreateParams,
    ResourceDeleteParams,
    ResourceDetail,
    ResourceSummary,
    ResourceTypeEnum,
    ResourceUpdateParams,
)
from common.utils.logger import get_logger

logger = get_logger(__name__)

class ResourceService:
    """
    资源服务
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------- 公共方法 ----------

    async def get_resource_by_id(self, id: str, current_user: User) -> ResourceDetail | None:
        """根据 id 查询资源详情"""
        return resource_to_detail((await self.db.execute(
            select(Resource)
            .where(
                Resource.id == id,
                Resource.creator_id == current_user.id,
            )
            .options(
                joinedload(Resource.related_course).joinedload(Course.managers),
                joinedload(Resource.related_unit),
                joinedload(Resource.parent_resource),
            )
        )).unique().scalars().first())

    async def list_resources(
        self,
        course_id: str | None,
        unit_id: str | None,
        resource_type: ResourceTypeEnum | None,
        keyword: str | None,
        current_user: User,
        parent_resource_id: str | None = None,
        root_only: bool = False,
    ) -> list[ResourceSummary]:
        """条件查询资源。

        parent_resource_id：只返回挂在该父资源下的子版本（层级下钻用）。
        root_only：只返回没有父资源的根级资源（课程页大纲版本列表用，排除已挂接的子资源）。
        """
        child = aliased(Resource)
        child_count_col = (
            select(func.count(child.id))
            .where(child.parent_resource_id == Resource.id)
            .correlate(Resource)
            .scalar_subquery()
        )
        query = (
            select(Resource, child_count_col)
            .where(
                Resource.creator_id == current_user.id,
                Resource.related_course_id == course_id if course_id else True,
                Resource.related_unit_id == unit_id if unit_id else True,
                Resource.resource_type == resource_type if resource_type else True,
                Resource.parent_resource_id == parent_resource_id if parent_resource_id else True,
                Resource.parent_resource_id.is_(None) if root_only else True,
                or_(
                    Resource.name.contains(keyword),
                    Resource.related_course.has(Course.name.contains(keyword)),
                    Resource.related_unit.has(CourseUnit.name.contains(keyword)),
                )
                if keyword
                else True,
            )
            .options(
                joinedload(Resource.related_course).selectinload(Course.managers),
                joinedload(Resource.related_unit),
            )
        )
        # 层级视图（按父资源/课程下钻）按版本号倒序；全局列表保持时间倒序
        if parent_resource_id or root_only:
            query = query.order_by(Resource.version_number.desc(), Resource.create_time.desc())
        else:
            query = query.order_by(Resource.create_time.desc())

        rows = (await self.db.execute(query)).unique().all()
        return [resource_to_summary(resource, child_count or 0) for resource, child_count in rows]

    async def create_resource(self, params: ResourceCreateParams, current_user: User) -> str:
        """创建资源"""
        editable = params.editable
        if not editable and not params.path:
            raise BizException("只读资源必须提供文件路径")

        related_course_id = params.related_course_id or None
        related_unit_id = params.related_unit_id or None

        # 父资源校验（类型链：大纲 → 教案 → PPT）。子资源的课程归属与父资源强一致，
        # 否则「按课程过滤」与「按父资源下钻」两个视图会互相矛盾。
        parent_resource_id = params.parent_resource_id or None
        if parent_resource_id:
            parent = await self._get_parent_or_raise(parent_resource_id, params.resource_type, current_user.id)
            related_course_id = parent.related_course_id

        # 关联课程/单元需要校验存在性
        if related_course_id:
            related_course = (await self.db.execute(
                select(Course)
                .where(Course.id == related_course_id)
                .options(selectinload(Course.managers))
            )).scalars().first()
            if not related_course:
                logger.error(f"[service.py] 关联课程不存在: {related_course_id}")
                raise SystemException(f"关联课程不存在: {related_course_id}")
        if related_unit_id:
            related_unit = (await self.db.execute(
                select(CourseUnit)
                .where(CourseUnit.id == related_unit_id)
                .options(joinedload(CourseUnit.course).selectinload(Course.managers))
            )).scalars().first()
            if not related_unit:
                logger.error(f"[service.py] 关联单元不存在: {related_unit_id}")
                raise SystemException(f"关联单元不存在: {related_unit_id}")

        version_number = await self._next_version_number(
            params.resource_type, current_user.id, related_course_id, parent_resource_id
        )

        db_resource = Resource(
            name=params.name,
            path=params.path if not editable else None,
            resource_type=params.resource_type,
            editable=editable,
            version_number=version_number,
            creator_id=current_user.id,
            related_course_id=related_course_id,
            related_unit_id=related_unit_id,
            parent_resource_id=parent_resource_id,
        )
        await self._add_with_version_retry(db_resource, params.resource_type, current_user.id)
        return db_resource.id

    async def update_resource(self, params: ResourceUpdateParams, current_user: User) -> None:
        """更新资源"""
        db_resource = await self._get_resource_or_raise(params.id, current_user.id)

        if params.content is not None:
            if not db_resource.editable:
                raise BizException("只读资源不允许编辑内容，请先复制为可编辑副本")
            db_resource.content = params.content
            db_resource.word_count = count_text_words(params.content)

        if params.name is not None:
            db_resource.name = params.name

        await self.db.commit()

    async def delete_resource(self, params: ResourceDeleteParams, current_user: User) -> None:
        """删除资源。只读资源会同步删除对应的物理文件。"""
        db_resource = await self._get_resource_or_raise(params.id, current_user.id)

        # 有子版本（教案/PPT 等挂在其下）的资源不允许直接删除，避免层级断链
        child_count = (await self.db.execute(
            select(func.count(Resource.id)).where(Resource.parent_resource_id == params.id)
        )).scalar()
        if child_count:
            raise BizException(f"该资源下还有 {child_count} 个子版本资源（教案/PPT 等），请先删除或改挂子资源")

        # 只读资源：删除物理文件
        if not db_resource.editable:
            os.remove(db_resource.path)

        await self.db.delete(db_resource)
        await self.db.commit()

    async def copy_resource(self, params: ResourceCopyParams, current_user: User) -> str:
        """复制资源为可编辑副本。"""
        db_resource = await self._get_resource_or_raise(params.id, current_user.id)

        # 只读资源：提取文件内容转为可编辑；可编辑资源直接复制
        if not db_resource.editable:
            raw_md = convert_file_to_markdown(db_resource.path)
            # LLM 修复 Markdown 格式（标题、列表、表格等）
            try:
                content = await complete_chat(
                    system_prompt=(
                        "你是一位 Markdown 格式化专家。请对以下由自动化工具提取的 Markdown 进行修复和优化：\n"
                        "1. 修复渲染错误：修复断裂的表格、错位的列表、不匹配的标题层级、错误的代码块等\n"
                        "2. 补充语义格式：根据内容语义，适当添加或修复标题（# ## ###）、列表（- / 1.）、表格、加粗、斜体等\n"
                        "3. 保留所有实质内容和数据，严禁增删信息\n"
                        "4. 输出必须是合法、可直接渲染的 Markdown，不要包含任何解释性文字"
                    ),
                    user_prompt=raw_md,
                )
            except Exception as e:
                logger.warning(f"[resource/service.py] LLM 修复 Markdown 失败，回退到原始文本: {e}")
                content = raw_md
            word_count = count_text_words(content)
        else:
            content = db_resource.content
            word_count = db_resource.word_count

        version_number = await self._next_version_number(
            ResourceTypeEnum(db_resource.resource_type),
            current_user.id,
            db_resource.related_course_id,
            db_resource.parent_resource_id,
        )

        db_new_resource = Resource(
            name=params.name,
            resource_type=db_resource.resource_type,
            content=content,
            word_count=word_count,
            editable=True,
            version_number=version_number,
            creator_id=current_user.id,
            related_course_id=db_resource.related_course_id,
            related_unit_id=db_resource.related_unit_id,
            parent_resource_id=db_resource.parent_resource_id,
        )
        await self._add_with_version_retry(
            db_new_resource, ResourceTypeEnum(db_resource.resource_type), current_user.id
        )
        return db_new_resource.id

    async def bind_resource(self, params: ResourceBindingParams, current_user: User) -> None:
        """绑定或取绑资源的课程/单元/父资源。

        版本号是作用域（父资源 / 课程）内的编号：作用域发生变化时必须按目标
        作用域重算，否则会与目标作用域中已有版本撞号。
        """
        db_resource = await self._get_resource_or_raise(params.id, current_user.id)
        old_scope = (db_resource.related_course_id, db_resource.parent_resource_id)

        if params.unbind:
            db_resource.related_course_id = None
            db_resource.related_unit_id = None
            db_resource.parent_resource_id = None
        else:
            # 关联课程/单元需要校验存在性
            if params.related_course_id:
                related_course = (await self.db.execute(
                    select(Course)
                    .where(Course.id == params.related_course_id)
                    .options(selectinload(Course.managers))
                )).scalars().first()
                if not related_course:
                    logger.error(f"[service.py] 关联课程不存在: {params.related_course_id}")
                    raise SystemException(f"关联课程不存在: {params.related_course_id}")
                db_resource.related_course_id = params.related_course_id
            if params.related_unit_id:
                related_unit = (await self.db.execute(
                    select(CourseUnit)
                    .where(CourseUnit.id == params.related_unit_id)
                    .options(joinedload(CourseUnit.course).selectinload(Course.managers))
                )).scalars().first()
                if not related_unit:
                    logger.error(f"[service.py] 关联单元不存在: {params.related_unit_id}")
                    raise SystemException(f"关联单元不存在: {params.related_unit_id}")
                db_resource.related_unit_id = params.related_unit_id

            # 改挂父资源（手动把游离教案/PPT 挂到某个大纲/教案版本下）。
            # 子资源课程归属与父资源强一致（覆盖本次请求传入的课程），避免
            # 「按课程过滤」与「按父资源下钻」两个视图互相矛盾。
            if params.parent_resource_id:
                parent = await self._get_parent_or_raise(
                    params.parent_resource_id,
                    ResourceTypeEnum(db_resource.resource_type),
                    current_user.id,
                )
                db_resource.parent_resource_id = parent.id
                db_resource.related_course_id = parent.related_course_id

        # 作用域变化时按目标作用域重算版本号（autoflush=False，查询看到的是改动前的库内数据）
        new_scope = (db_resource.related_course_id, db_resource.parent_resource_id)
        if new_scope != old_scope:
            db_resource.version_number = await self._next_version_number(
                ResourceTypeEnum(db_resource.resource_type),
                db_resource.creator_id,
                db_resource.related_course_id,
                db_resource.parent_resource_id,
            )

        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise BizException("版本号分配冲突，请重试")

    # ---------- 私有方法 ----------

    async def _add_with_version_retry(
        self,
        db_resource: Resource,
        resource_type: ResourceTypeEnum,
        creator_id: str,
    ) -> None:
        """提交新资源；版本号唯一索引冲突（并发 max+1 撞号）时重算版本号重试。"""
        for _ in range(3):
            self.db.add(db_resource)
            try:
                await self.db.commit()
                return
            except IntegrityError:
                await self.db.rollback()
                db_resource.version_number = await self._next_version_number(
                    resource_type,
                    creator_id,
                    db_resource.related_course_id,
                    db_resource.parent_resource_id,
                )
        logger.error(f"[service.py] 资源版本号分配重试失败: {db_resource.name}")
        raise SystemException("版本号分配冲突，请重试")

    async def _next_version_number(
        self,
        resource_type: ResourceTypeEnum,
        creator_id: str,
        related_course_id: str | None,
        parent_resource_id: str | None,
    ) -> int:
        """计算同作用域内的下一个版本号（max + 1）。

        作用域：有父资源时按父资源；否则按 (创建者, 课程, 类型) 的根级资源。
        """
        if parent_resource_id:
            scope = [
                Resource.parent_resource_id == parent_resource_id,
                Resource.resource_type == resource_type,
            ]
        else:
            scope = [
                Resource.creator_id == creator_id,
                Resource.related_course_id == related_course_id if related_course_id else Resource.related_course_id.is_(None),
                Resource.resource_type == resource_type,
                Resource.parent_resource_id.is_(None),
            ]
        max_version = (await self.db.execute(
            select(func.max(Resource.version_number)).where(*scope)
        )).scalar()
        return (max_version or 0) + 1

    async def _get_parent_or_raise(
        self,
        parent_resource_id: str,
        child_type: ResourceTypeEnum,
        user_id: str,
    ) -> Resource:
        """校验父资源存在、归属当前用户且类型符合层级链（大纲 → 教案 → PPT）。"""
        allowed_parents = RESOURCE_PARENT_TYPES.get(ResourceTypeEnum(child_type))
        if not allowed_parents:
            raise BizException(f"该类型资源不支持挂接父资源: {child_type}")
        parent = await self._get_resource_or_raise(parent_resource_id, user_id)
        if ResourceTypeEnum(parent.resource_type) not in allowed_parents:
            allowed_label = "/".join(t.value for t in allowed_parents)
            raise BizException(f"父资源类型不匹配：{child_type} 只能挂在 {allowed_label} 下")
        return parent

    async def _get_resource_or_raise(self, resource_id: str, user_id: str) -> Resource:
        """按 ID 查询资源（携带关联课程/单元），不存在或无权限时抛出 SystemException。"""
        db_resource = (await self.db.execute(
            select(Resource)
            .where(
                Resource.id == resource_id,
                Resource.creator_id == user_id,
            )
            .options(
                joinedload(Resource.related_course).joinedload(Course.managers),
                joinedload(Resource.related_unit),
            )
        )).unique().scalars().first()
        if not db_resource:
            logger.error(f"[service.py] 资源不存在或无权限: {resource_id}")
            raise SystemException(f"资源不存在或无权限: {resource_id}")
        return db_resource
