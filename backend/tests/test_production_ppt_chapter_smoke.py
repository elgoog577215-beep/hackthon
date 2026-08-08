from course_document import CourseBlock, CourseDocument, CourseSection
from production_ppt_chapter_smoke import (
    SmokeFailure,
    build_chapter_document,
    extract_source_code_lines,
    rank_programming_chapter_candidates,
)


def _document() -> CourseDocument:
    return CourseDocument(
        course_id="course-online",
        title="Online programming course",
        document_revision="cdr_online",
        sections=[
            CourseSection(
                section_id="chapter-code",
                title="Programming chapter",
                position=0,
                level=1,
            ),
            CourseSection(
                section_id="lesson-code",
                parent_section_id="chapter-code",
                title="Lifecycle methods",
                position=1,
                level=2,
            ),
            CourseSection(
                section_id="chapter-prose",
                title="Background chapter",
                position=2,
                level=1,
            ),
            CourseSection(
                section_id="lesson-prose",
                parent_section_id="chapter-prose",
                title="Background reading",
                position=3,
                level=2,
            ),
        ],
        blocks=[
            CourseBlock(
                block_id="concept",
                section_id="lesson-code",
                position=0,
                kind="rich_text",
                role="concept",
                payload={"markdown": "Lifecycle callbacks have a defined order."},
            ),
            CourseBlock(
                block_id="code",
                section_id="lesson-code",
                position=1,
                kind="code",
                role="example",
                payload={
                    "markdown": (
                        "```csharp\n"
                        "void Tick1() { Debug.Log(1); }\n"
                        "void Tick32() { Debug.Log(32); }\n"
                        "```"
                    )
                },
            ),
            CourseBlock(
                block_id="practice",
                section_id="lesson-code",
                position=2,
                kind="practice_ref",
                role="checkpoint",
                payload={"markdown": "Explain the callback order."},
            ),
            CourseBlock(
                block_id="prose",
                section_id="lesson-prose",
                position=0,
                kind="rich_text",
                role="concept",
                payload={"markdown": "Only prose is available here."},
            ),
        ],
    )


def test_programming_smoke_selects_one_source_chapter_with_code_and_loop() -> None:
    document = _document()

    candidates = rank_programming_chapter_candidates(document)

    assert [item.chapter_id for item in candidates] == ["chapter-code"]
    assert candidates[0].source_role_count == 3
    assert candidates[0].code_character_count > 40

    chapter_document = build_chapter_document(
        document,
        candidates[0].chapter_id,
    )
    assert [item.section_id for item in chapter_document.sections] == [
        "chapter-code",
        "lesson-code",
    ]
    assert [item.block_id for item in chapter_document.blocks] == [
        "concept",
        "code",
        "practice",
    ]
    assert extract_source_code_lines(chapter_document) == [
        "void Tick1() { Debug.Log(1); }",
        "void Tick32() { Debug.Log(32); }",
    ]


def test_programming_smoke_rejects_requested_chapter_without_code() -> None:
    try:
        rank_programming_chapter_candidates(
            _document(),
            requested_chapter_id="chapter-prose",
        )
    except SmokeFailure as exc:
        assert exc.code == "production_chapter_has_no_code_source"
    else:
        raise AssertionError("A programming smoke must not use a prose-only chapter")
