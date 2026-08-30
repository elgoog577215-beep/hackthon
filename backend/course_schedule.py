"""浙江大学课程节次与正式讲次的确定性投影。

教师选择的每一个课表格子都表示一个 45 分钟课时。相邻格子只表示一次
连续授课可能包含多个课时，系统不得据此假定“一讲固定两课时”。正式讲数
由教师确认；本模块只提供可解释的建议和旧字段兼容投影。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


COURSE_PERIOD_MINUTES = 45
WEEKDAY_LABELS = {
    1: "周一",
    2: "周二",
    3: "周三",
    4: "周四",
    5: "周五",
    6: "周六",
    7: "周日",
}


def normalize_schedule_slots(value: Any) -> list[dict[str, int]]:
    """Return unique, sorted weekday/period cells and ignore malformed legacy data."""
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, dict)):
        return []
    cells: set[tuple[int, int]] = set()
    for raw in value:
        if not isinstance(raw, dict):
            continue
        try:
            weekday = int(raw.get("weekday"))
            period = int(raw.get("period"))
        except (TypeError, ValueError):
            continue
        if 1 <= weekday <= 7 and 1 <= period <= 13:
            cells.add((weekday, period))
    return [
        {"weekday": weekday, "period": period}
        for weekday, period in sorted(cells)
    ]


def schedule_sessions(value: Any) -> list[dict[str, Any]]:
    """Group adjacent cells on the same weekday into one weekly teaching session."""
    by_weekday: dict[int, list[int]] = defaultdict(list)
    for cell in normalize_schedule_slots(value):
        by_weekday[cell["weekday"]].append(cell["period"])

    sessions: list[dict[str, Any]] = []
    for weekday in sorted(by_weekday):
        run: list[int] = []
        for period in by_weekday[weekday]:
            if run and period != run[-1] + 1:
                sessions.append(_session(weekday, run))
                run = []
            run.append(period)
        if run:
            sessions.append(_session(weekday, run))
    return sessions


def _session(weekday: int, periods: list[int]) -> dict[str, Any]:
    return {
        "weekday": weekday,
        "periods": list(periods),
        "period_count": len(periods),
        "duration_minutes": len(periods) * COURSE_PERIOD_MINUTES,
    }


def suggested_lecture_count(value: Any, active_week_start: int, active_week_end: int) -> int:
    weeks = max(0, int(active_week_end) - int(active_week_start) + 1)
    return len(schedule_sessions(value)) * weeks


def lecture_duration_minutes(value: Any, lecture_index: int) -> int:
    """Project the selected weekly session pattern onto a zero-based lecture index."""
    sessions = schedule_sessions(value)
    if not sessions:
        return COURSE_PERIOD_MINUTES
    session = sessions[max(0, int(lecture_index)) % len(sessions)]
    return int(session["duration_minutes"])


def legacy_schedule_labels(value: Any) -> tuple[str, str]:
    """Project structured cells into the historic weekday/period display fields."""
    sessions = schedule_sessions(value)
    weekdays: list[str] = []
    details: list[str] = []
    for session in sessions:
        weekday = WEEKDAY_LABELS[int(session["weekday"])]
        if weekday not in weekdays:
            weekdays.append(weekday)
        periods = session["periods"]
        period_label = (
            f"第{periods[0]}节"
            if len(periods) == 1
            else f"第{periods[0]}-{periods[-1]}节"
        )
        details.append(f"{weekday}{period_label}")
    return "、".join(weekdays), "；".join(details)
