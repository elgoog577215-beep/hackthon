"""Regressions for narration-to-slide inflation and whole-lesson editing."""
from copy import deepcopy

import pytest

from ppt_presentation import presentation_states
from ppt_teaching_content import PageTeachingV2, PagePresentationV1, PptPacingV1
from ppt_teaching_manuscript import refresh_manuscript, resolve_manuscript_page
from .test_ppt_teaching_content import comparison_fixture, compiled_manuscript


def progressive_comparison():
    value, notes = comparison_fixture()
    ids = value["states"][0]["visible_element_ids"]
    value["states"] = [{"state_id": f"step-{i}", "visible_element_ids": ids[:size], "teaching_note": f"讲述提示{i}"}
        for i, size in enumerate([4, 5, 5, 5, 6], 1)]
    return value, notes


def test_ordinary_page_collapses_narration_and_formal_payload_cannot_bypass_policy():
    from ppt_teaching_planner import normalize_page_response
    value, notes = progressive_comparison()
    sources = {b: {"block_id": b, "block_revision": revision, "full_text": text} for b, (revision, text) in notes.items()}
    result = normalize_page_response({"title": "执行方式", "page_goal": "比较执行方式", "teaching": value}, sources)
    content = PageTeachingV2.model_validate(result["teaching"])
    assert content.presentation.mode == "complete"
    assert len(presentation_states(content)) == 1
    assert [s.teaching_note for s in content.states] == [s["teaching_note"] for s in value["states"]]
    # Explicit key stops still merge identical canvases, without changing notes.
    content.presentation = PagePresentationV1(mode="key_steps", checkpoints=[{"state_id": s.state_id, "reason": "观察当前差异"} for s in content.states])
    assert [s.state_id for s in presentation_states(content)] == ["step-1", "step-2", "step-5"]


def test_question_answer_exports_two_views_and_retains_all_narration():
    from ppt_teaching_planner import normalize_page_response
    from .test_ppt_page_draft import draft_fixture
    value, sources = draft_fixture()
    citation = value["elements"][0]["sources"]
    value.update(expression_kind="exercise", relations=[], elements=[
        {"key": "q", "text": "怎样选择？", "role": "question", "sources": citation},
        {"key": "a", "text": "符合条件时分类", "role": "answer", "show_from": 4, "sources": citation}],
        reveal_notes=["先提问", "等待回答", "讨论判断依据", "核对答案", "反馈"])
    content = PageTeachingV2.model_validate(normalize_page_response(value, sources)["teaching"])
    states = presentation_states(content)
    assert content.presentation.mode == "question_answer"
    assert [s.visible_element_ids for s in states] == [["q"], ["q", "a"]]
    assert all(note in "\n".join(s.teaching_note for s in content.states) for note in value["reveal_notes"])
    content.presentation = PagePresentationV1(mode="complete")
    with pytest.raises(ValueError, match="answer_requires_separation"):
        presentation_states(content)


def test_compact_narration_preserves_checkpoint_ids_without_concatenation_overflow():
    from .test_ppt_page_draft import draft_fixture
    from ppt_teaching_planner import normalize_page_response
    value, sources = draft_fixture()
    value["reveal_notes"] = ["讲述" * 200, "观察" * 200, "讨论" * 200]
    value["presentation"] = {"mode": "key_steps", "checkpoints": [{"state_id": "step-3", "reason": "完整观察后讨论"}]}
    content = PageTeachingV2.model_validate(normalize_page_response(value, sources)["teaching"])
    assert [s.state_id for s in content.states] == ["step-1", "step-2", "step-3"]
    assert [s.teaching_note for s in content.states] == value["reveal_notes"]
    assert len(presentation_states(content)) == 1


def test_non_cumulative_views_require_explicit_stops_and_full_coverage():
    value, _ = progressive_comparison()
    value["states"] = [value["states"][1], {**value["states"][-1], "visible_element_ids": [*value["states"][0]["visible_element_ids"], "b-mode"]}]
    content = PageTeachingV2.model_validate(value)
    content.presentation = PagePresentationV1(mode="complete")
    with pytest.raises(ValueError, match="complete_state_missing"):
        presentation_states(content)
    content.presentation = PagePresentationV1(mode="key_steps", checkpoints=[{"state_id": s.state_id, "reason": "独立观察后比较"} for s in content.states])
    assert len(presentation_states(content)) == 2
    content.presentation.checkpoints.pop(0)
    with pytest.raises(ValueError, match="screen_element_never_visible"):
        presentation_states(content)


def test_invalid_stop_order_and_empty_reason_are_rejected():
    value, _ = progressive_comparison()
    value["presentation"] = {"mode": "key_steps", "checkpoints": [{"state_id": s, "reason": "核对依据"} for s in ["step-5", "step-1"]]}
    with pytest.raises(ValueError, match="checkpoint_order_invalid"):
        presentation_states(PageTeachingV2.model_validate(value))
    value["presentation"]["checkpoints"][0]["reason"] = " "
    with pytest.raises(ValueError, match="checkpoint_reason_missing"):
        PageTeachingV2.model_validate(value)


def test_old_serialized_manuscript_keeps_state_sequence_and_has_no_new_defaults():
    value, _ = progressive_comparison()
    _, _, _, manuscript = compiled_manuscript(value)
    assert manuscript.page_count == 5
    payload = manuscript.model_dump(mode="json")
    assert "pacing" not in payload
    assert "presentation" not in payload["pages"][0]["teaching"]
    assert "teaching_notes" not in payload["pages"][0]["speaker_notes"]
    assert [s.state_id for s in presentation_states(manuscript.pages[0].teaching)] == [s["state_id"] for s in value["states"]]


def test_notes_are_exported_after_policy_change_and_budget_is_recomputed(monkeypatch):
    from ppt_teaching_manuscript import revise_teaching_manuscript, physical_pages, validate_reviewable_manuscript
    from slide_deck_v6 import compile_slide_deck_v6_from_manuscript
    from slide_speaker_notes import _speaker_notes
    value, _ = progressive_comparison()
    doc, graph, template, manuscript = compiled_manuscript(value)
    monkeypatch.setattr("ppt_teaching_manuscript.template_for_manuscript", lambda _: template)
    changed = deepcopy(value)
    changed["presentation"] = {"mode": "key_steps", "checkpoints": [{"state_id": s["state_id"], "reason": "比较当前可见差异"} for s in value["states"]]}
    revised = revise_teaching_manuscript(manuscript, [{"page_id": "p1", "teaching": changed}], pacing={"max_physical_pages": 2, "rationale": "比较留出讨论时间"})
    assert revised.page_count == 3 and revised.quality_status == "blocked"
    validate_reviewable_manuscript(doc, graph, revised, template)
    with pytest.raises(ValueError, match="ppt_pacing_budget_exceeded"):
        compile_slide_deck_v6_from_manuscript(doc, graph, revised, template)
    # The output gate recomputes the audit instead of trusting stored passed.
    forged = revised.model_copy(update={"quality_status": "passed", "quality_issues": []})
    from course_document import stable_hash
    forged.manuscript_revision = stable_hash(forged.model_dump(mode="json", exclude={"schema_version", "manuscript_revision"}), prefix="pptman_")
    with pytest.raises(ValueError, match="ppt_pacing_budget_exceeded"):
        compile_slide_deck_v6_from_manuscript(doc, graph, forged, template)
    changed["presentation"] = {"mode": "complete"}
    fixed = revise_teaching_manuscript(revised, [{"page_id": "p1", "teaching": changed}])
    assert fixed.page_count == 1 and fixed.quality_status == "passed"
    assert fixed.manuscript_revision != revised.manuscript_revision
    exported_notes = _speaker_notes(physical_pages(fixed)[0])
    assert all(s["teaching_note"] in exported_notes for s in value["states"])
    assert manuscript.page_count == 5


def test_adjacent_duplicate_canvas_blocked_even_if_title_changes():
    value, _ = comparison_fixture()
    value["presentation"] = {"mode": "complete"}
    _, _, template, manuscript = compiled_manuscript(value)
    other = manuscript.pages[0].model_copy(deep=True, update={"page_id": "p2", "page_number": 2, "title": "另一种标题"})
    resolve_manuscript_page(other, template, manuscript.source_document_revision)
    manuscript.pages.append(other)
    revised = refresh_manuscript(manuscript)
    assert revised.quality_status == "blocked"
    assert revised.quality_issues[0].code == "ppt_pacing_duplicate_canvas"
    assert revised.quality_issues[0].page_id == "p2"


def test_related_contiguous_sources_can_cross_units_without_losing_notes():
    from course_document import CourseBlock, CourseSection
    from course_presentation_graph import compile_course_presentation_graph
    from ppt_teaching_manuscript import compile_teaching_manuscript
    doc, _, template, existing = compiled_manuscript()
    doc.sections.append(CourseSection(section_id="s2", title="执行条件", position=1))
    doc.blocks.append(CourseBlock(block_id="b2", section_id="s2", position=0, payload={"markdown": "独立工作可以同时处理。"}, internal_revision="r2"))
    graph = compile_course_presentation_graph(doc, teaching_plan={})
    assert len(graph.units) == 2
    value = existing.pages[0].teaching.model_dump(mode="json")
    value["source_dispositions"].append({"block_id": "b2", "purpose": "notes", "reason": "教师结合独立工作解释共同条件", "element_ids": []})
    page = {"page_id": "merged", "title": "条件与执行方式", "page_goal": "用独立工作条件理解执行差异", "teaching_unit_id": graph.units[0].teaching_unit_id,
        "source_block_ids": ["b", "b2"], "layout_id": template.layout_id("compare-matrix"), "teaching": value}
    result = compile_teaching_manuscript(doc, graph, template, {}, [page])
    assert len(result.pages) == 1
    assert [s.full_text for s in result.pages[0].speaker_notes.source_blocks] == [doc.blocks[0].payload["markdown"], doc.blocks[1].payload["markdown"]]
    with pytest.raises(ValueError, match="teaching_unit_source_mismatch"):
        compile_teaching_manuscript(doc, graph, template, {}, [{**page, "source_block_ids": ["b2", "b"]}])


def test_narrative_ranges_bind_exact_sources_across_units_and_reject_invalid_span():
    from types import SimpleNamespace
    from ppt_teaching_planner import normalize_narrative_response
    graph = SimpleNamespace(formal_block_ids=["a", "b", "c"], units=[
        SimpleNamespace(teaching_unit_id="u1", primary_block_ids=["a"]),
        SimpleNamespace(teaching_unit_id="u2", primary_block_ids=["b", "c"])])
    value = {"narrative_brief": {}, "pacing": {"max_physical_pages": 3, "rationale": "完整比较"},
        "pages": [{"source_first": 1, "source_last": 3, "title": "比较", "layout_id": "compare", "page_goal": "比较共同条件"}]}
    page = normalize_narrative_response(value, graph)["pages"][0]
    assert page["source_block_ids"] == ["a", "b", "c"]
    assert page["teaching_unit_id"] == "u1"
    for start, end in [(3, 2), (1, 4)]:
        value["pages"][0].update(source_first=start, source_last=end)
        with pytest.raises(ValueError, match="source_span_invalid"):
            normalize_narrative_response(value, graph)


@pytest.mark.parametrize("formal_minutes", [45, 0])
def test_model_cannot_replace_formal_duration_or_invent_missing_timing(formal_minutes):
    import asyncio
    from ppt_teaching_planner import plan_teaching_manuscript
    doc, graph, template, manuscript = compiled_manuscript()
    page = manuscript.pages[0]
    calls = []
    async def planner(request):
        calls.append(request)
        if request["teaching_request"] == "narrative":
            return {"narrative_brief": {"time_budget_minutes": 90 if len(calls) == 1 else formal_minutes},
                "pacing": {"max_physical_pages": 2, "rationale": "比较后讨论"}, "pages": [
                    {"source_first": 1, "source_last": 1, "title": page.title, "page_goal": page.page_goal, "layout_id": page.layout_id}]}
        return {"title": page.title, "page_goal": page.page_goal, "teaching": page.teaching.model_dump(mode="json")}
    result, _ = asyncio.run(plan_teaching_manuscript(doc, graph, template, planner,
        source_context={"teaching_plan": {"lesson_duration_minutes": formal_minutes}}))
    assert "ppt_pacing_duration_mismatch" in calls[1]["validation_error"]
    assert result.narrative_brief.time_budget_minutes == formal_minutes


def test_repair_feedback_names_short_slots_without_echoing_model_payload():
    from ppt_comparison_draft import DraftShortText
    from ppt_teaching_planner import page_failure_message
    from pydantic import ValidationError
    with pytest.raises(ValidationError) as error:
        DraftShortText.model_validate({"text": "对齐变量", "kind": "formula", "sources": [{"quote_id": "q1"}]})
    message = page_failure_message(error.value)
    assert "kind: Input should be 'text'" in message
    assert "https://" not in message and "input_value" not in message


def test_model_field_repair_preserves_unmodified_content_and_rejects_unknown_fields():
    from .test_ppt_page_draft import draft_fixture
    from ppt_teaching_planner import apply_page_repair
    value, _ = draft_fixture()
    before = deepcopy(value)
    revised = apply_page_repair({"patch": {"split_reason": "独立观察两个分支"}}, value)
    assert revised["elements"] == value["elements"]
    assert revised["split_reason"] == "独立观察两个分支"
    assert value == before and revised["elements"] is not value["elements"]
    for patch in [{"source_block_ids": ["invented"]}, {}]:
        with pytest.raises(ValueError, match="patch_fields_invalid"):
            apply_page_repair({"patch": patch}, value)
    with pytest.raises(ValueError, match="patch_expression_change"):
        apply_page_repair({"patch": {"expression_kind": "comparison"}}, value)


def test_budget_repair_can_merge_the_whole_task_instead_of_isolating_a_sibling():
    import asyncio
    from ppt_teaching_planner import plan_teaching_manuscript
    doc, graph, template, manuscript = compiled_manuscript()
    page = manuscript.pages[0]
    part = {"title": page.title, "page_goal": page.page_goal, "split_reason": "比较一次执行方式",
        "teaching": page.teaching.model_dump(mode="json")}
    calls = []
    async def planner(request):
        calls.append(request)
        if request["teaching_request"] == "narrative":
            return {"narrative_brief": {}, "pacing": {"max_physical_pages": 1, "rationale": "同一画面完成比较"},
                "pages": [{"source_first": 1, "source_last": 1, "title": page.title, "page_goal": page.page_goal, "layout_id": page.layout_id}]}
        if len(calls) == 2:
            return {"pages": [deepcopy(part), deepcopy(part)]}
        assert "task_budget_exceeded" in request["validation_error"]
        assert len(request["previous_candidate"]["pages"]) == 2
        return deepcopy(part)
    result, _ = asyncio.run(plan_teaching_manuscript(doc, graph, template, planner))
    assert len(calls) == 3 and result.page_count == 1 and result.quality_status == "passed"


def test_duplicate_manuscript_is_saved_for_review_but_final_build_is_blocked(tmp_path):
    import asyncio
    from slide_deck_v6_models import PptManuscriptV1, V6BuildError
    from slide_deck_v6_orchestrator import SlideDeckV6Orchestrator, SlideDeckV6CandidateRepository
    from teaching_representations import TeachingRepresentationRepository
    doc, _, template, manuscript = compiled_manuscript()
    page = manuscript.pages[0]
    async def planner(request):
        if request["teaching_request"] == "narrative":
            return {"narrative_brief": {}, "pacing": {"max_physical_pages": 4, "rationale": "两次比较"},
                "pages": [{"source_first": 1, "source_last": 1, "title": title, "page_goal": page.page_goal, "layout_id": page.layout_id}
                    for title in ["执行方式", "换个标题仍然重复"]]}
        return {"title": request["page"]["title"], "page_goal": page.page_goal, "teaching": page.teaching.model_dump(mode="json")}
    async def forbidden(_):
        pytest.fail("blocked manuscript invoked final model")
    candidates = SlideDeckV6CandidateRepository(tmp_path / "candidates")
    orchestrator = SlideDeckV6Orchestrator(representation_repository=TeachingRepresentationRepository(tmp_path / "representations"),
        candidate_repository=candidates, progress_root=tmp_path / "progress")
    args = dict(document=doc, course_data={}, mode="teaching", theme="academic-editorial", visual_planner=forbidden,
        source_revision_provider=lambda: doc.document_revision, template_contract=template, publish_result=False)
    result = asyncio.run(orchestrator.build(task_id="draft", story_planner=planner, manuscript_only=True, **args))
    assert result["status"] == "manuscript_ready"
    draft = PptManuscriptV1.model_validate(result["ppt_manuscript"])
    assert draft.quality_status == "blocked"
    assert draft.quality_issues[0].code == "ppt_pacing_duplicate_canvas"
    assert candidates.load("draft")["ppt_manuscript"]["quality_status"] == "blocked"
    with pytest.raises(V6BuildError, match="ppt_pacing_duplicate_canvas"):
        asyncio.run(orchestrator.build(task_id="final", story_planner=forbidden, confirmed_manuscript=draft, **args))
