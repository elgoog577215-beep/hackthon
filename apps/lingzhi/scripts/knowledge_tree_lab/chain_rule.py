"""Finite, authored chain-rule evidence lab; no runtime persistence or diagnosis.

The patterns distinguish stipulated examples, not validated learner traits.
Unknown free text is ungraded. No score or mastery record is written.
"""
from .pipeline import digest


def build_bundle():
    knowledge = [
        {'id': 'K-COMP', 'name': '复合函数：先算里面，再算外面', 'claim': '先算出g(x)，再把这个结果放进f，就得到f(g(x))。例如sin(x²)要先平方，再取正弦。',
         'conditions': ['x在g的定义域且g(x)在f的定义域'], 'prerequisites': []},
        {'id': 'K-POWER', 'name': 'x²、x³这类函数怎样求导', 'claim': '求导时，先把原来的指数乘到前面，再把指数减1。例如(x²)′=2x、(x³)′=3x²；一般写成(x^n)′=n*x^(n-1)。',
         'conditions': ['自变量x为实数；n为固定正整数'], 'prerequisites': []},
        {'id': 'K-SIN', 'name': 'sin 的导数', 'claim': '(sin u)′=cos u。',
         'conditions': ['对实变量u求导，角度采用弧度'], 'prerequisites': []},
        {'id': 'K-COS', 'name': 'cos 的导数', 'claim': '(cos u)′=-sin u。',
         'conditions': ['对实变量u求导，角度采用弧度'], 'prerequisites': []},
        {'id': 'K-CHAIN', 'name': '链式法则：别漏乘里面的导数', 'claim': '函数一层套一层时，先对外面求导，里面的式子先保留，再乘上里面的导数。在x0处写成公式就是(f(g(x)))′(x0)=f′(g(x0))*g′(x0)。',
         'conditions': ['x0为被求导的实数点', 'g在x0可导', 'f在g(x0)可导', '复合在x0邻域内有定义'],
         'prerequisites': ['K-COMP']},
    ]
    checks = {}

    def check(key, prompt, answers, wrong, knowledge_ids, dimension, context, role='diagnostic'):
        checks[key] = {'check_id': key, 'prompt': prompt, 'accepted_answers': answers,
                       'wrong_answers': wrong, 'knowledge_ids': knowledge_ids,
                       'dimension': dimension, 'context': context, 'role': role}

    check('trigger', '试着求 sin(x²) 的导数。', ['2*x*cos(x^2)'], ['cos(x^2)'],
          ['K-COMP', 'K-POWER', 'K-SIN', 'K-CHAIN'], '综合表现', '共同错题', 'symptom')
    check('structure-1', '先不求导。sin(x²)要先算里面、再算外面。外面是sin(u)，里面的u是什么？请按这个顺序写出来。',
          ['内层x^2，外层sin(u)'], ['内层sin(x)，外层u^2'], ['K-COMP'], '看清里面和外面', '先不求导，认一认')
    check('structure-2', '先不求导。计算(3x+1)²时，先算哪一部分，再做平方？用u表示先算出的结果，写出这两步。',
          ['u=3x+1，y=u^2'], ['u=x^2，y=3u+1'], ['K-COMP'], '看清里面和外面', '换个式子认一认')
    check('power-1', '先单独做这一小步：x²的导数是多少？', ['2*x'], ['x', '2'], ['K-POWER'], '基础求导', '平方')
    check('power-2', '再试一个：x³的导数是多少？', ['3*x^2'], ['x^2', '3*x'], ['K-POWER'], '基础求导', '立方')
    check('trig-1', '先只看sin(u)：它对u的导数是什么？这里的角度都用弧度。', ['cos(u)'], ['sin(u)'],
          ['K-SIN'], '基础求导', '正弦')
    check('trig-2', '再看cos(u)：它对u的导数是什么？这里的角度都用弧度。', ['-sin(u)'], ['sin(u)'],
          ['K-COS'], '基础求导', '余弦')
    check('arithmetic', '先算一道乘法：3 × 5等于多少？', ['15'], ['5', '8'], [], '先算一道乘法', '先不管函数')
    check('evaluation-1', "有一个函数y=f(g(x))。已知g(1)=9、g'(1)=3、f'(9)=7、f'(1)=2。这里可以用链式法则。当x=1时，y的导数是多少？",
          ['21'], ['6'], ['K-CHAIN'], '外面要代哪个数', '需要的导数已经给出')
    check('evaluation-2', "还是y=f(g(x))。这次已知g(2)=4、g'(2)=2、f'(4)=5、f'(2)=11。这里可以用链式法则。当x=2时，y的导数是多少？",
          ['10'], ['22'], ['K-CHAIN'], '外面要代哪个数', '换一组已知的数')
    check('combination-1', "要求y=f(g(x))在x0处的导数。已经算出f'(g(x0))=5、g'(x0)=3，而且可以用链式法则。你最后会怎样写？请写完整算式，不用算出结果；如果只写一个数，请说说另一个数要不要用上。",
          ['5*3', '3*5'], ['我认为最终式子就是5，不需要其他因子'], ['K-CHAIN'], '两部分怎样合起来', '两部分的导数已经给出')
    check('combination-2', "再试一次：要求y=f(g(x))在x0处的导数，已知f'(g(x0))=2、g'(x0)=4，而且可以用链式法则。请写最后的完整算式，不用算出结果；如果只写一个数，请说说另一个数要不要用上。",
          ['2*4', '4*2'], ['我认为最终式子就是2，不需要其他因子'], ['K-CHAIN'], '两部分怎样合起来', '换一组已知的导数')
    check('familiar-1', '对sin(2x)求导。', ['2*cos(2*x)'], ['cos(2*x)'],
          ['K-SIN', 'K-CHAIN'], '用熟悉的函数试一试', '平常见过的写法')
    check('familiar-2', '对cos(3x)求导。', ['-3*sin(3*x)'], ['-sin(3*x)'],
          ['K-COS', 'K-CHAIN'], '用熟悉的函数试一试', '另一种熟悉的写法')
    check('transfer-1', "F和sin一样，都是函数的名字。已知F'(u)=2u，里面的3x+1的导数是3。请对F(3x+1)求导；这里可以用链式法则。",
          ['6*(3*x+1)'], ['2*(3*x+1)'], ['K-CHAIN'], '换个函数名字试一试', 'F是函数的名字，导数已经给出')
    check('transfer-2', "这次把函数名字换成A。已知A'(z)=cos(z)，里面的2t的导数是2。请对A(2t)求导；这里可以用链式法则。",
          ['2*cos(2*t)'], ['cos(2*t)'], ['K-CHAIN'], '换个函数名字试一试', '换个函数名和字母')
    verification = {
        'structure': [
            ('先不求导。看√(1+x²)：用u表示根号里的整块，再写y=√u。请把先算u、再算y的两步写出来。', 'u=1+x^2，y=sqrt(u)', 'u=sqrt(x)，y=1+u^2', ['K-COMP']),
            ('先不求导。看sin(4x−1)：外面是sin(u)，里面的u是什么？请把先算u、再算y的两步写出来。', 'u=4x-1，y=sin(u)', 'u=sin(x)，y=4u-1', ['K-COMP'])],
        'power': [('求x^4对x的导数。', '4*x^3', 'x^3', ['K-POWER']), ('求x^5对x的导数。', '5*x^4', 'x^4', ['K-POWER'])],
        'trig': [('求sin(v)对v的导数，采用弧度。', 'cos(v)', 'sin(v)', ['K-SIN']), ('求cos(v)对v的导数，采用弧度。', '-sin(v)', 'sin(v)', ['K-COS'])],
        'evaluation': [
            ("有函数y=f(g(x))。已知g(0)=2、g'(0)=4、f'(2)=3、f'(0)=5。这里可以用链式法则。请算出x=0时y的导数。", '12', '20', ['K-CHAIN']),
            ("再试一题y=f(g(x))。已知g(3)=1、g'(3)=5、f'(1)=4、f'(3)=7。这里可以用链式法则。请算出x=3时y的导数。", '20', '35', ['K-CHAIN'])],
        'combination': [
            ("要求y=f(g(x))在x0处的导数。已知f'(g(x0))=7、g'(x0)=2，而且可以用链式法则。请写最后的完整算式，不用算出结果。", '7*2', '我认为最终式子就是7，不需要其他因子', ['K-CHAIN']),
            ("再试一次：要求y=f(g(x))在x0处的导数，已知f'(g(x0))=3、g'(x0)=6，而且可以用链式法则。请写最后的完整算式，不用算出结果。", '3*6', '我认为最终式子就是3，不需要其他因子', ['K-CHAIN'])],
        'transfer': [
            ("D是一个函数的名字。已知D'(u)=3u²，里面的2s−1的导数是2。请对D(2s−1)求导；这里可以用链式法则。", '6*(2*s-1)^2', '3*(2*s-1)^2', ['K-CHAIN']),
            ("H是一个函数的名字。已知H'(v)=−sin(v)，里面的4s的导数是4。请对H(4s)求导；这里可以用链式法则。", '-4*sin(4*s)', '-sin(4*s)', ['K-CHAIN'])],
    }
    verify_keys = {}
    for target, tasks in verification.items():
        verify_keys[target] = []
        for index, (prompt, answer, wrong, refs) in enumerate(tasks, 1):
            key = f'verify-{index}' if target == 'combination' else f'verify-{target}-{index}'
            check(key, prompt, [answer], [wrong], refs, '换一道题自己试试', '这道题还没有看过答案', 'verification')
            checks[key]['verification_target'] = target
            verify_keys[target].append(key)
    components = ['structure-1', 'structure-2', 'power-1', 'power-2', 'trig-1', 'trig-2',
                  'arithmetic', 'evaluation-1', 'evaluation-2']
    rules = {
        'structure': ('先看看里面和外面的函数有没有分清', ['K-COMP'], 'concept_gap', ['structure-1', 'structure-2'], [],
                      '先不求导。看sin(x²)：先把x平方，再把得到的数放进sin。先用这种两步写法，把里面和外面的函数分清。'),
        'power': ('先练x²、x³这些基本求导', ['K-POWER'], 'concept_gap', ['power-1', 'power-2'], [],
                  '先练平方和立方：x²的导数是2x，x³的导数是3x²。注意先把原来的指数乘到前面，再把指数减1。'),
        'trig': ('先熟悉sin、cos的导数', ['K-SIN', 'K-COS'], 'concept_gap', ['trig-1', 'trig-2'], [],
                 '先把这两条分开记：sin x的导数是cos x；cos x的导数是−sin x。第二条前面的负号别漏掉。这里的角度用弧度。'),
        'evaluation': ('再看看外面要代哪个数', ['K-CHAIN'], 'boundary_confusion',
                       ['evaluation-1', 'evaluation-2'], ['structure-1', 'structure-2', 'arithmetic'],
                       '外面的函数要用里面算出的结果。例如y=f(g(x))，在x=1时，如果g(1)=9，就要看f在9处的导数f′(9)，而不是直接看f′(1)。'),
        'combination': ('再练一步：乘上里面的导数', ['K-CHAIN'], 'process_error',
                        ['combination-1', 'combination-2'], components,
                        '对sin(x²)求导时，先得到外面的cos(x²)，再乘里面x²的导数2x。所以要写成cos(x²) × 2x；里面这一步不能漏。'),
        'transfer': ('换个函数名字，再试一试', ['K-CHAIN'], 'transfer_gap',
                     ['transfer-1', 'transfer-2'], [*components, 'combination-1', 'combination-2', 'familiar-1', 'familiar-2'],
                     'F只是函数的名字，和sin一样。看到F(3x+1)，先把3x+1当作一整块：先对外面的F求导，再乘里面的导数。换个函数名字，做法仍然一样。'),
    }
    hypotheses = {key: {'hypothesis_id': key, 'label': label, 'knowledge_ids': refs, 'category': category,
                        'fail_checks': fails, 'controls': controls, 'help': explanation, 'verify_checks': verify_keys[key]}
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
                          'verify_with': list(bundle['hypotheses'][key]['verify_checks']), 'effect': 'pending'}
    next_checks = [] if candidates else [key for key, check in bundle['checks'].items()
        if check['role'] == 'diagnostic' and states[key] in {'not_observed', 'conflicting'}][:1]
    return {'status': 'candidate' if len(candidates) == 1 else 'multiple_candidates' if candidates else 'insufficient',
            'candidate_ids': candidates, 'findings': findings, 'check_states': states, 'next_checks': next_checks,
            'help': help_candidate, 'excluded': excluded, 'independent_activity_count': len(usable),
            'history_event_count': len(events), 'mastery_updated': False, 'diagnosis_confirmed': False}


def help_effect(events, *, help_id, target='combination', actor='sample-student', course='chain-sample'):
    bundle = build_bundle()
    usable, excluded = _eligible(events, bundle, actor, course, 'verification')
    expected = set(bundle['hypotheses'][target]['verify_checks'])
    outcomes = {}
    for event in usable:
        if event.get('help_id') == help_id and event['check_id'] in expected:
            outcomes.setdefault(event['check_id'], set()).add(event['passed'])
    complete = set(outcomes) == expected and all(len(values) == 1 for values in outcomes.values())
    status = ('pending' if not complete else 'short_term_independent_pass'
              if all(values == {True} for values in outcomes.values()) else 'no_clear_improvement')
    return {'status': status, 'retention': 'not_observed', 'transfer': 'not_observed',
            'causal_effect_proven': False, 'mastery_updated': False, 'excluded': excluded}
