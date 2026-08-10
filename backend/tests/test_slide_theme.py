from slide_layout_registry import select_layout_v2
from slide_theme import slide_theme, slide_theme_asset_path


def test_qizhi_classroom_theme_bundles_authored_visual_assets() -> None:
    theme = slide_theme("qizhi-classroom")

    assert theme["template"]["template_id"] == "qizhi-classroom-v2"
    for asset_name in (
        "cover",
        "chapter",
        "recap",
        "interior_content",
        "interior_reasoning",
        "interior_practice",
        "interior_evidence",
    ):
        asset_path = slide_theme_asset_path(theme, asset_name)
        assert asset_path is not None
        assert asset_path.is_file()
    assert theme["background_profiles"]["practice"]["asset"] == "interior_practice"
    assert theme["text_box_styles"]["misconception"]["accent"] == "C45443"
    assert theme["text_box_styles"]["misconception"]["depth"] == "E9BEB5"


def test_qizhi_classroom_layout_preferences_participate_in_selection() -> None:
    selection = select_layout_v2(
        scene_kind="chapter_entry",
        evidence_kinds=["text"],
        character_count=120,
        item_count=1,
        theme="qizhi-classroom",
    )

    assert selection.layout_id == "chapter-question"
    assert selection.theme_score == 1.3
    assert "theme=qizhi-classroom:1.30" in selection.reason
