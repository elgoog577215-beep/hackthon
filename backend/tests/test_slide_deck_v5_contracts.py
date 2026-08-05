from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt

from slide_deck_renderer import audit_exported_pptx, audit_rendered_slide_images
from slide_quality_v5 import (
    build_slide_deck_quality_v5,
    repair_render_slides_v5,
    repair_semantic_slides_v5,
)


def _slide(
    page_id: str,
    *,
    title: str,
    content: str,
    episode_id: str = "episode-1",
    scene_kind: str = "concept",
    block_type: str = "statement",
) -> dict:
    return {
        "unit_id": page_id,
        "position": 0,
        "layout": "concept",
        "slide_purpose": scene_kind,
        "title": title,
        "key_message": "",
        "episode_id": episode_id,
        "scene_kind": scene_kind,
        "blocks": [{
            "block_id": f"{page_id}:body",
            "type": block_type,
            "title": "",
            "content": content,
            "items": [],
            "metadata": {"semantic_atom_id": f"atom:{page_id}"},
        }],
        "visuals": [],
        "quality": {
            "requested_layout": "editorial-body",
            "resolved_layout": "editorial-body",
        },
    }


def test_unique_quality_report_rejects_stale_scores_and_uses_final_slide_count() -> None:
    slides = [
        _slide(
            "slide:v5:episode-1:001",
            title="概念成立需要同时满足两个条件",
            content="条件一给出对象边界，条件二说明对象之间的关系。",
        )
    ]

    report = build_slide_deck_quality_v5(
        slides,
        planner="deterministic_v5",
        fallback_reason="ai_unavailable",
        legacy_quality={
            "score": 12,
            "pedagogical_score": 44,
            "presentation_score": 31,
        },
    )

    assert report["schema_version"] == "slide_deck_quality_v5"
    assert report["status"] == "passed"
    assert report["metrics"]["total_slide_count"] == len(slides)
    assert set(report["dimensions"]) == {
        "source_integrity",
        "teaching_closure",
        "pagination_narrative",
        "layout_export",
        "visual_effectiveness",
        "attribution_accessibility",
    }
    assert "pedagogical_score" not in report
    assert "presentation_score" not in report
    assert report["score"] >= 80


def test_quality_contract_blocks_split_atoms_duplicate_copy_and_empty_answers() -> None:
    first = _slide(
        "slide:v5:episode-1:001",
        title="用共同维度比较两个对象",
        content="比较时先固定同一个观察维度，再说明两个对象的差异结论。",
        scene_kind="comparison",
    )
    first["blocks"][0]["metadata"]["semantic_atom_id"] = "atom-shared"
    second = _slide(
        "slide:v5:episode-1:002",
        title="用共同维度比较两个对象",
        content="比较时先固定同一个观察维度，再说明两个对象的差异结论。",
        scene_kind="practice_feedback",
        block_type="exercise",
    )
    second["blocks"][0]["metadata"].update({
        "semantic_atom_id": "atom-shared",
        "question_mode": "closed",
        "question_id": "question-1",
    })
    second["blocks"].append({
        "block_id": "answer-1",
        "type": "callout",
        "title": "答案",
        "content": "",
        "items": [],
        "metadata": {"answer_for": "question-1"},
    })

    report = build_slide_deck_quality_v5([first, second])
    codes = {issue["code"] for issue in report["blockers"]}

    assert report["status"] == "blocked"
    assert "semantic_atom_split" in codes
    assert "duplicate_visible_content" in codes
    assert "duplicate_title" in codes
    assert "empty_answer" in codes


def test_continuation_requires_parent_link_and_visible_sequence() -> None:
    continuation = _slide(
        "slide:v5:episode-1:continuation",
        title="完整主题标题",
        content="这是超长语义原子的后续完整分段。",
    )
    continuation["quality"].update({
        "continuation_of": "slide:v5:episode-1:root",
        "continuation_index": 2,
        "continuation_total": 3,
    })

    report = build_slide_deck_quality_v5([continuation])

    assert "continuation_sequence_missing" in {
        issue["code"] for issue in report["blockers"]
    }


def test_deterministic_semantic_repair_is_targeted_and_never_invents_an_answer() -> None:
    healthy = _slide(
        "slide:v5:episode-1:001",
        title="证据支持这一判断",
        content="记录中的两个观察结果共同支持本页结论。",
        scene_kind="evidence",
    )
    question = _slide(
        "slide:v5:episode-2:001",
        title="哪一个选项符合材料？",
        content="请选择符合材料描述的选项。",
        episode_id="episode-2",
        scene_kind="practice_feedback",
        block_type="exercise",
    )
    question["blocks"][0]["metadata"].update({
        "question_mode": "closed",
        "question_id": "question-2",
        "source_answer": "",
    })
    question["blocks"].append({
        "block_id": "answer-2",
        "type": "callout",
        "title": "答案",
        "content": "",
        "items": [],
        "metadata": {"answer_for": "question-2"},
    })
    original_healthy = deepcopy(healthy)

    repaired, history = repair_semantic_slides_v5([healthy, question], max_rounds=2)

    assert repaired[0] == original_healthy
    assert repaired[1]["quality"]["question_mode"] == "open_discussion"
    assert all(block.get("title") != "答案" for block in repaired[1]["blocks"])
    assert "开放讨论" in repaired[1]["key_message"]
    assert history
    assert all(item["page_id"] == "slide:v5:episode-2:001" for item in history)


def test_non_exempt_sparse_page_and_internal_labels_are_blockers() -> None:
    slide = _slide(
        "slide:v5:episode-1:001",
        title="知识规范名称",
        content="定义",
    )

    report = build_slide_deck_quality_v5([slide])
    codes = {issue["code"] for issue in report["blockers"]}

    assert "raw_internal_label_visible" in codes
    assert "sparse_non_exempt_page" in codes


def test_semantic_repair_removes_internal_labels_from_source_body_without_losing_text() -> None:
    slide = _slide(
        "slide:v5:episode-1:001",
        title="本页解释完整对象关系",
        content="知识规范名称：对象之间的完整关系",
    )

    repaired, history = repair_semantic_slides_v5([slide], max_rounds=2)

    assert repaired[0]["blocks"][0]["content"] == "对象之间的完整关系"
    assert any(item["action"] == "replace_internal_label" for item in history)
    assert "raw_internal_label_visible" not in {
        issue["code"] for issue in build_slide_deck_quality_v5(repaired)["issues"]
    }


def test_semantic_repair_completes_a_hard_truncated_title_from_source_copy() -> None:
    slide = _slide(
        "slide:v5:episode-1:001",
        title="本节课的核心目标是建立局部解剖学的空",
        content="本节课的核心目标是建立局部解剖学的空间定位基础。",
    )
    slide["quality"]["title_character_budget"] = 18

    repaired, history = repair_semantic_slides_v5([slide], max_rounds=2)

    assert repaired[0]["title"] == "局部解剖学的空间定位基础"
    assert any(
        item["action"] == "complete_title_from_existing_copy"
        for item in history
    )


def test_export_audit_detects_inner_text_clipping_and_unreadable_body_font(
    tmp_path: Path,
) -> None:
    presentation = Presentation()
    presentation.slide_width = Inches(13.333)
    presentation.slide_height = Inches(7.5)
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    box = slide.shapes.add_textbox(Inches(0.8), Inches(2.0), Inches(3.0), Inches(0.35))
    box.text_frame.word_wrap = True
    paragraph = box.text_frame.paragraphs[0]
    paragraph.text = "这是一段必然超过文本框内部容量并造成裁切的正文。" * 5
    paragraph.font.size = Pt(10)
    path = tmp_path / "clipped.pptx"
    presentation.save(path)

    report = audit_exported_pptx(path, expected_slide_count=1)
    codes = {issue["code"] for issue in report["blockers"]}

    assert "exported_text_frame_overflow" in codes
    assert "exported_body_font_below_16pt" in codes


def test_rendered_page_ocr_checks_every_page_for_missing_visible_text(
    tmp_path: Path,
) -> None:
    presentation = Presentation()
    first = presentation.slides.add_slide(presentation.slide_layouts[6])
    first.shapes.add_textbox(
        Inches(0.5), Inches(0.5), Inches(8), Inches(1)
    ).text = "第一页标题与完整正文都必须可见"
    second = presentation.slides.add_slide(presentation.slide_layouts[6])
    second.shapes.add_textbox(
        Inches(0.5), Inches(0.5), Inches(8), Inches(1)
    ).text = "第二页标题与完整正文也必须可见"
    images = [tmp_path / "page-1.png", tmp_path / "page-2.png"]
    for image in images:
        image.touch()

    report = audit_rendered_slide_images(
        presentation,
        images,
        ocr_runner=lambda path: (
            "第一页标题与完整正文都必须可见"
            if path.name == "page-1.png"
            else "第二页标题"
        ),
    )

    assert report["page_count"] == 2
    assert report["checked_pages"] == 2
    assert {
        (issue["code"], issue.get("page")) for issue in report["blockers"]
    } == {("exported_ocr_text_missing_or_clipped", 2)}


def test_render_repair_changes_only_the_audited_page() -> None:
    first = _slide(
        "slide:v5:episode-1:001",
        title="这个标题在导出后发生了意外换行并需要压缩",
        content="同一段正文。同一段正文。",
    )
    first["blocks"].append(deepcopy(first["blocks"][0]))
    first["blocks"][1]["block_id"] = "duplicate"
    second = _slide(
        "slide:v5:episode-2:001",
        title="第二页保持不变",
        content="这一页的文字容量和布局都满足要求。",
        episode_id="episode-2",
    )
    original_second = deepcopy(second)
    review = {
        "issues": [
            {"severity": "critical", "code": "exported_text_frame_overflow", "page": 1},
            {"severity": "critical", "code": "exported_title_unexpected_wrap", "page": 1},
        ]
    }

    repaired, history = repair_render_slides_v5([first, second], review, round_index=1)

    assert repaired[1] == original_second
    assert repaired[0]["quality"]["requested_layout"] == "editorial-body"
    assert len(repaired[0]["blocks"]) == 1
    assert len(repaired[0]["title"]) <= 24
    assert {item["page_id"] for item in history} == {"slide:v5:episode-1:001"}


def test_process_result_in_source_grounded_takeaway_satisfies_contract() -> None:
    slide = _slide(
        "slide:v5:process:source-result",
        title="先检查条件，再形成判断",
        content="先检查两个条件；两项都成立才能形成最终判断。",
        scene_kind="process",
    )
    slide["takeaway"] = "两项都成立才能形成最终判断。"

    report = build_slide_deck_quality_v5([slide])

    assert "process_result_missing" not in {
        issue["code"] for issue in report["issues"]
    }


def test_worked_example_accepts_source_backed_linked_answer_as_conclusion() -> None:
    prompt = _slide(
        "slide:v5:example:prompt",
        title="根据条件完成判断",
        content="请依据给定条件完成推导并判断结论。",
        scene_kind="worked_example",
        block_type="exercise",
    )
    prompt["blocks"][0]["metadata"].update({
        "question_id": "question-linked",
        "question_mode": "closed",
    })
    answer = _slide(
        "slide:v5:example:answer",
        title="推导结果与理由",
        content="结论成立，因为两个来源条件均已满足。",
        scene_kind="practice_feedback",
        block_type="callout",
    )
    answer["blocks"][0]["title"] = "答案"
    answer["blocks"][0]["metadata"].update({
        "answer_for": "question-linked",
        "source_fragment_id": "fragment-answer",
    })

    report = build_slide_deck_quality_v5([prompt, answer])

    assert "worked_example_conclusion_missing" not in {
        issue["code"] for issue in report["issues"]
    }


def test_open_worked_example_accepts_source_backed_analysis_as_conclusion() -> None:
    slide = _slide(
        "slide:v5:example:analysis",
        title="根据条件解释判断依据",
        content="推导依据：来源材料中的两个条件共同支持这一判断。",
        scene_kind="worked_example",
        block_type="exercise",
    )
    slide["blocks"][0]["metadata"].update({
        "question_mode": "open_discussion",
        "fragment_ids": ["fragment-analysis"],
    })

    report = build_slide_deck_quality_v5([slide])

    assert "worked_example_conclusion_missing" not in {
        issue["code"] for issue in report["issues"]
    }


def test_four_domain_styles_use_the_same_generic_quality_contract() -> None:
    structure = _slide(
        "slide:v5:structure:001",
        title="对象之间的空间关系决定观察顺序",
        content="先辨认两个对象，再依据材料说明它们的相对位置与连接关系。",
        scene_kind="structure",
    )
    structure["visuals"] = [{
        "kind": "relational_diagram",
        "alt_text": "两个对象及其空间关系",
    }]
    structure["quality"]["need_visual"] = True

    formula = _slide(
        "slide:v5:formula:001",
        title="公式与解释共同支持数量结论",
        content="公式给出数量关系，正文解释变量含义以及结论成立的条件。",
        scene_kind="concept",
    )
    formula["quality"]["resolved_layout"] = "formula-explanation"
    formula["visuals"] = [{"kind": "formula", "alt_text": "来源公式"}]

    narrative = _slide(
        "slide:v5:narrative:001",
        title="事件顺序解释了结果如何形成",
        content="材料先交代背景，再呈现关键转折，最后说明该转折带来的影响。",
        scene_kind="concept",
    )

    process = _slide(
        "slide:v5:process:001",
        title="完整流程从输入走向可检查结果",
        content="流程从明确输入开始，依次完成关键步骤，并产出可以复核的结果。",
        scene_kind="process",
    )
    process["quality"]["process_result"] = "产出可以复核的结果"

    report = build_slide_deck_quality_v5([
        structure,
        formula,
        narrative,
        process,
    ])

    assert report["passed"] is True
    assert report["blockers"] == []
