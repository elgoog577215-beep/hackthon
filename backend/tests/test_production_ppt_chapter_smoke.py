import json

from course_document import CourseBlock, CourseDocument, CourseSection
from production_ppt_chapter_smoke import (
    SmokeFailure,
    _planned_scene_requirements,
    _source_disposition,
    build_chapter_document,
    extract_source_code_lines,
    finalize_deferred_render,
    rank_programming_chapter_candidates,
)


def test_smoke_uses_final_source_bound_story_scenes() -> None:
    story = {
        "chapters": [{
            "episodes": [
                {"scene_kind": "chapter_entry", "beats": []},
                {
                    "scene_kind": "concept",
                    "beats": [{"fragment_ids": ["concept-1"]}],
                },
                {
                    "scene_kind": "worked_example",
                    "beats": [{"fragment_ids": []}],
                },
                {
                    "scene_kind": "practice_feedback",
                    "beats": [{"fragment_ids": ["feedback-1"]}],
                },
                {"scene_kind": "chapter_recap", "beats": []},
            ],
        }],
    }

    assert _planned_scene_requirements(story) == {
        "concept",
        "practice_feedback",
    }


def test_smoke_accepts_only_explicit_code_source_disposition() -> None:
    allocation = {
        "pages": [{"fragment_ids": ["code-1", "prose-1"]}],
        "exclusions": [{
            "fragment_id": "code-2",
            "reason": "subject_artifact_redundant_after_chapter_coverage",
        }],
    }

    allocated, excluded = _source_disposition(
        allocation,
        {"code-1", "code-2"},
    )

    assert allocated == {"code-1"}
    assert excluded == {
        "code-2": "subject_artifact_redundant_after_chapter_coverage",
    }


def test_deferred_render_finalizer_promotes_only_matching_page_count(
    tmp_path,
    monkeypatch,
) -> None:
    (tmp_path / "chapter-smoke.pptx").write_bytes(b"pptx")
    (tmp_path / "report.json").write_text(
        json.dumps({
            "status": "passed_pending_render",
            "chain": {"candidate_status": "v5_ready"},
            "deck": {"slide_count": 3},
            "gates": {"quality_gate": True},
            "export": {"pptx_bytes": 4},
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "production_ppt_chapter_smoke._render_artifacts",
        lambda _pptx, _output: {
            "pdf_bytes": 100,
            "rendered_page_count": 3,
            "contact_sheet_bytes": 50,
        },
    )

    report = finalize_deferred_render(tmp_path)

    assert report["status"] == "passed"
    assert report["gates"]["rendered_page_count_matches"] is True
    assert report["render_verification"] == {
        "status": "passed",
        "executor": "isolated_ci_runner",
    }


def test_deferred_render_finalizer_blocks_page_count_mismatch(
    tmp_path,
    monkeypatch,
) -> None:
    (tmp_path / "chapter-smoke.pptx").write_bytes(b"pptx")
    (tmp_path / "report.json").write_text(
        json.dumps({
            "status": "passed_pending_render",
            "chain": {"candidate_status": "v5_needs_manual_edit"},
            "deck": {"slide_count": 3},
            "gates": {"quality_gate": True},
            "export": {"pptx_bytes": 4},
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "production_ppt_chapter_smoke._render_artifacts",
        lambda _pptx, _output: {
            "pdf_bytes": 100,
            "rendered_page_count": 2,
            "contact_sheet_bytes": 50,
        },
    )

    report = finalize_deferred_render(tmp_path)

    assert report["status"] == "failed"
    assert report["failure"]["failed_gates"] == [
        "rendered_page_count_matches",
    ]


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
