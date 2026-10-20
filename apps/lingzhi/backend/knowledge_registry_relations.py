"""Relations over explicit knowledge IDs; no lexical or quotation admission gate."""
from copy import deepcopy

from course_document import stable_hash
from knowledge_registry_contract import render
from knowledge_relation_generation import validate_graph
from knowledge_relations import relation_index


def prompt(tree, focus_keys):
    return render(
        '核对冻结知识之间有教学意义的关系，不改写知识。只提出明确成立的先修、推导或应用关系，不能按同一分类强连。'
        '先修prerequisite区分required必要前提与recommended建议先学；推导derives须给至少两步推导；'
        '应用applies_to须说明目标怎样使用源知识。关系双方用目录key，至少一方在focus_keys。'
        'conditions只放额外适用条件，reason解释关系，context说明教学场景。'
        'reviews的键必须恰好等于focus_keys，只处理本批焦点。catalog中的其余知识只供选择关系目标，禁止为它们补写reviews。'
        '每个focus_key给关系取舍理由，可以没有关系；取舍关系不代表删除知识。'
        '输出{"reviews":{"K1":"取舍理由"},"edges":[{"source":"K1","target":"K2","type":"prerequisite",'
        '"necessity":"recommended","reason":"关系理由","context":"教学场景","conditions":[],"steps":[]}]}。'
        '非先修的necessity填null，非推导steps填[]。不要输出引用或其他内容字段。',
        {'stage': 'candidate_relations', 'focus_keys': focus_keys,
         'catalog': [{k: p.get(k) for k in ('key', 'name', 'statement', 'conditions', 'symbol_definitions')}
                     for p in tree['knowledge_points']]})


def compile_edges(value, tree, focus_keys, lesson_id):
    if not isinstance(value, dict) or set(value) != {'reviews', 'edges'}:
        raise ValueError('关系响应只允许reviews和edges')
    reviews, edges = value['reviews'], value['edges']
    if not isinstance(reviews, dict):
        raise ValueError('reviews必须为对象，键只能为：' + ','.join(focus_keys))
    if set(reviews) != set(focus_keys):
        raise ValueError('reviews键不匹配：缺少=' + ','.join(sorted(set(focus_keys)-set(reviews)))
                         + '；多余=' + ','.join(sorted(set(reviews)-set(focus_keys)))
                         + '。只调整本批取舍记录，不修改知识目录。')
    if any(not isinstance(r, str) or not r.strip() for r in reviews.values()):
        raise ValueError('每个焦点必须有非空关系取舍理由')
    if not isinstance(edges, list) or len(edges) > 80:
        raise ValueError('edges必须是最多80项的列表')
    by_key = {p['key']: p for p in tree['knowledge_points']}
    result = []
    for row in edges:
        if not isinstance(row, dict) or set(row) != {'source', 'target', 'type', 'necessity', 'reason', 'context', 'conditions', 'steps'}:
            raise ValueError('关系字段无效')
        a, b, kind = row['source'], row['target'], row['type']
        if a not in by_key or b not in by_key or a == b or not {a, b} & set(focus_keys) or kind not in {'prerequisite', 'derives', 'applies_to'}:
            raise ValueError('关系端点或类型无效')
        if kind == 'prerequisite' and row['necessity'] not in {'required', 'recommended'}:
            raise ValueError('先修关系须区分必要与建议')
        if kind != 'prerequisite' and row['necessity'] is not None:
            raise ValueError('非先修关系不能指定必要性')
        for field in ('conditions', 'steps'):
            if not isinstance(row[field], list) or len(row[field]) > 20 or any(not isinstance(s, str) or not s.strip() for s in row[field]):
                raise ValueError('关系条件或步骤结构无效')
        if kind == 'derives' and len(row['steps']) < 2:
            raise ValueError('推导须提供可检查的步骤')
        if any(not isinstance(row[f], str) or not row[f].strip() for f in ('reason', 'context')):
            raise ValueError('关系理由或场景缺失')
        source, target = by_key[a], by_key[b]
        edge = {'source_id': source['knowledge_id'], 'target_id': target['knowledge_id'],
                'source_knowledge_id': source['knowledge_id'], 'target_knowledge_id': target['knowledge_id'],
                'type': kind, 'relation_type': kind, 'reason': row['reason'], 'context': row['context'],
                'conditions': deepcopy(row['conditions']), 'necessity': row['necessity'],
                'derivation_steps': deepcopy(row['steps']), 'strength': None, 'strength_level': None,
                'confidence': None, 'basis': 'model_proposed_owner_review', 'review_status': 'proposed',
                'source_revision_id': source['revision_id'], 'target_revision_id': target['revision_id'],
                'scope_lesson_id': lesson_id, 'cross_lesson': source.get('section_refs') != target.get('section_refs'),
                'evidence_refs': [{'knowledge_id': p['knowledge_id'], 'revision_id': p['revision_id'],
                                  'quote': p['statement'], 'source_kind': 'frozen_knowledge_statement'}
                                 for p in (source, target)]}
        edge['id'] = edge['relation_id'] = stable_hash(
            {k: edge[k] for k in ('source_id', 'target_id', 'type', 'conditions', 'necessity')}, prefix='kr_')
        result.append(edge)
    return result


def attach(tree, batches):
    result = deepcopy(tree)
    edges = {e['id']: deepcopy(e) for e in tree.get('relations', [])}
    proposed, excluded = [], []
    for batch in batches:
        for edge in batch['result']:
            if edge['id'] in edges:
                continue
            try:
                validate_graph(tree['knowledge_points'], [*edges.values(), edge])
            except Exception as error:
                from course_repository import CourseDocumentConflict
                if not isinstance(error, CourseDocumentConflict):
                    raise
                excluded.append({'relation_id': edge['id'], 'reason': str(error)})
            else:
                edges[edge['id']] = edge
                proposed.append(edge['id'])
    result['relations'] = list(edges.values())
    result['relation_index'] = relation_index(result)
    result['relation_assessment'] = {'schema_version': 'knowledge_registry_relations_v1',
        'mode': 'with_tree', 'ready_for_adoption': True, 'semantics_verified': False,
        'proposed_ids': proposed, 'proposed_count': len(proposed),
        'checked_points': sum(len(b['focus_keys']) for b in batches),
        'gaps': [e['reason'] for e in excluded], 'excluded_relations': excluded}
    result['atomic_assessment']['relation_status'] = 'completed'
    return result
