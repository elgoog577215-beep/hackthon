from course_schedule import (
    COURSE_PERIOD_MINUTES,
    canonical_zju_term,
    inferred_sessions_per_week,
    lecture_duration_minutes,
    normalize_schedule_slots,
    projected_lecture_week,
    resolve_active_week_range,
    schedule_sessions,
    suggested_lecture_count,
    zju_teaching_week_range,
)


def test_zju_schedule_keeps_every_selected_45_minute_cell():
    slots = normalize_schedule_slots([
        {"weekday": 2, "period": 3},
        {"weekday": 2, "period": 4},
        {"weekday": 2, "period": 5},
        {"weekday": 4, "period": 7},
        {"weekday": 4, "period": 7},
    ])

    assert COURSE_PERIOD_MINUTES == 45
    assert slots == [
        {"weekday": 2, "period": 3},
        {"weekday": 2, "period": 4},
        {"weekday": 2, "period": 5},
        {"weekday": 4, "period": 7},
    ]
    assert schedule_sessions(slots) == [
        {
            "weekday": 2,
            "periods": [3, 4, 5],
            "period_count": 3,
            "duration_minutes": 135,
        },
        {
            "weekday": 4,
            "periods": [7],
            "period_count": 1,
            "duration_minutes": 45,
        },
    ]


def test_schedule_only_suggests_lecture_count_and_preserves_variable_duration():
    slots = [
        {"weekday": 2, "period": 3},
        {"weekday": 2, "period": 4},
        {"weekday": 2, "period": 5},
        {"weekday": 4, "period": 7},
    ]

    assert suggested_lecture_count(slots, 1, 16) == 32
    assert lecture_duration_minutes(slots, 0) == 135
    assert lecture_duration_minutes(slots, 1) == 45
    assert lecture_duration_minutes(slots, 2) == 135


def test_zju_terms_resolve_to_eight_or_sixteen_teaching_weeks():
    assert canonical_zju_term("2026-2027 春夏学期") == "春夏"
    assert canonical_zju_term("2026-2027 秋季学期") == "秋"
    assert zju_teaching_week_range("春夏") == (1, 16)
    assert zju_teaching_week_range("秋冬") == (1, 16)
    assert zju_teaching_week_range("春学期") == (1, 8)
    assert zju_teaching_week_range("夏") == (1, 8)
    assert zju_teaching_week_range("暑期课") is None


def test_academic_calendar_is_default_but_custom_range_remains_available():
    assert resolve_active_week_range("秋", "academic_calendar", 3, 12) == (
        1,
        8,
        "academic_calendar",
    )
    assert resolve_active_week_range("秋", "custom", 2, 7) == (2, 7, "custom")
    assert resolve_active_week_range("秋", None, 1, 16) == (
        1,
        8,
        "academic_calendar",
    )
    assert resolve_active_week_range("秋", None, 2, 7) == (2, 7, "custom")
    assert resolve_active_week_range("暑期课", "academic_calendar", 2, 4) == (
        2,
        4,
        "custom",
    )


def test_sixteen_lectures_fill_an_eight_week_term_twice_per_week():
    density = inferred_sessions_per_week(16, 1, 8)
    weeks = [
        projected_lecture_week(
            index,
            active_week_start=1,
            active_week_end=8,
            sessions_per_week=density,
        )
        for index in range(16)
    ]

    assert density == 2
    assert weeks == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8]
