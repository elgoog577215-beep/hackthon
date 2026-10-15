"""Exercise the real preflight gate, without network requests or course writes."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from ai_base import AIBase
from backend.tests.test_knowledge_first import svc, initialize, start, tree_response
from course_knowledge_context import knowledge_context_prompt


@pytest.mark.asyncio
async def test_lesson_tree_with_adopted_knowledge_uses_its_own_context_budget(svc, monkeypatch):
    """A later lecture must not inherit the smaller handout-writing input cap."""
    from backend.tests.test_handout_knowledge import handouts
    from backend.tests.test_lesson_knowledge import one_lesson_response

    handouts(svc)
    async def seed_call(prompt, **kwargs):
        return json.dumps(one_lesson_response('memory'), ensure_ascii=False)
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=seed_call, model_smart='test', client=None)
    view = svc.view('c-pilot', source_mode='handouts')
    seed, _ = svc.start('c-pilot', 'tree', 'seed', '', view['document_revision'], source_mode='handouts', lesson_id='memory')
    await svc.run('c-pilot', seed['id'])
    svc.adopt('c-pilot', seed['id'], '', view['document_revision'])

    def grow_catalog(raw):
        tree = raw['course_knowledge_base']
        original = tree['knowledge_points'][0]
        tree['knowledge_points'] = [{**deepcopy(original), 'knowledge_id': f'old-{i}',
            'name': f'已采用知识{i}', 'statement': '这是已采用命题的完整定义及适用边界。' * 8,
            'meta_question': f'如何解释已采用知识{i}？', 'meta_answer': '完整回答必须保留原命题中的条件。' * 4}
            for i in range(44)]
        tree['lessons'][0]['knowledge_ids'] = [p['knowledge_id'] for p in tree['knowledge_points']]
        tree['relations'] = [{'id': f'old-relation-{i}', 'source_id': f'old-{i % 44}',
            'target_id': f'old-{(i + 1) % 44}', 'type': 'applies_to',
            'reason': '前一命题的规则用于后一命题描述的方法，并保留适用条件。' * 2,
            'conditions': [], 'scope_lesson_id': 'memory'} for i in range(63)]
        return raw
    svc.storage.update_course_data('c-pilot', grow_catalog)
    state = svc.authoring.load('c-pilot')
    state['lessons']['cpu']['script_revisions'][0]['sections'][0]['blocks'][0]['content'] = 'CPU执行指令。' + '完整讲义中的定义和方法步骤必须保留。' * 850
    svc.authoring._save(state)
    # This is a handout-writing knob, not the capacity of knowledge extraction.
    monkeypatch.setenv('COURSE_TEACHER_HANDOUT_MAX_INPUT_TOKENS', '32768')
    calls = []
    async def call(prompt, **kwargs):
        tokens = AIBase.estimate_request_tokens(prompt, kwargs['system_prompt'])
        assert tokens > 32768
        AIBase.validate_request_budget(prompt, kwargs['system_prompt'], kwargs['max_input_tokens'], kwargs['max_input_chars'])
        assert kwargs['max_input_tokens'] + kwargs['max_tokens'] + 1024 <= 131072
        calls.append(tokens)
        return json.dumps(one_lesson_response('cpu'), ensure_ascii=False)
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=call, model_smart='test', client=None)
    view = svc.view('c-pilot', source_mode='handouts')
    job, _ = svc.start('c-pilot', 'tree', 'later-lecture', view['knowledge_revision'], view['document_revision'], source_mode='handouts', lesson_id='cpu')
    frozen = deepcopy(job['request_snapshot']['knowledge_generation_context'])
    await svc.run('c-pilot', job['id'])
    saved = svc.authoring.get_job('c-pilot', job['id'])
    assert saved['status'] == 'completed', saved.get('error')
    assert len(calls) == 1
    assert saved['request_snapshot']['knowledge_generation_context'] == frozen
    assert saved['request_budget']['estimated_input_tokens'] == calls[0]


def test_generic_final_wire_prompt_keeps_all_facts_once_and_uses_short_ids():
    from generic_knowledge import tree_model_prompt
    context = {'source_mode': 'handouts', 'scope_lesson_id': 'lesson',
        'generation_request': {'requirements': '唯一课程要求'}, 'course_profile': {'title': '课程'},
        'handout_lessons': [{'key': 'lesson', 'title': '本讲'}],
        'reference_knowledge': [{'key': f'E{i}', 'knowledge_id': 'canonical_' + str(i), 'revision_id': 'version_' + str(i),
            'name': f'既有知识{i}', 'statement': f'完整命题{i}', 'conditions': [f'完整边界{i}'], 'meta_question': f'检查问题{i}', 'meta_answer': f'完整答案{i}'} for i in range(1, 67)],
        'reference_relations': [], 'reference_categories': [], 'reference_lessons': [],
        'evidence_package': {'package_revision_id': 'ev', 'course_id': 'c', 'units': [
            {'evidence_id': 'source', 'block_ids': ['block'], 'source_text': '完整讲义原文', 'locator': {'section_path': ['lesson']}, 'factual_allowed': True, 'purpose': 'content_source'}]},
        'handout_source_refs': {'secret_audit_id': {'block_id': 'block'}}, 'policy': {}, 'material_coverage': {},
        'scope_contract': {'revision_id': 'scope'}}
    before = deepcopy(context)
    prompt = tree_model_prompt({'course_name': '课程'}, context)
    assert prompt.count('唯一课程要求') == 1
    assert prompt.count('完整讲义原文') == 1
    assert 'canonical_' not in prompt and 'version_' not in prompt and 'secret_audit_id' not in prompt
    for point in context['reference_knowledge']:
        for key in ('key', 'name', 'statement', 'conditions', 'meta_question', 'meta_answer'):
            assert json.dumps(point[key], ensure_ascii=False) in prompt
    AIBase.validate_request_budget(prompt, '生成知识树', 32768, 64000)
    assert context == before


@pytest.mark.asyncio
async def test_tree_prompt_fits_real_input_gate_without_dropping_material(svc):
    svc.storage.update_course_data("c-pilot", lambda raw: {**raw,
        "generation_request": {"requirements": "理解计算机系统中的类型转换与控制流，能够说明判断依据与适用条件。" * 25}})
    initialize(svc)
    job = start(svc, "tree", "real-budget-gate")
    frozen = deepcopy(job["request_snapshot"]["knowledge_generation_context"])
    wire_calls = []
    async def call(prompt, **kwargs):
        AIBase.validate_request_budget(prompt, kwargs["system_prompt"], kwargs["max_input_tokens"])
        wire_calls.append(1)
        for unit in frozen["evidence_package"]["units"]:
            assert json.dumps(unit["source_text"], ensure_ascii=False) in prompt
        return json.dumps(tree_response(), ensure_ascii=False)
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=call, model_smart="test", client=None)
    await svc.run("c-pilot", job["id"])
    saved = svc.authoring.load("c-pilot")["jobs"][job["id"]]
    assert saved["status"] == "completed", saved.get("error")
    assert wire_calls == [1]
    assert saved["request_snapshot"]["knowledge_generation_context"] == frozen


def test_compaction_keeps_parse_gaps_and_source_versions_in_full_snapshot(svc):
    initialize(svc)
    context = start(svc, "tree", "inventory")["request_snapshot"]["knowledge_generation_context"]
    context["material_coverage"]["inventory"].append({"asset_id": "bad", "parse_status": "failed"})
    context["material_coverage"]["incomplete_assets"] = ["bad"]
    before = deepcopy(context)
    compact = knowledge_context_prompt(context, compact_evidence=True)
    assert "inventory" not in compact["material_coverage"]
    assert compact["material_coverage"]["inventory_count"] == 50
    assert compact["material_coverage"]["inventory_issues"] == [{"asset_id": "bad", "parse_status": "failed"}]
    assert compact["material_coverage"]["incomplete_assets"] == ["bad"]
    assert compact["evidence_package"]["package_revision_id"] == context["evidence_package"]["package_revision_id"]
    assert context == before


@pytest.mark.asyncio
async def test_real_oversize_fails_once_with_actionable_error(svc, monkeypatch):
    monkeypatch.setenv("COURSE_TEACHING_PLAN_MAX_INPUT_TOKENS", "2000")
    initialize(svc)
    job = start(svc, "tree", "too-large")
    attempts, wire_calls = [], []
    async def call(prompt, **kwargs):
        attempts.append(1)
        AIBase.validate_request_budget(prompt, kwargs["system_prompt"], kwargs["max_input_tokens"])
        wire_calls.append(1)
        return json.dumps(tree_response())
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=call, model_smart="test", client=None)
    await svc.run("c-pilot", job["id"])
    saved = svc.authoring.load("c-pilot")["jobs"][job["id"]]
    assert saved["status"] == "failed"
    assert saved["error"]["code"] == "AIRequestBudgetExceeded"
    assert "输入" in saved["error"]["message"]
    assert saved["error"]["retryable"] is False
    assert saved["error"]["model_request_sent"] is False
    assert attempts == [1] and not wire_calls
    assert not saved.get("partial_text")
