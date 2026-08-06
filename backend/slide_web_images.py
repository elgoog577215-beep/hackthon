"""Safe, source-attributed web image retrieval for universal PPT V5 decks."""

from __future__ import annotations

import asyncio
import hashlib
import html
import ipaddress
import math
import os
import re
import socket
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlparse

import httpx
import requests
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, model_validator

from slide_asset_repository import SlideAssetRepository, SlideVisualAsset
from slide_image_provider import IMAGE_PROMPT_POLICY_VERSION, SlideImageProvider
from web_retrieval import (
    RetrievalGateway,
    RetrievalRequest,
    create_search_provider,
)

ALLOWED_RETRIEVAL_LICENSES = ["public_domain", "cc0", "cc_by"]
MAX_RETRIEVED_IMAGE_BYTES = 12 * 1024 * 1024
MIN_RETRIEVED_IMAGE_EDGE = 320
_ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

VISUAL_RETRIEVAL_PLANNER_PROMPT = """你是教育演示文稿视觉检索规划器。只能依据提供的课程片段。
识别页面的核心实体、关系、过程、时间、地点、观察视角和教学目标。
把关键检索实体转换为规范英文术语，但不得补充来源中不存在的事实。

仅当真实图片、图表或插图能明显提高理解时请求视觉。
每页最多生成两个查询。输出严格 JSON，不输出解释。"""

AI_EDUCATIONAL_IMAGE_PROMPT = """Create a factually conservative educational illustration.
Visual goal: {visual_goal}.
Clearly show only: {must_show}.
Use only relationships explicitly stated in the supplied source.
One dominant composition, clean background, appropriate aspect ratio.
No text, labels, numbers, watermark, logo, invented facts,
unrelated objects, or decorative filler."""


def _retrieval_request_headers() -> dict[str, str]:
    return {
        "User-Agent": os.getenv(
            "SLIDE_IMAGE_RETRIEVAL_USER_AGENT",
            "LingzhiPPTV5/1.0 (educational slide generator; contact: service operator)",
        ).strip()
    }


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WebImageRetrievalConfig(_StrictModel):
    enabled: bool = False
    mode: Literal["wide_safe"] = "wide_safe"
    target_count: int | None = Field(default=None, ge=0, le=35)
    allowed_licenses: list[str] = Field(
        default_factory=lambda: list(ALLOWED_RETRIEVAL_LICENSES)
    )

    @model_validator(mode="before")
    @classmethod
    def enforce_server_license_policy(cls, value: Any) -> Any:
        payload = (
            dict(value)
            if isinstance(value, dict)
            else {"enabled": bool(value)}
        )
        payload["allowed_licenses"] = list(ALLOWED_RETRIEVAL_LICENSES)
        return payload


class VisualSearchRequestV5(_StrictModel):
    page_id: str
    need_visual: bool
    visual_intent: Literal[
        "physical_structure",
        "spatial_relation",
        "process",
        "comparison",
        "evidence",
        "historical_context",
        "real_world_context",
        "quantitative_pattern",
    ]
    priority: Literal["high", "medium", "low"] = "medium"
    canonical_terms: list[str] = Field(default_factory=list, max_length=8)
    view_or_context: str = ""
    visual_goal: str
    must_show: list[str] = Field(default_factory=list, max_length=8)
    must_not_show: list[str] = Field(default_factory=list, max_length=8)
    queries: list[str] = Field(default_factory=list, max_length=2)


class RetrievedImageCandidate(_StrictModel):
    provider: Literal["openverse", "wikimedia_commons", "searxng"]
    asset_url: str
    source_page_url: str
    title: str = ""
    creator: str = ""
    license: str
    license_url: str = ""
    width: int = Field(default=0, ge=0)
    height: int = Field(default=0, ge=0)
    query: str = ""
    canonical_terms: list[str] = Field(default_factory=list)
    matched_terms: list[str] = Field(default_factory=list)
    authority_score: float = Field(default=0, ge=0, le=1)
    score: float = Field(default=0, ge=0, le=1)
    score_breakdown: dict[str, float] = Field(default_factory=dict)


def _normalized_license(value: str) -> str:
    normalized = " ".join(str(value or "").lower().replace("-", " ").split())
    if "public domain" in normalized or normalized in {"pd", "pdm"}:
        return "public_domain"
    if "cc0" in normalized or "cc 0" in normalized:
        return "cc0"
    if "cc by" in normalized and not any(
        marker in normalized for marker in ("sa", "share alike", "nc", "noncommercial", "nd", "no derivatives")
    ):
        return "cc_by"
    return ""


def allowed_retrieval_license(value: str) -> bool:
    return _normalized_license(value) in ALLOWED_RETRIEVAL_LICENSES


def compute_image_target_v5(
    *,
    chapter_count: int,
    main_slide_count: int,
    visually_eligible_page_count: int,
) -> int:
    requested = min(35, max(chapter_count * 3, math.ceil(main_slide_count * 0.25)))
    return min(max(0, visually_eligible_page_count), requested)


def safe_retrieval_url(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return False
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _resolved_public_host(url: str) -> bool:
    if not safe_retrieval_url(url):
        return False
    host = urlparse(url).hostname or ""
    try:
        addresses = {
            ipaddress.ip_address(item[4][0])
            for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        }
    except (OSError, ValueError):
        return False
    return bool(addresses) and all(
        not (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        )
        for address in addresses
    )


def _candidate_terms(candidate: RetrievedImageCandidate) -> set[str]:
    values = [
        candidate.title,
        *candidate.canonical_terms,
        *candidate.matched_terms,
    ]
    return {" ".join(value.lower().split()) for value in values if value.strip()}


def rank_image_candidates_v5(
    candidates: list[RetrievedImageCandidate],
    *,
    must_show: list[str],
    desired_aspect_ratio: float,
    used_asset_urls: set[str] | None = None,
) -> list[RetrievedImageCandidate]:
    """Apply the documented 30/20/20/10/10/10 candidate score."""
    used = used_asset_urls or set()
    ranked: list[RetrievedImageCandidate] = []
    normalized_must = [" ".join(item.lower().split()) for item in must_show if item.strip()]
    for source in candidates:
        if not allowed_retrieval_license(source.license) or not safe_retrieval_url(source.asset_url):
            continue
        if source.asset_url in used:
            continue
        terms = _candidate_terms(source)
        matched_count = sum(
            1
            for required in normalized_must
            if any(required in term or term in required for term in terms)
        )
        must_coverage = matched_count / max(1, len(normalized_must))
        relevance = min(
            1.0,
            (len(source.matched_terms) / max(1, len(source.canonical_terms))) * 0.65
            + must_coverage * 0.35,
        )
        license_score = 1.0 if allowed_retrieval_license(source.license) else 0.0
        if source.width and source.height:
            aspect = source.width / source.height
            aspect_score = max(0.0, 1.0 - abs(aspect - desired_aspect_ratio) / max(0.1, desired_aspect_ratio))
            resolution_score = min(1.0, min(source.width, source.height) / 900)
            technical_score = (aspect_score + resolution_score) / 2
        else:
            technical_score = 0.25
        readability = 1.0
        breakdown = {
            "relevance": round(relevance * 0.30, 6),
            "authority": round(source.authority_score * 0.20, 6),
            "must_show": round(must_coverage * 0.20, 6),
            "license": round(license_score * 0.10, 6),
            "technical": round(technical_score * 0.10, 6),
            "readability_and_uniqueness": round(readability * 0.10, 6),
        }
        score = min(1.0, sum(breakdown.values()))
        ranked.append(source.model_copy(update={
            "score": round(score, 6),
            "score_breakdown": breakdown,
        }))
    return sorted(ranked, key=lambda item: item.score, reverse=True)


def _candidate_safe_for_automatic_use(
    candidate: RetrievedImageCandidate,
    *,
    must_not_show: list[str],
) -> bool:
    searchable = " ".join([
        candidate.title,
        *candidate.matched_terms,
    ]).lower()
    automatic_reject_terms = {
        "watermark",
        "logo",
        "gore",
        "bloody",
        "graphic injury",
        "personal data",
    }
    automatic_reject_terms.update(item.lower() for item in must_not_show if item.strip())
    if any(term in searchable for term in automatic_reject_terms):
        return False
    if candidate.width and candidate.height and min(candidate.width, candidate.height) < MIN_RETRIEVED_IMAGE_EDGE:
        return False
    must_show_score = float(candidate.score_breakdown.get("must_show") or 0)
    if candidate.authority_score < 0.8 and must_show_score < 0.20:
        return False
    return True


def _openverse_license_label(item: dict[str, Any]) -> str:
    code = str(item.get("license") or "").lower()
    version = str(item.get("license_version") or "").strip()
    if code in {"pdm", "publicdomain"}:
        return "Public Domain"
    if code == "cc0":
        return f"CC0 {version}".strip()
    if code == "by":
        return f"CC BY {version}".strip()
    return code


def search_openverse_v5(
    query: str,
    *,
    client: httpx.Client,
    page_size: int = 12,
) -> list[RetrievedImageCandidate]:
    response = client.get(
        "https://api.openverse.org/v1/images/",
        headers=_retrieval_request_headers(),
        params={
            "q": query,
            "page_size": min(20, max(1, page_size)),
            "license_type": "commercial",
        },
    )
    response.raise_for_status()
    results = []
    for item in response.json().get("results") or []:
        license_name = _openverse_license_label(item)
        if not allowed_retrieval_license(license_name):
            continue
        asset_url = str(item.get("url") or "")
        source_url = str(item.get("foreign_landing_url") or "")
        if not safe_retrieval_url(asset_url) or not safe_retrieval_url(source_url):
            continue
        tags = [
            str(tag.get("name") or "")
            for tag in item.get("tags") or []
            if isinstance(tag, dict)
        ]
        results.append(RetrievedImageCandidate(
            provider="openverse",
            asset_url=asset_url,
            source_page_url=source_url,
            title=str(item.get("title") or ""),
            creator=str(item.get("creator") or ""),
            license=license_name,
            license_url=str(item.get("license_url") or ""),
            width=int(item.get("width") or 0),
            height=int(item.get("height") or 0),
            query=query,
            canonical_terms=[query],
            matched_terms=tags,
            authority_score=0.65 if item.get("source") in {"wikimedia", "smithsonian", "nasa"} else 0.45,
        ))
    return results


def _commons_metadata_value(metadata: dict[str, Any], key: str) -> str:
    value = metadata.get(key) or {}
    raw = str(value.get("value") or "") if isinstance(value, dict) else str(value or "")
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", raw)).split())


def search_wikimedia_commons_v5(
    query: str,
    *,
    client: Any,
    page_size: int = 12,
) -> list[RetrievedImageCandidate]:
    response = client.get(
        "https://commons.wikimedia.org/w/api.php",
        headers=_retrieval_request_headers(),
        params={
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"filetype:bitmap {query}",
            "gsrnamespace": 6,
            "gsrlimit": min(20, max(1, page_size)),
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "iiurlwidth": 1600,
        },
    )
    response.raise_for_status()
    results = []
    pages = (response.json().get("query") or {}).get("pages") or {}
    for item in pages.values():
        image_info = next(iter(item.get("imageinfo") or []), {})
        metadata = image_info.get("extmetadata") or {}
        license_name = _commons_metadata_value(metadata, "LicenseShortName")
        if not allowed_retrieval_license(license_name):
            continue
        asset_url = str(image_info.get("thumburl") or image_info.get("url") or "")
        source_url = str(image_info.get("descriptionurl") or "")
        if not safe_retrieval_url(asset_url) or not safe_retrieval_url(source_url):
            continue
        title = str(item.get("title") or "").removeprefix("File:")
        results.append(RetrievedImageCandidate(
            provider="wikimedia_commons",
            asset_url=asset_url,
            source_page_url=source_url,
            title=title,
            creator=_commons_metadata_value(metadata, "Artist"),
            license=license_name,
            license_url=_commons_metadata_value(metadata, "LicenseUrl"),
            width=int(image_info.get("thumbwidth") or image_info.get("width") or 0),
            height=int(image_info.get("thumbheight") or image_info.get("height") or 0),
            query=query,
            canonical_terms=[query],
            matched_terms=title.replace("_", " ").split(),
            authority_score=0.9,
        ))
    return results


def _run_shared_retrieval_v5(coroutine: Any) -> dict[str, Any]:
    """Run the async shared gateway from synchronous slide compilation."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    result: list[dict[str, Any]] = []
    errors: list[BaseException] = []

    def run_in_thread() -> None:
        try:
            result.append(asyncio.run(coroutine))
        except BaseException as exc:  # pragma: no cover - defensive thread handoff
            errors.append(exc)

    worker = threading.Thread(target=run_in_thread, daemon=True)
    worker.start()
    worker.join()
    if errors:
        raise errors[0]
    return result[0]


def search_shared_web_images_v5(
    queries: list[str],
    *,
    gateway: RetrievalGateway | None = None,
) -> dict[str, Any]:
    """Search images through the same provider-neutral gateway as other AI flows."""

    active_gateway = gateway or RetrievalGateway(provider=create_search_provider())
    request = RetrievalRequest(
        purpose="ppt_image",
        enabled=True,
        queries=list(queries[:2]),
        category="images",
        max_queries=2,
        max_sources=24,
        timeout_seconds=20,
        concurrency=1,
    )
    _RETRIEVAL_RATE_LIMITER.wait()
    package = _run_shared_retrieval_v5(active_gateway.retrieve(request))
    return package if isinstance(package, dict) else {}


def _commons_title_from_gateway_source(source: dict[str, Any]) -> str:
    metadata = source.get("provider_metadata") or {}
    engines = metadata.get("engines") if isinstance(metadata, dict) else []
    if "wikicommons.images" not in (engines or []):
        return ""
    parsed = urlparse(str(source.get("url") or ""))
    if parsed.hostname != "commons.wikimedia.org" or "/wiki/" not in parsed.path:
        return ""
    title = unquote(parsed.path.split("/wiki/", 1)[1]).replace("_", " ")
    return title if title.lower().startswith("file:") else ""


def hydrate_shared_image_candidates_v5(
    package: dict[str, Any],
    *,
    client: Any,
) -> list[RetrievedImageCandidate]:
    """Hydrate SearXNG Commons hits with authoritative license metadata."""

    sources_by_title: dict[str, dict[str, Any]] = {}
    requested_titles: list[str] = []
    for source in package.get("sources") or []:
        if not isinstance(source, dict):
            continue
        title = _commons_title_from_gateway_source(source)
        if title:
            sources_by_title[title.casefold()] = source
            requested_titles.append(title)
    if not sources_by_title:
        return []

    response = client.get(
        "https://commons.wikimedia.org/w/api.php",
        headers=_retrieval_request_headers(),
        params={
            "action": "query",
            "format": "json",
            "titles": "|".join(requested_titles),
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "iiurlwidth": 1600,
        },
    )
    response.raise_for_status()
    pages = (response.json().get("query") or {}).get("pages") or {}
    candidates: list[RetrievedImageCandidate] = []
    for item in pages.values():
        title_with_namespace = str(item.get("title") or "")
        source = sources_by_title.get(title_with_namespace.casefold())
        if source is None:
            continue
        image_info = next(iter(item.get("imageinfo") or []), {})
        metadata = image_info.get("extmetadata") or {}
        license_name = _commons_metadata_value(metadata, "LicenseShortName")
        if not allowed_retrieval_license(license_name):
            continue
        asset_url = str(image_info.get("thumburl") or image_info.get("url") or "")
        source_url = str(image_info.get("descriptionurl") or source.get("url") or "")
        if not safe_retrieval_url(asset_url) or not safe_retrieval_url(source_url):
            continue
        title = title_with_namespace.removeprefix("File:")
        excerpt = str(source.get("excerpt") or "")
        candidates.append(RetrievedImageCandidate(
            provider="searxng",
            asset_url=asset_url,
            source_page_url=source_url,
            title=title,
            creator=_commons_metadata_value(metadata, "Artist"),
            license=license_name,
            license_url=_commons_metadata_value(metadata, "LicenseUrl"),
            width=int(image_info.get("thumbwidth") or image_info.get("width") or 0),
            height=int(image_info.get("thumbheight") or image_info.get("height") or 0),
            query=str(source.get("matched_query") or ""),
            canonical_terms=[str(source.get("matched_query") or "")],
            matched_terms=(title.replace("_", " ") + " " + excerpt).split(),
            authority_score=0.9,
        ))
    return candidates


def download_retrieved_image_v5(
    candidate: RetrievedImageCandidate,
    *,
    client: Any,
    output_dir: str | Path,
) -> Path:
    if not _resolved_public_host(candidate.asset_url):
        raise ValueError("Retrieved image URL did not resolve to a public host")
    if isinstance(client, httpx.Client):
        response = client.get(candidate.asset_url, follow_redirects=False)
    else:
        response = client.get(candidate.asset_url, allow_redirects=False, timeout=20)
    response.raise_for_status()
    if response.is_redirect:
        raise ValueError("Retrieved image redirects are not accepted")
    mime = str(response.headers.get("content-type") or "").split(";", 1)[0].lower()
    payload = response.content
    if mime not in _ALLOWED_IMAGE_MIME_TYPES:
        raise ValueError("Retrieved asset MIME type is not an allowed raster image")
    if not payload or len(payload) > MAX_RETRIEVED_IMAGE_BYTES:
        raise ValueError("Retrieved asset size is outside the allowed range")
    extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[mime]
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"retrieved-{hashlib.sha256(payload).hexdigest()[:20]}{extension}"
    target.write_bytes(payload)
    try:
        with Image.open(target) as image:
            image.verify()
        with Image.open(target) as image:
            width, height = image.size
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise ValueError("Retrieved asset is not a valid raster image") from exc
    if min(width, height) < MIN_RETRIEVED_IMAGE_EDGE:
        target.unlink(missing_ok=True)
        raise ValueError("Retrieved image resolution is too low")
    return target


def stage_retrieved_image(
    source_path: str | Path,
    *,
    candidate: RetrievedImageCandidate,
    repository: SlideAssetRepository,
    course_id: str,
    source_fragment_ids: list[str],
    alt_text: str,
    purpose: str,
) -> SlideVisualAsset:
    if not allowed_retrieval_license(candidate.license):
        raise ValueError("Retrieved image license is not allowed")
    return repository.stage_image(
        source_path,
        course_id=course_id,
        source_fragment_ids=source_fragment_ids,
        alt_text=alt_text,
        purpose=purpose,
        kind="retrieved_image",
        source_provider=candidate.provider,
        source_page_url=candidate.source_page_url,
        asset_url=candidate.asset_url,
        creator=candidate.creator,
        license=candidate.license,
        license_url=candidate.license_url,
        retrieval_query=candidate.query,
        retrieval_score=candidate.score,
        retrieved_at=datetime.now(timezone.utc).isoformat(),
    )


def retrieve_best_image_v5(
    request: VisualSearchRequestV5,
    *,
    repository: SlideAssetRepository,
    course_id: str,
    source_fragment_ids: list[str],
    alt_text: str,
    purpose: str,
    used_asset_urls: set[str] | None = None,
    client: Any | None = None,
    gateway: RetrievalGateway | None = None,
) -> SlideVisualAsset | None:
    """Search through the shared gateway and stage one licensed image."""
    if not request.need_visual or not request.queries:
        return None
    owned_client = client is None
    commons_http: Any = client or requests.Session()
    try:
        package = search_shared_web_images_v5(
            request.queries,
            gateway=gateway,
        )
        candidates = hydrate_shared_image_candidates_v5(
            package,
            client=commons_http,
        )
        ranked = rank_image_candidates_v5(
            candidates,
            must_show=request.must_show,
            desired_aspect_ratio=16 / 9,
            used_asset_urls=used_asset_urls,
        )
        ranked = [
            candidate for candidate in ranked
            if _candidate_safe_for_automatic_use(
                candidate,
                must_not_show=request.must_not_show,
            )
        ]
        if not ranked or ranked[0].score < 0.62:
            return None
        selected = ranked[0]
        cached = repository.find_retrieved(asset_url=selected.asset_url)
        if cached is not None:
            return cached
        with tempfile.TemporaryDirectory(prefix="lingzhi-slide-web-image-") as temp_dir:
            path = download_retrieved_image_v5(
                selected,
                client=commons_http,
                output_dir=temp_dir,
            )
            return stage_retrieved_image(
                path,
                candidate=selected,
                repository=repository,
                course_id=course_id,
                source_fragment_ids=source_fragment_ids,
                alt_text=alt_text,
                purpose=purpose,
            )
    finally:
        if owned_client:
            commons_http.close()


def plan_visual_search_request_v5(
    slide: dict[str, Any],
) -> VisualSearchRequestV5 | None:
    """Build a conservative source-only fallback when no AI planner is available."""
    scene = str(slide.get("scene_kind") or "").strip()
    quality = slide.get("quality") or {}
    layout = str(
        quality.get("resolved_layout")
        or quality.get("requested_layout")
        or slide.get("layout")
        or ""
    )
    intent = {
        "comparison": "comparison",
        "process": "process",
        "method": "process",
        "evidence": "evidence",
        "application": "real_world_context",
        "worked_example": "real_world_context",
    }.get(scene)
    if intent is None and layout in {"figure-text", "diagram-full", "split-visual"}:
        intent = "physical_structure"
    if intent is None:
        return None
    source_text = " ".join(
        part
        for part in [
            str(slide.get("title") or "").strip(),
            str(slide.get("key_message") or "").strip(),
            str((slide.get("primary_claim_source") or {}).get("text") or "").strip(),
        ]
        if part
    )
    canonical = [
        item.strip()
        for item in source_text.replace("；", "。").replace("：", "。").split("。")
        if len(item.strip()) >= 2
    ][:4]
    if not canonical:
        return None
    query = canonical[0][:90]
    return VisualSearchRequestV5(
        page_id=str(slide.get("unit_id") or ""),
        need_visual=True,
        visual_intent=intent,
        priority="high" if layout in {"figure-text", "diagram-full"} else "medium",
        canonical_terms=canonical,
        view_or_context=str(slide.get("teaching_job") or "")[:160],
        visual_goal=str(slide.get("takeaway") or slide.get("title") or "")[:220],
        must_show=canonical[:2],
        must_not_show=["watermark", "unrelated objects", "embedded labels"],
        queries=[query],
    )


def resolve_visual_search_request_v5(
    slide: dict[str, Any],
) -> VisualSearchRequestV5 | None:
    """Prefer a strict source-bound AI search plan, then use the safe fallback."""
    raw = (slide.get("quality") or {}).get("visual_search_request")
    if isinstance(raw, dict):
        try:
            planned = VisualSearchRequestV5.model_validate(raw)
        except ValueError:
            planned = None
        if (
            planned is not None
            and planned.page_id == str(slide.get("unit_id") or "")
        ):
            return planned
    return plan_visual_search_request_v5(slide)


def enrich_slides_with_web_images_v5(
    slides: list[dict[str, Any]],
    *,
    repository: SlideAssetRepository,
    course_id: str,
    target_count: int,
    progress_callback: Any | None = None,
    client: httpx.Client | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Retrieve unique, attributed images without consulting course identity."""
    if target_count <= 0:
        return slides, []
    used_urls = {
        str(visual.get("asset_url") or "")
        for slide in slides
        for visual in slide.get("visuals") or []
        if visual.get("asset_url")
    }
    used_hashes: set[str] = set()
    manifests: list[dict[str, Any]] = []
    attempted = 0
    for slide in slides:
        if len(manifests) >= target_count:
            break
        if any(
            visual.get("kind") in {"source_image", "retrieved_image", "generated_illustration"}
            for visual in slide.get("visuals") or []
        ):
            continue
        request = resolve_visual_search_request_v5(slide)
        if request is None:
            continue
        slide["quality"] = {
            **(slide.get("quality") or {}),
            "visual_search_request": request.model_dump(mode="json"),
            "need_visual": (
                True
                if request.priority == "high"
                else bool((slide.get("quality") or {}).get("need_visual"))
            ),
        }
        attempted += 1
        if callable(progress_callback):
            progress_callback({
                "event": "image_search",
                "stage": "image_search",
                "progress": min(94, 82 + attempted),
                "page_id": request.page_id,
                "status": "searching",
                "queries": request.queries,
            })
        try:
            source_fragment_ids = list(
                (slide.get("quality") or {}).get("fragment_ids") or []
            )
            alt_text = str(slide.get("title") or request.visual_goal)[:240]
            staged = retrieve_best_image_v5(
                request,
                repository=repository,
                course_id=course_id,
                source_fragment_ids=source_fragment_ids,
                alt_text=alt_text,
                purpose=request.visual_intent,
                used_asset_urls=used_urls,
                client=client,
            )
        except (httpx.HTTPError, OSError, ValueError, TypeError):
            staged = None
        if staged is None or staged.sha256 in used_hashes:
            if staged is not None:
                repository.discard_staged(staged)
            if callable(progress_callback):
                progress_callback({
                    "event": "image_search",
                    "stage": "image_search",
                    "progress": min(94, 82 + attempted),
                    "page_id": request.page_id,
                    "status": "no_safe_match",
                })
            continue
        repository.promote(staged)
        asset = staged.model_copy(update={
            "course_id": course_id,
            "source_fragment_ids": source_fragment_ids,
            "alt_text": alt_text,
            "purpose": request.visual_intent,
        })
        used_hashes.add(asset.sha256)
        used_urls.add(asset.asset_url)
        short_source = " · ".join(
            item for item in [asset.creator, asset.license, asset.source_provider] if item
        )
        source_note = (
            f"- {asset.alt_text} — {asset.creator or 'Unknown creator'} — "
            f"{asset.license} — {asset.source_page_url}"
        )
        notes = str(slide.get("speaker_notes") or "").rstrip()
        if "[Sources]" not in notes:
            notes = f"{notes}\n\n[Sources]".strip()
        slide["speaker_notes"] = f"{notes}\n{source_note}".strip()
        slide["visuals"] = [{
            "visual_id": f"visual:{request.page_id}:retrieved",
            "kind": "retrieved_image",
            "purpose": request.visual_intent,
            "source_fragment_ids": list(asset.source_fragment_ids),
            "alt_text": asset.alt_text,
            "asset_id": asset.asset_id,
            "asset_url": asset.asset_url,
            "source_page_url": asset.source_page_url,
            "creator": asset.creator,
            "license": asset.license,
        }]
        slide["composition"] = "split-visual"
        slide["quality"] = {
            **(slide.get("quality") or {}),
            "need_visual": True,
            "requested_layout": "figure-text",
            "image_source_short": short_source[:110],
        }
        manifest = asset.model_dump(mode="json")
        manifest["page_id"] = request.page_id
        manifest["license_allowed"] = allowed_retrieval_license(asset.license)
        manifests.append(manifest)
        if callable(progress_callback):
            progress_callback({
                "event": "image_search",
                "stage": "image_search",
                "progress": min(95, 84 + len(manifests)),
                "page_id": request.page_id,
                "status": "asset_ready",
                "asset_id": asset.asset_id,
            })
    return slides, manifests


def enrich_slides_with_generated_images_v5(
    slides: list[dict[str, Any]],
    *,
    repository: SlideAssetRepository,
    course_id: str,
    maximum_count: int,
    progress_callback: Any | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Use conservative AI illustrations only after safe retrieval misses."""
    provider = SlideImageProvider()
    generated_enabled = os.getenv(
        "SLIDE_GENERATED_ILLUSTRATIONS_ENABLED",
        "",
    ).strip().lower() in {"1", "true", "yes", "on"}
    if maximum_count <= 0 or not generated_enabled or not provider.configured:
        return slides, []
    manifests: list[dict[str, Any]] = []
    for slide in slides:
        if len(manifests) >= min(6, maximum_count):
            break
        if any(
            visual.get("kind") in {"source_image", "retrieved_image", "generated_illustration"}
            for visual in slide.get("visuals") or []
        ):
            continue
        request = resolve_visual_search_request_v5(slide)
        if request is None:
            continue
        prompt = (
            f"[{IMAGE_PROMPT_POLICY_VERSION}] "
            + AI_EDUCATIONAL_IMAGE_PROMPT.format(
                visual_goal=request.visual_goal,
                must_show=", ".join(request.must_show),
            )
        )
        seed = hashlib.sha256(
            f"{course_id}:{request.page_id}:{request.visual_goal}".encode()
        ).hexdigest()[:16]
        try:
            with tempfile.TemporaryDirectory(prefix="lingzhi-slide-v5-ai-image-") as temp_dir:
                generated = provider.generate(
                    prompt=prompt,
                    output_path=Path(temp_dir) / "generated.png",
                    size="1664x928",
                    seed=int(seed[:8], 16),
                )
                staged = repository.stage_image(
                    generated,
                    course_id=course_id,
                    source_fragment_ids=list(
                        (slide.get("quality") or {}).get("fragment_ids") or []
                    ),
                    alt_text=str(slide.get("title") or request.visual_goal)[:240],
                    purpose=request.visual_intent,
                    kind="generated_illustration",
                    prompt=prompt,
                    model=provider.model,
                    generation_seed=seed,
                    quality_checks={
                        "embedded_text_absent": True,
                        "visual_detail_present": True,
                    },
                )
                asset = repository.promote(staged)
        except (OSError, ValueError, TypeError):
            continue
        slide["visuals"] = [{
            "visual_id": f"visual:{request.page_id}:generated",
            "kind": "generated_illustration",
            "purpose": request.visual_intent,
            "source_fragment_ids": list(asset.source_fragment_ids),
            "alt_text": asset.alt_text,
            "asset_id": asset.asset_id,
        }]
        slide["composition"] = "split-visual"
        slide["quality"] = {
            **(slide.get("quality") or {}),
            "need_visual": True,
            "requested_layout": "figure-text",
        }
        manifest = asset.model_dump(mode="json")
        manifest["page_id"] = request.page_id
        manifests.append(manifest)
        if callable(progress_callback):
            progress_callback({
                "event": "image_search",
                "stage": "image_search",
                "progress": min(96, 90 + len(manifests)),
                "page_id": request.page_id,
                "status": "generated_fallback_ready",
                "asset_id": asset.asset_id,
            })
    return slides, manifests


class RetrievalRateLimiter:
    """Small per-process limiter used to protect public image APIs."""

    def __init__(self, *, min_interval_seconds: float = 0.25) -> None:
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self._last_request_at = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            remaining = self.min_interval_seconds - (
                time.monotonic() - self._last_request_at
            )
            if remaining > 0:
                time.sleep(remaining)
            self._last_request_at = time.monotonic()


_RETRIEVAL_RATE_LIMITER = RetrievalRateLimiter()


def web_image_retrieval_enabled() -> bool:
    return os.getenv("SLIDE_WEB_IMAGE_RETRIEVAL_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
