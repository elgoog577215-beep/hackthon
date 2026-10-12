"""Explicit Codex adjudication of this frozen run, not an automatic scorer."""
import argparse
from pathlib import Path
from .pipeline import read, save, digest
from .cross_course_round import validate_tree, validate_teaching
from .semantic_contract import compile_candidate, attach_review, REVIEW_AXES, question_bank

# These findings were recorded after inspecting every raw tree and teaching body.
REVIEWS = {
 'python': {
  'passed_axes':['prediction','repair'],
  'improvements':['Q1/Q2/Q3回到各自冻结题；训练明确每题独立重置，消除串行初始状态混用。',
                  '四条错规则分别推出False、[9]、[[1]]、[[9]]，对象图补救均与材料相符。'],
  'blockers':[
   ['tree.P4','把新外层对象、外层append隔离、元素替换又并入一条；比上轮8点的对象/操作分离更粗。'],
   ['supplemental_probes.N1 / S2.criteria.P5','a=[10]的元素是整数；不能回答c和a[0]是同一个“列表对象”。它也没有考到嵌套列表共享。'],
   ['S1.retest','R2涉及浅拷贝和元素替换，但前置仅列P1/P2/P3，仍缺P4/P5/P7；R2没有执行b=a的别名操作，不足复测整个S1。'],
   ['S2.retest','R1没有元素替换，不能代替P7的迁移检查；达标要求也没有包含复测成功。']],
  'prediction_checks':[['S1.A',True,'赋值被错当复制→身份不同'],['S1.B',True,'错规则明确同步改a指向→[9]'],
                       ['S2.C',True,'错规则复制内层→原a不变'],['S2.D',True,'错规则同步替换a[0]→[[9]]']],
  'repair_checks':[['S1.A',True,'同对象图'],['S1.B',True,'仅移b引用'],['S2.C',True,'共享内层修改'],['S2.D',True,'仅改b索引引用']],
  'coverage':['P1','P2','P3','P4','P5/P6','P7'], 'missing_criteria':[]},
 'calculus': {
  'passed_axes':['prediction'],
  'improvements':['Q1的评分答案恢复为极限0≠点值1；Q2为差商h、导数0，均由冻结题库装配。',
                  '不再把R1原题放进训练；连续/可导的先修关系方向比上一轮清楚。',
                  '三条错因预测都能从各自写出的规则推出，没有夹带“不连续→可导”的症状。'],
  'blockers':[
   ['S3.criteria.P7→Q6','P7是不连续→不可导；Q6问不可导能否推出不连续。绑定理由再充分也不能改变题目推理方向。'],
   ['skills.criteria','P6与P8没有标准；返回3包超出本轮1—2包合同（包数本身不是学科错误）。'],
   ['tree.P6','绝对值反例仍作为知识叶子，与可复用规则混放。'],
   ['S2.mastery_requirements','写左右极限相等就存在导数，遗漏共同值有限的必要条件。'],
   ['S3.mistakes.C1.repair_steps.scope_limit','“不可导是必要非充分条件”没有说明是谁的条件，补救不能省略“不连续的”这一逻辑对象。'],
   ['retest','S1选R2却未声明不可导判断所需的P7；S2选R1未声明连续性P1；复测与每个能力的前置、达标条件仍不完整。']],
  'prediction_checks':[['S1.A1',True,'点值存在就连续→连续'],['S2.B1',True,'连续就可导→|x|在0可导'],
                       ['S3.C1',True,'不可导当不连续→能断定不连续']],
  'repair_checks':[['S1.A1',True,'逐项比较点值和极限'],['S2.B1',True,'计算左右差商'],
                   ['S3.C1',False,'逻辑条件的对象缺失，补救仍不够明确']],
  'coverage':['P1','P2','P3','P4','P5/P6','P7/P8'], 'missing_criteria':['P6','P8']},
 'physics': {
  'passed_axes':[],
  'improvements':['重新保留“力相等不能推出加速度相等”的材料边界P4。',
                  'A1明确采用施力者质量，正确推出甲对乙更大；不再把受力者质量与施力者偷换。',
                  'A1补救只说明这对力仍等大，不再宣称力值与质量无关；不再要求受力图箭头指向受力物体。'],
  'blockers':[
   ['tree.P1/P3','大小与方向、等质量与静止两个独立条件仍合并；P1→Q2只覆盖大小，P3→Q4也不足检验全部条件。'],
   ['tree.P6.statement','“不能把其中任意一个力视为单个物体的受力平衡力”过强；正确边界是这一对力不能在单物体上互相平衡，其中一力可以与其他力平衡。'],
   ['S1.criteria.P4→Q2','Q2只比较相互作用力大小，并未要求回答加速度；学生不谈加速度也能答对，不能算P4已测。'],
   ['S2.criteria.P6/P7→Q5','Q5问是否同一作用反作用对；没有直接要求判断在单物体上抵消或证明平衡。标准仍写同对象“因此是平衡力”。'],
   ['S2.mistakes.A2','把平衡与作用反作用合成一个或规则，预测还混入可能正确的平衡相消；题干没有明确给出等大条件，不能暗加。'],
   ['S2.mistakes.A2.repair_steps','同对象就标平衡力、不同对象就标作用反作用力，两者都把必要条件当充分条件；逐字引文正确也不能使该动作成立。'],
   ['S2.discrimination','把Q5正确依据写成“受力对象不同故非作用反作用对”，实际两个力都作用在书上，正确依据是相同。'],
   ['S3.criteria.P8→Q6','Q6题干已给内部推力，主要检查内力抵消不推外力零；把读出已给条件当作独立的内力识别检查。'],
   ['supplemental_probes.N1','问大小和方向，候选答案只说不要求质量相等，缺少明确的反向判断；未承担真正缺题的P4。'],
   ['retest / mastery','S1的R1还需P5受力图规则，未列前置；“至少3个不同质量情境”也无足量题目支撑。']],
  'prediction_checks':[['S1.A1',True,'施力者甲更重→甲施加力更大'],['S2.A2',False,'多规则混合、前提增添、预测含可能正确结果'],
                       ['S3.A3',True,'错误忽略外力→外力合力零']],
  'repair_checks':[['S1.A1',True,'限于这对相互作用力等大'],['S2.A2',False,'两个必要条件被当充分条件'],['S3.A3',True,'内外力分别列项']],
  'coverage':['P1/P2','P1','P2','P3','P5/P6/P7','P8/P9'], 'missing_criteria':[],
  'extra_material_boundary':'P4覆盖材料中加速度推断限制；旧六项覆盖表未单列此项，不能仅用旧24项总数判断完整性。'},
 'history': {
  'passed_axes':[],
  'improvements':['材料A的可能动机仍用可能性表达，未断言确定动机。',
                  '程序保留原题的开放评分说明，没有把它转为唯一字符串答案匹配。'],
  'blockers':[
   ['tree.P1 / S1.criteria.P1 / repair.A','把产量增加标为观察事实、生活改善标为推断，没有稳定区分两者均为可观察的原文陈述，与事件本身是否已证实。'],
   ['tree.P9.meta_answer','“仅能证明该个体工人的情况”仍把日记当成已核验的事件事实；收入增加且工时延长也未必构成生活改善的反例。'],
   ['tree.P8-P10 / relations','仍有3个案例叶子；6条强度返回中文强/中；P6→P9预设A/B存在矛盾。'],
   ['S1.criteria.P2→Q2','P2要求分析者提供推断的证据和推理，标准却改为解释经理动机，逻辑依据与动机不等同。'],
   ['S1.criteria.P3→Q2','从受众为投资人推出结论只能用于投资人利益评价，范围被无根据地缩窄。'],
   ['S2.criteria.P4/P5','Q4的代表性不能覆盖一手材料客观性/有立场不等于无价值；Q3转载问题未覆盖P5的对象和时段可比性。'],
   ['S2.mistakes.B','数量投票与立场偏好没有分开，既未固定偏好方向也未明确计数，不能唯一推出A真B假。'],
   ['S1.mistakes.A.repair_steps','按“所以”前后强制打观察/推断标签，补救没有解决原文记载与已核验事实的边界。'],
   ['skills.criteria / retest','P8/P9/P10缺标准；S1的R1所需证据限度P7未列前置，S2的R2只检查转载，不能作为整个互证/矛盾能力达标。']],
  'prediction_checks':[['S1.A',True,'把文本因果结论当已核验事实→全体改善已证实'],['S2.B',False,'多种规则与未给优先级不能导出单一结果']],
  'repair_checks':[['S1.A',False,'连接词标签法没有保持认识层次'],['S2.B',True,'在本案列差异/背景/查证是可用动作；应保留其他合理查证路径']],
  'coverage':['P1/P2','P3','P4','P5/P10','P6','P7/P9'], 'missing_criteria':['P8','P9','P10']}
}


def timing(root):
    calls=[read(p) for p in (root/'calls').glob('*/result.json')]
    return {'calls':len(calls),'completed':sum(v['state']=='completed' for v in calls),
            'seconds':round(sum(v.get('seconds',0) for v in calls),2),
            'models':sorted({v['model'] for v in calls if v.get('model')})}


def export(root, baseline, destination):
    assert read(root/'fixtures.json') == read(baseline/'fixtures.json')
    assert read(root/'shared-contexts.json') == read(baseline/'shared-contexts.json')
    rows=[];records=[];frozen_count=0
    for course in read(root/'fixtures.json'):
        key=course['key'];tree=read(root/'calls'/f'{key}-tree'/'parsed.json')
        teaching=read(root/'calls'/f'{key}-teaching'/'parsed.json')
        oldtree=read(baseline/'calls'/f'{key}-tree'/'parsed.json')
        oldteach=read(baseline/'calls'/f'{key}-teaching'/'parsed.json')
        compiled=compile_candidate(course,tree,teaching)
        assert compiled==read(root/'compiled'/(key+'.json'))
        v=REVIEWS[key]
        review={'reviewer':'Codex；逐项内容复核，非学科教师/真实学生效度验收',
                'candidate_digest':digest(compiled),
                'axes':{axis:axis in v['passed_axes'] for axis in REVIEW_AXES},
                'blockers':v['blockers'], 'evidence':['independent-checks.json',*v['improvements']],
                'prediction_checks':v['prediction_checks'],'repair_checks':v['repair_checks']}
        reviewed=attach_review(compiled,review)
        save(root/'reviewed'/(key+'.json'),reviewed)
        bank=question_bank(course)
        for s in reviewed['skills']:
            for c in s['criteria']:
                if c['probe_key'] in bank:
                    assert c['resolved_check']==bank[c['probe_key']]
                    frozen_count+=1
        row={'key':key,'title':course['title'], 'before_points':len(oldtree['points']), 'after_points':len(tree['points']),
             'before_criteria':sum(len(s['criteria']) for s in oldteach['skills']),
             'after_criteria':sum(len(s['criteria']) for s in teaching['skills']),
             'before_tree_errors':validate_tree(course,oldtree),'after_tree_errors':validate_tree(course,tree),
             'before_teaching_errors':validate_teaching(course,oldtree,oldteach),
             'after_teaching_errors':compiled['contract']['structural_issues'],
             'new_questions':len(teaching.get('supplemental_probes',[])),
             'coverage_review':[{'requirement':r,'points':p} for r,p in zip(course['coverage'],v['coverage'])],
             'sample_usable':reviewed['contract']['sample_usable'],**v}
        rows.append(row)
        records.append({'fixture':course,'tree':tree,'raw_teaching':teaching,'resolved_and_reviewed':reviewed,'review':row})
    metrics={'baseline':timing(baseline),'new':timing(root),'points':sum(r['after_points'] for r in rows),
             'criteria':sum(r['after_criteria'] for r in rows),'frozen_criterion_answers_identical':frozen_count,
             'new_questions':sum(r['new_questions'] for r in rows),
             'tree_structure_before':sum(not r['before_tree_errors'] for r in rows),
             'tree_structure_after':sum(not r['after_tree_errors'] for r in rows),
             'teaching_structure_before':sum(not r['before_teaching_errors'] for r in rows),
             'teaching_structure_after':sum(not r['after_teaching_errors'] for r in rows),
             'prediction_review':{'passed':sum(p[1] for r in rows for p in r['prediction_checks']),
                                  'total':sum(len(r['prediction_checks']) for r in rows)},
             'repair_review':{'passed':sum(p[1] for r in rows for p in r['repair_checks']),
                              'total':sum(len(r['repair_checks']) for r in rows)},
             'usable_courses':sum(r['sample_usable'] for r in rows),'control':read(root/'control-assessment.json'),
             'model_content_edits':0,'production_course_writes':0,
             'limits':'一次四微单元试验；换合同并允许补题，不能解释成单一因素因果效应；人工复核不等于自动验证或真实学生诊断效度。'}
    result={'metrics':metrics,'courses':rows}
    save(root/'comparison.json',result)
    save(destination/'对照与逐项复核.json',result)
    save(destination/'四门课程原始输出与冻结答案装配.json',records)
    save(destination/'冻结评测规则.json',read(root/'eval.json'))
    save(destination/'独立核验.json',read(root/'independent-checks.json'))
    lines=['# 语义绑定与诊断补救：四课复核','','原始千问内容未修订。正式课程没有写入。冻结答案由程序装配，内容仍按实际语义复核。','']
    for r in records:
        v=r['review'];lines+=['## '+v['title'],'','### 改善','']+['- '+x for x in v['improvements']]
        lines+=['','### 阻断项','']+['- `'+p+'`：'+why for p,why in v['blockers']]
        lines+=['','### 逐条错因与补救复核','','| 条目 | 错因预测 | 补救 |','| --- | --- | --- |']
        repairs={x[0]:x for x in v['repair_checks']}
        for key,ok,why in v['prediction_checks']:
            repair=repairs[key]
            lines+=['| '+key+' | '+('通过：' if ok else '未通过：')+why+' | '+('通过：' if repair[1] else '未通过：')+repair[2]+' |']
        lines+=['','### 本轮知识叶子','']+['- **'+p['key']+' '+p['name']+'**：'+p['statement'] for p in r['tree']['points']]
        lines+=['','### 检查题绑定','']
        for s in r['resolved_and_reviewed']['skills']:
            for c in s['criteria']:
                q=c['resolved_check'];lines+=['- '+c['point_key']+' → '+c['probe_key']+'：'+q['question'],
                    '  - 答案来源：'+q['answer_origin']+'；'+q['answer'],
                    '  - 模型绑定理由（未经采用）：'+c['binding']['why_direct']]
    (destination/'逐科候选与问题.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(metrics)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('baseline',type=Path);p.add_argument('destination',type=Path)
    a=p.parse_args();export(a.root,a.baseline,a.destination)
