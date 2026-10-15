"""Immutable student copies of explicitly selected, confirmed PPT exports."""

from copy import deepcopy
import hashlib
from pathlib import Path
import os
import tempfile
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

from fastapi import HTTPException


def shareable_project(project, document):
    rendered = project.get("last_good_render") or {}
    revision = rendered.get("manuscript_revision")
    public_blocks = {b["block_id"]: b["internal_revision"] for b in document["blocks"]}
    sources = project.get("sources") or {}
    blocks = sources.get("blocks") or []
    lectures = sources.get("lectures") or []
    selected_ids = set(project.get("lesson_ids") or [])
    public_sections = {s["section_id"]: s for s in document["sections"]}
    scoped_sections = {
        s["section_id"]
        for s in document["sections"]
        if s["section_id"] in selected_ids or s.get("parent_section_id") in selected_ids
    }
    current_blocks = {
        b["block_id"]: b["internal_revision"] for b in document["blocks"] if b["section_id"] in scoped_sections
    }
    return bool(
        project.get("status") == "ready"
        and revision
        and revision
        == project.get("confirmed_revision")
        == (project.get("manuscript") or {}).get("manuscript_revision")
        and not sources.get("materials")
        and not project.get("asset_ids")
        and blocks
        and selected_ids
        and selected_ids == {s.get("lesson_id") for s in lectures}
        and all(public_sections.get(s.get("lesson_id"), {}).get("title") == s.get("title") for s in lectures)
        and {b.get("block_id"): b.get("revision") for b in blocks} == current_blocks
        and all(public_blocks.get(b.get("block_id")) == b.get("revision") and b.get("revision") for b in blocks)
    )


def public_ppt_options(course, document):
    return [
        {"project_id": key, "title": project["title"]}
        for key, project in (course.get("teacher_ppt_projects") or {}).items()
        if shareable_project(project, document)
    ]


def strip_private_ppt_parts(source: Path, destination: Path):
    """Remove speaker notes, comments and author metadata from the OOXML package."""

    def private(name):
        return name.startswith(
            ("ppt/notesSlides/", "ppt/notesMasters/", "ppt/comments/", "ppt/commentAuthors")
        ) or name in {"docProps/core.xml", "docProps/custom.xml"}

    with ZipFile(source) as incoming, ZipFile(destination, "w", ZIP_DEFLATED) as outgoing:
        for entry in incoming.infolist():
            if private(entry.filename):
                continue
            value = incoming.read(entry)
            if entry.filename == "ppt/presentation.xml":
                root = ET.fromstring(value)
                for child in list(root):
                    if child.tag.rsplit("}", 1)[-1] == "notesMasterIdLst":
                        root.remove(child)
                value = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            if entry.filename.endswith(".rels") or entry.filename == "[Content_Types].xml":
                root = ET.fromstring(value)
                for child in list(root):
                    kind = child.attrib.get("Type", "").rsplit("/", 1)[-1]
                    part = child.attrib.get("PartName", "").lstrip("/")
                    if kind in {
                        "notesSlide",
                        "notesMaster",
                        "comments",
                        "commentAuthors",
                        "core-properties",
                        "custom-properties",
                    } or private(part):
                        root.remove(child)
                value = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            outgoing.writestr(entry.filename, value)


def freeze_published_ppts(storage, course, document, project_ids):
    if not project_ids:
        return []
    if len(set(project_ids)) != len(project_ids):
        raise HTTPException(422, "PPT 选择重复")
    projects = course.get("teacher_ppt_projects") or {}
    root = Path(storage._data_dir) / "published_ppts"
    root.mkdir(parents=True, exist_ok=True)
    result = []
    from course_exchange import digest
    from slide_deck_v6_renderer import export_slide_deck_v6_pptx

    for project_id in project_ids:
        project = projects.get(project_id) or {}
        if not shareable_project(project, document):
            raise HTTPException(409, "所选 PPT 未完成、来源已变化或包含未公开来源，请刷新后重新选择")
        rendered = project["last_good_render"]
        # Export cache is bound to a frozen render, never to a mutable project id.
        snapshot = {**deepcopy(rendered["deck"]), "ppt_manuscript": deepcopy(rendered["ppt_manuscript"])}
        cache = root / ("render_" + digest(snapshot) + ".pptx")
        if not cache.exists():
            with tempfile.TemporaryDirectory(prefix=".publication-", dir=root) as temporary:
                source, cleaned = Path(temporary) / "original.pptx", Path(temporary) / "clean.pptx"
                try:
                    export_slide_deck_v6_pptx(snapshot, source)
                except (ValueError, RuntimeError) as exc:
                    raise HTTPException(422, "PPT 导出失败，已有发布版本已保留") from exc
                strip_private_ppt_parts(source, cleaned)
                os.replace(cleaned, cache)
        content = cache.read_bytes()
        if len(content) > 100 * 1024 * 1024:
            raise HTTPException(422, "PPT 成品超过发布大小限制")
        sha = hashlib.sha256(content).hexdigest()
        final = root / (sha + ".pptx")
        if not final.exists():
            with tempfile.NamedTemporaryFile(dir=root, delete=False) as output:
                temporary_path = Path(output.name)
                output.write(content)
            os.replace(temporary_path, final)
        result.append(
            {
                "asset_id": "ppt_" + sha[:32],
                "sha256": sha,
                "size_bytes": len(content),
                "filename": str(project["title"])[:180] + ".pptx",
            }
        )
    return result


def published_ppt_path(storage, manifest):
    sha = manifest["sha256"]
    import re

    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise HTTPException(503, "发布成品校验失败")
    path = Path(storage._data_dir) / "published_ppts" / (sha + ".pptx")
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != sha:
        raise HTTPException(503, "发布成品暂不可用")
    return path
