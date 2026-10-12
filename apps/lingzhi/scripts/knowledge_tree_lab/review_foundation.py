"""Source-by-source review of the foundation experiment, no model edits."""
import argparse
from pathlib import Path
from .pipeline import read,save,digest
from .foundation_round import validate_inventory,validate_atoms,assemble,REQUIREMENTS

MAPPINGS={
 'python':[(['C1'],['P1']),(['C2'],['P2']),(['C3'],['P3']),(['C4'],['P4']),(['C5'],['P5']),(['C6'],['P6']),(['C7'],['P7']),(['C8'],['P8'])],
 'calculus':[(['C1'],['P1']),(['C2'],['P2']),(['C3'],['P3']),(['C4'],['P4']),(['C5'],['P5']),(['C6'],['P7']),(['C8'],['P6']),(['C9'],['P8']),(['C7'],['P4','P7','P8'])],
 'physics':[(['C1'],['P1']),(['C1'],['P1']),(['C1'],['P1']),(['C2'],['P2']),(['C2'],['P2']),(['C3'],['P1','P2']),(['C4'],['P3']),(['C5'],['P4']),(['C6'],['P5']),(['C7'],['P6']),(['C8'],['P7'])],
 'history':[(['C1'],['P1']),(['C1'],['P1']),(['C2'],['P2']),(['C3'],['P3']),(['C4'],['P4']),(['C5'],['P5']),(['C5'],['P5']),(['C6'],['P6']),(['C7'],['P7']),(['C8'],['P8']),(['C9','C10'],['P9','P10']),(['C11','C12','C13','C14'],['P1','P2','P3','P5','P6','P9','P10'])]}
REVIEWS={
 'python':{'accuracy':'核心规则符合材料；P4引用支撑需补全','coverage':'8/8要求有承载；普通列表范围保留为全局限制及附件',
   'granularity':'大体清楚，P4仍需收窄','structure':'树结构合法；外层分类可更整齐',
   'improvements':['新建外层、外层append、内层引用共享、共享内层append、元素引用替换分别保留。','没有生成题目、迁移或深拷贝操作答案。'],
   'issues':[['P4.statement / meta_question','“新外层”又包含元素引用关系，与P6部分重复；元问题同时问深浅拷贝、外层与元素。建议只保留新外层身份，把元素引用交给P6。'],
             ['P4.claim_refs','仅引用C4的“新建外层”片段，却陈述元素引用规则；完整M2有依据，但逐点证据映射需补C6或收窄正文。'],
             ['P1.conditions','“a和b是列表变量”容易被读成b必须事先存在；改成a引用普通列表、执行b=a即可。'],
             ['G2/G21 placements','P4挂在浅拷贝总类，P5单独挂外层子类；把P4/P5并列放入外层类会更清楚。']]},
 'calculus':{'accuracy':'主命题正确；P8答案有歧义','coverage':'9/9要求有承载；反例作为附件保留',
   'granularity':'四种推理方向分开；范围不应独立成叶子','structure':'分类合法；范围类需转为元数据',
   'improvements':['正向、逆否、连续不能推可导、不可导不能推不连续分别成点。','绝对值反例没有继续冒充通用知识叶子。'],
   'issues':[['P1 / G1','“仅讨论内点”又被生成为范围叶子及分类；应作为全局范围并继承到相关点，不计作元知识。'],
             ['P2-P8.conditions','点内只写属于定义域，全局范围才写内点；单点展示或导出必须带上全局范围，不能丢失双侧/内点限制。'],
             ['P8.meta_answer','“不可导不包含不连续”表述不准确；应为“仅知不可导不能推出不连续”。不连续反而是不可导情形的子集。']]},
 'physics':{'accuracy':'主陈述保留了必要条件与推断限制','coverage':'11/11要求有承载；加速度边界通过附件保留',
   'granularity':'明显不够细，P1/P2需要拆分','structure':'分类合法，单体与系统可再分组',
   'improvements':['加速度不可推断边界留在清单C3并关联P1/P2，没有凭空补F=ma算题。','平衡力写为必须同一受力对象，没有写成同对象就必平衡。'],
   'issues':[['P1','大小、方向、受力对象三个可独立判断的属性仍合在一叶，元问题也一次问三件事。'],
             ['P2','不要求等质量与不要求静止仍合并，应按两种独立前提拆开。'],
             ['C3→P1/P2','原子化正文的boundaries为空，重要加速度边界仅在清单去向中；程序已把原清单内容装配为显式附件，展示不可省略。映射理由提到动力学结果差异不应被当作“加速度必不同”。'],
             ['P5.meta_question','“需要满足什么条件”容易读成完整平衡判据，应明确只问受力对象这一必要条件。'],
             ['G2','同一大类含单物体受力图和平衡判断、整体系统内外力；可分为单体与系统两个子组。']]},
 'history':{'accuracy':'主要规则忠实；结论强度措辞需收紧','coverage':'12/12要求有承载；A/B/C及缺证据保留为案例附件',
   'granularity':'比前轮清楚，仍有三个复合点','structure':'分类合法，P8应移动到矛盾处理组',
   'improvements':['一手不保证客观、有立场不等于无价值、转载不独立分别成点。','作者、时间、受众、目的及互证可比性恢复；案例不再作为独立叶子，也未断言A/B必然矛盾。'],
   'issues':[['P1','区分观察/推断与为推断提供依据是两项独立要求，仍合成一个元问题。'],
             ['P5','来源独立性与对象/时段可比性仍合并，应拆为不同核查维度。'],
             ['P8','数量投票和预设立场两条禁止推断仍合并；拆开可避免后续再次混成一个错因。'],
             ['P9.statement / disposition.C9','“结论强度”被写成“可信度强度”，映射理由又称数量与强度的对应规则；材料并未给出数量到可信度的定量或单调关系。'],
             ['P10','“可以说什么”改成“可以确定什么”，容易提高证据承诺；应保留可支持的主张及不确定性原意。'],
             ['P8.parent','真假判断禁区归入推论限制与结论表达，与同组其他点维度不一致；更适合互证逻辑与矛盾处理。']]}}


def tree_lines(tree):
    cats=tree['categories'];points=tree['points'];out=[]
    def walk(parent,prefix):
        entries=[('cat',c) for c in cats if c['parent_key']==parent]+[('point',p) for p in points if p['parent_key']==parent]
        for i,(kind,item) in enumerate(entries):
            last=i==len(entries)-1;out.append(prefix+('└─ ' if last else '├─ ')+item['name']+(' ['+item['key']+']' if kind=='point' else ''))
            if kind=='cat':walk(item['key'],prefix+('   ' if last else '│  '))
    walk(None,'');return out


def export(root,destination):
    rows=[];records=[]
    for c in read(root/'fixtures.json'):
        k=c['key'];inv=read(root/'calls'/(k+'-inventory')/'parsed.json');atoms=read(root/'calls'/(k+'-atoms')/'parsed.json');classification=read(root/'calls'/(k+'-classify')/'parsed.json')
        tree=assemble(c,inv,atoms,classification)
        assert not validate_inventory(c,inv) and not validate_atoms(inv,atoms)
        # Explicitly prove classification/assembly did not alter any generated atom field.
        for before,after in zip(atoms['points'],tree['points']):assert all(after[f]==v for f,v in before.items())
        coverage=[]
        for req,(claims,points) in zip(REQUIREMENTS[k],MAPPINGS[k]):
            assert set(claims)<={x['key'] for x in inv['claims']}
            assert set(points)<={x['key'] for x in atoms['points']}
            coverage.append({'requirement':req,'claims':claims,'points':points,'represented':True,
                             'note':'含边界/条件/案例承载；不表示每项都已成为独立原子叶子'})
        assert len(coverage)==len(REQUIREMENTS[k])
        review={'course':k,'title':c['title'],'claims':len(inv['claims']),'points':len(tree['points']),
            'categories':len(tree['categories']),'structure_checks_passed':True,'classification_preserves_atoms':True,
            'coverage':coverage,'reviewer':'Codex source-by-source review','tree_digest':digest(tree),
            'ready_for_adoption':False,**{('coverage_summary' if field=='coverage' else field):value for field,value in REVIEWS[k].items()}}
        save(root/'reviewed'/(k+'.json'),{'tree':tree,'review':review})
        save(destination/(k+'-知识树.json'),{'tree':tree,'review':review})
        rows.append(review);records.append({'course':c,'inventory':inv,'atoms':atoms,'classification':classification,'tree':tree,'review':review})
    calls=[read(p) for p in (root/'calls').glob('*/result.json')]
    metrics={'model':'qwen3.8-27b','calls':len(calls),'completed':sum(c['state']=='completed' for c in calls),
       'seconds':round(sum(c.get('seconds',0) for c in calls),2),'claims':sum(r['claims'] for r in rows),
       'points':sum(r['points'] for r in rows),'requirements':sum(len(REQUIREMENTS[r['course']]) for r in rows),
       'represented_requirements':sum(len(r['coverage']) for r in rows),'anchored_quotes':sum(r['claims'] for r in rows),
       'valid_classification_trees':len(rows),'atom_fields_preserved':sum(r['points'] for r in rows),
       'control':read(root/'control.json'),'content_edits':0,'teaching_calls':0,'production_course_writes':0,
       'interpretation':'40条冻结材料要求均找到承载；不是40个全部原子化知识点，也不是整课覆盖。当前四树可逐点审阅，仍需粒度与措辞修订。'}
    save(root/'assessment.json',{'metrics':metrics,'courses':rows})
    save(destination/'评测与材料覆盖.json',{'metrics':metrics,'courses':rows})
    save(destination/'三阶段原始结果.json',records)
    save(destination/'冻结规则.json',{'eval':read(root/'eval.json'),'requirements':read(root/'requirements.json'),'manifest':read(root/'manifest.json')})
    lines=['# 知识清单 → 原子化 → 分类树：实际输出','','下列树与正文来自千问；程序只补来源、附件、身份和归属，未人工修订知识。','']
    for r in records:
        v=r['review'];lines+=['## '+v['title'],'',f"{v['claims']}条清单 → {v['points']}个候选叶子 → {v['categories']}个分类。",'',
             '```text',*tree_lines(r['tree']),'```','','### 四项复核','']
        for label,field in [('准确性','accuracy'),('颗粒度','granularity'),('结构','structure')]:lines+=['- '+label+'：'+v[field]]
        lines+=['- 覆盖：'+REVIEWS[v['course']]['coverage'],'','### 待修订','']+['- `'+p+'`：'+why for p,why in v['issues']]
        lines+=['','### 元知识与原文','']
        for p in r['tree']['points']:
            lines+=['#### '+p['key']+' '+p['name'],'',p['statement'],'','元问题：'+p['meta_question'],'','核心回答：'+p['meta_answer'],'',
               '条件：'+'；'.join(p['conditions'] or ['继承课程范围']),'','边界：'+'；'.join(p['boundaries'] or ['未另列；另见关联附件']),'']
            lines += ['- 原文 `'+e['source_ref']+' / '+e['claim_key']+'`：'+e['quote'] for e in p['evidence']]
            lines += ['- 附件 `'+a['role']+' / '+a['claim_key']+'`：'+a['claim']['quote'] for a in p['attachments']]
            lines+=['']
    (destination/'四门课实际知识树.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(metrics)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('destination',type=Path)
    a=p.parse_args();export(a.root,a.destination)
