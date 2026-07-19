"""Page-level resume must reuse finished slides instead of recompiling them."""

from __future__ import annotations

import json
from copy import deepcopy

import slide_deck
from course_document import document_from_legacy_course

RESUMED_PAGE_COUNT = 6


def advanced_python_course(section_count: int = 25) -> dict:
    """A demo-sized course large enough to exercise the compressed deck plan."""
    roles = ("concept", "reasoning", "example", "application")
    nodes = []
    for index in range(section_count):
        section_number = index + 1
        nodes.append({
            "node_id": f"advanced-python-{section_number}",
            "parent_node_id": "root",
            "node_name": f"Advanced Python 核心主题 {section_number}",
            "node_level": 1,
            "learning_objective": f"能够解释并应用 Python 主题 {section_number}",
            "objective_id": f"objective-{section_number}",
            "concept_refs": [f"python-concept-{section_number}"],
            "content_blocks": [{
                "block_id": f"advanced-python-{section_number}-block",
                "title": f"主题 {section_number} 的关键判断",
                "content": (
                    f"主题 {section_number} 解决一个具体的 Python 工程问题。\n\n"
                    f"先识别主题 {section_number} 的适用条件。\n\n"
                    f"再比较常见做法与推荐做法。\n\n"
                    f"最后用一个小例子验证主题 {section_number}。"
                ),
                "metadata": {"role": roles[index % len(roles)]},
            }],
        })
    return {
        "course_id": "advanced-python-resume",
        "course_name": "Advanced Python",
        "nodes": nodes,
        "learning_assets": {
            "questions": [{
                "question_id": "python-practice-1",
                "revision_id": "python-practice-1-r1",
                "node_id": "advanced-python-8",
                "prompt": "说明主题 8 的适用边界，并给出一个最小示例。",
            }],
            "misconceptions": [],
        },
    }


def _canonical_bytes(value: dict) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _upserted_slides(events: list[dict]) -> list[dict]:
    return [event["slide"] for event in events if event["event"] == "slide_upsert"]


def _first_build() -> tuple[dict, list[dict], dict, list]:
    course = advanced_python_course()
    document = document_from_legacy_course(course)
    events: list[dict] = []
    content = slide_deck.compile_slide_deck(
        document,
        course,
        progress_callback=events.append,
    )
    return content, events, course, document


def test_first_build_emits_one_upsert_per_compiled_page():
    content, events, _, _ = _first_build()

    upserted = _upserted_slides(events)

    assert 12 <= len(content["slides"]) <= 18
    assert [item["unit_id"] for item in upserted] == [
        item["unit_id"] for item in content["slides"]
    ]
    assert content["quality_summary"]["passed"] is True


def test_resume_reuses_finished_pages_without_replanning_or_regenerating():
    content, _, course, document = _first_build()
    original_slides = deepcopy(content["slides"])
    resume_slides = deepcopy(original_slides[:RESUMED_PAGE_COUNT])
    resumed_ids = [item["unit_id"] for item in resume_slides]

    events: list[dict] = []
    resumed_content = slide_deck.compile_slide_deck(
        document,
        course,
        progress_callback=events.append,
        resume_slides=resume_slides,
    )

    upserted = _upserted_slides(events)
    upserted_ids = [item["unit_id"] for item in upserted]
    resumed_by_id = {item["unit_id"]: item for item in resumed_content["slides"]}

    # 1. No resumed page is re-emitted to the caller.
    assert not set(resumed_ids) & set(upserted_ids)

    # 2. Every resumed page survives byte-identical to the first build.
    for index, unit_id in enumerate(resumed_ids):
        assert _canonical_bytes(resumed_by_id[unit_id]) == _canonical_bytes(
            original_slides[index],
        )

    # 3. The remaining pages are still compiled and emitted.
    remaining_ids = [item["unit_id"] for item in original_slides[RESUMED_PAGE_COUNT:]]
    assert upserted_ids == remaining_ids
    assert len(upserted_ids) == len(original_slides) - RESUMED_PAGE_COUNT

    # 4. Positions stay contiguous and the deck is unchanged as a whole.
    assert [item["position"] for item in resumed_content["slides"]] == list(
        range(len(resumed_content["slides"])),
    )
    assert [item["unit_id"] for item in resumed_content["slides"]] == [
        item["unit_id"] for item in original_slides
    ]
    assert resumed_content["quality_summary"]["passed"] is True


def test_resume_skips_materializing_finished_pages(monkeypatch):
    """A savepoint must save compute, not merely discard duplicate output."""
    content, _, course, document = _first_build()
    resume_slides = deepcopy(content["slides"][:RESUMED_PAGE_COUNT])
    resumed_ids = {item["unit_id"] for item in resume_slides}

    materialized: list[str] = []
    original = slide_deck._materialize_planned_slide

    def spy(planned, *args, **kwargs):
        materialized.append(planned.slide_id)
        return original(planned, *args, **kwargs)

    monkeypatch.setattr(slide_deck, "_materialize_planned_slide", spy)
    slide_deck.compile_slide_deck(document, course, resume_slides=resume_slides)

    assert not resumed_ids & set(materialized)


def test_resume_ignores_pages_that_no_longer_match_the_slide_contract():
    content, _, course, document = _first_build()
    corrupted = deepcopy(content["slides"][:2])
    corrupted[0]["layout"] = "not-a-real-layout"

    events: list[dict] = []
    resumed_content = slide_deck.compile_slide_deck(
        document,
        course,
        progress_callback=events.append,
        resume_slides=corrupted,
    )

    upserted_ids = [item["unit_id"] for item in _upserted_slides(events)]

    # The invalid page falls back to a fresh compile; the valid one is reused.
    assert corrupted[0]["unit_id"] in upserted_ids
    assert corrupted[1]["unit_id"] not in upserted_ids
    assert [item["unit_id"] for item in resumed_content["slides"]] == [
        item["unit_id"] for item in content["slides"]
    ]


def test_resume_recovers_the_full_deck_after_a_mid_build_interruption():
    course = advanced_python_course()
    document = document_from_legacy_course(course)

    class _Interrupted(RuntimeError):
        pass

    partial: list[dict] = []

    def interrupting_callback(event: dict) -> None:
        if event["event"] != "slide_upsert":
            return
        partial.append(deepcopy(event["slide"]))
        if len(partial) == RESUMED_PAGE_COUNT:
            raise _Interrupted

    try:
        slide_deck.compile_slide_deck(
            document,
            course,
            progress_callback=interrupting_callback,
        )
    except _Interrupted:
        pass

    assert len(partial) == RESUMED_PAGE_COUNT

    events: list[dict] = []
    recovered = slide_deck.compile_slide_deck(
        document,
        course,
        progress_callback=events.append,
        resume_slides=partial,
    )

    upserted_ids = [item["unit_id"] for item in _upserted_slides(events)]
    recovered_by_id = {item["unit_id"]: item for item in recovered["slides"]}

    assert not set(item["unit_id"] for item in partial) & set(upserted_ids)
    for saved in partial:
        assert _canonical_bytes(recovered_by_id[saved["unit_id"]]) == _canonical_bytes(saved)
    assert [item["position"] for item in recovered["slides"]] == list(
        range(len(recovered["slides"])),
    )
    assert recovered["quality_summary"]["passed"] is True
