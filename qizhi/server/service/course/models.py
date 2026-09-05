from typing import Annotated, Literal

from pydantic import BaseModel, Field

from service.user import UserDetail


class CourseDetail(BaseModel):
    """
    课程详情
    """
    id: str = Field(description="ID")
    name: str = Field(description="名称")
    lesson_count: int = Field(description="课时数")
    description: str = Field(description="描述")
    labels: list[str] = Field(description="标签")
    create_time: str = Field(description="创建时间")
    managers: list[UserDetail] = Field(description="管理员列表")
    extra_info: dict | None = Field(default=None, description="课程展示扩展信息")


class CourseCreateParams(BaseModel):
    """创建课程参数"""
    operation: Literal["create"] = Field(description="操作类型")
    name: str = Field(description="名称")
    manager_ids: list[str] = Field(description="管理员ID列表")
    lesson_count: int = Field(default=0, description="课时数")
    description: str = Field(default="无", description="描述")
    labels: list[str] = Field(default=[], description="标签")
    extra_info: dict | None = Field(default=None, description="课程展示扩展信息")


class CourseUpdateParams(BaseModel):
    """更新课程参数"""
    operation: Literal["update"] = Field(description="操作类型")
    id: str = Field(description="ID")
    name: str | None = Field(default=None, description="名称")
    lesson_count: int | None = Field(default=None, description="课时数")
    description: str | None = Field(default=None, description="描述")
    labels: list[str] | None = Field(default=None, description="标签")
    manager_ids: list[str] | None = Field(default=None, description="管理员ID列表")
    extra_info: dict | None = Field(default=None, description="课程展示扩展信息")


class CourseDeleteParams(BaseModel):
    """删除课程参数"""
    operation: Literal["delete"] = Field(description="操作类型")
    id: str = Field(description="ID")


CourseOperationParams = Annotated[
    CourseCreateParams | CourseUpdateParams | CourseDeleteParams,
    Field(discriminator="operation"),
]
