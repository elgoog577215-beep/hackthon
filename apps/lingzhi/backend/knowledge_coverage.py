"""Learning-unit coverage, independent of literal material/source matching."""
from copy import deepcopy

from knowledge_registry_contract import FIELDS, render, validate_point

CONTRACT = 'knowledge_coverage_v1'


def plan_prompt(raw, context, materials, focus):
    return render(
        '先列本讲完整的独立知识清单，不写概括性摘要、不生成分类树或练习。逐个主题检查定义、规则、判断和必要的特殊情况。'
        '一个清单项必须能完整讲解、单独检查和补学。多个独立规则不能因同属一个法则而合成一项。'
        '常数求导、常数倍求导、和差求导应分别列项；乘积或商求导的完整公式保持整体，不把因子、符号顺序拆成叶子。'
        '几何对象的定义、斜率关系、方程和需要不同处理的特殊情况分别考虑；不能只保留最终方程。'
        '同一结论的逆否表达、同一公式换记号和重复例子不增加独立项；一般命题与算例分开。'
        '先识别最外层运算选择方法，不生成“复合函数唯一只能用某法则”等绝对断言。'
        'statement直接表达知识，branch是主题；check_intent写一个可观察的独立检查目标，不写学生已经掌握或已经犯错。'
        'profile_focus仅从给定teaching_focus选择最贴合的一项，不属于这些分支填空字符串。'
        '数量由内容决定，不按固定数量凑点；不要遗漏容易藏在综合描述中的独立知识。'
        '输出{"units":[{"statement":"完整知识陈述","branch":"主题","knowledge_type":"rule",'
        '"profile_focus":"","check_intent":"检查这一知识的具体表现"}]}。knowledge_type为definition/rule/method/comparison。',
        {'stage':'coverage_plan','contract':CONTRACT,'course_title':raw.get('course_name'),
         'lesson_id':context['scope_lesson_id'],'materials':materials,'teaching_focus':focus})


def review_prompt(units, materials, focus):
    return render(
        '逐项审阅知识清单，另列遗漏知识。每个draft_unit key必须有且只有一个处理决定，不重新总结整份清单。'
        '学生可能会一条结论却不会另一条，并且两条各能完整讲解、检查、补学时，拆分。'
        '对象定义、数值关系和表示方程应分别考虑；一个综合公式不能替代其中独立可学的基础规则。'
        '同一完整公式内部的因子、符号、操作步骤不拆叶子；同结论的逆否表达、换记号不拆叶子。'
        '每个原项可keep保留、replace纠错或拆分；replace必须保留该项全部有效独立知识，不能吞并其他原项。'
        '只有原项完全重复一个或多个保留项、没有新增知识且范围相同，才能covered，给出targets和明确布尔声明complete_coverage=true、adds_knowledge=false、same_scope=true；不能仅因主题相近就covered。'
        '再逐段阅读全文，检查尚未登记的对象定义、量的含义、数学表示、规则、方法和特殊情况，填写additions。'
        '特别检查指定teaching_focus的完整教学链：对象是什么、量之间的关系、表达与应用、边界情况。'
        '材料里有明确段落或小标题介绍而清单遗漏的独立知识也要补充。'
        '补充允许概括和必要背景，不要求逐字出现或绑定原文片段；不把具体答案升级为一般规则。'
        '修正过强断言、缺失条件和错误关系；不新增重复组合、同义、逆否知识。'
        'check_intent写可观察检查目标，profile_focus用指定分支或空字符串，相关基础子规则也归对应分支。'
        '输出{"decisions":{"U1":{"action":"keep","reason":"完整独立知识"},'
        '"U2":{"action":"replace","reason":"拆开独立结论","units":[{"statement":"完整知识",'
        '"branch":"主题","knowledge_type":"rule","profile_focus":"","check_intent":"检查目标"}]}}},'
        '"additions":[{"statement":"遗漏知识","branch":"主题","knowledge_type":"definition",'
        '"profile_focus":"","check_intent":"检查目标"}]}。'
        'knowledge_type仅为definition/rule/method/comparison。无新增时additions为空数组。',
        {'stage':'coverage_review','contract':CONTRACT,'draft_units':units,'materials':materials,'teaching_focus':focus})


def apply_review(value, units, focus):
    decisions=value.get('decisions') if isinstance(value,dict) else None
    if not isinstance(decisions,dict) or set(decisions)!={u['key'] for u in units}:
        raise ValueError('清单审阅必须逐项处理所有原清单ID，不得丢失或新增原ID')
    result=[]
    for unit in units:
        decision=decisions[unit['key']]
        if not isinstance(decision,dict) or not isinstance(decision.get('reason'),str) or not decision['reason'].strip():
            raise ValueError('清单审阅须说明处理理由')
        if decision.get('action')=='keep' and set(decision)=={'action','reason'}:
            result.append({k:v for k,v in unit.items() if k!='key'})
        elif decision.get('action')=='replace' and set(decision)=={'action','reason','units'}:
            revised=parse_plan({'units':decision['units']},focus)
            result.extend({k:v for k,v in u.items() if k!='key'} for u in revised)
        elif decision.get('action')=='covered' and set(decision)=={'action','reason','targets','complete_coverage','adds_knowledge','same_scope'}:
            targets=decision['targets']
            if (not isinstance(targets,list) or not targets or len(set(targets))!=len(targets)
                    or any(not isinstance(k,str) or k==unit['key'] or k not in decisions or decisions[k].get('action') not in {'keep','replace'} for k in targets)
                    or decision['complete_coverage'] is not True or decision['adds_knowledge'] is not False or decision['same_scope'] is not True):
                raise ValueError('重复清单项必须完整对应明确保留项，不能部分对应、成链或新增知识')
        else:
            raise ValueError('清单审阅须保留、显式替换或完整对应重复项，不能删除有效独立知识')
    additions=value.get('additions')
    if not isinstance(additions,list):
        raise ValueError('清单审阅须显式给出新增知识列表')
    result.extend(additions)
    return parse_plan({'units':result},focus)


FOCUS_FACETS = ('concepts','rules','representations','methods','boundary_cases')


def focus_prompt(focus, units, materials):
    return render(
        '为focus分支建立细颗粒度知识清单，按下面五个视角分别填写，不把整个分支压成几条综合摘要。'
        'concepts：学习对象是什么，定义和基本含义。rules：量或对象间的独立规律。'
        'representations：对象或关系的完整表示，例如表达式、方程或数据结构。'
        'methods：有独立教学价值的完整方法。boundary_cases：必须改变处理方式的特殊情况。'
        '每组可为空；每条必须是可单独讲解、检查和补学的完整知识。'
        '同一对象的定义、数值关系与方程是不同学习内容，分别放入合适视角，不把它们粘在一条里。'
        '同一公式的因子、符号、局部步骤保持整体；适用条件附在对应规则中，不另造条件叶子。'
        '常见失误、换记号、逆否表达、重复组合不增加知识。不要补一个仅把已有基础规则重新组合的综合叶子。'
        'draft_units是需保留的有效知识范围，允许重新组织和拆分；各输出条的covers列出其承载的原清单key。'
        '原清单所有key至少对应一个输出条；遗漏知识covers为空。一个完整公式及其条件必须仍完整保留。'
        '逐段阅读材料，补齐本分支缺失的对象定义与表示，允许概括与必要背景，不要求原文逐字匹配。'
        'existing_other_units已有知识不要重复生成，用include_existing引用其key。'
        '输出{"facets":{"concepts":[{"statement":"完整知识","branch":"主题","knowledge_type":"definition",'
        '"profile_focus":"分支名","check_intent":"可观察检查目标","covers":["原key"]}],'
        '"rules":[],"representations":[],"methods":[],"boundary_cases":[]},"include_existing":[]}。'
        'knowledge_type仅为definition/rule/method/comparison；不写学生画像。',
        {'stage':'coverage_focus','contract':CONTRACT,'focus':focus,
         'draft_units':[u for u in units if u['profile_focus']==focus],
         'existing_other_units':[u for u in units if u['profile_focus']!=focus], 'materials':materials})


def parse_focus(value, focus, units):
    selected={u['key'] for u in units if u['profile_focus']==focus}
    facets=value.get('facets') if isinstance(value,dict) else None
    if not isinstance(facets,dict) or set(facets)!=set(FOCUS_FACETS):
        raise ValueError('分支清单必须逐个填写五个教学视角，允许空组')
    rows=[];covered=set()
    for facet in FOCUS_FACETS:
        if not isinstance(facets[facet],list):raise ValueError('教学视角必须是知识列表')
        for row in facets[facet]:
            covers=row.get('covers') if isinstance(row,dict) else None
            if not isinstance(covers,list) or any(not isinstance(key,str) or key not in selected for key in covers):
                raise ValueError('分支清单承载了未知原清单ID')
            covered.update(covers)
            rows.append({k:v for k,v in row.items() if k!='covers'})
    if covered!=selected:raise ValueError('分支清单遗漏原有独立知识：'+','.join(sorted(selected-covered)))
    revised=parse_plan({'units':rows},[focus]) if rows else []
    included=value.get('include_existing')
    others={u['key']:u for u in units if not u['profile_focus']}
    if not isinstance(included,list) or any(not isinstance(k,str) or k not in others for k in included) or len(set(included))!=len(included):
        raise ValueError('分支审阅只能引用已有且尚未归属其他试点分支的知识ID')
    for unit in revised:unit['profile_focus']=focus
    return {'units':revised,'include_existing':included}


def combine_focus(units, reviews, focus):
    included={}
    for review in reviews:
        for key in review['result']['include_existing']:
            if key in included:raise ValueError('同一知识被多个试点分支重复领取')
            included[key]=review['focus']
    rows=[{**{k:v for k,v in u.items() if k!='key'},'profile_focus':included.get(u['key'],u['profile_focus'])}
          for u in units if u['profile_focus'] not in focus]
    rows.extend({k:v for k,v in u.items() if k!='key'} for review in reviews for u in review['result']['units'])
    return parse_plan({'units':rows},focus)


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
