"""Three-stage adapters for the existing manuscript, deck and revision APIs."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy

from course_document import stable_hash
from course_presentation_graph import block_source_text
from ppt_layout_execution import compile_teaching_template
from ppt_page_scene import display_element_text, resolve_page_scenes, verify_scene
from ppt_teaching_content import PageTeachingV2, validate_source_bindings


def _failure(error, page_id=""):
    import re
    from slide_deck_v6_models import V6BuildError
    code = str(error).split("\n")[0].split(":")[0]
    if not re.fullmatch(r"[a-z][a-z0-9_]+", code):
        code = "teaching_content_invalid"
    return V6BuildError(stage="manuscript", code=code,
                       message=str(error), page_id=page_id, retryable=False)


def _notes(page):
    if page.speaker_notes is None:
        raise ValueError("teaching_notes_missing")
    return {n.block_id: (n.block_revision, n.full_text) for n in page.speaker_notes.source_blocks}


def resolve_manuscript_page(page, template, source_revision):
    """Used by initial planning and teacher edits, never by final rendering."""
    from slide_deck_v6_models import SlideRegionV6
    if page.teaching is None:
        raise ValueError("teaching_content_missing")
    page.teaching = PageTeachingV2.model_validate(page.teaching.model_dump(mode="json"))
    validate_source_bindings(page.teaching, _notes(page))
    from ppt_adopted_visuals import validate_adopted_diagram
    validate_adopted_diagram(page.teaching)
    if not page.page_goal.strip():
        raise ValueError("teaching_goal_or_question_missing")
    # Comparison identities/cells and graph edges already express the teaching
    # relationship. Do not require the model to duplicate it as a prose claim.
    if page.teaching.expression.kind not in {"comparison", "concept", "process", "causal", "hierarchy", "cover", "agenda"} and not (
            page.primary_claim.strip() or page.audience_question.strip()
            or any(e.role in {"question", "claim"} for e in page.teaching.elements)):
        raise ValueError("teaching_goal_or_question_missing")
    if (page.audience_question.strip() or page.audience_action.strip()) and not (page.expected_response.strip() or page.observable_evidence.strip()):
        raise ValueError("teaching_response_missing")
    from slide_source_tokens import _protected_tokens
    full_source = "\n".join(text for _, text in _notes(page).values())
    for field in ("title", "page_goal", "primary_claim", "audience_question", "audience_action", "expected_response", "observable_evidence"):
        if _protected_tokens(getattr(page, field)) - _protected_tokens(full_source):
            raise ValueError(f"teaching_fact_token_unsupported:{field}")
    for element in page.teaching.elements:
        if element.kind == "image":
            adopted = {ref for note in page.speaker_notes.source_blocks for ref in note.asset_refs}
            if element.asset_id not in adopted:
                raise ValueError("teaching_asset_not_adopted")
            binding = next((a for a in page.teaching.adopted_assets if a.asset_id == element.asset_id), None)
            if binding and (binding.sha256 != element.asset_digest or binding.source_block_id not in {s.block_id for s in element.sources}):
                raise ValueError("teaching_adopted_asset_identity_mismatch")
            from slide_asset_repository import slide_asset_repository
            from ppt_layout_execution import file_digest
            try:
                asset_path = slide_asset_repository.resolve(element.asset_id)
            except (FileNotFoundError, ValueError) as exc:
                raise ValueError("teaching_adopted_asset_unavailable") from exc
            if file_digest(asset_path) != element.asset_digest:
                raise ValueError("teaching_asset_digest_mismatch")
        source = "\n".join(s.quote for s in element.sources)
        if _protected_tokens(element.text) - _protected_tokens(source):
            raise ValueError(f"teaching_fact_token_unsupported:{element.element_id}")
        if element.role == "answer" and len(element.text.strip()) >= 4 and element.text.strip() in page.title:
            raise ValueError("answer_revealed_in_title")
    layout = template.get_layout(page.layout_id)
    if layout is None:
        raise ValueError("teaching_layout_unavailable")
    page.resolved_scenes = resolve_page_scenes(page_id=page.page_id, title=page.title, content=page.teaching,
        layout=layout, template=template, source_document_revision=source_revision)
    page.visible_copy = [page.title, *(display_element_text(e) for e in page.teaching.elements)]
    page.regions = [SlideRegionV6(region_id=f"{page.page_id}:title", slot_id="title", content_kind="title",
        content=page.title, source_block_ids=page.source_script_block_ids)]
    page.regions.extend(SlideRegionV6(region_id=f"{page.page_id}:{e.element_id}", slot_id=e.element_id,
        content_kind=e.kind, content=display_element_text(e), source_block_ids=list(dict.fromkeys(s.block_id for s in e.sources)),
        metadata={"element_id": e.element_id, "subject_id": e.subject_id, "dimension_id": e.dimension_id}) for e in page.teaching.elements)
    page.reveal_steps = [s.teaching_note for s in page.teaching.states]
    page.web_renderer_adapter, page.pptx_renderer_adapter = layout.web_renderer_adapter, layout.pptx_renderer_adapter
    return page


def refresh_manuscript(manuscript):
    from slide_deck_v6_models import PptManuscriptV1
    payload = manuscript.model_dump(mode="json", exclude={"schema_version", "manuscript_revision"})
    payload["page_count"] = sum(len(p.resolved_scenes or []) for p in manuscript.pages)
    payload["quality_status"], payload["quality_issues"] = "passed", []
    return PptManuscriptV1(manuscript_revision=stable_hash(payload, prefix="pptman_"), **payload)


def compile_teaching_manuscript(document, graph, template, narrative, planned_pages, *, source_context=None):
    from slide_deck_v6_models import PptManuscriptV1, PptManuscriptPageV1, SlideSpeakerNotesV2, SourceNoteBlockV2, SlideVisualDecisionV2
    blocks = {b.block_id: b for b in document.blocks}
    units = {u.teaching_unit_id: u for u in graph.units}
    pages = []
    source_context = source_context or {}
    type_map = {"problem": "concept", "exercise": "practice", "derivation": "reasoning", "recap": "summary", "process": "diagram",
                "causal": "diagram", "hierarchy": "diagram", "concept": "concept", "comparison": "comparison", "cover": "cover", "agenda": "agenda", "evidence": "content"}
    for index, planned in enumerate(planned_pages):
        unit = units.get(planned["teaching_unit_id"])
        source_ids = planned["source_block_ids"]
        if unit is None or not set(source_ids) <= set(unit.primary_block_ids):
            raise _failure("teaching_unit_source_mismatch", planned["page_id"])
        from ppt_adopted_visuals import bind_adopted_assets
        try:
            content = PageTeachingV2.model_validate(planned["teaching"])
            content = bind_adopted_assets(content, source_context.get("accepted_visual_expressions", []), source_ids)
        except ValueError as error:
            raise _failure(error, planned["page_id"]) from error
        page = PptManuscriptPageV1(
            page_id=planned["page_id"], page_number=index + 1, teaching_unit_id=unit.teaching_unit_id,
            page_type=type_map[content.expression.kind], title=planned["title"], layout_id=planned["layout_id"],
            page_goal=planned["page_goal"], primary_claim=planned.get("primary_claim", ""),
            audience_question=planned.get("audience_question", ""), audience_action=planned.get("audience_action", ""),
            expected_response=planned.get("expected_response", ""), observable_evidence=planned.get("observable_evidence", ""),
            transition=planned.get("transition", ""), composition_notes=planned.get("composition_notes", ""),
            teaching=content, source_script_block_ids=source_ids, speaker_note_source_block_ids=source_ids,
            course_block_types=[blocks[b].kind for b in source_ids], visual_kind="text_native",
            visual_decision=SlideVisualDecisionV2(page_id=planned["page_id"], decision="text_native", source_block_ids=source_ids,
                resolved_template_layout_id=planned["layout_id"]),
            speaker_notes=SlideSpeakerNotesV2(source_document_revision=document.document_revision, teaching_unit_id=unit.teaching_unit_id,
                source_blocks=[SourceNoteBlockV2(block_id=b, block_revision=blocks[b].internal_revision,
                    full_text=block_source_text(blocks[b]), source_kind=blocks[b].kind, source_payload=blocks[b].payload,
                    asset_refs=list(dict.fromkeys([*blocks[b].asset_refs, *(a.asset_id for a in content.adopted_assets if a.source_block_id == b)]))) for b in source_ids]),
        )
        try:
            resolve_manuscript_page(page, template, document.document_revision)
        except ValueError as error:
            raise _failure(error, page.page_id) from error
        pages.append(page)
    ownership = Counter(b for p in pages for b in p.source_script_block_ids)
    if set(ownership) != set(graph.formal_block_ids):
        raise _failure("course_block_coverage_incomplete")
    ordered = list(dict.fromkeys(b for p in pages for b in p.source_script_block_ids))
    if ordered != graph.formal_block_ids:
        raise _failure("teaching_source_order_changed")
    manuscript = PptManuscriptV1(
        teaching_content_contract_version="page_teaching_v2", manuscript_revision="pending",
        source_document_revision=document.document_revision,
        source_lesson_plan_revision_id=source_context.get("lesson_plan_revision_id", ""),
        source_script_revision_id=source_context.get("script_revision_id", ""),
        material_bindings=source_context.get("material_bindings", []), narrative_brief=narrative,
        template_id=template.template_id, template_version=template.template_version, template_digest=template.template_digest,
        pages=pages, page_count=sum(len(p.resolved_scenes) for p in pages), story_page_count=len(pages),
    )
    return refresh_manuscript(manuscript)


def template_for_manuscript(manuscript):
    try:
        if manuscript.template_id.startswith("pptp-"):
            from ppt_template_packs import ppt_template_pack_repository
            template, _ = ppt_template_pack_repository.resolve_render_bundle_internal(manuscript.template_id, manuscript.template_version)
        else:
            template = compile_teaching_template(manuscript.template_id, version=manuscript.template_version)
    except (ValueError, FileNotFoundError) as exc:
        raise _failure("teaching_locked_template_unavailable") from exc
    if template.template_digest != manuscript.template_digest:
        raise _failure("ppt_manuscript_template_mismatch")
    return template


def revise_teaching_manuscript(manuscript, updates):
    from slide_deck_v6_models import PptManuscriptPageV1
    template = template_for_manuscript(manuscript)
    candidate = manuscript.model_copy(deep=True)
    pages = {p.page_id: p for p in candidate.pages}
    allowed = {"page_id", "title", "page_goal", "primary_claim", "audience_question", "audience_action", "expected_response",
               "observable_evidence", "transition", "composition_notes", "teaching", "teacher_locked", "layout_id"}
    seen = set()
    for update in updates:
        page_id = update.get("page_id")
        if not page_id or page_id in seen or page_id not in pages or set(update) - allowed:
            raise _failure("ppt_manuscript_edit_invalid", str(page_id or ""))
        seen.add(page_id)
        page = pages[page_id]
        payload = page.model_dump(mode="json")
        if "teaching" in update and update["teaching"].get("adopted_assets", []) != [a.model_dump(mode="json") for a in page.teaching.adopted_assets]:
            raise _failure("teaching_adopted_asset_binding_immutable", page_id)
        if "teaching" in update and update["teaching"].get("adopted_diagram") != (page.teaching.adopted_diagram.model_dump(mode="json") if page.teaching.adopted_diagram else None):
            raise _failure("teaching_adopted_diagram_binding_immutable", page_id)
        payload.update(deepcopy(update))
        try:
            revised = PptManuscriptPageV1.model_validate(payload)
            revised.lock_source_document_revision = manuscript.source_document_revision if revised.teacher_locked else ""
            resolve_manuscript_page(revised, template, revised.speaker_notes.source_document_revision)
        except ValueError as error:
            raise _failure(error, page_id) from error
        pages[page_id] = revised
    candidate.pages = [pages[p.page_id] for p in candidate.pages]
    return refresh_manuscript(candidate)


def physical_pages(manuscript):
    from slide_deck_v6_models import SlidePageV6, SlideRegionV6
    pages = []
    for logical in manuscript.pages:
        if not logical.teaching or not logical.resolved_scenes or logical.visual_decision is None:
            raise _failure("teaching_scene_missing", logical.page_id)
        validate_source_bindings(logical.teaching, _notes(logical))
        from ppt_adopted_visuals import validate_adopted_diagram
        validate_adopted_diagram(logical.teaching)
        if [s.state_id for s in logical.resolved_scenes] != [s.state_id for s in logical.teaching.states]:
            raise _failure("teaching_state_scene_mismatch", logical.page_id)
        expected_copy = [logical.title, *(display_element_text(e) for e in logical.teaching.elements)]
        if logical.visible_copy != expected_copy:
            raise _failure("teaching_visible_copy_mismatch", logical.page_id)
        for index, scene in enumerate(logical.resolved_scenes):
            verify_scene(scene)
            state = logical.teaching.states[index]
            if {o.element_id for o in scene.objects if o.element_id} != set(state.visible_element_ids):
                raise _failure("teaching_state_scene_mismatch", logical.page_id)
            regions = {r.slot_id: r for r in logical.regions}
            visible_regions = []
            for obj in scene.objects:
                region = regions.get(obj.element_id or "title")
                if region is None or region.content != obj.text:
                    raise _failure("teaching_scene_content_mismatch", logical.page_id)
                visible_regions.append(region.model_copy(deep=True))
            physical_id = f"{logical.page_id}--{scene.state_id}"
            decision = logical.visual_decision.model_copy(update={"page_id": physical_id}, deep=True)
            pages.append(SlidePageV6(page_id=physical_id, page_ordinal=len(pages), teaching_unit_id=logical.teaching_unit_id,
                title=logical.title, resolved_layout=logical.layout_id,
                web_renderer_adapter=logical.web_renderer_adapter, pptx_renderer_adapter=logical.pptx_renderer_adapter,
                regions=visible_regions, source_block_ids=logical.source_script_block_ids, source_section_ids=logical.source_section_ids,
                visual_decision=decision, speaker_notes=logical.speaker_notes.model_copy(deep=True), resolved_scene=scene.model_copy(deep=True),
                continuation_of_page_id=logical.page_id if index else "", continuation_index=index + 1, continuation_count=len(logical.resolved_scenes)))
    if len(pages) != manuscript.page_count:
        raise _failure("teaching_physical_page_count_changed")
    return pages


def teaching_deck_quality(document, graph, manuscript, template, pages):
    from slide_deck_v6_models import SlideDeckV6Quality
    blocks = {b.block_id: b for b in document.blocks}
    ownership = Counter(b for p in manuscript.pages for b in p.source_script_block_ids)
    if set(ownership) != set(graph.formal_block_ids):
        raise _failure("course_block_coverage_incomplete")
    for page in manuscript.pages:
        for note in page.speaker_notes.source_blocks:
            block = blocks.get(note.block_id)
            if block is None or note.block_revision != block.internal_revision or note.full_text != block_source_text(block):
                raise _failure("teaching_note_source_mismatch", page.page_id)
        # Recompute the scene deterministically for equality, never replace it.
        checked = page.model_copy(deep=True)
        # A page retains its original document snapshot when only unrelated
        # blocks changed. Exact block revisions above are the freshness proof.
        resolve_manuscript_page(checked, template, page.speaker_notes.source_document_revision)
        if checked.model_dump(mode="json") != page.model_dump(mode="json"):
            raise _failure("teaching_confirmed_scene_mismatch", page.page_id)
    ordered = list(dict.fromkeys(b for p in manuscript.pages for b in p.source_script_block_ids)) == graph.formal_block_ids
    if not ordered:
        raise _failure("teaching_source_order_changed")
    return SlideDeckV6Quality(formal_block_visible_coverage=1, full_text_note_binding=1,
        source_order_preserved=ordered, template_contract_passed=True, subject_artifacts_passed=True,
        web_pptx_contract_shared=True, story_page_count=len(manuscript.pages), final_page_count=len(pages),
        pagination_expansion_ratio=len(pages) / len(manuscript.pages), pagination_page_upper_bound=len(pages))
