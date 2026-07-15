"""Read-only APIs for course full-chain acceptance preflight."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool

from course_acceptance import (
    AcceptanceProfile,
    inspect_course_acceptance,
    read_version_context,
    scan_course_directory,
)
from course_versions import course_version_repository
from dependencies import get_course_or_404
from storage import COURSES_DIR


router = APIRouter(tags=["course_acceptance"])


@router.get("/courses/{course_id}/acceptance-preflight")
async def get_course_acceptance_preflight(
    course_id: str,
    profile: AcceptanceProfile = Query(default="standard"),
) -> dict[str, Any]:
    course = await get_course_or_404(course_id)
    version_context = await run_in_threadpool(
        read_version_context,
        course_version_repository,
        course_id,
    )
    return inspect_course_acceptance(
        course,
        requested_profile=profile,
        version_context=version_context,
    )


@router.get("/course-acceptance/preflight")
async def get_course_acceptance_scan(
    profile: AcceptanceProfile = Query(default="standard"),
    course_id: str | None = Query(default=None),
) -> dict[str, Any]:
    return await run_in_threadpool(
        scan_course_directory,
        COURSES_DIR,
        requested_profile=profile,
        course_id=course_id,
        version_reader=course_version_repository,
    )
