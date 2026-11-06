"""Derived reading aids on the owned handout; never a second content store."""
from copy import deepcopy
import uuid

READING_SCHEMA_VERSION = "study_reading_v1"
READING_PROMPT_VERSION = "study_reading_relations_v5"
RELATION_TYPES = {"prerequisite", "derives", "applies_to", "contrasts_with", "equivalent_to", "generalizes"}


def reading_response_schema(source: dict, prior: list[dict]) -> dict:
    """Bound metadata size and routing IDs at the same existing model call."""
    def obj(properties):
        return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}

    def array(items, maximum, minimum=0):
        return {"type": "array", "items": items, "minItems": minimum, "maxItems": maximum}

    short = {"type": "string", "maxLength": 120}
    sentence = {"type": "string", "maxLength": 240}
    refs = array(obj({"evidence_id": {"type": "string", "enum": [b["evidence_id"] for b in source["blocks"]]}}), 2, 1)
    local_keys = [f"c{i}" for i in range(1, 7)]
    point = obj({"key": {"type": "string", "enum": local_keys}, "name": short, "statement": sentence, "source_refs": refs})
    relation = obj({"source_ref": {"type": "string", "enum": [*local_keys, *[p["knowledge_id"] for p in prior]]},
                    "target_ref": {"type": "string", "enum": local_keys},
                    "relation_type": {"type": "string", "enum": sorted(RELATION_TYPES)},
                    "reason": sentence, "conditions": array(short, 3),
                    "derivation_steps": array({"type": "string", "maxLength": 2000}, 32), "source_refs": refs})
    section = obj({"node_id": {"type": "string", "enum": [source["node_id"]]},
                   "knowledge_structure": array(obj({"knowledge_points": array(point, 6)}), 1, 1),
                   "knowledge_relations": array(relation, 6)})
    return obj({"sections": array(section, 1, 1)})


def required_text(value, label: str, limit: int = 1200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{label}不完整，已保留正文，请主动继续")
    return value.strip()


def bind_refs(refs, source: dict) -> list[dict]:
    blocks = {block["evidence_id"]: block for block in source["blocks"]}
    if not isinstance(refs, list) or not refs:
        raise ValueError("阅读辅助的来源标识不完整，请主动继续")
    result = []
    for ref in refs:
        block = blocks.get(ref.get("evidence_id")) if isinstance(ref, dict) else None
        if not block:
            raise ValueError("阅读辅助引用了不存在或不可展示的正文来源，请主动继续")
        # Only server-owned locations survive. Model quotations are not evidence.
        bound = {key: source[key] for key in ("kind", "revision_id", "node_id", "title", "source_sha256")}
        bound.update({"evidence_id": block["evidence_id"], "block_id": block["block_id"], "locator": deepcopy(block["locator"])})
        if bound not in result:
            result.append(bound)
    return result


def validate_reading_plan(plan: dict, source: dict, prior: list[dict]) -> dict:
    """Validate structure and source pointers, not teaching correctness."""
    try:
        raw_points = [point for group in plan["knowledge_structure"] for point in group["knowledge_points"]]
    except (KeyError, TypeError):
        raise ValueError("知识概念结构不完整，请主动继续") from None
    if not 0 <= len(raw_points) <= 6:
        raise ValueError("本讲核心概念不能超过 6 个，请主动继续")
    points, by_name, by_key = [], {}, {}
    for point in raw_points:
        if not isinstance(point, dict):
            raise ValueError("知识概念结构不完整，请主动继续")
        name = required_text(point.get("name"), "概念名", 120)
        if name in by_name:
            raise ValueError("知识概念重复，请主动继续")
        identity = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source['revision_id']}:{source['node_id']}:concept:{name}"))
        item = {"knowledge_id": identity, "name": name,
                "statement": required_text(point.get("statement"), "概念说明"),
                "source_refs": bind_refs(point.get("source_refs"), source)}
        points.append(item)
        by_name[name] = item
        if "key" in point:
            key = point["key"]
            if key not in {"c1", "c2", "c3", "c4"} or key in by_key:
                raise ValueError("本讲概念引用键重复或无效，已保留正文，请主动继续")
            by_key[key] = identity
    known = {p["knowledge_id"]: p for p in [*prior, *points]}
    local = {p["knowledge_id"] for p in points}
    relations = []
    if not isinstance(plan.get("knowledge_relations"), list):
        raise ValueError("知识关系结构不完整，请主动继续")
    for edge in plan["knowledge_relations"]:
        if not isinstance(edge, dict):
            raise ValueError("知识关系结构不完整，请主动继续")
        if "source_ref" in edge or "target_ref" in edge:
            # New outputs route through finite keys rather than repeating free-text names.
            # Prior IDs are accepted only as sources; never infer an identity by similarity.
            prior_ids = {p["knowledge_id"] for p in prior}
            source_ref, target_ref = edge.get("source_ref"), edge.get("target_ref")
            endpoints = [by_key.get(source_ref) or (source_ref if source_ref in prior_ids else None), by_key.get(target_ref)]
        else:
            endpoints = [edge.get(f"{side}_knowledge_id") or by_name.get(edge.get(f"{side}_name"), {}).get("knowledge_id") for side in ("source", "target")]
        a, b = endpoints
        if a not in known or b not in known or b not in local:
            raise ValueError("知识关系引用了未声明的概念，已保留正文，请主动继续整理概念关系")
        if a == b:
            raise ValueError("知识关系的两个概念相同，已保留正文，请主动继续整理概念关系")
        if edge.get("relation_type") not in RELATION_TYPES:
            raise ValueError("知识关系类型不支持，已保留正文，请主动继续整理概念关系")
        conditions = edge.get("conditions", [])
        if not isinstance(conditions, list) or len(conditions) > 8:
            raise ValueError("关系条件结构不完整，请主动继续")
        derivation = edge.get("derivation_steps", [])
        if not isinstance(derivation, list) or len(derivation) > 32:
            raise ValueError("推导步骤结构不完整，请主动继续")
        relations.append({"source_knowledge_id": a, "target_knowledge_id": b,
                          "source_name": known[a]["name"], "target_name": known[b]["name"],
                          "relation_type": edge["relation_type"], "reason": required_text(edge.get("reason"), "关系依据"),
                          "conditions": [required_text(c, "关系条件") for c in conditions],
                          "derivation_steps": [required_text(step, "推导步骤", 2000) for step in derivation],
                          "source_refs": bind_refs(edge.get("source_refs"), source)})
    raw_paths = plan.get("learning_paths", [])
    if not isinstance(raw_paths, list) or len(raw_paths) > 3:
        raise ValueError("思维链结构不完整，请主动继续")
    paths = []
    for index, path in enumerate(raw_paths):
        if not isinstance(path, dict) or path.get("kind") not in {"derivation", "method", "example"}:
            raise ValueError("思维链类型不完整，请主动继续")
        steps = path.get("steps")
        if not isinstance(steps, list) or not 2 <= len(steps) <= 12:
            raise ValueError("思维链步骤不完整，请主动继续")
        seen, normalized = set(), []
        for number, step in enumerate(steps):
            if not isinstance(step, dict):
                raise ValueError("思维链步骤结构不完整，请主动继续")
            key = required_text(step.get("id"), "步骤标识", 80)
            parent = step.get("parent_id") or ""
            stage = step.get("stage")
            if key in seen or (number == 0 and (parent or stage != "start")) or (number > 0 and (parent not in seen or stage == "start")):
                raise ValueError("思维链分支或起点不完整，请主动继续")
            if stage not in {"start", "choice", "step", "result", "check"}:
                raise ValueError("思维链步骤类型不完整，请主动继续")
            reason = step.get("reason") or ""
            condition = step.get("condition") or ""
            if stage in {"choice", "step"}:
                reason = required_text(reason, "步骤依据")
            elif reason:
                reason = required_text(reason, "步骤依据")
            if condition:
                condition = required_text(condition, "分支条件")
            normalized.append({"id": key, "parent_id": parent, "stage": stage,
                               "text": required_text(step.get("text"), "步骤内容"), "reason": reason, "condition": condition,
                               "source_refs": bind_refs(step.get("source_refs"), source)})
            seen.add(key)
        # Siblings may be parallel explanatory steps, not alternative methods.
        # Only explicit choices require a selection condition for every branch.
        # Never invent conditions or rewrite the model's parent relationships.
        for parent in normalized:
            children = [s for s in normalized if s["parent_id"] == parent["id"]]
            is_choice = parent["stage"] == "choice" or any(child["condition"] for child in children)
            if len(children) > 1 and is_choice and any(not child["condition"] for child in children):
                raise ValueError("思维链的分支缺少选择条件，请主动继续")
        paths.append({"id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source['revision_id']}:{source['node_id']}:path:{index}")),
                      "title": required_text(path.get("title"), "思维链标题", 180), "kind": path["kind"], "steps": normalized})
    return {"node_id": source["node_id"], "knowledge_structure": [{"knowledge_points": points}],
            "knowledge_relations": relations, "learning_paths": paths, "reading_schema_version": READING_SCHEMA_VERSION, "reading_prompt_version": READING_PROMPT_VERSION}
