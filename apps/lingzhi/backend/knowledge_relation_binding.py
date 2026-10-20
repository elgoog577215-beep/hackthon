"""Explicit relation interpretation is separate from verifiable source binding."""
from copy import deepcopy
import re

from course_document import stable_hash
from knowledge_expression import semantic_signature
from knowledge_correction_plan import KnowledgePointValidationError

CONTRACT='knowledge_relation_binding_v1'


def needs_binding(point):
    # This only requests interpretation; it never extracts or invents an entity.
    return point.get('form')=='fact' and bool(re.search(r'(?:关系|联系|区别|差异)$',str(point.get('property',''))))


def binding_schema():
    from knowledge_compact import obj,string
    return obj({'kind':{'enum':['attribute','relation','uncertain']},
                'target':{'type':'string','maxLength':100},'relation_type':{'type':'string','maxLength':100}})


def seal_binding(point,source,declaration):
    from jsonschema import validate
    from knowledge_compact import source_literal
    validate(declaration,binding_schema())
    return {**deepcopy(declaration),'contract':CONTRACT,'semantic_signature':semantic_signature(point),
            'source_signature':stable_hash(source,prefix='ksrc_'),
            'source_span':source_literal(declaration['target'],source) if declaration['target'] else None,
            'semantics_verified':False}


def check_binding(point,source,binding):
    from knowledge_compact import source_literal
    def fail(code,message,field='relation_binding',actual=None):
        raise KnowledgePointValidationError([{'code':code,'category':'alignment','field':field,'fields':[field],
            'actual':actual,'expected':'明确关系对象及关系类型，并绑定当前冻结原文中的对象位置','message':message}])
    if binding is None:
        if needs_binding(point):fail('relation_binding_required','关系含义尚未结构化：请识别对象和关系类型，不改写知识表述',actual=point.get('property'))
        return {'kind':'attribute','status':'not_required'}
    if (binding.get('contract')!=CONTRACT or binding.get('semantic_signature')!=semantic_signature(point)
            or binding.get('source_signature')!=stable_hash(source,prefix='ksrc_')):
        fail('relation_binding_stale','关系绑定与当前知识或来源不一致，须重新识别')
    kind=binding.get('kind')
    if kind=='uncertain':fail('relation_binding_uncertain','关系含义尚不能确定，保留待核对，不判定为原文缺失')
    if kind=='attribute':
        if binding.get('target') or binding.get('relation_type') or str(point.get('property','')).startswith('与'):
            fail('relation_binding_uncertain','属性分类与显式关系表述不一致，须核对关系角色')
        return {**deepcopy(binding),'status':'model_classified_attribute'}
    if kind!='relation' or not binding.get('target') or not binding.get('relation_type'):
        fail('relation_binding_required','关系对象或关系类型缺失')
    target=binding['target']
    norm=lambda value:re.sub(r'\s+','',str(value)).strip('$`')
    if norm(target)==norm(point.get('subject')):
        fail('relation_binding_self_target','关系对象不能重复主体；需识别关系的另一对象','relation_binding.target',target)
    mentioned=source_literal(target,str(point.get('property',''))) or source_literal(target,str(point.get('value','')))
    if not mentioned:
        fail('relation_target_unresolved','声明的对象未在冻结属性或结论中出现，不能仅凭原文中有这个词就认定角色','relation_binding.target',target)
    span=source_literal(binding['target'],source)
    if not span:fail('relation_source_missing','已声明的关系对象未匹配当前原文：'+binding['target'],'relation_binding.target',binding['target'])
    return {**deepcopy(binding),'source_span':span,'status':'source_text_matched'}


def with_bindings(context,response):
    bindings=dict(context.get('_relation_bindings') or {})
    for trace in response.get('_content_review_trace') or []:
        b=trace.get('relation_binding')
        if b:bindings[b['semantic_signature']+b['source_signature']]=deepcopy(b)
    return {**context,'_relation_bindings':bindings}


def relation_kwargs(context,point,source):
    contract=context.get('relation_binding_contract')
    if not contract:return {}
    return {'relation_binding_contract':contract,'relation_binding':context.get('_relation_bindings',{}).get(
        semantic_signature(point)+stable_hash(source,prefix='ksrc_'))}
