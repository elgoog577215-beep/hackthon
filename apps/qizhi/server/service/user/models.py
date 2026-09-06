from typing import Annotated, Literal

from pydantic import BaseModel, Field

from common.models.constants import UserRole


class UserDetail(BaseModel):
    """
    用户详情
    """
    id: str = Field(description="ID")
    zju_id: str = Field(description="浙大ID")
    name: str = Field(description="名称")
    department: str = Field(description="院系")
    phone: str | None = Field(description="电话")
    email: str | None = Field(description="邮箱")
    role: str = Field(default=UserRole.STUDENT.value, description="角色")
    create_time: str = Field(description="创建时间")


class UserUpdateParams(BaseModel):
    """更新当前用户资料参数"""
    operation: Literal["update"] = Field(description="操作类型")
    phone: str | None = Field(default=None, description="电话")
    email: str | None = Field(default=None, description="邮箱")


class UserDeleteParams(BaseModel):
    """注销当前用户参数"""
    operation: Literal["delete"] = Field(description="操作类型")


UserOperationParams = Annotated[
    UserUpdateParams | UserDeleteParams,
    Field(discriminator="operation"),
]
