import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ppt_template_packs import PptTemplatePackRepository, TemplatePackError
from routers import ppt_template_packs as pack_router


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
    assert len(draft["representative_pages"]) == 6
    assert len(draft["preview_slides"]) == 8
    assert len(draft["text_box_styles"]) == 10
    assert draft["text_box_styles"]["evidence"]["text"] == "F4F6F7"

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
