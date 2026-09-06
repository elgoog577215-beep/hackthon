import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from ppt_template_packs import (
    PptTemplatePackRepository,
    TemplatePackError,
    _compile_layout_constructions,
    template_pack_variant_key,
)
from routers import ppt_template_packs as pack_router
from routers import teacher_lesson_authoring as teacher_lesson_router
from slide_ai_planning_v6 import _layout_prompt_contract
from template_layout_contract import (
    TemplateLayoutContractError,
    compile_personal_template_layout_contract_v1,
)


def reference_pptx_bytes(*, width: int = 12_192_000, height: int = 6_858_000) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
              <Default Extension="xml" ContentType="application/xml"/>
            </Types>""",
        )
        archive.writestr(
            "ppt/presentation.xml",
            f"""<?xml version="1.0" encoding="UTF-8"?>
            <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
              <p:sldSz cx="{width}" cy="{height}"/>
              <p:sldIdLst><p:sldId id="256"/><p:sldId id="257"/></p:sldIdLst>
            </p:presentation>""",
        )
        archive.writestr(
            "ppt/theme/theme1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <a:themeElements><a:clrScheme name="Brand">
                <a:dk1><a:srgbClr val="17233A"/></a:dk1>
                <a:accent1><a:srgbClr val="315E7D"/></a:accent1>
                <a:accent2><a:srgbClr val="B68A4C"/></a:accent2>
              </a:clrScheme><a:fontScheme name="Brand Fonts">
                <a:majorFont><a:latin typeface="Noto Serif SC"/></a:majorFont>
                <a:minorFont><a:latin typeface="Noto Sans SC"/></a:minorFont>
              </a:fontScheme></a:themeElements>
            </a:theme>""",
        )
        archive.writestr(
            "ppt/slides/slide1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
                   xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld>
                <p:bg><p:bgPr><a:solidFill><a:srgbClr val="F7F2E8"/></a:solidFill></p:bgPr></p:bg>
                <p:spTree>
                  <p:sp><p:spPr><a:xfrm><a:off x="914400" y="685800"/><a:ext cx="5486400" cy="1371600"/></a:xfrm></p:spPr><p:txBody><a:p/></p:txBody></p:sp>
                  <p:pic/>
                </p:spTree>
              </p:cSld>
            </p:sld>""",
        )
        archive.writestr(
            "ppt/slides/_rels/slide1.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1"
                Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout"
                Target="../slideLayouts/slideLayout1.xml"/>
            </Relationships>""",
        )
        archive.writestr(
            "ppt/slideLayouts/slideLayout1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <p:sldLayout xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
                         xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld name="Title and Content"><p:spTree>
                <p:sp><p:nvSpPr><p:cNvPr id="1" name="Title"/><p:cNvSpPr/><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>
                  <p:spPr><a:xfrm><a:off x="914400" y="457200"/><a:ext cx="9144000" cy="914400"/></a:xfrm></p:spPr><p:txBody><a:p/></p:txBody></p:sp>
                <p:sp><p:nvSpPr><p:cNvPr id="2" name="Content"/><p:cNvSpPr/><p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr>
                  <p:spPr><a:xfrm><a:off x="914400" y="1828800"/><a:ext cx="9144000" cy="3657600"/></a:xfrm></p:spPr><p:txBody><a:p/></p:txBody></p:sp>
              </p:spTree></p:cSld>
            </p:sldLayout>""",
        )
        archive.writestr(
            "ppt/slides/slide2.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
                   xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree>
                <p:sp><p:spPr><a:xfrm><a:off x="914400" y="914400"/><a:ext cx="9144000" cy="4572000"/></a:xfrm></p:spPr><p:txBody><a:p/></p:txBody></p:sp>
              </p:spTree></p:cSld>
            </p:sld>""",
        )
        archive.writestr("ppt/media/image1.png", b"reference-image")
    return buffer.getvalue()


def test_repository_import_publish_and_version_lock(tmp_path: Path) -> None:
    repository = PptTemplatePackRepository(tmp_path)
    draft = repository.create_draft(
        owner_id="teacher-a",
        name="学院蓝",
        base_theme="academic-editorial",
        reference_pptx=reference_pptx_bytes(),
        reference_filename="学院模板.pptx",
        brand={"footer_text": "示例学院"},
    )

    assert draft["status"] == "draft"
    assert draft["extracted_style"]["aspect_ratio"] == "16:9"
    assert draft["extracted_style"]["colors"]["accent1"] == "315E7D"
    assert draft["extracted_style"]["title_font"] == "Noto Serif SC"
    assert draft["extracted_style"]["background_candidates"][0]["color"] == "F7F2E8"
    assert draft["extracted_style"]["slide_profiles"][0]["picture_count"] == 1
    assert draft["extracted_style"]["slide_profiles"][0]["source_layout_name"] == "Title and Content"
    assert draft["extracted_style"]["text_box_structure"]["total"] == 2
    assert draft["extracted_style"]["media_inventory"][0]["filename"] == "image1.png"
    assert len(draft["representative_pages"]) == 6
    assert len(draft["preview_slides"]) == 8
    assert len(draft["text_box_styles"]) == 10
    assert draft["text_box_styles"]["evidence"]["text"] == "F4F6F7"
    assert draft["compiled_theme"]["label"] == "学院蓝"
    assert draft["layout_constructions"][0]["fill_strategy"] == "source_geometry"
    assert draft["layout_constructions"][0]["slot_frames"]["body"]["source"] in {
        "adaptive",
        "slide",
        "layout",
    }

    published_v1 = repository.publish(draft["pack_id"], "teacher-a")
    assert published_v1["version"] == 1
    locked_v1 = repository.resolve_version(draft["pack_id"], 1, "teacher-a")

    repository.update_draft(
        draft["pack_id"],
        "teacher-a",
        {"name": "学院蓝新版", "brand": {"footer_text": "新版"}},
    )
    published_v2 = repository.publish(draft["pack_id"], "teacher-a")

    assert published_v2["version"] == 2
    assert locked_v1["name"] == "学院蓝"
    assert repository.resolve_version(draft["pack_id"], 1, "teacher-a")["manifest_digest"] == locked_v1["manifest_digest"]
    assert repository.resolve_version(draft["pack_id"], 2, "teacher-a")["name"] == "学院蓝新版"
    assert published_v2["compiled_theme"]["label"] == "学院蓝新版"


def test_internal_render_bundle_resolves_and_verifies_the_published_reference(
    tmp_path: Path,
) -> None:
    repository = PptTemplatePackRepository(tmp_path)
    reference = reference_pptx_bytes()
    draft = repository.create_draft(
        owner_id="teacher-a",
        name="可填充原生模板",
        base_theme="academic-editorial",
        reference_pptx=reference,
        reference_filename="native-reference.pptx",
        brand={"primary_color": "#2F84D7"},
    )
    repository.update_draft(
        draft["pack_id"],
        "teacher-a",
        {"representative_pages": [
            {**item, "confirmed": True}
            for item in draft["representative_pages"]
        ]},
    )
    published = repository.publish(draft["pack_id"], "teacher-a")

    contract, source_path = repository.resolve_render_bundle_internal(
        draft["pack_id"],
        published["version"],
    )

    assert contract.template_id == draft["pack_id"]
    assert source_path.read_bytes() == reference

    source_path.write_bytes(b"tampered")
    with pytest.raises(TemplatePackError, match="digest mismatch"):
        repository.resolve_render_bundle_internal(
            draft["pack_id"],
            published["version"],
        )


def test_personal_contract_prefers_confirmed_compiled_brand_over_source_fonts(
    tmp_path: Path,
) -> None:
    repository = PptTemplatePackRepository(tmp_path)
    draft = repository.create_draft(
        owner_id="teacher-a",
        name="品牌字体锁定",
        base_theme="academic-editorial",
        reference_pptx=reference_pptx_bytes(),
        reference_filename="calibri-source.pptx",
        brand={
            "primary_color": "#2F84D7",
            "title_font": "Noto Serif SC",
            "body_font": "Noto Sans SC",
        },
    )
    repository.update_draft(
        draft["pack_id"],
        "teacher-a",
        {"representative_pages": [
            {**item, "confirmed": True}
            for item in draft["representative_pages"]
        ]},
    )
    published = repository.publish(draft["pack_id"], "teacher-a")

    contract, _source_path = repository.resolve_render_bundle_internal(
        draft["pack_id"],
        published["version"],
    )

    assert contract.render_theme_overrides["accent"] == "2F84D7"
    assert contract.render_theme_overrides["title_font"] == "Noto Serif SC"
    assert contract.render_theme_overrides["body_font"] == "Noto Sans SC"


def test_layout_compiler_does_not_treat_a_tiny_subtitle_as_the_body_canvas() -> None:
    constructions = _compile_layout_constructions({
        "slide_profiles": [{
            "slide_number": 1,
            "layout_hint": "visual-led",
            "picture_count": 1,
            "table_count": 0,
            "source_layout_name": "Title Slide",
            "text_box_frames": [
                {
                    "x": 0.06,
                    "y": 0.08,
                    "width": 0.80,
                    "height": 0.08,
                    "source": "slide",
                },
                {
                    "x": 0.06,
                    "y": 0.15,
                    "width": 0.22,
                    "height": 0.03,
                    "source": "slide",
                },
                {
                    "x": 0.10,
                    "y": 0.34,
                    "width": 0.34,
                    "height": 0.42,
                    "source": "slide",
                },
                {
                    "x": 0.53,
                    "y": 0.34,
                    "width": 0.37,
                    "height": 0.42,
                    "source": "slide",
                },
                {
                    "x": 0.05,
                    "y": 0.31,
                    "width": 0.64,
                    "height": 0.21,
                    "source": "layout",
                },
            ],
        }],
    })

    frames = constructions[0]["slot_frames"]
    assert frames["title"] == {
        "x": 0.06,
        "y": 0.08,
        "width": 0.8,
        "height": 0.08,
        "source": "slide",
    }
    assert frames["body"]["height"] >= 0.40
    assert frames["body"]["width"] >= 0.78
    assert frames["left"]["x"] < frames["right"]["x"]
    assert frames["left"]["width"] == frames["right"]["width"]


def test_template_variant_key_locks_the_pack_version() -> None:
    assert template_pack_variant_key(
        "teaching",
        "academic-editorial",
        "pptp-demo",
        3,
    ) == "teaching:academic-editorial:template:pptp-demo@3"


def test_repository_is_owner_isolated_and_soft_delete_preserves_versions(tmp_path: Path) -> None:
    repository = PptTemplatePackRepository(tmp_path)
    draft = repository.create_draft(
        owner_id="teacher-a",
        name="个人模板",
        base_theme="qizhi-classroom",
        reference_pptx=None,
        reference_filename="",
        brand={"primary_color": "#275DAD"},
    )
    published = repository.publish(draft["pack_id"], "teacher-a")

    with pytest.raises(FileNotFoundError):
        repository.load_owned(draft["pack_id"], "teacher-b")
    with pytest.raises(FileNotFoundError):
        repository.resolve_version(draft["pack_id"], 1, "teacher-b")

    repository.soft_delete(draft["pack_id"], "teacher-a")
    assert all(item["pack_id"] != draft["pack_id"] for item in repository.list_for_owner("teacher-a"))
    assert repository.resolve_version(draft["pack_id"], published["version"], "teacher-a")["version"] == 1


def test_draft_update_rejects_untyped_brand_and_out_of_range_representative_pages(
    tmp_path: Path,
) -> None:
    repository = PptTemplatePackRepository(tmp_path)
    draft = repository.create_draft(
        owner_id="teacher-a",
        name="受控模板",
        base_theme="qizhi-classroom",
        reference_pptx=reference_pptx_bytes(),
        reference_filename="reference.pptx",
        brand={},
    )

    with pytest.raises(TemplatePackError):
        repository.update_draft(draft["pack_id"], "teacher-a", {"brand": ["invalid"]})
    with pytest.raises(TemplatePackError):
        repository.update_draft(
            draft["pack_id"],
            "teacher-a",
            {
                "representative_pages": [
                    {"role": role, "slide_number": 99, "confirmed": True}
                    for role in ("cover", "chapter", "content", "practice", "evidence", "recap")
                ],
            },
        )


def test_repository_rejects_malformed_or_macro_reference(tmp_path: Path) -> None:
    repository = PptTemplatePackRepository(tmp_path)

    with pytest.raises(TemplatePackError):
        repository.create_draft(
            owner_id="teacher-a",
            name="坏模板",
            base_theme="qizhi-classroom",
            reference_pptx=b"not a zip",
            reference_filename="bad.pptx",
            brand={},
        )
    with pytest.raises(TemplatePackError):
        repository.create_draft(
            owner_id="teacher-a",
            name="宏模板",
            base_theme="qizhi-classroom",
            reference_pptx=reference_pptx_bytes(),
            reference_filename="macro.pptm",
            brand={},
        )


def test_repository_accepts_powerpoint_template_files(tmp_path: Path) -> None:
    repository = PptTemplatePackRepository(tmp_path)
    draft = repository.create_draft(
        owner_id="teacher-a",
        name="POTX 模板",
        base_theme="academic-editorial",
        reference_pptx=reference_pptx_bytes(),
        reference_filename="reference.potx",
        brand={},
    )

    assert draft["extracted_style"]["slide_count"] == 2
    assert len(draft["layout_constructions"]) == 2


def test_template_pack_api_flow_and_asset_ownership(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repository = PptTemplatePackRepository(tmp_path)
    monkeypatch.setattr(pack_router, "ppt_template_pack_repository", repository)
    monkeypatch.setenv("PPT_TEMPLATE_PACKS_ENABLED", "true")
    app = FastAPI()
    app.include_router(pack_router.router, prefix="/api")
    client = TestClient(app)
    headers = {"X-User-Id": "teacher-a"}

    response = client.post(
        "/api/ppt-template-packs/import",
        headers=headers,
        data={
            "name": "学院蓝",
            "base_theme": "academic-editorial",
            "brand_json": json.dumps({"primary_color": "#315E7D"}),
        },
        files={
            "reference_pptx": (
                "学院模板.pptx",
                reference_pptx_bytes(),
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ),
            "logo": ("logo.png", b"\x89PNG\r\n\x1a\nlogo", "image/png"),
        },
    )
    assert response.status_code == 201, response.text
    draft = response.json()

    listing = client.get("/api/ppt-template-packs", headers=headers)
    assert listing.status_code == 200
    assert any(item["pack_id"] == draft["pack_id"] for item in listing.json()["personal"])

    published = client.post(
        f"/api/ppt-template-packs/{draft['pack_id']}/publish",
        headers=headers,
    )
    assert published.status_code == 200
    logo_id = next(item["asset_id"] for item in published.json()["assets"] if item["role"] == "logo")
    assert client.get(
        f"/api/ppt-template-packs/{draft['pack_id']}/assets/{logo_id}",
        headers=headers,
    ).status_code == 200
    assert client.get(
        f"/api/ppt-template-packs/{draft['pack_id']}/assets/{logo_id}",
        headers={"X-User-Id": "teacher-b"},
    ).status_code == 404


def test_personal_template_requires_confirmed_mapping_before_v6_use(tmp_path: Path) -> None:
    repository = PptTemplatePackRepository(tmp_path)
    draft = repository.create_draft(
        owner_id="teacher-a",
        name="通用机构模板",
        base_theme="academic-editorial",
        reference_pptx=reference_pptx_bytes(),
        reference_filename="reference.pptx",
        brand={},
    )

    published_v1 = repository.publish(draft["pack_id"], "teacher-a")
    assert published_v1["v6_eligible"] is False
    assert "representative_page_mapping_incomplete" in published_v1["v6_validation_errors"]
    with pytest.raises(TemplatePackError, match="representative_page_mapping_incomplete"):
        repository.resolve_v6_layout_contract(draft["pack_id"], 1, "teacher-a")

    confirmed = [
        {**item, "confirmed": True}
        for item in draft["representative_pages"]
    ]
    repository.update_draft(
        draft["pack_id"],
        "teacher-a",
        {"representative_pages": confirmed},
    )
    published_v2 = repository.publish(draft["pack_id"], "teacher-a")
    contract = repository.resolve_v6_layout_contract(draft["pack_id"], 2, "teacher-a")

    assert published_v2["v6_eligible"] is True
    assert len(contract.layouts) >= 18
    assert all(layout.template_layout_id.startswith(f"{draft['pack_id']}@2/") for layout in contract.layouts)
    assert all(layout.base_layout_id.startswith("source-slide-") for layout in contract.layouts)
    assert all(layout.source_slide_number >= 1 for layout in contract.layouts)
    assert all(layout.slot_frames for layout in contract.layouts)
    assert {layout.fill_strategy for layout in contract.layouts} <= {
        "source_geometry",
        "adaptive_overlay",
    }
    assert contract.render_theme_overrides["accent"] == "315E7D"
    assert contract.render_theme_overrides["green"] == "B68A4C"
    assert contract.render_theme_overrides["title"] == "17233A"
    assert contract.render_theme_overrides["title_font"] == "Noto Serif SC"
    ai_contract = _layout_prompt_contract(
        contract.layouts[0].template_layout_id,
        contract,
    )
    assert ai_contract["source_slide_number"] >= 1
    assert ai_contract["fill_strategy"] in {
        "source_geometry",
        "adaptive_overlay",
    }
    assert ai_contract["slot_frames"]["title"]

    compact_manifest = json.loads(json.dumps(published_v2))
    evidence_slide = next(
        item["slide_number"]
        for item in compact_manifest["representative_pages"]
        if item["role"] == "evidence"
    )
    evidence_construction = next(
        item
        for item in compact_manifest["layout_constructions"]
        if item["source_slide_number"] == evidence_slide
    )
    evidence_construction["slot_frames"]["title"] = {
        "x": 0.06,
        "y": 0.08,
        "width": 0.80,
        "height": 0.075,
        "source": "slide",
    }
    compact_contract = compile_personal_template_layout_contract_v1(
        compact_manifest
    )
    formula_layout = next(
        item
        for item in compact_contract.layouts
        if item.layout_slug == "evidence-formula"
    )
    title_slot = next(
        item for item in formula_layout.slots if item.slot_kind == "title"
    )
    assert title_slot.max_lines == 1
    assert title_slot.max_chars == 22


def test_template_pack_import_rejects_active_svg_logo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = PptTemplatePackRepository(tmp_path)
    monkeypatch.setattr(pack_router, "ppt_template_pack_repository", repository)
    monkeypatch.setenv("PPT_TEMPLATE_PACKS_ENABLED", "true")
    app = FastAPI()
    app.include_router(pack_router.router, prefix="/api")
    client = TestClient(app)

    response = client.post(
        "/api/ppt-template-packs/import",
        headers={"X-User-Id": "teacher-a"},
        data={"name": "Unsafe logo", "base_theme": "academic-editorial"},
        files={
            "logo": (
                "logo.svg",
                b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
                "image/svg+xml",
            ),
        },
    )

    assert response.status_code == 422


def test_teacher_manuscript_and_final_build_share_one_personal_template_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = PptTemplatePackRepository(tmp_path)
    monkeypatch.setattr(
        teacher_lesson_router,
        "ppt_template_pack_repository",
        repository,
    )
    draft = repository.create_draft(
        owner_id="teacher-a",
        name="锁定模板",
        base_theme="academic-editorial",
        reference_pptx=reference_pptx_bytes(),
        reference_filename="reference.pptx",
        brand={},
    )
    repository.update_draft(
        draft["pack_id"],
        "teacher-a",
        {
            "representative_pages": [
                {**item, "confirmed": True}
                for item in draft["representative_pages"]
            ]
        },
    )
    published = repository.publish(draft["pack_id"], "teacher-a")
    request = teacher_lesson_router.TeacherLessonV6BuildRequest.model_validate({
        "mode": "teaching",
        "theme": "academic-editorial",
        "template_pack_id": draft["pack_id"],
        "template_version": published["version"],
    })

    manuscript_template = teacher_lesson_router._resolve_teacher_v6_template(
        request,
        "teacher-a",
    )
    locked_template = teacher_lesson_router._resolve_locked_teacher_v6_template(
        {
            "theme": "academic-editorial",
            "template_pack_id": draft["pack_id"],
            "template_id": manuscript_template.template_id,
            "template_version": manuscript_template.template_version,
            "template_digest": manuscript_template.template_digest,
        },
        "teacher-a",
    )

    assert locked_template.template_digest == manuscript_template.template_digest
    assert locked_template.template_version == str(published["version"])

    with pytest.raises(HTTPException) as drifted:
        teacher_lesson_router._resolve_locked_teacher_v6_template(
            {
                "theme": "academic-editorial",
                "template_pack_id": draft["pack_id"],
                "template_id": manuscript_template.template_id,
                "template_version": manuscript_template.template_version,
                "template_digest": "tmpl_drifted",
            },
            "teacher-a",
        )
    assert drifted.value.status_code == 409
    assert drifted.value.detail["code"] == "lesson_ppt_template_lock_drifted"


def test_precompiler_personal_template_versions_remain_readable(
    tmp_path: Path,
) -> None:
    repository = PptTemplatePackRepository(tmp_path)
    draft = repository.create_draft(
        owner_id="teacher-a",
        name="旧模板版本",
        base_theme="academic-editorial",
        reference_pptx=reference_pptx_bytes(),
        reference_filename="reference.pptx",
        brand={},
    )
    repository.update_draft(
        draft["pack_id"],
        "teacher-a",
        {
            "representative_pages": [
                {**item, "confirmed": True}
                for item in draft["representative_pages"]
            ]
        },
    )
    published = repository.publish(draft["pack_id"], "teacher-a")
    legacy_snapshot = repository.load_owned(draft["pack_id"], "teacher-a")
    legacy_snapshot["version"] = published["version"]
    legacy_snapshot.pop("layout_constructions", None)

    legacy_contract = compile_personal_template_layout_contract_v1(
        legacy_snapshot
    )
    assert all(
        layout.fill_strategy == "renderer_adapter"
        for layout in legacy_contract.layouts
    )

    invalid_new_snapshot = {**legacy_snapshot, "layout_constructions": []}
    with pytest.raises(
        TemplateLayoutContractError,
        match="template_layout_constructions_missing",
    ):
        compile_personal_template_layout_contract_v1(invalid_new_snapshot)
