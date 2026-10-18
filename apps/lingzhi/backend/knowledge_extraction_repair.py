"""One visible correction request for precisely identified invalid point slots."""
from copy import deepcopy
import json

from course_repository import CourseDocumentConflict
from generic_knowledge import require
from knowledge_compact import passage_catalog, parse_complete_json
from knowledge_semantic_contract import quality_point, quality_prompt


async def repair_points(svc, course_id, job_id, provider, raw, context, keys, index, response, record):
    from knowledge_atomic import call_stage
    context = {**context, 'knowledge_passage_mode': 'source_blocks_v1'}
    passages = {p['key']: p for p in passage_catalog(context, keys)}
    require(isinstance(response.get('passages'), dict) and set(response['passages']) == set(passages), '片段结构错误不可按知识点修正')
    targets = {}
    for key, entry in response['passages'].items():
        require(isinstance(entry, dict) and isinstance(entry.get('points'), list), '片段结构错误不可按知识点修正')
        for ordinal, point in enumerate(entry['points']):
            try: quality_point(point, passages[key]['text'])
            except (CourseDocumentConflict, KeyError, TypeError, ValueError) as error:
                targets[f'{key}:{ordinal}'] = {'point': point, 'error': str(error)[:400], 'passage_key': key}
    require(0 < len(targets) <= 16, '没有可精确定位或超出单次修正容量的知识点')
    payload = json.loads(quality_prompt(raw, context, keys).split('\nINPUT_JSON:\n')[1])
    payload.update(stage='extract_repair', targets=targets)
    prompt = quality_prompt(raw, context, keys).split('\nINPUT_JSON:\n')[0] + (
        '\n本请求只修正targets列出的无效点；禁止改动其他点或添加其他块。每个目标必须回应一次。'
        '把单一属性、实际原文主体和对应取值写清；必要时拆成多个完整点。'
        '具体轨迹、教学目标或没有独立一般知识的点可明确归context并说明理由，不能虚构替代知识。'
        '不要返回原顶层passages。只输出{"repairs":{"目标键":{"points":[修正后完整点],"handling":"replace","reason":"具体修改"}},"source_issues":[]}。'
        '归背景时points=[]，handling="context"；新增疑点只能指向targets所属块。只允许这一轮修正，所有原输出会保留。\nINPUT_JSON:\n'
    ) + json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    record.update(status='requested', target_keys=list(targets), targets=deepcopy(targets))
    text = await call_stage(svc, course_id, job_id, provider, prompt, 'extract_repair')
    record['raw_response'] = text
    parsed = parse_complete_json(text)
    require(isinstance(parsed, dict) and set(parsed) - {'_format_normalizations'} == {'repairs', 'source_issues'}
            and isinstance(parsed['repairs'], dict) and set(parsed['repairs']) == set(targets), '修正越界或未完整回应目标')
    output = deepcopy(response); decisions = []
    for key, entry in output['passages'].items():
        points = []
        for ordinal, original in enumerate(entry['points']):
            target = f'{key}:{ordinal}'
            if target not in targets:
                points.append(original); continue
            repair = parsed['repairs'][target]
            require(isinstance(repair, dict) and set(repair) == {'points', 'handling', 'reason'}
                    and isinstance(repair['points'], list) and len(repair['points']) <= 8
                    and isinstance(repair['reason'], str) and repair['reason'].strip(), '修正结构无效')
            require(repair['handling'] == ('replace' if repair['points'] else 'context'), '修正去向不明确')
            for point in repair['points']: quality_point(point, passages[key]['text'])
            points.extend(deepcopy(repair['points']))
            decisions.append({'target_key': target, **deepcopy(repair)})
        entry['points'] = points
        if not points:
            entry['note'] = {'handling': 'context', 'reason': '；'.join(d['reason'] for d in decisions if d['target_key'].startswith(key + ':'))}
    issues = parsed['source_issues']
    require(isinstance(issues, list) and all(isinstance(i, dict) and i.get('passage_key') in
            {v['passage_key'] for v in targets.values()} for i in issues), '修正来源疑点越界')
    output['source_issues'] = [*output['source_issues'], *deepcopy(issues)]
    record.update(status='validated', decisions=decisions)
    return output
