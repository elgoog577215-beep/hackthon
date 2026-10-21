"""One finite truth-only pass; no taxonomy, examples or teaching checks as input."""
from copy import deepcopy
from knowledge_registry_contract import FIELDS, render, validate_point

CONTRACT='knowledge_truth_review_v1'


def truth_prompt(points, context):
    return render(
        '只审查冻结知识核心的学科真值，不判断粒度，不去重，不生成名称或教学档案。'
        '对全称、必然、充要和必须使用某方法的命题，主动寻找满足条件的反例或另一条有效途径。'
        '区分知识结论和教学建议；教材当前例子可用的方法不能升级为所有情况必须使用的方法。'
        '保留冻结课程领域、量含义及版本，不通过换领域规避错误。每个key恰好给一个audit。'
        'verdict为valid表示本轮未发现反例，point必须为null；uncertain保留待核对，point为null。'
        '确有错误才用corrected，point给出修正后的单条完整知识，不额外新增知识，不改变身份。'
        'reason一句话，test_case给实际检验或反例及比较结果；不是形式检查，不把未验证自评当证明。'
        '输出{"audits":{"key":{"verdict":"valid","reason":"核对结论","test_case":"具体检验",'
        '"point":null}}}。corrected的point含statement,knowledge_type,conditions,symbol_definitions,teaching_context,examples。',
        {'stage':'candidate_truth_review','contract':CONTRACT,'course_context':deepcopy(context),
         'points':[{k:p.get(k) for k in ('key','statement','conditions','symbol_definitions','knowledge_type')} for p in points]})


def compile_audits(value, originals):
    audits=value.get('audits') if isinstance(value,dict) and set(value)=={'audits'} else None
    if not isinstance(audits,dict) or set(audits)!={p['key'] for p in originals}:
        raise ValueError('真值核对须完整处理冻结keys')
    result={'points':[],'issues':[],'audits':deepcopy(audits)}
    for original in originals:
        key=original['key'];row=audits[key]
        if (not isinstance(row,dict) or set(row)!={'verdict','reason','test_case','point'}
                or any(not isinstance(row[k],str) or not row[k].strip() or len(row[k])>1800 for k in ('reason','test_case'))
                or row['verdict'] not in {'valid','corrected','uncertain'}):
            raise ValueError(key+'：真值核对字段或结论无效')
        point=deepcopy(original)
        if row['verdict']=='corrected':
            facts=validate_point(row['point'])
            if all(facts[k]==original[k] for k in ('statement','conditions')):
                raise ValueError(key+'：无效修正，必须修改被推翻的知识核心')
            point.update(facts)
        elif row['point'] is not None:
            raise ValueError(key+'：valid/uncertain不能夹带改写')
        if row['verdict']=='uncertain':
            point['review_pending']=True
            result['issues'].append({'code':'knowledge_truth_pending','severity':'blocking','point_key':key,'message':row['reason']})
        point['truth_review']={'contract':CONTRACT,**deepcopy(row),'semantics_verified':False}
        result['points'].append(point)
    return result
