"""One-shot handout trial from the reviewed sample. Never writes live courses.

Qwen owns exposition; verified examples and check answers are resolved by stable
references. The separate trial report does not install a production audit loop.
"""
from pathlib import Path
from copy import deepcopy
from collections import Counter
import argparse
import hashlib
import json
import re
from .pipeline import read, save, digest, code_hash

APP=Path(__file__).resolve().parents[2]
TITLES={"types":"第1讲　数值类型转换", "if":"第2讲　if 的语句范围与 else 配对", "for":"第3讲　for 控制流"}
PREFIX={"types":"T","if":"I","for":"F"}
TERMS={
 "types":[("integer_literal","整数字面量",["整数常量"]),("integer_promotion","整数提升",[]),
  ("usual_conversion","通常算术转换",[]),("cast","显式类型转换",["强制类型转换"]),
  ("truncate","向零截断",[]),("mod_conversion","无符号整数的模转换",["模转换"]),
  ("implementation_defined","实现定义",[]),("undefined","未定义行为",["UB"]),
  ("range","数值范围",[]),("precision","有效精度",[])],
 "if":[("scalar","标量表达式",[]),("branch","分支体",[]),("compound","复合语句",["语句块"]),
  ("pairing","else 配对",["else归属"]),("null_statement","空语句",[]),
  ("chain","if/else-if 选择链",["选择链"]),("independent","独立 if",["独立if"])],
 "for":[("initializer","初始化子句",["初始化部分"]),("control","控制表达式",["条件表达式","控制条件"]),
  ("iteration","迭代表达式",["更新表达式","第三部分"]),("body","循环体",[]),
  ("scope","作用域",[]),("null_statement","空语句",[]),
  ("wrap","无符号回绕",["无符号整数回绕"]),("overflow","有符号整数溢出",[])]}

SECTIONS={
 "types":[
  ("types1","先确定表达式的类型",["默认整型","1U 的类型","浮点默认","整数提升规则","int 与 double 的共同类型","int与unsigned int的通常算术转换方向"]),
  ("types2","先计算再转换",["整数除法截断","接收类型不反向改变表达式","显式转换的位置","转换表达式不改原变量"]),
  ("types3","转换的边界",["模转换","有符号越界","可表示整数转换保持数值","浮点截断","浮点越界"]),
  ("types4","精度与易错辨析",["整数到浮点"])],
 "if":[
  ("if1","条件、语句范围与一次分支选择",["标量条件的真值语义","一次执行不重新选分支","分支体的语句范围"]),
  ("if2","else 配对：语法、花括号与缩进",["else 的词法就近配对","花括号显式修改 else 归属","缩进不改变语法归属"]),
  ("if3","外层未进入与空语句陷阱",["未进入外层则不执行内层","空语句对控制范围的破坏"]),
  ("if4","选择链与独立判断",["else if 的语法结构","选择链首命中后停止判断","独立 if 可以多次命中","后续 if 读取新状态"])],
 "for":[
  ("for1","一次 for 循环怎样推进",["初始化子句执行频次","每次入体前判断条件","首判为假与零次执行","体后更新顺序","正常退出时的条件判断次数"]),
  ("for2","头部省略与循环体范围",["省略初始化使用已有状态","省略条件视为真","省略迭代不自动更新","for头部保留两个分号","for 的单语句体","for 的空语句体"]),
  ("for3","continue、break、return 与嵌套目标",["continue 的执行逻辑","break 退出机制","return 结束机制","switch 内 break 的作用域","switch 内 continue 的目标"]),
  ("for4","变量作用域与终止边界",["头部声明的作用域","外部变量最终值","循环体修改变量","无符号变量倒序终止失败","有符号最大值后的迭代溢出"])]}

EXAMPLE_NAMES={
 "types":["整数除法截断","接收类型不反向改变表达式","显式转换的位置","转换表达式不改原变量","浮点截断","模转换"],
 "if":["标量条件的真值语义","一次执行不重新选分支","分支体的语句范围","未进入外层则不执行内层","选择链首命中后停止判断","后续 if 读取新状态"],
 "for":["首判为假与零次执行","体后更新顺序","continue 的执行逻辑","break 退出机制","return 结束机制","循环体修改变量","switch 内 break 的作用域","for 的空语句体"]}

PROMPT="""基于输入的已复核知识树，为初学者写一讲可独立阅读的中文教材式讲义。
这是一次整讲生成，必须完成所有小节。不要写备课教案、教师口播、模拟学生回应或AI工作记录。
用连贯段落解释规则、适用条件、因果和边界，再衔接例题与练习；不能只是逐条照抄知识卡或大纲。
四个小节的key、顺序与教学范围已给定；每个required_knowledge_key都要在有实际讲解的explanation块中引用。
若applications非空，须结合相应原子知识说明综合应用的控制流，不能因为它不是叶子就遗漏；用其knowledge_keys绑定讲解。
保持所有输入条件，不把int/unsigned int规则推广到任意类型，不把整数提升放到所有浮点混合运算前，不把无符号回绕写成UB。
术语优先使用terminology的canonical，允许列出的alias；术语首次出现时解释含义。禁止把别名当成另一个知识点。
知识标签只是稳定引用的短键，不是正文标题。每块knowledge_keys只能用本讲给定的真实短键。

例题和练习采用引用：example_bank内代码及已核验答案会由程序原样插入，不要复制代码、不另写output/answer字段。
你需要在worked_example块的text中说明观察什么、为何得到该结果、如何使用相关规则，可以解释数值但必须与给定答案一致。
至少使用4个不同的worked_example引用；不要改参数或在文字里改成另一道题。不要新增代码围栏或自造未核验的完整程序。
允许在讲解中写短小行内C表达式；这些也必须符合知识基线。输入代码都是void sample(void)的函数体片段，已有stdio.h、limits.h等头文件。
一种diagnosis块引用本讲固定的错因辨析，程序会插入三题、正确答案、A/B预测及分原因补救；你的text写如何理解比较，不能把错误预测冒充正确答案或确诊学生。
挑选4~6条exercise_bank中的练习作为本讲自测，给出exercise_keys；题干、答案、条件与依据由程序插入，不自行改写答案。
最后用summary块总结解题顺序与注意边界。正文要求内容充实，可供自主阅读，约2000~3500汉字，不能用长列表代替解释。

严格JSON格式：
{"title":"讲义标题","knowledge_revision":"输入原值","terminology_revision":"输入原值","introduction":"简短引入",
"sections":[{"key":"给定小节key","title":"给定标题","blocks":[
{"kind":"explanation|worked_example|diagnosis|summary","heading":"小标题","text":"中文教材段落，可使用普通Markdown，不含代码围栏",
"knowledge_keys":["K-T01"],"term_keys":["给定术语key"],"example_key":null,"diagnostic_key":null}]}],
"exercise_keys":["Q-T01"],"unresolved":[]}。
worked_example必须填example_key，其他类型为null；diagnosis必须填diagnostic_key，其他类型为null。
全讲恰好一个diagnosis块，至少一个summary块。模型不输出任何程序代码字段、答案字段或正式知识ID；这些由引用解析得到。
只输出最终JSON，不要Markdown围栏、思考过程、自我修正独白或请求再次继续。"""


def project_applications(applications,label_by_id):
    return [{**deepcopy(a),'knowledge_keys':[label_by_id[pid] for pid in a['knowledge_ids']]}
            for a in applications if a.get('knowledge_ids') and set(a['knowledge_ids'])<=set(label_by_id)]


def build(root,baseline_path,evidence):
    root.mkdir(parents=True,exist_ok=True)
    if (root/"manifest.json").exists():raise ValueError("trial_already_initialized")
    baseline=read(baseline_path)
    assert baseline['assessment']['reviewed_sample_gate']['passed']
    save(root/"knowledge.snapshot.json",baseline)
    revision=digest(baseline)
    terms={t:[{"key":key,"canonical":canonical,"aliases":aliases} for key,canonical,aliases in rows] for t,rows in TERMS.items()}
    save(root/"terminology.json",terms);term_revision=digest(terms)
    nodes={p['name']:p for p in baseline['points']}
    primaries={c['point_id']:c for c in baseline['checks']}
    jobs=[];bundles={}
    for topic,plan in SECTIONS.items():
        selected=[nodes[name] for _,_,names in plan for name in names]
        assert len(selected)==len({p['id'] for p in selected})
        label_by_id={p['id']:f"K-{PREFIX[topic]}{i:02d}" for i,p in enumerate(selected,1)}
        points=[{"key":label_by_id[p['id']],"knowledge_id":p['id'],"name":p['name'],"statement":p['statement'],
                 "conditions":p['conditions'],"meta_question":p['question'],"meta_answer":p['answer'],"source_refs":p['source_refs']} for p in selected]
        sections=[{"key":key,"title":title,"required_knowledge_keys":[label_by_id[nodes[name]['id']] for name in names]} for key,title,names in plan]
        probes=read(evidence/topic/'review-probes.json')
        receipts={r['check_id']:r for r in read(evidence/topic/'review-probe-code/results.json')}
        examples=[]
        for i,name in enumerate(EXAMPLE_NAMES[topic],1):
            pid=nodes[name]['id'];probe=next(p for p in probes if pid in p['knowledge_ids'])
            receipt=receipts[probe['id']]
            assert probe['reviewed_question_hash']==digest(primaries[pid])
            assert receipt['status']=='executed' and receipt['optimization_agrees'] and receipt['returncode']==0
            assert receipt['code_hash']==code_hash(probe) and receipt['stdout']==probe['predicted_stdout']
            examples.append({"key":f"E-{PREFIX[topic]}{i:02d}","title":name,"knowledge_keys":[label_by_id[pid]],
                "code":probe['code'],"answer_stdout":receipt['stdout'],"answer_ref":{"check_id":probe['id'],"code_hash":receipt['code_hash'],"receipt_hash":digest(receipt),"environment_hash":receipt['environment_hash']},
                "context":"void sample(void)函数体；代码与输出来自前轮已核验例子","origin":"reviewed_baseline_probe"})
        diag=next(m for m in baseline['misconceptions'] if m['topic']==topic)
        program_by_id={c['id']:c for c in diag['plan']['checks']}
        diagnosis={"key":"D-"+PREFIX[topic],"knowledge_keys":[label_by_id[pid] for pid in diag['plan']['knowledge_ids']],
            "hypothesis_a":diag['plan']['hypothesis_a'],"hypothesis_b":diag['plan']['hypothesis_b'],
            "repair_a":diag['plan']['repair_a'],"repair_b":diag['plan']['repair_b'],"examples":[]}
        for role in ['symptom','diagnostic','retest']:
            cid=diag['plan']['roles'][role]['correct'];program=program_by_id[cid];obs=diag['grade']['observations'][role]
            assert code_hash(program)==obs['correct']['code_hash']
            diagnosis['examples'].append({'role':role,'code':program['code'],'answer_stdout':obs['correct']['value'],
                'prediction_a':obs['a']['value'],'prediction_b':obs['b']['value'],'answer_ref':obs['correct']})
        exercises=[{"key":"Q-"+p['key'][2:],"knowledge_keys":[p['key']],
                    **{k:primaries[p['knowledge_id']][k] for k in ['question','answer','rationale','conditions']}} for p in points]
        bundle={"topic":topic,"title":TITLES[topic],"knowledge_revision":revision,"terminology_revision":term_revision,
            "course":"C17基础程序设计三组试写样稿","learner":"已认识变量、简单算术和语句的初学者",
            "points":points,"terminology":terms[topic],"sections":sections,"example_bank":examples,
            "diagnostic":diagnosis,"exercise_bank":exercises,"baseline_scope":"用户指定第四轮复核样本用于本次试写，不代表正式课程已采用"}
        bundle['applications']=project_applications(baseline.get('applications',[]),label_by_id)
        bundles[topic]=bundle
        save(root/topic/'bundle.json',bundle)
        jobs.append({"id":topic+'-handout',"topic":topic,"kind":"handout","max_tokens":14000,"instruction":PROMPT,"input":bundle})
    assert sum(len(b['points']) for b in bundles.values())==49
    save(root/'jobs.json',jobs)
    save(root/'protocol.json',{"version":"knowledge_bound_handout_trial_v1","model_calls_max":3,"one_call_per_lecture":True,
        "model_repair_calls":0,"baseline_revision":revision,"terminology_revision":term_revision,
        "evaluation":"User-requested offline consistency assessment; no production handout audit/rewrite loop.",
        "acceptance":["same frozen revision and terminology","all 49 points explained and referenced","references resolve within topic and to true supporting facts",
            "example and exercise answers resolve from approved evidence","prose explanations agree with rules, conditions and example outputs","readable textbook material, not an outline"],
        "grading":"Machine checks for structure/references; Codex nonblind semantic reading; no model self-audit or automatic rewrite.",
        "data_boundary":"No live course, handout, job or learning record writes."})
    frozen=[root/'knowledge.snapshot.json',root/'terminology.json',root/'jobs.json',root/'protocol.json']+[root/t/'bundle.json' for t in bundles]
    save(root/'manifest.json',{"model_calls_max":3,"input_hashes":{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in frozen}})
    print('Frozen',revision,'; three handout jobs')


def inspect(bundle,doc):
    issues=[];bindings=[];covered=set();examples=[];diagnoses=0;summary=0
    applications={a['id']:a for a in bundle.get('applications',[])};explained_applications=set()
    known={p['key']:p for p in bundle['points']};terms={t['key']:t for t in bundle['terminology']}
    eb={e['key']:e for e in bundle['example_bank']};qb={q['key']:q for q in bundle['exercise_bank']}
    if not isinstance(doc,dict):return {'issues':[{'code':'not_object'}],'bindings':[]}
    for field in ['knowledge_revision','terminology_revision']:
        if doc.get(field)!=bundle[field]:issues.append({'code':field+'_mismatch'})
    sections=doc.get('sections',[])
    if not isinstance(sections,list):sections=[];issues.append({'code':'sections_not_array'})
    if [s.get('key') for s in sections if isinstance(s,dict)]!=[s['key'] for s in bundle['sections']]:issues.append({'code':'section_order'})
    plan={s['key']:s for s in bundle['sections']}
    for si,s in enumerate(sections):
        if not isinstance(s,dict):issues.append({'code':'section_not_object','section':si});continue
        section_coverage=set()
        blocks=s.get('blocks',[])
        if not isinstance(blocks,list):issues.append({'code':'blocks_not_array','section':si});blocks=[]
        for bi,b in enumerate(blocks):
            where=f"{s.get('key',si)}:{bi+1}"
            if not isinstance(b,dict):issues.append({'code':'block_not_object','block':where});continue
            kind=b.get('kind');keys=b.get('knowledge_keys',[]);tkeys=b.get('term_keys',[])
            if kind not in ['explanation','worked_example','diagnosis','summary']:issues.append({'code':'block_kind','block':where})
            if not isinstance(keys,list) or not keys or any(not isinstance(k,str) or k not in known for k in keys):
                issues.append({'code':'knowledge_refs','block':where});keys=[k for k in keys if isinstance(k,str) and k in known] if isinstance(keys,list) else []
            if not isinstance(tkeys,list) or any(not isinstance(k,str) or k not in terms for k in tkeys):issues.append({'code':'term_refs','block':where})
            text=b.get('text','')
            if not isinstance(text,str) or not text.strip():issues.append({'code':'empty_text','block':where});text=''
            if '```' in text:issues.append({'code':'unbound_code_fence','block':where})
            if any(k in b for k in ['code','answer','output','expected_stdout']):issues.append({'code':'unbound_answer_or_code','block':where})
            if kind=='explanation':section_coverage.update(keys);covered.update(keys)
            if kind=='worked_example':
                e=eb.get(b.get('example_key')) if isinstance(b.get('example_key'),str) else None
                if not e:issues.append({'code':'example_ref','block':where})
                else:
                    examples.append(e['key'])
                    if not set(e['knowledge_keys'])<=set(keys):issues.append({'code':'example_knowledge_mismatch','block':where})
            if kind=='diagnosis':
                diagnoses+=1
                if b.get('diagnostic_key')!=bundle['diagnostic']['key']:issues.append({'code':'diagnostic_ref','block':where})
                if not set(bundle['diagnostic']['knowledge_keys'])<=set(keys):issues.append({'code':'diagnostic_knowledge_mismatch','block':where})
            if kind=='summary':summary+=1
            akeys=b.get('application_keys',[])
            if not isinstance(akeys,list) or any(not isinstance(k,str) or k not in applications for k in akeys):
                issues.append({'code':'application_refs','block':where});akeys=[]
            for key in akeys:
                if not set(applications[key]['knowledge_keys'])<=set(keys):issues.append({'code':'application_knowledge_mismatch','block':where})
                if kind=='explanation':explained_applications.add(key)
            bindings.append({'block':where,'block_id':b.get('block_id',where),'kind':kind,'knowledge_keys':keys,'knowledge_ids':[known[k]['knowledge_id'] for k in keys],
                             'application_ids':akeys,
                             'knowledge_revision':bundle['knowledge_revision'],'terminology_revision':bundle['terminology_revision']})
        missing=set(plan.get(s.get('key'),{}).get('required_knowledge_keys',[]))-section_coverage
        if missing:issues.append({'code':'section_explanation_coverage','section':s.get('key'),'missing':sorted(missing)})
    if len(set(examples))<4:issues.append({'code':'too_few_examples'})
    if diagnoses!=1:issues.append({'code':'diagnosis_count','count':diagnoses})
    if not summary:issues.append({'code':'missing_summary'})
    missing_apps=set(applications)-explained_applications
    if missing_apps:issues.append({'code':'missing_application_explanation','missing':sorted(missing_apps)})
    qkeys=doc.get('exercise_keys',[])
    if not isinstance(qkeys,list) or not 4<=len(qkeys)<=6 or any(not isinstance(k,str) for k in qkeys) or len(set(qkeys))!=len(qkeys) or any(k not in qb for k in qkeys):issues.append({'code':'exercise_refs'})
    if doc.get('unresolved'):issues.append({'code':'model_unresolved','items':doc['unresolved']})
    return {'issues':issues,'bindings':bindings,'explained_keys':sorted(covered),'expected_knowledge_points':len(known),
            'unique_examples':len(set(examples)),'exercise_keys':qkeys,'diagnoses':diagnoses,
            'summaries':summary,'explained_applications':sorted(explained_applications),
            'canonical_terms_present':[t['canonical'] for t in terms.values() if t['canonical'] in json.dumps(doc,ensure_ascii=False)],
            'note':'Coverage counts references in explanation blocks, not proof of correct semantic explanation.'}


def resolved_assets(bundle,doc):
    ekeys=[];qkeys=[];dkeys=[]
    for s in doc.get('sections',[]):
        if not isinstance(s,dict):continue
        ekeys += [k for k in s.get('example_keys',[]) if isinstance(k,str)]
        qkeys += [k for k in s.get('exercise_keys',[]) if isinstance(k,str)]
        for b in s.get('blocks',[]):
            if not isinstance(b,dict):continue
            if b.get('kind')=='worked_example' and isinstance(b.get('example_key'),str):ekeys.append(b['example_key'])
            if b.get('kind')=='diagnosis' and isinstance(b.get('diagnostic_key'),str):dkeys.append(b['diagnostic_key'])
    qkeys += [k for k in doc.get('exercise_keys',[]) if isinstance(k,str)]
    eb={e['key']:e for e in bundle['example_bank']};qb={q['key']:q for q in bundle['exercise_bank']}
    return {'examples':[deepcopy(eb[k]) for k in dict.fromkeys(ekeys) if k in eb],
            'exercises':[deepcopy(qb[k]) for k in dict.fromkeys(qkeys) if k in qb],
            'diagnostic':deepcopy(bundle['diagnostic']) if bundle['diagnostic']['key'] in dkeys else None}


def render(bundle,doc,assessment,destination):
    points={p['key']:p for p in bundle['points']};examples={e['key']:e for e in bundle['example_bank']};exercises={q['key']:q for q in bundle['exercise_bank']}
    editorial=doc.get('editorial_revision')
    banner=('知识树驱动讲义修订稿。根据用户要求由 Codex 定向修订，初稿另存供对照；例题、诊断与自测答案继续使用同一知识基线。'
            if editorial else '知识树驱动试写样稿。正文为千问首次输出；例题、诊断和自测答案按冻结引用插入。独立核对结论见配套验收报告。')
    lines=['# '+str(doc.get('title',bundle['title'])),'',banner,'',
           str(doc.get('introduction','')),'','本讲按 C17 讨论。代码示例为 `void sample(void)` 函数体内的片段，已包含 `<stdio.h>`、`<limits.h>` 等头文件，由 `main` 调用；出现 `return;` 表示结束该 `sample` 函数。','']
    if editorial:
        lines+=['需要运行例题时，将一个例题片段放入下面模板的 `sample` 中，以 C17 编译 `.c` 文件。不同例题分别运行，不把各题片段连续粘在同一个函数里。','',
                '```c','#include <stdio.h>','#include <limits.h>','',
                'void sample(void) {','    /* 在此放入一个例题片段 */','}',
                'int main(void) {','    sample();','    return 0;','}','```','']
    terms='；'.join(t['canonical']+('（可用别名：'+'、'.join(t['aliases'])+'）' if t['aliases'] else '') for t in bundle['terminology'])
    lines+=['本讲统一术语：'+terms+'。','']
    legacy=any(isinstance(s,dict) and isinstance(s.get('paragraphs'),list) for s in doc.get('sections',[]))
    if legacy:
        lines+=['> 本组模型返回了段落式结构，未提供约定的逐块知识引用。以下保留原段落并解析其明确给出的例题、练习键；没有替模型补写引用。','']
    for section in doc.get('sections',[]):
        if not isinstance(section,dict):continue
        lines+=['## '+str(section.get('title',section.get('heading','未命名小节'))),'']
        if isinstance(section.get('paragraphs'),list):
            for paragraph in section['paragraphs']:
                if isinstance(paragraph,str):lines+=[paragraph,'']
            for key in section.get('example_keys',[]):
                if isinstance(key,str) and key in examples:
                    e=examples[key]
                    lines+=['### 例题 '+key+'：'+e['title'],'','```c',e['code'],'```','',
                            '标准输出（核验记录）：','','```text',e['answer_stdout'].rstrip(),'```','']
                    if e['answer_stdout'].rstrip('\n').endswith((' ','\t')):
                        lines+=['输出末尾含空白；精确输出字符串：`'+json.dumps(e['answer_stdout'],ensure_ascii=False)+'`。','']
        for b in section.get('blocks',[]):
            if not isinstance(b,dict):continue
            lines+=['### '+str(b.get('heading','')),'']
            kind=b.get('kind');ref=b.get('example_key')
            if kind=='worked_example' and ref in examples:
                e=examples[ref]
                lines+=['**例题 '+ref+'：'+e['title']+'**','','```c',e['code'],'```','','标准输出（核验记录）：','','```text',e['answer_stdout'].rstrip(),'```','']
                if e['answer_stdout'].rstrip('\n').endswith((' ','\t')):
                    lines+=['输出末尾含空白；精确输出字符串：`'+json.dumps(e['answer_stdout'],ensure_ascii=False)+'`。','']
            if kind=='diagnosis' and b.get('diagnostic_key')==bundle['diagnostic']['key']:
                d=bundle['diagnostic'];lines+=['- 错误信念 A：'+d['hypothesis_a'],'- 错误信念 B：'+d['hypothesis_b'],'']
                for case in d['examples']:
                    label={'symptom':'共同表现题','diagnostic':'区分题','retest':'变式复测'}[case['role']]
                    lines+=['**'+label+'**','','```c',case['code'],'```','',
                        '正确输出：`'+case['answer_stdout'].strip()+'`；按错误信念 A 预测：`'+case['prediction_a'].strip()+'`；按 B 预测：`'+case['prediction_b'].strip()+'`。','']
                lines+=['针对 A：'+d['repair_a'],'','针对 B：'+d['repair_b'],'',
                    '上述错误预测是固定假设的模拟；一次作答不能直接确认学生真实错因。','']
            lines+=[str(b.get('text','')),'']
            refs=[k+' '+points[k]['name'] for k in b.get('knowledge_keys',[]) if k in points]
            lines+=['知识依据：'+'；'.join(refs)+'。','']
    lines+=['## 自测与参考解答','']
    qkeys=doc.get('exercise_keys',[])
    if legacy:
        qkeys=list(dict.fromkeys(k for s in doc.get('sections',[]) if isinstance(s,dict) for k in s.get('exercise_keys',[]) if isinstance(k,str)))
    selected=[exercises[k] for k in qkeys if isinstance(k,str) and k in exercises]
    for i,q in enumerate(selected,1):lines+=[f"### 自测 {i} · {q['key']}",'',q['question'],'','适用条件：'+'；'.join(q['conditions']),'']
    lines+=['### 参考解答','']
    for i,q in enumerate(selected,1):lines+=[f"{i}. {q['answer']} {q['rationale']}",'']
    lines+=['## 输入知识范围索引','',
            '下表是本讲输入的知识范围，不表示正文已逐点解释或正确引用；实际块绑定和缺口见绑定记录及验收报告。','',
            '本讲知识基线：`'+bundle['knowledge_revision']+'`；术语版本：`'+bundle['terminology_revision']+'`。','',
            '| 本讲标签 | 元知识 | 稳定知识 ID | 来源 |','| --- | --- | --- | --- |']
    for p in bundle['points']:lines.append('| '+p['key']+' | '+p['name']+' | `'+p['knowledge_id']+'` | '+', '.join(p['source_refs'])+' |')
    lines+=['','原始知识基线见同目录 `知识基线.snapshot.json`；输入、块引用及例题回执见对应的 `.bindings.json`。','']
    destination.mkdir(parents=True,exist_ok=True)
    filename={'types':'01-数值类型转换','if':'02-if配对与语句范围','for':'03-for控制流'}[bundle['topic']]
    (destination/(filename+'.md')).write_text('\n'.join(lines),encoding='utf-8')
    save(destination/(filename+'.bindings.json'),{'input_bundle':bundle,'output_hash':digest(doc),'assessment':assessment,
        'returned_schema':'paragraph_sections_without_block_bindings' if legacy else 'requested_block_schema',
        'editorial_revision':editorial,
        'resolved_exercise_keys':qkeys,
        'resolved_assets':resolved_assets(bundle,doc),
        'renderer_contract':('Exposition is the explicitly recorded Codex revision; canonical code and answers remain bound to the unchanged knowledge snapshot.' if editorial else 'Exposition remains model text; reference expansion inserts canonical code, answers and knowledge identities without another model call. Legacy paragraph fields are retained without inventing block knowledge links.')})


def export(root,destination):
    manifest=read(root/'manifest.json')
    assert all(hashlib.sha256((root/name).read_bytes()).hexdigest()==h for name,h in manifest['input_hashes'].items())
    all_reports={}
    for topic in SECTIONS:
        bundle=read(root/topic/'bundle.json');doc=read(root/'calls'/(topic+'-handout')/'parsed.json')
        report=inspect(bundle,doc);save(root/topic/'structure-report.json',report)
        render(bundle,doc,report,destination);all_reports[topic]=report
        print(topic,'explained',len(report['explained_keys']),'of',report['expected_knowledge_points'],'issues',report['issues'])
    save(destination/'知识基线.snapshot.json',read(root/'knowledge.snapshot.json'))
    save(root/'structure-report.json',all_reports)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('stage',choices=['build','export'])
    parser.add_argument('--baseline',type=Path);parser.add_argument('--evidence',type=Path);parser.add_argument('--destination',type=Path)
    args=parser.parse_args()
    if args.stage=='build':build(args.root,args.baseline,args.evidence)
    else:export(args.root,args.destination)
