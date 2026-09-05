"""Bridge accepted, current shared illustrations into the existing manuscript."""
from copy import deepcopy

from content_blocks import content_fingerprint
from course_document import stable_hash
from course_presentation_graph import block_source_text
from ppt_teaching_content import AdoptedAssetBinding
from ppt_draft_common import DraftMetadata
from pydantic import Field


class AdoptedDiagramDraft(DraftMetadata):
    adopted_diagram_id: str = Field(min_length=1)
    diagram_unit_id: str = Field(min_length=1)
    teaching_note: str = Field(min_length=1)


def diagram_semantics(content):
    """Digest source-selected identities and relationships, independent of style."""
    return stable_hash({"nodes": [{"id": e.element_id, "text": e.text, "kind": e.kind} for e in content.elements],
                        "expression": content.expression.model_dump(mode="json", exclude={"relations"}),
                        "relations": [{"id": r.relation_id, "source": r.source_id, "target": r.target_id,
                                       "kind": r.kind, "label": r.label} for r in content.expression.relations]}, prefix="diagram_")


def lower_adopted_diagram(value, sources, catalog):
    """Copy accepted nodes/edges without asking a model to reconstruct a graph."""
    from diagram_spec import DiagramSpec
    from ppt_teaching_content import PageTeachingV2
    draft = AdoptedDiagramDraft.model_validate(value)
    entries = [v for v in catalog if v["kind"] == "diagram" and v["representation_id"] == draft.adopted_diagram_id
               and v["source_block_id"] in sources]
    if len(entries) != 1:
        raise ValueError("teaching_diagram_not_adopted")
    entry = entries[0]
    spec = DiagramSpec.model_validate(entry["content"])
    units = [u for u in spec.units if u.unit_id == draft.diagram_unit_id]
    if len(units) != 1:
        raise ValueError("teaching_diagram_unit_missing")
    unit = units[0]
    source = sources[entry["source_block_id"]]
    text = source["full_text"]
    full_range = {"block_id": source["block_id"], "block_revision": source["block_revision"], "start": 0, "end": len(text), "quote": text}
    quotes = spec.quality_report.get("source_quotes", {})
    elements = []
    for node in unit.nodes:
        quote = quotes.get(node.node_id) or text
        if quote not in text:
            raise ValueError("teaching_diagram_source_quote_mismatch")
        start = text.index(quote)
        elements.append({"element_id": node.node_id, "text": node.label,
            "sources": [{**full_range, "start": start, "end": start + len(quote), "quote": quote}]})
    labels = {"supports": "支持", "prepares": "前提", "defines": "定义", "contains": "包含", "causes": "导致",
              "contrasts": "对比", "equivalent": "等价", "condition": "条件", "transforms_to": "转化"}
    ids = [e["element_id"] for e in elements]
    content = PageTeachingV2.model_validate({"elements": elements,
        "expression": {"kind": "concept", "node_element_ids": ids, "relations": [
            {"relation_id": r.edge_id, "source_id": r.source_node_id, "target_id": r.target_node_id,
             "kind": r.relation, "label": labels[r.relation], "sources": [full_range]} for r in unit.edges]},
        "must_show": ids, "states": [{"state_id": "adopted", "visible_element_ids": ids, "teaching_note": draft.teaching_note}],
        "source_dispositions": [{"block_id": b, "purpose": "screen" if b == source["block_id"] else "notes",
                                 "element_ids": ids if b == source["block_id"] else [], "reason": "采用当前讲义的已审阅图解，完整原文进入备注。"} for b in sources]})
    from ppt_teaching_content import AdoptedDiagramBinding
    content.adopted_diagram = AdoptedDiagramBinding(representation_id=entry["representation_id"],
        representation_revision=entry["revision"], expression_digest=entry["digest"], source_block_id=source["block_id"],
        unit_id=unit.unit_id, semantic_digest=diagram_semantics(content))
    return {**draft.model_dump(exclude={"adopted_diagram_id", "diagram_unit_id", "teaching_note"}), "teaching": content.model_dump(mode="json")}


def validate_adopted_diagram(content):
    if content.adopted_diagram:
        if content.expression.kind != "concept" or diagram_semantics(content) != content.adopted_diagram.semantic_digest:
            raise ValueError("teaching_adopted_diagram_changed")


def current_visual_catalog(items, *, course_id, script_revision_id, sources, asset_repository):
    catalog = []
    for item in items:
        source = item.get("source") or {}
        block_id = str(source.get("block_id") or source.get("source_block_id") or "")
        if (item.get("status") != "accepted" or item.get("stale_reasons") or block_id not in sources
                or source.get("script_revision_id") != script_revision_id
                or source.get("block_content_fingerprint") != content_fingerprint(sources[block_id])):
            continue
        if item.get("representation_type") not in {"diagram", "image"}:
            continue
        content = deepcopy(item.get("content") or {})
        entry = {"representation_id": item["representation_id"], "revision": item["revision"],
                 "kind": item["representation_type"], "source_block_id": block_id, "course_id": course_id,
                 "content": content, "assets": []}
        entry["digest"] = stable_hash(entry, prefix="adopted_")
        if entry["kind"] == "image":
            for metadata in content.get("visual_asset_manifest") or []:
                asset_id = metadata.get("asset_id")
                asset = asset_repository.get(asset_id)
                if asset is None or asset.course_id != course_id or asset.sha256 != metadata.get("sha256"):
                    raise ValueError("teaching_adopted_asset_identity_mismatch")
                from ppt_layout_execution import file_digest
                if file_digest(asset_repository.resolve(asset_id)) != asset.sha256:
                    raise ValueError("teaching_asset_digest_mismatch")
                entry["assets"].append({"asset_id": asset_id, "sha256": asset.sha256, "alt_text": asset.alt_text})
            if not entry["assets"]:
                continue
        catalog.append(entry)
    return catalog


def bind_adopted_assets(content, catalog, source_ids):
    """Trust only the server catalog. Model-supplied provenance is replaced."""
    bindings = []
    for element in content.elements:
        if element.kind != "image":
            continue
        matches = [(entry, asset) for entry in catalog for asset in entry["assets"]
                   if entry["source_block_id"] in source_ids and asset["asset_id"] == element.asset_id
                   and asset["sha256"] == element.asset_digest
                   and entry["source_block_id"] in {s.block_id for s in element.sources}]
        if len(matches) != 1:
            raise ValueError("teaching_asset_not_adopted")
        entry, asset = matches[0]
        binding = AdoptedAssetBinding(asset_id=asset["asset_id"], sha256=asset["sha256"], course_id=entry["course_id"],
            representation_id=entry["representation_id"], representation_revision=entry["revision"],
            expression_digest=entry["digest"], source_block_id=entry["source_block_id"])
        if binding not in bindings:
            bindings.append(binding)
    content.adopted_assets = bindings
    if content.adopted_diagram:
        binding = content.adopted_diagram
        entries = [v for v in catalog if v["kind"] == "diagram" and v["representation_id"] == binding.representation_id
                   and v["revision"] == binding.representation_revision and v["digest"] == binding.expression_digest
                   and v["source_block_id"] == binding.source_block_id and binding.source_block_id in source_ids]
        if len(entries) != 1:
            raise ValueError("teaching_diagram_not_adopted")
        validate_adopted_diagram(content)
        # Verify against the trusted accepted spec as well as the submitted hash.
        from diagram_spec import DiagramSpec
        unit = next((u for u in DiagramSpec.model_validate(entries[0]["content"]).units if u.unit_id == binding.unit_id), None)
        if unit is None or [(e.element_id, e.text) for e in content.elements] != [(n.node_id, n.label) for n in unit.nodes]:
            raise ValueError("teaching_adopted_diagram_changed")
        if [(r.relation_id, r.source_id, r.target_id, r.kind) for r in content.expression.relations] != [(r.edge_id, r.source_node_id, r.target_node_id, r.relation) for r in unit.edges]:
            raise ValueError("teaching_adopted_diagram_changed")
    return content


def catalog_for_teacher_source(service, document, course_view):
    context = course_view["teacher_lesson_source"]
    sources = {b.block_id: block_source_text(b) for b in document.blocks}
    # Read without reconcile_external_source, which writes derived states.
    registry = service.repository.load(context["real_course_id"])
    specs = {s.spec_id: s for s in registry.specs}
    items = [service._view_item(r, specs[r.spec_id]) for r in registry.representations
             if r.spec_id in specs and r.variant_key.startswith(f"script-visual:{context['lesson_unit_id']}:")]
    return current_visual_catalog(items, course_id=context["real_course_id"], script_revision_id=context["script_revision_id"],
                                  sources=sources, asset_repository=service.asset_repository)
