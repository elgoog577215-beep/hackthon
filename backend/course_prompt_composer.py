"""课程生成唯一 prompt 编排器。"""

from __future__ import annotations

import json
from typing import Any

from course_coherence import course_coherence_prompt_context
from course_difficulty import (
    format_difficulty_profile,
    format_node_difficulty_contract,
)
from course_knowledge_base import (
    compile_course_knowledge_base,
    course_knowledge_base_prompt_context,
)
from course_pedagogy import MODULES, TEMPLATES, SubjectPedagogyProfile, module_block_role

PROMPT_CONTRACT_VERSION = "course_prompt_v11"


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

## 知识身份边界
知识库只属于当前课程。只从本次课程要求、上传资料和当前蓝图生成知识点，
不得读取、复用或输出其他课程的知识 ID。

## 蓝图要求
1. 用户明确指定章数或小节总数时必须精确满足；未指定时才由知识和能力依赖决定。不要为了凑数重复主题，也不要用节数表示难度。
2. 每个小节必须承担明确的能力推进，后端会根据整体顺序编译锯齿型难度曲线。
3. 每个小节给出可观察学习目标、前置节点、范围边界、误区和验收标准。
4. `suggested_module_ids` 只能从可用模块中选择；后端会补齐必备模块并校验辅模式注入。
5. 每个小节必须给出 `node_id`，统一使用 `L2-章号-节号`，例如第 1 章第 1 节是 `L2-1-1`。
6. 前置依赖只能引用已经出现的 `node_id`，不得使用 `1.1`、`L1-1` 或尚未出现的节点。
7. `knowledge_structure` 就是当前课程自己的知识蓝图，不是章节标题索引，也不依赖外部学科库。每节按实际内容组织 1-4 个 `concept_group`，概念组名称必须表达知识问题域，禁止复制小节标题。
8. 每个概念组包含 2-5 个可单独解释、练习和诊断的原子知识点。每个知识点必须写出独立 `statement`、`knowledge_type`、成立 `conditions` 或适用 `boundaries`；不得把定义、公式、图像和应用打包成一个粗节点。
9. 每个原子知识点至少包含一个可观察 `capability_points` 和一个可验证 `mastery_criteria`。`misconceptions` 只有存在具体错误表现、判别方法和修复策略时才生成，允许为空，禁止模板填充。
10. `ImprovementPoint` 已退出知识库。稳定提升目标写成能力，具体训练进入练习，个性化建议留给学习阶段 AI，不得在蓝图中生成 `improvement_points`。
11. 同一知识在本课程内只能有一个名称身份；后续小节再次使用时不得在 `knowledge_structure` 重建，必须把前序规范名称写入该小节的 `reused_knowledge_names`，由绑定表示巩固或应用。不得从其他课程借用知识身份。
12. 不编造论文、链接、书目、年份或未上传资料。
13. 从整门课程角度分配小节责任：相邻小节的学习目标不得只是换句话重复；需要承接的前置必须写入 `prerequisite_node_ids`，只需上下文衔接但可并行生成的内容不要伪造成硬依赖。
14. 每节只完整展开自己的知识与能力产出。允许简短回顾前置，但不得复制前节实质讲解；后续小节的核心知识只能提示方向，不能在当前小节提前讲完。
15. 全课程使用统一术语和符号。相同概念优先复用规范名称，把其他叫法写入知识点 `aliases`，不得在不同章节把同一概念写成互不关联的新知识点。
16. 只允许六类知识关系：`prerequisite / derives / equivalent_to / contrasts_with / applies_to / generalizes`。禁止 `related`。每条关系必须给出具体理由；推导给步骤，对比给判别维度；没有入边的真正入口知识必须写 `entry_reason`。

## JSON Schema
{{
  "course_title": "课程名",
  "positioning": "课程定位与最终成果",
  "learning_objectives": ["可观察成果"],
  "prerequisites": ["必要前置"],
  "knowledge_relations": [
    {{
      "source_name": "来源知识点规范名称",
      "target_name": "目标知识点规范名称",
      "relation_type": "prerequisite",
      "reason": "为什么属于该关系，而不是课程先后顺序",
      "conditions": [],
      "distinction": "仅 contrasts_with 必填",
      "derivation_steps": ["仅 derives 必填"],
      "necessity": "required",
      "priority": "core"
    }}
  ],
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
              "concept_group": "知识问题域，不得复制小节标题",
              "description": "本主题在本节中的作用与边界",
              "knowledge_points": [
                {{
                  "name": "可单独解释和检测的细知识点",
                  "statement": "脱离章节标题也能独立成立的知识命题或操作规则",
                  "knowledge_type": "definition",
                  "conditions": ["成立条件；普遍成立时写明适用域"],
                  "boundaries": ["不适用范围或易混边界"],
                  "counterexamples": [],
                  "capability_points": [
                    {{
                      "name": "细颗粒能力名称",
                      "observable_behavior": "学习者在不依赖答案时可观察到的动作",
                      "required_evidence_types": ["practice_attempt"]
                    }}
                  ],
                  "misconceptions": [
                    {{
                      "name": "常见错误模式",
                      "observable_error_pattern": "学生会以什么具体方式出错",
                      "confused_with": "容易与什么混淆",
                      "discrimination": "靠什么条件或反例区分",
                      "repair_strategy": "如何辨别并修复"
                    }}
                  ],
                  "mastery_criteria": [
                    {{
                      "name": "掌握标准名称",
                      "observable_performance": "出现什么独立表现才算掌握",
                      "required_independence": "independent",
                      "required_transfer": "variation",
                      "verification_method": "用何种题目、产物或行为验证",
                      "required_evidence_types": ["practice_attempt"]
                    }}
                  ],
                  "aliases": [],
                  "entry_reason": "只有真正入口知识才填写",
                  "prerequisite_names": [],
                  "relations": []
                }}
              ]
            }}
          ],
          "reused_knowledge_names": ["仅填写前序小节已经定义、当前小节再次巩固或应用的规范知识名称"],
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

    def build_outline_correction_prompt(
        self,
        *,
        original_prompt: str,
        brief: dict[str, Any],
        issues: list[dict[str, Any]],
    ) -> str:
        issue_text = "\n".join(
            f"- {item.get('message')}" for item in issues
        ) or "- 上一次输出不是完整有效的 JSON"
        shape = brief.get("course_shape_constraints") or {}
        return f"""
## 蓝图纠正任务

上一次课程蓝图未通过确定性验收：
{issue_text}

用户明确课程形状：
- 章数：{shape.get('chapter_count') or '由教学设计决定'}
- 小节总数：{shape.get('section_count') or '由教学设计决定'}

请从头重新输出一份完整 JSON。不得输出截断 JSON、Markdown 围栏、简化占位大纲或解释。
所有原始要求、学科模式、知识结构和难度契约仍以下面的完整原始契约为准。

{original_prompt}
""".strip()

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
            (
                f"- {'必需' if item.get('required', True) else '可选'}模块 "
                f"`## {item.get('label')}` [角色={item.get('block_role') or module_block_role(item.get('module_id'))}]："
                f"{item.get('output_contract')}；{item.get('prompt_instruction')}"
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
        continuation_contract = ""
        if continuation:
            continuation_contract = f"""
## 已保存草稿
{existing_draft}

只输出从草稿最后一个完整句子之后开始的续写内容。不要重复标题和已有段落，不要解释你在续写。"""

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
10. 当前节点名称已经由页面显示，正文不得再次把“{node.get('node_name', '')}”写成二级标题，也不得输出只有标题没有正文的空模块。
11. 每个 `##` 教学块必须在首段明确写出它实际讲解、练习或检查的一个或多个知识点规范名称；不得只用“本概念”“上述方法”等代词。规范名称来自下方“当前课程知识库契约”，用于建立正文块到知识点的精确绑定。
12. `## 检查与反馈` 是静态检查参考，不得声称已经评价当前学生。对应多个学习任务时，每个任务必须使用 `### 任务 N：名称` 作为内部边界，并在任务内清楚区分核对标准、参考结论、推导依据和典型错误；不得把所有答案压成一个长段落。
13. Markdown 列表必须使用真实的 `1.` 或 `-` 列表语法并保留必要空行。任务级标题使用 `###`，不要用单独一行加粗文字伪装标题。
14. 数学表达必须使用 `$...$` 或 `$$...$$`，反引号只用于代码标识、命令或程序片段；不得用反引号书写幂、上下标、分式、复杂度或数学关系。

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
            f"继续撰写「{node.get('node_name', '')}」，只输出追加正文。"
            if continuation
            else f"撰写「{node.get('node_name', '')}」完整正文，只输出 Markdown。"
        )
        return user_prompt, system_prompt

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
