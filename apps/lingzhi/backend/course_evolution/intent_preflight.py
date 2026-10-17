"""Clarify a request once before spending model capacity on full-text scans."""
from copy import deepcopy
from course_document import stable_hash
from .semantic_scan import validate_batch

INTENT_CONTRACT = 'teacher_change_intent_v1'


async def assess_intent(*, overview, instruction, model_identity, analyzer, checkpoint, on_progress):
    saved = deepcopy(checkpoint or {})
    signature = stable_hash({'contract': INTENT_CONTRACT, 'overview': overview,
                             'instruction': instruction, 'model': model_identity}, prefix='intent-')
    previous = saved.get('intent_preflight') or {}
    if previous.get('signature') == signature:
        result = validate_batch(previous.get('result'), [])
    elif saved.get('results'):
        # An older in-flight scan already passed this point. Preserve its work.
        return None, saved
    else:
        if on_progress:
            await on_progress({'stage': 'intent', 'completed_parts': 0, 'total_parts': 0,
                               'reused_parts': 0, 'failed_parts': 0}, saved)
        result = validate_batch(await analyzer(overview, [], instruction), [])
    if not str(result.get('interpreted_goal') or '').strip():
        raise ValueError('修改意图分析未返回可用目标')
    if len(result['clarifications']) + len(result['blocking_questions']) > 3:
        raise ValueError('修改意图应集中为至多三个关键问题')
    for question in [*result['clarifications'], *result['blocking_questions']]:
        prompt = question.get('prompt') if isinstance(question, dict) else question
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError('修改意图问题缺少可回答的内容')
    saved['intent_preflight'] = {'contract': INTENT_CONTRACT, 'signature': signature,
                               'result': deepcopy(result)}
    if on_progress:
        await on_progress({'stage': 'intent', 'completed_parts': 0, 'total_parts': 0,
                           'reused_parts': 0, 'failed_parts': 0}, saved)
    return result, saved
