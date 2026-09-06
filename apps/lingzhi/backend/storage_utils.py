"""Small compatibility helpers for storage calls used by routers."""

from __future__ import annotations

import inspect
from typing import Any

from fastapi import HTTPException

from course_document import COURSE_DOCUMENT_SCHEMA


async def save_course_compat(storage_obj: Any, course_id: str, course_data: dict) -> None:
    """Persist a course whether the injected storage is sync or async.

    Production storage exposes async ``save_course`` while several tests inject a
    lightweight sync storage. Router code should await real persistence without
    forcing test doubles to become async-only.
    """

    if (
        course_data.get("course_schema_version") == COURSE_DOCUMENT_SCHEMA
        or course_data.get("course_document_authoritative") is True
    ):
        raise HTTPException(
            status_code=409,
            detail="Canonical course documents must be changed through the course command service",
        )

    result = storage_obj.save_course(course_id, course_data)
    if inspect.isawaitable(result):
        await result
