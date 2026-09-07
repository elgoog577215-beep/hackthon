"""Revision-scoped, bounded page previews without planning or file export."""
from collections import OrderedDict
from copy import deepcopy
from threading import RLock

from course_document import stable_hash
from course_presentation_graph import block_source_text
from ppt_teaching_manuscript import physical_pages, template_for_manuscript
from slide_deck_v6_models import V6BuildError

_cache = OrderedDict()
_lock = RLock()
PREVIEW_VERSION = "ppt_preview_v1"


def preview_manuscript(document, manuscript, *, actor, course_id, lesson_id, page_ids=None):
    template = template_for_manuscript(manuscript)
    from ppt_runtime_identity import tool_identity, file_digest
    runtime = tool_identity()
    for layout in template.layouts:
        if layout.execution and layout.execution.font_sha256 != runtime["font_sha256"]:
            raise V6BuildError(stage="preview", code="teaching_font_changed", message="预览字体版本已变化。")
    current = {b.block_id: b for b in document.blocks}
    if manuscript.source_document_revision != document.document_revision:
        raise V6BuildError(stage="preview", code="ppt_manuscript_source_revision_mismatch", message="讲义已变化，请同步受影响页面。")
    requested = set(page_ids or [manuscript.pages[0].page_id])
    known = {p.page_id for p in manuscript.pages}
    if requested - known:
        raise V6BuildError(stage="preview", code="ppt_preview_page_missing", message="所选页面已变化，请刷新内容稿。")
    if manuscript.teaching_content_contract_version != "page_teaching_v2":
        from course_presentation_graph import compile_course_presentation_graph
        from slide_deck_v6 import compile_slide_deck_v6_from_manuscript
        deck = compile_slide_deck_v6_from_manuscript(document, compile_course_presentation_graph(document, teaching_plan={}), manuscript, template)
        return {"schema_version": PREVIEW_VERSION, "manuscript_revision": manuscript.manuscript_revision,
            "source_script_revision_id": manuscript.source_script_revision_id,
            "manifest": [{"page_id": p.page_id, "title": p.title, "page_number": p.page_number, "physical_page_ids": [p.page_id]} for p in manuscript.pages],
            "deck": {"schema_version": "slide_deck_v6", "pages": [p.model_dump(mode="json") for p in deck.pages if p.page_id in requested]}, "page_count": manuscript.page_count}
    result, manifest = [], []
    ordinal = 0
    for page in manuscript.pages:
        ids = [f"{page.page_id}--{scene.state_id}" for scene in page.resolved_scenes]
        manifest.append({"page_id": page.page_id, "title": page.title, "page_number": page.page_number, "physical_page_ids": ids})
        if page.page_id not in requested:
            ordinal += len(ids)
            continue
        from slide_asset_repository import slide_asset_repository
        for binding in page.teaching.adopted_assets if page.teaching else []:
            if binding.course_id != course_id or file_digest(slide_asset_repository.resolve(binding.asset_id)) != binding.sha256:
                raise V6BuildError(stage="preview", code="teaching_asset_digest_mismatch", message="页面素材已变化。", page_id=page.page_id)
        for note in page.speaker_notes.source_blocks:
            source = current.get(note.block_id)
            if not source or source.internal_revision != note.block_revision or block_source_text(source) != note.full_text:
                raise V6BuildError(stage="preview", code="teaching_note_source_mismatch", message="本页讲义来源已变化。", page_id=page.page_id)
        key = stable_hash({"actor": actor, "course": course_id, "lesson": lesson_id,
            "page": page.model_dump(mode="json"), "template": template.template_digest,
            "preview": PREVIEW_VERSION, "runtime": runtime}, prefix="preview_")
        with _lock:
            cached = _cache.get(key)
            if cached is not None:
                _cache.move_to_end(key)
        if cached is None:
            subset = manuscript.model_copy(update={"pages": [page], "page_count": len(ids)})
            cached = [p.model_dump(mode="json") for p in physical_pages(subset)]
            with _lock:
                _cache[key] = cached
                while len(_cache) > 256:
                    _cache.popitem(last=False)
        for offset, physical in enumerate(deepcopy(cached)):
            physical["page_ordinal"] = ordinal + offset
            result.append(physical)
        ordinal += len(ids)
    return {"schema_version": PREVIEW_VERSION, "manuscript_revision": manuscript.manuscript_revision,
            "source_script_revision_id": manuscript.source_script_revision_id, "manifest": manifest,
            "deck": {"schema_version": "slide_deck_v6", "pages": result}, "page_count": manuscript.page_count}
