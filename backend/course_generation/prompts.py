"""课程生成唯一 prompt 编排器。"""

from __future__ import annotations

import json
import re
from typing import Any

from course_coherence import course_coherence_prompt_context
from course_composition import format_block_difficulty, format_composition_profile
from course_authoring_templates import compile_outline_prompt_contract
from course_difficulty import (
    format_difficulty_profile,
    format_node_difficulty_contract,
)
from course_generation.adaptive import (
    clip_text,
    compact_batch_inputs,
    compact_planning_context,
    compact_value,
)
from course_knowledge_base import (
    compile_course_knowledge_base,
    course_knowledge_base_prompt_context,
)
from course_pedagogy import SubjectPedagogyProfile, module_block_role
from teaching_design import (
    format_generation_teaching_guidance,
)

PROMPT_CONTRACT_VERSION = "course_prompt_v32"


def _course_planning_rules(brief: dict[str, Any]) -> str:
    """Compile directory rules from the current product classifications.

    ``course_type`` remains readable for old briefs, but a new brief is planned
    from learning purpose and course teaching type.  This keeps the old four-way
    compatibility value from overriding the three classifications shown to the
    teacher.
    """
    learning_purpose = str(brief.get("learning_purpose") or "").strip()
    unit = (
        "讲"
        if (brief.get("course_shape_constraints") or {}).get("teacher_lecture_mode")
        else "章"
    )
    if not learning_purpose:
        return _course_type_planning_rules(brief)
    if learning_purpose == "project":
        return """9. 项目实战按真实交付物组织：起点不足时不得使用 `compressed`；尚未证实的能力使用
   `verify_in_project`，明确缺口使用 `focus`，阶段成果使用 `milestone`。
10. `verify_in_project` 的理由必须指向可检查的任务；`milestone` 必须指向交付物验收。
11. `planning_stages` 使用空数组；项目进度由里程碑和学习路径角色表达。"""
    if learning_purpose == "exam":
        stage_ids = [
            "scope_diagnosis",
            "priority_review",
            "targeted_practice",
            "mock_assessment",
            "final_consolidation",
        ]
        return f"""9. 每{unit}必须填写 `planning_stages` 数组，只允许使用 {json.dumps(stage_ids, ensure_ascii=False)}。
10. 上述任务必须全部覆盖并按给定顺序推进；同一任务可以占多{unit}，一{unit}也可以连续承载多个任务，但不得倒序。
11. 学习路径角色只使用 `focus|standard|compressed`，不得把复习任务写成项目里程碑。"""
    return """9. `planning_stages` 使用空数组，目录按当前学科的学习先后关系推进。
10. 学习路径角色只使用 `focus|standard|compressed`，不得出现项目专属角色。
11. 整课怎样教由课程教学类型决定，不得再从旧 `course_type` 推断第二套课程结构。"""


def _course_type_planning_rules(brief: dict[str, Any]) -> str:
    course_type = str(brief.get("course_type") or "systematic")
    contract = brief.get("course_type_contract") or {}
    required_stages = contract.get("required_planning_stages") or []
    if course_type == "project":
        return """9. 仅项目实战使用以下路径规则：起点不足时不得使用 `compressed`；未证实能力使用
   `verify_in_project`，明确重点缺口使用 `focus`，阶段成果使用 `milestone`。
10. `verify_in_project` 的理由必须指向可观察任务或检查点；`milestone` 必须指向交付物验收。
11. `planning_stages` 使用空数组；项目阶段由里程碑和路径角色表达。"""
    if required_stages:
        stage_ids = [
            str(item.get("id") or "").strip()
            for item in required_stages
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        ]
        return f"""9. 每章必须填写 `planning_stages` 数组，只允许使用 {json.dumps(stage_ids, ensure_ascii=False)}。
10. 上述阶段必须全部覆盖并按给定顺序推进；同一阶段可以占多章，一章也可以连续承载多个阶段，但不得倒序。
11. 学习路径角色只使用 `focus|standard|compressed`，不得把探究或复习任务伪装成项目里程碑。"""
    return """9. 系统学习的 `planning_stages` 使用空数组，目录按知识先修关系推进。
10. 学习路径角色只使用 `focus|standard|compressed`，不得出现项目专属角色。"""


def _course_coverage_rules(verdict: dict[str, Any] | None) -> str:
    """State plainly what this course size may and may not claim to cover.

    Numbered separately from the type rules (which own slots 9-11) so both can
    grow without renumbering each other.
    """
    if not verdict:
        return ""
    if verdict.get("status") == "complete":
        return (
            "C1. 本课程规格可按完整课程组织；仍需在定位中说明确实不覆盖的进阶内容。"
        )
    subject = verdict.get("subject") or "本学科"
    scale_label = verdict.get("scale_label") or "当前规格"
    lines = [
        f"C1. 【课程规格判定】本次为{scale_label}，"
        f"{verdict.get('coverage_promise') or '不承担学科完整覆盖'}。",
        f"C2. 课程名称与 `positioning` 不得出现“完整课程/完整覆盖/全面覆盖”等表述，"
        f"也不得暗示已学完{subject}；建议定位为「"
        f"{verdict.get('required_positioning') or subject + '核心概览课'}」。",
    ]
    uncovered = [str(item) for item in verdict.get("uncovered_topics") or []]
    if uncovered:
        lines.append(
            f"C3. 以下{subject}核心主题在本次课时下无法覆盖，必须在 `positioning` 中"
            f"原样列为“本次不覆盖”，不得假装已覆盖，也不得默认学习者已掌握："
            f"{json.dumps(uncovered, ensure_ascii=False)}。"
        )
    elif verdict.get("core_topics"):
        lines.append(
            f"C3. 必须在 `positioning` 中明确列出本次不覆盖的{subject}主题；"
            "凡是无法在本课时内讲透的内容，宁可列为不覆盖，也不得罗列标题充数。"
        )
    for item in verdict.get("honest_naming") or []:
        lines.append(f"C{len(lines) + 1}. {item}")
    return "\n".join(lines)


class CoursePromptComposer:
    def build_outline_skeleton_v2_prompt(
        self,
        *,
        subject: str,
        audience: str,
        brief: dict[str, Any],
        profile: SubjectPedagogyProfile,
        difficulty_profile: dict[str, Any],
        gap_assessment: dict[str, Any],
        adaptation_decision: dict[str, Any],
        material_context: str,
        detail_level: str = "full",
        coverage_verdict: dict[str, Any] | None = None,
    ) -> str:
        """Build the small global decision used before parallel chapter expansion."""
        planning_brief = brief
        profile_data = profile.to_dict()
        if detail_level != "full":
            compact_chars = 220 if detail_level == "compact" else 100
            compact_items = 8 if detail_level == "compact" else 4
            subject = clip_text(subject, 200 if detail_level == "compact" else 100)
            audience = clip_text(audience, 120 if detail_level == "compact" else 72)
            brief = compact_value(
                brief,
                max_string_chars=compact_chars,
                max_list_items=compact_items,
                max_depth=4 if detail_level == "compact" else 3,
            )
            profile_data = compact_value(
                profile_data,
                max_string_chars=140 if detail_level == "compact" else 72,
                max_list_items=6 if detail_level == "compact" else 3,
                max_depth=3,
            )
            difficulty_profile = compact_value(
                difficulty_profile,
                max_string_chars=140 if detail_level == "compact" else 72,
                max_list_items=6 if detail_level == "compact" else 3,
                max_depth=3,
            )
            gap_assessment = compact_value(
                gap_assessment,
                max_string_chars=120 if detail_level == "compact" else 64,
                max_list_items=4 if detail_level == "compact" else 2,
                max_depth=2,
            )
            adaptation_decision = compact_value(
                adaptation_decision,
                max_string_chars=120 if detail_level == "compact" else 64,
                max_list_items=4 if detail_level == "compact" else 2,
                max_depth=2,
            )
            material_context = clip_text(
                material_context,
                4200 if detail_level == "compact" else 1600,
            )
        shape = brief.get("course_shape_constraints") or {}
        learning_purpose_contract = brief.get("learning_purpose_contract") or {}
        planning_rules = _course_planning_rules(planning_brief)
        coverage_rules = _course_coverage_rules(coverage_verdict)
        formal_outline_contract = compile_outline_prompt_contract(
            subject=subject,
            audience=audience,
            brief=brief,
        )
        teacher_lecture_mode = bool(shape.get("teacher_lecture_mode"))
        structure_heading = "全课讲次骨架 V2" if teacher_lecture_mode else "全课章节骨架 V2"
        structure_instruction = (
            "教师端正式结构只有‘课程→讲’。JSON 中 chapters/section_count 仅为现有引擎的技术兼容字段："
            "每个 chapter 必须对应一讲，标题直接写本讲主题，每讲 section_count 必须为 1；"
            "不得在教师可见文本中生成章、小节或二级教学目录。"
            if teacher_lecture_mode else
            "你只做一次轻量的全局课程决策：确定课程定位、全课成果、章节顺序、每章唯一学习焦点，以及每章需要展开的小节数量。"
        )
        # These values already have dedicated, typed sections below. Avoid
        # repeating them inside the generic brief where duplication increases
        # prompt noise and makes one fact look like several instructions.
        outline_input_brief = {
            key: value for key, value in brief.items()
            if key not in {
                "subject",
                "audience",
                "course_shape_constraints",
                "course_type",
                "course_type_label",
                "course_type_resolved_from",
                "course_type_contract",
                "teaching_definition",
                "universal_teaching_principles",
                "learning_purpose_contract",
                "subject_type_contract",
                "subject_standard_pack",
                "subject_standard_pack_version",
                "course_teaching_type_contract",
                "course_lesson_type_distribution",
                "classroom_constraint_contract",
                "course_intent",
                "learner_starting_profile",
                "personalization_rationale",
                "formal_course_profile",
                "teacher_course_brief",
            }
        }
        if teacher_lecture_mode:
            lecture_count = int(shape.get("chapter_count") or 0)
            teacher_brief = brief.get("teacher_course_brief") or {}
            total_hours = (
                teacher_brief.get("total_class_hours")
                or teacher_brief.get("total_hours")
                or shape.get("total_class_hours")
                or "未填写"
            )
            return f"""## 轻量讲次方案 V1

这是课程大纲生成的第一轮。请先形成教师可立即看到和编辑的轻量讲次方案。

## 课程输入
- 课程名称：{subject}
- 教学对象：{audience}
- 讲数：{lecture_count}
- 总学时：{total_hours}
- 教师要求：{json.dumps(teacher_brief, ensure_ascii=False)}
- 其他必要约束：{json.dumps(outline_input_brief, ensure_ascii=False)}

## 资料摘要
{material_context or '未上传资料；请依据课程信息和通用知识安排讲次。'}

## 生成要求
1. 按课程推进顺序返回每讲的标题和内容简介，供教师直接调整。
2. 讲数保持为 {lecture_count} 讲。标题使用纯主题名称，例如“监督学习基础”。
3. `content_summary` 使用二至四句自然中文，说明这一讲实际讲什么，以及它与前后讲的衔接。
4. 响应使用下方 JSON Schema。

## JSON Schema
{{
  "course_title": "课程名称",
  "lectures": [
    {{
      "lecture_number": 1,
      "title": "本讲主题",
      "content_summary": "本讲主要内容及其在全课中的衔接，二至四句。"
    }}
  ]
}}""".strip()
        return f"""## {structure_heading}

{structure_instruction}
不要生成任何知识点、教案、正文或题目。
后续系统会按章节并行生成小节目录并在本地汇编。只输出有效 JSON。

## 课程输入
- 主题：{subject}
- 学习对象：{audience}
- 其余生成约束：{json.dumps(outline_input_brief, ensure_ascii=False)}
- 用户指定章数：{shape.get('chapter_count') or '未指定'}
- 用户指定小节总数：{shape.get('section_count') or '未指定'}
- 完整课程最低章数：{shape.get('minimum_chapter_count') or '按用户明确数量'}
- 完整课程最低小节总数：{shape.get('minimum_section_count') or '按用户明确数量'}

## 学习目的契约
- 学习目的：{brief.get('learning_purpose_label') or brief.get('course_type_label') or '系统学习'}
- 结果要求：{brief.get('learning_purpose_result') or ''}
- 目的专属学习弧：{json.dumps((brief.get('learning_purpose_contract') or {}).get('learning_arc') or [], ensure_ascii=False)}
- 目的专属证据：{(brief.get('learning_purpose_contract') or {}).get('evidence_strategy') or ''}
- 整课目标规则：{json.dumps(learning_purpose_contract, ensure_ascii=False)}
- 类型化意图：{json.dumps(brief.get('course_intent') or {}, ensure_ascii=False)}
- 学习者暂定起点：{json.dumps(brief.get('learner_starting_profile') or {}, ensure_ascii=False)}
- 个性化依据：{json.dumps(brief.get('personalization_rationale') or [], ensure_ascii=False)}

## 课程教学类型契约
- 课程教学类型：{brief.get('course_teaching_type_label') or '综合课'}
- 整课编排规则：{json.dumps(brief.get('course_teaching_type_contract') or {}, ensure_ascii=False)}
- 讲次课型比例：{json.dumps(brief.get('course_lesson_type_distribution') or {}, ensure_ascii=False)}

## 教学与学科契约
- 教学定义：{(brief.get('teaching_definition') or {}).get('definition') or ''}
- 学科类型：{brief.get('subject_type_label') or '自动判断'}
- 学科成立方式：{json.dumps(brief.get('subject_type_contract') or {}, ensure_ascii=False)}
- 版本化学科标准：{json.dumps(brief.get('subject_standard_pack') or {}, ensure_ascii=False)}
- 共同教学底线：{json.dumps(brief.get('universal_teaching_principles') or [], ensure_ascii=False)}

## 难度与适配
- 难度：{json.dumps(difficulty_profile, ensure_ascii=False)}
- 就绪差距：{json.dumps(gap_assessment, ensure_ascii=False)}
- 适配决策：{json.dumps(adaptation_decision, ensure_ascii=False)}

## 教学画像
{json.dumps(profile_data, ensure_ascii=False)}

## 资料摘要
{material_context or '未上传资料；只能使用通用知识，不得伪装引用资料。'}

## 正式教学大纲模板契约（从属于灵知结构化真源）
{json.dumps(formal_outline_contract, ensure_ascii=False)}
当前模型只规划课程定位、目标和目录；模板中的逐讲实施、考核和参考资料栏目由后续讲次生成与本地汇编完成。

## 约束
0. {structure_instruction}
1. 用户指定章数或小节总数时必须精确满足；所有 `section_count` 之和必须等于指定总数。
2. 未指定数量时必须覆盖从必要前置到最终成果的完整知识与能力依赖，并达到上面的完整课程最低规模；可以按主题需要继续增加，课程总量没有固定产品上限。
3. 这是所有课程统一使用的完整规划入口。单次批次大小只是执行预算，不得把整门课程压缩成一个批次或默认六节。
4. 每章只定义一个清晰、互不重复的学习推进范围，不能把小节详情塞进章节焦点。
5. 章节按学习先后排列，后续章节不得重复承担前面已经完成的核心责任。
6. 只返回章节骨架，不返回 `sections`、知识点、关系、正文或题目。
7. 学科合同、共同教学底线和最终考核是章节推进的设计依据：课程必须为最终
   可观察成果逐章建立必要能力与证据，不能只按主题名或教材目录罗列章节。
8. 必须遵守教学类型契约。学习路径标签只能依据上面的起点信息；自述能力必须标为待验证，
   不得直接宣称已经掌握。
9. `course_title`、`positioning`、`learning_objectives`、章节 `title` 与 `learning_focus`
   都会直接给教师阅读，必须使用真实课程标准和高校教学大纲的表达：直接说明教什么、
   学生学完能做什么，不把内部规划术语写进成品。
10. 教师可见文本不得出现“全课知识地图、先修链定位、学习路径角色、内部证据流程、
    输入对象、输出对象、系统策略、课程主路径”等系统语言。内部字段
    `learning_path_role` 与 `path_reason` 仍按契约填写，但不得把这些词复制到标题、定位或目标。
11. 章节焦点用一条简洁自然的句子表达；优先使用“理解、掌握、会计算、能判断、能解释、
    能应用”等学科常用动词，不堆叠多个判断步骤、数据字段或实现说明。
12. `section_count` 由教师明确要求和本章真实学习责任决定。一章只需要一个完整教学单元时，
    填 1 完全合法；不得为了做出层级感强行拆成多个同义小节。需要分节时，必须能说明每节
    独立承担的概念、方法、练习或应用责任，不能只把一个主题换三种说法。
{coverage_rules}
{planning_rules}

## JSON Schema
{{
  "course_title": "课程名",
  "positioning": "课程定位与最终成果",
  "learning_objectives": ["可观察的全课成果"],
  "prerequisites": ["必要前置"],
  "chapters": [
    {{
      "chapter_number": 1,
      "title": "章节名",
      "planning_stages": ["专用规划器的一个或多个连续阶段；系统学习与项目实战为空数组"],
      "learning_focus": "本章独有的能力推进范围",
      "learning_path_role": "focus|standard|compressed|verify_in_project|milestone",
      "path_reason": "该章节为何以当前深度进入个人路径",
      "section_count": 3
    }}
  ]
}}""".strip()

    def build_outline_skeleton_v2_correction_prompt(
        self,
        *,
        original_prompt: str,
        issues: list[dict[str, Any]],
    ) -> str:
        issue_text = "\n".join(
            f"- {clip_text(item.get('message'), 240)}"
            for item in issues[:10]
        ) or "- 上一次输出不是完整有效的章节骨架 JSON"
        if '"lectures"' in original_prompt:
            return f"""## 轻量讲次方案修复

上一次讲次方案存在以下问题：
{issue_text}

请根据这些问题重新生成完整的轻量讲次方案。保持教师填写的讲数，
并继续使用上面的 `lectures` JSON Schema。

{clip_text(original_prompt, 12000)}
""".strip()
        return f"""## 全课章节骨架 V2 定点修复

上一次章节骨架存在以下问题：
{issue_text}

只修复章节骨架并重新输出完整 JSON。不得生成小节、知识点、教案、正文、题目或解释。

{clip_text(original_prompt, 8500)}
""".strip()

    def build_teacher_outline_course_contract_v1_prompt(
        self,
        *,
        skeleton: dict[str, Any],
        brief: dict[str, Any],
        material_context: str,
        detail_level: str = "full",
    ) -> str:
        """Generate the course-level formal fields from the edited light plan."""
        lectures = [
            {
                "lecture_number": int(
                    item.get("lecture_number")
                    or item.get("chapter_number")
                    or index
                ),
                "title": str(item.get("title") or ""),
                "content_summary": str(item.get("content_summary") or ""),
            }
            for index, item in enumerate(
                skeleton.get("chapters") or [],
                start=1,
            )
            if isinstance(item, dict)
        ]
        teacher_context = brief.get("teacher_course_brief") or {}
        formal_profile = brief.get("formal_course_profile") or {}
        formal_contract = compile_outline_prompt_contract(
            subject=str(skeleton.get("course_title") or "课程"),
            audience=str(
                teacher_context.get("target_audience")
                or brief.get("audience")
                or "未填写"
            ),
            brief=brief,
        )
        if detail_level != "full":
            max_text = 180 if detail_level == "compact" else 96
            lectures = compact_value(
                lectures,
                max_string_chars=max_text,
                max_list_items=36,
                max_depth=3,
            )
            teacher_context = compact_value(
                teacher_context,
                max_string_chars=max_text,
                max_list_items=8,
                max_depth=3,
            )
            formal_profile = compact_value(
                formal_profile,
                max_string_chars=max_text,
                max_list_items=8,
                max_depth=3,
            )
            formal_contract = compact_value(
                formal_contract,
                max_string_chars=max_text,
                max_list_items=12,
                max_depth=4,
            )
            material_context = clip_text(
                material_context,
                4200 if detail_level == "compact" else 1800,
            )
        skeleton_revision_id = str(skeleton.get("revision_id") or "")
        return f"""## 课程级完整大纲合同 V1

这是完整大纲生成的第二轮。请先根据教师最新编辑的讲次方案，形成课程级正式字段。
讲次方案作为本轮已经冻结的输入，响应使用下方课程级 JSON Schema。

## 轻量方案修订
{skeleton_revision_id}

## 教师当前讲次方案
{json.dumps(lectures, ensure_ascii=False)}

## 教师课程信息
{json.dumps(teacher_context, ensure_ascii=False)}

## 已有正式课程信息
{json.dumps(formal_profile, ensure_ascii=False)}

## 资料摘要
{material_context or '未上传资料；请依据课程信息和通用知识生成，需要来源确认的字段保持空值。'}

## 正式大纲模板合同
{json.dumps(formal_contract, ensure_ascii=False)}

## 生成要求
1. 课程定位、学习目标、可测量成果、授课方式、考核方案和知识模块必须与讲次方案一致。
2. 每项可测量成果都必须关联课程目标、覆盖讲次、评价证据和内容范围。
3. 知识模块用于组织讲次分组，全部讲次恰好出现一次。
4. 考核方案同时包含过程性与终结性评价，权重合计 100，并与可测量成果关联。
5. 参考书籍、网站、版次和网址取自教师输入或已解析资料；无法核实时保持空数组或空字符串。
6. 育人目标与实施案例使用和真实课程内容直接相关的具体表达。
7. 响应使用下方 JSON Schema。

## JSON Schema
{{
  "schema_version": "teacher_outline_course_contract_v1",
  "skeleton_revision_id": "{skeleton_revision_id}",
  "course_intro_zh": "中文课程简介",
  "course_intro_en": "与中文语义对应的英文简介",
  "positioning": "学习对象、课程边界与最终能力",
  "learning_objectives": ["可观察的学习目标"],
  "prerequisites": ["必要先修要求"],
  "education_objectives": ["与真实课程内容相关的育人目标"],
  "measurable_outcomes": ["可测量学习成果"],
  "outcome_alignment": [{{
    "outcome_number": 1,
    "objective_refs": ["学习目标1"],
    "lecture_numbers": [1],
    "assessment_evidence": ["可检查证据"],
    "coverage_scope": "内容范围"
  }}],
  "teaching_methods": ["授课方式"],
  "assessment_methods": ["考核方式摘要"],
  "assessment_plan": [{{
    "item": "考核项目",
    "category": "formative|summative",
    "weight_percent": 50,
    "criteria": "评分标准",
    "outcome_numbers": [1]
  }}],
  "course_modules": [{{
    "module_id": "M1",
    "title": "知识模块",
    "lecture_numbers": [1]
  }}],
  "ideology_cases": [],
  "reference_books": [],
  "reference_websites": [],
  "course_website": ""
}}""".strip()

    def build_teacher_outline_course_contract_v1_correction_prompt(
        self,
        *,
        original_prompt: str,
        issues: list[dict[str, Any]],
    ) -> str:
        issue_text = "\n".join(
            f"- {clip_text(item.get('message'), 240)}"
            for item in issues[:12]
        ) or "- 上一次输出不是完整有效的课程级大纲 JSON"
        return f"""## 课程级完整大纲合同 V1 定点修复

上一次课程级大纲字段存在以下结构问题：
{issue_text}

请根据这些问题重新生成完整的课程级字段，并保持轻量方案修订标识。
响应继续使用原请求中的课程级 JSON Schema。

{clip_text(original_prompt, 14000)}
""".strip()

    def build_teacher_outline_detail_batch_v1_prompt(
        self,
        *,
        skeleton: dict[str, Any],
        batch_spec: dict[str, Any],
        brief: dict[str, Any],
        material_context: str,
        detail_level: str = "full",
    ) -> str:
        """Generate one complete lecture object from the edited light plan."""
        selected_numbers = {
            int(item) for item in batch_spec.get("lecture_numbers") or []
        }
        all_lectures = [
            {
                "lecture_number": int(
                    item.get("lecture_number")
                    or item.get("chapter_number")
                    or index
                ),
                "title": str(item.get("title") or ""),
                "content_summary": str(item.get("content_summary") or ""),
            }
            for index, item in enumerate(
                skeleton.get("chapters") or [],
                start=1,
            )
            if isinstance(item, dict)
        ]
        selected_lectures = [
            item for item in all_lectures
            if item["lecture_number"] in selected_numbers
        ]
        course_contract = {
            "course_title": skeleton.get("course_title"),
            "positioning": skeleton.get("positioning"),
            "learning_objectives": skeleton.get("learning_objectives") or [],
            "education_objectives": skeleton.get("education_objectives") or [],
            "measurable_outcomes": skeleton.get("measurable_outcomes") or [],
            "outcome_alignment": skeleton.get("outcome_alignment") or [],
            "teaching_methods": skeleton.get("teaching_methods") or [],
            "assessment_plan": skeleton.get("assessment_plan") or [],
            "reference_books": skeleton.get("reference_books") or [],
            "reference_websites": skeleton.get("reference_websites") or [],
        }
        teacher_context = brief.get("teacher_course_brief") or {}
        if detail_level != "full":
            max_text = 180 if detail_level == "compact" else 96
            course_contract = compact_value(
                course_contract,
                max_string_chars=max_text,
                max_list_items=8 if detail_level == "compact" else 4,
                max_depth=4,
            )
            all_lectures = compact_value(
                all_lectures,
                max_string_chars=max_text,
                max_list_items=24,
                max_depth=3,
            )
            selected_lectures = compact_value(
                selected_lectures,
                max_string_chars=max_text,
                max_list_items=8,
                max_depth=3,
            )
            material_context = clip_text(
                material_context,
                3600 if detail_level == "compact" else 1600,
            )
            teacher_context = compact_value(
                teacher_context,
                max_string_chars=max_text,
                max_list_items=6,
                max_depth=3,
            )
        batch_id = str(batch_spec.get("batch_id") or "")
        skeleton_revision_id = str(skeleton.get("revision_id") or "")
        lecture_count = len(selected_lectures)
        return f"""## 单讲完整大纲 V2

这是完整大纲第二轮的逐讲生成任务。请根据已经冻结的讲次方案和课程级合同，
生成当前一讲的目标、内容边界、学时、教学活动、学习任务和达成检验。

## 批次身份
- 批次：{batch_id}
- 框架修订：{skeleton_revision_id}
- 讲次：{json.dumps(list(batch_spec.get('lecture_numbers') or []), ensure_ascii=False)}

## 课程级合同
{json.dumps(course_contract, ensure_ascii=False)}

## 全课讲次边界
{json.dumps(all_lectures, ensure_ascii=False)}

## 当前要补全的讲次
{json.dumps(selected_lectures, ensure_ascii=False)}

## 授课与教师输入
{json.dumps(teacher_context, ensure_ascii=False)}

## 资料摘要
{material_context or '未上传资料；请依据课程信息和通用知识生成，需要来源确认的字段保持空值。'}

## 生成要求
1. 返回当前讲次的 1 个完整对象，讲次身份使用“批次身份”中的值。
2. 根据冻结的标题和 `content_summary` 生成本讲目标、内容边界和分项学时；三项 `hour_breakdown` 之和必须大于 0。
3. 重点、难点、活动、作业和达成检验必须与本讲目标一致；达成检验写清学生产出与教师判断标准。
4. 每讲至少给出一个案例、问题、例题、实验或项目情境，以及一项课前或课后任务和可提交证据。
5. 在线或混合课程每讲至少一项 `mode=online` 任务；纯线下课程使用 `mode=offline`。课外任务的 `estimated_hours` 单独记录。
6. 拓展资源从课程级已确认参考资料中选择，`source_ref` 与确认来源完全一致；没有已确认来源时使用空数组。
7. `education_objective_refs` 和 `ideology_implementation` 在本讲确有责任、规范或价值判断时填写；`external_mentor` 使用教师输入已提供的信息。
8. 响应使用下方 JSON Schema。

## JSON Schema
{{
  "batch_id": "{batch_id}",
  "skeleton_revision_id": "{skeleton_revision_id}",
  "lectures": [
    {{
      "lecture_number": 1,
      "learning_objective": "本讲结束后学生能够完成的可观察目标",
      "scope_boundary": "本讲负责讲到哪里，不提前替代哪些后续内容",
      "hour_breakdown": {{
        "classroom_lecture": 1,
        "classroom_practice": 1,
        "online_instruction": 0
      }},
      "key_points": ["教学重点"],
      "key_difficulties": ["教学难点"],
      "activities": ["主要教学活动"],
      "homework": ["课后任务"],
      "application_anchors": ["案例、问题、例题、实验或项目情境"],
      "extension_resources": [
        {{
          "resource_type": "book|article|standard|regulation|dataset|video|website|other",
          "title": "资源名称",
          "edition": "已确认的版本；不适用则留空",
          "locator": "章、节或已核验页码",
          "source_ref": "与课程参考资料完全一致的来源",
          "verification_status": "verified|pending"
        }}
      ],
      "learning_tasks": [
        {{
          "mode": "online|offline",
          "stage": "before_class|after_class",
          "task": "学习任务",
          "evidence": "学生提交或留下的证据",
          "estimated_hours": 1
        }}
      ],
      "education_objective_refs": [],
      "ideology_implementation": "仅在真实相关时填写",
      "external_mentor": {{"name": "", "organization": "", "role": ""}},
      "assessment": ["学生产出和判断达成的标准"]
    }}
  ]
}}""".strip()

    def build_teacher_outline_detail_batch_v1_correction_prompt(
        self,
        *,
        original_prompt: str,
        issues: list[dict[str, Any]],
    ) -> str:
        issue_text = "\n".join(
            f"- {clip_text(item.get('message'), 240)}"
            for item in issues[:16]
        ) or "- 上一次输出不是完整有效的讲次详情 JSON"
        return f"""## 单讲完整大纲 V2 定点修复

当前讲次详情批次存在以下问题：
{issue_text}

请根据这些问题重新生成当前讲次的完整 JSON。保持任务标识、框架修订和讲次身份，
并继续使用原请求中的逐讲 JSON Schema。

{clip_text(original_prompt, 12000)}
""".strip()

    def build_outline_batch_v2_prompt(
        self,
        *,
        course_title: str,
        positioning: str,
        learning_objectives: list[str],
        chapter: dict[str, Any],
        neighbor_chapters: list[dict[str, Any]],
        batch_spec: dict[str, Any],
        previous_sections: list[dict[str, Any]],
        evidence_hints: list[dict[str, Any]],
        skeleton_revision_id: str,
        detail_level: str = "full",
    ) -> str:
        """Expand one bounded chapter slice without rebroadcasting the course."""
        if detail_level != "full":
            max_text = 180 if detail_level == "compact" else 88
            course_title = clip_text(course_title, 140 if detail_level == "compact" else 80)
            positioning = clip_text(positioning, 220 if detail_level == "compact" else 100)
            learning_objectives = [
                clip_text(item, max_text)
                for item in learning_objectives[:8 if detail_level == "compact" else 4]
            ]
            chapter = compact_value(
                chapter,
                max_string_chars=max_text,
                max_list_items=6 if detail_level == "compact" else 3,
                max_depth=3,
            )
            neighbor_chapters = compact_value(
                neighbor_chapters,
                max_string_chars=140 if detail_level == "compact" else 72,
                max_list_items=3,
                max_depth=3,
            )
            previous_sections = compact_value(
                previous_sections[-6 if detail_level == "compact" else -3:],
                max_string_chars=140 if detail_level == "compact" else 72,
                max_list_items=6 if detail_level == "compact" else 3,
                max_depth=3,
            )
            evidence_hints = compact_value(
                evidence_hints,
                max_string_chars=160 if detail_level == "compact" else 80,
                max_list_items=4 if detail_level == "compact" else 2,
                max_depth=3,
            )
        start = int(batch_spec.get("start_section_index") or 1)
        end = int(batch_spec.get("end_section_index") or start)
        single_section_rule = (
            "8. 当前章只有一个小节。它是数据上的教学单元，界面会自动折叠重复层级；"
            "小节标题不得机械复述章标题，目标应直接写本章真正要完成的学习任务。"
            if int(chapter.get("section_count") or 0) == 1
            else (
                "8. 当前章包含多个小节。每节必须承担清晰、递进且不可互换的学习责任；"
                "不能把同一个章目标拆成若干同义标题。"
            )
        )
        return f"""## 章节小节目录批次 V2

全课章节骨架已经确认。你只展开当前章节的第 {start}-{end} 个小节；不得修改课程
定位、章节边界、其他章节或已经完成的当前章小节。只输出有效 JSON。

## 课程
- 名称：{course_title}
- 定位：{positioning}
- 全课成果：{json.dumps(learning_objectives, ensure_ascii=False)}
- 章节骨架修订：{skeleton_revision_id}

## 当前章节
{json.dumps(chapter, ensure_ascii=False)}

## 相邻章节边界
{json.dumps(neighbor_chapters, ensure_ascii=False)}

## 当前批次
{json.dumps(batch_spec, ensure_ascii=False)}

## 当前章已完成的前序小节
{json.dumps(previous_sections, ensure_ascii=False)}

## 当前章限量证据提示
{json.dumps(evidence_hints, ensure_ascii=False)}

## 约束
1. 必须严格返回 {end - start + 1} 个小节，并按 `expected_node_ids` 的顺序逐一对应。
2. 每节只承担一个可观察且互不重复的责任，给出目标、范围和可检查验收任务。
   学习目标使用“动作 + 对象 + 条件/标准”，不能写成“完成本节任务”或只替换主题词的套话。
   达成检验必须写清学生提交、解释、推导、判错、比较、设计、实作或迁移出的具体证据，
   以及据此判断达成的标准；同章小节不得沿用同一检验句式只替换标题。
3. 当前章内部只能引用编号更早的小节。第一节只有确需承接时才可引用
   `previous_chapter_anchor_id`；不得引用其他章节或未来小节。
4. 当前批次不得重新解释整个章节，不得提前承担下一批次或相邻章节的核心责任。
5. `title` 与 `learning_objective` 是教师和学生直接阅读的课程大纲正文。标题采用该学科
   常见课程目录写法；目标控制在一至两句，优先使用“理解、掌握、会计算、能判断、
   能解释、能应用”等自然教学语言，不把能力点、验收细则和所有前置条件塞进一句话。
6. 教师可见文本不得出现“全课知识地图、先修链定位、学习路径角色、内部证据流程、
   输入对象、输出对象、系统策略、课程主路径”等内部规划语言。
   `scope_boundary` 与 `path_reason` 可以承载系统约束，但也应写成简洁的人话。
7. 不输出知识点、知识关系、教案、正文、题目答案或 Markdown 围栏。
{single_section_rule}

## JSON Schema
{{
  "sections": [
    {{
      "node_id": "L2-章号-节号",
      "section_number": "章号.节号",
      "title": "小节名",
      "learning_objective": "学完后能完成的任务",
      "prerequisite_node_ids": [],
      "assessment": ["验收标准或任务"],
      "scope_boundary": "本节负责什么，以及明确不提前展开什么",
      "learning_path_role": "focus|standard|compressed|verify_in_project|milestone",
      "path_reason": "该小节为何出现在当前学习路径"
    }}
  ]
}}""".strip()

    def build_outline_batch_v2_correction_prompt(
        self,
        *,
        original_prompt: str,
        issues: list[dict[str, Any]],
    ) -> str:
        issue_text = "\n".join(
            f"- {clip_text(item.get('message'), 240)}"
            for item in issues[:10]
        ) or "- 上一次输出不是完整有效的目录批次 JSON"
        return f"""## 章节小节目录批次 V2 定点修复

当前最小目录批次存在以下问题：
{issue_text}

只重新输出当前批次的完整 JSON。章节骨架、批次范围、节点顺序和其他已完成批次
不得改变；不要输出解释或 Markdown 围栏。

{clip_text(original_prompt, 8500)}
""".strip()

    def build_teaching_plan_skeleton_v3_prompt(
        self,
        *,
        course_title: str,
        positioning: str,
        learning_objectives: list[str],
        planning_context: dict[str, Any],
        detail_level: str = "full",
    ) -> str:
        planning_context = compact_planning_context(
            planning_context,
            detail_level=detail_level,
        )
        skeleton_context = self._compact_skeleton_planning_context(
            planning_context
        )
        prior_registry = list(
            skeleton_context.get("prior_knowledge_registry") or []
        )
        new_key_start = max(
            1,
            int(skeleton_context.get("new_knowledge_key_start") or 1),
        )
        new_key_example = f"K{new_key_start:03d}"
        shard_contract = (
            "这是全课骨架的后续分片。`prior_knowledge_registry` 是已确认、不可改动的前序"
            "知识：可以在 `prerequisite_keys` 或 `reused_knowledge_keys` 中引用，但不得"
            "把它们重复放进本次 `knowledge_registry`。本次只返回输入中的当前小节和"
            f"新知识；新知识键从 `{new_key_example}` 开始顺序编号，不得复用已有键。"
            "系统会按目录顺序本地合并并校验稳定键。"
            if prior_registry
            else (
                "这是首个或唯一骨架分片，只返回当前输入中的小节与新知识；"
                f"新知识键从 `{new_key_example}` 开始顺序编号。"
            )
        )
        if detail_level != "full":
            course_title = clip_text(
                course_title, 180 if detail_level == "compact" else 96
            )
            positioning = clip_text(
                positioning, 260 if detail_level == "compact" else 120
            )
            learning_objectives = [
                clip_text(item, 180 if detail_level == "compact" else 96)
                for item in learning_objectives[:8 if detail_level == "compact" else 4]
            ]
        return f"""## 全课知识职责骨架 V3

你只做当前有界分片的全局身份决策：确定原子知识身份、唯一首次负责小节、合法复用、
前置知识键和允许承担职责的课程块；前序分片已经确认的身份保持只读。不要展开能力、
易错、掌握标准、正文或题目。
目录已经确认，不得增删、改名或调序。只输出有效 JSON。

## 课程
- 名称：{course_title}
- 定位：{positioning}
- 全课成果：{json.dumps(learning_objectives, ensure_ascii=False)}

## 已去重的规划上下文
{json.dumps(skeleton_context, ensure_ascii=False)}

## 分片边界
{shard_contract}

## 约束
1. `sections` 必须按输入顺序完整返回当前输入中的全部 `node_id`，不得返回输入之外的小节。
2. 每个知识点使用稳定、简短且全课唯一的 `knowledge_key`，当前分片从
   `{new_key_example}` 开始连续编号；规范名称与一句话陈述全课唯一，后续批次不得
   改名或改写。
3. 每节通常首次负责 2-4 个可单独解释、练习和诊断的原子知识点；名称和陈述必须
   简洁，知识名不得复制小节标题，也不得写成教学动作。
   **例外——同一对象的多种表示要各自成点**：若一个对象在本节以多种表示形式
   出现（解析式与图像、文字规则与符号公式、递推式与通项式、结构式与分子式
   等），**每种表示各自成为一个独立知识点**，此时本节可以超过 4 个。
   判据是"换一种写法后说的还是同一件事"；若两者结论不同，那不是表示法，
   是两个本来就独立的知识点。表示法类知识点在详细教案里 `knowledge_type`
   标 `representation`，并用 `equivalent_to` 与它所表示的对象相连。
4. 每个键只有一个 `owner_node_id`。复用只能发生在负责小节之后，并同时登记到注册表
   的 `reused_in_node_ids` 与对应小节的 `reused_knowledge_keys`。
5. `prerequisite_keys` 只能引用当前知识之前已经定义的键；没有前置时留空。
6. `module_ids` 只能从负责小节 `module_set_id` 指向的全局 `module_sets` 中选择，
   至少选择一个。
7. `difficulty_baseline` 只出现一次；各小节只叠加自己的 `difficulty_delta`。

## JSON Schema
{{
  "knowledge_registry": [
    {{
      "knowledge_key": "K001",
      "name": "原子知识规范名称",
      "statement": "可独立成立的一句话规范陈述",
      "owner_node_id": "L2-1-1",
      "reused_in_node_ids": [],
      "prerequisite_keys": [],
      "module_ids": ["core_explanation"]
    }}
  ],
  "sections": [
    {{
      "node_id": "L2-1-1",
      "owned_knowledge_keys": ["K001"],
      "reused_knowledge_keys": []
    }}
  ]
}}""".strip()

    @staticmethod
    def _compact_skeleton_planning_context(
        planning_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Remove fields repeated identically across every skeleton section."""
        sections = [
            dict(item)
            for item in planning_context.get("sections") or []
            if isinstance(item, dict)
        ]
        module_set_ids: dict[tuple[str, ...], str] = {}
        module_sets: dict[str, list[str]] = {}
        compact_sections: list[dict[str, Any]] = []
        for item in sections:
            compact = dict(item)
            module_signature = tuple(
                str(value)
                for value in compact.pop(
                    "allowed_module_ids",
                    [],
                )
            )
            module_set_id = module_set_ids.get(module_signature)
            if module_set_id is None:
                module_set_id = f"M{len(module_set_ids) + 1}"
                module_set_ids[module_signature] = module_set_id
                module_sets[module_set_id] = list(module_signature)
            compact["module_set_id"] = module_set_id
            for key in (
                "chapter_id",
                "difficulty_delta",
                "evidence_hints",
                "prerequisite_node_ids",
            ):
                if compact.get(key) in ("", None, [], {}):
                    compact.pop(key, None)
            compact_sections.append(compact)
        return {
            **planning_context,
            "module_sets": module_sets,
            "sections": compact_sections,
        }

    def build_teaching_plan_skeleton_v3_correction_prompt(
        self,
        *,
        original_prompt: str,
        issues: list[dict[str, Any]],
    ) -> str:
        issue_text = "\n".join(
            f"- {clip_text(item.get('message'), 280)}" for item in issues[:12]
        ) or "- 上一次输出不是完整有效的骨架 JSON"
        original_prompt = clip_text(original_prompt, 8500)
        return f"""## 全课知识职责骨架 V3 纠正

上一次骨架存在以下结构或引用错误：
{issue_text}

只修复错误并重新输出完整骨架 JSON。不得展开详细教案、正文、题目或解释。

{original_prompt}
""".strip()

    @staticmethod
    def _batch_evidence_digest(
        batch_sections: list[dict[str, Any]],
        *,
        detail_level: str,
    ) -> list[dict[str, Any]]:
        """按小节汇总本批次可依据的证据摘要。

        证据已经随小节带进来（`evidence_hints`），但埋在 `batch_sections`
        的 JSON 里、没有任何提示语，模型没有被要求据此写作。单列一段并在
        约束里点名，才算真的"教案读得到证据"。

        长度按详细度收紧：教案批次 prompt 已在撞 token 上限，这里宁可短。
        """
        summary_chars = (
            220 if detail_level == "full"
            else 140 if detail_level == "compact"
            else 60
        )
        per_section = 4 if detail_level == "full" else 2
        digest: list[dict[str, Any]] = []
        for section in batch_sections or []:
            if not isinstance(section, dict):
                continue
            hints = [
                item for item in (section.get("evidence_hints") or [])
                if isinstance(item, dict)
            ][:per_section]
            if not hints:
                continue
            digest.append({
                "node_id": str(section.get("node_id") or ""),
                "evidence": [
                    {
                        "evidence_id": str(item.get("evidence_id") or ""),
                        "source_kind": str(item.get("source_kind") or ""),
                        "kind": str(item.get("kind") or ""),
                        "summary": clip_text(
                            str(item.get("summary") or ""),
                            (
                                4000
                                if detail_level == "full"
                                and item.get("source_kind") == "uploaded_lesson_plan"
                                else summary_chars
                            ),
                        ),
                        "source_order_start": item.get("source_order_start"),
                        "source_order_end": item.get("source_order_end"),
                        "fidelity_contract": str(
                            item.get("fidelity_contract") or ""
                        ),
                    }
                    for item in hints
                ],
            })
        return digest

    def build_teaching_plan_batch_v3_prompt(
        self,
        *,
        course_title: str,
        positioning: str,
        batch_spec: dict[str, Any],
        batch_sections: list[dict[str, Any]],
        knowledge_registry: list[dict[str, Any]],
        section_identities: list[dict[str, Any]],
        module_catalog: list[dict[str, Any]],
        skeleton_revision_id: str,
        overall_guidance: dict[str, Any] | None = None,
        detail_level: str = "full",
        generate_knowledge_contract: bool = False,
    ) -> str:
        bounded = compact_batch_inputs(
            batch_sections=batch_sections,
            knowledge_registry=knowledge_registry,
            section_identities=section_identities,
            module_catalog=module_catalog,
            detail_level=detail_level,
        )
        batch_sections = bounded["batch_sections"]
        knowledge_registry = bounded["knowledge_registry"]
        section_identities = bounded["section_identities"]
        module_catalog = bounded["module_catalog"]
        # 证据从小节里抽出来单列一段：批次 prompt 此前**完全看不到资料原文**，
        # 于是知识点的成立条件、边界、易错点只能凭模型常识写——
        # 而知识库正是对这一步产出的确定性重排，断在这里就一路断到底。
        batch_evidence = self._batch_evidence_digest(
            batch_sections,
            detail_level=detail_level,
        )
        overall_guidance = compact_value(
            overall_guidance or {},
            max_string_chars=(
                180 if detail_level == "full"
                else 120 if detail_level == "compact"
                else 72
            ),
            max_list_items=(
                8 if detail_level == "full"
                else 5 if detail_level == "compact"
                else 3
            ),
            max_depth=3,
        )
        if detail_level != "full":
            course_title = clip_text(
                course_title, 180 if detail_level == "compact" else 96
            )
            positioning = clip_text(
                positioning, 240 if detail_level == "compact" else 120
            )
            batch_spec = compact_value(
                batch_spec,
                max_string_chars=96,
                max_list_items=8,
                max_depth=2,
            )
        header = (
            "## 单讲知识责任与完整教案联合生成 V4"
            if generate_knowledge_contract
            else "## 详细小节教案批次 V3"
        )
        opening = (
            "本讲知识责任尚未生成。请在同一次响应中确定原子知识身份、每节唯一责任，"
            "并直接展开完整教案；不得把知识骨架与教案拆成两轮请求。"
            if generate_knowledge_contract
            else (
                "全课知识身份已经确认。你只展开当前批次，不得新增、删除、改名或迁移"
                "知识键；不得修改其他批次。"
            )
        )
        knowledge_context = (
            "由本次响应共同生成；不要依赖任何前置知识骨架请求。"
            if generate_knowledge_contract
            else json.dumps(knowledge_registry, ensure_ascii=False)
        )
        identity_context = (
            "由本次响应共同生成；每个小节与该小节完整教案放在同一个 sections 对象中。"
            if generate_knowledge_contract
            else json.dumps(section_identities, ensure_ascii=False)
        )
        joint_constraints = (
            "0A. `knowledge_registry` 与 `sections` 必须在同一个 JSON 中返回；"
            "每个 section 同时包含 `owned_knowledge_keys`、`reused_knowledge_keys` 和完整教案字段。\n"
            "0B. 响应内临时知识键按小节顺序从 `K001` 连续编号且本讲唯一，系统会在"
            "本地将它们确定性映射为正式稳定 ID；每个知识键只有一个 `owner_node_id`。"
            "每节通常首次负责 2-4 个可独立解释、练习和诊断的原子知识点。\n"
            "0C. `module_ids` 只能使用对应小节 `allowed_module_ids` 中的值，至少一个。"
            "注册表的 owner、复用位置与 sections 中的职责必须完全一致。\n"
            "0D. `knowledge_details` 必须逐一展开本节全部 `owned_knowledge_keys`。"
            "知识责任与详细教案必须语义一致，不能先写一套责任、再写另一套内容。"
            if generate_knowledge_contract
            else ""
        )
        registry_schema = (
            '''"knowledge_registry": [
    {
      "knowledge_key": "K001",
      "name": "原子知识规范名称",
      "statement": "可独立成立的一句话规范陈述",
      "owner_node_id": "L2-1-1",
      "reused_in_node_ids": [],
      "prerequisite_keys": [],
      "module_ids": ["core_explanation"]
    }
  ],'''
            if generate_knowledge_contract
            else ""
        )
        identity_schema = (
            '''"owned_knowledge_keys": ["K001"],
      "reused_knowledge_keys": [],'''
            if generate_knowledge_contract
            else ""
        )
        return f"""{header}

{opening}只输出有效 JSON，不输出正文、题目、评分、解释或 Markdown 围栏。

## 课程
- 课程：{course_title}
- 定位：{positioning}

## 共享课程块目录（只出现一次）
{json.dumps(module_catalog, ensure_ascii=False)}

## 总体教案引领（与教师视图同源，只读）
{json.dumps(overall_guidance, ensure_ascii=False)}

## 当前批次
- 批次：{json.dumps(batch_spec, ensure_ascii=False)}
- 骨架修订：{skeleton_revision_id}

## 当前小节（已去重）
{json.dumps(batch_sections, ensure_ascii=False)}

## 本批次可依据的资料证据（只读，来自教师上传资料与已确认联网来源）
{json.dumps(batch_evidence, ensure_ascii=False)}

## 当前批次知识与直接依赖闭包（只读）
{knowledge_context}

## 当前批次知识职责（只读）
{identity_context}

## 约束
{joint_constraints}
1. `sections` 必须按批次指定顺序返回，`knowledge_details` 必须按本节
   `owned_knowledge_keys` 顺序逐个展开，不能展开复用键。
2. 每个知识详情必须给出成立条件或边界、可观察能力、至少一个可信易错点和可验证
   掌握标准；易错点必须包含具体错误表现、判别方法与修复策略。
3. `knowledge_type` 只能取以下七类之一，取值不在表内会被系统**静默改写成
   `definition`**，不会报错也不会提示，所以必须选准：
   `definition` 定义；`principle` 原理；`rule` 规则判据；`method` 方法；
   `condition` 成立条件；`procedure` 操作流程；
   `representation` **表示法**（同一对象的另一种写法/记号/形式，
   例如解析式与图像、数表与公式）。不要自造词表外的取值。
4. 掌握标准要能被判定：`observable_performance` 写清用什么任务、做到什么程度算
   达标（能数的就写数量，如"3 道变式题全对"），`verification_method` 写清用什么
   题、看什么作答表现判定。不要写"理解××""掌握××"这类无法判定的话。
   `required_independence` 取 `scaffolded`/`guided`/`independent`（给范例/给追问/
   完全独立），`required_transfer` 取 `recall`/`procedure`/`variation`/`novel`
   （复述/照流程/变式/新情境）。两项按本知识点实际要求选，不要所有标准都填同一个值。
5. `concept_group` 是本节知识点的分组，不是知识点的别名：同一小节里彼此相关的
   知识点必须共用同一个组名，每组通常聚合 2-4 个知识点。组名写知识问题域
   （例如"容量与扩容"），不要写成某个知识点的改写；一节通常 1-2 个组，只有确实
   互不相关时才增加。不要为了让组数变多而硬拆，也不要给每个知识点各起一个组名。
6. 关系端点只能使用全局注册表中的键。当前批次不得把未来知识当作已经掌握的复用，
   也不得修改骨架中已确认的前置关系。
7. `relation_type` 按语义从六类中选，不要一律写 `prerequisite`；缺必填字段的关系整条丢弃。
   `prerequisite` 学习顺序依赖；`applies_to` source 是方法或原理、target 是应用对象；
   `generalizes` source 是一般情形、target 是其特例；`equivalent_to` 同一实质不同表述（对称）；
   `derives` target 可由 source 推出，必填 `derivation_steps`（有序关键步骤，不可为空）；
   `contrasts_with` 两者易混需辨析（对称），必填 `distinction`（凭什么区分两者）。
   本节教学上确实成立的前置之外关系都要给出，但不要为凑数编造。
   **关系写在引入该知识的那一节，不要攒到批次最后一节再一起写。** 本批次包含
   多个小节，每一节都要各自写出连接**本节新知识**的关系；一节新引入了知识却
   一条关系都不给，等于把这些知识孤立地丢进知识网。逐节检查：本批次每个小节的
   `knowledge_relations` 是否都非空。
   寻找关系时按下面的信号逐个自查，这三类最容易被漏掉：
   - 写了某个知识点的易错点 `confused_with` 字段时，该易错对象若也是本节知识，
     两者之间就应有一条 `contrasts_with`——学生会混淆，正是需要辨析的信号。
   - 同一个对象在本节出现了两种表述（定义式与图像、文字规则与符号公式、
     递推式与通项式），两者之间是 `equivalent_to`，不是前置。**尤其检查
     `knowledge_type` 标成 `representation` 的知识点**：表示法本身不是新内容，
     它一定是某个已有对象的另一种写法，那个对象若也在本节，就该连一条
     `equivalent_to`。判据是"两边说的是同一件事，只是换了写法/记号/形式"，
     而不是"两边有关系"。
   - 一个知识点是另一个的特例（参数取特定值、条件更强、只适用于更窄的范围），
     方向是一般 → 特例的 `generalizes`，不要写成 `prerequisite`。
   某一类自查后确实不成立就不写那一类，宁缺毋滥；本节只有两三个知识点时
   缺少上面这几类是正常的。但"某一类没有"不等于"整节没有关系"——覆盖要求仍然要满足。
8. `teaching_modules` 只能使用当前小节允许的模块 ID；知识键只能来自本节负责或复用
   集合。每个模块必须完整写清“教师动作 → 学习者可观察行动 → 产出与检查 → 反馈后的下一步”；
   不能只写教师讲什么，也不能用“参与讨论、认真听讲”冒充学习证据。
9. `teaching_purpose` 与 `teaching_guidance` 必须把总体教案的课程成果、教学主线和
   评价策略落实到本节，但不得复述总体教案，也不得改变已确认的目录、知识身份或模块集合。
10. 每节的 `lesson_archetype` 是当前学科课型合同。详细教案必须落实其教学目的、
   成果证据与质量底线；不能把同一学科的所有小节写成相同课堂流程，也不能越权创造课型外模块。
11. 若总体教案给出课堂交付约束，每节应给出可执行的时长、重点难点、师生活动、资源、
   课堂检查、作业或备注；这些字段必须与教学场景和总课时相容，未知内容可以省略，不能编造资料来源。
12. 「本批次可依据的资料证据」是本节已确认的教师资料与联网来源。写成立条件、边界、
   易错点与掌握标准时**必须优先依据这些证据**，不得与证据冲突；证据未覆盖的部分
   照常用学科通识补足，但不得把通识伪装成资料结论，也不得编造证据里没有的来源、
   数据或结论。该段为空时说明本节无可用证据，据实按通识展开即可。
13. 证据中 `source_kind=uploaded_lesson_plan` 表示老师明确选中的原教案主来源。
   必须按照 `source_order_start/source_order_end` 和原分块顺序忠实吸收：已有字段、
   教学环节、师生活动和原文表述优先保留，只补齐缺失项；不得为了套系统模板而重排、
   改写或删去原教案已有结构。原教案与课程大纲或已确认知识范围冲突时，不得静默覆盖，
   应保留可兼容内容，并把冲突写入备注或审核提示。
14. 「正式教案模板」是同一份结构化教案的展示和导出契约，不是第二份教案。每讲目标只分为
   `knowledge_objectives`（知识目标）、`ability_objectives`（能力目标）和
   `education_objectives`（育人目标）三类；育人目标必须由本讲真实内容支撑，没有时保持空数组，
   不得用创新、迁移或一般课堂活动冒充。每讲同时返回 `pre_study`、
   `key_analysis`、`case_intro`、`practice`、`class_summary`、`extension_learning` 字符串数组；
   以及 `homework_submission`、`homework_evaluation`、`next_lesson_connection` 字符串。
   总结、评价标准和衔接必须结合本讲内容生成；提交渠道、截止时间等必须由教师决定的事实，
   只有输入已提供时才填写，否则 `homework_submission` 留空。`teaching_activity_photos` 只保留已有引用，
   不得生成照片、链接、课堂过程或参与情况。
15. 正式教案外壳保持“本讲基本信息—教学目标—重点难点—本讲教学设计—教学资料与活动记录”；
   具体教学块只放在课堂教学过程中。流程必须完整承担「进入问题或任务 → 核心教学 → 学习者行动
   → 就近证据 → 反馈调整 → 迁移或收束」，但块名称和顺序由学科、目标与本讲课型决定，
   不得把所有课程强套成「案例导入—理论讲授—实践操作」同一顺序。
16. `resource_refs` 是给学生继续学习的推荐阅读，不能留空。优先使用已给定的课程资料或已确认来源，
   写成可识别的引用；若当前没有来源，可依据可靠的学科通识推荐 1—3 项权威教材、论文、标准或
   机构资料，并以“AI 推荐（待教师确认）”开头。引用至少包含作者或机构、题名和与本讲相关的章节
   或主题；只有确有把握时才写版次和年份，不得编造页码、链接、DOI、ISBN 或资料中的结论。
17. `engagement_mode` 只能取 `passive|active|constructive|interactive`。关键学习环节优先让学生
   产生解释、推导、作品、操作记录或基于证据的互动；互动必须围绕共同产物或观点修订，不能只写分组。
18. `adaptation_options` 至少覆盖达到、部分达到和未达到三种现场结果。调整可以改变提示、表征、
   分组、任务粒度或挑战度，但不得静默降低本讲核心目标与学科标准。
19. 教师可见教案必须像真实备课文本，而不是生成报告：`teacher_activities` 写“展示、提问、
    板演、巡视、追问、归纳”等可执行动作，`student_activities` 写学生实际进行的计算、
    作图、比较、解释、讨论或操作；`key_difficulties`、`in_class_checks`、`homework` 均用简洁
    的课堂语言。不要把知识键、内部证据流程、输入输出对象、系统策略或质量门写进这些字段。
20. `teaching_notes` 只保留教师上课前真正需要看的实施提醒，例如易错点、时间取舍、板书安排、
    分层提示和现场补救。不得复述“资料不足、不得编造来源、不能越界、系统将如何处理”等生成
    规则；这些规则只在内部执行，不能变成教师备注。
21. 教师可见语言要准确、顺畅、简洁。避免“调取经验并作出初始判断”“建立价值与任务边界”
    这类抽象套话，改成针对当前学科内容的真实动作，例如“观察两条割线，先判断哪一条斜率更大”。
    同一含义只说一次；先写对象与条件，再写动作与检查，不用“首先—其次—再次—最后”机械串联。
22. 学科准确性优先于文风：定义、公式、条件、单位、符号与结论必须和已确认的知识表一致；
    例题与课堂检查要给出可复核的依据。数学结果用代入、求导、量纲或图像至少完成一种核验；
    其他学科使用本学科相应的证据与核验方式。无法从证据或通识确认的事实不进入成品。

## JSON Schema
{{
  {registry_schema}
  "sections": [
    {{
      "node_id": "L2-1-1",
      {identity_schema}
      "knowledge_objectives": ["本讲需要理解和掌握的知识"],
      "ability_objectives": ["学生能够完成的可观察学科任务"],
      "education_objectives": [],
      "knowledge_details": [
        {{
          "knowledge_key": "K001",
          "concept_group": "知识问题域；本节相关知识点共用同一组名，通常每组 2-4 个知识点",
          "group_description": "本组作用与边界；描述整组，不是描述单个知识点",
          "knowledge_type": "definition",
          "conditions": ["成立条件"],
          "boundaries": ["不适用范围"],
          "counterexamples": [],
          "capability_points": [{{
            "name": "能力名称",
            "observable_behavior": "独立可观察动作",
            "required_evidence_types": ["practice_attempt"]
          }}],
          "misconceptions": [{{
            "name": "错误模式",
            "observable_error_pattern": "具体错误表现",
            "confused_with": "易混对象",
            "discrimination": "判别方法",
            "repair_strategy": "修复策略"
          }}],
          "mastery_criteria": [{{
            "name": "掌握标准",
            "observable_performance": "独立表现；写清用什么任务、做到什么程度算达标，能数的就给数量",
            "required_independence": "scaffolded|guided|independent 三选一，按本知识点实际要求选",
            "required_transfer": "recall|procedure|variation|novel 四选一，按本知识点实际要求选",
            "verification_method": "验证方法；写清用什么题、看什么作答表现判定",
            "required_evidence_types": ["practice_attempt"]
          }}],
          "aliases": []
        }}
      ],
      "knowledge_relations": [{{
        "source_key": "K001", "target_key": "K002",
        "relation_type": "prerequisite", "reason": "具体语义理由"
      }}, {{
        "source_key": "K002", "target_key": "K003",
        "relation_type": "derives", "reason": "K003 由 K002 推出",
        "derivation_steps": ["从 K002 出发", "代入成立条件", "整理得到 K003"]
      }}, {{
        "source_key": "K003", "target_key": "K004",
        "relation_type": "contrasts_with", "reason": "两者常被混同",
        "distinction": "K003 是瞬时变化率，K004 是累积总量"
      }}, {{
        "source_key": "K002", "target_key": "K005",
        "relation_type": "applies_to", "reason": "K002 是解 K005 这类问题的方法"
      }}, {{
        "source_key": "K005", "target_key": "K006",
        "relation_type": "equivalent_to", "reason": "同一结论的两种表述，给定条件下可互相推出（对称）"
      }}, {{
        "source_key": "K006", "target_key": "K001",
        "relation_type": "generalizes", "reason": "K006 是一般情形，K001 是它在参数取特定值时的特例"
      }}],
      "teaching_modules": [{{
        "module_id": "core_explanation",
        "teaching_purpose": "本节具体教学职责",
        "knowledge_keys": ["K001"],
        "teaching_guidance": "正文必须体现的讲法或学习者行动",
        "planned_minutes": 15,
        "teacher_activity": "教师演示或追问的具体动作",
        "student_activity": "学生完成的可观察动作",
        "expected_output": "学生在本环节留下的回答、过程、作品或操作结果",
        "check_method": "教师依据什么表现与标准判断当前达成情况",
        "feedback_strategy": "怎样指出差距、给出下一步并安排再次表现",
        "adaptation_options": ["达到标准时怎样推进", "部分达到时怎样补支架", "未达到时怎样重教并复查"],
        "engagement_mode": "constructive",
        "access_support": "怎样减少无关进入障碍，同时保持核心标准",
        "grouping": "个人、同伴或小组及其责任方式",
        "transition": "本环节证据怎样自然衔接下一环节",
        "handout_ppt_mapping": "本环节在讲义中的内容位置与 PPT 页面任务"
      }}],
      "planned_minutes": 45,
      "key_difficulties": ["需要重点突破的概念或操作"],
      "teacher_activities": ["教师组织的关键活动"],
      "student_activities": ["学生完成的关键活动"],
      "resource_refs": ["已给定资源的名称或标识"],
      "in_class_checks": ["可观察的课堂检查"],
      "homework": ["课后练习或迁移任务"],
      "homework_submission": "教师已提供时填写提交渠道与截止时间，否则留空",
      "homework_evaluation": "结合本讲任务写清准确性、过程、依据或迁移表现的评价标准",
      "next_lesson_connection": "本讲成果怎样支持下一讲；课程最后一讲则说明怎样完成整课收束",
      "teaching_notes": ["实施提醒"],
      "pre_study": ["课前完成的阅读、观察或小任务"],
      "key_analysis": ["对本节重点与难点的教学分析"],
      "case_intro": ["与本节内容直接相关的导入情境或问题"],
      "practice": ["学生实际执行的操作、练习或产出"],
      "class_summary": ["回到目标的当堂总结与检查"],
      "extension_learning": ["确有需要时的迁移或拓展任务"],
      "teaching_activity_photos": []
    }}
  ]
}}""".strip()

    def build_teaching_plan_batch_v3_correction_prompt(
        self,
        *,
        original_prompt: str,
        issues: list[dict[str, Any]],
    ) -> str:
        issue_text = "\n".join(
            f"- {clip_text(item.get('message'), 280)}" for item in issues[:12]
        ) or "- 上一次输出不是完整有效的批次 JSON"
        original_prompt = clip_text(original_prompt, 8500)
        return f"""## 详细教案批次 V3 纠正

当前批次存在以下结构或引用错误：
{issue_text}

只重新输出当前批次的完整 JSON。骨架修订、知识键、目录和批次范围不得改变；其他
已完成批次保持不变。不要输出解释或 Markdown 围栏。

{original_prompt}
""".strip()
    def build_content_prompt(
        self,
        *,
        course_data: dict[str, Any],
        node: dict[str, Any],
        context: str,
        existing_draft: str = "",
        detail_level: str = "full",
    ) -> tuple[str, str]:
        profile = course_data.get("subject_pedagogy_profile") or {}
        difficulty_profile = course_data.get("difficulty_profile") or {}
        difficulty_contract = node.get("difficulty_contract") or {}
        modules = node.get("module_plan") or []
        lesson_archetype = node.get("lesson_archetype") or {}
        composition_profile = course_data.get("course_composition_profile") or {}
        if detail_level != "full":
            max_text = 180 if detail_level == "compact" else 96
            profile = compact_value(
                profile,
                max_string_chars=max_text,
                max_list_items=6 if detail_level == "compact" else 3,
                max_depth=3,
            )
            difficulty_profile = compact_value(
                difficulty_profile,
                max_string_chars=max_text,
                max_list_items=6 if detail_level == "compact" else 3,
                max_depth=3,
            )
            difficulty_contract = compact_value(
                difficulty_contract,
                max_string_chars=max_text,
                max_list_items=6 if detail_level == "compact" else 3,
                max_depth=3,
            )
            composition_profile = compact_value(
                composition_profile,
                max_string_chars=max_text,
                max_list_items=6 if detail_level == "compact" else 3,
                max_depth=3,
            )
            lesson_archetype = compact_value(
                lesson_archetype,
                max_string_chars=max_text,
                max_list_items=4 if detail_level == "compact" else 2,
                max_depth=2,
            )
            context = clip_text(
                context,
                4200 if detail_level == "compact" else 700,
            )
        if detail_level == "minimal":
            module_contract = "\n".join(
                f"- `## {clip_text(item.get('label') or item.get('module_id'), 48)}`："
                f"{clip_text(item.get('output_contract') or item.get('prompt_instruction'), 80)}"
                for item in modules[:12]
                if isinstance(item, dict)
            )
        else:
            module_contract = "\n".join(
                (
                    f"- {'必需' if item.get('required', True) else '可选'}模块 "
                    f"`## {clip_text(item.get('label'), 80) if detail_level == 'compact' else item.get('label')}` "
                    f"[角色={item.get('block_role') or module_block_role(item.get('module_id'))}] "
                    f"[来源={item.get('composition_source') or 'subject_required'}；"
                    f"实例={item.get('module_instance_id') or item.get('module_id')}；"
                    f"难度={format_block_difficulty(item.get('block_difficulty_contract') or {})}]："
                    f"{clip_text(item.get('output_contract'), 180) if detail_level == 'compact' else item.get('output_contract')}；"
                    f"{clip_text(item.get('prompt_instruction'), 180) if detail_level == 'compact' else item.get('prompt_instruction')}"
                )
                for item in modules
            )
        continuation = bool(existing_draft.strip())
        grounding_contract = node.get("grounding_contract") or {}
        allowed_evidence = list(dict.fromkeys(
            list(grounding_contract.get("required_evidence_ids") or [])
            + list(grounding_contract.get("optional_evidence_ids") or [])
        ))
        knowledge_context, teaching_context, course_knowledge_context = self._node_knowledge_context(
            course_data, node
        )
        teaching_guidance = format_generation_teaching_guidance(
            course_data,
            node,
            compact=detail_level != "full",
        )
        coherence_context = course_coherence_prompt_context(
            course_data,
            str(node.get("node_id") or ""),
        )
        if detail_level == "compact":
            course_knowledge_context = clip_text(course_knowledge_context, 3200)
            coherence_context = clip_text(coherence_context, 1800)
        elif detail_level == "minimal":
            course_knowledge_context = clip_text(course_knowledge_context, 900)
            coherence_context = clip_text(coherence_context, 420)
        continuation_contract = ""
        if continuation:
            compact_draft = self._compact_continuation_draft(
                existing_draft,
                max_chars=(
                    6000
                    if detail_level == "full"
                    else 2600
                    if detail_level == "compact"
                    else 700
                ),
            )
            continuation_contract = f"""
## 已保存草稿的有界恢复上下文
{compact_draft}

只输出从草稿最后一个完整句子之后开始的续写内容。不要重复标题和已有段落，不要解释你在续写。"""

        if detail_level == "minimal":
            node_name = clip_text(node.get("node_name"), 96)
            objective = clip_text(node.get("learning_objective"), 160)
            scope = clip_text(node.get("scope_boundary"), 160)
            key_points = "；".join(
                clip_text(item, 72) for item in (node.get("key_points") or [])[:8]
            )
            assessments = "；".join(
                clip_text(item, 80) for item in (node.get("assessment") or [])[:4]
            )
            evidence_ids = "；".join(allowed_evidence[:12]) or "无"
            system_prompt = f"""## 有界正文生成契约
只输出当前小节可保存的 Markdown 正文，不输出解释、计划或任务复述。
按下列顺序和原始标签完整输出每个 `##` 教学模块；不得重写课程目录或提前讲后续小节。
每个模块首段必须明确写出负责的知识规范名称。例子、练习与检查必须共享同一知识口径。
不得编造来源；使用资料事实时追加 `[[evidence:证据ID]]`，且只能用允许列表中的 ID。
数学使用 `$...$` 或 `$$...$$`；列表使用真实 Markdown 语法。

## 课程
- 课程：{clip_text(course_data.get('course_name'), 96)}
"""
            node_brief = f"""## 当前小节
- 节点：{node_name}
- 目标：{objective}
- 知识：{key_points or '按当前知识库契约'}
- 范围：{scope or '只完成当前小节责任'}
- 验收：{assessments or '给出可检查的学习任务'}

## 总体教案对本节的引领
{teaching_guidance}

## 当前课程知识库（当前节点切片）
{course_knowledge_context}

## 教学模块
{module_contract or '- `## 核心教学`：解释、示例、行动与检查。'}

## 允许证据
{evidence_ids}

## 持久化上下文（已压缩）
{context or '无额外资料或前序摘要。'}
{continuation_contract}"""
            instruction = (
                f"续写「{node_name}」，只输出追加正文。"
                if continuation
                else f"撰写「{node_name}」正文，只输出 Markdown。"
            )
            return f"{node_brief}\n\n{instruction}", system_prompt

        course_name = (
            clip_text(course_data.get("course_name"), 180)
            if detail_level == "compact"
            else course_data.get("course_name", "")
        )
        audience = (
            clip_text(course_data.get("target_audience", "大学生"), 120)
            if detail_level == "compact"
            else course_data.get("target_audience", "大学生")
        )
        node_name = (
            clip_text(node.get("node_name"), 160)
            if detail_level == "compact"
            else node.get("node_name", "")
        )
        learning_objective = (
            clip_text(node.get("learning_objective"), 260)
            if detail_level == "compact"
            else node.get("learning_objective", "")
        )
        key_points = [
            clip_text(item, 120)
            for item in (node.get("key_points") or [])[:12]
        ] if detail_level == "compact" else list(node.get("key_points") or [])
        knowledge_structure = (
            compact_value(
                node.get("knowledge_structure") or [],
                max_string_chars=180,
                max_list_items=8,
                max_depth=4,
            )
            if detail_level == "compact"
            else node.get("knowledge_structure", [])
        )
        misconceptions = [
            clip_text(item, 120)
            for item in (node.get("misconceptions") or [])[:8]
        ] if detail_level == "compact" else list(node.get("misconceptions") or [])
        assessment = [
            clip_text(item, 140)
            for item in (node.get("assessment") or [])[:6]
        ] if detail_level == "compact" else list(node.get("assessment") or [])
        scope_boundary = (
            clip_text(node.get("scope_boundary"), 260)
            if detail_level == "compact"
            else node.get("scope_boundary", "")
        )

        system_prompt = f"""## 输出契约
1. 只输出可直接保存的 Markdown 正文或续写，不输出寒暄、身份、计划、边界确认或任务复述。
2. 只讲当前小节，不重写整章，不提前展开后续节点。
3. `##` 二级标题是同级教学块的语义边界。每个必需模块都必须以契约中的原始标签输出一次（可在标签后用冒号补充说明）；`###` 及更深标题只用于模块内部。
4. 不编造论文、来源、链接、年份、机构或未上传资料。
5. 基础课程正文只服从持久化课程蓝图，不根据临时学习状态改变主线。
6. 如果使用资料事实，必须在对应陈述后追加 `[[evidence:证据ID]]`；证据 ID 只能来自当前节点允许列表。
7. 证据标记不是参考文献装饰，不能把讲法参考或弱背景伪装成事实来源。
8. 输出前完成内部一致性检查；正文不得保留“我的计算有误”“等待，更正”“请重新检查任务”等模型自我纠错痕迹，也不得让题干、答案和量规互相矛盾。
9. 正文中的解释、例子、练习和反馈必须共享当前课程知识库的知识、能力、易错和掌握标准，不得各写各的。
10. 当前节点名称已经由页面显示，正文不得把本节标题重复写成二级标题，也不得输出只有标题没有正文的空模块。
11. 每个 `##` 教学块必须在首段明确写出它实际讲解、练习或检查的一个或多个知识点规范名称；不得只用“本概念”“上述方法”等代词。规范名称来自下方“当前课程知识库契约”，用于建立正文块到知识点的精确绑定。
12. `## 检查与反馈` 是静态检查参考，不得声称已经评价当前学生。对应多个学习任务时，每个任务必须使用 `### 任务 N：名称` 作为内部边界，并在任务内清楚区分核对标准、参考结论、推导依据和典型错误；不得把所有答案压成一个长段落。
13. Markdown 列表必须使用真实的 `1.` 或 `-` 列表语法并保留必要空行。任务级标题使用 `###`，不要用单独一行加粗文字伪装标题。
14. 数学表达必须使用 `$...$` 或 `$$...$$`，反引号只用于代码标识、命令或程序片段；不得用反引号书写幂、上下标、分式、复杂度或数学关系。
15. 下方“总体教案对本节的引领”是课程内容选择与讲法的上位约束：正文必须推进总体成果、体现教学主线并产出对应评价证据；不得把教案条目原样抄成正文。
16. 下方“本节学科课型”规定当前小节特有的学习行为和成果证据。必须体现该课型与前后小节的差异，不能机械复用同一学科的固定段落套路。

## 课程
- 名称：{course_name}
- 学习对象：{audience}
- 教学画像：{json.dumps(profile, ensure_ascii=False)}

## 课程块编排画像
{format_composition_profile(composition_profile)}

## 全课难度能力契约
{format_difficulty_profile(difficulty_profile)}

## 当前课程知识身份边界
{knowledge_context}

## 当前课程教学边界
{teaching_context}

内容必须通过学习任务、支架方式、独立性和验收证据展现难度；不得仅靠术语、篇幅、公式、代码量或题量展现难度。
"""
        # 节点专属内容放进 user 消息：system prompt 因此在全课各节之间
        # 完全一致，可缓存前缀覆盖整个 system 段而不只是它的前半部分。
        node_brief = f"""## 总体教案对本节的引领
{teaching_guidance}

## 本节学科课型
{json.dumps(lesson_archetype, ensure_ascii=False)}

## 当前节点契约
- 节点：{node_name}
- 学习目标：{learning_objective}
- 知识点：{'；'.join(key_points)}
- 细知识结构：{json.dumps(knowledge_structure, ensure_ascii=False)}
- 前置节点：{'；'.join(node.get('prerequisite_node_ids', []))}
- 常见误区：{'；'.join(misconceptions)}
- 验收标准：{'；'.join(assessment)}
- 范围边界：{scope_boundary}

## 当前课程知识库契约
{course_knowledge_context}

## 全课总编契约
{coherence_context}

## 当前节点难度契约
{format_node_difficulty_contract(difficulty_contract)}

## 当前节点证据契约
- 必用证据：{'；'.join(grounding_contract.get('required_evidence_ids', [])) or '无'}
- 可选证据：{'；'.join(grounding_contract.get('optional_evidence_ids', [])) or '无'}
- 允许的全部证据 ID：{'；'.join(allowed_evidence) or '无'}
- 是否允许模型通用知识：{'是' if grounding_contract.get('allow_general_knowledge', True) else '否'}

## 本节教学模块
{module_contract or '- 使用通用本节任务、核心教学、学习者行动和反馈检查。'}

## 持久化上下文
{context or '无额外资料或前置摘要。'}
{continuation_contract}"""
        instruction = (
            f"继续撰写「{node_name}」，只输出追加正文。"
            if continuation
            else f"撰写「{node_name}」完整正文，只输出 Markdown。"
        )
        user_prompt = f"{node_brief}\n\n{instruction}"
        return user_prompt, system_prompt

    @staticmethod
    def _compact_continuation_draft(
        content: str,
        *,
        max_chars: int = 6000,
    ) -> str:
        if len(content) <= max_chars:
            return content
        headings = re.findall(r"(?m)^#{1,3}\s+(.+)$", content)
        heading_text = clip_text(
            "；".join(headings[-12:]) or "未识别到模块标题",
            min(900, max(100, max_chars // 3)),
        )
        tail_budget = max(120, max_chars - len(heading_text) - 120)
        return (
            f"- 已完成模块：{heading_text}\n"
            f"- 已省略较早草稿 {len(content) - tail_budget} 个字符；"
            "以下仅保留最近尾部用于无重复续写：\n"
            f"{content[-tail_budget:]}"
        )

    def _node_knowledge_context(
        self,
        course_data: dict[str, Any],
        node: dict[str, Any],
    ) -> tuple[str, str, str]:
        node_id = str(node.get("node_id") or "")
        course_knowledge_base = course_data.get("course_knowledge_base") or compile_course_knowledge_base(
            course_data
        )
        local_context = course_knowledge_base_prompt_context(course_knowledge_base, node_id)
        return (
            "只允许使用当前课程知识点 ID；禁止读取或映射其他课程知识。",
            "能力、易错与掌握标准均以当前课程知识库为唯一依据。",
            local_context,
        )

    def build_repair_prompt(
        self,
        *,
        course_data: dict[str, Any],
        node: dict[str, Any],
        content: str,
        issues: list[dict[str, Any]],
    ) -> tuple[str, str]:
        issue_text = "\n".join(
            f"- [{item.get('code', 'quality')}] {item.get('message', '')}；修复目标：{item.get('suggestion', '')}"
            for item in issues
        )
        module_text = "\n".join(
            f"- {item.get('output_contract')}；{item.get('prompt_instruction')}"
            for item in node.get("module_plan", [])
        )
        difficulty_text = format_node_difficulty_contract(
            node.get("difficulty_contract") or {}
        )
        grounding_contract = node.get("grounding_contract") or {}
        evidence_ids = list(dict.fromkeys(
            list(grounding_contract.get("required_evidence_ids") or [])
            + list(grounding_contract.get("optional_evidence_ids") or [])
        ))
        evidence_by_id = {
            item.get("evidence_id"): item
            for item in course_data.get("evidence_catalog") or []
            if item.get("evidence_id") in evidence_ids
        }
        evidence_text = "\n".join(
            f"- [{evidence_id}] {item.get('source_text', '')}"
            for evidence_id, item in evidence_by_id.items()
        ) or "- 当前节点无资料证据。"
        course_knowledge_base = course_data.get("course_knowledge_base") or compile_course_knowledge_base(
            course_data
        )
        course_knowledge_text = course_knowledge_base_prompt_context(
            course_knowledge_base,
            str(node.get("node_id") or ""),
        )
        coherence_text = course_coherence_prompt_context(
            course_data,
            str(node.get("node_id") or ""),
        )
        teaching_guidance = format_generation_teaching_guidance(
            course_data,
            node,
        )
        lesson_archetype = node.get("lesson_archetype") or {}
        system_prompt = f"""你负责定向修复课程小节。只输出修复后的完整 Markdown，不输出说明。

## 课程与节点
- 课程：{course_data.get('course_name', '')}
- 节点：{node.get('node_name', '')}
- 学习目标：{node.get('learning_objective', '')}
- 范围边界：{node.get('scope_boundary', '')}

## 教学模块契约
{module_text}

## 总体教案对本节的引领
{teaching_guidance}

## 本节学科课型
{json.dumps(lesson_archetype, ensure_ascii=False)}

## 难度契约
{difficulty_text}

## 证据契约
- 必用证据：{'；'.join(grounding_contract.get('required_evidence_ids', [])) or '无'}
- 可用证据原文：
{evidence_text}

## 当前课程知识库契约
{course_knowledge_text}

## 全课总编契约
{coherence_text}

## 必须修复的问题
{issue_text}

## 原正文
{content}

只修改问题涉及的内容，保留正确部分；不得引入范围外知识或虚构来源。资料事实必须使用允许的 `[[evidence:证据ID]]` 标记。修复后必须再次核对题干、过程、答案与量规，不得保留模型自我纠错痕迹。若问题来自跨章节重复，保留必要的一两句承接并重写本节独有推进，不得删除当前学习目标所需内容。"""
        return "修复这些明确问题并输出完整正文。", system_prompt


_composer: CoursePromptComposer | None = None


def get_course_prompt_composer() -> CoursePromptComposer:
    global _composer
    if _composer is None:
        _composer = CoursePromptComposer()
    return _composer


__all__ = [
    "PROMPT_CONTRACT_VERSION",
    "CoursePromptComposer",
    "get_course_prompt_composer",
]
