"""Add only a missing optional teaching object or its explicit rationale."""
from copy import deepcopy
from jsonschema import Draft202012Validator
from knowledge_registry_contract import render
from knowledge_teaching_contract import response_schema,text,obj,TeachingDesignInvalid

CONTRACT='knowledge_teaching_completion_v1'


def completion_schema(field,catalog):
    if field not in {'mistakes','extensions'}:raise TeachingDesignInvalid('未知教学补充字段')
    items=response_schema(['focus'],[p['key']for p in catalog])['properties'][field]
    return obj({'objects':{**deepcopy(items),'maxItems':1},'reason':text(180,True)})


def completion_prompt(tree,key,field):
    catalog=tree['knowledge_points'];point=next(p for p in catalog if p['key']==key)
    return render('仅补充指定知识点缺失的一项教学配套，禁止改写知识、检查标准、已生成对象或其他字段。'
        'field=extensions时生成一项有内容的选学知识、应用或条件对比；field=mistakes时生成一个可辨别的潜在错误假设，不能声称学生已经犯错。'
        'objects中的knowledge_keys必须包含当前knowledge_key，也可关联catalog的已有知识。只补当前缺口，不复制其他教学内容。'
        '若确实没有合适内容，objects为空，reason写出针对该知识及本讲范围的具体原因；不能只写无需、暂不需要或虚构理由凑数。'
        '没有学生作答、尚未采用候选或处于基础阶段不构成省略理由。原因也只是待审教学建议，不代表教学质量已经确认。'
        '不要返回points、criteria或解释性正文。只返回符合output_schema的完整JSON。',
        {'stage':'candidate_teaching_completion','contract':CONTRACT,'knowledge_key':key,'field':field,
         'focus':{k:deepcopy(point.get(k))for k in ('key','name','statement','conditions','kc_skill_profile')},
         'catalog':[{k:deepcopy(p.get(k))for k in ('key','name','statement','conditions')}for p in catalog],
         'output_schema':completion_schema(field,catalog)})


def compile_completion(value,key,field,catalog):
    errors=list(Draft202012Validator(completion_schema(field,catalog)).iter_errors(value))
    if errors:raise TeachingDesignInvalid('教学补充响应不符合约定：'+errors[0].message)
    if not value['objects'] and not value['reason'].strip():raise TeachingDesignInvalid(f'{key} 仍缺少教学对象或具体原因')
    if any(key not in row['knowledge_keys']for row in value['objects']):raise TeachingDesignInvalid('教学补充未关联指定知识点')
    return deepcopy(value)


def merge_completion(result,key,field,patch):
    merged=deepcopy(result);used={r['key']for r in merged[field]}
    for row in patch['objects']:
        added=deepcopy(row);original=added['key'];counter=1
        while added['key']in used:
            added['key']=f'{original}_{counter}';counter+=1
        used.add(added['key']);merged[field].append(added)
    if not patch['objects']:
        merged['points'][key]['no_mistakes'if field=='mistakes'else 'no_extensions']=patch['reason']
    merged.pop('pending_fields',None)
    return merged
