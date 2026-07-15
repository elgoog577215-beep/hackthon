"""课程生成唯一 prompt 编排器。"""

from __future__ import annotations

import json
from typing import Any

from course_difficulty import (
    format_difficulty_profile,
    format_node_difficulty_contract,
)
from course_knowledge_map import knowledge_ids_for_section, project_course_knowledge_map
from course_pedagogy import MODULES, TEMPLATES, SubjectPedagogyProfile
from subject_knowledge import (
    knowledge_index,
    knowledge_library_prompt_context,
    knowledge_library_slice,
    knowledge_library_slice_prompt_context,
    resolve_subject_library,
)


PROMPT_CONTRACT_VERSION = "course_prompt_v4"


class CoursePromptComposer:
    def build_profile_classifier_prompt(
        self,
        *,
        subject: str,
        requirements: str,
        deterministic_profile: SubjectPedagogyProfile,
        material_summary: str,
    ) -> str:
        modes = "\n".join(
            f"- {mode.value}: {template.label}；最终验收：{template.final_assessment}"
            for mode, template in TEMPLATES.items()
        )
        return f"""## 任务
判断课程最适合采用哪种教学结构。判断的是怎样教和怎样验收，不是院系分类。

## 课程输入
- 主题：{subject}
- 用户要求：{requirements or '无'}
- 资料摘要：{material_summary or '无资料'}

## 可选模式
{modes}

## 确定性初判
{json.dumps(deterministic_profile.to_dict(), ensure_ascii=False)}

## 输出约束
只输出 JSON：
{{
  "primary_mode": "八种模式之一",
  "secondary_mode": "八种模式之一或null",
  "secondary_intensity": "light/collaborative/dual_core或null",
  "evidence": ["来自目标、行为、资料或主题的证据"],
  "rationale": "一句话说明主模式为什么决定课程主线"
}}

主模式由最终学习成果和主要学习行为决定。辅模式必须是完成主任务不可缺少的能力，不能因为主题相关就加入。"""

    def build_outline_prompt(
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
    ) -> str:
        profile_data = profile.to_dict()
        enabled_modules = [
            MODULES[module_id].to_dict(
                source_mode="allowed",
                required=MODULES[module_id].frequency.value.endswith("required"),
            )
            for module_id in profile.enabled_module_ids
            if module_id in MODULES
        ]
        primary = TEMPLATES[profile.primary_mode]
        guardrails = "\n".join(f"- {item}" for item in primary.quality_guardrails)
        subject_knowledge_context = knowledge_library_prompt_context(subject)
        return f"""## 输出契约
你负责生成课程蓝图，不生成正文。只输出有效 JSON，不输出寒暄、计划或 Markdown 代码围栏。

## 课程输入
- 主题：{subject}
- 学习对象：{audience}
- 结构化 brief：{json.dumps(brief, ensure_ascii=False)}

## 难度能力契约
{format_difficulty_profile(difficulty_profile)}

## 就绪度差距与适配
- 差距评估：{json.dumps(gap_assessment, ensure_ascii=False)}
- 适配决策：{json.dumps(adaptation_decision, ensure_ascii=False)}

必须保持用户选择的目标难度。如果决策要求诊断、桥接或前置单元，将它体现在课程顺序和学习任务中，不得静默降级。

## 教学画像
{json.dumps(profile_data, ensure_ascii=False)}

主模式决定课程顺序和最终考核。辅模式只在主任务依赖它的位置注入。不要把两套目录简单拼接。

## 可用教学模块
{json.dumps(enabled_modules, ensure_ascii=False)}

## 主模式质量边界
{guardrails}

## 资料上下文
{material_context or '未上传资料；只能使用通用知识，不得伪装引用资料。'}

## 学科知识参照
{subject_knowledge_context}

## 蓝图要求
1. 章节数量由知识和能力依赖决定；不要为了凑数重复主题，也不要用节数表示难度。
2. 每个小节必须承担明确的能力推进，后端会根据整体顺序编译锯齿型难度曲线。
3. 每个小节给出可观察学习目标、前置节点、范围边界、误区和验收标准。
4. `suggested_module_ids` 只能从可用模块中选择；后端会补齐必备模块并校验辅模式注入。
5. 每个小节必须给出 `node_id`，统一使用 `L2-章号-节号`，例如第 1 章第 1 节是 `L2-1-1`。
6. 前置依赖只能引用已经出现的 `node_id`，不得使用 `1.1`、`L1-1` 或尚未出现的节点。
7. `knowledge_structure` 表达本课程对学科知识的覆盖，不是另一套正式知识库。优先使用学科参照中的规范名称或正式别名，并按实际教学需要组织 1-4 个局部主题；不得为了凑数重复知识。
8. 每个局部主题包含 1-5 个可单独解释、练习和诊断的细知识要求；说明对象、成立条件或适用边界，并给出可观察学习动作。
9. 不得输出或编造正式知识 ID。参照中没有的课程必要内容可以保留真实名称，后端会将其标记为待归一，不要强行套入相近概念。
10. 不编造论文、链接、书目、年份或未上传资料。

## JSON Schema
{{
  "course_title": "课程名",
  "positioning": "课程定位与最终成果",
  "learning_objectives": ["可观察成果"],
  "prerequisites": ["必要前置"],
  "chapters": [
    {{
      "chapter_number": 1,
      "title": "章节名",
      "learning_focus": "本章能力推进",
      "sections": [
        {{
          "node_id": "L2-1-1",
          "section_number": "1.1",
          "title": "小节名",
          "key_points": ["核心知识点"],
          "knowledge_structure": [
            {{
              "topic": "可教学主题",
              "description": "本主题在本节中的作用与边界",
              "knowledge_points": [
                {{
                  "name": "可单独解释和检测的细知识点",
                  "description": "对象、条件、机制或适用边界",
                  "capability": "学习者能够完成的可观察动作",
                  "aliases": [],
                  "prerequisite_names": []
                }}
              ]
            }}
          ],
          "learning_objective": "学完后能完成的任务",
          "prerequisite_node_ids": [],
          "misconceptions": ["需要澄清的误区"],
          "assessment": ["验收标准或任务"],
          "scope_boundary": "本节边界",
          "suggested_module_ids": ["module_id"]
        }}
      ]
    }}
  ]
}}"""

    def build_content_prompt(
        self,
        *,
        course_data: dict[str, Any],
        node: dict[str, Any],
        context: str,
        existing_draft: str = "",
    ) -> tuple[str, str]:
        profile = course_data.get("subject_pedagogy_profile") or {}
        difficulty_profile = course_data.get("difficulty_profile") or {}
        difficulty_contract = node.get("difficulty_contract") or {}
        modules = node.get("module_plan") or []
        module_contract = "\n".join(
            f"- {item.get('output_contract')}；{item.get('prompt_instruction')}"
            for item in modules
        )
        continuation = bool(existing_draft.strip())
        grounding_contract = node.get("grounding_contract") or {}
        allowed_evidence = list(dict.fromkeys(
            list(grounding_contract.get("required_evidence_ids") or [])
            + list(grounding_contract.get("optional_evidence_ids") or [])
        ))
        knowledge_context, teaching_context = self._node_knowledge_context(course_data, node)
        continuation_contract = ""
        if continuation:
            continuation_contract = f"""
## 已保存草稿
{existing_draft}

只输出从草稿最后一个完整句子之后开始的续写内容。不要重复标题和已有段落，不要解释你在续写。"""

        system_prompt = f"""## 输出契约
1. 只输出可直接保存的 Markdown 正文或续写，不输出寒暄、身份、计划、边界确认或任务复述。
2. 只讲当前小节，不重写整章，不提前展开后续节点。
3. 教学模块是语义要求，不要机械地把模块名称全部写成标题。
4. 不编造论文、来源、链接、年份、机构或未上传资料。
5. 基础课程正文只服从持久化课程蓝图，不根据临时学习状态改变主线。
6. 如果使用资料事实，必须在对应陈述后追加 `[[evidence:证据ID]]`；证据 ID 只能来自当前节点允许列表。
7. 证据标记不是参考文献装饰，不能把讲法参考或弱背景伪装成事实来源。

## 课程
- 名称：{course_data.get('course_name', '')}
- 学习对象：{course_data.get('target_audience', '大学生')}
- 教学画像：{json.dumps(profile, ensure_ascii=False)}

## 全课难度能力契约
{format_difficulty_profile(difficulty_profile)}

## 当前节点契约
- 节点：{node.get('node_name', '')}
- 学习目标：{node.get('learning_objective', '')}
- 知识点：{'；'.join(node.get('key_points', []))}
- 细知识结构：{json.dumps(node.get('knowledge_structure', []), ensure_ascii=False)}
- 前置节点：{'；'.join(node.get('prerequisite_node_ids', []))}
- 常见误区：{'；'.join(node.get('misconceptions', []))}
- 验收标准：{'；'.join(node.get('assessment', []))}
- 范围边界：{node.get('scope_boundary', '')}

## 正式学科知识切片
{knowledge_context}

## 当前知识下的能力、易错与提升
{teaching_context}

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
            f"继续撰写「{node.get('node_name', '')}」，只输出追加正文。"
            if continuation
            else f"撰写「{node.get('node_name', '')}」完整正文，只输出 Markdown。"
        )
        return user_prompt, system_prompt

    def _node_knowledge_context(
        self,
        course_data: dict[str, Any],
        node: dict[str, Any],
    ) -> tuple[str, str]:
        library = resolve_subject_library(course_data)
        if not library.get("nodes"):
            return (
                "当前课程尚无正式学科包；保留课程局部知识表述，不得编造正式 ID。",
                "当前节点尚无正式能力、易错或提升条目；依据正文、任务和证据独立组织教学。",
            )
        course_map = project_course_knowledge_map(course_data)
        node_id = str(node.get("node_id") or "")
        selected_ids = knowledge_ids_for_section(course_map, node_id)
        by_id = knowledge_index(library)
        rows = [
            " / ".join(by_id[item].get("path_names") or [])
            for item in selected_ids
            if item in by_id
        ]
        knowledge_context = "\n".join(
            ["以下是当前节点已确定映射的正式知识路径：", *[f"- {row}" for row in rows]]
        ) if rows else "当前节点尚无精确正式映射；保留课程局部表述，不得强行映射。"
        teaching_context = knowledge_library_slice_prompt_context(
            knowledge_library_slice(library, selected_ids),
        )
        return knowledge_context, teaching_context

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

## 必须修复的问题
{issue_text}

## 原正文
{content}

只修改问题涉及的内容，保留正确部分；不得引入范围外知识或虚构来源。资料事实必须使用允许的 `[[evidence:证据ID]]` 标记。"""
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
