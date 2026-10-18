"""One visible correction request for precisely identified invalid point slots."""
from copy import deepcopy
import json
import re
from jsonschema import Draft202012Validator

from course_repository import CourseDocumentConflict
from generic_knowledge import require
from knowledge_compact import passage_catalog, parse_complete_json, obj, array, string
from knowledge_semantic_contract import quality_point, quality_prompt, point_variants, subject_options


def repair_schema(targets, passages):
    repairs = {}
    for key, target in targets.items():
        choices = point_variants(subject_options(passages[target['passage_key']], contract='knowledge_extract_v9'), contract='knowledge_extract_v9')['anyOf']
        form = 'definition' if any(term in target.get('error', '') for term in ('联合定义', '仅说明机制')) else target['point']['form']
        require(form in {'fact', 'definition', 'comparison', 'procedure'}, '无法精确限定修正形态')
        shape = next(choice for choice in choices if choice['properties']['form']['const'] == form)
        properties = shape['properties']
        shape = obj({'form': properties['form'], **{k: v for k, v in properties.items() if k != 'form'}})
        repairs[key] = obj({'points': array(shape, 8), 'handling': {'enum': ['replace', 'context']}, 'reason': string(600)})
    issue = obj({'passage_key': {'enum': list(dict.fromkeys(v['passage_key'] for v in targets.values()))},
                 'kind': {'enum': ['suspected_error', 'contradiction']}, 'detail': string(1000)})
    return obj({'repairs': obj(repairs), 'source_issues': array(issue, 16)})


async def repair_points(svc, course_id, job_id, provider, raw, context, keys, index, response, record):
    from knowledge_atomic import call_stage
    context = {**context, 'knowledge_passage_mode': 'source_blocks_v1'}
    passages = {p['key']: p for p in passage_catalog(context, keys)}
    require(isinstance(response.get('passages'), dict) and set(response['passages']) == set(passages), '片段结构错误不可按知识点修正')
    targets = {}; questions = {}
    for key, entry in response['passages'].items():
        require(isinstance(entry, dict) and isinstance(entry.get('points'), list), '片段结构错误不可按知识点修正')
        for ordinal, point in enumerate(entry['points']):
            try:
                compiled, _ = quality_point(point, passages[key]['text'])
                questions.setdefault(compiled['question'], []).append((key, ordinal, point, compiled['claim']))
            except (CourseDocumentConflict, KeyError, TypeError, ValueError) as error:
                targets[f'{key}:{ordinal}'] = {'point': point, 'error': str(error)[:400], 'passage_key': key}
    for group in questions.values():
        if len({entry[3] for entry in group}) <= 1: continue
        for key, ordinal, point, _ in group:
            targets[f'{key}:{ordinal}'] = {'point': point, 'passage_key': key,
                'error': '元问题重复且答案不同，必须用实际结构名作为subject，并在property中明确操作或检查角度；不改原答案含义。'}
    require(0 < len(targets) <= 16, '没有可精确定位或超出单次修正容量的知识点')
    for target in targets.values():
        conditions = target['point'].get('conditions', [])
        # Preserve unaffected scope exactly; diagnosed scope errors may be corrected.
        target['required_conditions'] = deepcopy(conditions) if isinstance(conditions, list) and not re.search(
            r'前提|范围|串用|条件|联合定义|仅说明机制', target.get('error', '')) else []
    payload = json.loads(quality_prompt(raw, context, keys).split('\nINPUT_JSON:\n')[1])
    payload.update(stage='extract_repair', targets=targets)
    prompt = quality_prompt(raw, context, keys).split('\nINPUT_JSON:\n')[0] + (
        '\n本请求只修正targets列出的无效点；禁止改动其他点或添加其他块。每个目标必须回应一次。'
        '把单一属性、实际原文主体和对应取值写清；必要时拆成多个完整点。'
        '错误“独立属性必须分别成为知识点”指的是property字段，而不是value；'
        'property不能包含任何与、和、及、顿号、分号、逗号，必须修改property本身。'
        '若描述两个对象或顺序的关系，使用单一性质名称（如对应方式、顺序一致性），保持原取值意义，不用并列名词充当属性名。'
        '每个新拆出的点也须满足全部规则：成本单独用成本属性，n等符号在该点conditions定义；不能在访问权限属性里新增O(...)。'
        '每个替换或拆分点的conditions必须原样包含该target.required_conditions全部条目，可以增加来源支持的前提，不能清空、改写或移入attachments。'
        '只修正subject拼写或property时尤其不能顺手删除原有条件；reason里的范围说明不能代替conditions。'
        '主体不能改成“策略”“数据结构”“算法”等栏目名，fact和definition都要指向当前块逐字出现的具体方法或结构。'
        '括号完整方法包含初始化空栈、空栈遇右括号立即失败；成功判据同时包括未提前失败和遍历结束空栈。'
        '错误“一个属性值不能夹带独立命题”指value内含分号或多个句子，应拆成分别成立的点，不可删掉其中事实。'
        '每个修正点保持目标点的form；若错误明确指出联合定义，则必须改为definition，meaning和constraints完整保留基本情况与递归关系，不拆成两个泛化fact。'
        '若错误指出当前块仅说明机制，则改为definition表达完整策略含义，不把缺少初始状态的几步机制冒充可执行完整算法。'
        '若错误指出环境数值或来源过强断言而无法由当前材料明确限定，则归context并在source_issues注明，不补造条件。'
        '若错误指出时间和空间独立量，则拆为不同property；若value中含若/当/如果，必须将真实前提移入conditions以进入元问题。'
        '括号定义不能禁止任意)(子串，()()是反例；根据冻结扫描算法改为前缀余额非负且最终余额为0，或记来源疑点。'
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
    clean = {k: v for k, v in parsed.items() if k != '_format_normalizations'}
    error = next(Draft202012Validator(repair_schema(targets, {k: p['text'] for k, p in passages.items()})).iter_errors(clean), None)
    require(error is None, '修正响应字段无效：' + ('/'.join(str(k) for k in error.absolute_path) if error else ''))
    output = deepcopy(response); decisions = []
    original_traces = response.get('_content_review_trace'); trace_cursor = 0; repaired_traces = []
    for key, entry in output['passages'].items():
        points = []
        for ordinal, original in enumerate(entry['points']):
            target = f'{key}:{ordinal}'
            trace = deepcopy(original_traces[trace_cursor]) if original_traces is not None else None
            trace_cursor += 1
            if target not in targets:
                points.append(original)
                if trace is not None: repaired_traces.append(trace)
                continue
            repair = parsed['repairs'][target]
            require(isinstance(repair, dict) and set(repair) == {'points', 'handling', 'reason'}
                    and isinstance(repair['points'], list) and len(repair['points']) <= 8
                    and isinstance(repair['reason'], str) and repair['reason'].strip(), '修正结构无效')
            require(repair['handling'] == ('replace' if repair['points'] else 'context'), '修正去向不明确')
            for point in repair['points']:
                require(all(condition in point.get('conditions', []) for condition in targets[target]['required_conditions']),
                        '定点修正丢失了未被诊断为错误的原有前提，不能删除或移至附件')
                quality_point(point, passages[key]['text'])
            points.extend(deepcopy(repair['points']))
            if trace is not None:
                repaired_traces.extend({**deepcopy(trace), 'structural_repair_target': target, 'semantics_verified': False} for _ in repair['points'])
            decisions.append({'target_key': target, **deepcopy(repair)})
        entry['points'] = points
        if not points and any(target.startswith(key + ':') for target in targets):
            entry['note'] = {'handling': 'context', 'reason': '；'.join(d['reason'] for d in decisions if d['target_key'].startswith(key + ':'))}
    issues = parsed['source_issues']
    require(isinstance(issues, list) and all(isinstance(i, dict) and i.get('passage_key') in
            {v['passage_key'] for v in targets.values()} for i in issues), '修正来源疑点越界')
    output['source_issues'] = [*output['source_issues'], *deepcopy(issues)]
    output['_format_normalizations'] = sorted(set(output.get('_format_normalizations', [])) | set(parsed.get('_format_normalizations', [])))
    if original_traces is not None: output['_content_review_trace'] = repaired_traces
    record.update(status='validated', decisions=decisions)
    return output
