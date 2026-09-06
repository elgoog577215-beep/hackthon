from ppt_fixed_draft import lower_fixed_response
from ppt_fixed_templates import compile_fixed_template
from ppt_page_scene import resolve_page_scenes
from ppt_teaching_content import PageTeachingV2
from ppt_teaching_planner import PageContentContract, normalize_page_response
from slide_theme import slide_theme


SOURCE_TEXT = "课堂来源。准备、识别、执行、核对、结算。中心概念连接三个场景。甲 10，乙 20，丙 30，单位：人。"
SOURCES = {"b": {"block_id": "b", "block_revision": "r", "full_text": SOURCE_TEXT}}


def field(text):
    return {"text": text, "sources": [{"block_id": "b", "quote": SOURCE_TEXT}]}


def exact(text):
    return {"sources": [{"block_id": "b", "quote": text}]}


def render_fixed(slug, response):
    template = compile_fixed_template("editorial-terracotta")
    plan = {"layout_id": template.layout_id(slug), "page_goal": "明确结构"}
    value = normalize_page_response(lower_fixed_response(response, plan), SOURCES)
    content = PageTeachingV2.model_validate(value["teaching"])
    scenes = resolve_page_scenes(
        page_id=slug,
        title=value["title"],
        content=content,
        layout=template.get_layout(plan["layout_id"]),
        template=template,
        source_document_revision="doc",
    )
    return scenes


def test_component_and_composition_registry_covers_reference_page_families():
    from ppt_compositions import COMPOSITIONS, PRIMITIVES

    for primitive in ("card", "step-node", "arrow", "connector", "center-node", "bar", "icon", "title-band", "conclusion-band", "page-number", "rule"):
        assert primitive in PRIMITIVES
    for composition in ("four_stage", "flow6", "triad", "mechanism_stack", "radial", "chart_explanation"):
        assert COMPOSITIONS[composition].status == "implemented"
        assert COMPOSITIONS[composition].primitives


def test_reference_compositions_resolve_to_native_editable_scenes():
    fixtures = {
        "four_stage": {"title": "四阶段", "notes": "说明", "points": [field(x) for x in ("准备", "识别", "执行", "检查")]},
        "flow6": {"title": "六步流程", "notes": "说明", "steps": [field(x) for x in ("准备", "识别", "分配", "执行", "核对", "结算")]},
        "triad": {"title": "三场景", "notes": "说明", "points": [field(x) for x in ("职业", "金钱", "婚姻")]},
        "mechanism_stack": {"title": "三机制", "notes": "说明", "points": [field(x) for x in ("定价", "锁定", "议价")]},
        "radial": {"title": "中心辐射", "notes": "说明", "center": field("选择权"), "satellites": [{"text": x, "sources": [{"block_id": "b", "quote": SOURCE_TEXT}]} for x in ("证据", "规则", "信任")]},
        "chart_explanation": {"title": "数据与结论", "notes": "说明", "unit": exact("人"), "points": [{"label": field(label), "value": exact(value)} for label, value in (("甲", "10"), ("乙", "20"), ("丙", "30"))], "explanation": field("数值逐步增加")},
    }
    for slug, response in fixtures.items():
        scenes = render_fixed(slug, response)
        assert scenes and scenes[0].objects
        if slug == "flow6":
            assert len(scenes[0].edges) == 5
        if slug == "radial":
            assert len(scenes[0].edges) == 3


def test_content_contract_is_structured_before_layout_fields():
    contract = PageContentContract(
        intent="application",
        core_claim="钱首先购买的是选择权",
        objects=["等待", "拒绝", "恢复"],
        relation="parallel",
        evidence=["source-1"],
        composition="triad",
        capacities={"card": 3, "body_chars": 44},
    )
    assert contract.composition == "triad"
    assert contract.capacities["card"] == 3


def test_theme_tokens_are_shared_and_editorial_theme_is_available():
    theme = slide_theme("editorial-terracotta")
    tokens = theme["component_tokens"]
    assert tokens["canvas"] == "F8F7F4"
    assert tokens["accent"] == "C45C3E"
    assert tokens["chart"]
