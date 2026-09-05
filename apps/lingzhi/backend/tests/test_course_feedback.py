from course_feedback import (
    FEEDBACK_SCHEMA_VERSION,
    compile_feedback_structure,
    enrich_feedback_payload,
)


def test_legacy_bold_task_headings_compile_to_stable_feedback_sections():
    markdown = (
        "**任务1 答案方向**：\n1. 第一项\n2. 第二项\n\n"
        "**任务2 反馈**：\n- 对照运行结果。\n\n"
        "**任务3 评价标准**：\n- 说明判断依据。\n\n---"
    )

    structure = compile_feedback_structure(markdown)

    assert structure["schema_version"] == FEEDBACK_SCHEMA_VERSION
    assert structure["mode"] == "static_reference"
    assert [section["title"] for section in structure["sections"]] == [
        "任务1 答案方向",
        "任务2 反馈",
        "任务3 评价标准",
    ]
    assert [section["kind"] for section in structure["sections"]] == [
        "reference_answer",
        "task_review",
        "rubric",
    ]
    assert all(section["collapsed_by_default"] for section in structure["sections"])
    assert all(section["section_id"].startswith("feedback-section-") for section in structure["sections"])


def test_level_three_feedback_headings_are_the_new_structured_contract():
    structure = compile_feedback_structure(
        "### 任务 1：判断\n\n**核对标准**：写出条件。\n\n"
        "### 任务 2：验证\n\n**参考结论**：继续扩大规模。"
    )

    assert len(structure["sections"]) == 2
    assert structure["sections"][0]["title"] == "任务 1：判断"
    assert structure["sections"][1]["title"] == "任务 2：验证"


def test_feedback_payload_recompiles_only_when_markdown_changes():
    payload = enrich_feedback_payload({"title": "检查与反馈", "markdown": "简短核对说明。"})
    first = payload["feedback_structure"]

    unchanged = enrich_feedback_payload(payload)
    changed = enrich_feedback_payload({**payload, "markdown": "已经变化的核对说明。"})

    assert unchanged["feedback_structure"] == first
    assert changed["feedback_structure"]["source_fingerprint"] != first["source_fingerprint"]
