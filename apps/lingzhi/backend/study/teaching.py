"""Source-bound teaching arrangements. They never write learner evidence."""

from copy import deepcopy
import json

_SEQUENCES = {
    "exam_prep": [
        ("conditions", "explanation", "梳理适用条件、题型选法与关键边界"),
        ("worked_example", "explanation", "展示一个完整典型例题并解释步骤选择"),
        ("contrast", "question", "对比只改变关键条件的例子，要求先判断再解释"),
        ("independent_check", "exercise", "给出未在例题中解答的新题，答案另块放在自测之后"),
        ("reflection", "question", "回看错误原因和仍待验证的问题，不编造考试频率或分值"),
    ],
    "project": [
        ("task", "question", "以来源能够支持的小型应用任务开场，明确输入、约束和成功条件"),
        ("necessary_knowledge", "explanation", "解释完成任务必须使用的概念及适用条件"),
        ("design", "question", "要求先说明方案、选择理由与边界，再给最小必要示例"),
        ("deliverable", "case", "安排可检查的产出，明确操作步骤、检查点和可观察结果"),
        ("verification", "exercise", "用正常与边界输入验证产出，不伪造已经运行或已经完成"),
        ("reflection", "question", "解释失败原因、适用范围和换场景时需要调整之处"),
    ],
    "systematic": [
        ("core_question", "question", "用核心问题建立本节学习方向"),
        ("explanation", "explanation", "连续解释概念、条件、推导与边界"),
        ("worked_example", "explanation", "用例子和反例建立联系"),
        ("independent_check", "exercise", "给出独立自查，并将答案与题目分开"),
    ],
}


def teaching_design(purpose, *, profile=None, knowledge_refs=None):
    if purpose not in _SEQUENCES:
        raise ValueError("Unsupported learning purpose")
    profile = profile or {}
    knowledge_refs = knowledge_refs or {}
    focus = []
    for point in (profile.get("knowledge_profile") or {}).get("nodes", []):
        kid = point.get("knowledge_id")
        if not kid or knowledge_refs.get(kid) != point.get("knowledge_revision_id"):
            continue
        evidence = sorted(
            point.get("evidence") or [], key=lambda e: str(e.get("observed_at") or e.get("created_at") or "")
        )
        last_pass = max(
            (
                i
                for i, e in enumerate(evidence)
                if e.get("support") == "independent" and e.get("outcome") == "passed" and e.get("counted") is not False
            ),
            default=-1,
        )
        if last_pass == len(evidence) - 1 and last_pass >= 0 and point.get("status") == "needs_review":
            focus.append(
                {
                    "knowledge_id": kid,
                    "knowledge_revision_id": knowledge_refs[kid],
                    "name": point.get("name") or kid,
                    "reason": "review_after_independent_pass",
                    "evidence_refs": deepcopy(evidence[-3:]),
                    "instruction": "已有新的独立通过，但正式画像仍需复查。保持基础讲解简洁，安排不同情境的新检查；不要重复同一种补讲或宣称已掌握。",
                }
            )
            continue
        evidence = evidence[last_pass + 1 :]
        failed = {
            e.get("source_id") or e.get("attempt_id")
            for e in evidence
            if e.get("outcome") == "not_passed" and e.get("support") == "independent" and e.get("counted") is not False
        } - {None, ""}
        if len(failed) >= 2:
            focus.append(
                {
                    "knowledge_id": kid,
                    "knowledge_revision_id": knowledge_refs[kid],
                    "name": point.get("name") or kid,
                    "reason": "repeated_independent_difficulty",
                    "evidence_refs": deepcopy(
                        [e for e in evidence if (e.get("source_id") or e.get("attempt_id")) in failed]
                    ),
                    "instruction": "先核对学生判断依据，再补一个最小对比例子；安排新的独立检查，不推断未获证实的错因。",
                }
            )
    return {
        "schema_version": "personal_teaching_design_v1",
        "purpose": purpose,
        "sequence": [
            {"role": role, "block_type": kind, "intent": intent} for role, kind, intent in _SEQUENCES[purpose]
        ],
        "focus": focus,
        "model_revision_id": profile.get("model_revision_id"),
        "mastery_write": False,
        "checks_are_learning_material_not_formal_attempts": True,
    }


def design_requirements(design):
    return (
        "\n本份个人讲义采用以下教学编排。按每节的实际知识和来源实现这些教学作用，不能只换标题；"
        "允许相邻讲解合并，保留题目与解答分离；应用场景的假设要明确标记。"
        "块标记的标题只写自然语言，不含小于号、大于号或 HTML；例如标题写‘严格与包含边界’，具体比较表达式放正文。"
        "材料中的练习只是学习材料，展示或阅读不得宣称产生正式作答与掌握证据。\n"
        + json.dumps(design, ensure_ascii=False)
    )


def source_knowledge_refs(profile, node_id, visible_blocks):
    """Use the freshly recomputed formal profile's exact current identities."""
    if not node_id:
        return {}
    return {
        p["knowledge_id"]: p["knowledge_revision_id"]
        for p in (profile.get("knowledge_profile") or {}).get("nodes", [])
        if p.get("knowledge_id")
        and p.get("knowledge_revision_id")
        and node_id in (p.get("section_refs") or [])
        and (not p.get("block_refs") or set(p["block_refs"]) & set(visible_blocks))
    }
