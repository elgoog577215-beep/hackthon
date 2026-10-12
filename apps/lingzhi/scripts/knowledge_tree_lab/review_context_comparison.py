"""Paired review of frozen baseline and shared-context calls; no content repairs."""
from pathlib import Path
import argparse
from copy import deepcopy
from .pipeline import read, save, digest
from .cross_course_round import validate_tree, validate_teaching

VERDICTS = {
 'python': {
  'granularity':'改善：新外层与外层操作隔离、共享内层与修改可见性分别拆开（6→8点）。',
  'specificity':'保持课程针对性，显式使用编程画像；仍用内存/指针措辞，不宜将实现细节当语言保证。',
  'question_binding':'局部改善：原来绑Q1却预测Q2的错误修复；仍需区分独立检查题与顺序训练题。',
  'diagnosis':'错误预测与题号更一致；复测跨能力依赖和训练上下文尚不清晰。',
  'issues':[
    ('S1.task / criteria[P3]','训练先执行b.append(2)，再执行b=[9]，此时a应保留[1,2]；绑定独立Q3的标准却写a保持[1]，未说明两套起始状态。'),
    ('S2.task','“随后修改操作为b[0]=[8]”未明确重置还是延续前面的内层修改，训练的初始状态存在歧义。'),
    ('S1.retest_key','仍用还涉及浅拷贝和元素替换的R2复测别名能力，未记录对S2知识的依赖。')]},
 'calculus': {
  'granularity':'改善：连续不能推出可导、不可导不能推出不连续已分成独立叶子；范围条件不再单列叶子。反例仍混在知识叶子中。',
  'specificity':'仍按定义、双侧差商和反例组织；增加了端点、高阶及导函数连续性等明确范围缺口。',
  'question_binding':'仅形式改善：两个null消失，但Q1/Q2评分内容换成了训练题，实际绑定仍失败。',
  'diagnosis':'双侧差商错误更具体；充分必要条件错因仍混入不能由该错误规则推出的症状，训练复用了复测题。',
  'issues':[
    ('S1.criteria[P1]→Q1','Q1是f(x)=x(x≠0),f(0)=1，不连续；标准却要求判断|x-2|在2连续，答案对象和结论均错配。'),
    ('S1.criteria[P2]→Q2','Q2是x²在0的差商h和导数0；标准却是绝对值的|h|/h。'),
    ('S2.criteria[P7]→Q1','P7检查不连续推出不可导；Q1仅问连续性，并未要求该逆否推理。'),
    ('tree.relations[P4→P1]','把“可导必连续”指向连续性定义并标prerequisite，理由却说前者依赖后者；与先修→后学约定反向。'),
    ('S1.task / retest_key','训练直接使用R1的|x-2|在2问题，不能再将同题R1作独立迁移证据。'),
    ('S2.mistakes.B.observable_error','连续与可导等价这一错误信念不会推出“不连续→可导”，症状夹带另一种错误。')]},
 'physics': {
  'granularity':'混合：等大与反向、系统内力与外力结论拆开；但漏掉材料M1的“力等大不能直接推出加速度相等”边界。',
  'specificity':'系统边界表述比上轮清楚；仍把“力对的等大关系不要求等质量”泛化成“力大小与质量无关”。',
  'question_binding':'仍有实际考点不足：Q2问谁的力更大，却承担“方向相反”的评分标准。',
  'diagnosis':'仍不合格：错误规则的施力者/受力者方向与其预测不对应；受力图箭头核对方法仍有问题。',
  'issues':[
    ('tree.points / M1','本轮未形成加速度推断边界点，也未报告该缺口；不能把原加速度错误不再出现计为已纠正。旧六项覆盖清单也未单列此边界，需如实记录评测局限。'),
    ('S1.mistakes.A.repair_steps','写“力的大小…与质量无关”，混淆一对力等大的关系与具体力值；例如引力大小本可依赖质量。'),
    ('S1.mistakes.A.wrong_rule / prediction','规则按受力者质量决定力；甲较重则应错推乙对甲更大，预测却写甲对乙更大，偷换成施力者质量。'),
    ('S1.criteria[P2]→Q2','冻结Q2只问大小，不检查方向。'),
    ('S2.criteria[P6]','写同一受力对象“故为平衡力”，受力对象相同只是必要条件，并不能单独推出合力为零。'),
    ('S1/S2.repair_steps','继续把箭头指向研究物体作为检查法，混淆力的归属与方向；受力图应标受力者并按实际力方向画箭头。')]},
 'history': {
  'granularity':'混合/未达标：转载规则从互证条件中拆出，但案例节点从4个增加到5个（总点数10→12），案例与通用知识仍混合。',
  'specificity':'改善：不再确定地编造隐瞒劳资纠纷的动机；增加工时延长未必代表生活恶化等不确定性。',
  'question_binding':'主要题目方向更贴合，仍不能将固定观点或把全部陈述标成推断作为评分捷径。',
  'diagnosis':'更明确承认材料张力并非必然矛盾；但树中先断言逻辑矛盾，教学gaps随后又承认不能确定，上下游不一致。',
  'issues':[
    ('tree.P8-P12','将具体A/B/C信息及案例差异继续作为通用知识叶子，案例变动会影响知识身份。'),
    ('tree.P11.conditions / teaching.gaps','树将A/B称为存在逻辑矛盾；教学又承认收入增加和工时变长未必推翻生活改善，条件不一致。'),
    ('S1.criteria[P1] / repair','要求把产量和生活改善陈述都当推断，补救又把产量当观察；没有稳定区分“原文可观察的陈述”与“历史事件已获证实”。'),
    ('S1.mistakes.A2.repair_steps','“可提取的信息如产量数据”超出了仅有文字主张的材料；应标为产量陈述并保留真实性待核对。')]}
}


def export(root, baseline, destination):
    assert read(root/'fixtures.json')==read(baseline/'fixtures.json')
    assert read(root/'prompts.json')==read(baseline/'prompts.json')
    contexts=read(root/'shared-contexts.json');rows=[];records=[]
    for c in read(root/'fixtures.json'):
        key=c['key'];oldtree=read(baseline/'calls'/f'{key}-tree'/'parsed.json');tree=read(root/'calls'/f'{key}-tree'/'parsed.json')
        oldteach=read(baseline/'calls'/f'{key}-teaching'/'parsed.json');teach=read(root/'calls'/f'{key}-teaching'/'parsed.json')
        oldinput=read(baseline/'calls'/f'{key}-tree'/'input.json');newinput=read(root/'calls'/f'{key}-tree'/'input.json')
        assert {k:v for k,v in newinput.items() if k!='shared_context'}==oldinput
        oldt=read(baseline/'calls'/f'{key}-teaching'/'input.json');newt=read(root/'calls'/f'{key}-teaching'/'input.json')
        assert oldt['probes']==newt['probes'] and oldt['retests']==newt['retests']
        assert newt['course']['shared_context']['revision_id']==newinput['shared_context']['revision_id']==contexts[key]['revision_id']
        row={'course':key,'title':c['title'],'baseline_points':len(oldtree['points']),'new_points':len(tree['points']),
             'baseline_tree_errors':validate_tree(c,oldtree),'new_tree_errors':validate_tree(c,tree),
             'baseline_teaching_errors':validate_teaching(c,oldtree,oldteach),'new_teaching_errors':validate_teaching(c,tree,teach),
             'skills':len(teach['skills']),'criteria':sum(len(s['criteria']) for s in teach['skills']),
             'primary_mode':contexts[key]['subject_pedagogy_profile']['primary_mode'],
             'context_revision':contexts[key]['revision_id'],'evidence_revision':contexts[key]['evidence_package']['package_revision_id'],
             'scope_revision':contexts[key]['scope_contract']['revision_id'],
             **deepcopy(VERDICTS[key]),'ready_for_adoption':False,'reviewer':'Codex'}
        rows.append(row);records.append({'course':c,'context':contexts[key],'baseline_tree':oldtree,'tree':tree,'baseline_teaching':oldteach,'teaching':teach,'review':row})
    def timing(folder):
        calls=[read(p) for p in (folder/'calls').glob('*/result.json')]
        return {'calls':len(calls),'completed':sum(c['state']=='completed' for c in calls),'seconds':round(sum(c.get('seconds',0) for c in calls),2)}
    metrics={'baseline':timing(baseline),'new':timing(root),'materials_unchanged':True,'prompts_unchanged':True,
        'probes_and_retests_unchanged':True,'tree_structure_before':sum(not r['baseline_tree_errors'] for r in rows),
        'tree_structure_after':sum(not r['new_tree_errors'] for r in rows),
        'teaching_structure_before':sum(not r['baseline_teaching_errors'] for r in rows),
        'teaching_structure_after':sum(not r['new_teaching_errors'] for r in rows),
        'semantic_ready_courses':0,'control':read(root/'control-assessment.json'),
        'limit':'每门一微单元、一次顺序运行；共同增加了画像/范围/证据等字段，不能归因于单一字段或宣称稳定提升。未修改模型内容。'}
    destination.mkdir(parents=True,exist_ok=True)
    save(root/'comparison.json',{'metrics':metrics,'courses':rows})
    save(destination/'对照结果.json',{'metrics':metrics,'courses':rows})
    save(destination/'四门课程上下文与原始输出.json',records)
    save(destination/'冻结对照规则.json',read(root/'eval.json'))
    text=['# 接回共享上下文后的四课对照','','同一材料、主提示词、题库与复测；仅增加共享上下文。所有候选均待修订。','']
    for r in records:
        row=r['review'];text+=['## '+row['title'],'']
        for k,label in [('granularity','粒度'),('specificity','针对性'),('question_binding','题目引用'),('diagnosis','错因诊断')]:text+=['- **'+label+'**：'+row[k]]
        text+=['','### 未解决问题','']+['- `'+field+'`：'+msg for field,msg in row['issues']]
        text+=['','### 本轮知识点','']+['- **'+p['key']+' '+p['name']+'**：'+p['statement'] for p in r['tree']['points']]
        text+=['','### 本轮能力与标准','']
        for s in r['teaching']['skills']:
            text+=['#### '+s['name'],'',s['task']['prompt'],'']+['- '+x['point_key']+' → '+str(x['probe_key'])+'：'+x['pass_evidence'] for x in s['criteria']]
            for m in s['mistakes']:text+=['','错因：'+m['wrong_rule'],'','预测：'+m['prediction'],'','补救：'+'；'.join(m['repair_steps'])]
            text+=['']
    (destination/'逐科对照与候选内容.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    print(metrics)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('baseline',type=Path);p.add_argument('destination',type=Path);a=p.parse_args();export(a.root,a.baseline,a.destination)
