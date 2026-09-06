"""Fixed fields -> saved manuscript -> editable PPTX, without model/network calls."""
import asyncio
from copy import deepcopy

import pytest
from pptx import Presentation

from course_document import CourseBlock, CourseDocument, CourseSection
from course_presentation_graph import compile_course_presentation_graph
from ppt_fixed_draft import lower_fixed_response
from ppt_fixed_templates import VERSION, compile_fixed_template
from ppt_teaching_content import PageTeachingV2
from ppt_teaching_manuscript import compile_teaching_manuscript, template_for_manuscript
from ppt_teaching_planner import normalize_page_response, plan_teaching_manuscript
from ppt_page_scene import resolve_page_scenes


TEXT = "课堂学习。先准备，再执行，最后检查。串行逐项执行，并行同时执行。相同任务条件下比较执行方式。为什么先准备？明确目标。公式为 x=1。"


def field(text):
    return {"text": text, "sources": [{"block_id": "b", "quote": TEXT}]}


def source():
    return {"b": {"block_id": "b", "block_revision": "r", "full_text": TEXT}}


def fixture():
    document = CourseDocument(course_id="fixed-test", title="课堂学习", document_revision="doc",
        sections=[CourseSection(section_id="s", title="课堂学习", position=0)],
        blocks=[CourseBlock(block_id="b", section_id="s", position=0, payload={"markdown": TEXT}, internal_revision="r")])
    graph = compile_course_presentation_graph(document, teaching_plan={})
    return document, graph, compile_fixed_template("qizhi-classroom")


def response(slug):
    base = {"title": "课堂学习", "notes": "详细讲解保存在教师备注。"}
    if slug in {"cover", "section"}:
        return {**base, "subtitle": field("明确目标")}
    if slug == "comparison":
        return {**base, "condition": field("相同任务条件"), "left_subject": field("串行"), "right_subject": field("并行"),
            "rows": [{"dimension": field("执行方式"), "left": field("逐项执行"), "right": field("同时执行")}],
            "conclusion": field("比较执行方式")}
    if slug == "flow":
        return {**base, "steps": [field(x) for x in ("准备", "执行", "检查")]}
    if slug == "question":
        return {**base, "question": field("为什么先准备？"), "answer": field("明确目标")}
    if slug == "formula":
        return {**base, "formula": {"sources": [{"block_id": "b", "quote": "x=1"}]}, "explanation": field("明确目标")}
    return {**base, "points": [field("明确目标"), field("先准备，再执行，最后检查") ]}


def lowered(slug):
    _, _, template = fixture()
    plan = {"layout_id": template.layout_id(slug), "page_goal": "明确目标"}
    return normalize_page_response(lower_fixed_response(response(slug), plan), source())


@pytest.mark.parametrize("slug", ["cover", "section", "agenda", "bullets", "summary", "comparison", "flow", "question", "formula"])
def test_every_fixed_form_resolves_to_auditable_editable_objects(slug, tmp_path):
    from ppt_native_scene import render_scene, audit_scene
    from pptx.util import Pt
    _, _, template = fixture()
    value = lowered(slug)
    scenes = resolve_page_scenes(page_id="p", title=value["title"], content=PageTeachingV2.model_validate(value["teaching"]),
        layout=template.get_layout(template.layout_id(slug)), template=template, source_document_revision="doc")
    prs = Presentation()
    prs.slide_width, prs.slide_height = Pt(960), Pt(540)
    for scene in scenes:
        render_scene(prs.slides.add_slide(prs.slide_layouts[6]), scene)
    path = tmp_path / "fixed.pptx"
    prs.save(path)
    readback = Presentation(path)
    for slide, scene in zip(readback.slides, scenes, strict=True):
        audit_scene(slide, scene)
    if slug == "comparison":
        cells = [o for o in scenes[0].objects if o.slot_id.startswith("cell.")]
        assert cells[0].y == cells[1].y and cells[0].x < cells[1].x
    if slug == "flow":
        assert len(scenes[0].edges) == 2
        nodes = [o for o in scenes[0].objects if o.element_id]
        assert len({o.y for o in nodes}) == 1
    if slug == "question":
        assert len(scenes) == 2
        assert "answer" not in {o.element_id for o in scenes[0].objects}
        assert "answer" in {o.element_id for o in scenes[1].objects}


def test_fixed_capacity_rejects_overflow_without_font_shrinking():
    _, _, template = fixture()
    value = lowered("bullets")
    value["teaching"]["elements"][0]["text"] = "明确目标" * 80
    with pytest.raises(ValueError, match="capacity"):
        resolve_page_scenes(page_id="p", title=value["title"], content=PageTeachingV2.model_validate(value["teaching"]),
            layout=template.get_layout(template.layout_id("bullets")), template=template, source_document_revision="doc")


def test_fixed_manuscript_roundtrip_edit_and_export(tmp_path):
    from ppt_teaching_manuscript import revise_teaching_manuscript
    from slide_deck_v6 import compile_slide_deck_v6_from_manuscript
    from slide_deck_v6_renderer import export_slide_deck_v6_pptx
    doc, graph, template = fixture()
    value = lowered("comparison")
    manuscript = compile_teaching_manuscript(doc, graph, template, {"central_question": "比较执行方式"}, [{
        **value, "page_id": "p", "teaching_unit_id": graph.units[0].teaching_unit_id, "source_block_ids": ["b"]}])
    assert template_for_manuscript(manuscript).template_digest == template.template_digest
    revised = revise_teaching_manuscript(manuscript, [{"page_id": "p", "title": "执行方式"}])
    assert revised.pages[0].resolved_scenes[0].objects[0].text == "执行方式"
    deck = compile_slide_deck_v6_from_manuscript(doc, graph, revised, template)
    path = export_slide_deck_v6_pptx(deck, tmp_path / "complete.pptx")
    assert TEXT in Presentation(path).slides[0].notes_slide.notes_text_frame.text


def test_fixed_planner_parallel_failure_recovery_and_selected_forms():
    from slide_deck_v6_models import V6BuildError
    doc, graph, template = fixture()
    saved, active, peak, requests = {}, 0, 0, []

    async def save(value, event):
        saved.clear()
        saved.update(deepcopy(value))

    async def planner(request):
        nonlocal active, peak
        if request["teaching_request"] == "narrative":
            assert not any(x["layout_id"].endswith("/figure") for x in request["layout_capabilities"]["available_layouts"])
            return {"narrative_brief": {"central_question": "明确目标"}, "pacing": {"max_physical_pages": 8, "rationale": "完整呈现教学任务"},
                "pages": [{"page_id": f"p{i}", "title": "课堂学习", "page_goal": goal, "teaching_unit_id": graph.units[0].teaching_unit_id,
                           "source_block_ids": ["b"], "layout_id": template.layout_id("bullets")} for i, goal in enumerate(("准备", "执行", "检查"))]}
        assert request["teaching_request"] == "fixed_fields"
        assert "composition_notes" not in str(request["response_contract"])
        requests.append(request)
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        if request["page"]["page_goal"] == "执行":
            raise RuntimeError("provider failed")
        return response("bullets")

    with pytest.raises(V6BuildError):
        asyncio.run(plan_teaching_manuscript(doc, graph, template, planner, on_checkpoint=save))
    assert peak == 3 and set(saved["pages"]) == {"p0", "p2"}
    retried = []
    async def recover(request):
        retried.append(request["page"]["page_goal"])
        return response("bullets")
    manuscript, _ = asyncio.run(plan_teaching_manuscript(doc, graph, template, recover, checkpoint=saved))
    assert retried == ["执行"]
    assert [p.page_id for p in manuscript.pages] == ["p0", "p1", "p2"]
    assert manuscript.template_version == VERSION


def test_new_default_template_and_historical_template_lock(monkeypatch):
    from routers import teacher_lesson_authoring as routes
    from template_layout_contract import compile_builtin_template_layout_contract_v1
    monkeypatch.delenv("PPT_THREE_STAGE_ENABLED", raising=False)
    template = routes._resolve_teacher_v6_template(routes.TeacherLessonV6BuildRequest(), "teacher")
    assert template.template_version == VERSION
    for candidate in (template, compile_builtin_template_layout_contract_v1("academic-editorial")):
        locked = routes._resolve_locked_teacher_v6_template({"theme": candidate.theme_id,
            "template_version": candidate.template_version, "template_digest": candidate.template_digest}, "teacher")
        assert locked.template_digest == candidate.template_digest


def test_fixed_form_repair_and_confirmed_build_use_existing_orchestrator(tmp_path):
    from slide_deck_v6_models import PptManuscriptV1
    from slide_deck_v6_orchestrator import SlideDeckV6Orchestrator, SlideDeckV6CandidateRepository
    from teaching_representations import TeachingRepresentationRepository
    doc, graph, template = fixture()
    calls = []
    async def planner(request):
        calls.append(request["teaching_request"])
        if request["teaching_request"] == "narrative":
            return {"narrative_brief": {"central_question": "明确目标"}, "pacing": {"max_physical_pages": 2, "rationale": "呈现一个教学任务"},
                "pages": [{"page_id": "p", "title": "课堂学习", "page_goal": "明确目标", "teaching_unit_id": graph.units[0].teaching_unit_id,
                           "source_block_ids": ["b"], "layout_id": template.layout_id("bullets")}]}
        if calls.count("fixed_fields") == 1:
            return {"title": "课堂学习", "points": [], "notes": "补充讲解"}
        assert request["validation_error"]
        value = response("bullets")
        quote_id = request["literal_source_ranges"][0]["quote_id"]
        for point in value["points"]:
            point["sources"] = [{"quote_id": quote_id}]
        return value
    async def forbidden(request):
        pytest.fail("confirmed export called an AI planner")
    orchestrator = SlideDeckV6Orchestrator(representation_repository=TeachingRepresentationRepository(tmp_path / "representations"),
        candidate_repository=SlideDeckV6CandidateRepository(tmp_path / "candidates"), progress_root=tmp_path / "progress")
    args = dict(document=doc, course_data={}, mode="teaching", theme=template.theme_id,
        visual_planner=forbidden, source_revision_provider=lambda: doc.document_revision,
        template_contract=template, publish_result=False)
    draft = asyncio.run(orchestrator.build(task_id="draft", story_planner=planner, manuscript_only=True, **args))
    assert draft["status"] == "manuscript_ready" and calls == ["narrative", "fixed_fields", "fixed_fields"]
    manuscript = PptManuscriptV1.model_validate(draft["ppt_manuscript"])
    final = asyncio.run(orchestrator.build(task_id="final", story_planner=forbidden, confirmed_manuscript=manuscript, **args))
    assert final["status"] == "v6_ready"


def test_fixed_figure_uses_the_existing_adopted_asset_catalog():
    _, _, template = fixture()
    value = lower_fixed_response({"title": "课堂学习", "notes": "观察图片", "asset_id": "asset",
        "caption": field("明确目标")}, {"layout_id": template.layout_id("figure"), "page_goal": "明确目标"},
        [{"kind": "image", "assets": [{"asset_id": "asset", "sha256": "digest"}]}])
    image = value["elements"][0]
    assert image["kind"] == "image" and image["asset_id"] == "asset" and image["asset_digest"] == "digest"
    with pytest.raises(ValueError, match="asset_unavailable"):
        lower_fixed_response({"title": "课堂学习", "notes": "观察图片", "asset_id": "unknown", "caption": field("明确目标")},
            {"layout_id": template.layout_id("figure"), "page_goal": "明确目标"})
