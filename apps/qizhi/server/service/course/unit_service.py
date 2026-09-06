from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from common.models import SystemException
from infra.db import Course, CourseUnit, User
from service.course.converters import unit_to_detail
from service.course.unit_models import (
    UnitCreateParams,
    UnitDeleteParams,
    UnitNode,
    UnitReorderParams,
    UnitUpdateParams,
)
from common.utils.logger import get_logger

logger = get_logger(__name__)


class UnitService:
    """
    单元服务
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------- 公共方法 ----------

    async def list_units(self, course_id: str, current_user: User) -> list[UnitNode]:
        """查询课程的单元树结构"""
        await self._get_course_or_raise(course_id, current_user.id)
        return await self._build_children_tree(course_id, None)

    async def create_unit(self, params: UnitCreateParams, current_user: User) -> str:
        """创建单元"""
        await self._get_course_or_raise(params.course_id, current_user.id)

        # 层级默认为1, 如果存在父单元, 则层级为父单元层级加1
        level = 1
        if params.parent_unit_id:
            db_parent_unit = (await self.db.execute(
                select(CourseUnit)
                .where(
                    CourseUnit.id == params.parent_unit_id,
                    CourseUnit.course_id == params.course_id,
                )
            )).scalars().first()
            if not db_parent_unit:
                logger.error(f"[unit_service.py] 父单元不存在: {params.parent_unit_id}")
                raise SystemException(f"父单元不存在: {params.parent_unit_id}")
            level = db_parent_unit.level + 1

        # 模拟链表插入，获取下一节点的ID
        next_unit_id = None
        if params.previous_unit_id:  # 链表中间
            db_previous_unit = (await self.db.execute(
                select(CourseUnit)
                .where(
                    CourseUnit.id == params.previous_unit_id,
                    CourseUnit.course_id == params.course_id,
                )
            )).scalars().first()
            if not db_previous_unit:
                logger.error(f"[unit_service.py] 上一个单元不存在: {params.previous_unit_id}")
                raise SystemException(f"上一个单元不存在: {params.previous_unit_id}")
            next_unit_id = db_previous_unit.next_unit_id
        else:  # 链表头部
            db_first_unit = await self._get_first_unit(params.course_id, params.parent_unit_id)
            if db_first_unit:
                next_unit_id = db_first_unit.id

        db_unit = CourseUnit(
            name=params.name,
            description=params.description,
            course_id=params.course_id,
            parent_unit_id=params.parent_unit_id,
            next_unit_id=next_unit_id,
            level=level,
        )
        self.db.add(db_unit)
        await self.db.flush()

        # 更新链表关系，修改前一节点的指针
        if params.previous_unit_id:
            db_previous_unit.next_unit_id = db_unit.id

        await self.db.commit()
        return db_unit.id

    async def update_unit(self, params: UnitUpdateParams, current_user: User) -> None:
        """更新单元"""
        db_unit = await self._get_unit_or_raise(params.id, current_user.id)

        if params.name is not None:
            db_unit.name = params.name
        if params.description is not None:
            db_unit.description = params.description
        await self.db.commit()

    async def reorder_unit(self, params: UnitReorderParams, current_user: User) -> None:
        """调整同层级单元顺序（基于 next_unit_id 链表）"""
        db_unit = await self._get_unit_or_raise(params.id, current_user.id)
        course_id = db_unit.course_id
        parent_unit_id = db_unit.parent_unit_id

        siblings = (await self.db.execute(
            select(CourseUnit)
            .where(
                CourseUnit.course_id == course_id,
                CourseUnit.parent_unit_id == parent_unit_id,
            )
        )).scalars().all()

        if params.previous_unit_id:
            if params.previous_unit_id == params.id:
                return
            db_previous = next((s for s in siblings if s.id == params.previous_unit_id), None)
            if not db_previous:
                logger.error(f"[unit_service.py] 前一单元不存在或非同级: {params.previous_unit_id}")
                raise SystemException(f"前一单元不存在或非同级: {params.previous_unit_id}")
            if db_previous.next_unit_id == db_unit.id:
                return

        # 从当前位置摘除
        for sibling in siblings:
            if sibling.next_unit_id == db_unit.id:
                sibling.next_unit_id = db_unit.next_unit_id
                break

        # 插入到新位置
        if params.previous_unit_id:
            db_previous = next(s for s in siblings if s.id == params.previous_unit_id)
            db_unit.next_unit_id = db_previous.next_unit_id
            db_previous.next_unit_id = db_unit.id
        else:
            db_head = await self._get_first_unit(course_id, parent_unit_id)
            if db_head and db_head.id != db_unit.id:
                db_unit.next_unit_id = db_head.id
            elif db_head and db_head.id == db_unit.id:
                pass
            else:
                db_unit.next_unit_id = None

        await self.db.commit()

    async def delete_unit(self, params: UnitDeleteParams, current_user: User) -> None:
        """删除单元"""
        db_unit = await self._get_unit_or_raise(params.id, current_user.id)

        # 删除单元子单元
        unit_children = await self.db.execute(select(CourseUnit).where(CourseUnit.parent_unit_id == params.id))
        child_unit_ids = [unit.id for unit in unit_children.scalars().all()]
        if child_unit_ids:
            await self.db.execute(delete(CourseUnit).where(CourseUnit.id.in_(child_unit_ids)))

        # 更新链表关系，修改前一节点的指针
        units_list = (await self.db.execute(
            select(CourseUnit)
            .where(
                CourseUnit.course_id == db_unit.course_id,
                CourseUnit.parent_unit_id == db_unit.parent_unit_id,
            )
        )).scalars().all()
        for unit in units_list:
            if unit.next_unit_id == db_unit.id:
                unit.next_unit_id = db_unit.next_unit_id

        await self.db.delete(db_unit)
        await self.db.commit()

    # ---------- 私有方法 ----------

    async def _get_course_or_raise(self, course_id: str, user_id: str) -> Course:
        """按 ID 查询课程，不存在或无权限时抛出 SystemException。"""
        db_course = (await self.db.execute(
            select(Course)
            .where(
                Course.id == course_id,
                Course.managers.any(User.id == user_id),
            )
            .options(joinedload(Course.managers))
        )).scalars().first()
        if not db_course:
            logger.error(f"[unit_service.py] 课程不存在或无权限: {course_id}")
            raise SystemException(f"课程不存在或无权限: {course_id}")
        return db_course

    async def _get_unit_or_raise(self, unit_id: str, user_id: str) -> CourseUnit:
        """按 ID 查询单元，不存在或无权限时抛出 SystemException。"""
        db_unit = (await self.db.execute(
            select(CourseUnit)
            .where(
                CourseUnit.id == unit_id,
                CourseUnit.course.has(Course.managers.any(User.id == user_id)),
            )
        )).scalars().first()
        if not db_unit:
            logger.error(f"[unit_service.py] 单元不存在或无权限: {unit_id}")
            raise SystemException(f"单元不存在或无权限: {unit_id}")
        return db_unit

    async def _get_first_unit(self, course_id: str, parent_unit_id: str | None) -> CourseUnit | None:
        """获取第一个单元的数据库对象"""
        # 查询当前层级的所有单元
        units_list = (await self.db.execute(
            select(CourseUnit)
            .where(
                CourseUnit.course_id == course_id,
                CourseUnit.parent_unit_id == parent_unit_id,
            )
        )).scalars().all()

        # 列出所有节点的指针，找到没有被指针指向的节点，即为头节点
        next_of_unit = {u.next_unit_id for u in units_list if u.next_unit_id}
        for unit in units_list:
            if unit.id not in next_of_unit:
                return unit
        return None

    async def _build_children_tree(self, course_id: str, parent_unit_id: str | None) -> list[UnitNode]:
        """构建子单元的树结构"""
        # 查询当前层级的所有节点
        units_list = (await self.db.execute(
            select(CourseUnit)
            .where(
                CourseUnit.course_id == course_id,
                CourseUnit.parent_unit_id == parent_unit_id,
            )
        )).scalars().all()

        # 找到当前层级链表的头节点
        head = None
        # 列出当前层级所有节点的指针，找到没有被指针指向的节点，即为头节点
        next_of_unit = {u.next_unit_id for u in units_list if u.next_unit_id}
        for unit in units_list:
            if unit.id not in next_of_unit:
                head = unit
                break

        # 构建单元ID到单元对象的映射
        unit_map = {u.id: u for u in units_list}
        # 构建有序的单元列表（安全遍历，防止脏数据导致的 KeyError）
        ordered_units: list[CourseUnit] = []
        cur = head
        visited = set()
        while cur and cur.id not in visited:
            ordered_units.append(cur)
            visited.add(cur.id)
            nxt_id = cur.next_unit_id
            if nxt_id and nxt_id in unit_map:
                cur = unit_map[nxt_id]
            else:
                cur = None

        # 递归构建子单元的树结构
        return [
            UnitNode(
                detail = unit_to_detail(unit),
                children = await self._build_children_tree(course_id, unit.id)
            ) for unit in ordered_units
        ]
