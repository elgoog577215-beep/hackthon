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
from course_knowledge_base import (
    compile_course_knowledge_base,
    course_knowledge_base_prompt_context,
)
from course_pedagogy import TEMPLATES, SubjectPedagogyProfile, module_block_role

PROMPT_CONTRACT_VERSION = "course_prompt_v20"


class CoursePromptComposer:
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
        max_sections: int = 24,
    ) -> str:
        profile_data = profile.to_dict()
        primary = TEMPLATES[profile.primary_mode]
        guardrails = "\n".join(f"- {item}" for item in primary.quality_guardrails)
        return f"""## 输出契约
你只负责生成供用户审阅的轻量课程目录，不生成知识点、知识关系、正文或练习。
只输出有效 JSON，不输出寒暄、计划或 Markdown 代码围栏。

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

## 主模式质量边界
{guardrails}

## 资料上下文
{material_context or '未上传资料；只能使用通用知识，不得伪装引用资料。'}

## 目录要求
1. 用户明确指定章数或小节总数时必须精确满足；未指定时才由知识和能力依赖决定。单门课程不得超过 {max_sections} 个小节，超过时应收敛范围而不是输出超大目录。不要为了凑数重复主题，也不要用节数表示难度。
2. 每个小节只承担一个明确、可观察、与其他小节不同的学习责任。
3. 每个小节给出可观察学习目标、前置小节、范围边界和验收任务。
4. 每个小节必须给出 `node_id`，统一使用 `L2-章号-节号`，例如第 1 章第 1 节是 `L2-1-1`。
5. 前置依赖只能引用已经出现的 `node_id`，不得引用尚未出现的小节。
6. 只需上下文衔接但可以独立生成的内容不要伪造成硬依赖。
7. 不输出 `knowledge_structure`、`knowledge_relations`、`reused_knowledge_names`、正文、题目或内部知识 ID。
8. 不编造论文、链接、书目、年份或未上传资料。

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
          "learning_objective": "学完后能完成的任务",
          "prerequisite_node_ids": [],
          "assessment": ["验收标准或任务"],
          "scope_boundary": "本节负责什么，以及明确不提前展开什么"
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
## 轻量目录纠正任务

上一次轻量课程目录未通过确定性验收：
{issue_text}

用户明确课程形状：
- 章数：{shape.get('chapter_count') or '由教学设计决定'}
- 小节总数：{shape.get('section_count') or '由教学设计决定'}

请重新输出一份完整的轻量目录 JSON。不得输出知识点、知识关系、正文、Markdown
围栏、占位目录或解释。所有原始要求、学科模式和难度契约仍以下面的原始契约为准。

{original_prompt}
""".strip()

    def build_course_teaching_plan_prompt(
        self,
        *,
        course_title: str,
        positioning: str,
        learning_objectives: list[str],
        sections: list[dict[str, Any]],
    ) -> str:
        return f"""## 输出契约
你一次性规划整门课所有小节的教案。目录已经冻结，不得修改章节、小节、顺序、
目标或范围。教案确定本节知识、能力、掌握标准和需要额外强调的课程块职责；系统会
把它编译到模板拥有的课程块骨架上、本地封装为唯一 `CourseTeachingPlanV3`，并从
同一结果编译课程知识库，不存在第二次知识库或知识图谱生成。只输出有效 JSON，
不输出解释或 Markdown 围栏。

## 课程
- 名称：{course_title}
- 定位：{positioning}
- 全课成果：{json.dumps(learning_objectives, ensure_ascii=False)}
- 按教学顺序排列的小节与模板：{json.dumps(sections, ensure_ascii=False)}

## 教案原则
1. 必须按输入顺序完整返回每个 `node_id`，不得增删、改名或调序。
2. 全课只维护一套知识身份。每个知识规范名称只在首次完整教学的小节定义一次；
   后续使用只写入 `reused_knowledge_names`。
3. 每节通常首次负责 2-5 个可单独解释、练习和诊断的原子知识点；不得把小节标题
   直接当知识点，也不得为凑数量拆分同义节点。
4. 每个知识点必须包含独立陈述、条件或边界、可观察能力、可验证掌握标准，以及
   它为何是课程入口或依赖哪些此前已经定义的知识。
5. `prerequisite_names` 只能引用本节更早出现或前序小节已定义的规范名称。确有
   对比、推导、应用或一般化关系时可写入 `relations`；不得为了画图制造关系。
6. 易错点只有能给出具体错误表现、辨别方法和修复策略时才生成。
7. 模板拥有硬骨架：`required=true` 的块由系统自动保留，不需要为了确认而重复
   返回；`required=false` 的块只在确有教学价值时选择。不得返回输入列表之外的块。
8. `teaching_modules` 只表达需要额外强调的局部职责。返回某个块时，应说明具体
   职责、负责的知识规范名称和写作指导；未显式绑定的新知识由系统绑定到核心教学
   块。教案只拥有局部选择和强调自由，不能删除或改写模板硬约束。
9. 遵守 `learning_objective`、`scope_boundary`、难度和编排风格，不提前完成后续
   小节的核心教学，不输出正文、题目或内部稳定 ID。
10. 带有 `evidence_hints` 时，只吸收与本节目标直接相关的资料概念，不得虚构来源。

## JSON Schema
{{
  "sections": [
    {{
      "node_id": "L2-1-1",
      "knowledge_structure": [
        {{
          "concept_group": "知识问题域",
          "description": "该问题域在本节中的作用与边界",
          "knowledge_points": [
            {{
              "name": "原子知识规范名称",
              "statement": "独立成立的知识命题或操作规则",
              "knowledge_type": "definition",
              "conditions": ["成立条件"],
              "boundaries": ["不适用范围或易混边界"],
              "counterexamples": [],
              "entry_reason": "没有前置知识时说明为何从这里开始，否则留空",
              "prerequisite_names": [],
              "relations": [
                {{
                  "target_name": "已经定义的相关知识名称",
                  "relation_type": "contrasts_with",
                  "reason": "具体关系理由",
                  "distinction": "对比关系必须提供判别维度"
                }}
              ],
              "capability_points": [
                {{
                  "name": "能力名称",
                  "observable_behavior": "不依赖答案时可以观察到的动作",
                  "required_evidence_types": ["practice_attempt"]
                }}
              ],
              "misconceptions": [
                {{
                  "name": "错误模式",
                  "observable_error_pattern": "具体怎样出错",
                  "confused_with": "容易与什么混淆",
                  "discrimination": "用什么条件或反例区分",
                  "repair_strategy": "如何修复"
                }}
              ],
              "mastery_criteria": [
                {{
                  "name": "掌握标准",
                  "observable_performance": "独立表现",
                  "required_independence": "independent",
                  "required_transfer": "variation",
                  "verification_method": "验证方法",
                  "required_evidence_types": ["practice_attempt"]
                }}
              ],
              "aliases": []
            }}
          ]
        }}
      ],
      "reused_knowledge_names": [],
      "knowledge_relations": [],
      "teaching_modules": [
        {{
          "module_id": "输入模板中允许的模块 ID",
          "teaching_purpose": "该课程块在本节承担的具体教学职责",
          "knowledge_names": ["该块负责的知识规范名称"],
          "teaching_guidance": "正文生成时必须体现的讲法、例子或学习者行动"
        }}
      ]
    }}
  ]
}}""".strip()

    def build_course_teaching_plan_correction_prompt(
        self,
        *,
        original_prompt: str,
        issues: list[dict[str, Any]],
    ) -> str:
        issue_text = "\n".join(
            f"- {item.get('message')}" for item in issues
        ) or "- 上一次输出不是完整有效的 JSON"
        return f"""## 全课小节教案结构纠正

上一次整课教案存在以下结构或引用错误：
{issue_text}

只修复这些错误并重新输出完整 JSON。不得改变目录、模板、难度或课程风格，不得
输出正文、评分、解释或 Markdown 围栏。

{original_prompt}
""".strip()

    def build_teaching_plan_skeleton_v3_prompt(
        self,
        *,
        course_title: str,
        positioning: str,
        learning_objectives: list[str],
        planning_context: dict[str, Any],
    ) -> str:
        skeleton_context = self._compact_skeleton_planning_context(
            planning_context
        )
        return f"""## 全课知识职责骨架 V3

你只做一次轻量的全局决策：冻结全课原子知识身份、唯一首次负责小节、合法复用、
前置知识键和允许承担职责的课程块。不要展开能力、易错、掌握标准、正文或题目。
目录已经冻结，不得增删、改名或调序。只输出有效 JSON。

## 课程
- 名称：{course_title}
- 定位：{positioning}
- 全课成果：{json.dumps(learning_objectives, ensure_ascii=False)}

## 已去重的规划上下文
{json.dumps(skeleton_context, ensure_ascii=False)}

## 约束
1. `sections` 必须按输入顺序完整返回全部 `node_id`。
2. 每个知识点使用稳定、简短且全课唯一的 `knowledge_key`，如 `K001`；规范名称与
   一句话陈述全课唯一，后续批次不得改名或改写。
3. 每节通常首次负责 2-5 个可单独解释、练习和诊断的原子知识点；知识名不得复制
   小节标题，也不得写成教学动作。
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
            f"- {item.get('message')}" for item in issues
        ) or "- 上一次输出不是完整有效的骨架 JSON"
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
    ) -> str:
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
            f"- {item.get('message')}" for item in issues
        ) or "- 上一次输出不是完整有效的批次 JSON"
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
    ) -> tuple[str, str]:
        profile = course_data.get("subject_pedagogy_profile") or {}
        difficulty_profile = course_data.get("difficulty_profile") or {}
        difficulty_contract = node.get("difficulty_contract") or {}
        modules = node.get("module_plan") or []
        module_contract = "\n".join(
            (
                f"- {'必需' if item.get('required', True) else '可选'}模块 "
                f"`## {item.get('label')}` "
                f"[角色={item.get('block_role') or module_block_role(item.get('module_id'))}] "
                f"[来源={item.get('composition_source') or 'subject_required'}；"
                f"实例={item.get('module_instance_id') or item.get('module_id')}；"
                f"难度={format_block_difficulty(item.get('block_difficulty_contract') or {})}]："
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
            compact_draft = self._compact_continuation_draft(existing_draft)
            continuation_contract = f"""
## 已保存草稿的有界恢复上下文
{compact_draft}

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

## 课程块编排画像
{format_composition_profile(course_data.get('course_composition_profile') or {})}

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

    @staticmethod
    def _compact_continuation_draft(
        content: str,
        *,
        max_chars: int = 6000,
    ) -> str:
        if len(content) <= max_chars:
            return content
        headings = re.findall(r"(?m)^#{1,3}\s+(.+)$", content)
        heading_text = "；".join(headings[-12:]) or "未识别到模块标题"
        tail_budget = max(1200, max_chars - len(heading_text) - 120)
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
