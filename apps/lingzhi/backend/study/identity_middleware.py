"""Apply authenticated local learner identity to the shared learning APIs."""

from __future__ import annotations

import os
from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from course_learning_access import learner_api_allowed
from qizhi_auth import _replace_header
from study.auth import LocalStudyAuth


class LocalStudyIdentityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, course_storage):
        super().__init__(app)
        self.storage = course_storage

    async def dispatch(self, request, call_next):
        from course_exchange import INTERNAL_PREFIX

        if request.url.path.startswith(INTERNAL_PREFIX):
            return await call_next(request)
        if (
            not request.url.path.startswith("/api/")
            or request.method == "OPTIONS"
            or os.getenv("QIZHI_AUTH_VERIFY_URL", "").strip()
        ):
            return await call_next(request)
        auth = LocalStudyAuth(self.storage)
        authorization = request.headers.get("Authorization", "")
        claimed_student = request.headers.get("X-User-Id", "").startswith("local-student:")
        if not authorization and not claimed_student:
            return await call_next(request)
        try:
            identity = auth.resolve(authorization)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        if not learner_api_allowed(request.url.path, request.method):
            return JSONResponse(status_code=403, content={"detail": "学生不能访问教师生产接口"})
        _replace_header(request, "X-User-Id", identity["id"])
        request.state.local_study_identity = identity
        return await call_next(request)
