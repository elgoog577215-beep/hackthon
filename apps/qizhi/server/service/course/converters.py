from common.utils import format_datetime
from infra.db import Course, CourseUnit
from service.course.models import CourseDetail
from service.course.unit_models import CourseUnitDetail
from service.user import user_to_detail


def course_to_detail(course: Course | None) -> CourseDetail | None:
    if not course:
        return None
    return CourseDetail(
        id=course.id,
        name=course.name,
        lesson_count=course.lesson_count,
        description=course.description,
        labels=course.labels,
        create_time=format_datetime(course.create_time),
        managers=[user_to_detail(user) for user in course.managers],
        extra_info=course.extra_info,
    )

def unit_to_detail(unit: CourseUnit | None) -> CourseUnitDetail | None:
    if not unit:
        return None
    return CourseUnitDetail(
        id=unit.id,
        name=unit.name,
        description=unit.description,
        level=unit.level,
        create_time=format_datetime(unit.create_time),
    )
