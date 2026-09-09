"""Measured code continuations over exact, contiguous source ranges."""
from copy import deepcopy
from math import ceil

from ppt_fixed_draft import lower_fixed_response
from ppt_fixed_templates import fixed_slug
from ppt_layout_execution import validate_text_frame, wrap_text
from ppt_page_scene import resolve_page_scenes
from ppt_teaching_content import PageTeachingV2
from ppt_teaching_planner import normalize_page_response

MAX_CODE_CONTINUATIONS = 128


def _code_frame(page, template):
    # Resolve the real layout with tiny measurement text. No course content is
    # generated or persisted; font/geometry stay owned by the template engine.
    source = {"block_id": "measure", "quote": "x"}
    fields = {"title": "x", "notes": "x", "code": {"sources": [source]}}
    if page["fields"].get("explanation"):
        fields["explanation"] = {"text": "x", "sources": [source]}
    lowered = lower_fixed_response(fields, {"layout_id": page["layout_id"], "page_goal": "x"})
    normalized = normalize_page_response(lowered, {"measure": {
        "block_id": "measure", "block_revision": "measure", "full_text": "x"}})
    scene = resolve_page_scenes(page_id="measure", title="x", content=PageTeachingV2.model_validate(normalized["teaching"]),
        layout=template.get_layout(page["layout_id"]), template=template, source_document_revision="measure")[0]
    obj = next(obj for obj in scene.objects if obj.element_id == "code")
    return obj.width, obj.height, obj.font_size, scene.execution.font_sha256


def paginate_code_page(page, block, template):
    if fixed_slug(str(page.get("layout_id") or "")) != "code":
        return [page]
    choices = (page.get("fields", {}).get("code") or {}).get("sources") or []
    if len(choices) != 1 or not isinstance(choices[0], dict):
        return [page]
    source = choices[0]
    quote = source.get("quote")
    if source.get("block_id") != block["block_id"] or not isinstance(quote, str) or not quote or quote not in block["content"]:
        return [page]  # The source gate, not pagination, owns invalid references.
    from slide_source_tokens import _protected_tokens
    source_tokens = _protected_tokens(block["content"])

    def unsupported_copy(value):
        if isinstance(value, dict):
            return any((_protected_tokens(child) - source_tokens) if key in {"title", "page_goal", "text", "heading"} and isinstance(child, str)
                       else unsupported_copy(child) for key, child in value.items() if key not in {"sources", "notes", "split_reason"})
        if isinstance(value, list):
            return any(unsupported_copy(child) for child in value)
        return False

    # Repair bad metadata once on the logical page before expanding code.
    # Otherwise the same model repair could repeat the full program per slice.
    if unsupported_copy(page):
        return [page]
    width, height, size, digest = _code_frame(page, template)
    try:
        validate_text_frame(quote, width, height, size, digest)
        return [page]
    except ValueError as exc:
        if "teaching_text_capacity_exceeded" not in str(exc):
            raise
    # Every unit is one measured visual row plus its original newline, if any.
    # Wrapping a long source line never introduces or drops source characters.
    units = []
    for paragraph in quote.splitlines(keepends=True):
        text = paragraph.rstrip("\r\n")
        ending = paragraph[len(text):]
        rows = wrap_text(text, width - 16, size, font_digest=digest)
        units.extend(rows[:-1])
        units.append(rows[-1] + ending)
    capacity = int((height - 12) / (size * 1.3)) - 1  # Reserve the trailing-newline row.
    if capacity < 1 or ceil(len(units) / capacity) > MAX_CODE_CONTINUATIONS:
        raise ValueError("script_ppt_code_pagination_capacity_exceeded")
    fragments = []
    offset = 0
    while offset < len(units):
        remaining = len(units) - offset
        count = ceil(remaining / ceil(remaining / capacity))
        end = offset + count
        boundaries = [i for i in range(offset + 1, end + 1) if units[i - 1].endswith("\n")]
        if boundaries and boundaries[-1] >= offset + max(2, count // 2):
            end = boundaries[-1]
        fragment = "".join(units[offset:end])
        validate_text_frame(fragment, width, height, size, digest)
        fragments.append(fragment)
        offset = end
        if len(fragments) > MAX_CODE_CONTINUATIONS:
            raise ValueError("script_ppt_code_pagination_capacity_exceeded")
    if "".join(fragments) != quote:
        raise ValueError("script_ppt_code_pagination_source_mismatch")
    pages = []
    for index, fragment in enumerate(fragments, 1):
        part = deepcopy(page)
        part["fields"]["code"]["sources"] = [{"block_id": block["block_id"], "quote": fragment}]
        part["fields"]["split_reason"] = f"代码连续分页 {index}/{len(fragments)}，原文和顺序保留"
        pages.append(part)
    return pages
