from io import BytesIO

import pytest
from PIL import Image

import material_parser
from material_pipeline import prepare_course_materials
from material_storage import MaterialRepository


class FakeUpload:
    def __init__(self, content: bytes):
        self.filename = "exam.png"
        self.content_type = "image/png"
        self._content = content
        self._offset = 0

    async def read(self, size: int) -> bytes:
        chunk = self._content[self._offset:self._offset + size]
        self._offset += len(chunk)
        return chunk


@pytest.mark.asyncio
async def test_image_question_ocr_preserves_confidence_and_coordinates(monkeypatch, tmp_path):
    stream = BytesIO()
    Image.new("RGB", (240, 120), color="white").save(stream, format="PNG")
    repository = MaterialRepository(tmp_path / "materials")
    asset = await repository.save_upload(FakeUpload(stream.getvalue()))

    def fake_ocr(_path):
        return [{
            "text": "题目：计算 2 + 3。答案：5。",
            "confidence": 0.93,
            "bbox": {"x": 0.1, "y": 0.2, "width": 0.7, "height": 0.2},
            "page": 1,
        }]

    monkeypatch.setattr(material_parser, "_ocr_image", fake_ocr)
    prepared = await prepare_course_materials(
        course_id="course-image",
        material_bindings=[{
            "asset_id": asset.asset_id,
            "purpose": "question_source",
            "reuse_policy": "verbatim_allowed",
            "rights_basis": "teacher_asserted",
        }],
        legacy_materials=[],
        repository=repository,
    )

    parsed = prepared["parsed_documents"][0]
    evidence = prepared["evidence_catalog"][0]
    assert parsed["parse_status"] == "parsed"
    assert parsed["quality"]["ocr_confidence"] == 0.93
    assert evidence["kind"] == "question"
    assert evidence["confidence"] == "high"
    assert evidence["locator"]["page"] == 1
    assert evidence["locator"]["bbox"]["x"] == 0.1
