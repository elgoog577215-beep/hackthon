"""Pure legacy extraction compilation, without semantic dispatch backedges."""
from copy import deepcopy
import re
from generic_knowledge import require,sources
from knowledge_compact import passage_catalog, PASSAGES, LEAVES
from knowledge_extract_contract import LEGACY_CONTRACT, FOCUS_CONTRACT, COMPLETE_CONTRACT, LITERAL_CONTRACT, PARTS_CONTRACT, SEMANTIC_CONTRACT, WIRE_CONTRACT, SCALAR_CONTRACT, CONTRACT, CONTRACTS, focus_options, focus_choices

def compile_extraction(raw, context, keys, index, response):
    from knowledge_atomic_compile import compile_inventory, compile_batch
    from knowledge_compact import source_issues
    require(isinstance(response, dict) and response.get('response_contract') in CONTRACTS, '直接提取合同无效')
    complete_question = response['response_contract'] in {LITERAL_CONTRACT, COMPLETE_CONTRACT}
    bound_focus = response['response_contract'] in {FOCUS_CONTRACT, COMPLETE_CONTRACT}
    require(response['response_contract'] == LEGACY_CONTRACT or 'passages' in response, '原文对象绑定需要逐片段响应')
    catalog = {p['key']: p for p in passage_catalog(context, keys)}
    if 'passages' in response:
        passages = response['passages']
        require(isinstance(passages, dict) and set(passages) == {p['key'] for p in passage_catalog(context, keys)}, '原文片段去向必须完整列出')
        points, unassigned = [], []
        for passage_key, passage in passages.items():
            require(isinstance(passage, dict) and isinstance(passage.get('points'), list), '片段知识结构无效')
            entries, note = passage['points'], passage.get('note')
            require((bool(entries) and note is None) or (not entries and isinstance(note, dict)), '每段必须提取知识或明确标注去向')
            if note is not None:
                unassigned.append({'passage_key': passage_key, **note})
            for entry in entries:
                require(isinstance(entry, dict), '提取知识点结构无效')
                point = deepcopy(entry)
                if bound_focus:
                    options = focus_options(catalog[passage_key]['text'])
                    require(point.get('focus_key') in options and 'focus_term' not in point, '原文对象短键无效或不属于当前片段')
                    point['focus_term'] = options[point.pop('focus_key')]
                if response['response_contract'] in {PARTS_CONTRACT, LITERAL_CONTRACT}:
                    require(point.get('focus_term') in focus_choices(catalog[passage_key]['text']) and 'focus_key' not in point,
                        '原文对象必须从当前片段逐字选择，不得改写')
                if complete_question:
                    require(isinstance(point.get('question'), str) and point['question'].strip()
                        and not {'question_before', 'question_after'} & set(point), '元问题必须完整生成，不得自动拼接对象')
                point['source_passage_keys'] = [passage_key]
                require(isinstance(point.get('attachments', []), list), '附件结构无效')
                for attachment in point.get('attachments', []):
                    require(isinstance(attachment, dict), '附件结构无效')
                    attachment['source_passage_keys'] = [passage_key]
                points.append(point)
        response = {**response, 'points': points, 'unassigned_passages': unassigned}
    if 'passage_notes' in response:
        notes = response['passage_notes']
        require(isinstance(notes, dict) and set(notes) == {p['key'] for p in passage_catalog(context, keys)}, '原文片段去向必须完整列出')
        require(all(n is None or isinstance(n, dict) for n in notes.values()), '片段去向结构无效')
        response = {**response, 'unassigned_passages': [{'passage_key': key, **note} for key, note in notes.items() if note is not None]}
    points = response.get('points')
    require(isinstance(points, list) and all(isinstance(p, dict) for p in points), '提取知识点结构无效')
    inventory, leaves = [], []
    for i, point in enumerate(points, 1):
        key = f'P{i}'; attachments = []
        require(point.get('kind') in {'definition', 'rule', 'method', 'comparison'}, '案例与条件不能成为知识叶子')
        question = point.get('question')
        if 'question_after' in point or 'question_before' in point:
            before, after, focus = point.get('question_before'), point.get('question_after'), point.get('focus_term')
            require(isinstance(before, str) and len(before) <= 120 and isinstance(after, str) and 3 <= len(after.strip()) <= 200
                    and isinstance(focus, str) and focus.strip(), '元问题必须引用原文检查对象并提出完整问题')
            question = before + focus + after
        inventory.append({**{k: point.get(k) for k in ('name', 'kind', 'claim', 'conditions', 'source_passage_keys')},
                          'key': key, 'focus_terms': [point.get('focus_term')]})
        for j, item in enumerate(point.get('attachments', []), 1):
            require(item.get('kind') in {'condition', 'boundary', 'example'}, '附件类型无效')
            attachment_key = f'{key}A{j}'; attachments.append(f'I{index}_{attachment_key}')
            inventory.append({**deepcopy(item), 'key': attachment_key, 'conditions': [], 'focus_terms': [item.get('name')]})
        leaves.append({'inventory_key': f'I{index}_{key}', 'attachment_keys': attachments, 'category_key': 'C1',
            'name': point.get('name'), 'claims': [point.get('claim')], 'meta_question': question,
            'meta_answer': point.get('claim'), 'extraction_method': 'summary', 'derivation_note': ''})
    value = {**deepcopy(response), 'response_contract': PASSAGES, 'items': inventory}
    items, coverage = compile_inventory(value, context, keys, index)
    tree = report = None
    if points:
        tree, report = compile_batch(raw, context, items, {'response_contract': LEAVES,
            'categories': [{'key': 'C1', 'name': context['handout_lessons'][0]['title'], 'parent_key': None}],
            'points': leaves, 'context_items': [], 'gaps': [],
            '_format_normalizations': response.get('_format_normalizations', [])})
        if complete_question or response['response_contract'] == PARTS_CONTRACT:
            for index, point in enumerate(points, 1):
                claim = point.get('claim', '')
                if re.search(r'^(?:本讲|本课|本课程|本节).{0,15}(?:目标|范围)|^(?:能(?:够)?|需要|要求|应当能|学生应)(?:画出|指出|解释|描述|判断|理解|掌握|学会|完成|分析)', claim):
                    report['issues'].append({'code': 'nonknowledge_leaf', 'severity': 'blocking', 'point_key': f'K{index}'})
                    report['ready_for_adoption'] = False
    return {'items': items, 'source_coverage': coverage, 'tree': tree, 'report': report,
        'source_issues': source_issues(value, sources(context), keys, context),
        'format_normalizations': response.get('_format_normalizations', [])}
