from course_schedule import (
    COURSE_PERIOD_MINUTES,
    lecture_duration_minutes,
    normalize_schedule_slots,
    schedule_sessions,
    suggested_lecture_count,
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
