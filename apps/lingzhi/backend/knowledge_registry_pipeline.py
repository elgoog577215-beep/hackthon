"""Registry-first generation inside the existing authoring task and course store."""
import asyncio
from copy import deepcopy
import json

from course_document import stable_hash
from course_repository import CourseDocumentConflict
from generic_knowledge import require, sources
from knowledge_registry_contract import CONTRACT, extraction_prompt, parse_candidates, identity_prompt, names_prompt, parse_names, parse_json
from knowledge_registry_identity import existing_catalog, apply_decisions
from knowledge_registry_projection import build_tree
from knowledge_transport import REQUEST_SCOPE, model_scope


def replay_saved(record, compile_result):
    """Recheck a complete previous response locally; never edit the historical record."""
    for attempt in reversed(record.get('attempts', [])):
        if not attempt.get('raw_response'):
            continue
        try:
            value = parse_json(attempt['raw_response'])
            return value, compile_result(value)
        except (ValueError, CourseDocumentConflict, TypeError, KeyError):
            return None
    return None


def continued_pipeline(checkpoint, retry_batch_id):
    result = deepcopy(checkpoint)
    result.pop('candidate', None)
    pipeline = result['atomic_pipeline']
    if retry_batch_id == 'hierarchy':
        pipeline.pop('hierarchy', None)
    elif retry_batch_id == 'relations':
        pipeline.pop('registry_relations', None)
    elif retry_batch_id:
        selected = pipeline['inventory_batches'] if retry_batch_id == 'all_atoms' else [
            b for i, b in enumerate(pipeline['inventory_batches'], 1) if retry_batch_id in {b['id'], f'atoms-{i}'}]
        require(bool(selected), '待重做批次不存在')
        for batch in selected:
            batch['status'] = 'pending'
            batch.pop('points', None)
            batch.pop('request', None)
        for key in ('registry', 'identity_review', 'names', 'hierarchy', 'registry_relations', 'preview_tree'):
            pipeline.pop(key, None)
    return result


async def run(svc, course_id, job_id):
    from knowledge_first import knowledge_revision, now
    from knowledge_atomic import call_stage, run_batches, source_groups, KnowledgeBatchValidationError
    job = svc._active(course_id, job_id)
    raw = svc.repository.load_raw(course_id)
    context = job['request_snapshot']['knowledge_generation_context']
    provider = None
    pipeline = deepcopy((job.get('checkpoint') or {}).get('atomic_pipeline'))
    if not pipeline or pipeline.get('generation_contract') != CONTRACT:
        pipeline = {'schema_version': 'inventory_atomic_v1', 'generation_contract': CONTRACT,
            'processing_contract': CONTRACT, 'prompt_contract': CONTRACT,
            'provenance_contract': 'input_material_record_v1', 'revision': 0,
            'source_unit_contract': context.get('source_unit_contract'),
            'extraction_mode': 'single_pass_v1', 'items': [], 'batches': [],
            'organize_hierarchy': job.get('organize_hierarchy', True), 'include_relations': job.get('include_relations', True),
            'inventory_batches': [{'id': f'inventory-{i}', 'source_keys': keys, 'status': 'pending'}
                                  for i, keys in enumerate(source_groups(context), 1)],
            'catalog': existing_catalog(raw)}

    def validate_version():
        svc._active(course_id, job_id)
        fresh = svc.repository.load_raw(course_id)
        require(fresh.get('owner_id') == job.get('actor')
                and knowledge_revision(fresh) == job['source_knowledge_revision']
                and fresh.get('course_document_revision') == job['source_document_revision']
                and svc._context(fresh, 'handouts', job['knowledge_lesson_id'])['revision_id'] == context['revision_id'],
                '课程、知识或讲义版本已变化，保留候选')

    def save(**updates):
        validate_version()
        pipeline['revision'] += 1
        if pipeline.get('registry') or any(b.get('points') for b in pipeline['inventory_batches']):
            pipeline['preview_tree'] = build_tree(raw, context, pipeline, job_id, preview=True)
        complete = sum(b['status'] == 'completed' for b in pipeline['inventory_batches'])
        progress = int(55 * complete / len(pipeline['inventory_batches']))
        if pipeline.get('registry'):
            progress = 70
        if pipeline.get('names', {}).get('status') == 'completed':
            progress = 80
        if pipeline.get('hierarchy', {}).get('status') == 'completed':
            progress = 90
        svc.authoring.update_job(course_id, job_id, checkpoint={'atomic_pipeline': deepcopy(pipeline)}, progress=progress, **updates)

    async def request(prompt, stage, record, compile_result):
        validate_version()
        if record.get('status') == 'completed':
            return compile_result(deepcopy(record['response']))
        replay = replay_saved(record, compile_result)
        if replay is not None:
            value, result = replay
            record.update(status='completed', response=value, validation_origin='recompiled_saved_response',
                          revalidated_by_job_id=job_id)
            record.pop('validation_error', None)
            save()
            return result
        previous = None
        for attempt in range(2):
            validate_version()
            effective = prompt
            if attempt:
                instruction, payload_text = prompt.split('\nINPUT_JSON:\n', 1)
                payload = json.loads(payload_text)
                payload['repair_feedback'] = {'error': record['validation_error'], 'previous_response': previous,
                    'scope': '仅修正响应协议或所指出字段，其他内容保持'}
                effective = instruction + '\nINPUT_JSON:\n' + json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
            entry = {'stage': stage, 'attempt': attempt + 1, 'status': 'requested', 'job_id': job_id}
            record.setdefault('attempts', []).append(entry)
            try:
                response = await call_stage(svc, course_id, job_id, provider, effective, stage)
                entry['raw_response'] = response
                value = parse_json(response)
                result = compile_result(value)
                validate_version()
                entry['status'] = 'completed'
                record.update(status='completed', response=value)
                record.pop('validation_error', None)
                save()
                return result
            except (ValueError, CourseDocumentConflict, TypeError, KeyError) as error:
                validate_version()
                record.update(status='failed', validation_error=str(error))
                entry.update(status='failed', validation_error=str(error))
                save()
                current = entry.get('raw_response')
                if current is None or current == previous or attempt:
                    raise
                previous = current

    token = REQUEST_SCOPE.set({'validate_source': validate_version,
        'retry_budget': {'used': int(job.get('transport_retry_count') or 0), 'active': {}}})
    try:
        validate_version()
        svc.authoring.update_job(course_id, job_id, status='running', phase='preparing',
            generation_started_at=now(), generation_contract=CONTRACT, checkpoint={'atomic_pipeline': deepcopy(pipeline)})
        if svc.provider_factory:
            provider = svc.provider_factory()
        else:
            from ai_base import AIBase
            provider = AIBase()
        available = sources(context)

        async def extract(index, batch):
            materials = [{'key': key, 'text': available[key]['source_text']} for key in batch['source_keys']]
            prompt = extraction_prompt(raw, context, materials, pipeline['catalog'])
            try:
                batch['points'] = await request(prompt, 'candidate_extract', batch.setdefault('request', {}),
                    lambda value: parse_candidates(value, f'B{index}', batch['source_keys']))
            except (ValueError, CourseDocumentConflict) as error:
                validate_version()
                batch['validation_error'] = {'message': str(error)}
                save()
                raise KnowledgeBatchValidationError(batch['id'], str(error)) from error
            batch['status'] = 'completed'
            batch.pop('validation_error', None)
            save()

        await run_batches(pipeline['inventory_batches'], extract, width=4, stage='candidate_extract')
        candidates = [p for b in pipeline['inventory_batches'] for p in b['points']]
        require(bool(candidates) and len(candidates) <= 240, '本讲知识候选为空或超过核对预算')
        if not pipeline.get('registry'):
            def resolve(value):
                if not isinstance(value, dict) or set(value) != {'decisions'}:
                    raise ValueError('统一核对只返回decisions')
                return apply_decisions(candidates, pipeline['catalog'], value['decisions'])
            pipeline['registry'] = await request(identity_prompt(candidates, pipeline['catalog']), 'identity_review',
                pipeline.setdefault('identity_review', {}), resolve)
            save()
        points = pipeline['registry']['points']
        new_points = [p for p in points if not p.get('_registered_point')]
        names = pipeline.setdefault('names', {})
        if new_points and names.get('status') != 'completed':
            names['result'] = await request(names_prompt(new_points), 'candidate_names', names,
                                            lambda value: parse_names(value, new_points))
        elif not new_points:
            names.update(status='completed', result={})
        # A completed request may have been persisted just before the caller stored its projection.
        if names.get('status') == 'completed' and 'result' not in names:
            names['result'] = parse_names(names['response'], new_points)
        save()
        tree = build_tree(raw, context, pipeline, job_id)
        # Whole-course unique keys also make reused cross-lesson identities unambiguous.
        for i, p in enumerate(tree['knowledge_points'], 1):
            p['key'] = f'K{i}'
        local = [p for p in tree['knowledge_points'] if context['scope_lesson_id'] in p['section_refs']]
        hierarchy = None
        if pipeline['organize_hierarchy']:
            from knowledge_hierarchy import organize
            hierarchy = await organize(svc, course_id, job_id, provider, raw, context, pipeline, local, save, validate_version, concurrency=4)
            # apply_hierarchy expects the same frozen local keys.
            from knowledge_hierarchy import apply_hierarchy
            categories, organized = apply_hierarchy(hierarchy, local)
            organized_by_id = {p['knowledge_id']: p for p in organized}
            tree['knowledge_points'] = [organized_by_id.get(p['knowledge_id'], p) for p in tree['knowledge_points']]
            existing_categories = {c['id']: c for c in tree['categories']}
            existing_categories.update({c['id']: c for c in categories})
            needed = set()
            for p in tree['knowledge_points']:
                parent = p['parent_id']
                while parent in existing_categories and parent not in needed:
                    needed.add(parent)
                    parent = existing_categories[parent]['parent_id']
            tree['categories'] = [c for key, c in existing_categories.items() if key in needed]
            tree['concept_groups'] = [{**c, 'concept_group_id': c['id']} for c in tree['categories']]
        if pipeline['include_relations']:
            from knowledge_registry_relations import prompt as relation_prompt, compile_edges, attach
            relation_state = pipeline.setdefault('registry_relations', {'batches': [
                {'id': f'relations-{i//12+1}', 'focus_keys': [p['key'] for p in local[i:i+12]], 'status': 'pending'}
                for i in range(0, len(local), 12)]})
            async def relate(index, batch):
                batch['result'] = await request(relation_prompt(tree, batch['focus_keys']), 'candidate_relations',
                    batch.setdefault('request', {}), lambda value: compile_edges(value, tree, batch['focus_keys'], context['scope_lesson_id']))
                batch['status'] = 'completed'
                save()
            await run_batches(relation_state['batches'], relate, width=4, stage='candidate_relations')
            tree = attach(tree, relation_state['batches'])
            relation_state['status'] = 'completed'
        validate_version()
        tree.update(source_context_revision=context['revision_id'],
                    source_scope_revision=context['scope_contract']['revision_id'], generation_job_id=job_id,
                    model=provider.model_smart, generation_contract=CONTRACT)
        tree['revision_id'] = stable_hash({k: v for k, v in tree.items() if k != 'revision_id'}, prefix='kb_')
        svc.authoring.update_job(course_id, job_id, status='completed', phase='completed', progress=100,
            checkpoint={'atomic_pipeline': deepcopy(pipeline), 'candidate': tree}, raw_response='', partial_text='',
            stream_complete=True, message='知识树候选已生成，请核对待确认项后采用')
    except asyncio.CancelledError:
        raise
    except Exception as error:
        current = svc.authoring.get_job(course_id, job_id)
        if current['status'] in {'pending', 'running'}:
            svc.authoring.update_job(course_id, job_id, status='failed', phase='failed',
                checkpoint={'atomic_pipeline': deepcopy(pipeline)},
                error={'code': type(error).__name__, 'message': str(error),
                       **deepcopy(getattr(error, 'knowledge_failure', {}))},
                message='已保留完成批次与候选，请继续未完成环节')
    finally:
        REQUEST_SCOPE.reset(token)
        if provider and getattr(provider, 'client', None):
            await provider.client.close()
