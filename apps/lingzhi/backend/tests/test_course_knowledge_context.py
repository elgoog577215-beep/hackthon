from copy import deepcopy
import hashlib
import pytest

from course_knowledge_context import build_knowledge_generation_context, documents_from_text_sources, knowledge_context_prompt
from evidence_package import freeze_evidence_package


def course():
    docs, bindings = documents_from_text_sources("course1", [
        {"id":"M1","scope_id":"lecture1","text":"赋值建立对象引用；修改对象与重新绑定名字不同。"},
        {"id":"M2","scope_id":"lecture2","text":"示例的排版风格。", "purpose":"style_reference"}])
    return {"course_id":"course1","course_name":"Python", "generation_request":{"pedagogy_mode":"programming_engineering"},
        "parsed_documents":docs,"material_bindings":bindings,
        "course_document":{"sections":[{"section_id":"lecture1","title":"引用","level":1},{"section_id":"lecture2","title":"复制","level":1}]}}


def test_context_reuses_freeze_profile_scope_and_does_not_mutate_input():
    source=course();before=deepcopy(source)
    first=build_knowledge_generation_context(source);second=build_knowledge_generation_context(source)
    assert source==before and first==second
    assert first["subject_pedagogy_profile"]["primary_mode"]=="programming_engineering"
    assert first["subject_pedagogy_profile"]["secondary_mode"] is None
    assert first["scope_contract"]["schema_version"]=="course_knowledge_scope_v2"
    assert [s['node_id'] for s in first['scope_contract']['section_responsibilities']]==['lecture1','lecture2']
    units=first['evidence_package']['units']
    assert len(units)==2 and units[1]['factual_allowed'] is False
    assert units[0]['content_hash']==hashlib.sha256(units[0]['source_text'].encode()).hexdigest()
    assert first['source_reference_aliases']['M1']==[units[0]['evidence_id']]
    assert not first['policy']['web_retrieval_enabled']


def test_context_revision_changes_for_goal_source_or_usage_policy():
    source=course();old=build_knowledge_generation_context(source)['revision_id']
    source['generation_request']['requirements']='新增课程目标'
    assert build_knowledge_generation_context(source)['revision_id']!=old
    source=course();source['parsed_documents'][0]['blocks'][0]['text']+='补充边界。'
    assert build_knowledge_generation_context(source)['revision_id']!=old
    source=course();source['material_bindings'][0]['purpose']='style_reference'
    assert build_knowledge_generation_context(source)['revision_id']!=old


def test_existing_frozen_package_remains_the_same_source_and_is_checked():
    source=course();context=build_knowledge_generation_context(source)
    package=context['evidence_package'];source['evidence_package']={**package,'frozen_at':'original-time'}
    reused=build_knowledge_generation_context(source)
    assert reused['evidence_package']==package
    source['evidence_package']['course_id']='foreign'
    with pytest.raises(ValueError,match='owner'):build_knowledge_generation_context(source)
    source['evidence_package']={}
    with pytest.raises(ValueError):build_knowledge_generation_context(source,fallback_sources=[{'id':'seed','text':'fallback'}])


def test_hash_tampering_and_failed_material_do_not_become_sample_fallback():
    source=course();package=build_knowledge_generation_context(source)['evidence_package']
    package['units'][0]['source_text']='tampered'
    source['evidence_package']=package
    with pytest.raises(ValueError,match='hash'):build_knowledge_generation_context(source)
    source=course();source['parsed_documents'][0]['parse_status']='failed'
    context=build_knowledge_generation_context(source,fallback_sources=[{'id':'seed','text':'fallback'}])
    assert context['material_coverage']['factual_evidence_count']==0
    assert context['material_coverage']['incomplete_assets']
    assert 'seed' not in context['source_reference_aliases']


def test_empty_material_and_scope_slice_keep_honest_provenance():
    empty=build_knowledge_generation_context({'course_id':'c','course_name':'只有名称'})
    assert empty['material_coverage']['factual_evidence_count']==0
    context=build_knowledge_generation_context(course())
    selected=knowledge_context_prompt(context,'lecture1')
    assert len(selected['evidence_package']['units'])==1
    assert selected['revision_id']==context['revision_id']
    assert len(context['evidence_package']['units'])==2
    assert selected['evidence_selection']['total_count']==2


def test_long_material_tail_is_in_evidence_not_just_summary():
    text='前文信息。'*700+'末尾独有知识标记。'
    docs,bindings=documents_from_text_sources('c',[{'id':'M1','text':text}])
    context=build_knowledge_generation_context({'course_id':'c','parsed_documents':docs,'material_bindings':bindings})
    assert any('末尾独有知识标记' in u['source_text'] for u in context['evidence_package']['units'])


def test_compact_prompt_preserves_every_selected_source_text():
    context=build_knowledge_generation_context(course())
    view=knowledge_context_prompt(context, compact_evidence=True)
    assert [(u['evidence_id'],u['source_text']) for u in view['evidence_package']['units']]==[(u['evidence_id'],u['source_text']) for u in context['evidence_package']['units']]
    assert view['revision_id']==context['revision_id']
    assert 'source_index' in context['evidence_package'] and 'source_index' not in view['evidence_package']
