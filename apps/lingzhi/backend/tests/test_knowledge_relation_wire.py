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
