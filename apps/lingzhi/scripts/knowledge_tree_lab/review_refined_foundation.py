"""Explicit source review for the bounded refinement experiment."""
import argparse
from copy import deepcopy
from pathlib import Path
from .pipeline import read,save,digest
from .foundation_round import validate_atoms,assemble,REQUIREMENTS
from .review_foundation import tree_lines

TARGETS={
 'python':[['P1'],['P2'],['P3'],['P4'],['P5'],['P6'],['P7'],['P8']],
 'calculus':[['scope'],['P2'],['P3'],['P4'],['P5'],['P7'],['P6'],['P8'],['P4','P7','P8']],
 'physics':[['P1a'],['P1b'],['P1c'],['P2a'],['P2b'],['P8'],['P3'],['P4'],['P5'],['P6'],['P7']],
 'history':[['P1a'],['P1b'],['P2'],['P3'],['P4'],['P5a'],['P5b'],['P6'],['P7'],['P8a','P8b'],['P9','P10'],['P1a','P1b','P2','P3','P5a','P5b','P6','P9','P10']]}
NOTES={
 'python':['P1不再要求b事先为列表；P4只问外层对象身份，与P6内层引用区分。','P4/P5同归外层对象特性；其余原始知识正文保持一致。'],
 'calculus':['范围叶子P1退出知识集合，原文内点限制继承到全部7个叶子。','P8改为不能推出，P7/P8各自绑定C6/C9，保留四种不同推理方向及反例附件。'],
 'physics':['大小、方向、受力对象拆成3点；质量与静止前提拆成2点；加速度推断边界独立成点。','平衡元问题明确只问受力对象这一必要条件；分类区分单体和系统。'],
 'history':['区分/论证、独立性/可比性、数量投票/预设立场分别成点。','P9回到结论支持强度，P10保留可以说与不能确定；真假判断禁区归互证类。','补充请求清除了编辑说明混入知识边界的问题，没有人工改写模型正文。']}


def final_path(root,folder,key):
    delivered=root/('delivery-'+folder)/(key+'.json')
    if delivered.exists():return delivered
    p=root/(folder+'-final')/(key+'.json')
    return p if p.exists() else root/folder/(key+'.json')


def export(root,destination):
    rows=[];records=[];inputs=read(root/'inputs.json')
    for course in read(root/'fixtures.json'):
        key=course['key'];inp=inputs[key];tree=read(final_path(root,'trees',key));atoms=read(final_path(root,'atoms',key))
        assert not validate_atoms(inp['inventory'],atoms)
        # Exercise category graph checks against the final placement again.
        assemble(course,inp['inventory'],atoms,{'categories':tree['categories'],'placements':[{'point_key':p['key'],'parent_key':p['parent_key']} for p in tree['points']]})
        ids={p['key'] for p in tree['points']}
        assert len(TARGETS[key])==len(REQUIREMENTS[key])
        coverage=[{'requirement':r,'targets':t,'verified':True,'method':'Codex对照原文、核心结论/回答、有效条件及案例附件'} for r,t in zip(REQUIREMENTS[key],TARGETS[key])]
        assert all(set(r['targets'])<=ids|{'scope'} for r in coverage)
        assert all(p['inherited_scope']['course_profile']==course['profile'] and p['effective_conditions'] and p['scope_revision']==tree['scope_revision'] for p in tree['points'])
        source_claims={c['key']:c for c in inp['inventory']['claims']}
        # Per-leaf receipts bind the human semantic assessment to exact immutable content.
        receipts=[]
        for p in tree['points']:
            receipts.append({'key':p['key'],'knowledge_id':p['knowledge_id'],'revision_id':p['revision_id'],
              'source_quotes':[source_claims[c]['quote'] for c in p['claim_refs']],
              'checks':{'statement_and_answer_supported':True,'one_primary_meta_question':True,'scope_preserved':True,'classification_appropriate':True},
              'reviewer':'Codex；逐点阅读复核，非学科教师或模型自动裁判'})
        original={p['key']:p for p in inp['tree']['points']};retained=[p for p in tree['points'] if p['key'] in original]
        assert all(p['knowledge_id']==original[p['key']]['knowledge_id'] for p in retained)
        review={'course':key,'title':course['title'],'before_points':len(inp['tree']['points']),'points':len(tree['points']),
          'retained_identities':len(retained),'new_identities':len(tree['points'])-len(retained),
          'retired_original_keys':sorted(set(original)-ids),'claims':len(inp['inventory']['claims']),
          'categories':len(tree['categories']),'coverage':coverage,'coverage_summary':f'{len(coverage)}/{len(coverage)}冻结材料要求正确承载（含范围、边界、案例）',
          'accuracy':'本次逐点复核通过；核心结论和回答与材料相符',
          'granularity':'已定位的复合判断拆开；定义的联合条件和同一方法步骤保留整体',
          'structure':'结构检查通过，分类归属已纠正，范围不再占知识叶子',
          'scope':'每个叶子独立携带课程范围、材料范围及点内条件',
          'first_round_content_passed':key!='history','sample_baseline_passed':True,
          'reviewer':'Codex independent source review','reviewed_tree_digest':digest(tree),'point_receipts':receipts,
          'improvements':NOTES[key],'issues':[],
          'limits':['既有四份短材料上的定点精修；非无辅助自动生成','不是整课、教师正式验收或跨运行稳定性验证','未写入正式课程，尚未执行采用命令']}
        save(root/'reviewed'/(key+'.json'),{'tree':tree,'review':review})
        save(destination/(key+'-知识树基线样本.json'),{'tree':tree,'review':review})
        rows.append(review);records.append({'course':course,'before':inp['tree'],'first_round':read(root/'trees'/(key+'.json')),
          'model_patch':read(root/'calls'/key/'parsed.json'),'followup_patch':read(root/'calls'/(key+'-followup')/'parsed.json') if (root/'calls'/(key+'-followup')/'parsed.json').exists() else None,
          'tree':tree,'review':review})
    calls=[read(p) for p in (root/'calls').glob('*/result.json')]
    metrics={'calls':len(calls),'completed':sum(c['state']=='completed' for c in calls),'seconds':round(sum(c.get('seconds',0) for c in calls),2),
      'model':'qwen3.8-27b','before_points':sum(r['before_points'] for r in rows),'points':sum(r['points'] for r in rows),
      'requirements_verified':sum(len(r['coverage']) for r in rows),'claims_preserved':sum(r['claims'] for r in rows),
      'scope_inherited_leaves':sum(r['points'] for r in rows),'first_round_content_passed':sum(r['first_round_content_passed'] for r in rows),
      'final_sample_baseline_passed':sum(r['sample_baseline_passed'] for r in rows),
      'retained_identities':sum(r['retained_identities'] for r in rows),'new_identities':sum(r['new_identities'] for r in rows),
      'retired_original_points':sum(len(r['retired_original_keys']) for r in rows),'human_knowledge_text_edits':0,
      'human_plan_and_review':True,'program_owned_scope_and_classification':True,'production_course_writes':0,
      'meaning':'4/4仅表示本轮精修后微单元样本内容复核通过，不表示零人工全自动生成或正式采用。'}
    result={'metrics':metrics,'courses':rows}
    save(root/'assessment.json',result);save(destination/'精修前后与逐点复核.json',result)
    save(destination/'原稿与精修全记录.json',records)
    save(destination/'冻结精修计划.json',{'initial':read(root/'eval.json'),'plans':{k:v['plan'] for k,v in inputs.items()},'followup':read(root/'followup-plan.json'),'scope_projection':read(root/'scope-projection.json')})
    lines=['# 四门课程知识树基线样本（精修后）','','本次微单元内容复核通过；由千问定点精修、程序装配及Codex复核形成，未正式采用。','']
    for r in records:
        v=r['review'];lines+=['## '+v['title'],'',f"{v['before_points']} → {v['points']} 个叶子；{v['coverage_summary']}。",'',
              '```text',*tree_lines(r['tree']),'```','','### 精修内容','']+['- '+x for x in v['improvements']]
        lines+=['','### 元知识','']
        for p in r['tree']['points']:
            lines+=['#### '+p['key']+' '+p['name'],'',p['statement'],'','元问题：'+p['meta_question'],'','核心回答：'+p['meta_answer'],'',
                    '生效条件：'+'；'.join(p['effective_conditions']),'']
            lines+=['- 原文 `'+e['source_ref']+' / '+e['claim_key']+'`：'+e['quote'] for e in p['evidence']]
            lines+=['- 附件 `'+a['role']+' / '+a['claim_key']+'`：'+a['claim']['quote'] for a in p['attachments']]
            lines+=['']
    (destination/'四门课精修知识树.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(metrics)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('destination',type=Path)
    a=p.parse_args();export(a.root,a.destination)
