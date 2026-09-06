from datetime import datetime
from zoneinfo import ZoneInfo

from common.models.constants import TIMEZONE_SHANGHAI


def format_datetime(dt: datetime | None) -> str | None:
    """将 UTC datetime 格式化为东八区可读字符串。"""
    if dt is None:
        return None
    return dt.astimezone(ZoneInfo(TIMEZONE_SHANGHAI)).strftime("%Y-%m-%d %H:%M:%S")
