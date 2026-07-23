from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from course_document import document_from_legacy_course
from slide_asset_repository import SlideAssetRepository, finalize_visual_assets
from slide_deck_v3 import (
    compile_slide_deck_v3,
    deterministic_slide_allocation,
    fragment_course_document,
)
from slide_deck_renderer import export_structured_slide_deck
from slide_visuals import (
    SlideVisualPlanV1,
    deterministic_visual_plan,
    plan_slide_visuals,
    validate_visual_plan,
)


def visual_course() -> dict:
    return {
        "course_id": "visual-course",
        "course_name": "线性映射：结构与应用",
        "nodes": [
            {
                "node_id": "chapter-1",
                "parent_node_id": "root",
                "node_name": "第一章 线性映射",
                "node_level": 1,
                "content_blocks": [
                    {
                        "block_id": "concept",
                        "title": "线性映射保持两类运算结构",
                        "content": (
                            "线性映射同时保持向量加法与数乘。"
                            "\n\n- 先验证加法保持性"
                            "\n- 再验证数乘保持性"
                            "\n- 最后检查零向量"
                        ),
                        "metadata": {"role": "concept"},
                    },
                    {
                        "block_id": "formula",
                        "title": "定义式",
                        "content": "$$T(au+bv)=aT(u)+bT(v)$$",
                        "metadata": {"role": "reasoning", "kind": "formula"},
                    },
                    {
                        "block_id": "example",
                        "title": "平面旋转是线性映射",
                        "content": "旋转把每个向量映射到同角度的新方向，并保持向量组合关系。",
                        "metadata": {"role": "example"},
                    },
                    {
                        "block_id": "check",
                        "title": "判断练习",
                        "content": "平移为什么通常不是线性映射？",
                        "metadata": {"role": "checkpoint"},
                    },
                ],
            }
        ],
    }


def test_compiler_adds_grounded_visual_director_plan() -> None:
    course = visual_course()
    document = document_from_legacy_course(course)
    fragments = fragment_course_document(document)
    allocation = deterministic_slide_allocation(
        document,
        fragments,
        mode="teaching",
        theme="qizhi-classroom",
    )

    content = compile_slide_deck_v3(
        document,
        course,
        mode="teaching",
        theme="qizhi-classroom",
        allocation_plan=allocation,
    )

    assert content["visual_plan"]["schema_version"] == "slide_visual_plan_v1"
    assert content["build_signature"]["visual_policy_version"]
    assert content["visual_quality_report"]["passed"] is True
    assert content["visual_quality_report"]["effective_visual_coverage_ratio"] >= 0.70
    assert any(
        visual["kind"] == "relational_diagram"
        for slide in content["slides"]
        for visual in slide["visuals"]
    )
    assert all(slide["teaching_job"] for slide in content["slides"])
    assert all(slide["takeaway"] for slide in content["slides"])


def test_deterministic_director_uses_source_bound_visual_variety() -> None:
    course = visual_course()
    document = document_from_legacy_course(course)
    fragments = fragment_course_document(document)
    allocation = deterministic_slide_allocation(
        document,
        fragments,
        mode="teaching",
        theme="qizhi-classroom",
    )

    plan = deterministic_visual_plan(document, allocation, fragments)
    visual_kinds = {
        page.visual_anchor.kind
        for page in plan.pages
        if page.visual_anchor.kind != "none"
    }

    assert {
        "relational_diagram",
        "coordinate_plot",
        "table",
        "formula",
    } <= visual_kinds
    assert all("**" not in page.takeaway and "$$" not in page.takeaway for page in plan.pages)


def test_visual_plan_rejects_unknown_fragment_bindings() -> None:
    course = visual_course()
    document = document_from_legacy_course(course)
    fragments = fragment_course_document(document)
    allocation = deterministic_slide_allocation(
        document,
        fragments,
        mode="teaching",
        theme="qizhi-classroom",
    )
    plan = deterministic_visual_plan(document, allocation, fragments)
    raw = plan.model_dump(mode="json")
    page = next(item for item in raw["pages"] if item["visual_anchor"]["kind"] != "none")
    page["visual_anchor"]["source_fragment_ids"] = ["unknown-fragment"]

    with pytest.raises(ValueError, match="unknown fragment"):
        validate_visual_plan(
            SlideVisualPlanV1.model_validate(raw),
            allocation,
            fragments,
        )


def test_visual_plan_takeaway_cannot_add_an_unbound_number() -> None:
    course = visual_course()
    document = document_from_legacy_course(course)
    fragments = fragment_course_document(document)
    allocation = deterministic_slide_allocation(
        document,
        fragments,
        mode="teaching",
        theme="qizhi-classroom",
    )
    plan = deterministic_visual_plan(document, allocation, fragments)
    raw = plan.model_dump(mode="json")
    page = next(item for item in raw["pages"] if item["takeaway_source_fragment_ids"])
    page["takeaway"] = "该方法可以把误差降低 99%"

    with pytest.raises(ValueError, match="ungrounded number"):
        validate_visual_plan(
            SlideVisualPlanV1.model_validate(raw),
            allocation,
            fragments,
        )


@pytest.mark.asyncio
async def test_ai_visual_plan_with_rewritten_body_falls_back() -> None:
    course = visual_course()
    document = document_from_legacy_course(course)
    fragments = fragment_course_document(document)
    allocation = deterministic_slide_allocation(
        document,
        fragments,
        mode="teaching",
        theme="qizhi-classroom",
    )
    valid = deterministic_visual_plan(document, allocation, fragments)
    raw = valid.model_dump(mode="json")
    page = next(item for item in raw["pages"] if item["takeaway_source_fragment_ids"])
    page["takeaway"] = "模型擅自改写出的新结论"
    page["body"] = "不允许出现的正文"

    async def invalid_planner(_request):
        return raw

    resolved = await plan_slide_visuals(
        document,
        allocation,
        fragments,
        ai_planner=invalid_planner,
    )

    assert resolved.deck_brief["planner"] == "deterministic_fallback"
    assert resolved.deck_brief["fallback_reason"] == "invalid_or_failed_ai_visual_plan"


def test_asset_repository_validates_and_promotes_content_addressed_images(
    tmp_path: Path,
) -> None:
    repository = SlideAssetRepository(tmp_path / "assets")
    source = tmp_path / "source.png"
    Image.new("RGB", (640, 360), "#2F6FE4").save(source)

    staged = repository.stage_image(
        source,
        course_id="visual-course",
        source_fragment_ids=["fragment-1"],
        alt_text="蓝色抽象教学背景",
        purpose="application",
    )
    assert repository.get(staged.asset_id) is None
    assert repository.get_staged(staged.asset_id) == staged
    published = repository.promote(staged)

    assert published.asset_id.startswith("sva_")
    assert published.sha256
    assert repository.resolve(published.asset_id).read_bytes() == source.read_bytes()


def test_asset_repository_rejects_bad_images(tmp_path: Path) -> None:
    repository = SlideAssetRepository(tmp_path / "assets")
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not-an-image")

    with pytest.raises(ValueError, match="valid raster image"):
        repository.stage_image(
            bad,
            course_id="visual-course",
            source_fragment_ids=["fragment-1"],
            alt_text="损坏图片",
            purpose="application",
        )


def test_failed_quality_discards_staged_assets_without_publishing(tmp_path: Path) -> None:
    repository = SlideAssetRepository(tmp_path / "assets")
    source = tmp_path / "source.png"
    Image.new("RGB", (640, 360), "#2F6FE4").save(source)
    staged = repository.stage_image(
        source,
        course_id="visual-course",
        source_fragment_ids=["fragment-1"],
        alt_text="课程应用场景",
        purpose="application",
        kind="generated_illustration",
    )

    finalize_visual_assets(
        [staged.model_dump(mode="json")],
        repository=repository,
        publish=False,
    )

    assert repository.get(staged.asset_id) is None
    assert not list(repository.staging.glob(f"{staged.asset_id}-*"))


def test_pptx_uses_editable_native_connectors_for_visual_diagrams(
    tmp_path: Path,
) -> None:
    course = visual_course()
    document = document_from_legacy_course(course)
    fragments = fragment_course_document(document)
    allocation = deterministic_slide_allocation(
        document,
        fragments,
        mode="teaching",
        theme="qizhi-classroom",
    )
    content = compile_slide_deck_v3(
        document,
        course,
        mode="teaching",
        theme="qizhi-classroom",
        allocation_plan=allocation,
    )

    output = export_structured_slide_deck(content, tmp_path / "visual-deck.pptx")
    presentation = Presentation(output)

    assert any(
        shape.shape_type == MSO_SHAPE_TYPE.LINE
        for slide in presentation.slides
        for shape in slide.shapes
    )
    assert any(
        shape.has_text_frame and "SOURCE" in shape.text
        for slide in presentation.slides
        for shape in slide.shapes
    )


def test_image_provider_failure_degrades_to_deterministic_diagram(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SLIDE_IMAGE_API_BASE", "https://images.invalid/v1")
    monkeypatch.setenv("SLIDE_IMAGE_API_KEY", "test-key")
    monkeypatch.setenv("SLIDE_IMAGE_MODEL", "test-image-model")

    def fail_generation(*_args, **_kwargs):
        raise TimeoutError("provider timeout")

    monkeypatch.setattr(
        "slide_asset_repository.SlideImageProvider.generate",
        fail_generation,
    )
    course = visual_course()
    document = document_from_legacy_course(course)
    fragments = fragment_course_document(document)
    allocation = deterministic_slide_allocation(
        document,
        fragments,
        mode="teaching",
        theme="qizhi-classroom",
    )

    content = compile_slide_deck_v3(
        document,
        course,
        mode="teaching",
        theme="qizhi-classroom",
        allocation_plan=allocation,
    )

    assert content["quality_report"]["passed"] is True
    assert not content["visual_asset_manifest"]
    assert all(
        visual["kind"] != "generated_illustration"
        for slide in content["slides"]
        for visual in slide["visuals"]
    )


def test_configured_image_provider_exports_a_real_picture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SLIDE_IMAGE_API_BASE", "https://images.example/v1")
    monkeypatch.setenv("SLIDE_IMAGE_API_KEY", "test-key")
    monkeypatch.setenv("SLIDE_IMAGE_MODEL", "test-image-model")

    def generate_image(_provider, *, output_path, **_kwargs):
        Image.new("RGB", (960, 640), "#B9DCF4").save(output_path)
        return Path(output_path)

    monkeypatch.setattr(
        "slide_asset_repository.SlideImageProvider.generate",
        generate_image,
    )
    course = visual_course()
    course["nodes"][0]["content_blocks"].append({
        "block_id": "application-context",
        "title": "设备状态流转案例",
        "content": "设备先接收输入，然后执行校验，最后输出处理结果。",
        "metadata": {"role": "example"},
    })
    document = document_from_legacy_course(course)
    repository = SlideAssetRepository(tmp_path / "assets")
    content = compile_slide_deck_v3(
        document,
        course,
        mode="teaching",
        theme="qizhi-classroom",
        asset_repository=repository,
    )
    monkeypatch.setattr(
        "slide_deck_renderer.slide_asset_repository",
        repository,
    )

    output = export_structured_slide_deck(content, tmp_path / "visual-image-deck.pptx")
    presentation = Presentation(output)

    assert content["visual_asset_manifest"]
    assert any(
        visual["kind"] == "generated_illustration" and visual["asset_id"]
        for slide in content["slides"]
        for visual in slide["visuals"]
    )
    assert any(
        shape.shape_type == MSO_SHAPE_TYPE.PICTURE
        for slide in presentation.slides
        for shape in slide.shapes
    )
