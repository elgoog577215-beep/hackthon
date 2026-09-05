from __future__ import annotations

from typing import TypeVar, Generic
from pydantic import BaseModel


T = TypeVar("T")

class ApiResponse(BaseModel, Generic[T]):
    """
    API 响应模型
    """
    success: bool = True
    data: T | None = None
    error: str | None = None

    @classmethod
    def success_response(cls, data: T | None = None) -> ApiResponse[T]:
        """成功响应"""
        return cls(success = True, data = data)

    @classmethod
    def error_response(cls, error: str) -> ApiResponse:
        """失败响应"""
        return cls(success = False, error = error)
