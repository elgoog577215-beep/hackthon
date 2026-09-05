"""Resolve one formal teacher lecture across legacy and lecture_v1 plans."""

from __future__ import annotations

import re
from typing import Any


_INTERNAL_LESSON_ID = re.compile(r"L1-(\d+)")


def _lecture_number(lesson_unit_id: str) -> int | None:
    match = _INTERNAL_LESSON_ID.fullmatch(str(lesson_unit_id or "").strip())
    return int(match.group(1)) if match else None


def chapter_matches_lesson(
    plan: dict[str, Any],
    chapter: dict[str, Any],
    lesson_unit_id: str,
) -> bool:
    """Match an internal L1 id to either a node-addressed or formal lecture."""
    direct_id = str(
        chapter.get("node_id") or chapter.get("chapter_id") or ""
    ).strip()
    if direct_id:
        return direct_id == lesson_unit_id
    if plan.get("authoring_structure_version") != "lecture_v1":
        return False
    expected = _lecture_number(lesson_unit_id)
    if expected is None:
        return False
    raw_number = chapter.get("lecture_number")
    if raw_number in (None, ""):
        raw_number = chapter.get("chapter_number")
    try:
        actual = int(raw_number)
    except (TypeError, ValueError):
        return False
    return actual == expected


def lesson_chapter_index(
    plan: dict[str, Any],
    lesson_unit_id: str,
) -> int | None:
    chapters = [
        chapter
        for chapter in plan.get("chapters") or []
        if isinstance(chapter, dict)
    ]
    for index, chapter in enumerate(chapters):
        if chapter_matches_lesson(
            plan,
            chapter,
            lesson_unit_id,
        ):
            return index
    return None


def resolve_lesson_chapter(
    plan: dict[str, Any],
    lesson_unit_id: str,
) -> dict[str, Any] | None:
    index = lesson_chapter_index(plan, lesson_unit_id)
    if index is None:
        return None
    chapters = [
        chapter
        for chapter in plan.get("chapters") or []
        if isinstance(chapter, dict)
    ]
    return chapters[index]


__all__ = [
    "chapter_matches_lesson",
    "lesson_chapter_index",
    "resolve_lesson_chapter",
]
