import pytest

from routers import courses
from storage import Storage
from teaching_calendar import TeachingCalendarRepository


@pytest.mark.asyncio
async def test_course_summary_projects_teacher_identity_metadata(tmp_path):
    test_storage = Storage(str(tmp_path / "data"))
    await test_storage.save_course("course-1", {
        "course_id": "course-1",
        "course_name": "矩阵与线性变换",
        "academic_year": "2026-2027",
        "term": "秋季",
        "course_profile": {"course_code": "MATH-221"},
        "course_document": {"sections": [{"section_id": "L1", "level": 2}]},
    })

    summary = test_storage.list_courses()[0]

    assert summary["academic_year"] == "2026-2027"
    assert summary["term"] == "秋季"
    assert summary["course_code"] == "MATH-221"


def test_calendar_session_projection_keeps_term_metadata(tmp_path):
    repository = TeachingCalendarRepository(tmp_path / "teaching-calendars")
    repository.save("teacher-a", "course-1", {
        "course_title": "矩阵与线性变换",
        "academic_year": "2026-2027",
        "term": "秋季",
        "status": "ready",
        "sessions": [{
            "session_id": "session-7",
            "sequence": 7,
            "date": "2099-08-25",
            "start_time": "14:00",
            "end_time": "15:35",
            "content_summary": "特征向量",
            "requirements": "",
            "location": "理科楼 A108",
            "teacher_name": "",
            "teaching_type": "理论课",
            "group_code": "",
            "notes": "",
            "status": "scheduled",
            "source": "manual",
        }],
    }, base_revision=0)

    session = repository.list_sessions("teacher-a")[0]

    assert session["academic_year"] == "2026-2027"
    assert session["term"] == "秋季"


def test_teacher_list_attaches_next_session_without_replacing_course_truth(monkeypatch):
    monkeypatch.setattr(courses.storage, "list_courses", lambda: [{
        "course_id": "course-1",
        "course_name": "矩阵与线性变换",
        "node_count": 12,
        "is_published": True,
        "academic_year": "",
        "term": "",
        "course_code": "MATH-221",
    }])
    next_session = {
        "session_id": "session-7",
        "sequence": 7,
        "date": "2026-08-25",
        "start_time": "14:00:00",
        "content_summary": "特征向量",
        "academic_year": "2026-2027",
        "term": "秋季",
    }

    projected = courses._list_teacher_courses(set(), {"course-1": next_session})[0]

    assert projected["node_count"] == 12
    assert projected["course_code"] == "MATH-221"
    assert projected["academic_year"] == "2026-2027"
    assert projected["term"] == "秋季"
    assert projected["next_session"] == next_session
