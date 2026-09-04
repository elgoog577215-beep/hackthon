from course_document import CourseBlock, CourseDocument, CourseSection, refresh_document_revision
from routers import teacher_lesson_authoring as router


def test_selected_ppt_evidence_binds_only_to_relevant_script_blocks() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="teacher-lesson-fixture",
        title="观察与解释",
        sections=[CourseSection(
            section_id="L2-1-1",
            title="现场观察记录",
            position=0,
        )],
        blocks=[
            CourseBlock(
                block_id="observe",
                section_id="L2-1-1",
                position=0,
                payload={"markdown": "记录观察对象、时间和环境条件。"},
            ),
            CourseBlock(
                block_id="unrelated",
                section_id="L2-1-1",
                position=1,
                payload={"markdown": "绘制算法流程图。"},
            ),
        ],
    ))

    original_revision = document.document_revision
    attached = router._attach_ppt_reference_evidence(document, [{
        "evidence_id": "ev-observation",
        "keywords": ["观察", "时间", "环境"],
        "summary": "观察手册要求记录时间和环境。",
    }])

    by_id = {block.block_id: block for block in attached.blocks}
    assert by_id["observe"].evidence_refs == ["ev-observation"]
    assert by_id["unrelated"].evidence_refs == []
    assert attached.document_revision != original_revision


def test_uploaded_ppt_review_context_includes_ppt_stage_materials(monkeypatch) -> None:
    source = {
        "course_id": "course-1",
        "blueprint_revision_id": "outline-1",
        "nodes": [
            {
                "node_id": "L1-1",
                "parent_node_id": "root",
                "node_level": 1,
                "node_name": "第一讲",
            },
            {
                "node_id": "L2-1-1",
                "parent_node_id": "L1-1",
                "node_level": 2,
                "node_name": "观察条件",
                "learning_objective": "能记录观察条件",
            },
        ],
    }

    class Repository:
        @staticmethod
        def lesson(_course_id: str, _lesson_unit_id: str):
            return {}

    monkeypatch.setattr(router.question_bank_repository, "load_bundle", lambda _course_id: None)
    monkeypatch.setattr(router, "_ppt_material_bundle", lambda *_args: ([{
        "material_asset_id": "mat-1",
        "source_asset_id": "tca-1",
        "source_label": "观察手册.pdf",
        "role": "primary",
    }], [{
        "evidence_id": "ev-1",
        "source_label": "观察手册.pdf",
        "summary": "观察时需记录时间与环境。",
    }]))

    sources, units, _revisions = router._imported_ppt_review_context(
        source,
        Repository(),
        "course-1",
        "L1-1",
        actor="teacher-1",
    )

    assert any(item["label"] == "主参考：观察手册.pdf" for item in sources)
    assert any(
        item["kind"] == "reference_material"
        and "记录时间与环境" in item["text"]
        for item in units
    )
