"""One visible correction request for precisely identified invalid point slots."""
from copy import deepcopy
from difflib import get_close_matches
import json
import re
from jsonschema import Draft202012Validator

from course_repository import CourseDocumentConflict
from generic_knowledge import require, normalized
from knowledge_compact import passage_catalog, parse_complete_json, obj, array, string
from knowledge_semantic_contract import quality_point, quality_prompt, point_variants, subject_options
from knowledge_correction_plan import correction_plan


class KnowledgeCorrectionNotApplicable(CourseDocumentConflict):
    """The compiler error has no invalid point that this transaction can edit."""


def specialize_schema(schema, value):
    """Select declared action/form branches so diagnostics name the bad field."""
    schema = deepcopy(schema)
    if 'anyOf' in schema and isinstance(value, dict):
        candidates = schema['anyOf']; selected = []
        for field in ('handling', 'form'):
            if field not in value: continue
            selected = [choice for choice in candidates if value[field] in
                choice.get('properties', {}).get(field, {}).get('enum', [choice.get('properties', {}).get(field, {}).get('const')])]
            if selected: break
        if not selected:
            selected = [choice for choice in candidates if set(value) <= set(choice.get('properties', {}))]
        if selected: return specialize_schema(selected[0], value)
    if isinstance(value, dict):
        for key, child in schema.get('properties', {}).items():
            if key in value: schema['properties'][key] = specialize_schema(child, value[key])
    elif isinstance(value, list) and isinstance(schema.get('items'), dict) and 'anyOf' in schema['items']:
        schema['prefixItems'] = [specialize_schema(schema['items'], item) for item in value]
        schema['items'] = False
    return schema


def repair_schema(targets, passages, *, expression_contract=None):
    repairs = {}
    for key, target in targets.items():
        choices = point_variants(subject_options(passages[target['passage_key']], contract='knowledge_extract_v9'), contract='knowledge_extract_v9')['anyOf']
        plan = target.get('correction_plan', {})
        allowed = plan.get('allowed_forms', [])
        form = (target['point']['form'] if target['point']['form'] in allowed else allowed[0]) if allowed else (
            'definition' if any(term in target.get('error', '') for term in ('联合定义', '仅说明机制')) else target['point']['form'])
        require(form in {'fact', 'definition', 'comparison', 'procedure'}, '无法精确限定修正形态')
        shape = next(choice for choice in choices if choice['properties']['form']['const'] == form)
        properties = shape['properties']
        for field, value in plan.get('fixed_fields', {}).items():
            if field in properties: properties[field] = {'const': deepcopy(value)}
        shape = obj({'form': properties['form'], **{k: v for k, v in properties.items() if k != 'form'}})
        shape['properties'] = properties
        replacement = obj({'points': array(shape, 1 if plan.get('single_point') else 8,
            1 if plan.get('single_point') else 0), 'handling': {'enum': ['replace'] if plan.get('single_point') else ['replace', 'context']}, 'reason': string(600)})
        alternatives = [replacement]
        if plan:
            patch_fields = {k: deepcopy(properties[k]) for k in plan['editable_fields'] if k in properties}
            patch = obj(patch_fields)
            patch['required'] = []
            patch['minProperties'] = 1
            if 'conditions' in patch_fields:
                # In a field patch, conditions are additive. The model never
                # needs to reproduce the original scope strings.
                patch_fields['conditions'] = array(string(1000), 20)
            # Conditions can be supplemented when repairing a subject qualifier;
            # omit them to preserve the original byte-for-byte.
            if not plan.get('required_symbols') and 'conditions' in patch['required']:
                patch['required'].remove('conditions')
            append_fields = {k: deepcopy(v) for k, v in patch_fields.items() if k != 'conditions'}
            append_fields['append_conditions'] = array(string(1000), 20, 1)
            append_patch = obj(append_fields); append_patch['required'] = []; append_patch['minProperties'] = 1
            alternatives.append(obj({'patch': {'anyOf': [patch, append_patch]}, 'handling': {'const': 'patch'}, 'reason': string(600)}))
        if target.get('duplicate_group'):
            alternatives.append(obj({'merge_into': {'enum': [k for k in target['duplicate_group'] if k != key]},
                'handling': {'const': 'merge'}, 'reason': string(600)}))
        if plan.get('context_allowed'):
            alternatives.append(obj({'points': array({}, 0), 'handling': {'const': 'context'}, 'reason': string(600)}))
        if plan.get('source_issue_allowed'):
            alternatives.append(obj({'points': array({}, 0), 'handling': {'const': 'source_issue'}, 'reason': string(600)}))
        allowed_forms = plan.get('allowed_forms', [form])
        if len(allowed_forms) > 1:
            # A cost present on only one side must become a fact, rather than a
            # comparison with an invented "unknown" answer on the other side.
            shapes = [deepcopy(c) for c in choices if c['properties']['form']['const'] in allowed_forms]
            replacement['properties']['points']['items'] = {'anyOf': shapes}
        repairs[key] = {'anyOf': alternatives} if len(alternatives)>1 else replacement
    issue = obj({'passage_key': {'enum': list(dict.fromkeys(v['passage_key'] for v in targets.values()))},
                 'kind': {'enum': ['suspected_error', 'contradiction']}, 'detail': string(1000)})
    result = obj({'repairs': obj(repairs), 'source_issues': array(issue, 16)})
    if expression_contract:
        result['properties']['short_statements'] = obj({key: array(string(200), 8) for key in targets})
        result['required'].append('short_statements')
    return result


async def repair_points(svc, course_id, job_id, provider, raw, context, keys, index, response, record, *, feedback=None):
    from knowledge_atomic import call_stage
    from knowledge_expression import check_contract, named_traces
    expression_contract = check_contract(context.get('expression_contract'))
    context = {**context, 'knowledge_passage_mode': 'source_blocks_v1'}
    passages = {p['key']: p for p in passage_catalog(context, keys)}
    require(isinstance(response.get('passages'), dict) and set(response['passages']) == set(passages), '片段结构错误不可按知识点修正')
    targets = {}; questions = {}; duplicate_groups = []; duplicate_resolutions = []
    for key, entry in response['passages'].items():
        require(isinstance(entry, dict) and isinstance(entry.get('points'), list), '片段结构错误不可按知识点修正')
        for ordinal, point in enumerate(entry['points']):
            try:
                compiled, _ = quality_point(point, passages[key]['text'], allow_literal_slash=bool(expression_contract))
                questions.setdefault(normalized(compiled['question']), []).append((key, ordinal, point, normalized(compiled['claim'])))
            except (CourseDocumentConflict, KeyError, TypeError, ValueError) as error:
                diagnostics = getattr(error, 'diagnostics', [{'code': 'invalid_point', 'message': str(error)}])
                targets[f'{key}:{ordinal}'] = {'point': point, 'error': str(error)[:400], 'passage_key': key,
                    'correction_plan': correction_plan(point, diagnostics)}
    for group in questions.values():
        if len({entry[3] for entry in group}) <= 1: continue
        group_keys = [f'{key}:{ordinal}' for key, ordinal, _, _ in group]
        duplicate_groups.append(group_keys)
        duplicate_resolutions.append({'target_keys': group_keys,
            'question': quality_point(group[0][2], passages[group[0][0]]['text'], allow_literal_slash=bool(expression_contract))[0]['question'],
            'answers': [quality_point(point, passages[key]['text'], allow_literal_slash=bool(expression_contract))[0]['claim'] for key, _, point, _ in group],
            'allowed_resolutions': ['merge_equivalent', 'different_questions']})
        for key, ordinal, point, _ in group:
            targets[f'{key}:{ordinal}'] = {'point': point, 'passage_key': key,
                'duplicate_group': group_keys,
                'error': '同一元问题存在不同答案措辞。必须先对照整组来源判断：语义等价则保留一个规范点，其余显式merge；含义不同则明确不同检查角度或成立前提。不能只批量重命名同一个property而留下不同答案，也不能丢弃知识。'}
    if not targets: raise KnowledgeCorrectionNotApplicable('没有可精确定位的知识点')
    require(len(targets) <= 16, '超出单次修正容量的知识点')
    for target in targets.values():
        if 'correction_plan' not in target:
            target['correction_plan'] = correction_plan(target['point'], [{'code': 'duplicate_question', 'message': target['error']}])
        conditions = target['point'].get('conditions', [])
        # Preserve unaffected scope exactly; diagnosed scope errors may be corrected.
        target['required_conditions'] = deepcopy(conditions) if isinstance(conditions, list) and (target.get('duplicate_group') or not re.search(
            r'前提|范围|串用|条件|联合定义', target.get('error', ''))) else []
        target['correction_plan']['conditions_mode'] = 'replace' if conditions and not target['required_conditions'] else 'append'
        if target.get('error') == '知识主体必须逐字来自当前原文块':
            target['fixed_fields'] = {k:deepcopy(v) for k,v in target['point'].items()
                if k not in {'subject','left_subject','right_subject'}}
        if target.get('correction_plan', {}).get('fixed_fields'):
            target['fixed_fields'] = deepcopy(target['correction_plan']['fixed_fields'])
        plan = target.get('correction_plan', {})
        target['literal_subjects'] = {}
        for field in ('subject', 'left_subject', 'right_subject'):
            if field not in plan.get('editable_fields', []): continue
            options = subject_options(passages[target['passage_key']]['text'], contract='knowledge_extract_v9')
            nearest = get_close_matches(target['point'][field], options, n=16, cutoff=0)
            target['literal_subjects'][field] = nearest
    payload = json.loads(quality_prompt(raw, context, keys).split('\nINPUT_JSON:\n')[1])
    payload.update(stage='extract_repair', targets=targets, duplicate_question_groups=duplicate_groups,
                   duplicate_resolution_required=duplicate_resolutions)
    if expression_contract:
        payload['expression_contract'] = expression_contract
    if feedback: payload['correction_feedback'] = deepcopy(feedback)
    prompt = quality_prompt(raw, context, keys).split('\nINPUT_JSON:\n')[0] + (
        '\n只修正targets，修正合同knowledge_correction_plan_v2，一轮请求。每个目标恰好回应一次。'
        'correction_plan.single_point=true时只返回handling="patch",patch={仅需修改的字段},reason；'
        '绝不重新输出完整点、公式或正确字段。程序将patch应用到冻结原点，fixed_fields由程序保留。'
        '主体从当前source_passages逐字选择，literal_subjects只是候选提示而非封闭名录。主体中原有的最好/最坏等实际范围若不在新主体中，补到conditions，避免丢失含义。'
        'source_issue_allowed=true且原块实际没有该命题时，必须返回handling="source_issue",points=[],reason="具体缺少何种证据"，并在source_issues登记该passage_key。'
        '不能为满足冻结答案改成另一结构，不能把不同算法的结论移植过来；来源不足有明确出口，不强迫凑出一个知识点。理由简短，最多120字。'
        '补充前提使用patch.append_conditions=[新增前提]，程序原样保留原conditions并追加；不要抄写已有前提。'
        '完整replace或拆分的新点也由程序继承required_conditions，不必重复抄写这些冻结前提；只填写新增前提，合成后仍统一校验。'
        'conditions_mode="replace"表示原前提本身被诊断为错误，此时patch.conditions整体替换，可为[]；append_conditions仍仅追加。'
        '主体已正确时不要重新输出subject。无需增加前提时省略append_conditions。'
        'required_symbols每个符号在conditions定义输入或计量对象，例如n表示待排序元素数；只写O(n)不算定义。'
        '没有single_point限制时可使用patch修改需要的字段，或handling="replace",points=[完整修正点],reason；无一般知识时明确context且points=[]。'
        'correction_feedback若存在，是本事务前一次修正未通过的完整诊断，必须修正该错误，不能照抄失败答案。'
        'comparison的左右subject必须为不同的实际结构或算法，不能都写“递归深度”等属性再用前提区别。'
        'context_allowed=true的目标是绑定n=8等具体输入的示例比较，可归context保留在记录，不冒充通用知识。'
        '复合属性必须拆为不同属性；每点自己定义符号；一个成本仅在一侧有来源时用fact，不编造对侧答案来凑comparison。'
        '诊断compound_property明确指property字段，不能只改conditions。property不使用与/和/及/顿号连接多个维度；单一对应规律可用“对应规律”命名并保留原关系结论。'
        '每个fact.value及comparison左右value均不能有分号或多个句子；复杂度须用时间/空间/次数等成本属性。'
        '方法缺少初始状态且诊断仅说明机制时改definition；完整算法和联合定义保留共同约束与全部分支。'
        'duplicate_question_groups必须作为一组对照来源：若仅同义措辞，选择一个目标为规范点，其他目标返回'
        'handling="merge",merge_into="该规范目标键",reason="两条原文为何等价"；规范点仍返回replace。'
        '合并不得形成链或环，不能合并组外知识。程序将保留各自来源、附件及等价判断记录。'
        '若含义不同必须明确不同的检查属性或成立前提，使元问题可区分，不能把同一个property给两条不同答案。'
        'duplicate_resolution_required逐组列出实际元问题和答案，必须解决整组，不是只润色属性名。'
        '例如“某排序稳定性为稳定”与“某排序稳定性为是”若来源同义，应一个规范点replace，其余merge到该点；'
        '不要把全组property都改为“排序稳定性”后仍留下“稳定/是”两种答案。不能用context删除这类有效知识。'
        '不删除有效知识以避开问题，不把实质问题归背景；仅来源不足、具体轨迹、教学目标或疑点可归context并说明。'
        '只输出{"repairs":{"目标键":{"handling":"patch","patch":{"subject":"原文主体"},"reason":"具体修改"}},"source_issues":[]}。'
        '\nINPUT_JSON:\n'
    ) + json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    if expression_contract:
        prompt = prompt.replace('\nINPUT_JSON:\n',
            '本任务还冻结knowledge_expression_v1。顶层另给short_statements对象，键为全部targets；'
            '每个值是该目标修正后的短陈述数组，与最终点逐项同序：patch为1项，replace与points同数，context/source_issue为[]。'
            '名称使用简短陈述句，与修正后完整命题、继承的条件及当前来源一致；不沿用已失效旧名称。'
            'merge与其规范目标的名称数组完全相同。只修正已授权语义字段，不为短名改写其他命题。\nINPUT_JSON:\n', 1)
        record['expression_contract'] = expression_contract
    record.update(status='requested', contract='knowledge_correction_plan_v2', target_keys=list(targets), targets=deepcopy(targets))
    text = await call_stage(svc, course_id, job_id, provider, prompt, 'extract_repair')
    record['raw_response'] = text
    parsed = parse_complete_json(text)
    required = {'repairs', 'source_issues'} | ({'short_statements'} if expression_contract else set())
    require(isinstance(parsed, dict) and set(parsed) - {'_format_normalizations'} == required
            and isinstance(parsed['repairs'], dict) and set(parsed['repairs']) == set(targets), '修正越界或未完整回应目标')
    clean = {k: v for k, v in parsed.items() if k != '_format_normalizations'}
    schema = repair_schema(targets, {k: p['text'] for k, p in passages.items()}, expression_contract=expression_contract)
    schema = specialize_schema(schema, clean)
    for key, decision in parsed['repairs'].items():
        shape = schema['properties']['repairs']['properties'][key]
        for choice in shape.get('anyOf', [shape]):
            handling = choice['properties']['handling']
            if decision.get('handling') in handling.get('enum', [handling.get('const')]):
                schema['properties']['repairs']['properties'][key] = choice
                patch = choice['properties'].get('patch')
                if patch and 'anyOf' in patch:
                    choice['properties']['patch'] = patch['anyOf'][1 if 'append_conditions' in decision.get('patch', {}) else 0]
                break
    errors = list(Draft202012Validator(schema).iter_errors(clean))[:32]
    error_label = '修正响应字段或前提无效（主体等未授权字段不可改动）：'
    require(not errors, error_label + '；'.join('/'.join(str(k) for k in error.absolute_path) + '：' + error.message[:300] for error in errors))
    resolved = {}
    for key, repair in parsed['repairs'].items():
        if repair['handling'] == 'merge': continue
        if repair['handling'] == 'source_issue':
            require(any(i.get('passage_key') == targets[key]['passage_key'] for i in parsed['source_issues']),
                    '来源不足的修正必须登记对应块的具体疑点')
            resolved[key] = {**deepcopy(repair), 'handling': 'context', 'action': 'source_issue'}
            continue
        if repair['handling'] == 'patch':
            patch = deepcopy(repair['patch']); additions = patch.pop('append_conditions', [])
            conditions = patch.pop('conditions', None)
            point = {**deepcopy(targets[key]['point']), **patch}
            if conditions is not None:
                if targets[key]['correction_plan']['conditions_mode'] == 'replace': point['conditions'] = conditions
                else: additions.extend(conditions)
            if additions: point['conditions'] = list(dict.fromkeys([*point['conditions'], *additions]))
            resolved[key] = {'handling': 'replace', 'points': [point],
                             'reason': repair['reason'], 'action': 'field_patch'}
        else: resolved[key] = deepcopy(repair)
    for key, repair in parsed['repairs'].items():
        if repair['handling'] != 'merge': continue
        canonical = resolved.get(repair['merge_into'])
        require(parsed['repairs'][repair['merge_into']]['handling'] != 'merge'
                and canonical and canonical['handling'] == 'replace' and len(canonical['points']) == 1,
                '等价合并不能形成链、环或指向空知识')
        point = deepcopy(canonical['points'][0])
        point['attachments'].extend(deepcopy(a) for a in targets[key]['point'].get('attachments', []) if a not in point['attachments'])
        resolved[key] = {'handling': 'replace', 'points': [point], 'reason': repair['reason'],
                         'action': 'model_declared_equivalence', 'merge_into': repair['merge_into']}
    output = deepcopy(response); decisions = []; point_errors = []
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
            repair = resolved[target]
            require(isinstance(repair, dict) and not set(repair) - {'points', 'handling', 'reason', 'action', 'merge_into'}
                    and isinstance(repair['points'], list) and len(repair['points']) <= 8
                    and isinstance(repair['reason'], str) and repair['reason'].strip(), '修正结构无效')
            require(repair['handling'] == ('replace' if repair['points'] else 'context'), '修正去向不明确')
            if targets[target].get('fixed_fields') and repair.get('action') != 'source_issue' and not (targets[target].get('correction_plan', {}).get('context_allowed') and not repair['points']):
                fixed = targets[target]['fixed_fields']
                require(len(repair['points']) == 1 and all(repair['points'][0].get(k) == v for k,v in fixed.items()),
                        '定点修正违反冻结字段：主体或前提以外的正确内容不得改变或拆分')
            for point in repair['points']:
                point['conditions'] = list(dict.fromkeys([*targets[target]['required_conditions'], *point.get('conditions', [])]))
                require(all(condition in point.get('conditions', []) for condition in targets[target]['required_conditions']),
                        '定点修正丢失了未被诊断为错误的原有前提，不能删除或移至附件')
                try: quality_point(point, passages[key]['text'], allow_literal_slash=bool(expression_contract))
                except CourseDocumentConflict as error:
                    point_errors.append({'target_key': target, 'message': str(error),
                        'diagnostics': deepcopy(getattr(error, 'diagnostics', []))})
            points.extend(deepcopy(repair['points']))
            if trace is not None:
                repaired_trace = {**deepcopy(trace), 'structural_repair_target': target, 'semantics_verified': False}
                if expression_contract:
                    names = parsed['short_statements'][target]
                    if repair.get('merge_into'):
                        require(names == parsed['short_statements'][repair['merge_into']], '等价知识的短陈述须使用规范目标')
                    repaired_traces.extend(named_traces(names, repair['points'], passages[key]['text'], repaired_trace))
                else:
                    repaired_traces.extend(deepcopy(repaired_trace) for _ in repair['points'])
            decisions.append({'target_key': target, **deepcopy(repair),
                              'program_preserved_conditions': deepcopy(targets[target]['required_conditions'])})
        entry['points'] = points
        if not points and any(target.startswith(key + ':') for target in targets):
            entry['note'] = {'handling': 'context', 'reason': '；'.join(d['reason'] for d in decisions if d['target_key'].startswith(key + ':'))}
    require(not point_errors, '；'.join(v['target_key'] + '：' + v['message'] for v in point_errors))
    for group in duplicate_groups:
        remaining = {}
        for target in group:
            require(bool(resolved[target]['points']), '重复元问题不能通过丢弃有效知识规避：' + target)
            for point in resolved[target]['points']:
                compiled, _ = quality_point(point, passages[targets[target]['passage_key']]['text'], allow_literal_slash=bool(expression_contract))
                remaining.setdefault(normalized(compiled['question']), []).append((target, compiled['claim']))
        for question, entries in remaining.items():
            require(len({normalized(claim) for _, claim in entries}) <= 1,
                '重复元问题尚未解决：' + '；'.join(f'{target}={claim}' for target, claim in entries)
                + '。须明确等价merge或不同检查角度，不能仅批量重命名属性。')
    issues = parsed['source_issues']
    require(isinstance(issues, list) and all(isinstance(i, dict) and i.get('passage_key') in
            {v['passage_key'] for v in targets.values()} for i in issues), '修正来源疑点越界')
    output['source_issues'] = [*output['source_issues'], *deepcopy(issues)]
    output['_format_normalizations'] = sorted(set(output.get('_format_normalizations', [])) | set(parsed.get('_format_normalizations', [])))
    if original_traces is not None: output['_content_review_trace'] = repaired_traces
    record.update(status='validated', decisions=decisions)
    return output


async def correct_points(svc, course_id, job_id, provider, raw, context, keys, index, response, record,
                         *, compile_result, validate_source, max_attempts=1):
    """A finite correction transaction; never repeats extraction or retries transport."""
    require(max_attempts in {1, 2}, '定点修正预算无效')
    attempts = []; feedback = None
    for ordinal in range(1, max_attempts + 1):
        attempt = {'ordinal': ordinal, 'status': 'pending'}
        try:
            validate_source()
            corrected = await repair_points(svc, course_id, job_id, provider, raw, context, keys, index,
                                            response, attempt, feedback=feedback)
            validate_source()
            compiled = compile_result(corrected)
            attempt['status'] = 'completed'
            attempts.append(deepcopy(attempt)); record.update(**attempt, attempts=attempts)
            return corrected, compiled
        except Exception as error:
            if hasattr(error, 'partial_response'):
                attempt.update(raw_response=error.partial_response, response_complete=False)
            attempt.update(status='failed', validation_error={'code': type(error).__name__, 'message': str(error)})
            attempts.append(deepcopy(attempt)); record.update(**attempt, attempts=attempts)
            validate_source()  # ownership/source changes always stop immediately
            if not isinstance(error, (CourseDocumentConflict, ValueError, TypeError, KeyError)): raise
            if ordinal == max_attempts or not attempt.get('target_keys'): raise
            feedback = {'diagnostic': str(error), 'failed_correction_response': attempt.get('raw_response', '')}
