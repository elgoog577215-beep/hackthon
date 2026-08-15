"""Student-side course change tops out at the current chapter.

Owner decision 2026-08-12 (Q6): a learner's request may widen from one section
to the chapter that contains it, but never to the whole course — whole-course
edits belong to the teacher authoring chain. `whole_course` therefore stays a
supported scope in the domain (the teacher chain uses it); what changes is that
`current_chapter` exists and bounds its matching to one chapter's sections.

The test that matters most is the containment one: a chapter-scoped request
must not touch a section in a different chapter, however well it matches the
requested role.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from course_document import document_from_legacy_course
from course_evolution import CourseEvolutionRepository
from course_repository import CourseDocumentRepository
from section_evolution import generate_section_evolution_plan


class _MemoryCourseStorage:
    def __init__(self, *courses: dict) -> None:
        self.courses = {str(course["course_id"]): deepcopy(course) for course in courses}

    def load_course(self, course_id: str) -> dict | None:
        value = self.courses.get(course_id)
        return deepcopy(value) if value else None

    async def save_course(self, course_id: str, course: dict) -> None:
        self.courses[course_id] = deepcopy(course)


def _document_repository(course: dict) -> CourseDocumentRepository:
    return CourseDocumentRepository(_MemoryCourseStorage(course))


class _DeterministicGenerator:
    """Keeps these tests about scope, not about model output.

    Output must differ per call: a `not_duplicate` quality gate rejects two
    identical candidates in one plan, and a chapter-scoped plan spans several
    sections by design.
    """

    def __init__(self) -> None:
        self.calls = 0

    def _body(self, kind: str) -> str:
        self.calls += 1
        return (
            f"（第 {self.calls} 个{kind}候选）先给出一个贴近学习者已有经验的具体情境，"
            f"再逐步把情境里的每个量对应到本节定义的对象上，说明它们为什么可以这样对应；"
            f"接着回到本节结论，指出这个结论在该情境下具体断言了什么；"
            f"最后给出一个边界情形，说明超出条件时结论为什么不再成立。"
        )

    async def generate_course_block_candidate(self, **_kwargs) -> str:
        return self._body("升级")

    async def generate_new_course_block_candidate(self, **_kwargs) -> str:
        return self._body("新增")


def _chaptered_course() -> dict:
    """Two chapters, three teachable sections each."""
    nodes: list[dict] = []
    for chapter_index, chapter_title in enumerate(["第一章 线性变换", "第二章 特征值"], start=1):
        chapter_id = f"chapter-{chapter_index}"
        nodes.append({
            "node_id": chapter_id,
            "parent_node_id": "root",
            "node_name": chapter_title,
            "node_level": 1,
            "node_content": "",
        })
        for section_index in range(1, 4):
            section_id = f"c{chapter_index}-section-{section_index}"
            label = f"{chapter_index}.{section_index}"
            nodes.append({
                "node_id": section_id,
                "parent_node_id": chapter_id,
                "node_name": f"{label} 小节",
                "node_level": 2,
                "learning_objective": f"理解 {label}",
                "objective_id": f"objective-{section_id}",
                # Every section compiles to the same block role, so role
                # matching alone cannot be what keeps the change inside one
                # chapter — only the scope can.
                "node_content": (
                    f"这是 {label} 的正文。\n\n"
                    f"例如：用一个具体例子说明 {label}。"
                ),
                # A section without a knowledge contract is refused outright,
                # so every section needs one for the scope test to be about
                # scope rather than about missing knowledge.
                "knowledge_structure": [{
                    "concept_group": f"{label} 概念组",
                    "knowledge_points": [{
                        "name": f"{label} 知识点",
                        "statement": f"{label} 的核心结论。",
                        "knowledge_type": "principle",
                        "capability_points": [{
                            "name": f"应用 {label}",
                            "observable_behavior": f"在新情境中应用 {label}",
                        }],
                        "mastery_criteria": [{
                            "name": f"{label} 达标",
                            "observable_performance": f"独立完成 {label} 的应用",
                            "verification_method": f"完成 {label} 的检查题",
                        }],
                    }],
                }],
            })
    course = {
        "course_id": "course-chaptered",
        "course_name": "线性代数",
        "nodes": nodes,
    }
    document = document_from_legacy_course(course)
    course["course_document"] = document.model_dump(mode="json")
    course["course_schema_version"] = "course_document_v1"
    course["course_document_revision"] = document.document_revision
    course["course_document_authoritative"] = True
    course["current_course_version_id"] = document.document_revision
    course["course_operation_log"] = []
    return course


def _sections_of(state, plan_id: str) -> set[str]:
    plan = next(item for item in state.change_sets if item.change_set_id == plan_id)
    return {
        str(operation.target_section_id)
        for operation in plan.operations
        if operation.operation_type != "ADJUST_COURSE_DIFFICULTY"
    }


@pytest.mark.asyncio
async def test_chapter_scope_stays_inside_the_requesting_chapter(tmp_path: Path):
    repository = CourseEvolutionRepository(tmp_path)
    course = _chaptered_course()

    state = await generate_section_evolution_plan(
        course,
        user_id="student-a",
        section_id="c1-section-1",
        instruction="这一章的概念都讲得详细一点",
        scope_selection="current_chapter",
        request_id="req-chapter-1",
        repository=repository,
        document_repository=_document_repository(course),
        generator=_DeterministicGenerator(),
    )

    plan = state.change_sets[-1]
    assert plan.scope_selection == "current_chapter"
    touched = _sections_of(state, plan.change_set_id)
    assert touched, "a chapter-scoped request should match something"
    # The whole point: nothing from chapter 2, even though its sections carry
    # the same example role and would match a whole-course scan.
    assert all(section.startswith("c1-") for section in touched), touched
    assert not any(section.startswith("c2-") for section in touched), touched


@pytest.mark.asyncio
async def test_chapter_scope_can_reach_beyond_the_originating_section(tmp_path: Path):
    """Otherwise it would be indistinguishable from `current_section`."""
    repository = CourseEvolutionRepository(tmp_path)
    course = _chaptered_course()

    state = await generate_section_evolution_plan(
        course,
        user_id="student-a",
        section_id="c1-section-1",
        instruction="这一章的概念都讲得详细一点",
        scope_selection="current_chapter",
        request_id="req-chapter-2",
        repository=repository,
        document_repository=_document_repository(course),
        generator=_DeterministicGenerator(),
    )

    touched = _sections_of(state, state.change_sets[-1].change_set_id)
    assert len(touched) > 1, touched


@pytest.mark.asyncio
async def test_chapter_scope_reports_its_affected_sections(tmp_path: Path):
    """The impact preview reads `affected_section_ids`; it must be populated."""
    repository = CourseEvolutionRepository(tmp_path)
    course = _chaptered_course()

    state = await generate_section_evolution_plan(
        course,
        user_id="student-a",
        section_id="c1-section-1",
        instruction="这一章的概念都讲得详细一点",
        scope_selection="current_chapter",
        request_id="req-chapter-3",
        repository=repository,
        document_repository=_document_repository(course),
        generator=_DeterministicGenerator(),
    )

    plan = state.change_sets[-1]
    declared = {str(item) for item in plan.impact_summary.get("affected_section_ids") or []}
    assert declared == _sections_of(state, plan.change_set_id), (
        "the previewed sections must be exactly the sections that will change"
    )


@pytest.mark.asyncio
async def test_section_scope_is_unchanged_by_the_new_chapter_scope(tmp_path: Path):
    repository = CourseEvolutionRepository(tmp_path)
    course = _chaptered_course()

    state = await generate_section_evolution_plan(
        course,
        user_id="student-a",
        section_id="c1-section-1",
        instruction="这一节的概念讲得详细一点",
        scope_selection="current_section",
        request_id="req-section-1",
        repository=repository,
        document_repository=_document_repository(course),
        generator=_DeterministicGenerator(),
    )

    touched = _sections_of(state, state.change_sets[-1].change_set_id)
    assert touched == {"c1-section-1"}, touched


@pytest.mark.asyncio
async def test_whole_course_scope_remains_available_to_the_domain(tmp_path: Path):
    """The teacher authoring chain still needs it; only the student entry went away."""
    repository = CourseEvolutionRepository(tmp_path)
    course = _chaptered_course()

    state = await generate_section_evolution_plan(
        course,
        user_id="teacher-a",
        section_id="c1-section-1",
        instruction="全课程的概念都讲得详细一点",
        scope_selection="whole_course",
        request_id="req-whole-1",
        repository=repository,
        document_repository=_document_repository(course),
        generator=_DeterministicGenerator(),
    )

    touched = _sections_of(state, state.change_sets[-1].change_set_id)
    assert any(section.startswith("c2-") for section in touched), touched


@pytest.mark.asyncio
async def test_unknown_scope_is_rejected(tmp_path: Path):
    repository = CourseEvolutionRepository(tmp_path)
    course = _chaptered_course()

    with pytest.raises(ValueError):
        await generate_section_evolution_plan(
            course,
            user_id="student-a",
            section_id="c1-section-1",
            instruction="随便改",
            scope_selection="entire_universe",
            request_id="req-bad-1",
            repository=repository,
            document_repository=_document_repository(course),
            generator=_DeterministicGenerator(),
        )
