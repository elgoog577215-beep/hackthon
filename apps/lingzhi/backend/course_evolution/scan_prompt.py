"""Single prompt contract shared by scan packing and the model call."""
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

SCAN_INPUT_TOKEN_LIMIT = 11000
SCAN_SYSTEM_PROMPT = '你是高校课程总编与变更影响分析师。你在课程大纲、教案、讲义、PPT、题库之间追踪因果与依赖。索引负责召回，你负责最终语义判断；保持老师原话、解释判断原因，并把结构调整与内容调整分开。'

def build_scan_prompt(overview: dict[str, Any], ranked_candidates: list[dict[str, Any]], instruction: str) -> str:
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
        "content_field 指明 content 的真实字段，补丁 field 必须与它一致；title 是章节上下文，"
        "block_title 才是正文块标题，两者都不能冒充正文定位片段。"
        "existing_sections 是完整正文已有的小节；若已有实践项目或验收标准，应在原有小节内补充，"
        "不要在不同分片中重复添加同一个项目或同义的验收标准。当前分片不含所需位置就不生成补丁。"
        "本步骤只判断修改影响，不要在每批输出完整的实践项目、参考答案或大段代码。"
        "候选只是当前批次，不是整门课程。本批没有目标内容时 affected_units=[]；"
        "不得据此追问目标在哪里、要求提供原文、取消修改，或断言整门课程不存在目标。"
        "intent_assessment 是集中确认的修改目标，本批只定位真实影响，不重新询问全课意图。"
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
    if overview.get('patch_repair'):
        prompt = (
            '请修复当前这一条课程正文的修改建议，只返回 JSON 对象 affected_units 数组。'
            '不要重新分析全课或提出结构调整。老师要求：' + instruction + '\n'
            '完整原文（content_field 是唯一允许修改的字段，其他标题只是上下文）：\n'
            + json.dumps(scan_candidates, ensure_ascii=False) + '\n'
            '之前来自不同分片的建议与校验问题：\n'
            + json.dumps(overview['patch_repair'], ensure_ascii=False) + '\n'
            '每项只含 unit_id、content_patches；每条补丁含 field、before、after、replace_all=false。'
            'before 必须逐字匹配完整原文，使用完整段落或小节且各补丁不得重叠。'
            '将不同分片对同一实践项目的建议合并成一份连贯修改；已有任务或验收标准时直接完善原小节，'
            '不得再追加一份同义小节。逐条合并同义条件，保留不重复的约束、数值、案例和要求。'
            '保留与本次要求无关的原文。不要把摘要或章节名称当成正文，不要将解释或项目要求插入代码块内部，'
            '也不要补写截断代码或删除原有代码。不能可靠修复时返回空 content_patches。'
        )
    return prompt
