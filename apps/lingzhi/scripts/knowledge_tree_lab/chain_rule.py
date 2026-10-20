"""Finite, authored chain-rule evidence lab; no runtime persistence or diagnosis.

The patterns distinguish stipulated examples, not validated learner traits.
Unknown free text is ungraded. No score or mastery record is written.
"""
from .pipeline import digest


def build_bundle():
    knowledge = [
        {'id': 'K-COMP', 'name': '函数复合', 'claim': '(f∘g)(x)=f(g(x))，先g后f。',
         'conditions': ['x在g的定义域且g(x)在f的定义域'], 'prerequisites': []},
        {'id': 'K-POWER', 'name': '正整数幂函数求导', 'claim': '(x^n)′=n*x^(n-1)。',
         'conditions': ['自变量x为实数；n为固定正整数'], 'prerequisites': []},
        {'id': 'K-SIN', 'name': '正弦函数求导', 'claim': '(sin u)′=cos u。',
         'conditions': ['对实变量u求导，角度采用弧度'], 'prerequisites': []},
        {'id': 'K-COS', 'name': '余弦函数求导', 'claim': '(cos u)′=-sin u。',
         'conditions': ['对实变量u求导，角度采用弧度'], 'prerequisites': []},
        {'id': 'K-CHAIN', 'name': '链式求导', 'claim': '(f∘g)′(x0)=f′(g(x0))*g′(x0)。',
         'conditions': ['x0为被求导的实数点', 'g在x0可导', 'f在g(x0)可导', '复合在x0邻域内有定义'],
         'prerequisites': ['K-COMP']},
    ]
    checks = {}

    def check(key, prompt, answers, wrong, knowledge_ids, dimension, context, role='diagnostic'):
        checks[key] = {'check_id': key, 'prompt': prompt, 'accepted_answers': answers,
                       'wrong_answers': wrong, 'knowledge_ids': knowledge_ids,
                       'dimension': dimension, 'context': context, 'role': role}

    check('trigger', '对sin(x^2)求导。', ['2*x*cos(x^2)'], ['cos(x^2)'],
          ['K-COMP', 'K-POWER', 'K-SIN', 'K-CHAIN'], '综合表现', '共同错题', 'symptom')
    check('structure-1', '只辨认sin(x^2)的内外层：指定外层为sin(u)，写出内层并说明顺序，不求导。',
          ['内层x^2，外层sin(u)'], ['内层sin(x)，外层u^2'], ['K-COMP'], '结构理解', '指定分解')
    check('structure-2', '将(3x+1)^2写成先计算u再计算y的两步，指定外层为u^2，不求导。',
          ['u=3x+1，y=u^2'], ['u=x^2，y=3u+1'], ['K-COMP'], '结构理解', '指定分解变式')
    check('power-1', '只求x^2对x的导数。', ['2*x'], ['x', '2'], ['K-POWER'], '基础求导', '平方')
    check('power-2', '只求x^3对x的导数。', ['3*x^2'], ['x^2', '3*x'], ['K-POWER'], '基础求导', '立方')
    check('trig-1', '只求sin(u)对u的导数，采用弧度。', ['cos(u)'], ['sin(u)'],
          ['K-SIN'], '基础求导', '正弦')
    check('trig-2', '只求cos(u)对u的导数，采用弧度。', ['-sin(u)'], ['sin(u)'],
          ['K-COS'], '基础求导', '余弦')
    check('arithmetic', '只计算3乘5，不涉及函数。', ['15'], ['5', '8'], [], '控制项', '算术控制')
    check('evaluation-1', "已知g(1)=9、g'(1)=3、f'(9)=7、f'(1)=2，且满足链式可导条件。求(f∘g)'(1)。",
          ['21'], ['6'], ['K-CHAIN'], '外层求值位置', '提供基础导数的数值点')
    check('evaluation-2', "已知g(2)=4、g'(2)=2、f'(4)=5、f'(2)=11，且满足链式可导条件。求(f∘g)'(2)。",
          ['10'], ['22'], ['K-CHAIN'], '外层求值位置', '提供基础导数的另一数值点')
    check('combination-1', "已知f'(g(x0))=5、g'(x0)=3，且满足链式可导条件。写出你认为最终应采用的完整运算式，先不求值；若认为只需一个数，请说明是否还需其他因子。",
          ['5*3', '3*5'], ['我认为最终式子就是5，不需要其他因子'], ['K-CHAIN'], '规则组合', '已提供对应位置的两部分导数')
    check('combination-2', "已知f'(g(x0))=2、g'(x0)=4，且满足链式可导条件。写出你认为最终应采用的完整运算式，先不求值；若认为只需一个数，请说明是否还需其他因子。",
          ['2*4', '4*2'], ['我认为最终式子就是2，不需要其他因子'], ['K-CHAIN'], '规则组合', '另一组已知导数')
    check('familiar-1', '对sin(2x)求导。', ['2*cos(2*x)'], ['cos(2*x)'],
          ['K-SIN', 'K-CHAIN'], '显式函数应用', '熟悉表示')
    check('familiar-2', '对cos(3x)求导。', ['-3*sin(3*x)'], ['-sin(3*x)'],
          ['K-COS', 'K-CHAIN'], '显式函数应用', '熟悉表示变式')
    check('transfer-1', "已知F'(u)=2u、(3x+1)'=3，求F(3x+1)对x的导数；各函数满足链式条件。",
          ['6*(3*x+1)'], ['2*(3*x+1)'], ['K-CHAIN'], '表示变化', '抽象函数记号，已提供基础导数')
    check('transfer-2', "已知A'(z)=cos(z)、(2t)'=2，求A(2t)对t的导数；各函数满足链式条件。",
          ['2*cos(2*t)'], ['cos(2*t)'], ['K-CHAIN'], '表示变化', '另一抽象记号及自变量')
    check('verify-1', '独立对sin(4x)求导。', ['4*cos(4*x)'], ['cos(4*x)'],
          ['K-SIN', 'K-CHAIN'], '后续独立验证', '新题', 'verification')
    check('verify-2', '独立对cos(5x)求导。', ['-5*sin(5*x)'], ['-sin(5*x)'],
          ['K-COS', 'K-CHAIN'], '后续独立验证', '另一新题', 'verification')
    components = ['structure-1', 'structure-2', 'power-1', 'power-2', 'trig-1', 'trig-2',
                  'arithmetic', 'evaluation-1', 'evaluation-2']
    rules = {
        'structure': ('复合结构辨认待补', ['K-COMP'], 'concept_gap', ['structure-1', 'structure-2'], [],
                      '先画输入输出顺序，分清先计算内层、再把结果送入外层；换表达式重新辨认。'),
        'power': ('幂函数基本求导待补', ['K-POWER'], 'concept_gap', ['power-1', 'power-2'], [],
                  '回到正整数幂求导规则，用平方与立方说明指数与系数的变化，再做新题。'),
        'trig': ('三角函数基本求导待核对', ['K-SIN', 'K-COS'], 'concept_gap', ['trig-1', 'trig-2'], [],
                 '分别核对正弦与余弦的基本导数及余弦求导负号；不先重复整套链式公式。'),
        'evaluation': ('外层导数求值位置待核对', ['K-CHAIN'], 'boundary_confusion',
                       ['evaluation-1', 'evaluation-2'], ['structure-1', 'structure-2', 'arithmetic'],
                       '沿x0到g(x0)再到外层导数的代入路径标记求值位置，用已给数值核对。'),
        'combination': ('链式规则组合仍不稳定', ['K-CHAIN'], 'process_error',
                        ['combination-1', 'combination-2'], components,
                        '先标记外层导数与内层导数这两个整体，再连接运算；随后撤去步骤提示做新题。'),
        'transfer': ('抽象函数记号下的应用待补', ['K-CHAIN'], 'transfer_gap',
                     ['transfer-1', 'transfer-2'], [*components, 'combination-1', 'combination-2', 'familiar-1', 'familiar-2'],
                     '对照sin(2x)与F(3x+1)中的相同复合结构，再换未见的函数记号独立作答。'),
    }
    hypotheses = {key: {'hypothesis_id': key, 'label': label, 'knowledge_ids': refs, 'category': category,
                        'fail_checks': fails, 'controls': controls, 'help': explanation}
                  for key, (label, refs, category, fails, controls, explanation) in rules.items()}
    bundle = {'contract': 'chain_rule_diagnostic_lab_v1', 'source_kind': 'authored_sample',
              'knowledge': knowledge, 'checks': checks, 'hypotheses': hypotheses}
    bundle['revision'] = digest(bundle)
    return bundle


def public_bundle():
    bundle = build_bundle()
    fields = ('check_id', 'prompt', 'knowledge_ids', 'dimension', 'context', 'role')
    return {'contract': bundle['contract'], 'revision': bundle['revision'], 'knowledge': bundle['knowledge'],
            'checks': {key: {field: check[field] for field in fields} for key, check in bundle['checks'].items()}}


def grade_fixture(check_id, response):
    """Closed authored answer set, not a free-text mathematical grader."""
    check = build_bundle()['checks'][check_id]
    value = ''.join(str(response).split())
    for field, result in [('accepted_answers', True), ('wrong_answers', False)]:
        if value in {''.join(answer.split()) for answer in check[field]}:
            return result
    return None


def _eligible(events, bundle, actor, course, phase):
    usable, excluded = [], []
    for event in events:
        reason = ('scope' if event.get('user_id') != actor or event.get('course_id') != course
                  else 'teacher_preview' if event.get('teacher_preview')
                  else 'stale_revision' if event.get('knowledge_revision') != bundle['revision']
                  else 'unknown_check' if event.get('check_id') not in bundle['checks']
                  else 'other_phase' if event.get('phase') != phase
                  else 'assisted' if event.get('support_level') != 0 or event.get('answer_revealed') is not False
                  else 'ungraded' if type(event.get('passed')) is not bool
                  else 'missing_identity' if not event.get('event_id') or not event.get('activity_id') else '')
        if reason:
            excluded.append({'event_id': event.get('event_id'), 'reason': reason})
        else:
            usable.append(event)
    # An explicit correction can replace the interpretation, never the source history.
    by_id = {event['event_id']: event for event in usable}
    superseded = set()
    for event in usable:
        if event.get('supersedes'):
            old = by_id.get(event['supersedes'])
            if (old and event.get('correction_reason') and not old.get('supersedes') and old['event_id'] != event['event_id']
                    and all(old.get(key) == event.get(key) for key in ('activity_id', 'check_id'))):
                superseded.add(old['event_id'])
            else:
                superseded.add(event['event_id'])
                excluded.append({'event_id': event['event_id'], 'reason': 'invalid_correction'})
    groups = {}
    for event in usable:
        if event['event_id'] not in superseded:
            groups.setdefault(event['activity_id'], []).append(event)
    unique = []
    for copies in groups.values():
        if len({(event['check_id'], event['passed'], event.get('response')) for event in copies}) > 1:
            excluded.extend({'event_id': event['event_id'], 'reason': 'conflicting_activity'} for event in copies)
        else:
            unique.append(copies[0])
    return unique, excluded


def replay(events, *, bundle=None, actor='sample-student', course='chain-sample'):
    bundle = bundle or build_bundle()
    usable, excluded = _eligible(events, bundle, actor, course, 'diagnostic')
    states = {}
    for key in bundle['checks']:
        results = {event['passed'] for event in usable if event['check_id'] == key}
        states[key] = 'conflicting' if len(results) > 1 else 'pass' if results == {True} else 'fail' if results == {False} else 'not_observed'
    candidates, findings = [], []
    for key, hypothesis in bundle['hypotheses'].items():
        supports = [event['event_id'] for event in usable if event['check_id'] in hypothesis['fail_checks'] and not event['passed']]
        against = [event['event_id'] for event in usable if event['check_id'] in hypothesis['fail_checks'] and event['passed']]
        matches = (all(states[check] == 'fail' for check in hypothesis['fail_checks'])
                   and all(states[check] == 'pass' for check in hypothesis['controls']))
        if matches:
            candidates.append(key)
        findings.append({'hypothesis_id': key, 'category': hypothesis['category'], 'claim': hypothesis['label'],
                         'status': 'candidate' if matches else 'unresolved',
                         'evidence_for': supports, 'evidence_against': against,
                         'missing_controls': [check for check in hypothesis['controls'] if states[check] != 'pass']})
    help_candidate = None
    if len(candidates) == 1:
        key = candidates[0]
        help_candidate = {'target': key, 'explanation': bundle['hypotheses'][key]['help'],
                          'student_choices': ['accept', 'adjust', 'later', 'decline'],
                          'verify_with': ['verify-1', 'verify-2'], 'effect': 'pending'}
    next_checks = [] if candidates else [key for key, check in bundle['checks'].items()
        if check['role'] == 'diagnostic' and states[key] in {'not_observed', 'conflicting'}][:1]
    return {'status': 'candidate' if len(candidates) == 1 else 'multiple_candidates' if candidates else 'insufficient',
            'candidate_ids': candidates, 'findings': findings, 'check_states': states, 'next_checks': next_checks,
            'help': help_candidate, 'excluded': excluded, 'independent_activity_count': len(usable),
            'history_event_count': len(events), 'mastery_updated': False, 'diagnosis_confirmed': False}


def help_effect(events, *, help_id, actor='sample-student', course='chain-sample'):
    bundle = build_bundle()
    usable, excluded = _eligible(events, bundle, actor, course, 'verification')
    outcomes = {}
    for event in usable:
        if event.get('help_id') == help_id and event['check_id'] in {'verify-1', 'verify-2'}:
            outcomes.setdefault(event['check_id'], set()).add(event['passed'])
    complete = set(outcomes) == {'verify-1', 'verify-2'} and all(len(values) == 1 for values in outcomes.values())
    status = ('pending' if not complete else 'short_term_independent_pass'
              if all(values == {True} for values in outcomes.values()) else 'no_clear_improvement')
    return {'status': status, 'retention': 'not_observed', 'transfer': 'not_observed',
            'causal_effect_proven': False, 'mastery_updated': False, 'excluded': excluded}
