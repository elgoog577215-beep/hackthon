from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PIL import Image

import slide_web_images
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


def test_ppt_image_retrieval_uses_shared_gateway_and_hydrates_commons_license(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeGateway:
        async def retrieve(self, request: Any) -> dict[str, Any]:
            captured["request"] = request
            return {
                "provider": "searxng",
                "status": "completed",
                "queries": request.queries,
                "sources": [{
                    "url": "https://commons.wikimedia.org/wiki/File:Heart_diagram.png",
                    "title": "Heart diagram",
                    "excerpt": "Anatomical diagram of the human heart",
                    "matched_query": request.queries[0],
                    "provider_metadata": {
                        "engines": ["wikicommons.images"],
                        "image_url": "https://upload.wikimedia.org/heart-diagram.png",
                        "resolution": "1600 x 900",
                    },
                }],
                "receipt": {"status": "completed", "source_count": 1},
            }

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "query": {
                    "pages": {
                        "1": {
                            "title": "File:Heart diagram.png",
                            "imageinfo": [{
                                "thumburl": "https://upload.wikimedia.org/heart-diagram-thumb.png",
                                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Heart_diagram.png",
                                "thumbwidth": 1600,
                                "thumbheight": 900,
                                "extmetadata": {
                                    "LicenseShortName": {"value": "CC BY 4.0"},
                                    "LicenseUrl": {
                                        "value": "https://creativecommons.org/licenses/by/4.0/"
                                    },
                                    "Artist": {"value": "Example Author"},
                                },
                            }],
                        }
                    }
                }
            }

    class FakeCommonsClient:
        def get(self, url: str, *, params: dict, headers: dict) -> FakeResponse:
            captured["metadata_url"] = url
            captured["metadata_params"] = params
            captured["metadata_headers"] = headers
            return FakeResponse()

        def close(self) -> None:
            return None

    def fake_download(candidate: Any, *, client: Any, output_dir: str | Path) -> Path:
        del candidate, client
        target = Path(output_dir) / "retrieved.png"
        Image.new("RGB", (1600, 900), color=(40, 80, 120)).save(target)
        return target

    monkeypatch.setattr(slide_web_images, "download_retrieved_image_v5", fake_download)
    request = slide_web_images.VisualSearchRequestV5(
        page_id="slide:v5:heart",
        need_visual=True,
        visual_intent="physical_structure",
        priority="high",
        canonical_terms=["human heart"],
        visual_goal="Show the structure of the human heart",
        must_show=["heart"],
        queries=["human heart anatomy"],
    )

    asset = slide_web_images.retrieve_best_image_v5(
        request,
        repository=SlideAssetRepository(tmp_path / "assets"),
        course_id="course-1",
        source_fragment_ids=["fragment-1"],
        alt_text="Human heart anatomy",
        purpose="physical_structure",
        client=FakeCommonsClient(),  # type: ignore[arg-type]
        gateway=FakeGateway(),  # type: ignore[arg-type]
    )

    gateway_request = captured["request"]
    assert gateway_request.purpose == "ppt_image"
    assert gateway_request.category == "images"
    assert captured["metadata_url"] == "https://commons.wikimedia.org/w/api.php"
    assert captured["metadata_params"]["titles"] == "File:Heart diagram.png"
    assert str(captured["metadata_headers"]["User-Agent"]).startswith("LingzhiPPTV5/")
    assert asset is not None
    assert asset.source_provider == "searxng"
    assert asset.license == "CC BY 4.0"


def test_hydrate_shared_image_candidates_accepts_public_domain_archive_without_api() -> None:
    class NetworkMustNotBeUsed:
        def get(self, *_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError("public-domain result must not require Commons API")

    candidates = slide_web_images.hydrate_shared_image_candidates_v5(
        {
            "sources": [{
                "url": "https://pdimagearchive.org/images/heart",
                "title": "Model of the Heart of a Human Embryo",
                "excerpt": "Public-domain anatomical heart model",
                "matched_query": "human heart anatomy",
                "provider_metadata": {
                    "engines": ["public domain image archive"],
                    "image_url": "https://images.pdimagearchive.org/heart.jpg",
                    "thumbnail_url": (
                        "https://images.pdimagearchive.org/heart.jpg?fit=max&h=360&w=360"
                    ),
                },
            }]
        },
        client=NetworkMustNotBeUsed(),
    )

    assert len(candidates) == 1
    assert candidates[0].provider == "searxng"
    assert candidates[0].asset_url == "https://images.pdimagearchive.org/heart.jpg"
    assert candidates[0].source_page_url == "https://pdimagearchive.org/images/heart"
    assert candidates[0].license == "Public Domain"
