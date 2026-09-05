"""Subject-agnostic teaching storyboard for source-first slide decks.

The storyboard does not rewrite course content and does not contain
discipline-specific concepts.  It groups allocated pages into knowledge
episodes and measures whether each episode has a usable learning progression.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from course_document import CourseDocument, CourseSection, stable_hash

TEACHING_STORYBOARD_SCHEMA = "teaching_storyboard_v1"
TEACHING_STORYBOARD_POLICY_VERSION = "knowledge_episode_director_v1"

TeachingBeat = Literal[
    "orientation",
    "concept",
    "reasoning",
    "method",
    "example",
    "misconception",
    "checkpoint",
    "recap",
    "appendix",
]

_BEAT_ORDER: dict[str, int] = {
    "orientation": 0,
    "concept": 1,
    "reasoning": 2,
    "method": 3,
    "example": 4,
    "misconception": 5,
    "checkpoint": 6,
    "recap": 7,
    "appendix": 8,
}


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TeachingBeatV1(_StrictModel):
    page_id: str
    role: TeachingBeat
    beat_index: int = Field(ge=1)
    source_fragment_ids: list[str] = Field(default_factory=list)


class TeachingEpisodeV1(_StrictModel):
    episode_id: str
    chapter_id: str = ""
    topic_id: str = ""
    title: str
    learning_question: str
    beats: list[TeachingBeatV1] = Field(default_factory=list)
    present_roles: list[TeachingBeat] = Field(default_factory=list)
    missing_roles: list[TeachingBeat] = Field(default_factory=list)
    progression_score: float = Field(ge=0, le=1)


class TeachingStoryboardV1(_StrictModel):
    schema_version: Literal["teaching_storyboard_v1"] = TEACHING_STORYBOARD_SCHEMA
    policy_version: str = TEACHING_STORYBOARD_POLICY_VERSION
    course_id: str
    source_document_revision: str
    communication_job: str
    audience: str = "课程学习者"
    episodes: list[TeachingEpisodeV1] = Field(default_factory=list)


def build_teaching_storyboard(
    document: CourseDocument,
    allocation_plan: Any,
) -> TeachingStoryboardV1:
    """Compile allocated pages into source-bound, subject-neutral episodes."""
    sections = {section.section_id: section for section in document.sections}
    grouped: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for page in allocation_plan.pages:
        if page.appendix or not page.fragment_ids:
            continue
        chapter_id = str(getattr(page, "chapter_id", "") or "")
        topic_id = _topic_id(
            str(getattr(page, "section_id", "") or ""),
            sections,
        )
        grouped[(chapter_id, topic_id or chapter_id)].append(page)

    episodes: list[TeachingEpisodeV1] = []
    for (chapter_id, topic_id), pages in grouped.items():
        section = sections.get(topic_id) or sections.get(chapter_id)
        title = section.title if section else document.title
        beats = [
            TeachingBeatV1(
                page_id=page.page_id,
                role=_normalized_role(
                    str(getattr(page, "narrative_role", "") or "concept")
                ),
                beat_index=index,
                source_fragment_ids=list(page.fragment_ids),
            )
            for index, page in enumerate(pages, start=1)
        ]
        present_roles = list(dict.fromkeys(beat.role for beat in beats))
        expected = _expected_roles(present_roles)
        missing = [role for role in expected if role not in present_roles]
        transitions = sum(
            _BEAT_ORDER.get(beats[index].role, 0)
            >= _BEAT_ORDER.get(beats[index - 1].role, 0)
            for index in range(1, len(beats))
        )
        ordered_ratio = (
            1.0
            if len(beats) <= 1
            else transitions / (len(beats) - 1)
        )
        completeness = (
            1.0
            if not expected
            else (len(expected) - len(missing)) / len(expected)
        )
        progression = round((ordered_ratio * 0.55) + (completeness * 0.45), 6)
        episode_id = stable_hash(
            {
                "course_id": document.course_id,
                "topic_id": topic_id,
                "page_ids": [page.page_id for page in pages],
                "policy": TEACHING_STORYBOARD_POLICY_VERSION,
            },
            prefix="tse_",
        )
        episodes.append(TeachingEpisodeV1(
            episode_id=episode_id,
            chapter_id=chapter_id,
            topic_id=topic_id,
            title=title,
            learning_question=_learning_question(title),
            beats=beats,
            present_roles=present_roles,
            missing_roles=missing,
            progression_score=progression,
        ))

    return TeachingStoryboardV1(
        course_id=document.course_id,
        source_document_revision=document.document_revision,
        communication_job=(
            f"帮助课程学习者理解“{document.title}”中的关键概念，"
            "并能够通过例证、辨析和练习检验理解。"
        ),
        episodes=episodes,
    )


def storyboard_page_index(
    storyboard: TeachingStoryboardV1,
) -> dict[str, tuple[TeachingEpisodeV1, TeachingBeatV1]]:
    return {
        beat.page_id: (episode, beat)
        for episode in storyboard.episodes
        for beat in episode.beats
    }


def _topic_id(
    section_id: str,
    sections: dict[str, CourseSection],
) -> str:
    section = sections.get(section_id)
    if not section:
        return section_id
    visited: set[str] = set()
    while section.level > 2 and section.parent_section_id not in visited:
        visited.add(section.section_id)
        parent = sections.get(section.parent_section_id or "")
        if not parent:
            break
        section = parent
    return section.section_id


def _normalized_role(role: str) -> TeachingBeat:
    return {
        "application": "example",
        "activity": "checkpoint",
        "feedback": "checkpoint",
        "counterexample": "misconception",
        "summary": "recap",
        "transfer": "example",
        "appendix": "appendix",
    }.get(role, role if role in _BEAT_ORDER else "concept")  # type: ignore[return-value]


def _expected_roles(present: list[TeachingBeat]) -> list[TeachingBeat]:
    if not present:
        return []
    # A chapter opener/closer is a navigation beat, not a knowledge episode.
    # Requiring concept/example/checkpoint on that single divider creates a
    # false incomplete-story warning for every well-structured course.
    if set(present).issubset({"orientation", "recap"}):
        return []
    expected: list[TeachingBeat] = ["concept"]
    if any(role in present for role in ("reasoning", "method")):
        expected.append("reasoning" if "reasoning" in present else "method")
    expected.extend(["example", "checkpoint"])
    return expected


def _learning_question(title: str) -> str:
    clean = str(title or "").strip().rstrip("？?")
    if not clean:
        return "本节要建立怎样的理解，并用什么证据检验？"
    return f"{clean}解决了什么问题，又该如何检验理解？"


__all__ = [
    "TEACHING_STORYBOARD_POLICY_VERSION",
    "TeachingBeatV1",
    "TeachingEpisodeV1",
    "TeachingStoryboardV1",
    "build_teaching_storyboard",
    "storyboard_page_index",
]
