"""Central ownership guard for unpublished teacher-course resources."""

from __future__ import annotations

from urllib.parse import unquote

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from learner_context import DEFAULT_USER_ID
from course_learning_access import CourseLearningAccess, learner_api_allowed, trusted_student, learner_request_course


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
    path: str = "",
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
    if is_published and learner_runtime_write_allowed(path):
        return None
    return {
        "code": "teacher_course_unavailable",
        "message": "课程不存在或不属于当前教师",
    }


def learner_runtime_write_allowed(path: str) -> bool:
    """Allow learner-owned state writes without opening teacher authoring APIs."""
    parts = [unquote(part) for part in str(path or "").split("/") if part]
    if len(parts) < 4 or parts[:2] != ["api", "courses"]:
        return False
    domain = parts[3]
    if domain in {
        "learning-progress",
        "learning-snapshot",
        "learner-model",
        "learning-runtime",
        "learning-continuation",
        "learning-records",
        "learning-assets",
        "practice",
        "review",
        "personal-adaptation",
    }:
        return True
    return domain == "blocks" and "personalization-proposals" in parts[4:]


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
        if trusted_student(request):
            if not learner_api_allowed(request.url.path, request.method):
                return JSONResponse(status_code=403, content={"detail": "学生不能访问教师生产接口"})
            # AI routes carry the course in a query/body rather than their path.
            if request.url.path.startswith("/api/ai-teacher/") or request.url.path == "/api/ask_events":
                course_id = request.query_params.get("course_id", "")
                if not course_id and request.method not in {"GET", "HEAD"}:
                    try:
                        body = await request.json()
                        course_id = str(body.get("course_id") or "")
                    except (ValueError, AttributeError):
                        pass
                if not course_id:
                    return JSONResponse(status_code=422, content={"detail": "course_id is required"})
            if course_id:
                course = self.course_storage.load_course(course_id)
                actor = request.headers.get("X-User-Id", "")
                from course_exchange import is_remote_course, read_remote_course, remote_course_context
                if not course and is_remote_course(course_id):
                    from fastapi import HTTPException
                    from fastapi.concurrency import run_in_threadpool
                    try:
                        remote = await run_in_threadpool(read_remote_course, self.course_storage, actor, course_id)
                    except HTTPException as exc:
                        return JSONResponse(status_code=exc.status_code, content={"detail":exc.detail})
                    if "/personal-adaptation" in request.url.path and request.method not in {"GET", "HEAD"}:
                        return JSONResponse(status_code=403, content={"detail":"学习授权不能修改教师课程正文"})
                    token = remote_course_context.set(remote)
                    try:
                        return await call_next(request)
                    finally:
                        remote_course_context.reset(token)
                if not course or (course.get("owner_id") != actor
                        and not CourseLearningAccess(self.course_storage).active(course, actor)):
                    return JSONResponse(status_code=404, content={"detail": "课程不存在或授权已撤销"})
                if (course.get("owner_id") != actor
                        and "/personal-adaptation" in request.url.path
                        and request.method not in {"GET", "HEAD"}
                        and not request.url.path.endswith(("/evaluate", "/reject"))):
                    return JSONResponse(status_code=403, content={"detail": "学习授权不能修改教师课程正文"})
                token = learner_request_course.set(course_id)
                try:
                    return await call_next(request)
                finally:
                    learner_request_course.reset(token)
        if course_id:
            course = self.course_storage.load_course(course_id)
            denial = teacher_course_access_denial(
                course,
                request.headers.get("X-User-Id"),
                method=request.method,
                path=request.url.path,
            )
            if denial:
                return JSONResponse(status_code=404, content={"detail": denial})
        return await call_next(request)


__all__ = [
    "CourseOwnershipMiddleware",
    "course_id_from_api_path",
    "learner_runtime_write_allowed",
    "teacher_course_access_denial",
]
