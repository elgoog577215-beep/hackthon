from __future__ import annotations
from copy import deepcopy
import json
from typing import Any

async def analyze_teacher_course_change(
    self,
    overview: dict[str, Any],
    ranked_candidates: list[dict[str, Any]],
    instruction: str,
) -> dict[str, Any] | None:
    """Judge one bounded batch of a complete whole-course impact scan.

    The index is only a speed layer. The model receives cross-asset
    candidates and decides which units are genuinely affected; returned
    IDs must come from the supplied candidate set and are validated again
    by the orchestration service.
    """
    scan_candidates = []
    for item in ranked_candidates:
        item = deepcopy(item)
        if isinstance(item.get('content'), str):
            # Full editable text is already represented by content fragments.
            # Keep field names for exact patches without sending it twice.
            item['editable_field_names'] = list((item.pop('editable_fields', None) or {}).keys())
            item.pop('summary', None)
            item.pop('rank_score', None)
        scan_candidates.append(item)
    prompt = (
        "请分析老师对整门课程的修改要求，只输出一个 JSON 对象。\n"
        f"老师原话：{instruction}\n\n"
        "课程与资产概况：\n"
        f"{json.dumps(overview, ensure_ascii=False)}\n\n"
        "经过索引与关系扩展后的候选单元：\n"
        f"{json.dumps(scan_candidates, ensure_ascii=False)}\n\n"
        "返回字段：interpreted_goal、signal_kind、signal_confidence、"
        "hard_constraints、soft_preferences、protected_requirements、assumptions、"
        "blocking_questions、clarifications、affected_units、structure。"
        "signal_kind 只能是 semantic、structural、mixed、uncertain。"
        "affected_units 每项只能包含候选中真实存在的 unit_id，以及 disposition、"
        "reason、confidence、content_patches；disposition 只能是 reuse_exact、reuse_rebind、"
        "rewrite_partial、regenerate、retire、blocked。"
        "如果 course_content 候选的 editable_fields 已足够支撑精确修改，"
        "content_patches 返回逐条 {field,before,after,replace_all}；field 只能是"
        "markdown、text、content、title、summary，before 必须逐字存在于该候选"
        "editable_fields 中。术语全局替换要为每个真实命中的单元分别返回 patch；"
        "不能可靠形成逐字候选时 content_patches=[]，不得猜测原文。"
        "分片模式下 content 是当前原文，editable_field_names 是可编辑字段名；"
        "before 必须逐字来自 content，使用最短可唯一定位的片段，不复述整段原文。"
        "本步骤只判断修改影响，不要在每批输出完整的实践项目、参考答案或大段代码。"
        "content 可能从代码或段落中间切开，这是正常分片，不需要独立编译；不要补全或执行分片代码。"
        "补充实践、例题或解释通常是在现有讲次内修改，不等于拆分或新增讲次；"
        "只有老师明确要求改变讲次层级、数量或顺序时才提出结构重建。"
        "structure 包含 required、reason、affected_node_ids、retire_node_ids、proposed_outline。"
        "若结构不变，required=false 且 proposed_outline=[]；若章节要合并、删除、"
        "拆分、移动或重建，先给可审阅的完整新课程树（不是只返回变化节点），"
        "proposed_outline 每项包含 provisional_id、title、parent_ref、"
        "source_node_ids、learning_focus。删除的旧节点 ID 必须逐个放入 retire_node_ids；"
        "合并时新节点引用全部来源 ID，拆分时多个新节点可引用同一来源 ID。"
        "不要因为老师措辞不专业就机械缩小范围；要从目标推断可能受影响的资产，"
        "但不要把仅仅同词出现的单元判为必改。无法安全推断且会改变结构时，"
        "把问题放入 clarifications。blocking_questions 只允许是纯字符串数组，"
        "不得在其中放对象；正式内容不会在本步骤被修改。"
        "需要老师决定时，clarifications 返回 1—3 个真正影响方案的问题；每项包含"
        "question_id、prompt、response_type=single_choice、required=true 和 2—4 个 options。"
        "每个 option 包含 option_id、label、impact、recommended，最多一个 recommended。"
        "如果课程概况中已有 clarification_answer_snapshot，其中 decision_facts 是老师"
        "已经逐题确认的硬约束，不得重新解释、覆盖或再次询问同一问题。"
    )
    response = await self._call_llm(
        prompt,
        system_prompt=(
            "你是高校课程总编与变更影响分析师。你在课程大纲、教案、讲义、"
            "PPT、题库之间追踪因果与依赖。索引负责召回，你负责最终语义判断；"
            "保持老师原话、解释判断原因，并把结构调整与内容调整分开。"
        ),
        use_fast_model=True,
        retry_count=1,
        enable_thinking=False,
        max_tokens=4200,
        max_input_tokens=11000,
        max_attempts=1,
        reject_truncated=True,
        raise_on_failure=True,
        json_mode=True,
        model_role="teacher_course_change_impact",
        wait_for_capacity=True,
    )
    parsed = self._extract_json(response or "")
    return parsed if isinstance(parsed, dict) else None
