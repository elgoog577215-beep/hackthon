"""Frozen per-lecture additions, independent of legacy assessment slot identity."""
from copy import deepcopy

from course_versioning import stable_hash

QUANTITY_SCHEMA = 'assessment_quantity_plan_v1'


def build_quantity_plan(course, blueprint, *, previous, node_ids, count, append_only, batch_id):
    if type(count) is not int or not 1 <= count <= 20:
        raise ValueError('questions_per_lesson must be between 1 and 20')
    templates = {str(n['node_id']): n.get('slots') or [] for n in blueprint.get('nodes') or []}
    lookup = {str(n.get('node_id')): n for n in course.get('nodes') or []}
    groups = {}
    for node_id in node_ids:
        if node_id not in templates or not templates[node_id]:
            continue
        node = lookup.get(node_id) or {}
        parent = str(node.get('parent_node_id') or node.get('parent_id') or node_id)
        groups.setdefault(parent, []).append(node_id)
    plan = {'schema_version':QUANTITY_SCHEMA,'batch_id':batch_id,'count':count,'append_only':bool(append_only),'slots':{},'lectures':{}}
    for lecture, nodes in groups.items():
        existing = sum(str(i.get('node_id') or '') in nodes and i.get('lifecycle_status') not in {'rejected','discarded'}
                       for i in (previous or {}).get('items') or [])
        needed = count if append_only else max(0, count-existing)
        plan['lectures'][lecture] = {'node_ids':nodes,'existing':existing,'requested_additions':needed}
        for node_id in nodes:
            plan['slots'][node_id] = []
        for index in range(needed):
            node_id = nodes[index % len(nodes)]
            template_index = (index // len(nodes)) % len(templates[node_id])
            plan['slots'][node_id].append({
                'generation_key':stable_hash({'batch':batch_id,'node':node_id,'index':index},prefix='aqs_'),
                'template_index':template_index,'variant_index':existing+index,
            })
    return plan


def apply_quantity_plan(nodes, plan):
    if plan.get('schema_version') != QUANTITY_SCHEMA:
        raise ValueError('unsupported assessment quantity plan')
    result = deepcopy(nodes)
    for node in result:
        node_id = str(node['node_id'])
        templates = node.get('slots') or []
        node['slots'] = []
        for entry in plan['slots'].get(node_id, []):
            slot = deepcopy(templates[entry['template_index']])
            slot.update(slot_id=entry['generation_key'],generation_key=entry['generation_key'],
                        variant_index=entry['variant_index'],quantity_schema=QUANTITY_SCHEMA,quantity_batch_id=plan['batch_id'])
            node['slots'].append(slot)
        node['diversity_checks'] = {'status':'quantity_plan','passed':True}
    return result
