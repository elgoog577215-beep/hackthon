"""Export independent, explicit adjudication without repairing model outputs."""
import argparse
from pathlib import Path
from .pipeline import read, save, digest
from .cross_course_round import validate_tree, validate_teaching

COVERAGE = {
    'python': [['P1'],['P2'],['P3'],['P4'],['P5'],['P6']],
    'calculus': [['P2'],['P3'],['P4'],['P5'],['P6','P8'],['P6','P7']],
    'physics': [['P1','P2'],['P1'],['P2'],['P3'],['P5','P6','P7'],['P8']],
    'history': [['P1'],['P2'],['P3'],['P4','P9'],['P5'],['P6','P10']],
}
FINDINGS = {
 'python': [
  ('tree.relations[*].strength','返回“强/中”等字符串，未遵守可持久化的数值/未知强度格式。'),
  ('tree.P1.meta_answer / P6.statement','把Python对象身份、引用描述为内存地址或指针，超出给定材料及Python语言层面的保证；应统一为对象/引用术语。'),
  ('teaching.S1.mistakes.A','绑定Q1（a is b），预测却回答添加元素后a的值，即Q2情境；引用存在不等于真的检查了所引用的题。'),
  ('teaching.criteria','多个达标标准虽绑定冻结Q题，却使用新训练题的变量值与操作序号，无法直接作为所绑定Q题的评分条件。'),
  ('teaching.S1.retest','S1仅覆盖赋值别名，选择的R2还依赖浅拷贝和元素替换；应补齐能力依赖或调整复测范围。')],
 'calculus': [
  ('tree.P6','把连续不能推出可导、不可导不能推出不连续合在一个叶子；元问题只问前者，独立检查粒度不一致。'),
  ('tree.P8 / categories','将完整反例同时作为独立知识叶子，和定义/关系并列；应区分知识规则、范围前提和应用例证。'),
  ('teaching.S1.criteria[P1,P2]','两条probe_key为null，达标证据未绑定题库；P1范围前提被新增为叶子，但题库没有直接测试它。'),
  ('teaching.S2.criteria[P7]','P7是不连续→不可导，绑定Q6却检查不可导是否推出不连续；问的是另一推理方向。'),
  ('teaching.S1.mistakes.A.reason','用“没有尖角/拐点”描述可导，混淆尖角与可导函数也可具有的拐点；补救直观不宜替代差商条件。')],
 'physics': [
  ('tree.relations[*].strength','返回strong/moderate字符串，与通用存储格式不符。'),
  ('teaching.S1.criteria[P4]','材料只给相互作用力等大、质量不同，未说明各物体合力；不能直接推出加速度不等。F=ma使用合外力，不是任意一对相互作用力。'),
  ('teaching.S1.criteria[P4] / discrimination','Q2只问相互作用力谁更大，不能据此确认学生会比较加速度；引用的题没有实际考到标准。'),
  ('teaching.S2.task','将“两车及外部拉力系统”都选为整体，与只选两车的冻结题改变了系统边界，后续外力结论未同步。'),
  ('teaching.S2.mistakes.B.repair','把“箭头指向受力对象”作为受力图规则，容易混淆受力归属和力方向；应按施力者/受力者识别力，箭头表示其方向。')],
 'history': [
  ('tree.P7-P10','把具体虚构材料内容与证据缺口作为通用知识叶子，导致案例一变知识树就需重建；应作为材料/案例实体引用。'),
  ('tree.P8.meta_answer','将收入与工时同时变化写成“作为代价”，加入材料没有给出的因果解释。'),
  ('teaching.S1.criteria[P8] / S2.criteria[P6]','把工人日记中的陈述写成已证明的个人事实；应区分“材料记载如此”和“事件已经被证实”。'),
  ('teaching.S1.criteria[P2] / repair','将可能的选择性呈现、争取资金或隐瞒劳资纠纷写成确定动机，超出虚构材料；也不能要求学生必须采用这些特定解释。'),
  ('teaching.S1.expected_evidence','要求明确提及固定关键概念，缺少接受同义表达和其他有证据论证的显式标准；开放评价的方向已有，但边界未稳固。')],
}


def export(root, output):
    fixtures=read(root/'fixtures.json');records=[];summary=[]
    for c in fixtures:
        key=c['key'];tree=read(root/'calls'/f'{key}-tree'/'parsed.json');teaching=read(root/'calls'/f'{key}-teaching'/'parsed.json')
        ids={p['key'] for p in tree['points']}
        assert len(COVERAGE[key])==len(c['coverage']) and all(set(v)<=ids for v in COVERAGE[key])
        row={'course':key,'title':c['title'],'point_count':len(tree['points']),
             'skills':len(teaching['skills']),'criteria':sum(len(s['criteria']) for s in teaching['skills']),
             'tree_structure_errors':validate_tree(c,tree),'teaching_structure_errors':validate_teaching(c,tree,teaching),
             'coverage_review':[{'requirement':rule,'covered_by':points} for rule,points in zip(c['coverage'],COVERAGE[key])],
             'reviewer':'Codex','ready_for_adoption':False,'findings':[{'field':f,'finding':m} for f,m in FINDINGS[key]],
             'review_limit':'一份人工准备的短材料、每阶段单次生成；不代表整课覆盖或稳定通过率'}
        records.append({'fixture':c,'tree':tree,'teaching':teaching,'review':row});summary.append(row)
    calls=[read(p) for p in (root/'calls').glob('*/result.json')]
    metrics={'model':'qwen3.8-27b','calls':len(calls),'completed':sum(c['state']=='completed' for c in calls),
             'seconds':round(sum(c.get('seconds',0) for c in calls),2),'points':sum(s['point_count'] for s in summary),
             'skills':sum(s['skills'] for s in summary),'scope_requirements':24,'covered_scope_requirements':24,
             'tree_structure_passed':sum(not s['tree_structure_errors'] for s in summary),
             'teaching_structure_passed':sum(not s['teaching_structure_errors'] for s in summary),
             'semantically_ready_courses':0,'insufficient_material_control':read(root/'control-assessment.json'),
             'production_changes':False,'model_content_repairs':0,
             'configuration_changes':['中性学科提示词','材料抽取阶段为隔离原型新增能力','允许1-2个错因而非固定3个','按学科采用exact/reasoning/rubric证据'],
             'comparison_limit':'这不是原C17代码原样运行的成功率，也不能和上一轮C17的0/15直接横比。'}
    save(root/'final-assessment.json',{'metrics':metrics,'courses':summary})
    output.mkdir(parents=True,exist_ok=True)
    save(output/'四门课程原始结果与复核.json',records)
    save(output/'跨课程评测结果.json',{'metrics':metrics,'courses':summary})
    save(output/'冻结评测规则.json',read(root/'eval.json'))
    save(output/'独立核验.json',read(root/'independent-checks.json'))
    lines=['# 跨课程通用性：原始候选与逐项复核','','中性提示词隔离原型；没有写入正式课程，没有修改模型内容。','']
    for r in records:
        c=r['fixture'];lines += ['## '+c['title'],'','### 复核问题','']
        lines += ['- `'+f['field']+'`：'+f['finding'] for f in r['review']['findings']]
        lines += ['','### 知识叶子','']
        for p in r['tree']['points']:
            lines += ['- **'+p['key']+' '+p['name']+'**：'+p['statement'],'  - 前提：'+'；'.join(p['conditions']),'  - 元问题：'+p['meta_question'],'  - 回答：'+p['meta_answer']]
        lines += ['','### 能力与教学候选','']
        for s in r['teaching']['skills']:
            lines += ['#### '+s['name'],'',s['observable_behavior'],'',s['task']['prompt'],'','需提交：'+s['task']['expected_evidence'],'']
            lines += ['- '+x['point_key']+' → '+str(x['probe_key'])+'：'+x['pass_evidence'] for x in s['criteria']]
            for m in s['mistakes']:
                lines += ['','错因候选：'+m['wrong_rule'],'','预测（待核验）：'+m['prediction'],'','补救：'+'；'.join(m['repair_steps'])]
            lines += ['','区分依据：'+s['discrimination']['distinguishes'],'','局限：'+s['discrimination']['limits'],'']
    (output/'四门课程对照样稿.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(metrics)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('output',type=Path);a=p.parse_args();export(a.root,a.output)
