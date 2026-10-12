"""Experimental teaching compiler. Identity checks never certify semantics.

Frozen answers are resolved by code, never rewritten by the teaching model.
New questions, binding rationales, predictions and repairs remain review candidates.
"""
from copy import deepcopy
from .pipeline import digest

VERSION = 'teaching_semantic_contract_v1'


def question_bank(course):
    return {q['key']: {**deepcopy(q), 'revision': digest(q),
                      'role': role, 'answer_origin': 'frozen_fixture'}
            for role, field in [('practice', 'probes'), ('transfer', 'retests')]
            for q in course[field]}


def compile_candidate(course, tree, doc):
    """Return reviewable resolved content and fail-closed mechanical findings."""
    bank = question_bank(course)
    issues = []
    points = {p['key']: p for p in tree['points']}
    sources = {m['id']: m['text'] for m in course['materials']}
    result = deepcopy(doc)

    def bad(code, path):
        issues.append({'code': code, 'path': path})

    for i, q in enumerate(doc.get('supplemental_probes', [])):
        path = f'supplemental_probes[{i}]'
        key = q.get('key', '')
        if not key.startswith('N') or key in bank:
            bad('question_identity_collision', path)
            continue
        if not all(q.get(k) for k in ('question', 'answer', 'evidence_type', 'source_refs')):
            bad('incomplete_question', path)
        if not set(q.get('source_refs', [])) <= sources.keys():
            bad('unknown_source', path)
        bank[key] = {**deepcopy(q), 'revision': digest(q), 'role': 'practice',
                     'answer_origin': 'model_candidate'}

    covered = []
    for i, skill in enumerate(result.get('skills', [])):
        path = f'skills[{i}]'
        owned = skill.get('point_keys', [])
        if not owned or not set(owned) <= points.keys():
            bad('skill_points', path)
        task = skill.get('task', {})
        if task.get('state_policy') != 'independent_reset' or not task.get('probe_keys'):
            bad('ambiguous_training_state', path)
        used = set(task.get('probe_keys', []))
        for key in used:
            if key not in bank or bank[key]['role'] != 'practice':
                bad('training_uses_transfer_or_unknown', path + '.task')
        for j, c in enumerate(skill.get('criteria', [])):
            cp = f'{path}.criteria[{j}]'
            covered.append(c.get('point_key'))
            key = c.get('probe_key')
            if c.get('point_key') not in owned:
                bad('criterion_point', cp)
            if key not in bank or bank[key]['role'] != 'practice':
                bad('criterion_question', cp)
                continue
            q = bank[key]
            if q['answer_origin'] == 'frozen_fixture' and c.get('question_revision') != q['revision']:
                bad('stale_question', cp)
            if not all(c.get('binding', {}).get(k) for k in ('target', 'required_evidence', 'why_direct')):
                bad('missing_semantic_binding', cp)
            # Reject freeform scoring fields rather than silently overwriting them.
            if any(k in c for k in ('pass_evidence', 'answer', 'correct_answer')):
                bad('answer_rewrite', cp)
            c['resolved_check'] = deepcopy(q)
        mistakes = skill.get('mistakes', [])
        if not 1 <= len(mistakes) <= 2:
            bad('mistake_count', path)
        mkeys = set()
        for j, m in enumerate(mistakes):
            mp = f'{path}.mistakes[{j}]'
            if not m.get('key') or m['key'] in mkeys:
                bad('mistake_identity', mp)
            mkeys.add(m.get('key'))
            if not m.get('point_keys') or not set(m['point_keys']) <= set(owned):
                bad('mistake_points', mp)
            if m.get('probe_key') not in bank or bank[m['probe_key']]['role'] != 'practice':
                bad('mistake_question', mp)
            if not all(m.get(k) for k in ('wrong_rule', 'prediction', 'derivation', 'limits')):
                bad('missing_prediction_trace', mp)
            for n, step in enumerate(m.get('repair_steps', [])):
                rp = f'{mp}.repair_steps[{n}]'
                quote = step.get('source_quote', '')
                if not quote or quote not in sources.get(step.get('source_ref'), ''):
                    bad('unsupported_repair_quote', rp)
                ref = step.get('check_key')
                if ref not in bank or bank[ref]['role'] != 'practice':
                    bad('repair_uses_transfer_or_unknown', rp)
                else:
                    used.add(ref)
                    step['resolved_check'] = deepcopy(bank[ref])
                if not step.get('action') or not step.get('scope_limit'):
                    bad('incomplete_repair', rp)
            if not m.get('repair_steps'):
                bad('missing_repair', mp)
        disc = skill.get('discrimination', {})
        if not disc.get('limits') or not disc.get('distinguishes'):
            bad('diagnostic_limits', path)
        if not set(disc.get('probe_keys', [])) <= bank.keys():
            bad('diagnostic_question', path)
        for key in disc.get('probe_keys', []):
            if key in bank and bank[key]['role'] != 'practice':
                bad('diagnostic_uses_transfer', path)
        retest = skill.get('retest', {})
        rkey = retest.get('key')
        if rkey not in bank or bank[rkey]['role'] != 'transfer':
            bad('transfer_question', path)
        else:
            transfer = bank[rkey]
            if retest.get('question_revision') != transfer['revision']:
                bad('stale_transfer', path)
            if any(bank[k]['question'] == transfer['question'] for k in used if k in bank):
                bad('transfer_reused_as_training', path)
            skill['retest']['resolved_check'] = deepcopy(transfer)
        if not retest.get('prerequisite_point_keys', []) == list(dict.fromkeys(retest.get('prerequisite_point_keys', []))):
            bad('duplicate_prerequisite', path)
        if not set(retest.get('prerequisite_point_keys', [])) <= points.keys():
            bad('transfer_prerequisite', path)
        if not retest.get('why_transfer') or not skill.get('mastery_requirements'):
            bad('transfer_or_mastery_evidence', path)
    if set(covered) != points.keys() or len(covered) != len(points):
        bad('criteria_coverage', 'skills')
    if not 1 <= len(result.get('skills', [])) <= 2:
        bad('skill_count', 'skills')
    result['contract'] = {'version': VERSION, 'tree_revision': digest(tree),
        'question_bank_revision': digest(question_bank(course)), 'structural_issues': issues,
        'semantic_status': 'pending_independent_review', 'ready_for_adoption': False}
    return result


REVIEW_AXES = ('atomicity_and_coverage', 'question_binding', 'prediction',
              'repair', 'transfer', 'cross_content_consistency')


def attach_review(candidate, review):
    """Bind an independent review to exact content; no production adoption."""
    if review.get('candidate_digest') != digest(candidate):
        raise ValueError('stale_semantic_review')
    axes = review.get('axes', {})
    if set(axes) != set(REVIEW_AXES) or any(type(v) is not bool for v in axes.values()):
        raise ValueError('incomplete_semantic_review')
    if not review.get('reviewer') or not review.get('evidence'):
        raise ValueError('missing_review_evidence')
    result = deepcopy(candidate)
    result['independent_review'] = deepcopy(review)
    usable = all(axes.values()) and not result['contract']['structural_issues'] and not review.get('blockers')
    result['contract']['semantic_status'] = 'sample_usable' if usable else 'needs_revision'
    result['contract']['sample_usable'] = usable
    # A lab review is not an owner adoption command or a teacher approval.
    result['contract']['ready_for_adoption'] = False
    return result
