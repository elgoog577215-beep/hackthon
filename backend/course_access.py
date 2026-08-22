"""Central ownership guard for unpublished teacher-course resources."""

from __future__ import annotations

from urllib.parse import unquote

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from learner_context import DEFAULT_USER_ID


def course_id_from_api_path(path: str) -> str:
    """Return the course id embedded in a course-scoped API path."""
    parts = [unquote(part) for part in str(path or "").split("/") if part]
    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "courses":
        return parts[2]
    if (
        len(parts) >= 4
        and parts[0] == "api"
        and parts[1] == "teacher"
        and parts[2] == "courses"
    ):
        return parts[3]
    return ""


def teacher_course_access_denial(
    course: dict | None,
    actor_id: str | None,
    *,
    method: str = "GET",
) -> dict | None:
    """Return a non-leaking 404 for foreign private reads or any foreign write."""
    if not course or course.get("authoring_surface") != "teacher":
        return None
    owner_id = str(course.get("owner_id") or "").strip()
    if not owner_id:
        return None
    normalized_actor = str(actor_id or "").strip()
    if normalized_actor and normalized_actor != DEFAULT_USER_ID and normalized_actor == owner_id:
        return None
    is_published = bool(
        course.get("is_published") or course.get("course_document_publication")
    )
    if is_published and str(method or "GET").upper() in {"GET", "HEAD"}:
        return None
    return {
        "code": "teacher_course_unavailable",
        "message": "课程不存在或不属于当前教师",
    }


class CourseOwnershipMiddleware(BaseHTTPMiddleware):
    """Apply the same private-course boundary to every course sub-router."""

    def __init__(self, app, *, course_storage):
        super().__init__(app)
        self.course_storage = course_storage

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)
        course_id = course_id_from_api_path(request.url.path)
        if course_id:
            course = self.course_storage.load_course(course_id)
            denial = teacher_course_access_denial(
                course,
                request.headers.get("X-User-Id"),
                method=request.method,
            )
            if denial:
                return JSONResponse(status_code=404, content={"detail": denial})
        return await call_next(request)


__all__ = [
    "CourseOwnershipMiddleware",
    "course_id_from_api_path",
    "teacher_course_access_denial",
]
