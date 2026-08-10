"""Versioned, user-scoped storage for PowerPoint visual template packs.

The public workflow intentionally accepts a reference PPTX or a compact brand
brief.  Users never need to author the internal manifest directly.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import shutil
import uuid
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from slide_theme import load_slide_theme_pack
from storage import DATA_DIR


MAX_REFERENCE_BYTES = 25 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 2_000
MAX_UNCOMPRESSED_BYTES = 160 * 1024 * 1024
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
PRESENTATION_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
REPRESENTATIVE_ROLES = ("cover", "chapter", "content", "practice", "evidence", "recap")
PREVIEW_ROLES = ("cover", "chapter", "objectives", "definition", "process", "practice", "evidence", "recap")


class TemplatePackError(ValueError):
    """Raised when an uploaded template or manifest is unsafe or invalid."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _safe_name(value: str, *, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > 160:
        raise TemplatePackError(f"Invalid {field}")
    return normalized


def _safe_identifier(value: str, *, field: str) -> str:
    normalized = str(value or "").strip()
    if not SAFE_IDENTIFIER.fullmatch(normalized):
        raise TemplatePackError(f"Invalid {field}")
    return normalized


def _normalize_brand(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise TemplatePackError("Brand fields must be an object")
    allowed = {
        "primary_color",
        "secondary_color",
        "accent_color",
        "title_font",
        "body_font",
        "font_name",
        "header_text",
        "footer_text",
        "copyright_text",
        "organization_name",
        "logo_position",
    }
    unknown = set(value) - allowed
    if unknown:
        raise TemplatePackError(f"Unsupported brand fields: {', '.join(sorted(unknown))}")
    normalized: dict[str, str] = {}
    for key, raw_value in value.items():
        if not isinstance(raw_value, str):
            raise TemplatePackError(f"Brand field {key} must be text")
        text = raw_value.strip()
        if len(text) > 500:
            raise TemplatePackError(f"Brand field {key} is too long")
        if key.endswith("_color") and text:
            color = text.lstrip("#")
            if not re.fullmatch(r"[0-9A-Fa-f]{6}", color):
                raise TemplatePackError(f"Brand field {key} must be a six-digit color")
            text = f"#{color.upper()}"
        normalized[key] = text
    return normalized


def _updated_extracted_style(current: dict[str, Any], value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TemplatePackError("Extracted style changes must be an object")
    allowed = {"colors", "title_font", "body_font"}
    unknown = set(value) - allowed
    if unknown:
        raise TemplatePackError(f"Unsupported extracted style fields: {', '.join(sorted(unknown))}")
    updated = deepcopy(current)
    if "colors" in value:
        if not isinstance(value["colors"], dict):
            raise TemplatePackError("Extracted colors must be an object")
        colors: dict[str, str] = {}
        for key, raw_color in value["colors"].items():
            color = str(raw_color or "").strip().lstrip("#")
            if not re.fullmatch(r"[0-9A-Fa-f]{6}", color):
                raise TemplatePackError("Extracted colors must use six-digit hex values")
            colors[str(key)[:40]] = color.upper()
        updated["colors"] = colors
    for key in ("title_font", "body_font"):
        if key not in value:
            continue
        font = str(value[key] or "").strip()
        if len(font) > 160:
            raise TemplatePackError(f"{key} is too long")
        updated[key] = font
    return updated


def _validated_representative_pages(value: Any, slide_count: int) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) != len(REPRESENTATIVE_ROLES):
        raise TemplatePackError("Representative pages must contain all six semantic roles")
    maximum = max(1, int(slide_count or 0))
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise TemplatePackError("Representative page entries must be objects")
        role = str(item.get("role") or "")
        if role not in REPRESENTATIVE_ROLES or role in seen:
            raise TemplatePackError("Representative page roles are invalid or duplicated")
        try:
            slide_number = int(item.get("slide_number"))
        except (TypeError, ValueError) as exc:
            raise TemplatePackError("Representative slide numbers must be integers") from exc
        if slide_number < 1 or slide_number > maximum:
            raise TemplatePackError("Representative slide number is out of range")
        seen.add(role)
        normalized.append({
            "role": role,
            "slide_number": slide_number,
            "confirmed": bool(item.get("confirmed")),
        })
    return sorted(normalized, key=lambda item: REPRESENTATIVE_ROLES.index(item["role"]))


def _asset_id(role: str) -> str:
    return f"asset-{role}-{uuid.uuid4().hex[:12]}"


def template_pack_variant_key(
    mode: str,
    theme: str,
    pack_id: str,
    version: int | str,
) -> str:
    """Create the cache/representation key for an immutable pack snapshot."""
    safe_pack_id = _safe_identifier(pack_id, field="pack id")
    resolved_version = int(version)
    if resolved_version < 1:
        raise TemplatePackError("Template pack version must be positive")
    return f"{mode}:{theme}:template:{safe_pack_id}@{resolved_version}"


def _compiled_theme(
    base_theme: str,
    extracted_style: dict[str, Any],
    brand: dict[str, Any],
    label: str,
) -> dict[str, Any]:
    theme = deepcopy((load_slide_theme_pack().get("themes") or {})[base_theme])
    theme["label"] = _safe_name(label, field="name")
    colors = dict(extracted_style.get("colors") or {})
    primary = str(brand.get("primary_color") or "").strip().lstrip("#")
    if re.fullmatch(r"[0-9A-Fa-f]{6}", primary):
        colors["accent1"] = primary.upper()
    overrides = {
        "title": colors.get("dk1"),
        "accent": colors.get("accent1"),
        "green": colors.get("accent2"),
        "amber": colors.get("accent3"),
    }
    for key, value in overrides.items():
        if value and re.fullmatch(r"[0-9A-Fa-f]{6}", value):
            theme[key] = value.upper()
    title_font = str(
        brand.get("title_font")
        or brand.get("font_name")
        or extracted_style.get("title_font")
        or ""
    ).strip()
    body_font = str(
        brand.get("body_font")
        or brand.get("font_name")
        or extracted_style.get("body_font")
        or ""
    ).strip()
    if title_font:
        theme["title_font"] = title_font
    if body_font:
        theme["body_font"] = body_font
    theme["template"] = {
        **(theme.get("template") or {}),
        "base_theme": base_theme,
        "customized": True,
        "accent_rail_owner": "card-shell",
    }
    return theme


def _extract_reference_style(payload: bytes, filename: str) -> dict[str, Any]:
    if not filename.lower().endswith(".pptx"):
        raise TemplatePackError("Reference presentation must be a .pptx file")
    if not payload or len(payload) > MAX_REFERENCE_BYTES:
        raise TemplatePackError("Reference presentation is empty or too large")
    try:
        archive = zipfile.ZipFile(BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise TemplatePackError("Reference presentation is not a valid PPTX archive") from exc
    with archive:
        entries = archive.infolist()
        if len(entries) > MAX_ARCHIVE_ENTRIES:
            raise TemplatePackError("Reference presentation contains too many files")
        if sum(item.file_size for item in entries) > MAX_UNCOMPRESSED_BYTES:
            raise TemplatePackError("Reference presentation expands beyond the safe limit")
        lowered = {item.filename.lower() for item in entries}
        if any(name.endswith("vbaproject.bin") for name in lowered):
            raise TemplatePackError("Macro-enabled presentations are not supported")
        if "ppt/presentation.xml" not in lowered:
            raise TemplatePackError("Reference presentation is missing presentation.xml")

        try:
            presentation_name = next(
                item.filename for item in entries if item.filename.lower() == "ppt/presentation.xml"
            )
            presentation = ElementTree.fromstring(archive.read(presentation_name))
        except (ElementTree.ParseError, KeyError, StopIteration) as exc:
            raise TemplatePackError("Reference presentation metadata is malformed") from exc

        slide_size = presentation.find(f"{{{PRESENTATION_NS}}}sldSz")
        width = int(slide_size.get("cx", "12192000") if slide_size is not None else "12192000")
        height = int(slide_size.get("cy", "6858000") if slide_size is not None else "6858000")
        ratio = width / max(height, 1)
        aspect_ratio = "16:9" if abs(ratio - 16 / 9) < abs(ratio - 4 / 3) else "4:3"
        slide_ids = presentation.findall(
            f".//{{{PRESENTATION_NS}}}sldId"
        )
        slide_count = max(1, len(slide_ids))

        colors: dict[str, str] = {}
        title_font = ""
        body_font = ""
        theme_names = sorted(
            item.filename
            for item in entries
            if item.filename.lower().startswith("ppt/theme/theme")
            and item.filename.lower().endswith(".xml")
        )
        if theme_names:
            try:
                theme_root = ElementTree.fromstring(archive.read(theme_names[0]))
                scheme = theme_root.find(f".//{{{DRAWING_NS}}}clrScheme")
                if scheme is not None:
                    for color_node in list(scheme):
                        child = next(iter(color_node), None)
                        value = child.get("val", "") if child is not None else ""
                        if value and len(value) in {6, 8}:
                            colors[color_node.tag.rsplit("}", 1)[-1]] = value.upper()
                major = theme_root.find(f".//{{{DRAWING_NS}}}majorFont/{{{DRAWING_NS}}}latin")
                minor = theme_root.find(f".//{{{DRAWING_NS}}}minorFont/{{{DRAWING_NS}}}latin")
                title_font = major.get("typeface", "") if major is not None else ""
                body_font = minor.get("typeface", "") if minor is not None else ""
            except ElementTree.ParseError:
                pass

        slide_names = [
            item.filename
            for item in entries
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", item.filename.lower())
            and item.file_size <= 2 * 1024 * 1024
        ]
        slide_names.sort(
            key=lambda value: int(re.search(r"slide(\d+)\.xml$", value.lower()).group(1))
        )
        slide_profiles: list[dict[str, Any]] = []
        background_candidates: list[dict[str, Any]] = []
        text_box_total = 0
        text_box_max = 0
        for slide_number, slide_name in enumerate(slide_names[:200], start=1):
            try:
                slide_root = ElementTree.fromstring(archive.read(slide_name))
            except (ElementTree.ParseError, KeyError):
                continue
            text_shapes = [
                shape
                for shape in slide_root.findall(f".//{{{PRESENTATION_NS}}}sp")
                if shape.find(f"{{{PRESENTATION_NS}}}txBody") is not None
            ]
            pictures = slide_root.findall(f".//{{{PRESENTATION_NS}}}pic")
            tables = slide_root.findall(f".//{{{DRAWING_NS}}}tbl")
            shape_frames: list[dict[str, float]] = []
            for shape in text_shapes[:12]:
                transform = shape.find(f".//{{{DRAWING_NS}}}xfrm")
                offset = (
                    transform.find(f"{{{DRAWING_NS}}}off")
                    if transform is not None
                    else None
                )
                extent = (
                    transform.find(f"{{{DRAWING_NS}}}ext")
                    if transform is not None
                    else None
                )
                if offset is None or extent is None:
                    continue
                shape_frames.append({
                    "x": round(int(offset.get("x", "0")) / max(width, 1), 4),
                    "y": round(int(offset.get("y", "0")) / max(height, 1), 4),
                    "width": round(int(extent.get("cx", "0")) / max(width, 1), 4),
                    "height": round(int(extent.get("cy", "0")) / max(height, 1), 4),
                })
            text_box_count = len(text_shapes)
            text_box_total += text_box_count
            text_box_max = max(text_box_max, text_box_count)
            layout_hint = (
                "visual-led"
                if pictures
                else "multi-card"
                if text_box_count >= 3
                else "editorial-body"
            )
            slide_profiles.append({
                "slide_number": slide_number,
                "text_box_count": text_box_count,
                "picture_count": len(pictures),
                "table_count": len(tables),
                "layout_hint": layout_hint,
                "text_box_frames": shape_frames,
            })
            background = slide_root.find(f".//{{{PRESENTATION_NS}}}bg")
            if background is not None:
                solid = background.find(f".//{{{DRAWING_NS}}}srgbClr")
                scheme = background.find(f".//{{{DRAWING_NS}}}schemeClr")
                color = (
                    str(solid.get("val") or "").upper()
                    if solid is not None
                    else ""
                )
                scheme_name = str(scheme.get("val") or "") if scheme is not None else ""
                if color or scheme_name:
                    background_candidates.append({
                        "slide_number": slide_number,
                        "color": color,
                        "scheme": scheme_name,
                    })
        media_inventory = [
            {
                "filename": Path(item.filename).name,
                "mime_type": mimetypes.guess_type(item.filename)[0] or "application/octet-stream",
                "size": item.file_size,
            }
            for item in entries
            if item.filename.lower().startswith("ppt/media/")
            and not item.is_dir()
        ][:100]

    return {
        "aspect_ratio": aspect_ratio,
        "source_aspect_ratio": round(ratio, 4),
        "slide_count": slide_count,
        "colors": colors,
        "title_font": title_font,
        "body_font": body_font,
        "background_candidates": background_candidates,
        "slide_profiles": slide_profiles,
        "media_inventory": media_inventory,
        "text_box_structure": {
            "total": text_box_total,
            "maximum_per_slide": text_box_max,
            "profiled_slides": len(slide_profiles),
        },
        "requires_widescreen_confirmation": aspect_ratio == "4:3",
    }


def _default_extracted_style(brand: dict[str, Any]) -> dict[str, Any]:
    colors: dict[str, str] = {}
    for source, destination in (
        ("primary_color", "accent1"),
        ("secondary_color", "accent2"),
        ("accent_color", "accent3"),
    ):
        value = str(brand.get(source) or "").strip().lstrip("#")
        if re.fullmatch(r"[0-9A-Fa-f]{6}", value):
            colors[destination] = value.upper()
    return {
        "aspect_ratio": "16:9",
        "source_aspect_ratio": round(16 / 9, 4),
        "slide_count": 0,
        "colors": colors,
        "title_font": str(brand.get("title_font") or brand.get("font_name") or ""),
        "body_font": str(brand.get("body_font") or brand.get("font_name") or ""),
        "background_candidates": [],
        "slide_profiles": [],
        "media_inventory": [],
        "text_box_structure": {
            "total": 0,
            "maximum_per_slide": 0,
            "profiled_slides": 0,
        },
        "requires_widescreen_confirmation": False,
    }


def _representative_pages(slide_count: int) -> list[dict[str, Any]]:
    last_index = max(1, slide_count)
    if last_index == 1:
        indices = [1] * len(REPRESENTATIVE_ROLES)
    else:
        indices = [
            1 + round(position * (last_index - 1) / (len(REPRESENTATIVE_ROLES) - 1))
            for position in range(len(REPRESENTATIVE_ROLES))
        ]
    return [
        {"role": role, "slide_number": indices[index], "confirmed": False}
        for index, role in enumerate(REPRESENTATIVE_ROLES)
    ]


def _preview_slides() -> list[dict[str, Any]]:
    return [
        {"role": role, "status": "ready", "thumbnail_asset_id": ""}
        for role in PREVIEW_ROLES
    ]


class PptTemplatePackRepository:
    """Filesystem repository with immutable published version snapshots."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or Path(DATA_DIR) / "ppt_template_packs").resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _pack_dir(self, pack_id: str) -> Path:
        safe_id = _safe_identifier(pack_id, field="pack id")
        candidate = (self.root / safe_id).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise TemplatePackError("Invalid pack path") from exc
        return candidate

    def _manifest_path(self, pack_id: str) -> Path:
        return self._pack_dir(pack_id) / "draft.json"

    @staticmethod
    def _public(manifest: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(manifest)
        result.pop("owner_id", None)
        for asset in result.get("assets") or []:
            asset.pop("stored_name", None)
        return result

    def _read_manifest(self, pack_id: str) -> dict[str, Any]:
        path = self._manifest_path(pack_id)
        if not path.is_file():
            raise FileNotFoundError(pack_id)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise TemplatePackError("Template pack manifest is unreadable") from exc

    def load_owned(self, pack_id: str, owner_id: str) -> dict[str, Any]:
        manifest = self._read_manifest(pack_id)
        if manifest.get("owner_id") != owner_id:
            raise FileNotFoundError(pack_id)
        return manifest

    def create_draft(
        self,
        *,
        owner_id: str,
        name: str,
        base_theme: str,
        reference_pptx: bytes | None,
        reference_filename: str,
        brand: dict[str, Any] | None,
        extra_assets: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        owner = _safe_name(owner_id, field="owner id")
        display_name = _safe_name(name, field="name")
        themes = load_slide_theme_pack().get("themes") or {}
        if base_theme not in themes:
            raise TemplatePackError("Unknown base theme")
        normalized_brand = _normalize_brand(brand or {})
        extracted = (
            _extract_reference_style(reference_pptx, reference_filename)
            if reference_pptx is not None
            else _default_extracted_style(normalized_brand)
        )
        pack_id = f"pptp-{uuid.uuid4().hex}"
        pack_dir = self._pack_dir(pack_id)
        asset_dir = pack_dir / "draft-assets"
        asset_dir.mkdir(parents=True, exist_ok=False)
        assets: list[dict[str, Any]] = []

        def store_asset(role: str, filename: str, payload: bytes, mime_type: str = "") -> None:
            original_name = Path(filename).name or f"{role}.bin"
            extension = Path(original_name).suffix.lower()[:12]
            current_id = _asset_id(role)
            stored_name = f"{current_id}{extension}"
            target = asset_dir / stored_name
            target.write_bytes(payload)
            assets.append(
                {
                    "asset_id": current_id,
                    "role": role,
                    "filename": original_name,
                    "stored_name": stored_name,
                    "mime_type": mime_type or mimetypes.guess_type(original_name)[0] or "application/octet-stream",
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                }
            )

        if reference_pptx is not None:
            store_asset(
                "reference_pptx",
                reference_filename or "reference.pptx",
                reference_pptx,
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
        for asset in extra_assets or []:
            payload = asset.get("payload")
            if not isinstance(payload, bytes) or not payload:
                continue
            store_asset(
                str(asset.get("role") or "reference"),
                str(asset.get("filename") or "asset.bin"),
                payload,
                str(asset.get("mime_type") or ""),
            )

        timestamp = _utc_now()
        manifest: dict[str, Any] = {
            "schema_version": "ppt_template_pack_manifest_v1",
            "pack_id": pack_id,
            "owner_id": owner,
            "name": display_name,
            "status": "draft",
            "base_theme": base_theme,
            "brand": normalized_brand,
            "extracted_style": extracted,
            "compiled_theme": _compiled_theme(
                base_theme,
                extracted,
                normalized_brand,
                display_name,
            ),
            "representative_pages": _representative_pages(extracted["slide_count"]),
            "preview_slides": _preview_slides(),
            "semantic_page_mappings": deepcopy(themes[base_theme].get("semantic_layout_weights") or {}),
            "text_box_styles": deepcopy(themes[base_theme].get("text_box_styles") or {}),
            "assets": assets,
            "latest_version": 0,
            "hidden": False,
            "created_at": timestamp,
            "updated_at": timestamp,
            "compile": {"status": "ready", "progress": 100, "errors": []},
        }
        _atomic_json(self._manifest_path(pack_id), manifest)
        return self._public(manifest)

    def update_draft(
        self,
        pack_id: str,
        owner_id: str,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        manifest = self.load_owned(pack_id, owner_id)
        allowed = {"name", "brand", "representative_pages", "extracted_style"}
        unknown = set(changes) - allowed
        if unknown:
            raise TemplatePackError(f"Unsupported draft fields: {', '.join(sorted(unknown))}")
        if "name" in changes:
            manifest["name"] = _safe_name(str(changes["name"]), field="name")
        if "brand" in changes:
            manifest["brand"] = _normalize_brand(changes["brand"])
        if "extracted_style" in changes:
            manifest["extracted_style"] = _updated_extracted_style(
                dict(manifest.get("extracted_style") or {}),
                changes["extracted_style"],
            )
        if "representative_pages" in changes:
            manifest["representative_pages"] = _validated_representative_pages(
                changes["representative_pages"],
                int((manifest.get("extracted_style") or {}).get("slide_count") or 0),
            )
        if {"name", "brand", "extracted_style"}.intersection(changes):
            manifest["compiled_theme"] = _compiled_theme(
                str(manifest["base_theme"]),
                dict(manifest.get("extracted_style") or {}),
                dict(manifest.get("brand") or {}),
                str(manifest["name"]),
            )
        manifest["updated_at"] = _utc_now()
        _atomic_json(self._manifest_path(pack_id), manifest)
        return self._public(manifest)

    def publish(self, pack_id: str, owner_id: str) -> dict[str, Any]:
        manifest = self.load_owned(pack_id, owner_id)
        version = int(manifest.get("latest_version") or 0) + 1
        version_dir = self._pack_dir(pack_id) / "versions" / str(version)
        if version_dir.exists():
            raise TemplatePackError("Template version already exists")
        asset_dir = version_dir / "assets"
        asset_dir.mkdir(parents=True, exist_ok=False)
        for asset in manifest.get("assets") or []:
            source = self._pack_dir(pack_id) / "draft-assets" / asset["stored_name"]
            if source.is_file():
                shutil.copy2(source, asset_dir / asset["stored_name"])

        snapshot = deepcopy(manifest)
        snapshot["status"] = "published"
        snapshot["version"] = version
        snapshot["published_at"] = _utc_now()
        snapshot.pop("latest_version", None)
        snapshot.pop("hidden", None)
        snapshot["manifest_digest"] = _canonical_digest(
            {key: value for key, value in snapshot.items() if key != "manifest_digest"}
        )
        _atomic_json(version_dir / "manifest.json", snapshot)
        manifest["latest_version"] = version
        manifest["status"] = "published"
        manifest["updated_at"] = snapshot["published_at"]
        manifest["manifest_digest"] = snapshot["manifest_digest"]
        _atomic_json(self._manifest_path(pack_id), manifest)
        return self._public(snapshot)

    def resolve_version(
        self,
        pack_id: str,
        version: int | str | None,
        owner_id: str,
    ) -> dict[str, Any]:
        manifest = self.load_owned(pack_id, owner_id)
        resolved_version = int(version or manifest.get("latest_version") or 0)
        if resolved_version < 1:
            raise FileNotFoundError(f"{pack_id}@{resolved_version}")
        path = self._pack_dir(pack_id) / "versions" / str(resolved_version) / "manifest.json"
        if not path.is_file():
            raise FileNotFoundError(f"{pack_id}@{resolved_version}")
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        if snapshot.get("owner_id") != owner_id:
            raise FileNotFoundError(pack_id)
        return self._public(snapshot)

    def list_for_owner(self, owner_id: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for path in self.root.glob("pptp-*/draft.json"):
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if manifest.get("owner_id") == owner_id and not manifest.get("hidden"):
                result.append(self._public(manifest))
        return sorted(result, key=lambda item: str(item.get("updated_at") or ""), reverse=True)

    def list_builtin(self) -> list[dict[str, Any]]:
        pack = load_slide_theme_pack()
        version = str(pack.get("version") or "")
        return [
            {
                "pack_id": theme_id,
                "name": theme.get("label") or theme.get("name") or theme_id,
                "status": "builtin",
                "version": version,
                "base_theme": theme_id,
                "preview": (theme.get("template") or {}).get("preview_path", ""),
            }
            for theme_id, theme in (pack.get("themes") or {}).items()
        ]

    def soft_delete(self, pack_id: str, owner_id: str) -> None:
        manifest = self.load_owned(pack_id, owner_id)
        manifest["hidden"] = True
        manifest["updated_at"] = _utc_now()
        _atomic_json(self._manifest_path(pack_id), manifest)

    def compile_status(self, pack_id: str, owner_id: str) -> dict[str, Any]:
        manifest = self.load_owned(pack_id, owner_id)
        return {
            "pack_id": pack_id,
            **deepcopy(manifest.get("compile") or {"status": "ready", "progress": 100, "errors": []}),
        }

    def asset_path(
        self,
        pack_id: str,
        asset_id: str,
        owner_id: str,
        *,
        version: int | str | None = None,
    ) -> tuple[Path, dict[str, Any]]:
        _safe_identifier(asset_id, field="asset id")
        manifest = self.load_owned(pack_id, owner_id)
        if version is None and manifest.get("latest_version"):
            version = int(manifest["latest_version"])
        if version is not None:
            raw_path = self._pack_dir(pack_id) / "versions" / str(int(version)) / "manifest.json"
            if not raw_path.is_file():
                raise FileNotFoundError(asset_id)
            source_manifest = json.loads(raw_path.read_text(encoding="utf-8"))
            asset_root = raw_path.parent / "assets"
        else:
            source_manifest = manifest
            asset_root = self._pack_dir(pack_id) / "draft-assets"
        asset = next(
            (item for item in source_manifest.get("assets") or [] if item.get("asset_id") == asset_id),
            None,
        )
        if not asset:
            raise FileNotFoundError(asset_id)
        path = (asset_root / asset["stored_name"]).resolve()
        try:
            path.relative_to(asset_root.resolve())
        except ValueError as exc:
            raise FileNotFoundError(asset_id) from exc
        if not path.is_file():
            raise FileNotFoundError(asset_id)
        return path, deepcopy(asset)


ppt_template_pack_repository = PptTemplatePackRepository()


__all__ = [
    "PptTemplatePackRepository",
    "TemplatePackError",
    "template_pack_variant_key",
    "ppt_template_pack_repository",
]
