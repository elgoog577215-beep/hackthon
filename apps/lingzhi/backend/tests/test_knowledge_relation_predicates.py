from knowledge_tree_relations import candidate_links


def node(key, subject, prop, value, form='fact', **extra):
    return {'key': key, 'knowledge_id': key, 'revision_id': 'r'+key, 'name': subject+'的'+prop,
        'statement': subject+'的'+prop+'为'+value+'。', 'conditions': [], 'subjects': [subject],
        'lesson_ids': ['l'], 'form': form, 'property': prop, 'value': value, **extra}


def candidates(source, target):
    return candidate_links({'contract': 'knowledge_tree_relations_v4', 'wire': 'candidate_edges_v2',
        'catalog': [source, target], 'focus_keys': ['P1', 'P2']}, ['P1', 'P2'], 'l')


def test_emptiness_is_not_a_necessary_prerequisite_for_push_or_fifo():
    empty = node('P1', '栈', '判空检查对象', '栈是否为空')
    assert not candidates(empty, node('P2', '入栈', '操作效果', '将元素插入栈顶'))
    assert not candidates(node('P1', '队列', '判空检查对象', '队列是否为空'), node('P2', '队列', '核心特征', 'FIFO'))


def test_physical_representation_does_not_determine_unrelated_logical_properties():
    physical = node('P1', '栈', '物理实现形式', '数组或链表')
    assert not candidates(physical, node('P2', '栈', '核心特征', 'LIFO'))
    assert not candidates(physical, node('P2', '递归', '调用帧行为', '在调用栈中保存参数'))


def test_operation_application_requires_a_method_which_actually_uses_the_operation():
    push = node('P1', '入栈', '操作效果', '将元素插入栈顶')
    method = node('P2', '栈', '判断括号匹配', '扫描时左括号入栈、右括号出栈', form='procedure', steps=['初始化空栈','左括号入栈','右括号出栈'])
    row = next(iter(candidates(push, method).values()))
    assert row['allowed_types'] == ['applies_to']
    assert not candidates(push, node('P2', '栈', '物理实现', '数组'))


def test_definition_can_be_recommended_without_inventing_logical_necessity():
    definition = node('P1', '栈', '定义', '仅允许在栈顶插入和删除的线性表', form='definition')
    row = next(iter(candidates(definition, node('P2', '入栈', '操作效果', '将元素插入栈顶')).values()))
    assert row['allowed_types'] == ['prerequisite']
    assert row['allowed_necessities'] == ['recommended']


def test_stack_depth_cannot_derive_an_unrelated_sorting_time_bound():
    depth = node('P1', '递归深度', '调用帧数量', 'n')
    sorting = node('P2', '归并排序', '时间复杂度', 'O(n log n)，含递归深度n的调用栈')
    assert not candidates(depth, sorting)


def test_lifo_is_used_in_a_stack_method_but_not_in_a_physical_storage_fact():
    lifo = node('P1', '栈', '核心特征', 'LIFO')
    method = node('P2', '栈', '匹配方法', '左括号入栈，右括号出栈', form='procedure', steps=['初始化栈','入栈','出栈'])
    assert next(iter(candidates(lifo, method).values()))['allowed_types'] == ['applies_to']
    assert not candidates(lifo, node('P2', '栈', '物理实现', '数组或链表'))
