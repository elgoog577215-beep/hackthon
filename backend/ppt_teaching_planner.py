"""Bounded private-model planning before manuscript confirmation."""
from __future__ import annotations

import asyncio
import json
import re
import time
from copy import deepcopy

from pydantic import Field, TypeAdapter

from course_document import stable_hash
from course_presentation_graph import block_source_text
from ppt_layout_execution import PLANNER_VERSION, capability_summary
from ppt_teaching_content import Contract, PageTeachingV2
from ppt_teaching_manuscript import compile_teaching_manuscript
from ppt_comparison_draft import ComparisonPageDraft, lower_comparison_draft
from ppt_page_draft import ChartTeachingPageDraft, GraphTeachingPageDraft, LinearTeachingPageDraft, lower_teaching_draft
from ppt_source_quotes import source_excerpt_catalog
from ppt_adopted_visuals import AdoptedDiagramDraft, lower_adopted_diagram


class PlannedPage(Contract):
    page_id: str = Field(min_length=1)
    teaching_unit_id: str = Field(min_length=1)
    source_block_ids: list[str] = Field(min_length=1)
    title: str = Field(min_length=1, max_length=60)
    layout_id: str = Field(min_length=1)
    page_goal: str = Field(min_length=1)
    primary_claim: str = ""
    audience_question: str = ""
    audience_action: str = ""
    expected_response: str = ""
    observable_evidence: str = ""
    transition: str = ""
    composition_notes: str = ""


class NarrativeResponse(Contract):
    narrative_brief: dict
    pages: list[PlannedPage] = Field(min_length=1)


class PageRevision(Contract):
    layout_id: str = ""
    title: str = Field(min_length=1, max_length=60)
    page_goal: str = Field(min_length=1)
    primary_claim: str = ""
    audience_question: str = ""
    audience_action: str = ""
    expected_response: str = ""
    observable_evidence: str = ""
    transition: str = ""
    composition_notes: str = ""
    teaching: PageTeachingV2


PageResponseDraft = ComparisonPageDraft | LinearTeachingPageDraft | GraphTeachingPageDraft | ChartTeachingPageDraft | AdoptedDiagramDraft


class PageGroupDraft(Contract):
    pages: list[PageResponseDraft] = Field(min_length=1, max_length=12)


def page_response_contract():
    schema = TypeAdapter(PageResponseDraft | PageGroupDraft).json_schema()
    def compact(value):
        if isinstance(value, dict):
            return {k: compact(v) for k, v in value.items() if k != "default" and not (k == "title" and isinstance(v, str))}
        return [compact(v) for v in value] if isinstance(value, list) else value
    return compact(schema)


def normalize_page_response(response, sources, catalog=None):
    if "adopted_diagram_id" in response:
        return lower_adopted_diagram(response, sources, catalog or [])
    if "teaching" in response:
        return _bind_exact_quotes(response, sources)
    lower = lower_comparison_draft if "subjects" in response or response.get("expression_kind") == "comparison" else lower_teaching_draft
    return lower(response, sources)


def revised_plan(plan, revision):
    return {**plan, **revision, "layout_id": revision.get("layout_id") or plan["layout_id"]}


def page_failure_message(error):
    from slide_deck_v6_models import V6BuildError
    return (f"{error.failure.page_id}: {error.failure.message}" if isinstance(error, V6BuildError) else str(error))[:1800]


async def invoke_teaching_provider(provider, request):
    """Use the already configured AIBase; no deterministic/provider fallback."""
    from slide_planning_telemetry import _AIPlannerResponse, _sanitize_provider_attempts
    telemetry = []
    async def call(*args, **kwargs):
        from slide_planning_telemetry import AIPlannerInvocationError
        try:
            return await provider._call_llm(*args, **kwargs)
        except Exception as exc:
            raise AIPlannerInvocationError(exc, telemetry=telemetry) from exc
    response = await call(
        json.dumps(request, ensure_ascii=False),
        system_prompt=(
            "Return JSON matching response_contract only. Prepare classroom slides from the supplied handout in its language. "
            "Only use supplied facts, source block IDs, assets and certified layouts. Full prose stays in notes. "
            "Screen content expresses a clear teaching task through concise evidence, comparisons and relations. "
            "Every element and relation cites a literal contiguous quote from the source. Never invent numbers, quotations, "
            "code or formulas. A selected formula/code/data/quote must copy source text exactly, including Markdown syntax; "
            "ordinary concise explanations use kind=text. The compiler binds quotes to revisions and character offsets. "
            "The compiler assigns reference IDs and expands show_from into cumulative visible states; do not return "
            "full formal manuscript fields unless response_contract explicitly requires them. reveal_notes contains "
            "one note per step. Show every condition and question before its corresponding answer, with answers on a later step. "
            "Never put an answer in a question title. Use short labels and readable text; no shrinking or ellipses. "
            "Comparison requires common conditions, stable subject keys, common dimension keys and every cell. "
            "Comparison conditions, subject headers and dimension labels always remain visible from the first state. "
            "Compare-visual requires actual source-backed relations, images or formula evidence; otherwise use compare-matrix. "
            "Give related cell elements unique keys and reference them with source_key/target_key. "
            "Graph relations follow source meaning, not node array order. Process uses sequence, causal uses causal, "
            "hierarchy uses parent_child. Association does not prove causality. Graph conditions have role=condition, "
            "standalone conclusions role=claim. Referenced edge endpoints are graph nodes regardless of role. "
            "Linear elements follow their supplied array order. Preserve only material needed for THIS page goal; "
            "For linear problem, exercise, derivation, recap, cover, agenda and evidence pages, relations MUST be []. "
            "Page order and show_from express presentation timing; never invent graph edges such as 'display' or 'ask'. "
            "do not copy full explanations into graph nodes. The source is already complete in notes. "
            "Images require accepted immutable asset IDs from the supplied catalog. Do not invent assets. "
            "Data-bars supports 2-6 nonnegative decimal data values, copied exactly from sources with kind=data. "
            "chart_points pairs existing label/value element keys; chart_unit_key cites an exact source unit using kind=quote. "
            "All categories and the unit show from step 1; the compiler fixes one shared zero baseline and scale for every step. "
            "To reuse an accepted diagram, return AdoptedDiagramDraft with its adopted_diagram_id and diagram_unit_id "
            "and a concept-map layout. Its complete nodes and edges are copied from the accepted source; do not reconstruct them. "
            "For narrative planning, cover each supplied formal source block in original first-appearance order and keep "
            "each page within one teaching unit. A long block may support several pages with distinct tasks. "
            "Choose only expression forms supported by the listed layouts. Include cover or recap only if compatible. "
            "During repair preserve valid meaning. Capacity repair may recompose the entire target page, reduce dimensions "
            "or remove optional text. Never shorten or alter a selected exact artifact to fit. "
            "When one planned task needs multiple slides, return {pages:[...]} of complete page drafts, each with its own "
            "title, goal, layout and reveal_notes. Split a compound exercise into separate answerable tasks; keep each "
            "question with all its necessary conditions/options, then reveal its answer. Do not spread one question's "
            "essential options across unrelated pages. Large formulas and code need dedicated space. "
            "Omit optional empty fields. In source choices return quote_id only, without repeating block_id or quote. "
        ),
        model_role="ppt_story", use_fast_model=False, json_mode=True,
        enable_thinking=False,
        max_tokens=10000, max_input_tokens=26000, max_input_chars=70000,
        reject_truncated=True, raise_on_failure=True, retry_count=1, max_attempts=2,
        telemetry_sink=telemetry.append,
    )
    from slide_planning_telemetry import AIPlannerInvocationError
    try:
        value = provider._extract_json(response or "")
        if not isinstance(value, dict) or "error" in value:
            raise ValueError("teaching_model_response_invalid")
        records = _sanitize_provider_attempts(telemetry)
        if not records or records[-1].model != "qwen3.8-27b":
            raise ValueError("teaching_model_provenance_missing")
    except Exception as exc:
        raise AIPlannerInvocationError(exc, telemetry=telemetry) from exc
    return _AIPlannerResponse(value, telemetry=telemetry)


def _bind_exact_quotes(value, sources):
    value = deepcopy(value)
    def walk(obj):
        if isinstance(obj, dict):
            if {"block_id", "block_revision", "quote", "start", "end"} <= set(obj):
                source = sources.get(obj["block_id"])
                if source:
                    text, quote = source["full_text"], obj["quote"]
                    start, end = obj["start"], obj["end"]
                    if not (isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(text) and text[start:end] == quote):
                        # Identical repeated quotations carry identical text
                        # evidence. Bind their canonical first occurrence;
                        # never alter the quote or cross a source block.
                        if isinstance(quote, str) and quote and quote in text:
                            obj["start"] = text.index(quote)
                            obj["end"] = obj["start"] + len(quote)
            for child in obj.values():
                walk(child)
        elif isinstance(obj, list):
            for child in obj:
                walk(child)
    walk(value)
    return value


async def plan_teaching_manuscript(document, graph, template, planner, *, source_context=None, checkpoint=None, on_checkpoint=None):
    from slide_planning_telemetry import _provider_attempts_from
    from slide_deck_v6_models import SlideNarrativeBriefV1, V6BuildError
    source_context = source_context or {}
    checkpoint = deepcopy(checkpoint or {})
    sources = {b.block_id: {"block_id": b.block_id, "block_revision": b.internal_revision, "full_text": block_source_text(b)}
               for b in document.blocks if b.block_id in graph.formal_block_ids}
    signature = stable_hash({"source": document.document_revision, "template": template.template_digest,
                             "planner": PLANNER_VERSION, "source_context": source_context}, prefix="plan_")
    if checkpoint and checkpoint.get("signature") != signature:
        raise V6BuildError(stage="recovery", code="teaching_planning_checkpoint_mismatch", message="内容规划检查点与当前来源或模板不一致。")
    checkpoint.setdefault("signature", signature)
    checkpoint.setdefault("pages", {})
    checkpoint.setdefault("draft_pages", {})
    checkpoint.setdefault("page_revisions", {})
    checkpoint.setdefault("page_groups", {})
    checkpoint.setdefault("calls", [])

    async def save(event):
        if on_checkpoint:
            await on_checkpoint(deepcopy(checkpoint), event)

    async def invoke(request, item_id):
        await save({"phase": "started", "item_id": item_id})
        start = time.monotonic()
        try:
            response = await asyncio.wait_for(planner(request), timeout=300)
        except Exception as exc:
            records = _provider_attempts_from(exc)
            checkpoint["calls"].append({"item_id": item_id, "duration_ms": round((time.monotonic() - start) * 1000),
                "status": "failed", "code": type(exc).__name__, "attempts": [r.model_dump(mode="json") for r in records],
                "input_tokens": sum(r.input_tokens for r in records), "output_tokens": sum(r.output_tokens for r in records),
                "physical_requests": sum(r.physical_request_count for r in records)})
            await save({"phase": "failed", "item_id": item_id})
            raise V6BuildError(stage="story", code="teaching_provider_failed", message="指定模型未完成页面内容规划，可恢复重试。", retryable=True) from exc
        records = _provider_attempts_from(response)
        checkpoint["calls"].append({"item_id": item_id, "duration_ms": round((time.monotonic() - start) * 1000), "status": "returned",
            "attempts": [r.model_dump(mode="json") for r in records], "input_tokens": sum(r.input_tokens for r in records),
            "output_tokens": sum(r.output_tokens for r in records), "physical_requests": sum(r.physical_request_count for r in records)})
        return dict(response)

    def validate_narrative(response):
        narrative = NarrativeResponse.model_validate(response)
        ids = [b for p in narrative.pages for b in p.source_block_ids]
        first_use = list(dict.fromkeys(ids))
        missing = [b for b in graph.formal_block_ids if b not in first_use]
        unknown = [b for b in first_use if b not in graph.formal_block_ids]
        if missing or unknown:
            raise ValueError(f"teaching_narrative_coverage_invalid: missing={missing}; unknown={unknown}")
        if first_use != graph.formal_block_ids:
            raise ValueError(f"teaching_narrative_order_invalid: required first-use order={graph.formal_block_ids}; actual={first_use}")
        if len({p.page_id for p in narrative.pages}) != len(narrative.pages):
            raise ValueError("teaching_narrative_page_id_duplicate")
        units = {u.teaching_unit_id: set(u.primary_block_ids) for u in graph.units}
        layouts = {l.template_layout_id for l in template.layouts if l.execution is not None}
        for page in narrative.pages:
            if not set(page.source_block_ids) <= units.get(page.teaching_unit_id, set()):
                raise ValueError(f"teaching_unit_source_mismatch:{page.page_id}: use sources from {page.teaching_unit_id} only")
            if page.layout_id not in layouts:
                raise ValueError(f"teaching_layout_unavailable:{page.page_id}")
        SlideNarrativeBriefV1.model_validate(narrative.narrative_brief)
        return narrative

    if "narrative" not in checkpoint:
        schema = NarrativeResponse.model_json_schema()
        page_schema = schema["$defs"]["PlannedPage"]
        page_schema["properties"] = {k: v for k, v in page_schema["properties"].items() if k in page_schema["required"]}
        error = ""
        raw = checkpoint.get("draft_narrative")
        for attempt in range(3):
            if raw is not None and not error:
                try:
                    narrative = validate_narrative(raw)
                except ValueError as exc:
                    error = str(exc)
                else:
                    checkpoint["narrative"] = narrative.model_dump(mode="json")
                    break
            response = await invoke({"teaching_request": "narrative", "title": document.title,
                "response_contract": schema,
                "narrative_contract": SlideNarrativeBriefV1.model_json_schema(),
                "planning_instruction": "Return only a compact lesson path and required page fields. Detailed text, questions, answers and relations belong to the later page request. Preserve the supplied source order on first appearance; include ALL blocks, even short objective and feedback blocks.",
                "required_first_use_order": graph.formal_block_ids,
                "layout_capabilities": capability_summary(template),
                "units": [{"teaching_unit_id": u.teaching_unit_id, "intent": u.teaching_intent,
                           "sources": [sources[b] for b in u.primary_block_ids]} for u in graph.units],
                "previous_candidate": raw, "validation_error": error}, "teaching-narrative")
            raw = response
            checkpoint["draft_narrative"] = response
            try:
                narrative = validate_narrative(response)
            except ValueError as exc:
                error = str(exc)
                checkpoint["calls"][-1]["validation_error"] = error
                await save({"phase": "repair", "item_id": "teaching-narrative"})
            else:
                checkpoint["narrative"] = narrative.model_dump(mode="json")
                await save({"phase": "completed", "item_id": "teaching-narrative"})
                break
        else:
            raise V6BuildError(stage="story", code="teaching_narrative_invalid", message=error, retryable=True)
    narrative = NarrativeResponse.model_validate(checkpoint["narrative"])
    # The bounded group currently holds one logical page; accepted pages survive
    # provider failure and restart, and are never resent as repair targets.
    for plan in narrative.pages:
        if plan.page_id in checkpoint["pages"]:
            continue
        item_id = f"teaching-page-{plan.page_id}"
        error = next((c.get("validation_error", "") for c in reversed(checkpoint["calls"]) if c["item_id"] == item_id), "")
        previous_candidate = checkpoint["draft_pages"].get(plan.page_id)
        repair_parts, repair_index = None, None

        async def accept(response):
            nonlocal repair_parts, repair_index
            repair_parts, repair_index = None, None
            responses = response.get("pages") if isinstance(response, dict) and "pages" in response else [response]
            if not isinstance(responses, list) or not 1 <= len(responses) <= 12:
                raise ValueError("teaching_page_group_invalid")
            subgraph = graph.model_copy(update={"formal_block_ids": plan.source_block_ids})
            revisions, planned = [], []
            for index, part in enumerate(responses):
                try:
                    if not isinstance(part, dict):
                        raise ValueError("teaching_page_draft_invalid: each page must be an object")
                    revision = PageRevision.model_validate(normalize_page_response(part,
                        {b: sources[b] for b in plan.source_block_ids}, source_context.get("accepted_visual_expressions", [])))
                    item = revised_plan({**plan.model_dump(mode="json"),
                        "page_id": plan.page_id if len(responses) == 1 else f"{plan.page_id}-part-{index + 1}"}, revision.model_dump(mode="json"))
                    compile_teaching_manuscript(document, subgraph, template, narrative.narrative_brief,
                        [item], source_context=source_context)
                except (ValueError, V6BuildError):
                    if len(responses) > 1:
                        repair_parts, repair_index = deepcopy(responses), index
                    raise
                revisions.append(revision)
                planned.append(item)
            single = compile_teaching_manuscript(document, subgraph, template, narrative.narrative_brief,
                planned, source_context=source_context)
            checkpoint["pages"][plan.page_id] = single.pages[0].teaching.model_dump(mode="json")
            checkpoint["page_revisions"][plan.page_id] = revisions[0].model_dump(mode="json", exclude={"teaching"})
            checkpoint["page_groups"][plan.page_id] = planned
            await save({"phase": "completed", "item_id": item_id})

        if previous_candidate:
            try:
                await accept(previous_candidate)
            except (ValueError, V6BuildError) as exc:
                error = page_failure_message(exc)
            else:
                continue
        for attempt in range(3):
            request_plan = plan.model_dump(mode="json")
            request_candidate = previous_candidate
            if repair_parts is not None:
                request_candidate = repair_parts[repair_index]
                if isinstance(request_candidate, dict):
                    request_plan.update({key: request_candidate[key] for key in ("title", "page_goal", "layout_id") if request_candidate.get(key)})
            response = await invoke({"teaching_request": "page", "page": request_plan,
                "narrative_brief": narrative.narrative_brief, "response_contract": page_response_contract(),
                "comparison_instruction": "Fill every subject-by-dimension cell with source-backed content. Do not return empty cells: use show_from to reveal values later. All object/dimension labels and shared conditions must appear before any cell. reveal_notes has one note per reveal step. The compiler assigns IDs and source ranges; you provide only semantic keys and exact quotes.",
                "sources": [sources[b] for b in plan.source_block_ids], "layout_capabilities": capability_summary(template),
                "literal_source_ranges": source_excerpt_catalog({b: sources[b] for b in plan.source_block_ids}),
                "accepted_visual_expressions": [v for v in source_context.get("accepted_visual_expressions", []) if v["source_block_id"] in plan.source_block_ids],
                "source_instruction": "Prefer sources=[{quote_id: supplied_id}]. For formula/code/data/quote set use_source_text=true and omit text; the compiler copies the selected quote exactly, including delimiters and whitespace. Choose a range containing only the desired artifact, not its surrounding paragraph. For ordinary text write a concise summary and cite supporting quote IDs.",
                "validation_error": error, "previous_candidate": request_candidate,
                "repair_scope": ("Return only the failing subpage shown in previous_candidate, or split that subpage into pages. "
                    "Other subpages are preserved by the compiler; do not repeat them." if repair_parts is not None else "Current page task"),
                "repair_instruction": (
                    "Capacity failure: recompose this target page to its stated goal only. You may return a different layout_id "
                    "from this template's capabilities when its expression kind better fits the task. Graph nodes need concise labels, "
                    "not full paragraphs: remove secondary ideas from this page and leave complete prose in notes. "
                    "A multi-line matrix needs ONE comparison dimension and "
                    "only the matrix itself per cell; move optional prose to the teacher metadata or leave it in source notes. "
                    "Common conditions, question and conclusion are short single-line text. Preserve exact formulas. "
                    "Return the complete revised page or {pages:[...]} to split this task into several answerable pages. "
                    "When a derivation exceeds capacity, use ONE large matrix/formula per page with one short operation or question; "
                    "place intermediate arithmetic on its own page. A two-page draft can need three or more pages. "
                    "Do not add more elements while repairing overflow. Preserve healthy page parts; split the named failing part. "
                    "For linear expressions relations must be []; use reveal timing, not graph edges, for instruction order. "
                    "Each linear element shares the frame, so 10-15 formula/option elements cannot fit on one page. "
                    "Use fewer grouped options with concise source excerpts, or separate distinct questions. "
                    if "capacity" in error or "too_long" in error else
                    "Correct the reported field or relation, preserve other valid meaning, and return the complete page."
                )}, item_id)
            if repair_parts is not None:
                parts = response.get("pages") if "pages" in response else [response]
                if isinstance(parts, list):
                    response = {"pages": [*repair_parts[:repair_index], *parts, *repair_parts[repair_index + 1:]]}
            previous_candidate = response
            checkpoint["draft_pages"][plan.page_id] = response
            try:
                await accept(response)
                break
            except (ValueError, V6BuildError) as exc:
                error = page_failure_message(exc)
                error = re.sub(r"cell-(\d+)-(\d+)", lambda m: f"cells[{m[1]}].content[{m[2]}].text", error)
                error = re.sub(r"subject-(\d+)", lambda m: f"subjects[{m[1]}].text", error)
                error = re.sub(r"dimension-(\d+)", lambda m: f"dimensions[{m[1]}].text", error)
                checkpoint["calls"][-1]["validation_error"] = error
                await save({"phase": "repair", "item_id": item_id})
        else:
            raise V6BuildError(stage="manuscript", code="teaching_page_validation_failed", message=error, page_id=plan.page_id, retryable=True)
    manuscript = compile_teaching_manuscript(document, graph, template, narrative.narrative_brief,
        [part for p in narrative.pages for part in checkpoint["page_groups"].get(p.page_id, [
            {**revised_plan(p.model_dump(mode="json"), checkpoint["page_revisions"].get(p.page_id, {})), "teaching": checkpoint["pages"][p.page_id]}])], source_context=source_context)
    return manuscript, checkpoint


async def regenerate_teaching_pages(manuscript, target_page_ids, planner, *, timeout_seconds=180,
                                    accepted_question_bank_items=None, accepted_visual_expressions=None):
    """Build all selected pages before returning a single atomic draft update."""
    from slide_deck_v6_models import V6BuildError
    from ppt_teaching_manuscript import revise_teaching_manuscript, template_for_manuscript, resolve_manuscript_page, refresh_manuscript
    template = template_for_manuscript(manuscript)
    page_map = {p.page_id: p for p in manuscript.pages}
    candidate_base = manuscript.model_copy(deep=True)
    replacements = {}
    for page_id in target_page_ids:
        page = page_map[page_id]
        if page.teacher_locked:
            raise V6BuildError(stage="manuscript", code="ppt_manuscript_target_locked", message="请先解锁目标页。", page_id=page_id)
        if page.speaker_notes is None:
            raise V6BuildError(stage="manuscript", code="ppt_manuscript_regeneration_source_missing", message="目标页缺少讲义快照。", page_id=page_id)
        sources = {n.block_id: {"block_id": n.block_id, "block_revision": n.block_revision, "full_text": n.full_text}
                   for n in page.speaker_notes.source_blocks}
        error = ""
        previous_candidate = None
        for attempt in range(3):
            request = {"teaching_request": "revision", "response_contract": page_response_contract(),
                "current_page": page.model_dump(mode="json", exclude={"resolved_scenes", "regions", "speaker_notes"}),
                "narrative_brief": manuscript.narrative_brief.model_dump(mode="json"),
                "sources": list(sources.values()), "layout_capabilities": capability_summary(template),
                "literal_source_ranges": source_excerpt_catalog(sources),
                "accepted_question_bank_items": accepted_question_bank_items or [],
                "accepted_visual_expressions": accepted_visual_expressions or [], "validation_error": error,
                "previous_candidate": previous_candidate}
            try:
                response = await asyncio.wait_for(planner(request), timeout=timeout_seconds)
            except Exception as exc:
                raise V6BuildError(stage="story", code="teaching_provider_failed", message="指定模型未完成选定页重生，原稿已保留。", page_id=page_id, retryable=True) from exc
            try:
                previous_candidate = dict(response)
                parts = response.get("pages") if "pages" in response else [response]
                if not isinstance(parts, list) or not 1 <= len(parts) <= 12:
                    raise ValueError("teaching_page_group_invalid")
                from ppt_adopted_visuals import bind_adopted_assets
                resolved = []
                for index, part in enumerate(parts):
                    revision = PageRevision.model_validate(normalize_page_response(dict(part), sources, accepted_visual_expressions or []))
                    bind_adopted_assets(revision.teaching, accepted_visual_expressions or [], set(sources))
                    temporary = candidate_base.model_copy(deep=True)
                    base_page = next(p for p in temporary.pages if p.page_id == page_id)
                    base_page.teaching.adopted_assets = deepcopy(revision.teaching.adopted_assets)
                    base_page.teaching.adopted_diagram = deepcopy(revision.teaching.adopted_diagram)
                    for note in base_page.speaker_notes.source_blocks:
                        note.asset_refs = list(dict.fromkeys([*note.asset_refs, *(a.asset_id for a in revision.teaching.adopted_assets if a.source_block_id == note.block_id)]))
                    update = {"page_id": page_id, **revision.model_dump(mode="json"), "layout_id": revision.layout_id or page.layout_id}
                    validated = revise_teaching_manuscript(temporary, [update])
                    generated = next(p for p in validated.pages if p.page_id == page_id)
                    if len(parts) > 1:
                        generated.page_id = f"{page_id}-part-{index + 1}"
                        if generated.page_id in page_map:
                            raise ValueError("teaching_generated_page_id_collision")
                        resolve_manuscript_page(generated, template, manuscript.source_document_revision)
                    resolved.append(generated)
                replacements[page_id] = resolved
                break
            except (ValueError, V6BuildError) as exc:
                error = page_failure_message(exc)
        else:
            raise V6BuildError(stage="manuscript", code="teaching_page_validation_failed", message=error, page_id=page_id, retryable=True)
    candidate_base.pages = [part for page in candidate_base.pages for part in replacements.get(page.page_id, [page])]
    for number, page in enumerate(candidate_base.pages, 1):
        page.page_number = number
    candidate_base.story_page_count = len(candidate_base.pages)
    return refresh_manuscript(candidate_base)


def manuscript_trace_plans(manuscript):
    """Trace adapters only; final export does not run a planning algorithm."""
    from slide_deck_v6_models import SlideStoryPlanV3, SlideStoryBatchV3, SlideStoryPageV3, SlideVisualPlanV2
    story = SlideStoryPlanV3(source_document_revision=manuscript.source_document_revision, template_digest=manuscript.template_digest,
        batches=[SlideStoryBatchV3(batch_id="teaching-manuscript", chapter_id="lesson", provider="confirmed-manuscript", model="confirmed-manuscript",
            duration_ms=0, attempts=1, validation_status="passed", narrative_brief=manuscript.narrative_brief,
            pages=[SlideStoryPageV3(page_id=p.page_id, teaching_unit_id=p.teaching_unit_id, template_layout_id=p.layout_id,
                title=p.title, source_block_ids=p.source_script_block_ids, page_ordinal=i, visible_copy=[])
                for i, p in enumerate(manuscript.pages)])])
    visual = SlideVisualPlanV2(source_document_revision=manuscript.source_document_revision, template_digest=manuscript.template_digest,
        decisions=[p.visual_decision for p in manuscript.pages])
    return story, visual
