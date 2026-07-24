"""视频一“课程随知识更新”的确定性人工智能通识课预置。"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any

from course_document import (
    COURSE_DOCUMENT_SCHEMA,
    CourseBlock,
    CourseDocument,
    CourseSection,
    refresh_document_revision,
)
from course_revisions import revision_vector_for_document
from representation_compiler import compile_core_representations
from storage import Storage
from teaching_representations import TeachingRepresentationRepository


COURSE_ID = "demo-ai-literacy-update-v1"
COURSE_TITLE = "人工智能通识课"
TARGET_SECTION_ID = "ai-sec-17"
BASELINE_GOAL = "直接介绍 DeepSeek V3.2 的核心能力与典型应用"
TARGET_GOAL = "以 DeepSeek V4 为当前主线，并回顾 V3.2 的关键能力与技术演进"
FOLLOWUP_GOAL = "先回顾 DeepSeek V3.2，再比较 V4 的核心变化、能力边界与应用场景"

_CREATED_AT = "2026-07-24T00:00:00+00:00"
_LESSONS = (
    ("认识人工智能", "区分人工智能、机器学习与生成式人工智能的基本概念。"),
    ("数据如何教会机器", "理解数据、标签与训练之间的关系。"),
    ("机器学习的三种任务", "识别分类、回归与聚类的典型使用场景。"),
    ("神经网络入门", "用直观方式理解神经元、层与参数。"),
    ("大语言模型如何工作", "理解预测下一个词与语言生成的基本机制。"),
    ("提示词设计基础", "能够写出目标、背景、约束和输出格式清楚的提示词。"),
    ("让 AI 使用资料", "理解检索增强生成如何让回答基于指定资料。"),
    ("多模态 AI", "认识文本、图像、语音与视频模型的协同方式。"),
    ("AI 搜索与信息核验", "能够检查来源、时间与证据是否支持结论。"),
    ("AI 写作助手", "把构思、成稿、核验和修改组织成可检查流程。"),
    ("AI 数据分析", "理解表格分析、可视化与结论核验的基本步骤。"),
    ("AI 编程助手", "认识代码生成、测试与人工审查之间的分工。"),
    ("智能体与工具调用", "理解 AI 如何拆解任务并调用外部工具。"),
    ("AI 工作流设计", "把复杂任务组织成输入、处理、检查和确认环节。"),
    ("AI 幻觉与可信度", "识别模型不确定性并建立事实核验机制。"),
    ("隐私、版权与伦理", "判断使用 AI 时的数据、版权和责任边界。"),
    ("DeepSeek 核心能力与应用", BASELINE_GOAL),
    ("设计 AI 论文助手", "把检索、比较、核验、引用和人工确认组合成完整项目。"),
    ("个人 AI 学习系统", "设计能够积累证据并持续调整的个人学习流程。"),
    ("综合项目展示", "完成一个有真实输入、过程证据与人工确认的 AI 项目。"),
)

def build_video1_course_document() -> CourseDocument:
    sections = [
        _lesson(index, title, objective)
        for index, (title, objective) in enumerate(_LESSONS, start=1)
    ]
    blocks: list[CourseBlock] = []
    for index, (title, objective) in enumerate(_LESSONS, start=1):
        blocks.extend(
            _target_blocks() if index == 17 else _compact_lesson_blocks(index, title, objective)
        )
    target = sections[16]
    target.attributes = {
        **target.attributes,
        "demo_baseline_goal": BASELINE_GOAL,
        "demo_target_goal": TARGET_GOAL,
        "demo_followup_goal": FOLLOWUP_GOAL,
        "demo_same_source_block_ids": [block.block_id for block in _target_blocks()],
    }
    return refresh_document_revision(CourseDocument(
        course_id=COURSE_ID,
        title=COURSE_TITLE,
        sections=sections,
        blocks=blocks,
    ))


def build_video1_course_envelope() -> dict[str, Any]:
    document = build_video1_course_document()
    return {
        "course_id": COURSE_ID,
        "course_name": COURSE_TITLE,
        "course_description": "面向大学生的 20 讲人工智能通识课程，覆盖原理、工具、可信使用与项目实践。",
        "course_purpose": "systematic",
        "target_audience": "大学生与非技术专业学习者",
        "difficulty": "beginner",
        "style": "visual",
        "estimated_hours": 20,
        "generation_status": "passed",
        "generation_schema_version": "manual_video1_ai_demo_v1",
        "generation_source": "curated_local_preset",
        "course_schema_version": COURSE_DOCUMENT_SCHEMA,
        "course_document": document.model_dump(mode="json"),
        "course_document_revision": document.document_revision,
        "course_revision_vector": revision_vector_for_document(document).model_dump(mode="json"),
        "course_document_authoritative": True,
        "current_course_version_id": document.document_revision,
        "course_operation_log": [],
        "created_at": _CREATED_AT,
        "updated_at": _CREATED_AT,
        "demo_metadata": {
            "schema_version": "video_demo_preset_v1",
            "video": "课程随知识更新",
            "lesson_count": 20,
            "target_section_id": TARGET_SECTION_ID,
            "baseline_goal": BASELINE_GOAL,
            "target_goal": TARGET_GOAL,
            "followup_goal": FOLLOWUP_GOAL,
            "external_model_required": False,
        },
    }


def prepare_video1_demo(data_dir: str | Path) -> dict[str, Any]:
    root = Path(data_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    _clear_previous_demo_state(root)

    course = build_video1_course_envelope()
    storage = Storage(str(root))
    storage.delete_course(COURSE_ID)
    storage.save_course_sync(COURSE_ID, course)

    document = CourseDocument.model_validate(course["course_document"])
    repository = TeachingRepresentationRepository(root / "teaching_representations")
    build = compile_core_representations(document, course, repository)
    registry = repository.load(COURSE_ID)
    slide_representation = next(
        item for item in registry.representations if item.representation_type == "slide_deck"
    )
    slide_spec = next(item for item in registry.specs if item.spec_id == slide_representation.spec_id)
    slides = slide_spec.payload["content"]["slides"]
    target_index = next(
        index
        for index, slide in enumerate(slides)
        if slide.get("section_id") == TARGET_SECTION_ID
    )
    target_slide = slides[target_index]
    if target_slide.get("key_message") != BASELINE_GOAL:
        raise RuntimeError("视频一目标页未生成预期的 V3.2 初始内容")
    return {
        "course_id": COURSE_ID,
        "course_title": COURSE_TITLE,
        "lesson_count": len(_LESSONS),
        "target_section_id": TARGET_SECTION_ID,
        "target_slide_unit_id": target_slide["unit_id"],
        "target_slide_number": target_index + 1,
        "baseline_goal": BASELINE_GOAL,
        "target_goal": TARGET_GOAL,
        "followup_goal": FOLLOWUP_GOAL,
        "course_revision": document.document_revision,
        "representation_registry_revision": registry.registry_revision,
        "compiled_representation_count": len(build["representations"]),
        "course_file": str(root / "courses" / f"{COURSE_ID}.json"),
        "relative_url": f"/course/{COURSE_ID}/ppt",
        "external_model_required": False,
    }


def _lesson(index: int, title: str, objective: str) -> CourseSection:
    section_id = f"ai-sec-{index:02d}"
    objective_id = f"ai-obj-{index:02d}"
    return CourseSection(
        section_id=section_id,
        title=f"第{index:02d}讲 {title}",
        position=index - 1,
        level=1,
        learning_objective=objective,
        objective_id=objective_id,
        objective_revision_id=f"{objective_id}-r1",
        attributes={
            "key_points": [title, "真实场景", "可信使用"],
            "estimated_minutes": 45,
            "difficulty": "beginner" if index <= 10 else "intermediate",
        },
    )


def _compact_lesson_blocks(index: int, title: str, objective: str) -> list[CourseBlock]:
    return [
        _block(
            index,
            "overview",
            0,
            f"{title}：从问题出发",
            f"本讲围绕一个真实任务展开。学习完成后，学生需要能够：{objective}",
            role="orientation",
        ),
        _block(
            index,
            "check",
            1,
            "学习检查",
            "用一个具体案例说明本讲方法解决了什么问题，并指出仍需人工核验的环节。",
            role="checkpoint",
            kind="practice_ref",
        ),
    ]


def _target_blocks() -> list[CourseBlock]:
    index = 17
    return [
        _block(
            index,
            "context",
            0,
            "课程进行到第 17 讲",
            "20 讲课程已经准备完成。讲到第 17 讲时，新版本发布，教师需要更新本讲，"
            "同时检查大纲、教案、讲义、PPT 和练习是否仍然一致。",
            role="orientation",
        ),
        _block(
            index,
            "objective",
            1,
            "本讲目标",
            "认识当前版本的核心能力、典型场景与使用边界，并能解释它相对上一版本的关键变化。",
            role="objective",
            kind="callout",
        ),
        _block(
            index,
            "v32-overview",
            2,
            "认识 DeepSeek V3.2",
            "本讲以 DeepSeek V3.2 为当前版本，重点理解它如何处理复杂指令、组织长文本，"
            "并在代码、资料研读和结构化写作等任务中提供可检查的输出。",
            role="concept",
        ),
        _block(
            index,
            "reasoning",
            3,
            "能力一：复杂任务分解",
            "面对“阅读资料并形成报告”这类复合任务，先明确目标与约束，再拆成提取信息、"
            "比较观点、组织证据和生成结论四步；每一步都保留中间结果，便于人工纠错。",
            role="reasoning",
        ),
        _block(
            index,
            "structured-output",
            4,
            "能力二：代码与结构化输出",
            "模型可以按照表格、JSON 或分步骤清单输出结果，也能辅助解释和修改代码。"
            "结构化格式让结果更容易复用，但字段完整、代码可运行不等于内容一定正确。",
            role="concept",
        ),
        _block(
            index,
            "grounded-answer",
            5,
            "能力三：基于资料回答",
            "先限定资料范围，再要求回答标注原文依据。学习者要区分“模型根据材料归纳的内容”"
            "和“模型自行补充的判断”，避免把流畅表达误当成可靠证据。",
            role="concept",
        ),
        _block(
            index,
            "case-paper",
            6,
            "完整案例：做一个 AI 论文助手",
            "输入 3 篇课程论文后，让模型分别提取研究问题、研究方法和主要结论，"
            "再比较不同论文的证据。每条结论必须保留论文来源、页码或原文片段。",
            role="example",
        ),
        _block(
            index,
            "workflow",
            7,
            "从一句提示词到可复用流程",
            "明确研究问题 → 限定资料范围 → 分篇提取证据 → 比较结论 → 标注引用 → 检查遗漏"
            " → 人工确认。模型负责提高处理效率，学生负责研究判断和最终结论。",
            role="application",
            kind="project",
        ),
        _block(
            index,
            "boundary",
            8,
            "能力边界：三类结果不能直接相信",
            "没有来源的事实、无法定位的引用、超出材料范围的推断，都不能直接进入报告。"
            "遇到信息不足时，应明确标记“不足以判断”，而不是要求模型补出一个答案。",
            role="misconception",
            kind="callout",
        ),
        _block(
            index,
            "version-view",
            9,
            "为什么课程还要关注版本变化",
            "同一个任务在新版本发布后，任务理解、工具调用和输出质量可能变化。"
            "课程更新不能只替换版本号，而要重做案例、讲解重点、比较维度和检查标准。",
            role="concept",
        ),
        _block(
            index,
            "comparison",
            10,
            "用同一任务比较新旧版本",
            "选择同一组论文、同一研究问题和同一输出格式，比较任务理解、来源使用、"
            "结论质量与人工修订次数。只有输入和评价标准一致，版本对照才有意义。",
            role="reasoning",
        ),
        _block(
            index,
            "activity",
            11,
            "课堂活动：找出一条不可靠结论",
            "两人一组检查论文助手生成的对比表，定位一条缺少来源或过度推断的结论，"
            "补回原文证据；若证据不足，就将该结论退回而不是润色。",
            role="activity",
            kind="project",
        ),
        _block(
            index,
            "check",
            12,
            "本讲理解检查",
            "提交一个可运行的 AI 论文助手流程：至少处理 3 篇论文，输出研究问题、方法、"
            "结论和来源依据；无来源结论不得进入最终报告，并说明哪些环节必须人工确认。",
            role="checkpoint",
            kind="practice_ref",
        ),
        _block(
            index,
            "summary",
            13,
            "本讲小结",
            "DeepSeek V3.2 可以帮助分解复杂任务、处理资料并生成结构化结果；"
            "真正可靠的使用方式，是限定来源、保留证据、检查边界并由使用者确认结论。",
            role="summary",
        ),
    ]


def _block(
    lesson_index: int,
    suffix: str,
    position: int,
    title: str,
    markdown: str,
    *,
    role: str,
    kind: str = "rich_text",
) -> CourseBlock:
    section_id = f"ai-sec-{lesson_index:02d}"
    objective_id = f"ai-obj-{lesson_index:02d}"
    return CourseBlock(
        block_id=f"ai-b-{lesson_index:02d}-{suffix}",
        section_id=section_id,
        position=position,
        kind=kind,
        role=role,
        payload={"title": title, "markdown": markdown, "summary": markdown},
        objective_refs=[objective_id],
        status="final",
    )


def _clear_previous_demo_state(data_dir: Path) -> None:
    courses_dir = data_dir / "courses"
    if courses_dir.exists():
        for path in courses_dir.glob(f"{COURSE_ID}*.json"):
            path.unlink()
    for directory_name in (
        "learning_assets",
        "question_banks",
        "course_versions",
        "teaching_representations",
        "generation_workspaces",
    ):
        directory = data_dir / directory_name / COURSE_ID
        if directory.exists():
            shutil.rmtree(directory)
        file_path = data_dir / directory_name / f"{COURSE_ID}.json"
        if file_path.exists():
            file_path.unlink()
    for directory_name in (
        "teaching_representations",
        "change_proposals",
        "block_regeneration_candidates",
    ):
        _remove_scoped_json_files(data_dir / directory_name)
    _filter_learning_events(data_dir / "learning_events.json")


def _remove_scoped_json_files(directory: Path) -> None:
    if not directory.exists():
        return
    for path in directory.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if _payload_belongs_to_course(payload):
            path.unlink()


def _payload_belongs_to_course(payload: Any) -> bool:
    if isinstance(payload, dict):
        if str(payload.get("course_id") or "") == COURSE_ID:
            return True
        rows = [
            row
            for key in ("conversations", "proposals", "receipts", "suppressions")
            for row in (payload.get(key) or [])
            if isinstance(row, dict)
        ]
        return bool(rows) and all(str(row.get("course_id") or "") == COURSE_ID for row in rows)
    if isinstance(payload, list) and payload:
        return all(
            isinstance(row, dict) and str(row.get("course_id") or "") == COURSE_ID
            for row in payload
        )
    return False


def _filter_learning_events(path: Path) -> None:
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if isinstance(payload, list):
        filtered = [
            item for item in payload
            if not isinstance(item, dict) or str(item.get("course_id") or "") != COURSE_ID
        ]
        if filtered != payload:
            path.write_text(f"{json.dumps(filtered, ensure_ascii=False, indent=2)}\n", encoding="utf-8")


__all__ = [
    "BASELINE_GOAL",
    "COURSE_ID",
    "COURSE_TITLE",
    "FOLLOWUP_GOAL",
    "TARGET_GOAL",
    "TARGET_SECTION_ID",
    "build_video1_course_document",
    "build_video1_course_envelope",
    "prepare_video1_demo",
]
