"""智云课堂视频导入的「取消标记」——以文件系统为准，跨进程/worker 生效。

为什么用文件系统而不是进程内集合：导入是一条长连接 SSE，整个生命周期固定在
某个 worker 上；而「取消」是另一个独立的 HTTP 请求，多 worker 部署时可能落到
别的 worker。把取消信号写到共享卷上的标记文件，正在跑导入的那个 worker 就一定
能读到（与分片上传「状态以文件系统为准」同理）。

注意：仅靠客户端断开 SSE 连接来取消并不可靠——反向代理常会缓冲上游连接，后端
直到下载结束、视频已落库才察觉断开，于是「取消后视频仍出现在列表里」。显式的
取消标记是带外信号，不依赖 TCP 断开，因此可靠。
"""

import re
from pathlib import Path

from common.config import settings
from common.utils.logger import get_logger

logger = get_logger(__name__)

# import_id 仅允许数字/字母/下划线/连字符，过滤非法值并防止路径穿越
_IMPORT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def is_valid_import_id(import_id: str | None) -> bool:
    return bool(import_id) and bool(_IMPORT_ID_RE.match(import_id or ""))


def _cancel_dir() -> Path:
    return Path(settings.UPLOAD_DIR) / "videos" / "import_cancel"


def _flag_path(import_id: str | None) -> Path | None:
    if not is_valid_import_id(import_id):
        return None
    return _cancel_dir() / f"{import_id}.cancel"


def request_cancel(import_id: str) -> bool:
    """登记一次取消请求（写标记文件）。返回是否成功登记。"""
    path = _flag_path(import_id)
    if path is None:
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("1", encoding="utf-8")
        return True
    except OSError as e:
        logger.warning(f"[import_cancel] 写取消标记失败: import_id={import_id}, err={e}")
        return False


def is_cancelled(import_id: str | None) -> bool:
    """导入循环里轮询：该导入是否已被请求取消。"""
    path = _flag_path(import_id)
    return path is not None and path.exists()


def clear_cancel(import_id: str | None) -> None:
    """清理标记文件（导入结束时调用，避免残留）。"""
    path = _flag_path(import_id)
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as e:
        logger.warning(f"[import_cancel] 清理取消标记失败: import_id={import_id}, err={e}")
