"""Resolve explicit scope locally; uncertain requests retain the full scan."""
from __future__ import annotations

from .scan_fingerprints import routing_fingerprint, unit_fingerprint

import re
from copy import deepcopy
from collections import defaultdict
from typing import Any


ROUTING_CONTRACT = 'course_change_routing_v1'
ROUTED_SCAN_CONTRACT = 'teacher_semantic_scan_v2+routing_v1'


def _text(unit: Any) -> str:
    return '\n'.join([unit.title, unit.text, *unit.full_text_fields.values()]).casefold()


def resolve_scope(context: Any, instruction: str, proposal: Any, *, force_full: bool = False) -> dict:
    all_ids = {u.unit_id for u in context.units}
    base = {'contract': ROUTING_CONTRACT, 'mode': 'full', 'topics': [], 'lecture_ids': [], 'evidence': '',
            'indexed_units': len(all_ids), 'selected_unit_ids': sorted(all_ids),
            'direct_unit_ids': [], 'related_unit_ids': [], 'outside_unit_ids': []}
    if force_full or not isinstance(proposal, dict):
        return base
    # A topic mentioned as an example must not narrow an explicit whole-course request.
    if re.search(r'全课|全课程|整门|整个课程|所有内容|全部内容|每一?讲|各讲|重构|重排|合并|拆分|(?:新增|删除).{0,12}讲|调整.{0,12}大纲|all\s+(?:content|lessons)|entire\s+course', instruction, re.I):
        return base
    nodes = {str(n['node_id']): n for n in context.outline}
    children = defaultdict(set)
    for node in context.outline:
        children[str(node.get('parent_node_id') or 'root')].add(str(node['node_id']))
    roots = [str(n['node_id']) for n in context.outline if int(n.get('node_level') or 1) == 1]
    topics = proposal.get('topics') or []
    lectures = proposal.get('lecture_ids') or []
    if (not isinstance(topics, list) or not isinstance(lectures, list)
            or any(not isinstance(item, str) for item in lectures)
            or len(topics) + len(lectures) > 8):
        return base
    mode = proposal.get('mode')
    evidence = proposal.get('evidence')
    if mode not in {'topics', 'lectures'} or not isinstance(evidence, str) or evidence not in instruction or len(evidence.strip()) < 3:
        return base
    if mode == 'topics':
        if not topics or lectures or any(not isinstance(p, str) or len(p.strip()) < 2 or p not in instruction for p in topics):
            return base
        # All quoted subjects must remain in scope, including a second requested topic.
        quoted = re.findall(r'[“「『"\u0027]([^”」』"\u0027]{2,80})[”」』"\u0027]', instruction)
        if any(not any(q in p or p in q for p in topics) for q in quoted):
            return base
        direct = {u.unit_id for u in context.units if any(p.casefold() in _text(u) for p in topics)}
    else:
        numbers = [int(v) for v in re.findall(r'第\s*(\d+)\s*讲', instruction)]
        explicit_ids = {roots[n-1] for n in numbers if 1 <= n <= len(roots)}
        named_ids = {nid for nid,n in nodes.items() if str(n.get('node_name') or '') and str(n['node_name']) in instruction}
        if topics or not lectures or not set(lectures).issubset(explicit_ids | named_ids):
            return base
        if explicit_ids - set(lectures):
            return base
        selected_sections = set(lectures)
        for _ in nodes:
            selected_sections.update(c for p in list(selected_sections) for c in children[p])
        direct = {u.unit_id for u in context.units if selected_sections.intersection(u.section_ids)}
    if not direct:
        return base
    seeds = set(direct)
    selected, sections = set(), set()
    # Follow explicit references to a fixed point, including the newly reached sections.
    for _ in range(len(context.units) + 1):
        sections = {s for u in context.units if u.unit_id in seeds for s in u.section_ids}
        for _ in nodes:
            sections.update(c for p in list(sections) for c in children[p])
        selected = seeds | {u.unit_id for u in context.units if sections.intersection(u.section_ids)}
        refs = {str(x) for u in context.units if u.unit_id in selected
                for k in ('concept_refs','objective_refs') for x in (u.metadata.get('course_block') or {}).get(k) or []}
        linked = {u.unit_id for u in context.units if refs.intersection(
            str(x) for k in ('concept_refs','objective_refs') for x in (u.metadata.get('course_block') or {}).get(k) or [])}
        if linked.issubset(seeds):
            break
        seeds.update(linked)
    ancestors = set(sections)
    for _ in nodes:
        ancestors.update(str(nodes[s].get('parent_node_id') or 'root') for s in list(ancestors) if s in nodes)
    # Lesson plans and slide decks can bind a parent lesson rather than a leaf section.
    selected.update(u.unit_id for u in context.units if u.asset_type in {'lesson_plan','ppt','outline'}
                    and ancestors.intersection(u.section_ids))
    return {**base, 'mode': mode, 'topics': topics, 'lecture_ids': lectures, 'evidence': evidence,
            'selected_unit_ids': sorted(selected), 'direct_unit_ids': sorted(direct),
            'related_unit_ids': sorted(selected-direct), 'outside_unit_ids': sorted(all_ids-selected)}


def canonical_aliases(context: Any, selected: set[str]) -> dict[str, str]:
    """Only a verified unified teacher projection may share its owning handout analysis."""
    if not context.canonical_authoring:
        return {}
    docs = {u.metadata['course_block']['block_id']: u for u in context.units
            if u.asset_type == 'course_content' and u.unit_id in selected and u.metadata.get('course_block')}
    aliases = {}
    for script in context.units:
        if script.asset_type != 'script' or script.unit_id not in selected or script.source_state != 'current':
            continue
        doc = docs.get(script.unit_id.rsplit(':', 1)[-1])
        if doc is None or doc.role != script.role or set(doc.section_ids) != set(script.section_ids):
            continue
        payload = doc.metadata['course_block']['payload']
        body = str(payload.get('markdown') or payload.get('text') or payload.get('content') or '')
        owner_body = script.full_text_fields.get('/content') or script.full_text_fields.get('/markdown') or ''
        if (body and body == owner_body and str(payload.get('title') or '') == script.full_text_fields.get('/title', '')
                and script.source_revision and doc.source_revision):
            aliases[script.unit_id] = doc.unit_id
    return aliases


def reusable_observation(*, plans, context, user_id, instruction, asset_types, model_identity, routing, contract,
                         answer_digest='', confirmed=False):
    """Reuse judgments only; never copy an older plan's edits or approval authority."""
    from .semantic_scan import validate_batch
    if not model_identity:
        return None
    outline = [{k:v for k,v in n.items() if k != 'section_snapshot'} for n in context.outline]
    selected = set(routing['selected_unit_ids'])
    required = {u.unit_id:unit_fingerprint(u) for u in context.units if u.unit_id in selected}
    for plan in reversed(plans):
        summary = plan.impact_summary
        if (plan.user_id != user_id or plan.course_id != context.course_id or plan.status != 'pending'
                or plan.generation_status == 'generating' or plan.request_text != instruction
                or not plan.teacher_change_planning or plan.teacher_change_planning.intent.blocking_questions
                or summary.get('scan_model_identity') != model_identity or summary.get('scan_contract') != contract
                or summary.get('current_outline') != outline or summary.get('source_mode') != context.source_mode
                or set(summary.get('request_asset_types') or []) != set(asset_types or [u.asset_type for u in context.units])
                or summary.get('clarification_answer_digest','') != answer_digest
                or bool(summary.get('clarification_confirmation')) != confirmed
                or routing_fingerprint(summary.get('request_routing') or {}) != routing_fingerprint(routing)):
            continue
        if routing['mode'] == 'full' and plan.base_revision_vector != context.base_revision_vector:
            continue
        coverage = summary.get('coverage') or {}
        missing = set(coverage.get('unscanned_unit_ids') or [])
        hashes = coverage.get('source_fingerprints') or {}
        if missing.intersection(selected) or any(hashes.get(uid) != fp for uid,fp in required.items()):
            continue
        raw = summary.get('scan_analysis')
        if not isinstance(raw, dict):
            continue
        try:
            analysis = validate_batch(raw, [{'unit_id':uid} for uid in selected])
        except (ValueError, TypeError):
            continue
        return deepcopy(analysis), selected, {'plan_id':plan.change_set_id,'unit_ids':sorted(selected)}
    return None
