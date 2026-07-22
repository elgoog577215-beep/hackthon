"""课程生成唯一 prompt 编排器。"""

from __future__ import annotations

import json
import re
from typing import Any

from course_coherence import course_coherence_prompt_context
from course_composition import format_block_difficulty, format_composition_profile
from course_difficulty import (
    format_difficulty_profile,
    format_node_difficulty_contract,
)
from course_generation_adaptive import (
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

PROMPT_CONTRACT_VERSION = "course_prompt_v23"


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
    ) -> str:
        """Build the small global decision used before parallel chapter expansion."""
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
        return f"""## 全课章节骨架 V2

你只做一次轻量的全局课程决策：确定课程定位、全课成果、章节顺序、每章唯一学习
焦点，以及每章需要展开的小节数量。不要生成任何小节、知识点、教案、正文或题目。
后续系统会按章节并行生成小节目录并在本地汇编。只输出有效 JSON。

## 课程输入
- 主题：{subject}
- 学习对象：{audience}
- 结构化 brief：{json.dumps(brief, ensure_ascii=False)}
- 用户指定章数：{shape.get('chapter_count') or '未指定'}
- 用户指定小节总数：{shape.get('section_count') or '未指定'}
- 完整课程最低章数：{shape.get('minimum_chapter_count') or '按用户明确数量'}
- 完整课程最低小节总数：{shape.get('minimum_section_count') or '按用户明确数量'}

## 难度与适配
- 难度：{json.dumps(difficulty_profile, ensure_ascii=False)}
- 就绪差距：{json.dumps(gap_assessment, ensure_ascii=False)}
- 适配决策：{json.dumps(adaptation_decision, ensure_ascii=False)}

## 教学画像
{json.dumps(profile_data, ensure_ascii=False)}

## 资料摘要
{material_context or '未上传资料；只能使用通用知识，不得伪装引用资料。'}

## 约束
1. 用户指定章数或小节总数时必须精确满足；所有 `section_count` 之和必须等于指定总数。
2. 未指定数量时必须覆盖从必要前置到最终成果的完整知识与能力依赖，并达到上面的完整课程最低规模；可以按主题需要继续增加，课程总量没有固定产品上限。
3. 这是所有课程统一使用的完整规划入口。单次批次大小只是执行预算，不得把整门课程压缩成一个批次或默认六节。
4. 每章只定义一个清晰、互不重复的学习推进范围，不能把小节详情塞进章节焦点。
5. 章节按学习先后排列，后续章节不得重复承担前面已经完成的核心责任。
6. 只返回章节骨架，不返回 `sections`、知识点、关系、正文或题目。

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
      "learning_focus": "本章独有的能力推进范围",
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
        return f"""## 全课章节骨架 V2 定点修复

上一次章节骨架存在以下问题：
{issue_text}

只修复章节骨架并重新输出完整 JSON。不得生成小节、知识点、教案、正文、题目或解释。

{clip_text(original_prompt, 8500)}
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
        return f"""## 章节小节目录批次 V2

全课章节骨架已经冻结。你只展开当前章节的第 {start}-{end} 个小节；不得修改课程
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
3. 当前章内部只能引用编号更早的小节。第一节只有确需承接时才可引用
   `previous_chapter_anchor_id`；不得引用其他章节或未来小节。
4. 当前批次不得重新解释整个章节，不得提前承担下一批次或相邻章节的核心责任。
5. 不输出知识点、知识关系、教案、正文、题目答案或 Markdown 围栏。

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
      "scope_boundary": "本节负责什么，以及明确不提前展开什么"
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
            "这是全课骨架的后续分片。`prior_knowledge_registry` 是已经冻结的只读前序"
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

你只做当前有界分片的全局身份决策：冻结原子知识身份、唯一首次负责小节、合法复用、
前置知识键和允许承担职责的课程块；前序分片已经冻结的身份保持只读。不要展开能力、
易错、掌握标准、正文或题目。
目录已经冻结，不得增删、改名或调序。只输出有效 JSON。

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
        detail_level: str = "full",
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
        return f"""## 详细小节教案批次 V3

全课知识身份已经冻结。你只展开当前批次，不得新增、删除、改名或迁移知识键；不得
修改其他批次。只输出有效 JSON，不输出正文、题目、评分、解释或 Markdown 围栏。

## 课程与批次
- 课程：{course_title}
- 定位：{positioning}
- 批次：{json.dumps(batch_spec, ensure_ascii=False)}
- 骨架修订：{skeleton_revision_id}

## 当前小节（已去重）
{json.dumps(batch_sections, ensure_ascii=False)}

## 当前批次知识与直接依赖闭包（只读）
{json.dumps(knowledge_registry, ensure_ascii=False)}

## 当前批次知识职责（只读）
{json.dumps(section_identities, ensure_ascii=False)}

## 共享课程块目录（只出现一次）
{json.dumps(module_catalog, ensure_ascii=False)}

## 约束
1. `sections` 必须按批次指定顺序返回，`knowledge_details` 必须按本节
   `owned_knowledge_keys` 顺序逐个展开，不能展开复用键。
2. 每个知识详情必须给出成立条件或边界、可观察能力、至少一个可信易错点和可验证
   掌握标准；易错点必须包含具体错误表现、判别方法与修复策略。
3. 关系端点只能使用全局注册表中的键。当前批次不得把未来知识当作已经掌握的复用，
   也不得修改骨架冻结的前置关系。
4. `teaching_modules` 只能使用当前小节允许的模块 ID；知识键只能来自本节负责或复用
   集合。必需块即使省略也会由系统恢复，返回的模块只表达具体局部职责。

## JSON Schema
{{
  "sections": [
    {{
      "node_id": "L2-1-1",
      "knowledge_details": [
        {{
          "knowledge_key": "K001",
          "concept_group": "知识问题域",
          "group_description": "本组作用与边界",
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
            "observable_performance": "独立表现",
            "required_independence": "independent",
            "required_transfer": "variation",
            "verification_method": "验证方法",
            "required_evidence_types": ["practice_attempt"]
          }}],
          "aliases": []
        }}
      ],
      "knowledge_relations": [{{
        "source_key": "K001",
        "target_key": "K002",
        "relation_type": "prerequisite",
        "reason": "具体语义理由"
      }}],
      "teaching_modules": [{{
        "module_id": "core_explanation",
        "teaching_purpose": "本节具体教学职责",
        "knowledge_keys": ["K001"],
        "teaching_guidance": "正文必须体现的讲法或学习者行动"
      }}]
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

## 当前小节
- 课程：{clip_text(course_data.get('course_name'), 96)}
- 节点：{node_name}
- 目标：{objective}
- 知识：{key_points or '按当前知识库契约'}
- 范围：{scope or '只完成当前小节责任'}
- 验收：{assessments or '给出可检查的学习任务'}

## 当前课程知识库（当前节点切片）
{course_knowledge_context}

## 教学模块
{module_contract or '- `## 核心教学`：解释、示例、行动与检查。'}

## 允许证据
{evidence_ids}

## 持久化上下文（已压缩）
{context or '无额外资料或前序摘要。'}
{continuation_contract}
"""
            user_prompt = (
                f"续写「{node_name}」，只输出追加正文。"
                if continuation
                else f"撰写「{node_name}」正文，只输出 Markdown。"
            )
            return user_prompt, system_prompt

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
10. 当前节点名称已经由页面显示，正文不得再次把“{node_name}”写成二级标题，也不得输出只有标题没有正文的空模块。
11. 每个 `##` 教学块必须在首段明确写出它实际讲解、练习或检查的一个或多个知识点规范名称；不得只用“本概念”“上述方法”等代词。规范名称来自下方“当前课程知识库契约”，用于建立正文块到知识点的精确绑定。
12. `## 检查与反馈` 是静态检查参考，不得声称已经评价当前学生。对应多个学习任务时，每个任务必须使用 `### 任务 N：名称` 作为内部边界，并在任务内清楚区分核对标准、参考结论、推导依据和典型错误；不得把所有答案压成一个长段落。
13. Markdown 列表必须使用真实的 `1.` 或 `-` 列表语法并保留必要空行。任务级标题使用 `###`，不要用单独一行加粗文字伪装标题。
14. 数学表达必须使用 `$...$` 或 `$$...$$`，反引号只用于代码标识、命令或程序片段；不得用反引号书写幂、上下标、分式、复杂度或数学关系。

## 课程
- 名称：{course_name}
- 学习对象：{audience}
- 教学画像：{json.dumps(profile, ensure_ascii=False)}

## 课程块编排画像
{format_composition_profile(composition_profile)}

## 全课难度能力契约
{format_difficulty_profile(difficulty_profile)}

## 当前节点契约
- 节点：{node_name}
- 学习目标：{learning_objective}
- 知识点：{'；'.join(key_points)}
- 细知识结构：{json.dumps(knowledge_structure, ensure_ascii=False)}
- 前置节点：{'；'.join(node.get('prerequisite_node_ids', []))}
- 常见误区：{'；'.join(misconceptions)}
- 验收标准：{'；'.join(assessment)}
- 范围边界：{scope_boundary}

## 当前课程知识身份边界
{knowledge_context}

## 当前课程教学边界
{teaching_context}

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

内容必须通过学习任务、支架方式、独立性和验收证据展现难度；不得仅靠术语、篇幅、公式、代码量或题量展现难度。

## 本节教学模块
{module_contract or '- 使用通用本节任务、核心教学、学习者行动和反馈检查。'}

## 持久化上下文
{context or '无额外资料或前置摘要。'}
{continuation_contract}
"""
        user_prompt = (
            f"继续撰写「{node_name}」，只输出追加正文。"
            if continuation
            else f"撰写「{node_name}」完整正文，只输出 Markdown。"
        )
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
        system_prompt = f"""你负责定向修复课程小节。只输出修复后的完整 Markdown，不输出说明。

## 课程与节点
- 课程：{course_data.get('course_name', '')}
- 节点：{node.get('node_name', '')}
- 学习目标：{node.get('learning_objective', '')}
- 范围边界：{node.get('scope_boundary', '')}

## 教学模块契约
{module_text}

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
