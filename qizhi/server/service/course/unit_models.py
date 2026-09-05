from typing import Annotated, Literal

from pydantic import BaseModel, Field


class CourseUnitDetail(BaseModel):
    """
    单元详情
    """
    id: str
    name: str
    description: str
    level: int
    create_time: str


class UnitNode(BaseModel):
    """
    单元节点
    """
    detail: CourseUnitDetail
    children: list[UnitNode]


class UnitCreateParams(BaseModel):
    """创建单元参数"""
    operation: Literal["create"]
    name: str
    course_id: str
    parent_unit_id: str | None = None
    previous_unit_id: str | None = None
    description: str = "无"


class UnitUpdateParams(BaseModel):
    """更新单元参数"""
    operation: Literal["update"]
    id: str
    name: str | None = None
    description: str | None = None


class UnitDeleteParams(BaseModel):
    """删除单元参数"""
    operation: Literal["delete"]
    id: str


class UnitReorderParams(BaseModel):
    """调整同层级单元顺序参数"""
    operation: Literal["reorder"]
    id: str
    previous_unit_id: str | None = None


UnitOperationParams = Annotated[
    UnitCreateParams | UnitUpdateParams | UnitDeleteParams | UnitReorderParams,
    Field(discriminator="operation"),
]
