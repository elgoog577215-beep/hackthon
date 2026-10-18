"""Regressions observed in real isolated Qwen output, not synthetic pass-throughs."""
import pytest

from course_repository import CourseDocumentConflict
from knowledge_semantic_contract import quality_point


def fact(subject, prop, value, conditions=None):
    return dict(form='fact', subject=subject, property=prop, value=value,
                conditions=conditions or [], attachments=[])


@pytest.mark.parametrize('point,source,error', [
    (fact('数据结构', 'BFS数据结构', '队列'), 'BFS的数据结构是队列。', '具体'),
    (fact('策略', 'DFS策略', '先访问根节点'), 'DFS策略先访问根节点。', '具体'),
    (fact('算法', '特性利用', 'LIFO'), '括号算法利用LIFO。', '具体'),
    ({'form':'definition','subject':'策略','meaning':'访问根节点然后访问子树','constraints':[], 'conditions':[], 'attachments':[]}, 'DFS策略：访问根节点然后访问子树。', '具体'),
    (fact('栈', '物理实现', '数组或链表', ['必须建立在线性表物理存储之上']), '栈可用数组或链表物理实现。', '绝对'),
    (fact('递归', '执行速度对比', '通常比等价循环慢'), '递归通常比循环慢。', '模型'),
    (fact('递归', '内存占用对比', '占用更多内存（栈空间）'), '递归比循环占用更多内存。', '模型'),
    (fact('循环', '执行速度优势', '通常优于递归'), '循环速度通常优于递归。', '模型'),
    (fact('递归深度', '限制因素', '系统栈空间'), '递归深度受系统栈空间限制。', '实现'),
    ({'form':'definition','subject':'DFS','meaning':'深度优先探索', 'constraints':['将子节点压入栈'], 'conditions':[], 'attachments':[]}, 'DFS用栈探索，将子节点压入栈。', '实现'),
    ({'form':'procedure','subject':'栈','goal':'判断圆括号是否匹配', 'steps':['扫描字符','遇到左括号入栈','遇到右括号且栈空时立即失败','否则弹出一个左括号'], 'completion':'没有提前失败且最终栈为空', 'conditions':[], 'attachments':[]}, '栈算法：stack = []，然后扫描圆括号，空栈时失败。', '初始'),
    ({'form':'procedure','subject':'栈','goal':'判断圆括号是否匹配', 'steps':['初始化空栈','扫描字符','遇到左括号入栈','遇到右括号且栈空时立即失败','否则弹出一个左括号'], 'completion':'最终栈为空', 'conditions':[], 'attachments':[]}, '栈算法判断圆括号是否匹配。', '提前失败'),
])
def test_real_output_scope_losses_are_blocked(point, source, error):
    with pytest.raises(CourseDocumentConflict, match=error):
        quality_point(point, source)


def test_scoped_implementation_and_complete_matching_method_remain_usable():
    p = fact('递归', '执行速度对比', '通常比等价循环慢',
             ['本讲普通调用栈实现', '相同工作量和基本操作计量，调用帧开销未被优化'])
    quality_point(p, '递归通常比等价循环慢，讨论普通调用栈的调用开销。')
    p = {'form':'procedure','subject':'栈','goal':'判断圆括号是否匹配',
         'steps':['初始化空栈','扫描字符','遇到左括号入栈','右括号且空栈时立即返回失败','否则弹出一个左括号'],
         'completion':'没有提前失败且扫描结束时栈为空', 'conditions':['输入只含圆括号'], 'attachments':[]}
    quality_point(p, '栈算法判断圆括号是否匹配。')
    p['completion'] = '遍历过程中未提前返回 False 且遍历结束后栈为空'
    quality_point(p, '栈算法判断圆括号是否匹配。')


def test_algorithm_itself_can_be_a_named_concept_when_the_source_defines_it():
    p = {'form':'definition','subject':'算法','meaning':'解决问题的有限步骤序列','constraints':[], 'conditions':[], 'attachments':[]}
    quality_point(p, '算法是解决问题的有限步骤序列。')


@pytest.mark.parametrize('scope', ['此处展示队列实现', '本节展示队列实现', '这里讨论的队列实现'])
def test_explicit_local_implementation_scope_is_not_rejected_by_word_choice(scope):
    p = fact('BFS', '数据结构', '队列', [scope])
    quality_point(p, 'BFS使用队列实现。')
