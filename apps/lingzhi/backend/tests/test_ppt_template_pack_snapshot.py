from routers.teaching_representations import SlideDeckVariantBuildRequest
from slide_deck import SlideDeckContent
from slide_deck_renderer import validate_theme


def _compiled_theme() -> dict:
    return {
        "name": "Custom Academic",
        "background": "FAF7EF",
        "surface": "FFFFFF",
        "surface_alt": "F3EFE5",
        "primary": "315E7D",
        "secondary": "8297A5",
        "accent": "B7834A",
        "title": "243B53",
        "body": "3E4C59",
        "muted": "7B8794",
        "border": "D7DCE1",
        "title_font": "Noto Serif SC",
        "body_font": "Noto Sans SC",
        "visual_assets": {},
        "background_profiles": {},
        "text_box_styles": {},
        "semantic_layout_weights": {},
    }


def test_variant_request_accepts_an_immutable_template_pack_reference() -> None:
    request = SlideDeckVariantBuildRequest.model_validate({
        "mode": "teaching",
        "theme": "academic-editorial",
        "template_pack_id": "pptp-demo",
        "template_pack_version": 3,
    })

    assert request.template_pack_id == "pptp-demo"
    assert request.template_pack_version == 3


def test_slide_content_retains_the_template_snapshot_for_preview_and_export() -> None:
    content = SlideDeckContent.model_validate({
        "title": "Template snapshot",
        "slides": [],
        "template_pack": {
            "pack_id": "pptp-demo",
            "version": 3,
            "manifest_digest": "sha256:demo",
            "compiled_theme": _compiled_theme(),
        },
    })

    assert content.template_pack["version"] == 3
    assert content.template_pack["compiled_theme"]["primary"] == "315E7D"


def test_pptx_renderer_accepts_the_same_compiled_theme_snapshot() -> None:
    theme = _compiled_theme()

    assert validate_theme(theme)["primary"] == "315E7D"
