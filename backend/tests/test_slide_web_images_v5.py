from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from routers.teaching_representations import SlideDeckVariantBuildRequest
from slide_asset_repository import SlideAssetRepository
from slide_web_images import (
    RetrievedImageCandidate,
    WebImageRetrievalConfig,
    allowed_retrieval_license,
    compute_image_target_v5,
    rank_image_candidates_v5,
    resolve_visual_search_request_v5,
    safe_retrieval_url,
    search_wikimedia_commons_v5,
    stage_retrieved_image,
)


@pytest.mark.parametrize(
    ("license_name", "allowed"),
    [
        ("CC0 1.0", True),
        ("Public Domain Mark", True),
        ("CC BY 4.0", True),
        ("CC BY-SA 4.0", False),
        ("CC BY-NC 4.0", False),
        ("CC BY-ND 4.0", False),
        ("unknown", False),
    ],
)
def test_retrieval_license_policy_is_fixed_server_side(
    license_name: str,
    allowed: bool,
) -> None:
    assert allowed_retrieval_license(license_name) is allowed


def test_image_target_is_generic_and_capped_by_visually_eligible_pages() -> None:
    assert compute_image_target_v5(
        chapter_count=8,
        main_slide_count=100,
        visually_eligible_page_count=18,
    ) == 18
    assert compute_image_target_v5(
        chapter_count=2,
        main_slide_count=12,
        visually_eligible_page_count=20,
    ) == 6


def test_client_config_cannot_widen_license_policy() -> None:
    config = WebImageRetrievalConfig.model_validate({
        "enabled": True,
        "mode": "wide_safe",
        "target_count": 9,
        "allowed_licenses": ["CC BY-SA", "unknown"],
    })

    assert config.target_count == 9
    assert config.allowed_licenses == ["public_domain", "cc0", "cc_by"]


def test_slide_build_request_accepts_wide_safe_retrieval_config() -> None:
    request = SlideDeckVariantBuildRequest.model_validate({
        "mode": "teaching",
        "theme": "grid-notebook",
        "force_rebuild": True,
        "web_image_retrieval": {
            "enabled": True,
            "mode": "wide_safe",
            "target_count": 7,
        },
    })

    assert request.web_image_retrieval.enabled is True
    assert request.web_image_retrieval.target_count == 7


def test_candidate_ranking_prefers_authority_and_must_show_coverage() -> None:
    generic = RetrievedImageCandidate(
        provider="openverse",
        asset_url="https://images.example.test/generic.jpg",
        source_page_url="https://example.test/item",
        title="generic object",
        creator="creator",
        license="CC BY 4.0",
        width=1600,
        height=900,
        canonical_terms=["engine"],
        matched_terms=["engine"],
        authority_score=0.4,
    )
    authoritative = generic.model_copy(update={
        "provider": "wikimedia_commons",
        "asset_url": "https://upload.wikimedia.org/example.jpg",
        "source_page_url": "https://commons.wikimedia.org/wiki/File:Example.jpg",
        "matched_terms": ["engine", "piston"],
        "authority_score": 0.95,
    })

    ranked = rank_image_candidates_v5(
        [generic, authoritative],
        must_show=["engine", "piston"],
        desired_aspect_ratio=16 / 9,
    )

    assert ranked[0].asset_url == authoritative.asset_url
    assert ranked[0].score > ranked[1].score


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("https://upload.wikimedia.org/example.jpg", True),
        ("http://127.0.0.1/private.jpg", False),
        ("https://localhost/private.jpg", False),
        ("file:///etc/passwd", False),
        ("https://169.254.169.254/latest/meta-data", False),
    ],
)
def test_retrieval_url_rejects_ssrf_targets(url: str, allowed: bool) -> None:
    assert safe_retrieval_url(url) is allowed


def test_retrieved_asset_manifest_keeps_full_provenance(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (640, 360), color=(40, 80, 120)).save(source)
    repository = SlideAssetRepository(tmp_path / "assets")
    candidate = RetrievedImageCandidate(
        provider="wikimedia_commons",
        asset_url="https://upload.wikimedia.org/example.png",
        source_page_url="https://commons.wikimedia.org/wiki/File:Example.png",
        title="Example",
        creator="Example Author",
        license="CC BY 4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        width=640,
        height=360,
        query="example structure",
        canonical_terms=["example"],
        matched_terms=["example"],
        authority_score=0.9,
        score=0.91,
    )

    asset = stage_retrieved_image(
        source,
        candidate=candidate,
        repository=repository,
        course_id="course-1",
        source_fragment_ids=["fragment-1"],
        alt_text="示例结构",
        purpose="structure",
    )
    manifest = asset.model_dump(mode="json")

    assert manifest["kind"] == "retrieved_image"
    assert manifest["source_page_url"] == candidate.source_page_url
    assert manifest["creator"] == "Example Author"
    assert manifest["license"] == "CC BY 4.0"
    assert manifest["retrieval_query"] == "example structure"
    assert manifest["retrieval_score"] == pytest.approx(0.91)
    assert manifest["retrieved_at"]


def test_commons_request_uses_a_descriptive_user_agent() -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"query": {"pages": {}}}

    class FakeClient:
        def get(self, url: str, *, params: dict, headers: dict) -> FakeResponse:
            captured.update({"url": url, "params": params, "headers": headers})
            return FakeResponse()

    assert search_wikimedia_commons_v5(
        "generic educational structure",
        client=FakeClient(),  # type: ignore[arg-type]
    ) == []
    assert str((captured["headers"] or {}).get("User-Agent", "")).startswith(
        "LingzhiPPTV5/"
    )


def test_source_bound_ai_search_plan_is_used_before_deterministic_fallback() -> None:
    slide = {
        "unit_id": "slide:v5:source-bound-search",
        "scene_kind": "concept",
        "title": "原始课程概念",
        "quality": {
            "visual_search_request": {
                "page_id": "slide:v5:source-bound-search",
                "need_visual": True,
                "visual_intent": "spatial_relation",
                "priority": "high",
                "canonical_terms": ["countercurrent heat exchanger"],
                "view_or_context": "cross-sectional view",
                "visual_goal": "Show the stated spatial relationship",
                "must_show": ["countercurrent flow"],
                "must_not_show": ["watermark"],
                "queries": [
                    "countercurrent heat exchanger cross section",
                    "countercurrent flow diagram public domain",
                ],
            },
        },
    }

    resolved = resolve_visual_search_request_v5(slide)

    assert resolved is not None
    assert resolved.visual_intent == "spatial_relation"
    assert resolved.queries == [
        "countercurrent heat exchanger cross section",
        "countercurrent flow diagram public domain",
    ]
