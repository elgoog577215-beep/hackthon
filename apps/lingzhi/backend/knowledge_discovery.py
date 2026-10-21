"""Discover complete claims directly from small, unabridged material batches.

Material keys describe what a request read, never lexical evidence requirements.
The initial claim ledger survives identity decisions without an intermediate
whole-lesson summary or a second expansion of that summary.
"""
from copy import deepcopy

from knowledge_registry_contract import FIELDS, render, validate_point

CONTRACT = 'knowledge_discovery_v1'


def material_batches(materials):
    return [
        {'id': f'inventory-{i // 2 + 1}',
         'source_keys': [m['key'] for m in materials[i:i + 2]], 'status': 'pending'}
        for i in range(0, len(materials), 2)
    ]


def discovery_prompt(raw, lesson_title, materials, focus):
    return render(
        '直接阅读本批完整教学材料，发现可独立讲解、检查和补学的完整知识。不要先概括本讲，也不要按标题只选代表性知识。'
        '逐句辨别其中的独立定义、关系、规律、表示方法与特殊情况；一个段落可以包含多个独立知识。'
        '将“学生能掌握前一条但不会后一条”的不同结论分别写出。对象的定义、量之间的关系、对象的方程各自完整时分别保留。'
        '完整公式内部的因子与符号不能拆成叶子；适用条件放conditions，不单独复制成条件叶子。'
        '同一规律的口头解释、公式和换记号只算一个知识，统一放在同一statement里。'
        '具体题目的代入步骤和答案放examples；一般方法须能够迁移到另一道题，不用算例答案冒充一般知识。'
        '操作失误放check_intents，指出需要检查的具体表现，不写学生已犯错或已掌握。'
        '完整保留规则及必要限定；conditions只放真实适用条件，symbol_definitions只放符号含义，teaching_context只放使用情境。'
        '注意充分与必要条件的区别，不把示例中的现象升级为普遍断言；可以纠正材料表述并补足必要背景，不要求原文逐字匹配。'
        '不要为填满类型而创造“某某法则是用来做某某运算的”等空泛叶子。数量取决于独立知识，不设最低个数。'
        'profile_focus只从teaching_focus选择最贴合的一项，其余填空字符串。branch是主题标签，不是知识名称。'
        '输出{"points":[{"statement":"完整知识陈述","knowledge_type":"rule","conditions":[],'
        '"symbol_definitions":[],"teaching_context":[],"examples":[],"branch":"主题",'
        '"profile_focus":"","check_intents":["可观察的检查目标"]}],"context_note":""}。'
        'knowledge_type仅为definition/rule/method/comparison。纯课堂安排等无独立知识时points可为空，context_note须说明原因。',
        {'stage': 'knowledge_discovery', 'contract': CONTRACT,
         'course_title': raw.get('course_name', ''), 'lesson_title': lesson_title,
         'materials': materials, 'teaching_focus': focus})


def parse_discovery(value, batch_id, source_keys, focus):
    if not isinstance(value, dict) or set(value) != {'points', 'context_note'}:
        raise ValueError('发现响应仅允许points与context_note')
    rows, note = value['points'], value['context_note']
    if not isinstance(rows, list) or len(rows) > 80 or not isinstance(note, str):
        raise ValueError('发现结果必须为知识列表与背景说明')
    if not rows and not note.strip():
        raise ValueError('无独立知识时须说明背景或教学安排')
    result = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict) or set(row) != set(FIELDS) | {'branch', 'profile_focus', 'check_intents'}:
            raise ValueError('发现知识的字段不完整')
        if not isinstance(row['branch'], str) or not row['branch'].strip() or len(row['branch']) > 200:
            raise ValueError('知识主题为空或过长')
        if row['profile_focus'] not in ['', *focus]:
            raise ValueError('教学档案分支必须来自指定列表')
        checks = row['check_intents']
        if not isinstance(checks, list) or not 1 <= len(checks) <= 12 or any(
                not isinstance(c, str) or not c.strip() or len(c) > 1200 for c in checks):
            raise ValueError('完整知识须有可观察的检查目标')
        key = f'{batch_id}P{index}'
        result.append({
            **validate_point({k: row[k] for k in FIELDS}), 'key': key,
            'coverage_unit_ids': [key], 'branch': row['branch'],
            'profile_focus': row['profile_focus'], 'check_intents': deepcopy(checks),
            'input_material_keys': list(source_keys),
        })
    return result


def discovered_units(points):
    return [
        {'key': p['coverage_unit_ids'][0], 'statement': p['statement'],
         'branch': p['branch'], 'knowledge_type': p['knowledge_type'],
         'profile_focus': p['profile_focus'], 'check_intent': '；'.join(p['check_intents'])}
        for p in points
    ]


def coverage_inputs(batches):
    """Keep classified examples in the ledger even before semantic review."""
    points = [p for batch in batches for p in batch.get('points', [])]
    resolutions = []
    for batch in batches:
        originals = {p['key']: p for p in batch.get('discovery_points', [])}
        for group in batch.get('atomization_batches', []):
            if group.get('status') != 'completed':
                continue
            items = group.get('request', {}).get('response', {}).get('items', {})
            for key in group['keys']:
                row = items.get(key, {})
                if row.get('disposition') in {'example', 'context'}:
                    original = originals[key]
                    resolutions.append({'candidate_key':key,'coverage_unit_ids':deepcopy(original['coverage_unit_ids']),
                        'disposition':row['disposition'],'reason':row['reason'],'original':deepcopy(original)})
                    points.append(original)
    return discovered_units(points), resolutions


def atomization_prompt(points):
    if len(points) != 1:
        raise ValueError('每次只拆分一个完整候选，不能再次概括一组知识')
    return render(
        '直接列出每个候选中可分别讲解、检查和补学的最小完整知识，不重新概括本讲，不按主题合并不同候选。'
        '对象定义、数量关系、表示方程是不同结论；不同对象的定义分别列出。'
        '联合公式若只是几个可独立使用性质的缩写，分别表达这些性质；若删除一部分会破坏同一规律，则保留完整公式。'
        '不是每个词或操作步骤都成为知识。必要前提附在对应结论里；同一结论的公式、口头表述、换记号、逆否命题合在同一点。'
        '多个检查角度本身不构成多条知识。能会前一结论而不会后一结论、且两者能分别完整讲解时，必须分为两个知识。'
        '不能用教材通常合讲、计算中经常连用或方便记忆来保留多个结论的总括式。'
        '例如映射保持加法与保持数乘是两条可独立使用的性质，虽然可合写为一个线性组合式，仍分别表达；'
        '圆面积与圆周长应分开，同一面积规则的文字说明与公式合并。'
        '不要把“知道某法则的名字或用途”另列成空泛定义。纯算例答案归example，纯课堂安排归context，不生成叶子。'
        '补全缺少的必要条件，区分必要与充分条件，修正过强的普遍断言。数学公式使用标准LaTeX分隔符。'
        '对每个候选key返回一个items条目。disposition为knowledge/example/context。'
        'knowledge的points至少一条；example/context的points为空；reason用一句话说明分别检查的依据或为什么不是独立知识，不写推敲过程。'
        '输出{"items":{"候选key":{"disposition":"knowledge","reason":"拆分或保持完整的理由","points":['
        '{"statement":"单条完整知识","knowledge_type":"rule","conditions":[],'
        '"check_intents":["可观察检查目标"]}]}}}。'
        'knowledge_type只允许definition/rule/method/comparison。check_intents用陈述表达，不写学生已犯错。',
        {'stage': 'knowledge_atomize', 'contract': CONTRACT,
         'candidates': [{k: p.get(k) for k in ('key', *FIELDS, 'check_intents')} for p in points]})


def parse_atoms(value, originals):
    items = value.get('items') if isinstance(value, dict) else None
    if not isinstance(items, dict) or set(items) != {p['key'] for p in originals}:
        raise ValueError('逐点拆分须完整处理本批候选ID，不能遗漏或新增原ID')
    result = []
    for original in originals:
        record = items[original['key']]
        if not isinstance(record, dict) or set(record) != {'disposition', 'reason', 'points'}:
            raise ValueError('逐点拆分须给出处理类型、理由与完整知识列表')
        if not isinstance(record['reason'], str) or not record['reason'].strip():
            raise ValueError('逐点拆分须说明独立检查或保持完整的理由')
        disposition, rows = record['disposition'], record['points']
        if not isinstance(rows, list) or len(rows) > 12:
            raise ValueError('每个候选须返回最多12条完整知识')
        if disposition in {'example', 'context'} and not rows:
            continue
        if disposition != 'knowledge' or not rows:
            raise ValueError('独立知识不能返回空列表，算例或背景不能夹带知识')
        for index, row in enumerate(rows, 1):
            if not isinstance(row, dict) or set(row) != {'statement','knowledge_type','conditions','check_intents'}:
                raise ValueError('拆分后的完整知识字段无效')
            parsed = parse_discovery(
                {'points': [{**{k:deepcopy(original[k]) for k in ('symbol_definitions','teaching_context','examples')},
                             **row, 'branch': original['branch'],
                             'profile_focus': original['profile_focus']}], 'context_note': ''},
                f"{original['key']}A{index}", original['input_material_keys'],
                [original['profile_focus']] if original['profile_focus'] else [])
            parsed[0].update(discovery_parent_key=original['key'], split_reason=record['reason'])
            result.extend(parsed)
    return result
