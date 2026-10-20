"""Learning-unit coverage, independent of literal material/source matching."""
from copy import deepcopy

from knowledge_registry_contract import FIELDS, render, validate_point

CONTRACT = 'knowledge_coverage_v1'


def parse_plan(value, focus):
    units=value.get('units') if isinstance(value,dict) else None
    if not isinstance(units,list) or not 1<=len(units)<=120:
        raise ValueError('知识清单须有1至120个独立项')
    result=[]
    for i,row in enumerate(units,1):
        if not isinstance(row,dict) or set(row)!={'statement','branch','knowledge_type','profile_focus','check_intent'}:
            raise ValueError('清单项字段不完整')
        if any(not isinstance(row[f],str) or not row[f].strip() or len(row[f])>1200 for f in ('statement','branch','check_intent')):
            raise ValueError('清单项须说明完整知识、主题和检查目标')
        if row['profile_focus'] not in ['',*focus] or row['knowledge_type'] not in {'definition','rule','method','comparison'}:
            raise ValueError('清单项分支或类型无效')
        result.append({**deepcopy(row),'key':f'U{i}'})
    return result


def units_prompt(units, materials, catalog):
    return render(
        '逐项展开冻结知识清单，为每个unit key返回完整知识。允许通俗改写和跨段概括。'
        '每项通常一个点；只有清单项确实包含多个独立知识时才拆分。不得将不同unit压成一个摘要，也不能遗漏任何unit。'
        '每点完整保留结论、公式及必要限定。conditions只放真实适用条件，symbol_definitions放变量含义，'
        'teaching_context放情境，examples放应用实例。检查角度和失误提醒不作为额外知识点。'
        '不生成名称或正式ID。不要把具体题目答案当一般规则。'
        '输出{"points":{"U1":[{"statement":"完整知识","knowledge_type":"rule","conditions":[],'
        '"symbol_definitions":[],"teaching_context":[],"examples":[]}]}}。每个unit key恰好出现一次。',
        {'stage':'coverage_extract','contract':CONTRACT,'units':units,'materials':materials,
         'existing_knowledge':[{k:p.get(k) for k in ('key','name',*FIELDS)} for p in catalog]})


def parse_unit_points(value, units, materials):
    points=value.get('points') if isinstance(value,dict) else None
    if not isinstance(points,dict) or set(points)!={u['key'] for u in units}:
        raise ValueError('展开结果必须恰好覆盖本批所有知识清单ID')
    result=[]
    for unit in units:
        rows=points[unit['key']]
        if not isinstance(rows,list) or not 1<=len(rows)<=4:
            raise ValueError(unit['key']+'须有完整知识，不能用空数组跳过')
        for i,row in enumerate(rows,1):
            result.append({**validate_point(row),'key':unit['key']+'P'+str(i),
                'coverage_unit_ids':[unit['key']],'profile_focus':unit['profile_focus'],
                'check_intents':[unit['check_intent']],'input_material_keys':list(materials)})
    return result


def coverage_report(units, points):
    mapping={u['key']:[] for u in units}
    for point in points:
        for uid in point.get('coverage_unit_ids',[]):
            if uid not in mapping:
                raise ValueError('知识引用了未知清单项：'+uid)
            mapping[uid].append(point.get('knowledge_id') or point['key'])
    missing=[key for key,ids in mapping.items() if not ids]
    return {'contract':CONTRACT,'unit_count':len(units),'covered_unit_count':len(units)-len(missing),
            'missing_unit_ids':missing,'unit_points':mapping,'semantics_verified':False}
