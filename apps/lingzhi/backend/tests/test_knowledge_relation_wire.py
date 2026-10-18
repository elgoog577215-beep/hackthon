from copy import deepcopy

import pytest

from backend.tests.test_knowledge_tree_relations import compact_pipeline
from course_repository import CourseDocumentConflict


def case():
    pipeline = compact_pipeline(); pipeline['contract'] = 'knowledge_tree_relations_v4'
    a, b = pipeline['catalog'][1:3]
    b['statement'] = '知识2是知识3当前操作的直接基础。'
    response = {'point_reviews': {'P2': '已比较冻结目录。', 'P3': '知识3依赖知识2。'},
        'focus_links': {'P3': [{'p': 'P2', 'd': 'in', 't': 'prerequisite', 'n': 'recommended',
            'c': '当前操作', 'r': '知识3明确以知识2为基础', 'if': [], 'w': 'medium',
            'sn': a['name'], 'tn': b['name'], 'sq': a['statement'], 'tq': b['statement']}]}, 'gaps': []}
    return pipeline, response


def test_new_wire_keeps_complete_reviews_and_accepts_sparse_owned_or_duplicate_pair_transport():
    from knowledge_tree_relations import compile_relations
    pipeline, response = case(); before = deepcopy(response)
    result = compile_relations({'course_id': 'c'}, pipeline, ['P2', 'P3'], response, 'l')
    assert len(result['decisions']) == 2 and len(result['relations']) == 1
    assert result['relations'][0]['source_id'] == 'k2' and result['relations'][0]['target_id'] == 'k3'
    assert response == before
    pipeline['contract'] = 'knowledge_tree_relations_v3'
    with pytest.raises(CourseDocumentConflict): compile_relations({'course_id': 'c'}, pipeline, ['P2', 'P3'], response, 'l')


def test_new_wire_never_infers_missing_point_reviews_or_accepts_unknown_endpoints():
    from knowledge_tree_relations import compile_relations
    pipeline, response = case()
    response['focus_links']['P3'][0]['p'] = 'unknown'
    result = compile_relations({'course_id': 'c'}, pipeline, ['P2', 'P3'], response, 'l')
    assert not result['relations']
    assert result['semantic_rejections'][0]['code'] == 'unknown_endpoint'
    response['point_reviews'].pop('P2')
    with pytest.raises(CourseDocumentConflict): compile_relations({'course_id': 'c'}, pipeline, ['P2', 'P3'], response, 'l')


def test_candidate_selection_binds_direction_and_evidence_before_generation():
    from knowledge_tree_relations import candidate_links, compile_relations
    pipeline, _ = case(); pipeline['wire'] = 'candidate_edges_v1'
    candidates = candidate_links(pipeline, ['P2', 'P3'], 'l')
    identity, candidate = next((k, v) for k, v in candidates.items() if v['source_key'] == 'P2' and v['target_key'] == 'P3')
    assert candidate['focus_key'] == 'P2'
    response = {'point_reviews': {'P2': '知识3明确使用知识2', 'P3': '前一焦点负责该点对'},
        'focus_links': {'P2': [{'e': identity, 't': 'prerequisite', 'n': 'recommended', 'c': '当前操作',
            'r': '知识3以知识2为基础', 'if': [], 'w': 'medium'}]}, 'gaps': []}
    result = compile_relations({'course_id': 'c'}, pipeline, ['P2', 'P3'], response, 'l')
    assert len(result['relations']) == 1
    assert result['relations'][0]['evidence_origin'] == 'program_bound_selected_candidate_statements'
    response['focus_links']['P2'][0]['e'] = 'not-a-frozen-pair'
    rejected = compile_relations({'course_id': 'c'}, pipeline, ['P2', 'P3'], response, 'l')
    assert not rejected['relations'] and rejected['semantic_rejections'][0]['code'] == 'unknown_candidate_pair'
    response['focus_links']['P2'][0].update(e=identity)
    response['focus_links']['P2'][0]['if'] = None
    malformed = compile_relations({'course_id': 'c'}, pipeline, ['P2', 'P3'], response, 'l')
    assert not malformed['relations'] and malformed['semantic_rejections'][0]['code'] == 'invalid_relation_fields'


def test_prebound_candidate_count_replaces_the_old_arbitrary_twelve_edge_limit():
    from knowledge_tree_relations import candidate_links, compile_relations
    source = {'key': 'P1', 'knowledge_id': 'source', 'revision_id': 's1', 'name': '规则', 'statement': '规则的冻结定义。', 'subjects': ['规则'], 'conditions': [], 'lesson_ids': ['l']}
    points = [source, *[{'key': f'P{i}', 'knowledge_id': f't{i}', 'revision_id': f'r{i}', 'name': f'操作{i}',
        'statement': f'操作{i}明确使用规则。', 'subjects': [f'操作{i}'], 'conditions': [], 'lesson_ids': ['l']} for i in range(2, 16)]]
    pipeline = {'contract': 'knowledge_tree_relations_v4', 'wire': 'candidate_edges_v1', 'catalog': points,
        'focus_keys': [p['key'] for p in points], 'baseline_relations': [], 'base_revision': 'frozen'}
    candidates = candidate_links(pipeline, ['P1'], 'l')
    links = [{'e': key, 't': 'prerequisite', 'n': 'recommended', 'c': '当前操作', 'r': f"规则直接用于{row['target_key']}", 'if': [], 'w': 'medium'} for key, row in candidates.items()]
    result = compile_relations({'course_id': 'c'}, pipeline, ['P1'], {'point_reviews': {'P1': '逐项核对冻结候选'}, 'focus_links': {'P1': links}, 'gaps': []}, 'l')
    assert len(result['relations']) == 14
