"""Post-run independent adjudication; preserve model/auditor disagreements."""
from pathlib import Path
import argparse
from copy import deepcopy
from .pipeline import read,save,digest
from .independent_round import validate
from .independent_answers import compare
from .semantic_contract import attach_review,REVIEW_AXES

FINDINGS={
 'python':{
  'passed_axes':['question_binding'],
  'improvements':['内层共享补题改为a=[[1]]，修复上一轮把整数当内层列表的问题。','7个点各有检查、错因、补救、迁移及标准，初始状态均具体可读。'],
  'blockers':[
   ['P6.transfer.answer','p=[[10,20]];q=p.copy();p[0].pop()后q应为[[10]]，生成与一次修正仍写[[20]]。初审解答正确，V2复核反而写pop移除10并判通过。'],
   ['P1/P5.transfer / P6.transfer','迁移引入字典、pop，超过材料限定的普通列表与所列操作；自加“假设类似”不能证明此微单元已经支持该迁移。'],
   ['P4/P5.repair.cannot_infer','将“不影响a的元素替换”“共享内层append可见”等课程已成立规则写成不能推断，边界栏与其他知识点不一致。'],
   ['P4.mistake.wrong_rule','把copy等同别名与copy全部独立用“或者”并列，两种规则对append的预测不同；后文聚焦第一条不能消除规则本身的歧义。'],
   ['check.origin_key','6道题改了题干却继续复用冻结Q标识；需保留原题原文或生成新的候选身份。']],
  'audit_failure':['初审P6独立解答[[10]]，修正未据此纠错；V2独立解答[[20]]，与生成器一致但共同错误。'],
  'material_checks_remaining':['外层新对象与外层操作隔离仍合并','超出既定材料范围的迁移不可计作已核验覆盖']},
 'calculus':{
  'passed_axes':['atomicity_and_coverage','question_binding','repair'],
  'improvements':['移走绝对值案例叶子，7条规则各有检查；不连续→不可导与不可导不能推出不连续分别检查，修复上一轮方向错绑。',
                  '一次修正纠正P1迁移答案自相矛盾：左右函数极限为2和4，双侧极限不存在。'],
  'blockers':[
   ['P2.transfer.answer','sqrt(x)在1处差商有理化应为1/(sqrt(1+h)+1)。答案仍写h/((1+h)+1)但给出极限1/2；结论正确不能掩盖推导错误。'],
   ['P3.mistake.prediction','错误规则只说左右有限就可导，不能推出“导数为0/平均值0”，额外偷加了平均规则。'],
   ['P5.transfer','题干同时给出y=x为直线，却把论证归结为仅凭连续；已有额外充分条件，无法干净地区分目标误解。'],
   ['P7.mistake.derivation','相对于可导→连续，不可导→不连续是否命题，文中却标为逆命题，逻辑术语不准确。'],
   ['check.origin_key','7个题干改写后仍使用旧Q/R标识，结构校验不通过。']],
  'audit_failure':['P3修正为左段x²、右段2x+1、f(1)=1。首复审错误地只求两段导数得2/2；V2虽判不可导，却又把左差商算成h、右差商错写成(2h+1-3)/h。正确为左2+h、右2/h+2。'],
  'material_checks_remaining':['7条主要规则均有检查；诊断的单一错误规则和推导准确性仍不通过']},
 'physics':{
  'passed_axes':[],
  'improvements':['加速度检查题明确给出“仅考虑这对相互作用力”，实际问加速度，不再硬绑只问力大小的Q2。','7个生成点都有检查与迁移；一次修正尝试把运动状态引入P3迁移。'],
  'blockers':[
   ['P1.check / P3.check','P1仍合并大小和方向但检查只问大小；P3合并质量与运动条件但检查仅问静止不否定反作用力。部分判断仍无直接检查。'],
   ['P3.transfer（修正新增）','题干同时给“光滑桌面”和“非零滑动摩擦”，情境自相矛盾。第一次复审发现，V2复核又忽略了它。'],
   ['P4.transfer.answer','碰撞题没有限定合外力/接触时刻，却直接断言质量小者加速度更大；不等质量、等大相互作用力可以在其他外力作用下产生相同加速度。'],
   ['P2/P5.repair','仍使用箭头起点在物体表面或脚底来判断受力归属；擦去不在脚底的箭头会误删重力等有效表示。'],
   ['P6.check / mistake','知识点检查单体上能否抵消，却仍用“书的重力和支持力是不是作用反作用”代替；错规则只给反作用力可抵消，预测却又自行把这两个力识别为反作用力对。'],
   ['P7','内力分类、内力抵消及不能推出外力零仍合并，检查主要问外力推断，迁移转而问材料未提供的总动量。']],
  'audit_failure':['V2将有矛盾前提的P3迁移及缺合外力条件的P4迁移均判通过，还自行补充“墙受地面摩擦平衡”作为具体事实。'],
  'material_checks_remaining':['作用反作用的方向直接检查','质量/运动两个适用条件独立检查','单体力对相消的直接判断','系统内力识别与外力边界分开检查']},
 'history':{
  'passed_axes':['question_binding','transfer'],
  'improvements':['A的两项陈述在P1中均明确标为作者说法，补救也增加“未证实不等于为假”，改善原文与事件事实边界。',
                  '3个案例叶子移到examples，6个生成点各带检查；关系强度在修正中转为null。'],
  'blockers':[
   ['P2.mistake','由“个例可推广全体”不能单独推出“生活恶化”；还偷加工时增长就恶化、记录真实等假设。一个真实反例可否定全称命题，不能把支持全称与反驳全称混成一个错误规则。'],
   ['P5.mistake','私人记录优先与数量投票仍用“或”混合：前者可能选B，按文本数量A+C对B则选A，预测不能当成单一错因的必然结果。'],
   ['P6.repair.action','写“目前可以说该工人收入增加且工时变长”，没有保留“日记记载”，又将文本陈述升级为事实，与P1不一致。'],
   ['points / checks','一手材料不必完全客观、时间背景与对象/时段可比性未形成充分独立检查；案例移走不等于材料所有判断均被测到。'],
   ['check.origin_key','6道检查扩写原题仍保留旧Q标识，修正只将该错误留在gaps，没有修复身份。']],
  'audit_failure':['V2 P6把材料“通勤更快”改成“通勤时间增加”；同时给所有点全部通过意见，并重复把日记陈述当作已知个体事实。'],
  'material_checks_remaining':['一手材料客观性边界','材料时间背景','互证对象与时段可比性','推断依据与推理的单独检查']}
}


def export(root,destination):
    fixtures=read(root/'fixtures.json');rows=[];records=[]
    status={r['key']:r for r in read(root/'summary.json')}
    v2status={r['key']:r for r in read(root/'audit-v2-summary.json')}
    for c in fixtures:
        k=c['key'];final=read(root/'candidates'/(k+'-final.json'));initial=read(root/'candidates'/(k+'-initial.json'))
        audit=read(root/'calls'/(k+'-audit-v2')/'parsed.json')
        comparison=compare(final,audit);save(root/'answer-comparisons'/(k+'-final.json'),comparison)
        v=FINDINGS[k]
        resolved=deepcopy(final)
        resolved['contract']={'version':'point_card_independent_v2','structural_issues':validate(c,final),
            'candidate_revision':digest(final),'question_revision':digest([{'key':p['key'],'check':p['check'],'transfer':p['transfer']} for p in final['points']]),
            'semantic_status':'pending_independent_review','ready_for_adoption':False}
        review={'candidate_digest':digest(resolved),'reviewer':'Codex independently inspected final candidate, audits and computations',
            'axes':{axis:axis in v['passed_axes'] for axis in REVIEW_AXES},'evidence':['independent-computations.json',*v['improvements']],
            'blockers':v['blockers'],'auditor_false_positive_examples':v['audit_failure']}
        resolved=attach_review(resolved,review)
        # Keys are local experiment keys, not production knowledge identities.
        row={'key':k,'title':c['title'],'initial_points':len(initial['points']),'final_points':len(final['points']),
            'points_with_check':sum(bool(p.get('check',{}).get('question') and p['check'].get('answer')) for p in final['points']),
            'points_with_repair':sum(bool(p.get('repair',{}).get('action')) for p in final['points']),
            'structural_errors':validate(c,final),'qwen_v2_positive_cards':sum(all(r[a] is True for a in ('atomic','binding','prediction','repair','transfer')) and not r['issues'] for r in audit['reviews']),
            'sample_usable':resolved['contract']['sample_usable'],**v}
        save(root/'reviewed'/(k+'.json'),resolved);rows.append(row)
        records.append({'fixture':c,'initial':initial,'patch':read(root/'calls'/(k+'-repair')/'parsed.json'),
            'final_candidate':final,'v2_blind_input':read(root/'calls'/(k+'-audit-v2')/'input.json'),
            'v2_audit':audit,'literal_comparison':comparison,'independent_reviewed':resolved,'review':row})
    calls=[read(p) for p in (root/'calls').glob('*/result.json')]
    metrics={'calls':len(calls),'json_completed':sum(r['state']=='completed' for r in calls),
        'failure_types':[r['error_type'] for r in calls if r['state']=='failed'],
        'seconds':round(sum(r.get('seconds',0) for r in calls),2),
        'models':sorted({r['model'] for r in calls if r.get('model')}),
        'format_recoveries':2,'points':sum(r['final_points'] for r in rows),
        'points_with_check':sum(r['points_with_check'] for r in rows),
        'qwen_v2_positive_cards':sum(r['qwen_v2_positive_cards'] for r in rows),
        'usable_courses':sum(r['sample_usable'] for r in rows),'control':read(root/'control.json'),
        'production_writes':0,'human_content_edits':0,'qwen_repair_calls':4,
        'scope':'原相同四微单元；协议和调用预算改变，不是纯提示词或统计可靠性实验；生成点27/27有题不是材料语义覆盖27/27通过。'}
    save(root/'comparison.json',{'metrics':metrics,'courses':rows})
    save(destination/'对照与独立复核.json',{'metrics':metrics,'courses':rows})
    save(destination/'四课候选与盲审原件.json',records)
    save(destination/'独立计算回执.json',read(root/'independent-computations.json'))
    save(destination/'冻结规则与追加复核.json',{'initial':read(root/'eval.json'),'v2':read(root/'audit-v2-plan.json'),
        'format_recovery':[read(root/'recovery/calculus.json'),read(root/'recovery/calculus-reaudit-normalization.json')]})
    lines=['# 逐点检查、独立解题与补救复核','','候选及模型审查保留原文；未修订为人工正确稿。','']
    for r in records:
        v=r['review'];lines+=['## '+v['title'],'','### 改善','']+['- '+x for x in v['improvements']]
        lines+=['','### 独立复核阻断项','']+['- `'+p+'`：'+why for p,why in v['blockers']]
        lines+=['','### 模型审查器漏报或错误','']+['- '+x for x in v['audit_failure']]
        lines+=['','### 最终候选逐点卡片（未通过采用）','']
        for p in r['final_candidate']['points']:
            lines+=['#### '+p['key']+' '+p['name'],'',p['statement'],'',
                '**检查：** '+p['check']['question'],'','**模型答案：** '+p['check']['answer'],'',
                '**错规则：** '+p['mistake']['wrong_rule'],'','**预测：** '+p['mistake']['prediction'],'',
                '**补救：** '+p['repair']['action'],'','**不可扩大：** '+p['repair']['cannot_infer'],'',
                '**迁移：** '+p['transfer']['question'],'','**模型答案：** '+p['transfer']['answer'],'']
    (destination/'逐科候选与核验问题.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(metrics)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('destination',type=Path)
    a=p.parse_args();export(a.root,a.destination)
