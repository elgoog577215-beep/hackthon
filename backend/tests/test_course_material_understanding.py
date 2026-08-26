from __future__ import annotations

import pytest

from ai_base import AIProviderUnavailable
from course_material_understanding import CourseMaterialUnderstandingService
from material_models import DocumentBlock, ParsedDocument


def _package() -> dict:
    return {
        "package_id": "tcs-test-package",
        "course_id": "course-1",
        "course_name": "数据结构",
        "academic_year": "2026-2027",
        "term": "秋季",
        "assets": [
            {
                "asset_id": "asset-plan",
                "filename": "第一讲课堂资料.docx",
                "relative_path": "已有资料/第一讲课堂资料.docx",
                "extension": ".docx",
            },
            {
                "asset_id": "asset-ppt",
                "filename": "第一讲课件.pptx",
                "relative_path": "已有资料/第一讲课件.pptx",
                "extension": ".pptx",
            },
        ],
    }


class FakeUnderstandingModel:
    async def analyze(self, payload: dict) -> dict:
        assert {item["asset_id"] for item in payload["assets"]} == {"asset-plan", "asset-ppt"}
        return {
            "assets": [
                {
                    "asset_id": "asset-plan",
                    "document_type": "lesson_plan",
                    "confidence": 0.92,
                    "reason": "正文包含教学目标、教学重点和课堂流程",
                    "course_alignment": {"match": "matched", "confidence": 0.9, "reason": "内容对应数据结构课程"},
                    "structure_matches": [{"node_id": "lesson-1", "confidence": 0.94, "reason": "内容对应第一讲"}],
                    "version_role": "current",
                    "version_reason": "与当前讲次结构一致",
                },
                {
                    "asset_id": "asset-ppt",
                    "document_type": "ppt",
                    "confidence": 0.98,
                    "reason": "PowerPoint课件",
                    "course_alignment": {"match": "matched", "confidence": 0.88, "reason": "内容对应数据结构课程"},
                    "structure_matches": [{"node_id": "lesson-1", "confidence": 0.91, "reason": "内容对应第一讲"}],
                    "version_role": "current",
                    "version_reason": "当前使用版本",
                },
            ],
            "relationships": [
                {
                    "source_asset_id": "asset-plan",
                    "target_asset_id": "asset-ppt",
                    "relation": "same_lesson",
                    "confidence": 0.96,
                    "reason": "教案与课件对应同一讲",
                }
            ],
            "summary": "识别出第一讲教案及对应课件",
        }


class FailingUnderstandingModel:
    async def analyze(self, payload: dict) -> dict:
        raise AIProviderUnavailable("not_configured")


class MisclassifyingModel:
    async def analyze(self, payload: dict) -> dict:
        asset_id = payload["assets"][0]["asset_id"]
        return {
            "assets": [{
                "asset_id": asset_id,
                "document_type": "school_material",
                "confidence": 0.94,
                "reason": "错误的模型判断",
                "course_alignment": {"match": "uncertain", "confidence": 0.6, "reason": "待确认"},
                "structure_matches": [],
                "version_role": "unknown",
                "version_reason": "待确认",
            }],
            "relationships": [],
        }


class CapturingBatchModel:
    def __init__(self) -> None:
        self.payload: dict | None = None

    async def analyze(self, payload: dict) -> dict:
        self.payload = payload
        return {"assets": [], "relationships": []}


@pytest.mark.asyncio
async def test_ai_understanding_covers_all_four_dimensions() -> None:
    package = _package()
    result = await CourseMaterialUnderstandingService(model=FakeUnderstandingModel()).analyze_batch(
        package=package,
        assets=package["assets"],
        course={"nodes": [{"node_id": "lesson-1", "node_name": "第1讲 线性表", "node_level": 1}]},
        batch_id="batch-1",
    )

    plan = next(item for item in result["assets"] if item["asset_id"] == "asset-plan")
    assert result["status"] == "ai_completed"
    assert result["dimensions"] == [
        "document_type", "course_structure", "version_role", "file_relationships",
    ]
    assert plan["document_type"] == "lesson_plan"
    assert plan["course_alignment"]["match"] == "matched"
    assert plan["structure_matches"][0]["node_id"] == "lesson-1"
    assert plan["version_role"] == "current"
    assert plan["related_asset_ids"] == ["asset-ppt"]
    assert result["relationships"][0]["relation"] == "same_lesson"
    assert result["missing_document_types"] == ["outline", "script", "question_bank"]


@pytest.mark.asyncio
async def test_model_failure_is_an_explicit_rule_fallback() -> None:
    package = _package()
    package["assets"][0].update({
        "filename": "第一讲教案.docx",
        "relative_path": "已有资料/第一讲教案.docx",
    })
    result = await CourseMaterialUnderstandingService(model=FailingUnderstandingModel()).analyze_batch(
        package=package,
        assets=package["assets"],
        course={"nodes": [{"node_id": "lesson-1", "node_name": "第1讲 线性表", "node_level": 1}]},
        batch_id="batch-2",
    )

    assert result["status"] == "rule_fallback"
    assert result["failure_code"] == "not_configured"
    assert [item["document_type"] for item in result["assets"]] == ["lesson_plan", "ppt"]
    assert result["relationships"][0]["relation"] == "same_lesson"
    assert set(result["low_confidence_asset_ids"]) == {"asset-plan", "asset-ppt"}


@pytest.mark.asyncio
async def test_teacher_confirmation_survives_later_batch_analysis() -> None:
    package = _package()
    package["assets"][0].update({
        "document_type": "script",
        "document_type_reason": "教师确认",
        "classification_source": "teacher",
    })
    result = await CourseMaterialUnderstandingService(model=FakeUnderstandingModel()).analyze_batch(
        package=package,
        assets=package["assets"],
        course={"nodes": [{"node_id": "lesson-1", "node_name": "第1讲 线性表", "node_level": 1}]},
    )

    plan = next(item for item in result["assets"] if item["asset_id"] == "asset-plan")
    assert plan["document_type"] == "script"
    assert plan["analysis_source"] == "teacher"
    assert plan["confidence"] == 1.0


@pytest.mark.asyncio
async def test_high_signal_content_structure_prevents_ai_type_drift() -> None:
    package = _package()
    package["assets"] = [package["assets"][0]]
    document = ParsedDocument(
        document_id="doc-1",
        asset_id="material-1",
        source_sha256="abc",
        parse_status="parsed",
        parser_name="test",
        parser_version="1",
        parse_options_hash="test",
        blocks=[
            DocumentBlock(block_id="b1", kind="heading", text="教学目标", order=0),
            DocumentBlock(block_id="b2", kind="heading", text="教学重点", order=1),
            DocumentBlock(block_id="b3", kind="heading", text="教学过程", order=2),
        ],
        created_at="2026-08-27T00:00:00+00:00",
    )
    result = await CourseMaterialUnderstandingService(model=MisclassifyingModel()).analyze_batch(
        package=package,
        assets=package["assets"],
        documents={"asset-plan": document},
    )

    plan = result["assets"][0]
    assert plan["document_type"] == "lesson_plan"
    assert plan["analysis_source"] == "hybrid"
    assert "教学目标" in plan["reason"]


@pytest.mark.asyncio
async def test_large_package_shares_one_bounded_excerpt_budget() -> None:
    package = _package()
    package["assets"] = [
        {
            "asset_id": f"asset-{index}",
            "filename": f"第{index}讲课堂资料.md",
            "relative_path": f"已有资料/第{index}讲课堂资料.md",
            "extension": ".md",
        }
        for index in range(1, 121)
    ]
    document = ParsedDocument(
        document_id="doc-large",
        asset_id="material-large",
        source_sha256="large",
        parse_status="parsed",
        parser_name="test",
        parser_version="1",
        parse_options_hash="test",
        blocks=[DocumentBlock(block_id="b1", kind="paragraph", text="课程资料" * 5000, order=0)],
        created_at="2026-08-27T00:00:00+00:00",
    )
    model = CapturingBatchModel()

    await CourseMaterialUnderstandingService(model=model).analyze_batch(
        package=package,
        assets=package["assets"],
        documents={item["asset_id"]: document for item in package["assets"]},
    )

    assert model.payload is not None
    excerpts = [item["text_excerpt"] for item in model.payload["assets"]]
    assert len(excerpts) == 120
    assert sum(len(item) for item in excerpts) <= 32_000
