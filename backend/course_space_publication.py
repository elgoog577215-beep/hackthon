"""Publish generated course artifacts into the teacher's course file space.

The teacher's acceptance test is "create a course, upload material, generate, and
the artifacts show up in the file system without ever leaving the workbench".
Generation already produced everything; this module is the last hop that was
missing -- ``course_service`` and the course space had no reference to each other,
so the file space was an island.

Three properties this module owes the caller, in priority order:

1. **Never fail the generation.** Artifacts are already produced and persisted by
   the time we run. A file-space problem is reported, never raised -- the course
   must survive a full disk or a permission error.
2. **Idempotent.** Re-running generation must not duplicate entries, and must
   never clobber a file the teacher uploaded by hand. Dedupe is by
   ``(relative_path, sha256)``, mirroring the existing import path; a manually
   uploaded file at the same path is left untouched and reported as a conflict.
3. **Legible layout.** Artifacts land in the school template's own folders
   (教学大纲 / 教案 / PPT) under an ``AI 生成`` subdirectory, so they match how
   teachers already archive while staying visually separable from their uploads.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path, PurePosixPath
from typing import Any
import uuid

from course_authoring_templates import (
    compile_formal_course_context,
    project_lesson_objective_dimensions,
)
from teacher_course_space import (
    MaterialStorageError,
    classify_path,
    normalize_relative_path,
    teacher_course_space_repository,
)

logger = logging.getLogger(__name__)

PUBLISH_SCHEMA_VERSION = "course_artifact_publication_v1"

# The generated-artifact subdirectory. Kept as one constant because it is the
# marker that separates "the system wrote this" from "the teacher uploaded this",
# and the conflict check below depends on that distinction.
GENERATED_DIR = "AI 生成"

_OUTLINE_FOLDER = "0、教学大纲"
_LESSON_FOLDER = "1、教案"
_SLIDES_FOLDER = "2、PPT"


MISSING_TEACHER_IDENTITY = "missing_teacher_identity"
MISSING_COURSE_ID = "missing_course_id"
NO_COURSE_SPACE_PACKAGE = "no_course_space_package"

# Human-facing explanation per skip reason. A caller that only logs
# ``status=skipped`` would leave the teacher guessing, and "入库失败" without a
# cause is the kind of message that turns a fixable setup problem into a support
# ticket. Each reason therefore carries what went wrong and what to do.
SKIP_MESSAGES = {
    MISSING_TEACHER_IDENTITY: (
        "缺少教师身份（X-User-Id），未创建课程包也未写入任何文件；"
        "请在请求头带上教师身份后重试"
    ),
    MISSING_COURSE_ID: (
        "课程缺少 course_id，无法与课程包建立绑定；未创建课程包也未写入任何文件"
    ),
    NO_COURSE_SPACE_PACKAGE: (
        "该课程没有绑定的教师课程空间，且当前调用不允许自动创建；未写入任何文件"
    ),
    "no_publishable_artifact": (
        "这门课当前没有可归档的产物（大纲/教案/正文都为空）；未写入任何文件"
    ),
}


def _digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _safe_segment(value: str, *, fallback: str) -> str:
    """Make one path segment safe without losing the teacher-facing name."""
    text = str(value or "").strip()
    for bad in ("/", "\\", ":", "*", "?", '"', "<", ">", "|", "\n", "\r", "\t"):
        text = text.replace(bad, "_")
    text = text.strip(". ")
    if not text:
        return fallback
    return text[:80]


def _md_cell(value: Any) -> str:
    """Keep deterministic projections valid inside Markdown tables."""
    return " ".join(str(value or "").split()).replace("|", "\\|")


def _text_items(value: Any) -> list[str]:
    if isinstance(value, str):
        values = value.splitlines()
    elif isinstance(value, list):
        values = value
    else:
        values = []
    return list(dict.fromkeys(
        text
        for item in values
        if (text := " ".join(str(item or "").split()))
    ))


def _first_items(source: dict[str, Any], *keys: str) -> list[str]:
    for key in keys:
        values = _text_items(source.get(key))
        if values:
            return values
    return []


def _outline_lessons(chapters: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    lecture = 0
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        chapter_title = str(chapter.get("title") or "").strip()
        for section in chapter.get("sections") or []:
            if not isinstance(section, dict):
                continue
            lecture += 1
            result.append({
                **section,
                "chapter_title": chapter_title,
                "lecture": section.get("lecture") or section.get("lesson_number") or lecture,
                "week": section.get("week") or section.get("teaching_week") or lecture,
            })
    return result


def _lesson_title(section: dict[str, Any]) -> str:
    return " ".join(filter(None, (
        str(section.get("section_number") or "").strip(),
        str(section.get("title") or section.get("node_name") or "").strip(),
    )))


def _module_text(module: dict[str, Any]) -> str:
    parts = _text_items([
        module.get("teacher_activity"),
        module.get("student_activity"),
    ])
    return "；".join(parts)


def _lesson_flow_items(section: dict[str, Any], flow: str) -> list[str]:
    explicit_keys = {
        "课前预习": ("pre_study", "prestudy", "pre_class_tasks", "preparation"),
        "重点分析": ("key_analysis",),
        "案例导入": ("case_intro", "case_introduction"),
        "知识讲解与讨论": ("knowledge_explanation_discussion", "explanation_discussion"),
        "实践操作": ("practice", "practice_tasks"),
        "课堂总结": ("summary", "class_summary"),
        "课后作业": ("homework",),
        "拓展学习": ("extension_learning", "extension", "further_learning"),
        "教学活动照片": ("activity_photos", "teaching_activity_photos"),
    }
    explicit = _first_items(section, *explicit_keys[flow])
    if explicit:
        return explicit
    if flow == "重点分析":
        return [
            *(f"重点：{item}" for item in _text_items(section.get("key_points"))),
            *(f"难点：{item}" for item in _text_items(section.get("key_difficulties"))),
        ]
    if flow == "实践操作":
        checks = _text_items(section.get("in_class_checks"))
        if checks:
            return checks
    module_signals = {
        "案例导入": ("case", "intro", "opening", "scenario"),
        "知识讲解与讨论": ("explanation", "discussion", "core", "concept"),
        "实践操作": ("practice", "learner", "experiment", "exercise", "activity"),
        "课堂总结": ("summary", "reflection", "closure"),
    }
    signals = module_signals.get(flow, ())
    if not signals:
        return []
    result: list[str] = []
    for module in section.get("teaching_modules") or []:
        if not isinstance(module, dict):
            continue
        module_id = str(module.get("module_id") or "").lower()
        label = str(module.get("label") or "")
        if signals and not any(signal in module_id for signal in signals):
            continue
        text = _module_text(module)
        if text:
            result.append(f"{label}：{text}" if label else text)
    return result


def build_course_artifact_documents(course_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Render the course into the markdown documents that belong in the space.

    Pure function: no I/O, no course mutation. Returns ``relative_path`` +
    ``content`` pairs so the layout can be asserted in tests without touching a
    repository, and so callers can diff what *would* be written.
    """
    documents: list[dict[str, Any]] = []
    course_name = _safe_segment(course_data.get("course_name"), fallback="课程")

    outline = _render_outline(course_data)
    if outline:
        documents.append({
            "relative_path": f"{_OUTLINE_FOLDER}/{GENERATED_DIR}/{course_name}-课程大纲.md",
            "content": outline,
            "artifact_type": "course_outline",
        })

    teaching_plan = _render_teaching_plan(course_data)
    if teaching_plan:
        documents.append({
            "relative_path": f"{_LESSON_FOLDER}/{GENERATED_DIR}/{course_name}-全课教案.md",
            "content": teaching_plan,
            "artifact_type": "course_teaching_plan",
        })

    documents.extend(_render_section_documents(course_data))
    documents.extend(_render_slide_documents(course_data))
    return documents


def _render_outline(course_data: dict[str, Any]) -> str:
    plan = (
        course_data.get("course_outline")
        or course_data.get("course_plan")
        or {}
    )
    chapters = plan.get("chapters") if isinstance(plan, dict) else None
    if not isinstance(chapters, list) or not chapters:
        return ""
    context = compile_formal_course_context(course_data, plan=plan)
    lines = [f"# {course_data.get('course_name') or '课程'}｜课程教学大纲", ""]

    information = context["course_information"]
    lines += ["## 一、课程基本信息", ""]
    if information:
        lines += ["| 项目 | 内容 |", "|---|---|"]
        lines.extend(
            f"| {_md_cell(label)} | {_md_cell(value)} |"
            for label, value in information.items()
        )
    else:
        lines.append("尚未确认课程基本信息。")
    lines.append("")

    lines += ["## 二、中英文课程简介", ""]
    if context["course_intro_zh"]:
        lines += ["### 中文简介", context["course_intro_zh"], ""]
    if context["course_intro_en"]:
        lines += ["### English Description", context["course_intro_en"], ""]
    if context["positioning"] and context["positioning"] != context["course_intro"]:
        lines += ["### 课程定位", context["positioning"], ""]
    if context["student_profile"]:
        lines += ["### 教学对象与学情", context["student_profile"], ""]
    if (
        not context["course_intro_zh"]
        and not context["course_intro_en"]
        and not context["positioning"]
        and not context["student_profile"]
    ):
        lines += ["尚未确认课程定位与简介。", ""]

    lines += ["## 三、教学目标", ""]
    objective_groups = (
        ("学习目标", context["learning_objectives"]),
        ("育人目标", _first_items(plan, "education_objectives", "育人目标")),
        ("可测量成果", _first_items(plan, "measurable_outcomes", "measurable_objectives", "可测量成果")),
    )
    for label, values in objective_groups:
        lines.append(f"### {label}")
        lines.extend([f"- {item}" for item in values] if values else ["尚未确认。"])
        lines.append("")

    lines += ["## 四、课程要求", ""]
    prerequisites = context["prerequisites"]
    coverage = _coverage_section(course_data)
    requirement_lines = []
    if prerequisites:
        requirement_lines.append(f"- 预修要求：{'；'.join(prerequisites)}")
    requirement_lines.extend(
        f"- {item}" for item in context["teaching_requirements"]
    )
    lines.extend(requirement_lines)
    if not requirement_lines and not coverage:
        lines.append("暂无额外课程要求。")
    lines.append("")

    if coverage:
        # Coverage is a requirement boundary, not another parallel outline
        # section. Keep the existing honesty verdict under the formal template.
        coverage[0] = "### 覆盖范围说明"
        lines += coverage

    lines += ["## 五、考核与成绩构成", ""]
    lines += (
        [f"- {item}" for item in context["assessment_methods"]]
        if context["assessment_methods"]
        else ["尚未确认课程考核方式。"]
    )
    lines.append("")

    outline_lessons = _outline_lessons(chapters)
    lines += [
        "## 六、按周与按讲教学进度", "",
        "| 周次 | 讲次 | 章节 | 主题 | 内容与目标 | 重难点 | 活动 | 作业 | 学时 |",
        "|---|---|---|---|---|---|---|---|---:|",
    ]
    for lesson in outline_lessons:
        hours = lesson.get("planned_hours") or lesson.get("credit_hours") or ""
        key_difficult = "；".join(
            _text_items(lesson.get("key_points"))
            + _text_items(lesson.get("key_difficulties"))
        )
        activities = "；".join(_text_items(
            lesson.get("activities") or lesson.get("student_activities")
        ))
        homework = "；".join(_text_items(lesson.get("homework")))
        lines.append(
            f"| {_md_cell(lesson['week'])} | {_md_cell(lesson['lecture'])} | "
            f"{_md_cell(lesson['chapter_title'])} | {_md_cell(_lesson_title(lesson))} | "
            f"{_md_cell(lesson.get('learning_objective'))} | {_md_cell(key_difficult)} | "
            f"{_md_cell(activities)} | {_md_cell(homework)} | {_md_cell(hours)} |"
        )
    lines.append("")

    lines += [
        "## 七、教学日历", "",
        "| 周次 | 讲次 | 教学主题 | 日期/地点 | 课前准备 |",
        "|---|---|---|---|---|",
    ]
    for lesson in outline_lessons:
        schedule = " / ".join(filter(None, (
            str(lesson.get("date") or "").strip(),
            str(lesson.get("location") or "").strip(),
        )))
        lines.append(
            f"| {_md_cell(lesson['week'])} | {_md_cell(lesson['lecture'])} | "
            f"{_md_cell(_lesson_title(lesson))} | {_md_cell(schedule or '待排课')} | "
            f"{_md_cell(lesson.get('pre_study') or lesson.get('preparation'))} |"
        )
    lines.append("")

    lines += [
        "## 八、课程思政案例", "",
        "| 讲次 | 课程内容 | 育人目标 | 案例与实施方式 |",
        "|---|---|---|---|",
    ]
    ideology_cases = [
        item for item in context["ideology_cases"] if isinstance(item, dict)
    ]
    if ideology_cases:
        for item in ideology_cases:
            lines.append(
                f"| {_md_cell(item.get('lecture') or item.get('lesson'))} | "
                f"{_md_cell(item.get('course_content') or item.get('content'))} | "
                f"{_md_cell(item.get('education_objective') or item.get('objective'))} | "
                f"{_md_cell(item.get('case') or item.get('implementation'))} |"
            )
    else:
        lines.append("| 待补充 | 待确认 | 待确认 | 待确认 |")
    lines.append("")

    lines += ["## 九、参考书目与网站", "", "### 参考书目"]
    books = context["reference_books"] or context["references"]
    lines.extend(
        [f"- {item}" for item in books]
        if books else ["暂无已确认参考书目。"]
    )
    lines += ["", "### 参考网站"]
    lines.extend(
        [f"- {item}" for item in context["reference_websites"]]
        if context["reference_websites"] else ["暂无已确认参考网站。"]
    )
    lines += [
        "", "## 十、课程网站", "",
        context["course_website"] or "暂未确认课程网站。",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _coverage_section(course_data: dict[str, Any]) -> list[str]:
    """Carry the D-1 coverage verdict into the archived outline.

    A teacher reading the exported outline months later must still see that this
    course was, say, a 微型课 that deliberately left topics out. Dropping the
    verdict here would recreate exactly the dishonesty D-1 exists to prevent.
    """
    verdict = (
        (course_data.get("generation_stage_artifacts") or {}).get("outline") or {}
    ).get("course_coverage_verdict")
    if not isinstance(verdict, dict) or not verdict:
        return []
    lines = ["## 覆盖范围说明"]
    label = str(verdict.get("scale_label") or "").strip()
    promise = str(verdict.get("coverage_promise") or "").strip()
    if label:
        lines.append(f"- 课程规格：{label}" + (f"（{promise}）" if promise else ""))
    hours = verdict.get("class_hours")
    if hours:
        lines.append(f"- 课时：{hours}")
    uncovered = [str(item) for item in verdict.get("uncovered_topics") or []]
    if uncovered:
        lines.append(f"- **本次不覆盖**：{'、'.join(uncovered)}")
    covered = [str(item) for item in verdict.get("covered_topics") or []]
    if covered:
        lines.append(f"- 已覆盖：{'、'.join(covered)}")
    lines.append("")
    return lines


def _render_teaching_plan(course_data: dict[str, Any]) -> str:
    plan = course_data.get("course_teaching_plan")
    sections = plan.get("sections") if isinstance(plan, dict) else None
    if not isinstance(sections, list) or not sections:
        return ""
    context = compile_formal_course_context(course_data)
    node_titles = {
        str(item.get("node_id") or ""): str(item.get("node_name") or "")
        for item in course_data.get("nodes") or []
        if isinstance(item, dict)
    }
    outline = course_data.get("course_outline") or course_data.get("course_plan") or {}
    if isinstance(outline, dict):
        for chapter in outline.get("chapters") or []:
            if not isinstance(chapter, dict):
                continue
            for item in chapter.get("sections") or []:
                if isinstance(item, dict):
                    node_titles.setdefault(
                        str(item.get("node_id") or ""),
                        " ".join(filter(None, (
                            str(item.get("section_number") or "").strip(),
                            str(item.get("title") or "").strip(),
                        ))),
                    )

    lines = [f"# {course_data.get('course_name') or '课程'}｜全课教案", ""]
    if context["course_information"]:
        lines += ["## 一、课程信息", "", "| 项目 | 内容 |", "|---|---|"]
        lines.extend(
            f"| {_md_cell(label)} | {_md_cell(value)} |"
            for label, value in context["course_information"].items()
        )
        lines.append("")
    if context["learning_objectives"]:
        lines += ["## 二、整体教学目标", ""]
        lines.extend(f"- {item}" for item in context["learning_objectives"])
        lines.append("")
    if context["positioning"]:
        lines += ["## 三、整体教学设计", "", context["positioning"], ""]

    lines += ["## 四、分讲教案", ""]
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("node_id") or "")
        title = str(section.get("node_name") or node_titles.get(section_id) or "").strip()
        lines.append(f"### {title or section_id}".rstrip())
        resource_refs = _text_items(section.get("resource_refs"))
        lines += ["", f"- **课程名称**：{course_data.get('course_name') or '尚未确认'}"]
        if resource_refs:
            lines.append(f"- **来源资料**：{'；'.join(resource_refs)}")
        lines.append("")

        objective_dimensions = project_lesson_objective_dimensions(section)
        for heading, objective_key in (
            ("知识目标", "知识目标"),
            ("能力目标", "能力目标"),
            ("育人目标", "育人目标"),
        ):
            lines.append(f"#### {heading}")
            values = objective_dimensions.get(objective_key) or []
            lines.extend([f"- {item}" for item in values] if values else ["尚未确认。"])
            lines.append("")

        key_points = _text_items(section.get("key_points"))
        difficulties = _text_items(section.get("key_difficulties"))
        lines += ["#### 教学重点与难点"]
        lines.append(f"- 教学重点：{'；'.join(key_points) or '尚未确认'}")
        lines.append(f"- 教学难点：{'；'.join(difficulties) or '尚未确认'}")
        lines.append("")

        lines += [
            "#### 课前准备（按需）",
            *(
                [f"- {item}" for item in _lesson_flow_items(section, "课前预习")]
                or ["尚未确认。"]
            ),
            "",
            "#### 课堂教学过程",
            "",
            "| 教学块 | 时间 | 本块目标与内容 | 教师活动 | 学生活动 | 课堂产出与达成检查 | 反馈与调整 | 衔接 | 讲义与 PPT 对应 |",
            "|---|---:|---|---|---|---|---|---|---|",
        ]
        modules = [
            item for item in section.get("teaching_modules") or []
            if isinstance(item, dict)
        ]
        for module in modules:
            minutes = module.get("planned_minutes")
            time_label = f"{minutes} 分钟" if minutes not in (None, "") else ""
            lines.append(
                f"| {_md_cell(module.get('label') or module.get('module_id'))} | {_md_cell(time_label)} | "
                f"{_md_cell(module.get('teaching_purpose') or module.get('teaching_guidance'))} | "
                f"{_md_cell(module.get('teacher_activity'))} | {_md_cell(module.get('student_activity'))} | "
                f"{_md_cell('；'.join(filter(None, (str(module.get('expected_output') or ''), str(module.get('check_method') or '')))))} | "
                f"{_md_cell('；'.join([str(module.get('feedback_strategy') or ''), *_text_items(module.get('adaptation_options'))]))} | "
                f"{_md_cell(module.get('transition'))} | {_md_cell(module.get('handout_ppt_mapping'))} |"
            )
        if not modules:
            lines.append("| 待完善 |  | 尚未确认可执行教学流程 |  |  |  |  |  |  |")
        lines.append("")

        for flow in (
            "课堂总结", "课后作业", "拓展学习", "教学活动照片",
        ):
            heading = {
                "课堂总结": "课程总结",
                "课后作业": "作业布置",
                "拓展学习": "拓展学习",
                "教学活动照片": "教学资料与活动记录｜教学活动照片",
            }[flow]
            lines.append(f"#### {heading}")
            values = _lesson_flow_items(section, flow)
            empty = (
                "待教师补充，不编造照片。"
                if flow == "教学活动照片"
                else "尚未确认。"
            )
            lines.extend([f"- {item}" for item in values] if values else [empty])
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_section_documents(course_data: dict[str, Any]) -> list[dict[str, Any]]:
    """One markdown file per section, filed under its chapter."""
    nodes = [item for item in course_data.get("nodes") or [] if isinstance(item, dict)]
    chapters = {
        str(item.get("node_id") or ""): str(item.get("node_name") or "")
        for item in nodes
        if int(item.get("node_level") or 0) == 1
    }
    documents: list[dict[str, Any]] = []
    for node in nodes:
        if int(node.get("node_level") or 0) != 2:
            continue
        content = str(node.get("node_content") or "").strip()
        if not content:
            continue
        chapter_name = _safe_segment(
            chapters.get(str(node.get("parent_node_id") or "")) or "未分章",
            fallback="未分章",
        )
        section_name = _safe_segment(
            node.get("node_name") or node.get("node_id"),
            fallback=str(node.get("node_id") or "小节"),
        )
        documents.append({
            "relative_path": (
                f"{_LESSON_FOLDER}/{GENERATED_DIR}/{chapter_name}/{section_name}.md"
            ),
            "content": f"# {node.get('node_name') or ''}\n\n{content}\n",
            "artifact_type": "section_content",
            "node_id": str(node.get("node_id") or ""),
        })
    return documents


def _render_slide_documents(course_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Export slide decks as markdown outlines.

    The built decks are HTML/binary artifacts owned by the slide pipeline; what
    belongs here is a readable per-section outline the teacher can archive
    alongside them.
    """
    documents: list[dict[str, Any]] = []
    for node in course_data.get("nodes") or []:
        if not isinstance(node, dict) or int(node.get("node_level") or 0) != 2:
            continue
        deck = node.get("slide_deck")
        slides = deck.get("slides") if isinstance(deck, dict) else None
        if not isinstance(slides, list) or not slides:
            continue
        section_name = _safe_segment(
            node.get("node_name") or node.get("node_id"),
            fallback=str(node.get("node_id") or "小节"),
        )
        lines = [f"# {node.get('node_name') or ''}｜讲义大纲", ""]
        for index, slide in enumerate(slides, start=1):
            if not isinstance(slide, dict):
                continue
            lines.append(f"## {index}. {slide.get('title') or ''}".rstrip())
            for bullet in slide.get("bullets") or []:
                lines.append(f"- {bullet}")
            lines.append("")
        documents.append({
            "relative_path": f"{_SLIDES_FOLDER}/{GENERATED_DIR}/{section_name}.md",
            "content": "\n".join(lines).rstrip() + "\n",
            "artifact_type": "slide_outline",
            "node_id": str(node.get("node_id") or ""),
        })
    return documents


def publish_course_artifacts(
    course_data: dict[str, Any],
    *,
    owner_id: str,
    repository: Any = None,
    create_package_if_missing: bool = True,
) -> dict[str, Any]:
    """Write the generated artifacts into the teacher's course space.

    Never raises: every failure mode is folded into the returned report so the
    caller can surface it without rolling back a course that generated fine.
    """
    report: dict[str, Any] = {
        "schema_version": PUBLISH_SCHEMA_VERSION,
        "status": "skipped",
        "package_id": "",
        "written": [],
        "unchanged": [],
        "conflicts": [],
        "failures": [],
    }
    repo = repository or teacher_course_space_repository
    try:
        documents = build_course_artifact_documents(course_data)
        if not documents:
            report["reason"] = "no_publishable_artifact"
            report["message"] = SKIP_MESSAGES["no_publishable_artifact"]
            return report
        package, skip_reason = _resolve_package(
            course_data,
            owner_id=owner_id,
            repository=repo,
            create_if_missing=create_package_if_missing,
        )
        if package is None:
            report["reason"] = skip_reason
            report["message"] = SKIP_MESSAGES.get(skip_reason, "")
            return report
        report["package_id"] = str(package.get("package_id") or "")
        for document in documents:
            _publish_one(document, package=package, repository=repo, report=report)
        repo.save(package)
        report["status"] = "failed" if report["failures"] else "completed"
    except Exception as exc:  # noqa: BLE001 - publishing must never fail generation
        logger.exception("Publishing course artifacts to the course space failed")
        report["status"] = "failed"
        report["failures"].append({
            "relative_path": "",
            "error": f"{type(exc).__name__}: {exc}",
        })
    return report


def _resolve_package(
    course_data: dict[str, Any],
    *,
    owner_id: str,
    repository: Any,
    create_if_missing: bool,
) -> tuple[dict[str, Any] | None, str]:
    """Find the package bound to this course, creating one when allowed.

    Returns ``(package, skip_reason)``. The reason distinguishes the three ways
    this can come back empty -- missing teacher identity, missing course id, and
    "no package and not allowed to create one" -- because they need different
    fixes and a single vague failure would hide which one happened.

    Binding is recorded on the package (``course_id``) rather than only on the
    course, so a package that already exists for the course is reused across
    regenerations even if the course record was rebuilt.
    """
    if not str(owner_id or "").strip():
        return None, MISSING_TEACHER_IDENTITY
    course_id = str(course_data.get("course_id") or "")
    if not course_id:
        return None, MISSING_COURSE_ID
    for summary in repository.list_owned(owner_id):
        if str(summary.get("course_id") or "") == course_id:
            return (
                repository.load_owned(str(summary.get("package_id")), owner_id),
                "",
            )
    if not create_if_missing:
        return None, NO_COURSE_SPACE_PACKAGE
    classroom = (
        course_data.get("teacher_course_brief")
        or (course_data.get("generation_request") or {}).get("teacher_course_brief")
        or {}
    )
    term = str(classroom.get("academic_term") or "").strip()
    academic_year, term_name = _split_academic_term(term)
    created = repository.create_package(
        owner_id,
        str(course_data.get("course_name") or "未命名课程"),
        academic_year,
        term_name,
        template="school_course_materials",
    )
    package = repository.load_owned(str(created.get("package_id")), owner_id)
    # Record the binding both ways so neither side has to guess later.
    package["course_id"] = course_id
    package["created_by"] = "course_generation"
    repository.save(package)
    return package, ""


def _split_academic_term(value: str) -> tuple[str, str]:
    """Split a free-text 学期 into (学年, 学期); fall back rather than fail.

    ``academic_term`` is optional in the teacher brief and often blank. Refusing
    to publish over a missing label would strand the artifacts, so the fallback
    is deliberate and visible in the package name.
    """
    text = str(value or "").strip()
    if not text:
        return "未标注学年", "未标注学期"
    for marker in ("秋季学期", "春季学期", "夏季学期", "第一学期", "第二学期"):
        if marker in text:
            year = text.replace(marker, "").strip(" -—·")
            return (year or "未标注学年"), marker
    return text, "未标注学期"


def _publish_one(
    document: dict[str, Any],
    *,
    package: dict[str, Any],
    repository: Any,
    report: dict[str, Any],
) -> None:
    relative_path = str(document.get("relative_path") or "")
    content = str(document.get("content") or "")
    try:
        relative_path = normalize_relative_path(relative_path)
        digest = _digest(content)
        assets = package.setdefault("assets", [])
        existing = next(
            (item for item in assets if item.get("relative_path") == relative_path),
            None,
        )
        if existing is not None:
            if str(existing.get("sha256") or "") == digest:
                # Same bytes already there: nothing to do, and nothing to report
                # as a change. This is what makes re-generation idempotent.
                report["unchanged"].append(relative_path)
                return
            if str(existing.get("origin") or "") != "course_generation":
                # A teacher-uploaded file lives here. Never overwrite it -- the
                # teacher's own material outranks a regenerated artifact.
                report["conflicts"].append({
                    "relative_path": relative_path,
                    "reason": "manual_upload_present",
                })
                return
        _write_asset(
            package=package,
            repository=repository,
            relative_path=relative_path,
            content=content,
            digest=digest,
            existing=existing,
            artifact_type=str(document.get("artifact_type") or ""),
            node_id=str(document.get("node_id") or ""),
        )
        report["written"].append(relative_path)
    except (MaterialStorageError, OSError, ValueError) as exc:
        report["failures"].append({
            "relative_path": relative_path,
            "error": f"{type(exc).__name__}: {exc}",
        })


def _write_asset(
    *,
    package: dict[str, Any],
    repository: Any,
    relative_path: str,
    content: str,
    digest: str,
    existing: dict[str, Any] | None,
    artifact_type: str,
    node_id: str,
) -> None:
    package_id = str(package.get("package_id") or "")
    payload = content.encode("utf-8")
    asset_id = str((existing or {}).get("asset_id") or f"tca-{uuid.uuid4().hex}")
    extension = PurePosixPath(relative_path).suffix.lower() or ".md"
    stored_name = f"{asset_id}{extension}"

    package_root = Path(repository.root) / package_id
    (package_root / "files" / stored_name).parent.mkdir(parents=True, exist_ok=True)
    (package_root / "files" / stored_name).write_bytes(payload)
    materialized = repository._content_path(package_id, relative_path)
    materialized.parent.mkdir(parents=True, exist_ok=True)
    materialized.write_bytes(payload)

    category, reason = classify_path(relative_path)
    asset = {
        "asset_id": asset_id,
        "filename": PurePosixPath(relative_path).name,
        "relative_path": relative_path,
        "stored_name": stored_name,
        "materialized_path": relative_path,
        "extension": extension,
        "size_bytes": len(payload),
        "sha256": digest,
        "suggested_category": category,
        "category": str((existing or {}).get("category") or category),
        "category_reason": reason,
        "import_batch_id": "",
        "uploaded_at": _now(),
        # The marker that lets a re-publish tell its own output apart from a
        # teacher's upload at the same path.
        "origin": "course_generation",
        "artifact_type": artifact_type,
    }
    if node_id:
        asset["node_id"] = node_id
    assets = package.setdefault("assets", [])
    if existing is not None:
        assets[assets.index(existing)] = asset
    else:
        assets.append(asset)
    _ensure_folder_entries(package, relative_path)


def _ensure_folder_entries(package: dict[str, Any], relative_path: str) -> None:
    """Register the ancestor folders so the teacher-visible tree shows them."""
    entries = package.setdefault("entries", [])
    known = {
        str(item.get("path") or item.get("name") or "")
        for item in entries
        if isinstance(item, dict) and item.get("kind") == "folder"
    }
    parts = PurePosixPath(relative_path).parts[:-1]
    for index in range(1, len(parts) + 1):
        folder = str(PurePosixPath(*parts[:index]))
        if folder in known:
            continue
        entries.append({
            "name": parts[index - 1],
            "path": folder,
            "kind": "folder",
            "custom": True,
            "generated": True,
        })
        known.add(folder)


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "GENERATED_DIR",
    "MISSING_COURSE_ID",
    "MISSING_TEACHER_IDENTITY",
    "NO_COURSE_SPACE_PACKAGE",
    "SKIP_MESSAGES",
    "PUBLISH_SCHEMA_VERSION",
    "build_course_artifact_documents",
    "publish_course_artifacts",
]
