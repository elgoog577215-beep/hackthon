"""AI-proposed knowledge split candidates.

The requirement is specific: when several independently teachable objects are
compressed into one node that cannot be explained, practised or diagnosed
separately, the AI must be able to propose a split — listing the new nodes, the
old→new id mapping, and the affected downstream references — while the active
knowledge base stays untouched until a teacher confirms.

Two design consequences run through this module:

**The AI never writes.** It returns a *proposal*: names, statements, and which
existing content each new node covers. This module turns that into a normal
whitelist knowledge command candidate, which then goes through the same quality
gate, identity check and impact analysis as a hand-authored edit. There is no
path from model output to the knowledge base that skips teacher confirmation.

**The AI never invents ids.** Split ids are derived deterministically here from
the parent id, and the old→new mapping is constructed by this module, not by
the model. Letting a model mint stable identifiers is how historical practice
attempts end up pointing at knowledge that never existed.

A rejected proposal is recorded with its base revision so the same coarse node
is not re-proposed against unchanged evidence — the "证据修订冷却" the spec asks
for.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ai_base import AIBase
from course_knowledge_commands import KnowledgeCommandRejected, build_knowledge_candidate
from course_knowledge_point_edits import resolve_knowledge_id
from course_versioning import stable_hash

logger = logging.getLogger(__name__)

SPLIT_PROPOSAL_SCHEMA = "course_knowledge_split_proposal_v1"

# A split below this many parts is not a split; above it, the model is almost
# certainly shredding a legitimate node rather than separating real objects.
MIN_SPLIT_PARTS = 2
MAX_SPLIT_PARTS = 5

_SYSTEM_PROMPT = (
    "你是课程知识结构审阅者。你的任务是判断一个知识点是否把多个"
    "可以分别解释、分别练习、分别诊断的教学对象压在了一起。"
    "只有确实存在多个独立命题时才建议拆分；"
    "同一个命题的不同表述、举例或应用场景不是独立对象，不要拆。"
    "只输出 JSON，不要输出任何解释性文字。"
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _split_id(parent_id: str, index: int, name: str) -> str:
    """Derive a new knowledge id deterministically from its parent.

    Deterministic so that re-running the same proposal produces the same ids,
    and derived from the parent so the lineage stays visible in the id itself.
    """
    return stable_hash(
        {"parent": _text(parent_id), "index": index, "name": _text(name)},
        prefix="ckp_",
    )


def build_split_prompt(point: dict[str, Any]) -> str:
    """Ask about one specific node, quoting only what the judgement needs."""
    payload = {
        "name": _text(point.get("name")),
        "statement": _text(point.get("statement")),
        "conditions": [_text(item) for item in point.get("conditions") or []],
        "boundaries": [_text(item) for item in point.get("boundaries") or []],
        "knowledge_type": _text(point.get("knowledge_type")),
    }
    return (
        "判断下面这个知识点是否需要拆分。\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "若不需要拆分，输出：{\"should_split\": false, \"reason\": \"...\"}\n"
        "若需要拆分，输出：\n"
        "{\n"
        '  "should_split": true,\n'
        '  "reason": "为什么这是多个独立对象",\n'
        '  "parts": [\n'
        '    {"name": "新知识点名称", "statement": "该知识点表达的单一命题",\n'
        '     "conditions": ["适用条件"], "boundaries": ["边界"]}\n'
        "  ]\n"
        "}\n"
        f"parts 至少 {MIN_SPLIT_PARTS} 个，至多 {MAX_SPLIT_PARTS} 个。"
    )


def normalize_split_proposal(
    raw: dict[str, Any] | None,
    *,
    point: dict[str, Any],
) -> dict[str, Any]:
    """Validate the model's answer and assign stable ids ourselves.

    Everything the model says about identity is discarded: it may propose names
    and statements, but ids, the mapping and the source binding are computed
    here from the parent node.
    """
    parent_id = _text(point.get("knowledge_id"))
    result: dict[str, Any] = {
        "schema_version": SPLIT_PROPOSAL_SCHEMA,
        "knowledge_id": parent_id,
        "parent_name": _text(point.get("name")),
        "should_split": False,
        "reason": "",
        "parts": [],
        "identity_map": {},
        "rejected_reason": "",
    }
    if not isinstance(raw, dict):
        result["rejected_reason"] = "model_output_unparseable"
        return result

    result["reason"] = _text(raw.get("reason"))
    if not raw.get("should_split"):
        return result

    parts = raw.get("parts")
    if not isinstance(parts, list):
        result["rejected_reason"] = "parts_missing"
        return result

    normalized: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for index, part in enumerate(parts):
        if not isinstance(part, dict):
            continue
        name = _text(part.get("name"))
        statement = _text(part.get("statement"))
        if not name or not statement or name in seen_names:
            # A part without its own proposition is not a separable object;
            # dropping it beats letting the quality gate reject the whole split.
            continue
        seen_names.add(name)
        normalized.append({
            "knowledge_id": _split_id(parent_id, index, name),
            "name": name,
            "statement": statement,
            "conditions": [_text(item) for item in part.get("conditions") or [] if _text(item)],
            "boundaries": [_text(item) for item in part.get("boundaries") or [] if _text(item)],
        })

    if len(normalized) < MIN_SPLIT_PARTS:
        result["rejected_reason"] = "too_few_valid_parts"
        return result
    if len(normalized) > MAX_SPLIT_PARTS:
        result["rejected_reason"] = "too_many_parts"
        return result

    result["should_split"] = True
    result["parts"] = normalized
    result["identity_map"] = {parent_id: [part["knowledge_id"] for part in normalized]}
    return result


def apply_split_to_knowledge_base(
    knowledge_base: dict[str, Any],
    proposal: dict[str, Any],
) -> dict[str, Any]:
    """Produce the proposed knowledge base for a validated split.

    The parent node is replaced by its parts, each inheriting the parent's
    course placement and supporting records so the split does not silently drop
    the skills, misconceptions and criteria that hung off the original.
    """
    from copy import deepcopy

    parent_id = _text(proposal.get("knowledge_id"))
    parts = proposal.get("parts") or []
    if not parent_id or not parts:
        raise KnowledgeCommandRejected(
            "knowledge_split_proposal_invalid",
            "拆分候选缺少父知识点或子节点",
        )

    proposed = deepcopy(knowledge_base)
    parent = next(
        (
            item
            for item in proposed.get("knowledge_points") or []
            if _text(item.get("knowledge_id")) == parent_id
        ),
        None,
    )
    if parent is None:
        raise KnowledgeCommandRejected(
            "knowledge_point_not_found",
            "拆分目标不在当前知识库中，请刷新后重试",
        )

    new_points: list[dict[str, Any]] = []
    for part in parts:
        clone = deepcopy(parent)
        clone["knowledge_id"] = part["knowledge_id"]
        clone["name"] = part["name"]
        clone["statement"] = part["statement"]
        if part.get("conditions"):
            clone["conditions"] = list(part["conditions"])
        if part.get("boundaries"):
            clone["boundaries"] = list(part["boundaries"])
        # Keep the old name resolvable: plan paths and projections bind by name.
        aliases = [_text(item) for item in clone.get("aliases") or [] if _text(item)]
        parent_name = _text(parent.get("name"))
        if parent_name and parent_name not in aliases:
            aliases.append(parent_name)
        clone["aliases"] = aliases
        clone["revision_id"] = stable_hash(
            {key: value for key, value in clone.items() if key != "revision_id"},
            prefix="ckpr_",
        )
        new_points.append(clone)

    proposed["knowledge_points"] = [
        item for item in proposed.get("knowledge_points") or []
        if _text(item.get("knowledge_id")) != parent_id
    ] + new_points

    # Everything that hung off the parent must be re-pointed, or the split
    # leaves orphans: skills and misconceptions whose primary knowledge no
    # longer exists, criteria and bindings referencing a dead id, relations
    # with a dangling endpoint. The quality gate rejects all four, so a split
    # that ignores them can never be confirmed.
    primary_id = new_points[0]["knowledge_id"]
    all_new_ids = [part["knowledge_id"] for part in parts]

    for collection, field in (("skill_units", "primary_knowledge_id"),
                              ("misconceptions", "primary_knowledge_id")):
        for item in proposed.get(collection) or []:
            if isinstance(item, dict) and _text(item.get(field)) == parent_id:
                item[field] = primary_id

    for criterion in proposed.get("mastery_criteria") or []:
        if not isinstance(criterion, dict):
            continue
        ids = [_text(item) for item in criterion.get("knowledge_ids") or []]
        if parent_id in ids:
            # A criterion over the coarse node covers all of its parts.
            criterion["knowledge_ids"] = [
                item for item in ids if item != parent_id
            ] + all_new_ids

    for binding in proposed.get("bindings") or []:
        if not isinstance(binding, dict):
            continue
        ids = [_text(item) for item in binding.get("knowledge_ids") or []]
        if parent_id in ids:
            binding["knowledge_ids"] = [
                item for item in ids if item != parent_id
            ] + all_new_ids

    # Relations: the parent's edges attach to the first part, and the parts are
    # linked to each other so the split does not create disconnected nodes with
    # no inbound edge and no entry reason.
    relations = [
        item for item in proposed.get("relations") or [] if isinstance(item, dict)
    ]
    for relation in relations:
        if _text(relation.get("source_knowledge_id")) == parent_id:
            relation["source_knowledge_id"] = primary_id
        if _text(relation.get("target_knowledge_id")) == parent_id:
            relation["target_knowledge_id"] = primary_id
    for follower in new_points[1:]:
        relations.append({
            "relation_id": stable_hash(
                {"source": primary_id, "target": follower["knowledge_id"],
                 "type": "prerequisite"},
                prefix="ckrel_",
            ),
            "course_id": _text(proposed.get("course_id")),
            "source_knowledge_id": primary_id,
            "target_knowledge_id": follower["knowledge_id"],
            "relation_type": "prerequisite",
            "reason": f"由「{_text(parent.get('name'))}」拆分而来，先理解前者才能处理后者",
            "confidence": "medium",
            "status": "accepted",
        })
    proposed["relations"] = relations

    decisions = [
        item for item in proposed.get("relation_decisions") or []
        if isinstance(item, dict) and _text(item.get("knowledge_id")) != parent_id
    ]
    parent_decision = next(
        (
            item
            for item in knowledge_base.get("relation_decisions") or []
            if isinstance(item, dict) and _text(item.get("knowledge_id")) == parent_id
        ),
        None,
    )
    for index, part in enumerate(new_points):
        decisions.append({
            "knowledge_id": part["knowledge_id"],
            "decision": (
                _text((parent_decision or {}).get("decision")) or "course_entry"
            ) if index == 0 else "connected",
            "reason": (
                _text((parent_decision or {}).get("reason"))
                or "沿用拆分前的课程入口判断"
            ) if index == 0 else "由同一知识点拆分而来，依赖首个子节点",
        })
    proposed["relation_decisions"] = decisions

    proposed["revision_id"] = stable_hash(
        {"base": _text(knowledge_base.get("revision_id")), "split": parent_id,
         "parts": [part["knowledge_id"] for part in parts]},
        prefix="ckbr_",
    )
    return proposed


class KnowledgeRefinementService(AIBase):
    """Proposes knowledge refinements; never applies them."""

    async def propose_split(
        self,
        course_data: dict[str, Any],
        *,
        knowledge_id: str,
        actor: str = "ai",
    ) -> dict[str, Any]:
        """Ask the model whether one node should be split, and build a candidate.

        Returns `{"proposal": …, "candidate": … | None}`. The candidate is a
        normal whitelist command candidate — unconfirmed, quality-gated, and
        carrying its own impact report. Nothing is written here.
        """
        active = course_data.get("course_knowledge_base") or {}
        # The teacher clicks a knowledge *view*; when the stored base was
        # rejected on fingerprint mismatch the view's ids differ from it.
        resolved = resolve_knowledge_id(active, knowledge_id, course_data=course_data)
        point = next(
            (
                item
                for item in active.get("knowledge_points") or []
                if _text(item.get("knowledge_id")) == (resolved or _text(knowledge_id))
            ),
            None,
        )
        if point is None:
            raise KnowledgeCommandRejected(
                "knowledge_point_not_found",
                "知识点不在当前知识库中，请刷新后重试",
            )

        response = await self._call_llm(
            build_split_prompt(point),
            system_prompt=_SYSTEM_PROMPT,
            json_mode=True,
        )
        proposal = normalize_split_proposal(self._extract_json(response or ""), point=point)
        proposal["base_knowledge_revision_id"] = _text(active.get("revision_id"))

        if not proposal["should_split"]:
            return {"proposal": proposal, "candidate": None}

        proposed = apply_split_to_knowledge_base(active, proposal)
        try:
            candidate = build_knowledge_candidate(
                course_data,
                operation="split_knowledge_point",
                proposed_knowledge_base=proposed,
                reason=proposal["reason"] or "AI 判断该知识点包含多个独立教学对象",
                identity_map=proposal["identity_map"],
                actor=actor,
            )
        except KnowledgeCommandRejected as error:
            # A proposal that cannot pass the gate is reported as such rather
            # than raised: the teacher should see that AI suggested a split and
            # why it was refused.
            proposal["rejected_reason"] = error.code
            return {"proposal": proposal, "candidate": None}
        return {"proposal": proposal, "candidate": candidate, "proposed_knowledge_base": proposed}


__all__ = [
    "MAX_SPLIT_PARTS",
    "MIN_SPLIT_PARTS",
    "SPLIT_PROPOSAL_SCHEMA",
    "KnowledgeRefinementService",
    "apply_split_to_knowledge_base",
    "build_split_prompt",
    "normalize_split_proposal",
]
