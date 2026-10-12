"""Partial held-out evaluation. Never fabricates absent atom/tree results."""
from pathlib import Path
import argparse
from .pipeline import read,save,digest
from .foundation_round import validate_inventory

# This ledger was adjudicated after reading raw claims, without feeding it back.
LEDGER={
 'M1':[('covered',['C1','C2']),('covered',['C3']),('covered',['C4']),('covered',['C5','C6']),('covered',['C8']),('covered',['C8'])],
 'M2':[('covered',['C1','C2']),('covered',['C5']),('covered',['C6','C7']),('covered',['C8']),('covered',['C9']),('covered',['C10','C11'])],
 'M3':[('covered',['C1']),('covered',['C2']),('covered',['C3']),('covered',['C4']),('covered',['C5']),('covered',['C5']),('covered',['C6']),('covered',['C7','C8']),('covered',['C9','C10','C11']),('covered',['C12']),('partial',['C13']),('covered',['C14'])],
 'M5':[('covered',['C1']),('covered',['C2']),('covered',['C14']),('covered',['C3']),('covered',['C4','C5']),('covered',['C6','C7']),('covered',['C8']),('covered',['C9']),('partial',['C10']),('missing',[]),('covered',['C11']),('covered',['C12','C15'])],
 'M6':[('partial',['C1']),('covered',['C2']),('partial',['C3']),('covered',['C10']),('missing',[]),('partial',['C4']),('covered',['C5']),('covered',['C5']),('partial',[]),('covered',['C6']),('covered',['C7']),('covered',['C8'])],
 'M7':[('covered',['C1']),('covered',['C2']),('partial',['C4','C13']),('covered',['C6','C7']),('covered',['C9']),('covered',['C10']),('covered',['C5','C12']),('covered',['C14','C15']),('covered',['C16']),('missing',[]),('covered',['C17','C18','C19'])],
 'M8':[('covered',['C1']),('partial',['C2','C3']),('partial',['C3']),('covered',['C4','C5'])]}


def export(root,destination):
    course=read(root/'fixtures.json')[0];requirements=read(root/'requirements.json');records=[];coverage=[]
    for material in course['materials']:
        key=material['id'];p=root/'calls'/(key+'-inventory')/'parsed.json'
        inv=read(p) if p.exists() else None
        states=LEDGER.get(key,[('unavailable',[]) for _ in requirements[key]])
        assert len(states)==len(requirements[key])
        for req,(state,refs) in zip(requirements[key],states):
            if refs:assert set(refs)<={c['key'] for c in inv['claims']}
            coverage.append({'source_id':key,'requirement':req,'status':state,'claim_refs':refs,
                             'stage':'inventory only; not atomic knowledge acceptance','reviewer':'Codex'})
        public_claims=[]
        if inv:
            for claim in inv['claims']:
                # Complete source quotes remain in the private raw-call folder.
                public_claims.append({k:v for k,v in claim.items() if k!='quote'}|{
                    'source_url':material['url'],'quote_digest':digest(claim['quote']),
                    'quote_start':material['text'].find(claim['quote']),'quote_length':len(claim['quote'])})
        records.append({'source_id':key,'title':material['title'],'url':material['url'],
            'inventory_available':bool(inv),'claims':public_claims,
            'inventory_errors':validate_inventory({'materials':[material]},inv) if inv else ['call_failed'],
            'atoms_available':False,'classification_available':False})
    roots=[root.parent/n for n in ['holdout-sql-20261011','holdout-sql-recovery-20261011','holdout-sql-compact-20261011']]
    all_results=[read(p) for r in roots for p in (r/'calls').glob('*/result.json')]
    all_results += [read(p) for folder in ('calls','recovery-calls') for p in (root/folder).glob('*/result.json')]
    counts={s:sum(r['status']==s for r in coverage) for s in ['covered','partial','missing','unavailable']}
    metrics={'logical_call_records':len(all_results),'completed_json_calls':sum(r['state']=='completed' for r in all_results),
        'recorded_provider_requests':sum(max([t.get('physical_request_count',0) for t in r.get('telemetry',[])]+[0]) for r in all_results),
        'calls_without_provider_telemetry':sum(not r.get('telemetry') for r in all_results),
        'inventory_sections_available':sum(r['inventory_available'] for r in records),'source_sections':9,
        'inventory_claims':sum(len(r['claims']) for r in records),'inventory_sections_valid':sum(not r['inventory_errors'] for r in records),
        'quote_matches':sum(c['quote_start']>=0 for r in records for c in r['claims']),
        'coverage_counts':counts,'coverage_requirements':len(coverage),'atomic_points':None,'classification_tree':None,
        'baseline_status':'not_evaluable_due_to_incomplete_generation','model_content_repairs':0,'human_node_guidance':False,
        'production_course_writes':0,'meaning':'服务阻断导致原子化与分类未完成；不得视为知识准确率0，也不得宣称维持基线。'}
    findings=[
      {'path':'M5.C10','type':'semantic_scope','finding':'排序未完全指定时，是相同排序键的行相对次序未定；概括成结果可能任意顺序过宽。'},
      {'path':'M1.C8','type':'granularity_risk','finding':'文件读入与单步模式两种独立功能合成case；尚未进入原子化，不能计作合格叶子。'},
      {'path':'M3.C13','type':'coverage','finding':'仅保留point类型用于地理位置案例，未明确保留它是PostgreSQL特有类型的边界。'},
      {'path':'M6.C4 / M7.C4,C13','type':'scope_review_needed','finding':'连接等价性需保留此前内连接情境；WHERE聚合限制需与独立子查询例外一起解释，不能泛化成任何嵌套层都禁止。'},
      {'path':'M7.C7','type':'schema','finding':'kind返回reason，不在冻结枚举中，原流程守卫拒绝该节继续。'},
      {'path':'M8.C2-C4','type':'citation','finding':'3处quote改写了空白/拼接片段，没有与冻结输入的连续原文精确匹配；未手工修正。'},
      {'path':'M7.C14-C19','type':'positive','finding':'保留了HAVING允许无聚合的例外，以及FILTER仅影响所附聚合的边界。'}]
    result={'metrics':metrics,'source':read(root/'source-provenance.json'),'sections':records,'coverage':coverage,'findings':findings}
    save(root/'assessment.json',result);save(destination/'留出测试部分结果.json',result)
    save(destination/'冻结规则与未发送给模型的评测清单.json',{'eval':read(root/'eval.json'),'requirements':requirements,'recovery':read(root/'recovery-plan.json')})
    lines=['# SQL新材料留出测试：知识清单部分结果','','未生成原子知识与分类树；以下为模型原始清单概括，不是通过验收的知识树。','']
    for r in records:
        lines+=['## '+r['title'],'','来源：'+r['url'],'', '状态：'+('取得清单；待后续阶段' if r['inventory_available'] else '请求失败，未取得清单'),'']
        lines+=['- **'+c['key']+' ['+c['kind']+']** '+c['claim'] for c in r['claims']]
        lines+=['']
    (destination/'已取得的知识清单.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(metrics)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('destination',type=Path);a=p.parse_args();export(a.root,a.destination)
