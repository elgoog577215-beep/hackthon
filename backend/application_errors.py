"""Cross-application HTTP error traceability without exposing sensitive internals."""

from __future__ import annotations

import logging
import re
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


REQUEST_ID_HEADER = "X-Request-Id"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{8,160}$")


def _request_id(request: Request) -> str:
    incoming = str(request.headers.get(REQUEST_ID_HEADER, "")).strip()
    if incoming and _SAFE_REQUEST_ID.fullmatch(incoming):
        return incoming
    return f"req_{uuid4().hex}"


def install_application_error_contract(
    app: FastAPI,
    *,
    logger: logging.Logger | None = None,
) -> None:
    error_logger = logger or logging.getLogger("application_errors")

    @app.middleware("http")
    async def request_traceability(request: Request, call_next):
        request_id = _request_id(request)
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    @app.exception_handler(Exception)
    async def unhandled_application_error(request: Request, exc: Exception):
        request_id = str(getattr(request.state, "request_id", "") or _request_id(request))
        error_logger.exception(
            "unhandled_request_error request_id=%s method=%s path=%s",
            request_id,
            request.method,
            request.url.path,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            headers={REQUEST_ID_HEADER: request_id},
            content={
                "detail": {
                    "code": "internal_server_error",
                    "message": "服务器处理请求时发生异常，请稍后重试。",
                    "request_id": request_id,
                }
            },
        )
