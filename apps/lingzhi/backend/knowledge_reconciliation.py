"""One finite reconciliation of remaining question collisions before tree layout."""
from copy import deepcopy

from generic_knowledge import normalized, require
from knowledge_extraction_repair import correct_points
from knowledge_extract import compile_extraction
from knowledge_semantic_contract import quality_point


def frozen_response(batch):
    return deepcopy(batch.get('reconciled_response') or batch.get('repair', {}).get('corrected_response')
                    or batch['content_review']['reviewed_response'])


async def reconcile(svc, course_id, job_id, provider, raw, context, pipeline, save, validate_source):
    from knowledge_compact import passage_catalog
    context = {**context, 'knowledge_passage_mode': 'source_blocks_v1'}
    batches = pipeline['inventory_batches']; questions = {}; responses = {}
    for index, batch in enumerate(batches, 1):
        response = frozen_response(batch); responses[index] = response
        passages = {p['key']: p for p in passage_catalog(context, batch['source_keys'])}
        for key, entry in response['passages'].items():
            for point in entry['points']:
                compiled, _ = quality_point(point, passages[key]['text'])
                questions.setdefault(normalized(compiled['question']), []).append((index, key, normalized(compiled['claim'])))
    collisions = [group for group in questions.values() if len({v[2] for v in group}) > 1]
    if not collisions: return
    record = pipeline.setdefault('reconciliation', {'status': 'pending', 'contract': 'knowledge_global_questions_v1'})
    require(record['status'] != 'completed', '全讲核对后仍有冲突，不能自动重复修正')
    selected = {key for group in collisions for _, key, _ in group}
    combined = {'response_contract': 'knowledge_extract_v9', 'passages': {}, 'source_issues': [], '_content_review_trace': []}
    keys = []
    for index, batch in enumerate(batches, 1):
        response = responses[index]; cursor = 0
        for key, entry in response['passages'].items():
            traces = response['_content_review_trace'][cursor:cursor+len(entry['points'])]; cursor += len(entry['points'])
            if key not in selected: continue
            combined['passages'][key] = deepcopy(entry)
            combined['_content_review_trace'].extend(deepcopy(traces))
            keys.append(key.rsplit('.', 1)[0])
        combined['source_issues'].extend(deepcopy(i) for i in response['source_issues'] if i['passage_key'] in selected)
    try:
        validate_source()
        def compile_corrected(response):
            result = compile_extraction(raw, context, list(dict.fromkeys(keys)), 0, response)
            require(not any(i['code'] == 'duplicate_meta_question' for i in (result.get('report') or {}).get('issues', [])),
                    '全讲定点核对后元问题仍重复，须明确等价合并或不同检查角度')
            return result
        corrected, _ = await correct_points(svc, course_id, job_id, provider, raw, context, list(dict.fromkeys(keys)), 0,
            combined, record, compile_result=compile_corrected, validate_source=validate_source,
            max_attempts=context.get('knowledge_correction_attempts', 1))
        validate_source(); traces = {}; cursor = 0
        for key, entry in corrected['passages'].items():
            traces[key] = corrected['_content_review_trace'][cursor:cursor+len(entry['points'])]; cursor += len(entry['points'])
        for index, batch in enumerate(batches, 1):
            response = responses[index]
            if not set(response['passages']) & selected: continue
            final_traces = []; cursor = 0
            for key, entry in list(response['passages'].items()):
                previous = response['_content_review_trace'][cursor:cursor+len(entry['points'])]; cursor += len(entry['points'])
                if key in selected: response['passages'][key] = deepcopy(corrected['passages'][key])
                final_traces.extend(deepcopy(traces[key] if key in selected else previous))
            response['_content_review_trace'] = final_traces
            response['source_issues'] = [i for i in response['source_issues'] if i['passage_key'] not in selected] + [
                deepcopy(i) for i in corrected['source_issues'] if i['passage_key'] in response['passages']]
            result = compile_extraction(raw, context, batch['source_keys'], index, response)
            if batch.get('content_review', {}).get('program_quarantines'):
                from knowledge_source_rules import annotate_verified_issues
                annotate_verified_issues(result, batch['content_review']['program_quarantines'])
            atom = next(b for b in pipeline['batches'] if b['id'] == f'atoms-{index}')
            atom.update(tree=result['tree'], report=result['report'])
            batch.update(reconciled_response=response, **{k: result[k] for k in ('items', 'source_coverage', 'source_issues', 'format_normalizations')})
        pipeline['items'] = [i for batch in batches for i in batch['items']]
        record['status'] = 'completed'; save()
    except Exception:
        record['status'] = 'failed'; save(); raise
