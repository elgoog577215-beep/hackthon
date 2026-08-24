from material_models import DocumentBlock, DocumentLocator, ParsedDocument
from question_bank import QuestionBankRepository, merge_teacher_imported_questions
from question_bank_imports import (
    QuestionBankImportRepository,
    extract_question_drafts,
)


def _parsed_document(*, degraded: bool = False) -> ParsedDocument:
    return ParsedDocument(
        document_id="doc-import",
        asset_id="mat-import",
        source_sha256="source-hash",
        parse_status="degraded" if degraded else "parsed",
        parser_name="test",
        parser_version="1",
        parse_options_hash="options",
        created_at="2026-08-24T00:00:00+00:00",
        blocks=[
            DocumentBlock(
                block_id="heading",
                order=0,
                text="一、单项选择题",
                locator=DocumentLocator(page=1),
            ),
            DocumentBlock(
                block_id="question-1",
                order=1,
                text=(
                    "1. HTTP 默认端口是？\n"
                    "A. 21\nB. 80\nC. 443\n"
                    "答案：B\n解析：HTTP 默认使用 80 端口。"
                ),
                locator=DocumentLocator(page=1),
            ),
            DocumentBlock(
                block_id="heading-2",
                order=2,
                text="二、简答题",
                locator=DocumentLocator(page=2),
            ),
            DocumentBlock(
                block_id="question-2",
                order=3,
                text="2. 说明 HTTP 请求与响应的关系。",
                locator=DocumentLocator(page=2),
            ),
        ],
    )


def test_extract_question_drafts_preserves_pages_and_flags_uncertain_answers():
    drafts, pages = extract_question_drafts(
        _parsed_document(),
        node_ids=["node-http"],
    )

    assert len(drafts) == 2
    assert drafts[0]["question_type"] == "single_choice"
    assert drafts[0]["answer"] == "B"
    assert drafts[0]["options"][1] == {"id": "B", "text": "80"}
    assert drafts[0]["source_page"] == 1
    assert drafts[0]["confirmed"] is True
    assert drafts[1]["question_type"] == "short_answer"
    assert drafts[1]["warnings"] == ["answer_missing"]
    assert drafts[1]["confirmed"] is False
    assert [page["page"] for page in pages] == [1, 2]


def test_import_session_is_recoverable_and_requires_warning_confirmation(tmp_path):
    document = _parsed_document()
    drafts, pages = extract_question_drafts(document)
    repository = QuestionBankImportRepository(tmp_path / "imports")

    session = repository.create(
        course_id="course-http",
        actor_id="teacher-1",
        asset=type(
            "Asset",
            (),
            {
                "asset_id": "mat-import",
                "filename": "HTTP 测试题.docx",
                "extension": ".docx",
                "size_bytes": 1024,
            },
        )(),
        document=document,
        questions=drafts,
        source_pages=pages,
    )

    assert session["pending_count"] == 1
    restored = repository.load("course-http", session["import_id"])
    assert restored is not None
    assert restored["questions"][1]["prompt"].startswith("说明 HTTP")

    updated = repository.update_question(
        "course-http",
        session["import_id"],
        drafts[1]["draft_id"],
        {"confirmed": True},
    )
    assert updated["pending_count"] == 0
    assert updated["status"] == "ready"


def test_confirmed_import_merges_without_ai_generated_questions(tmp_path):
    drafts, _ = extract_question_drafts(_parsed_document())
    drafts[1]["confirmed"] = True
    repository = QuestionBankRepository(tmp_path / "banks")
    course = {
        "course_id": "course-http",
        "course_name": "网络爬虫",
        "course_purpose": "systematic",
        "difficulty": "intermediate",
        "nodes": [{
            "node_id": "node-http",
            "node_level": 2,
            "node_name": "HTTP 基础",
            "learning_objective": "解释 HTTP 请求与响应",
            "key_points": ["HTTP", "状态码"],
            "assessment": ["识别请求与响应"],
        }],
    }

    bundle = merge_teacher_imported_questions(
        course,
        drafts,
        asset_id="mat-import",
        document_id="doc-import",
        source_label="HTTP 测试题.docx",
        repository=repository,
    )

    assert len(bundle["items"]) == 2
    assert {item["source_type"] for item in bundle["items"]} == {"imported"}
    assert bundle["items"][0]["source_records"][0]["page"] == 1
    assert bundle["generation_audit"]["teacher_imports"][0]["question_count"] == 2
