"""Read-only knowledge aliases, independent of task lifecycle."""
import json
from copy import deepcopy
from knowledge_contracts import GENERIC_WORKFLOW

def knowledge_projection(tree):
    """Read-only v2 aliases for existing knowledge consumers; no new identities.

    A tree's source is reviewed material, not the subsequently written body.
    These aliases must never cause a body-derived rebuild of its stable atoms.
    """
    value = deepcopy(tree)
    from knowledge_relations import relation_index
    value['relation_index'] = relation_index(value)
    value["lifecycle_status"] = "active" if tree.get("status") == "accepted" else "candidate"
    if tree.get("tree_schema") == GENERIC_WORKFLOW:
        # Generic trees store canonical lecture/source references, while legacy
        # readers use bindings. Derive aliases without revising the saved tree.
        bindings = value.setdefault('bindings', [])
        for point in value.get('knowledge_points', []):
            targets = [('section', sid) for sid in point.get('section_refs', [])]
            targets += [('course_block', q['handout_ref']['block_id'])
                        for q in point.get('source_quotes', [])
                        if (q.get('handout_ref') or {}).get('block_id')]
            for kind, target in dict.fromkeys(targets):
                if target and not any(b.get('target_type') == kind and b.get('target_id') == target
                                      and point['knowledge_id'] in b.get('knowledge_ids', []) for b in bindings):
                    bindings.append({'target_type': kind, 'target_id': target, 'knowledge_ids': [point['knowledge_id']]})
        return value
    categories = {c["id"]: c for c in tree["categories"]}
    value["concept_groups"] = [{**c, "concept_group_id": c["id"], "primary_section_ref": c["parent_id"]}
                               for c in categories.values() if c.get("parent_id")]
    for point in value["knowledge_points"]:
        point.update(knowledge_type="rule", granularity_status="atomic", section_refs=[point["topic"]])
    for relation in value["relations"]:
        relation.update(relation_id=relation["id"], source_knowledge_id=relation["source_id"],
                        target_knowledge_id=relation["target_id"], relation_type=relation["type"])
    by_key = {p["key"]: p["knowledge_id"] for p in tree["knowledge_points"]}
    for diagnosis in value["misconceptions"]:
        if "hypothesis_a" not in diagnosis:
            # New teaching-package misconceptions already use the v2 fields.
            continue
        diagnosis.update(primary_knowledge_id=by_key[diagnosis["knowledge_keys"][0]],
            name=diagnosis["hypothesis_a"], observable_error_pattern=diagnosis["hypothesis_a"] + " / " + diagnosis["hypothesis_b"],
            discrimination=json.dumps(diagnosis["examples"], ensure_ascii=False),
            repair_strategy=diagnosis["repair_a"] + " / " + diagnosis["repair_b"])
    return value
