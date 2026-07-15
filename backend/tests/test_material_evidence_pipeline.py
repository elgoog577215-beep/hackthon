from io import BytesIO

import pytest
from docx import Document
from fastapi import FastAPI
from fastapi.testclient import TestClient

from course_generation_workflow import (
    build_course_blueprint_from_plan,
    build_node_generation_context,
    normalize_course_plan_contract,
)
from course_quality import build_grounding_quality_report
from material_evidence import attach_evidence_to_plan, extract_grounding_annotations
from material_pipeline import prepare_course_materials
from material_storage import MaterialRepository, MaterialStorageError


class FakeUpload:
    def __init__(self, filename: str, content: bytes, content_type: str = "text/markdown"):
        self.filename = filename
        self.content_type = content_type
        self._content = content
        self._offset = 0

    async def read(self, size: int) -> bytes:
        if self._offset >= len(self._content):
            return b""
        chunk = self._content[self._offset:self._offset + size]
        self._offset += len(chunk)
        return chunk


@pytest.mark.asyncio
async def test_upload_parse_evidence_and_cache(tmp_path):
    repository = MaterialRepository(tmp_path / "materials")
    content = "# 导数\n\n定义：导数刻画瞬时变化率。\n\n题目：根据定义求导？\n"
    first = await repository.save_upload(FakeUpload("calculus.md", content.encode()))
    second = await repository.save_upload(FakeUpload("same.md", content.encode()))

    assert first.asset_id == second.asset_id
    prepared = await prepare_course_materials(
        course_id="course-1",
        material_bindings=[{
            "asset_id": first.asset_id,
            "purpose": "content_source",
            "priority": "core",
            "authority": "primary",
            "usage_policy": "must_use",
        }],
        legacy_materials=[],
        repository=repository,
    )
    prepared_again = await prepare_course_materials(
        course_id="course-2",
        material_bindings=prepared["material_bindings"],
        legacy_materials=[],
        repository=repository,
    )

    assert prepared["parsed_documents"][0]["parse_status"] == "parsed"
    assert prepared["evidence_catalog"]
    assert prepared["evidence_catalog"][0]["source_text"]
    assert prepared["evidence_catalog"][0]["locator"]["section_path"] == ["导数"]
    assert prepared_again["parsed_documents"][0]["document_id"] == prepared["parsed_documents"][0]["document_id"]
    assert repository.get_asset(first.asset_id).bound_course_ids == ["course-1", "course-2"]


@pytest.mark.asyncio
async def test_docling_slim_parses_real_docx_into_evidence(tmp_path):
    stream = BytesIO()
    document = Document()
    document.add_heading("Derivative", level=1)
    document.add_paragraph("A derivative describes an instantaneous rate of change.")
    document.save(stream)

    repository = MaterialRepository(tmp_path / "materials")
    asset = await repository.save_upload(FakeUpload(
        "derivative.docx",
        stream.getvalue(),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ))
    prepared = await prepare_course_materials(
        course_id="course-docx",
        material_bindings=[{"asset_id": asset.asset_id}],
        legacy_materials=[],
        repository=repository,
    )

    parsed = prepared["parsed_documents"][0]
    assert parsed["parse_status"] == "parsed"
    assert parsed["parser_name"] == "docling"
    assert any("instantaneous rate of change" in item["source_text"] for item in prepared["evidence_catalog"])


@pytest.mark.asyncio
async def test_upload_rejects_path_traversal_and_fake_pdf(tmp_path):
    repository = MaterialRepository(tmp_path / "materials")
    with pytest.raises(MaterialStorageError, match="文件名不安全"):
        await repository.save_upload(FakeUpload("../bad.md", b"# bad"))
    with pytest.raises(MaterialStorageError, match="有效 PDF"):
        await repository.save_upload(FakeUpload("fake.pdf", b"not a pdf", "application/pdf"))


@pytest.mark.asyncio
async def test_evidence_is_assigned_by_node_instead_of_broadcast(tmp_path):
    repository = MaterialRepository(tmp_path / "materials")
    asset = await repository.save_upload(FakeUpload(
        "calculus.md",
        "# 导数\n\n定义：导数是瞬时变化率。\n\n# 积分\n\n定义：积分描述累积量。".encode(),
    ))
    prepared = await prepare_course_materials(
        course_id="course-grounded",
        material_bindings=[{
            "asset_id": asset.asset_id,
            "purpose": "content_source",
            "priority": "core",
            "authority": "primary",
            "usage_policy": "must_use",
        }],
        legacy_materials=[],
        repository=repository,
    )
    plan = normalize_course_plan_contract({
        "course_title": "微积分",
        "chapters": [{
            "title": "基础",
            "sections": [
                {"title": "导数定义", "learning_objective": "解释导数", "assessment": ["解释变化率"]},
                {"title": "概率导论", "learning_objective": "解释概率", "assessment": ["计算概率"]},
            ],
        }],
    })
    plan, coverage = attach_evidence_to_plan(
        plan,
        evidence=prepared["evidence_catalog"],
        bindings=prepared["material_bindings"],
    )
    first, second = plan["chapters"][0]["sections"]

    assert first["evidence_refs"]
    assert second["evidence_refs"] == []
    assert "material_refs" not in first
    assert coverage["asset_coverage"][0]["assigned_nodes"] == ["L2-1-1"]

    artifacts = {
        **prepared,
        "course_generation_brief": {"subject": "微积分"},
        "subject_pedagogy_profile": {},
        "difficulty_profile": {},
        "evidence_coverage_plan": coverage,
    }
    blueprint = build_course_blueprint_from_plan(plan, artifacts)
    context = build_node_generation_context(
        course_metadata={**artifacts, "course_blueprint": blueprint},
        node=blueprint["nodes"][0],
    )
    assert "当前节点限定证据包" in context
    assert prepared["evidence_catalog"][0]["evidence_id"] in context


def test_grounding_markers_are_extracted_and_reported():
    evidence_id = "ev-abc123"
    content, annotations, invalid = extract_grounding_annotations(
        f"导数描述瞬时变化率。[[evidence:{evidence_id}]]",
        {evidence_id},
    )
    assert "[[evidence:" not in content
    assert annotations[0]["evidence_id"] == evidence_id
    assert invalid == []

    course = {
        "material_assets": [{"asset_id": "mat-1", "filename": "导数.md", "status": "parsed"}],
        "material_bindings": [{"asset_id": "mat-1", "purpose": "content_source", "usage_policy": "must_use"}],
        "evidence_catalog": [{"evidence_id": evidence_id, "asset_id": "mat-1"}],
        "evidence_coverage_plan": {"asset_coverage": [{"asset_id": "mat-1", "assigned_nodes": ["L2-1-1"]}]},
        "nodes": [{
            "node_id": "L2-1-1",
            "node_level": 2,
            "grounding_contract": {"required_evidence_ids": [evidence_id]},
            "grounding_annotations": annotations,
        }],
    }
    report = build_grounding_quality_report(course)
    assert report["passed"] is True
    assert report["material_coverage"][0]["coverage_level"] == "used"


def test_material_upload_api_uses_persisted_asset(monkeypatch, tmp_path):
    from routers import materials

    repository = MaterialRepository(tmp_path / "materials")
    monkeypatch.setattr(materials, "material_repository", repository)
    app = FastAPI()
    app.include_router(materials.router, prefix="/api")
    client = TestClient(app)

    response = client.post(
        "/api/materials",
        files={"file": ("notes.md", b"# Notes\n\nEvidence.", "text/markdown")},
    )
    assert response.status_code == 201
    asset_id = response.json()["asset_id"]
    assert repository.get_asset(asset_id) is not None
    assert "source_name" not in response.json()

    delete = client.delete(f"/api/materials/{asset_id}")
    assert delete.status_code == 200
