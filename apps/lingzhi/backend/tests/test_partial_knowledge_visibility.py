from copy import deepcopy

from knowledge_first import knowledge_projection
from course_knowledge_base import build_course_knowledge_library_view


def test_adopted_single_lecture_keeps_bindings_hierarchy_and_empty_lectures():
    tree = {'tree_schema': 'knowledge_first_generic_v1', 'course_id': 'c', 'status': 'accepted', 'revision_id': 'kb',
        'concept_groups': [{'id': 'g', 'concept_group_id': 'g', 'name': '栈', 'parent_id': None},
                           {'id': 'child', 'concept_group_id': 'child', 'name': '规则', 'parent_id': 'g'}],
        'knowledge_points': [{'knowledge_id': 'p', 'revision_id': 'pr', 'name': 'LIFO', 'statement': '规则',
            'primary_concept_group_id': 'child', 'parent_id': 'child', 'section_refs': ['l2'],
            'source_quotes': [{'handout_ref': {'lesson_id': 'l2', 'block_id': 'b', 'script_revision_id': 'h'}}]}],
        'bindings': [], 'relations': []}
    before = deepcopy(tree)
    course = {'course_id': 'c', 'nodes': [{'node_id': f'l{i}', 'node_name': f'第{i}讲', 'node_level': 1} for i in range(1, 4)]}
    result = build_course_knowledge_library_view(knowledge_projection(tree), {}, {}, course)
    nodes = {n['knowledge_id']: n for n in result['nodes']}
    assert nodes['p']['covered_by_course'] is True
    assert nodes['p']['section_ids'] == ['l2']
    assert nodes['p']['block_ids'] == ['b']
    assert nodes['p']['revision_id'] == 'pr'
    assert nodes['child']['parent_id'] == 'g'
    assert nodes['g']['parent_id'] == 'course-path:chapter:l2'
    assert {n['name'] for n in nodes.values() if n['node_type'] == 'chapter'} == {'第1讲', '第2讲', '第3讲'}
    assert tree == before


def test_candidate_does_not_become_a_student_tree():
    tree = {'tree_schema': 'knowledge_first_generic_v1', 'status': 'candidate', 'bindings': [], 'knowledge_points': []}
    assert build_course_knowledge_library_view(knowledge_projection(tree), {}, {}, {})['nodes'] == []
