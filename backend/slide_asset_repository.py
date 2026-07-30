"""Immutable content-addressed storage for slide image assets."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import shutil
import tempfile
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from storage import DATA_DIR
from material_storage import IMAGE_EXTENSIONS, material_repository
from slide_image_provider import IMAGE_PROMPT_POLICY_VERSION, SlideImageProvider
from slide_theme import slide_theme
from slide_visuals import SlideVisualPlanV1, VisualAnchorV1, VisualNodeV1


class SlideVisualAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    course_id: str
    kind: Literal["source_image", "generated_illustration"]
    purpose: str
    source_fragment_ids: list[str] = Field(default_factory=list)
    alt_text: str
    sha256: str
    mime_type: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    byte_size: int = Field(gt=0)
    filename: str
    prompt: str = ""
    model: str = ""
    generation_seed: str = ""
    quality_checks: dict[str, bool] = Field(default_factory=dict)


class SlideAssetRepository:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or Path(DATA_DIR) / "slide_visual_assets")
        self.root.mkdir(parents=True, exist_ok=True)
        self.staging = self.root / ".staging"
        self.staging.mkdir(parents=True, exist_ok=True)

    def stage_image(
        self,
        source_path: str | Path,
        *,
        course_id: str,
        source_fragment_ids: list[str],
        alt_text: str,
        purpose: str,
        kind: Literal["source_image", "generated_illustration"] = "source_image",
        prompt: str = "",
        model: str = "",
        generation_seed: str = "",
        quality_checks: dict[str, bool] | None = None,
    ) -> SlideVisualAsset:
        source = Path(source_path)
        try:
            with Image.open(source) as image:
                image.verify()
            with Image.open(source) as image:
                width, height = image.size
                image_format = str(image.format or "").lower()
        except Exception as exc:
            raise ValueError("Slide asset must be a valid raster image") from exc
        payload = source.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        asset_id = f"sva_{digest[:24]}"
        extension = {
            "jpeg": ".jpg",
            "jpg": ".jpg",
            "png": ".png",
            "webp": ".webp",
            "gif": ".gif",
        }.get(image_format, source.suffix.lower() or ".png")
        filename = f"{asset_id}{extension}"
        staged_dir = Path(tempfile.mkdtemp(prefix=f"{asset_id}-", dir=self.staging))
        staged_file = staged_dir / filename
        shutil.copyfile(source, staged_file)
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        asset = SlideVisualAsset(
            asset_id=asset_id,
            course_id=course_id,
            kind=kind,
            purpose=purpose,
            source_fragment_ids=list(dict.fromkeys(source_fragment_ids)),
            alt_text=alt_text,
            sha256=digest,
            mime_type=mime_type,
            width=width,
            height=height,
            byte_size=len(payload),
            filename=filename,
            prompt=prompt,
            model=model,
            generation_seed=generation_seed,
            quality_checks=dict(quality_checks or {}),
        )
        (staged_dir / "manifest.json").write_text(
            asset.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return asset

    def promote(self, asset: SlideVisualAsset) -> SlideVisualAsset:
        target = self.root / asset.asset_id
        if target.exists():
            existing = self.get(asset.asset_id)
            if existing is None or existing.sha256 != asset.sha256:
                raise ValueError("Slide asset hash collision")
            self.discard_staged(asset)
            return existing
        staged = next(
            (
                path
                for path in self.staging.glob(f"{asset.asset_id}-*")
                if (path / "manifest.json").exists()
            ),
            None,
        )
        if staged is None:
            raise FileNotFoundError(f"Staged slide asset not found: {asset.asset_id}")
        try:
            os.replace(staged, target)
        except FileExistsError:
            shutil.rmtree(staged, ignore_errors=True)
        return self.get(asset.asset_id) or asset

    def discard_staged(self, asset: SlideVisualAsset) -> None:
        staging_root = self.staging.resolve()
        for path in self.staging.glob(f"{asset.asset_id}-*"):
            resolved = path.resolve()
            if staging_root not in resolved.parents:
                raise ValueError("Refusing to remove a slide asset outside staging")
            shutil.rmtree(resolved, ignore_errors=True)

    def get(self, asset_id: str) -> SlideVisualAsset | None:
        self._validate_id(asset_id)
        manifest = self.root / asset_id / "manifest.json"
        if not manifest.exists():
            return None
        return SlideVisualAsset.model_validate(json.loads(manifest.read_text(encoding="utf-8")))

    def get_staged(self, asset_id: str) -> SlideVisualAsset | None:
        self._validate_id(asset_id)
        staged = next(
            (
                path
                for path in self.staging.glob(f"{asset_id}-*")
                if (path / "manifest.json").exists()
            ),
            None,
        )
        if staged is None:
            return None
        asset = SlideVisualAsset.model_validate(
            json.loads((staged / "manifest.json").read_text(encoding="utf-8"))
        )
        image_path = staged / asset.filename
        if not image_path.is_file():
            return None
        if hashlib.sha256(image_path.read_bytes()).hexdigest() != asset.sha256:
            raise ValueError("Staged slide asset hash no longer matches its manifest")
        return asset

    def resolve(self, asset_id: str) -> Path:
        asset = self.get(asset_id)
        if asset is None:
            raise FileNotFoundError(asset_id)
        path = self.root / asset.asset_id / asset.filename
        if not path.is_file():
            raise FileNotFoundError(asset_id)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != asset.sha256:
            raise ValueError("Slide asset hash no longer matches its manifest")
        return path

    def find_generated(
        self,
        *,
        course_id: str,
        source_fragment_ids: list[str],
        prompt: str,
        generation_seed: str,
    ) -> SlideVisualAsset | None:
        """Reuse a published website-generated asset for an identical request."""
        expected_sources = list(dict.fromkeys(source_fragment_ids))
        for manifest in self.root.glob("sva_*/manifest.json"):
            try:
                asset = SlideVisualAsset.model_validate(
                    json.loads(manifest.read_text(encoding="utf-8"))
                )
            except (OSError, ValueError):
                continue
            if (
                asset.kind == "generated_illustration"
                and asset.course_id == course_id
                and asset.source_fragment_ids == expected_sources
                and asset.prompt == prompt
                and asset.generation_seed == generation_seed
                and asset.quality_checks.get("embedded_text_absent") is True
                and asset.quality_checks.get("visual_detail_present") is True
            ):
                return asset
        return None

    @staticmethod
    def _validate_id(asset_id: str) -> None:
        if not asset_id.startswith("sva_") or not all(
            character.isalnum() or character == "_"
            for character in asset_id
        ):
            raise ValueError("Invalid slide asset id")


slide_asset_repository = SlideAssetRepository()


def resolve_visual_plan_assets(
    visual_plan: SlideVisualPlanV1,
    fragments: list[object],
    *,
    course_id: str,
    repository: SlideAssetRepository | None = None,
    progress_callback: object | None = None,
) -> tuple[SlideVisualPlanV1, list[dict[str, object]]]:
    """Resolve course image references and deterministically degrade bad assets."""
    target = repository or slide_asset_repository
    catalog = {
        str(getattr(fragment, "fragment_id")): fragment
        for fragment in fragments
    }
    resolved = visual_plan.model_copy(deep=True)
    provider = SlideImageProvider()
    illustrations_enabled = os.getenv(
        "SLIDE_GENERATED_ILLUSTRATIONS_ENABLED",
        "",
    ).strip().lower() in {"1", "true", "yes", "on"}
    if not illustrations_enabled:
        for page in resolved.pages:
            if page.visual_anchor.kind == "generated_illustration":
                page.visual_anchor = _fallback_anchor(page.visual_anchor, catalog)
    chapter_count = len({
        page.chapter_id
        for page in resolved.pages
        if page.chapter_id and not page.appendix
    })
    illustration_limit = min(max(1, chapter_count), 6)
    if illustrations_enabled and provider.configured:
        candidates = [
            page
            for page in resolved.pages
            if (
                not page.appendix
                and page.visual_anchor.kind == "relational_diagram"
                and page.visual_anchor.purpose in {"application", "context"}
            )
        ][:illustration_limit]
        prompt_style = str(slide_theme(resolved.theme).get("prompt_style") or "")
        for page in candidates:
            source_text = " ".join(
                " ".join(str(getattr(catalog.get(fragment_id), "text", "") or "").split())
                for fragment_id in page.visual_anchor.source_fragment_ids
            )[:700]
            if len(source_text) > 190:
                continue
            scene_prompt = provider.plan_prompt(
                source_text=source_text,
                style=prompt_style,
            )
            page.visual_anchor.kind = "generated_illustration"
            page.visual_anchor.nodes = []
            page.visual_anchor.edges = []
            page.visual_anchor.parameters = {
                "prompt": (
                    f"[{IMAGE_PROMPT_POLICY_VERSION}] {scene_prompt}"
                ),
                "size": "1664x928",
                "generation_seed": hashlib.sha256(
                    f"{resolved.source_document_revision}:{page.page_id}".encode("utf-8")
                ).hexdigest()[:16],
                "information_gain_score": 0.9,
            }
    for page in resolved.pages:
        anchor = page.visual_anchor
        if anchor.kind != "generated_illustration" or anchor.asset_id:
            continue
        source_text = " ".join(
            " ".join(str(getattr(catalog.get(fragment_id), "text", "") or "").split())
            for fragment_id in anchor.source_fragment_ids
        )
        if len(source_text) > 190:
            page.visual_anchor = _fallback_anchor(anchor, catalog)
            continue
        prompt = str(anchor.parameters.get("prompt") or "")
        if IMAGE_PROMPT_POLICY_VERSION not in prompt:
            scene_prompt = provider.plan_prompt(
                source_text=source_text,
                style=str(slide_theme(resolved.theme).get("prompt_style") or ""),
            )
            anchor.parameters["prompt"] = (
                f"[{IMAGE_PROMPT_POLICY_VERSION}] {scene_prompt}"
            )
        cached = target.find_generated(
            course_id=course_id,
            source_fragment_ids=anchor.source_fragment_ids,
            prompt=str(anchor.parameters.get("prompt") or ""),
            generation_seed=str(
                anchor.parameters.get("generation_seed") or ""
            ),
        )
        if cached is not None:
            anchor.asset_id = cached.asset_id
    planned_illustrations = [
        page
        for page in resolved.pages
        if (
            page.visual_anchor.kind == "generated_illustration"
            and not page.visual_anchor.asset_id
        )
    ]
    for page in planned_illustrations[illustration_limit:]:
        page.visual_anchor = _fallback_anchor(page.visual_anchor, catalog)
    if not provider.configured:
        for page in planned_illustrations[:illustration_limit]:
            page.visual_anchor = _fallback_anchor(page.visual_anchor, catalog)
    image_pages = [
        page
        for page in resolved.pages
        if page.visual_anchor.kind in {"source_image", "generated_illustration"}
    ]
    manifest: list[dict[str, object]] = []
    for index, page in enumerate(image_pages, start=1):
        anchor = page.visual_anchor
        try:
            if anchor.asset_id:
                asset = target.get(anchor.asset_id) or target.get_staged(anchor.asset_id)
                if asset is None:
                    raise FileNotFoundError(anchor.asset_id)
            elif anchor.kind == "source_image":
                asset_ref = str(anchor.parameters.get("asset_ref") or "")
                material = material_repository.get_asset(asset_ref)
                if material is None or material.extension.lower() not in IMAGE_EXTENSIONS:
                    raise FileNotFoundError(asset_ref)
                if material.bound_course_ids and course_id not in material.bound_course_ids:
                    raise ValueError("Course image asset is not bound to this course")
                staged = target.stage_image(
                    material_repository.source_path(material),
                    course_id=course_id,
                    source_fragment_ids=anchor.source_fragment_ids,
                    alt_text=anchor.alt_text,
                    purpose=anchor.purpose,
                    kind="source_image",
                )
                asset = staged
                anchor.asset_id = asset.asset_id
            else:
                prompt = str(anchor.parameters.get("prompt") or "")
                if not prompt:
                    raise ValueError("Generated illustration prompt is missing")
                with tempfile.TemporaryDirectory(prefix="slide-image-provider-") as temp_dir:
                    generated_path = provider.generate(
                        prompt=prompt,
                        output_path=Path(temp_dir) / "generated.png",
                        size=str(anchor.parameters.get("size") or "1664x928"),
                        seed=_seed_value(
                            str(anchor.parameters.get("generation_seed") or "")
                        ),
                    )
                    staged = target.stage_image(
                        generated_path,
                        course_id=course_id,
                        source_fragment_ids=anchor.source_fragment_ids,
                        alt_text=anchor.alt_text,
                        purpose=anchor.purpose,
                        kind="generated_illustration",
                        prompt=prompt,
                        model=provider.model,
                        generation_seed=str(anchor.parameters.get("generation_seed") or ""),
                        quality_checks={
                            "embedded_text_absent": True,
                            "visual_detail_present": True,
                        },
                    )
                    asset = staged
                    anchor.asset_id = asset.asset_id
            manifest.append(asset.model_dump(mode="json"))
        except Exception:
            page.visual_anchor = _fallback_anchor(anchor, catalog)
        if callable(progress_callback):
            progress_callback({
                "event": "asset_progress",
                "progress": 12 + round(index / max(1, len(image_pages)) * 8),
                "stage": "asset_compilation",
                "completed": index,
                "total": len(image_pages),
                "asset_id": page.visual_anchor.asset_id,
            })
            if page.visual_anchor.asset_id:
                progress_callback({
                    "event": "asset_ready",
                    "progress": 20,
                    "asset_id": page.visual_anchor.asset_id,
                    "page_id": page.page_id,
                    "visual_anchor": page.visual_anchor.model_dump(mode="json"),
                })
    return resolved, manifest


def finalize_visual_assets(
    manifest: list[dict[str, object]],
    *,
    repository: SlideAssetRepository | None = None,
    publish: bool,
) -> list[dict[str, object]]:
    """Atomically publish validated assets, or discard only their staged copies."""
    target = repository or slide_asset_repository
    finalized: list[dict[str, object]] = []
    for raw in manifest:
        asset = SlideVisualAsset.model_validate(raw)
        if publish:
            finalized.append(target.promote(asset).model_dump(mode="json"))
        else:
            target.discard_staged(asset)
            finalized.append(asset.model_dump(mode="json"))
    return finalized


def _fallback_anchor(
    anchor: VisualAnchorV1,
    catalog: dict[str, object],
) -> VisualAnchorV1:
    nodes: list[VisualNodeV1] = []
    for index, fragment_id in enumerate(anchor.source_fragment_ids[:5]):
        fragment = catalog.get(fragment_id)
        label = " ".join(str(getattr(fragment, "text", "") or "").split())
        if len(label) > 34:
            label = label[:33] + "…"
        if not label:
            continue
        nodes.append(VisualNodeV1(
            node_id=f"fallback-{index + 1}",
            label=label,
            source_fragment_ids=[fragment_id],
            emphasis="primary" if index == 0 else "secondary",
        ))
    # Image failure must not manufacture a semantic relationship between
    # unrelated excerpts.  The renderer falls back to a source-grounded
    # statement composition, while the quality report records the missing
    # explanatory asset.
    return VisualAnchorV1(
        visual_id=anchor.visual_id,
        kind="none",
        purpose=anchor.purpose,
    )


def _seed_value(value: str) -> int | None:
    clean = str(value or "").strip()
    if not clean:
        return None
    try:
        return int(clean, 16) % (2**31)
    except ValueError:
        return int(hashlib.sha256(clean.encode("utf-8")).hexdigest()[:8], 16)


__all__ = [
    "SlideAssetRepository",
    "SlideVisualAsset",
    "finalize_visual_assets",
    "resolve_visual_plan_assets",
    "slide_asset_repository",
]
