"""Reviewed short statements bound to immutable semantic slots and source text."""
from copy import deepcopy
import re

from course_repository import CourseDocumentConflict
from course_versioning import stable_hash


CONTRACT = 'knowledge_expression_v1'
REVIEW_CONTRACT = 'knowledge_content_review_v2'


def check_contract(contract):
    if contract not in {None, CONTRACT}:
        raise CourseDocumentConflict('未知短陈述合同，不能静默切换')
    return contract


def validate_name(name, point):
    if (not isinstance(name, str) or not 2 <= len(name.strip()) <= 200
            or re.search(r'[？?\n\r]', name)
            or re.match(r'^(?:如何|怎样|怎么|为何|为什么|什么|能否|是否)', name.strip())):
        raise CourseDocumentConflict('短陈述名称必须是简短、完整的陈述，不得使用问句')
    name = name.strip()
    subject = point.get('subject', '')
    nominal = {subject, f'{subject}的定义', f'{subject}的性质', f'{subject}的规则', f'{subject}的公式'}
    if point.get('property'):
        nominal.add(f"{subject}的{point['property']}")
    if name in nominal:
        raise CourseDocumentConflict('短陈述不能只有对象或属性名，须表达具体知识')
    return name


def semantic_signature(point):
    return stable_hash({key: val for key, val in point.items() if key != 'attachments'}, prefix='ksem_')


def bind_name(name, point, source_text):
    return {'contract': CONTRACT, 'text': validate_name(name, point),
            'semantic_signature': semantic_signature(point),
            'source_signature': stable_hash(source_text, prefix='ksrc_'),
            'semantics_verified': False}


def bound_name(expression, point, source_text):
    if (not isinstance(expression, dict) or expression.get('contract') != CONTRACT
            or expression.get('semantic_signature') != semantic_signature(point)
            or expression.get('source_signature') != stable_hash(source_text, prefix='ksrc_')):
        raise CourseDocumentConflict('短陈述与完整知识或来源不匹配，需重新核对')
    return validate_name(expression.get('text'), point)


def named_traces(names, points, source_text, trace):
    if not isinstance(names, list) or len(names) != len(points):
        raise CourseDocumentConflict('短陈述与最终知识点数量不一致')
    return [{**deepcopy(trace), 'expression': bind_name(name, point, source_text)}
            for name, point in zip(names, points)]


def review_instruction():
    return (
        '本次使用knowledge_expression_v1和knowledge_content_review_v2。'
        '在原内容核对中，为每个最终保留的知识点同时写一个学生能读懂的短陈述名称。'
        '每个point_reviews对象增加names数组：keep对应原点，names恰好1项；replace对应points的原顺序，逐点各1项；context/source_issue的names=[]。'
        '顶层增加addition_names对象，与additions具有完全相同的块号；每个数组与该块新增points顺序和数量完全对应，无新增填[]。'
        '名称只说明完整知识的核心意思，不使用“如何/怎样/是什么”等问句，不只写“某对象的属性/定义”。'
        '优先写一行能读懂的短句，长公式允许直接陈述，不硬截断。不得省略会改变含义的否定、对象、必要限定或把例子当规则。'
        '例如可写“常数的导数为零”“入栈把元素加入栈顶”“匀速直线运动的速度保持不变”；例子不是新增知识清单。'
        '完整公式、定义限定、方法步骤仍留在原语义字段；名称不替代正文，不能为了短名重写有效命题。'
        '逐点检查来源中对符号和适用范围的定义，点内conditions须自足；使用某符号的点保留其含义，不能只放在reason或相邻点。'
        '材料没有支持的内容标疑点或缺口，不补造。名称是否等义须逐点核对；此模型核对不等于独立学科认证。'
    )
