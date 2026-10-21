"""Bounded, recorded content normalization before immutable identity matching.

The compiler checks scope and obligations, not subject words or source wording.
Model judgments remain reviewable teaching drafts, never certified truth.
"""
from copy import deepcopy

from knowledge_registry_contract import FIELDS, render, validate_point

CONTRACT = 'knowledge_semantic_review_v1'


def review_prompt(points):
    return render(
        '核对这些候选的知识正确性和独立结论，不做去重、不写名称。不要沿用前一步对粒度或正确性的自评。'
        '先尝试构造满足前提但不满足结论的反例，检查量词、指定位置、边界、定义域、必要与充分及符号含义。'
        'challenge描述实际检验的具体情形、结果和理由，不以“已核对”“符合教材”代替检验。'
        '若找到反例，result=refuted，随后在conclusions给出准确修正，不能原样保留已被推翻的结论。'
        '不能确认时disposition=uncertain、result=inconclusive、conclusions=[]，保留待核对，不能强行通过。'
        '知识粒度按独立结论确定，不按教材常合讲或一个总括公式确定。'
        '逐条列出可分别成立、讲解和检查的结论，每个conclusions条目只含一个知识核和一个独立check。'
        '对象定义、量之间的关系、对象的表示方程分别列出；合写多个独立运算性质时分别表达。'
        '能会一个结论而不会另一个结论，即使两者常常连用，也不能留在一个条目。'
        '同一规律的因子、符号、必要条件、换记号和具体代入不能拆成新知识；完整联合定义或不可分的规律保持完整。'
        '每条保留自己的适用条件，符号说明、例子及教学情境分别处理，不能继承不适用的例子或结论。'
        '具体计算答案归example，纯课堂安排归context，两者conclusions=[]并说明理由，不伪造知识叶子。'
        '若例题同时包含可迁移的一般方法，保留方法知识，具体代入放该知识的examples。'
        'disposition仅knowledge/example/context/uncertain。knowledge至少一个conclusions条目；其他类型为空。'
        'result仅consistent/refuted/inconclusive；consistent只表示本轮检验未发现反例，不是学科认证。'
        '每个候选key必须有一个reviews条目，不得删除或新增原key。输出'
        '{"reviews":{"候选key":{"disposition":"knowledge","reason":"核对与拆分理由",'
        '"challenge":{"case":"具体检验情形","result":"consistent","explanation":"前提与结论比较"},'
        '"conclusions":[{"statement":"单条完整知识","knowledge_type":"rule","conditions":[],"symbol_definitions":[],"teaching_context":[],"examples":[],"check":"单独检查该结论的可观察表现"}]}}}。',
        {'stage': 'candidate_semantic_review', 'contract': CONTRACT,
         'points': [{k: p.get(k) for k in ('key', *FIELDS, 'check_intents')} for p in points]})


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 2400


def compile_reviews(value, originals):
    reviews = value.get('reviews') if isinstance(value, dict) and set(value) == {'reviews'} else None
    if not isinstance(reviews, dict) or set(reviews) != {p['key'] for p in originals}:
        raise ValueError('内容核对须恰好处理本批全部候选')
    result = {'points': [], 'resolutions': [], 'issues': [], 'reviews': []}
    for original in originals:
        key = original['key']; row = reviews[key]
        if not isinstance(row, dict) or set(row) != {'disposition', 'reason', 'challenge', 'conclusions'} or not _text(row['reason']):
            raise ValueError(key + '：内容核对字段或理由不完整')
        challenge = row['challenge']; disposition = row['disposition']; conclusions = row['conclusions']
        if (not isinstance(challenge, dict) or set(challenge) != {'case', 'result', 'explanation'}
                or not _text(challenge['case']) or not _text(challenge['explanation'])
                or challenge['result'] not in {'consistent', 'refuted', 'inconclusive'}):
            raise ValueError(key + '：须给出具体反例或边界检验')
        if not isinstance(conclusions, list) or len(conclusions) > 12:
            raise ValueError(key + '：独立结论数量无效')
        if disposition not in {'knowledge', 'example', 'context', 'uncertain'}:
            raise ValueError(key + '：未知内容去向')
        result['reviews'].append({'candidate_key': key, 'original': deepcopy(original), **deepcopy(row)})
        certificate = {'contract': CONTRACT, 'independence_group': key, 'reason': row['reason'],
                       'challenge': deepcopy(challenge), 'model_reviewed': True, 'semantics_verified': False}
        if disposition != 'knowledge':
            if conclusions:
                raise ValueError(key + '：例题、背景和待核对不能夹带确认结论')
            if disposition == 'uncertain':
                point = deepcopy(original)
                point.update(semantic_review=certificate, review_pending=True)
                result['points'].append(point)
                result['issues'].append({'code': 'knowledge_semantics_pending', 'severity': 'blocking',
                                         'point_key': key, 'message': row['reason']})
            else:
                result['resolutions'].append({'candidate_key': key, 'coverage_unit_ids': deepcopy(original.get('coverage_unit_ids', [])),
                    'disposition': disposition, 'reason': row['reason'], 'original': deepcopy(original), 'challenge': deepcopy(challenge)})
            continue
        if not conclusions or challenge['result'] == 'inconclusive':
            raise ValueError(key + '：未确定的知识不能通过内容核对')
        parsed = []
        for index, conclusion in enumerate(conclusions, 1):
            if not isinstance(conclusion, dict) or set(conclusion) != {*FIELDS, 'check'} or not _text(conclusion['check']):
                raise ValueError(key + '：每条独立结论须有完整知识和独立检查')
            facts = validate_point({field: conclusion[field] for field in FIELDS})
            point = {**deepcopy(original), **facts,
                'key': key if len(conclusions) == 1 else f'{key}R{index}',
                'check_intents': [conclusion['check']], 'semantic_review': deepcopy(certificate)}
            point.pop('review_pending', None)
            parsed.append(point)
        if (challenge['result'] == 'refuted' and len(parsed) == 1
                and all(parsed[0][field] == original[field] for field in FIELDS)):
            raise ValueError(key + '：无效修正，反例已推翻的知识不能原样通过')
        result['points'].extend(parsed)
    return result
