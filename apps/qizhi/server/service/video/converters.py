from pathlib import Path

from common.config import settings
from common.utils import format_datetime
from infra.db import Video
from service.video.models import VideoSummary, VideoDetail


def media_path_to_static_url(raw: str | None) -> str | None:
    """将库内存储的媒体路径规范为可经 /static 静态挂载访问的 URL。

    历史数据存在两种格式：
      - 智云导入：相对路径 ``uploads/videos/<id>.mp4``
      - 本地上传：绝对路径 ``/.../server/uploads/videos/<upload_id>/<id>.mp4``
        （/finish 经 ``_resolve_upload_dir().resolve()`` 落库为绝对路径）

    旧实现 ``raw.replace(settings.UPLOAD_DIR, "/static")`` 对绝对路径只替换中间的
    ``uploads`` 子串，残留前缀 ``/.../server//static/...``，导致封面与视频 404。

    这里按「路径组件」定位上传根目录，取其后的相对部分拼到 ``/static/`` 下，
    同时兼容绝对/相对两种历史数据，无需做数据迁移。
    """
    if not raw:
        return None
    s = str(raw).replace("\\", "/")
    if s.startswith(("http://", "https://", "/static/")):
        return s
    upload_name = Path(settings.UPLOAD_DIR).name or settings.UPLOAD_DIR.strip("/")
    parts = [p for p in s.split("/") if p]
    if upload_name in parts:
        rel = "/".join(parts[parts.index(upload_name) + 1:])
        return f"/static/{rel}"
    # 兜底：无法定位上传根时退回原值，避免误伤未知格式
    return s


def video_to_summary(video: Video | None) -> VideoSummary | None:
    if not video:
        return None
    return VideoSummary(
        id=video.id,
        name=video.name,
        status=video.status,
        cover=media_path_to_static_url(video.cover),
        analysis_start_time=format_datetime(video.analysis_start_time),
        related_course_id=video.related_course_id,
        related_resource_id=video.related_resource_id,
        create_time=format_datetime(video.create_time),
    )

def video_to_detail(video: Video | None) -> VideoDetail | None:
    if not video:
        return None
    return VideoDetail(
        id=video.id,
        name=video.name,
        path=media_path_to_static_url(video.path) or video.path,
        status=video.status,
        analysis_id=video.analysis_id,
        analysis_start_time=format_datetime(video.analysis_start_time),
        analysis_result=video.analysis_result,
        related_course_id=video.related_course_id,
        related_resource_id=video.related_resource_id,
        create_time=format_datetime(video.create_time),
    )
