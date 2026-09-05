from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from service.course import CourseDetail, CourseUnitDetail


class ResourceTypeEnum(str, Enum):
    """
    资源类型枚举
    """
    OUTLINE = "outline" # 教学大纲
    TEACHING_PLAN = "teaching_plan" # 教案
    PPT = "ppt" # PPT
    QUESTION_BANK = "question_bank" # 习题集


class ResourceSummary(BaseModel):
    """
    资源概要
    """
    id: str = Field(description="ID")
    name: str = Field(description="名称")
    resource_type: ResourceTypeEnum = Field(description="资源类型")
    word_count: int = Field(description="字数")
    editable: bool = Field(description="是否可编辑")
    version_number: int = Field(default=1, description="版本号")
    parent_resource_id: str | None = Field(default=None, description="父资源 ID")
    child_count: int = Field(default=0, description="子资源（下级版本）数量")
    related_course: CourseDetail | None = Field(description="关联课程")
    related_unit: CourseUnitDetail | None = Field(description="关联单元")
    create_time: str = Field(description="创建时间")
    update_time: str = Field(description="更新时间")


class ResourceDetail(BaseModel):
    """
    资源详情
    """
    id: str = Field(description="ID")
    name: str = Field(description="名称")
    path: str | None = Field(description="路径")
    resource_type: ResourceTypeEnum = Field(description="资源类型")
    content: str | None = Field(description="内容")
    word_count: int = Field(description="字数")
    ppt_html_url: str | None = Field(default=None, description="PPT 在线预览(html)地址")
    ppt_pptx_url: str | None = Field(default=None, description="PPT 下载(pptx)地址")
    editable: bool = Field(description="是否可编辑")
    version_number: int = Field(default=1, description="版本号")
    parent_resource_id: str | None = Field(default=None, description="父资源 ID")
    parent_resource_name: str | None = Field(default=None, description="父资源名称")
    related_course: CourseDetail | None = Field(description="关联课程")
    related_unit: CourseUnitDetail | None = Field(description="关联单元")
    create_time: str = Field(description="创建时间")
    update_time: str = Field(description="更新时间")


class ResourceCreateParams(BaseModel):
    """
    创建资源参数
    """
    operation: Literal["create"] = Field(description="操作类型")
    name: str = Field(description="名称")
    resource_type: ResourceTypeEnum = Field(description="资源类型")
    editable: bool = Field(description="是否可编辑")
    path: str | None = Field(default=None, description="路径")
    related_course_id: str | None = Field(default=None, description="关联课程ID")
    related_unit_id: str | None = Field(default=None, description="关联单元ID")
    parent_resource_id: str | None = Field(default=None, description="父资源ID（教案挂大纲版本，PPT 挂教案版本）")


class ResourceUpdateParams(BaseModel):
    """
    更新资源参数
    """
    operation: Literal["update"] = Field(description="操作类型")
    id: str = Field(description="ID")
    name: str | None = Field(default=None, description="名称")
    content: str | None = Field(default=None, description="内容")


class ResourceDeleteParams(BaseModel):
    """
    删除资源参数
    """
    operation: Literal["delete"] = Field(description="操作类型")
    id: str = Field(description="ID")


class ResourceCopyParams(BaseModel):
    """
    复制资源参数
    """
    operation: Literal["copy"] = Field(description="操作类型")
    id: str = Field(description="ID")
    name: str = Field(description="名称")


ResourceOperationParams = Annotated[
    ResourceCreateParams | ResourceUpdateParams | ResourceDeleteParams | ResourceCopyParams,
    Field(discriminator="operation"),
]


# 资源层级链：子类型 → 允许的父类型集合（课程 → 大纲版本 → 教案版本 → PPT 版本；习题集可挂大纲或教案）
RESOURCE_PARENT_TYPES: dict[ResourceTypeEnum, set[ResourceTypeEnum]] = {
    ResourceTypeEnum.TEACHING_PLAN: {ResourceTypeEnum.OUTLINE},
    ResourceTypeEnum.PPT: {ResourceTypeEnum.TEACHING_PLAN},
    ResourceTypeEnum.QUESTION_BANK: {ResourceTypeEnum.OUTLINE, ResourceTypeEnum.TEACHING_PLAN},
}


class ResourceBindingParams(BaseModel):
    """
    资源绑定参数
    """
    id: str = Field(description="ID")
    related_course_id: str | None = Field(default=None, description="关联课程ID")
    related_unit_id: str | None = Field(default=None, description="关联单元ID")
    parent_resource_id: str | None = Field(default=None, description="父资源ID（手动挂接游离资源）")
    unbind: bool = Field(default=False, description="是否解绑")
