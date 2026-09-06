"""
统一API响应格式

所有API端点应该使用这个模块中的工具函数来格式化响应，
确保前端可以依赖一致的响应结构。

响应格式:
{
    "status": "success" | "error",
    "data": {...} | null,
    "message": "可选的消息",
    "error": {"code": "ERROR_CODE", "details": "..."} | null
}
"""

from typing import Any, Optional, Dict, List, Union
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ErrorCode(str, Enum):
    """错误代码枚举"""
    # 通用错误
    INTERNAL_ERROR = "INTERNAL_ERROR"
    INVALID_REQUEST = "INVALID_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    
    # 课程相关
    COURSE_NOT_FOUND = "COURSE_NOT_FOUND"
    NODE_NOT_FOUND = "NODE_NOT_FOUND"
    INVALID_COURSE_ID = "INVALID_COURSE_ID"
    
    # AI相关
    AI_SERVICE_ERROR = "AI_SERVICE_ERROR"
    AI_TIMEOUT = "AI_TIMEOUT"
    AI_RATE_LIMITED = "AI_RATE_LIMITED"
    
    # 文件相关
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_PARSE_ERROR = "FILE_PARSE_ERROR"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    
    # 验证相关
    VALIDATION_ERROR = "VALIDATION_ERROR"
    MISSING_PARAMETER = "MISSING_PARAMETER"
    INVALID_PARAMETER = "INVALID_PARAMETER"


@dataclass
class APIResponse:
    """统一API响应结构"""
    status: str
    data: Optional[Any] = None
    message: Optional[str] = None
    error: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {"status": self.status}
        if self.data is not None:
            result["data"] = self.data
        if self.message:
            result["message"] = self.message
        if self.error:
            result["error"] = self.error
        return result


def success_response(
    data: Any = None,
    message: Optional[str] = None
) -> Dict[str, Any]:
    """
    创建成功响应
    
    Args:
        data: 响应数据
        message: 可选的成功消息
        
    Returns:
        标准化的成功响应字典
    """
    return APIResponse(
        status="success",
        data=data,
        message=message
    ).to_dict()


def error_response(
    code: Union[ErrorCode, str],
    message: str,
    details: Optional[Any] = None,
    status_code: int = 400
) -> Dict[str, Any]:
    """
    创建错误响应
    
    Args:
        code: 错误代码
        message: 错误消息
        details: 错误详情
        status_code: HTTP状态码
        
    Returns:
        标准化的错误响应字典
    """
    error_code = code.value if isinstance(code, ErrorCode) else code
    
    logger.error(f"API Error: {error_code} - {message}", extra={"details": details})
    
    return APIResponse(
        status="error",
        message=message,
        error={
            "code": error_code,
            "details": details
        }
    ).to_dict()


def paginated_response(
    items: List[Any],
    total: int,
    page: int = 1,
    page_size: int = 20,
    message: Optional[str] = None
) -> Dict[str, Any]:
    """
    创建分页响应
    
    Args:
        items: 当前页数据
        total: 总数量
        page: 当前页码
        page_size: 每页数量
        message: 可选消息
        
    Returns:
        标准化的分页响应
    """
    total_pages = (total + page_size - 1) // page_size
    
    return success_response(
        data={
            "items": items,
            "pagination": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            }
        },
        message=message
    )


def created_response(
    data: Any = None,
    message: str = "资源创建成功"
) -> Dict[str, Any]:
    """创建资源创建成功响应"""
    return success_response(data=data, message=message)


def updated_response(
    data: Any = None,
    message: str = "资源更新成功"
) -> Dict[str, Any]:
    """创建资源更新成功响应"""
    return success_response(data=data, message=message)


def deleted_response(
    message: str = "资源删除成功"
) -> Dict[str, Any]:
    """创建资源删除成功响应"""
    return success_response(data=None, message=message)


def not_found_response(
    resource: str = "资源",
    resource_id: Optional[str] = None
) -> Dict[str, Any]:
    """创建404未找到响应"""
    message = f"{resource}未找到"
    if resource_id:
        message = f"{resource} (ID: {resource_id}) 未找到"
    
    return error_response(
        code=ErrorCode.NOT_FOUND,
        message=message,
        status_code=404
    )


def validation_error_response(
    errors: Dict[str, List[str]]
) -> Dict[str, Any]:
    """
    创建验证错误响应
    
    Args:
        errors: 字段名到错误消息列表的映射
        例如: {"name": ["名称不能为空"], "email": ["邮箱格式不正确"]}
        
    Returns:
        标准化的验证错误响应
    """
    return error_response(
        code=ErrorCode.VALIDATION_ERROR,
        message="数据验证失败",
        details=errors
    )


def handle_exception(
    exc: Exception,
    default_message: str = "服务器内部错误"
) -> Dict[str, Any]:
    """
    统一处理异常，返回标准化的错误响应
    
    Args:
        exc: 捕获的异常
        default_message: 默认错误消息
        
    Returns:
        标准化的错误响应
    """
    # 根据异常类型返回不同的错误码和消息
    if isinstance(exc, FileNotFoundError):
        return error_response(
            code=ErrorCode.FILE_NOT_FOUND,
            message=str(exc) or "文件未找到",
            status_code=404
        )
    
    if isinstance(exc, ValueError):
        return error_response(
            code=ErrorCode.INVALID_PARAMETER,
            message=str(exc),
            status_code=400
        )
    
    if isinstance(exc, TimeoutError):
        return error_response(
            code=ErrorCode.AI_TIMEOUT,
            message="请求超时，请稍后重试",
            status_code=504
        )
    
    # 未知异常，记录详细日志但返回通用消息
    logger.exception(f"Unhandled exception: {exc}")
    
    return error_response(
        code=ErrorCode.INTERNAL_ERROR,
        message=default_message,
        details=str(exc) if logger.isEnabledFor(logging.DEBUG) else None,
        status_code=500
    )
