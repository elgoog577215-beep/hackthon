"""Automatic source-section batching for a held-out chapter; no edit plans."""
import argparse
import asyncio
from copy import deepcopy
import json
import logging
import os
from pathlib import Path
import sys
import time
from .pipeline import read,save,digest
from .cross_course_round import parse
from .foundation_round import validate_inventory,validate_atoms,assemble


def prefix_records(inventory,atoms,prefix):
    inv=deepcopy(inventory);doc=deepcopy(atoms)
    for c in inv['claims']:c['key']=prefix+'_'+c['key']
    for p in doc['points']:
        p['key']=prefix+'_'+p['key'];p['claim_refs']=[prefix+'_'+k for k in p['claim_refs']]
    for d in doc['dispositions']:
        d['claim_key']=prefix+'_'+d['claim_key'];d['point_keys']=[prefix+'_'+k for k in d['point_keys']]
    return inv,doc


def prepare(root,source):
    if (root/'manifest.json').exists():raise ValueError('already_frozen')
    for n in ('fixtures.json','prompts.json','requirements.json','source-provenance.json'):save(root/n,read(source/n))
    save(root/'eval.json',{'max_calls':19,'concurrency':2,'json_mode':False,'max_tokens':8000,
        'source':str(source),'material_unchanged':True,'prompts_unchanged':True,
        'batching':'按官方原小节边界机械分批，每节清单→原子化，再一次全章分类；无逐点计划、修正或重试',
        'gate':'77项未发送给模型的固定要求逐项复核；所有缺失/失败部分计入分母',
        'no_production_writes':True,'no_model_code_execution':True,
        'preceding_transport_failures':'三个完整正文请求失败，单独保留；分批及JSON模式恢复是执行适配，不计作语义纠错'})
    names=('fixtures.json','prompts.json','requirements.json','source-provenance.json','eval.json')
    save(root/'manifest.json',{'input_hashes':{n:digest(read(root/n)) for n in names}})


async def run(root,recovery=False):
    assert all(digest(read(root/n))==h for n,h in read(root/'manifest.json')['input_hashes'].items())
    os.environ['LINGZHI_DATA_DIR']=str(root/'isolated-data');os.environ['LINGZHI_GENERATION_TELEMETRY']='false'
    logging.disable(logging.CRITICAL);sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
    from ai_base import AIBase
    provider=AIBase();prompts=read(root/'prompts.json');course=read(root/'fixtures.json')[0];sem=asyncio.Semaphore(1 if recovery else 2)
    if recovery:
        receipt=read(root/'recovery-plan.json')
        assert receipt['max_additional_calls']==12 and receipt['diagnostic_continuation'] is True
    async def call(key,stage,payload):
        async with sem:
            folder=root/('recovery-calls' if recovery else 'calls')/key;folder.mkdir(parents=True,exist_ok=True)
            if (folder/'result.json').exists():raise ValueError('duplicate_call')
            call_root=root/('recovery-calls' if recovery else 'calls')
            if len(list(call_root.glob('*/result.json'))) >= (12 if recovery else 19):raise ValueError('budget')
            save(folder/'input.json',payload);(folder/'prompt.txt').write_text(prompts[stage],encoding='utf-8')
            save(folder/'result.json',{'state':'started','model':provider.model_smart,'input_hash':digest(payload)})
            parts=[];telemetry=[];start=time.monotonic();print('started',key,flush=True)
            task=asyncio.create_task(provider._call_llm(prompts[stage]+'\n输入：'+json.dumps(payload,ensure_ascii=False),system_prompt=prompts['system'],
              retry_count=1,max_attempts=1,enable_thinking=False,max_tokens=8000,request_timeout_seconds=300,wait_for_capacity=recovery,
              reject_truncated=True,require_stop=True,raise_on_failure=True,on_content_delta=parts.append,telemetry_sink=telemetry.append))
            try:
                while not task.done():
                    await asyncio.wait({task},timeout=20);(folder/'partial.txt').write_text(''.join(parts),encoding='utf-8');print('progress',key,len(''.join(parts)),flush=True)
                raw=await task;(folder/'raw.txt').write_text(raw,encoding='utf-8');doc=parse(raw);save(folder/'parsed.json',doc)
                save(folder/'result.json',{'state':'completed','model':provider.model_smart,'seconds':round(time.monotonic()-start,2),'telemetry':telemetry})
                print('completed',key,flush=True);return doc
            except Exception as e:
                save(folder/'result.json',{'state':'failed','error_type':type(e).__name__,'seconds':round(time.monotonic()-start,2),'telemetry':telemetry})
                print('failed',key,type(e).__name__,flush=True);return None
    async def section(material):
        c={**course,'materials':[material]};c.pop('coverage',None);m=material['id']
        prior=root/'calls'/(m+'-inventory')/'parsed.json'
        inv=read(prior) if recovery and prior.exists() else await call(m+'-inventory','inventory',{'course':c})
        errors=validate_inventory(c,inv) if inv else ['call_failed']
        row={'section':m,'inventory_errors':errors,'atom_errors':['not_started']}
        if not inv or (errors and not recovery):return row,None,None
        atoms=await call(m+'-atoms','atoms',{'course':c,'inventory':inv})
        row['atom_errors']=validate_atoms(inv,atoms) if atoms else ['call_failed']
        if row['atom_errors']:return row,inv,atoms
        inv,atoms=prefix_records(inv,atoms,m)
        return row,inv,atoms
    try:
        if recovery:
            results=[]
            for m in course['materials']:results.append(await section(m))
        else:results=await asyncio.gather(*(section(m) for m in course['materials']))
        save(root/('recovery-sections.json' if recovery else 'sections.json'),[r[0] for r in results])
        inv={'status':'candidate','claims':[],'gaps':[]};atoms={'points':[],'dispositions':[],'gaps':[]}
        for row,i,a in results:
            if row['atom_errors'] or (row['inventory_errors'] and not recovery):
                inv['gaps'].append(row);atoms['gaps'].append(row);continue
            if row['inventory_errors']:inv['gaps'].append(row);atoms['gaps'].append(row)
            inv['claims']+=i['claims'];atoms['points']+=a['points'];atoms['dispositions']+=a['dispositions']
            inv['gaps']+=i.get('gaps',[]);atoms['gaps']+=a.get('gaps',[])
        output=root/'diagnostic' if recovery else root
        save(output/'inventory.json',inv);save(output/'atoms.json',atoms)
        if not atoms['points']:save(output/'assembly.json',{'passed':False,'error':'no_atoms'});return
        classification=await call('chapter-classify','classify',{'title':course['title'],'scope':course['profile'],
            'points':[{k:p[k] for k in ('key','name','statement','conditions')} for p in atoms['points']]})
        try:
            tree=assemble(course,inv,atoms,classification)
            scope={'course_profile':course['profile'],'course_scope_quote':course['profile']}
            for p in tree['points']:
                p['inherited_scope']=deepcopy(scope)
                local_scopes=[a['claim']['quote'] for a in p['attachments'] if a['role'] in {'scope','condition'}]
                p['effective_conditions']=list(dict.fromkeys([course['profile'],*local_scopes,*p['conditions']]))
                p['scope_revision']=digest(scope);p.pop('revision_id',None);p['revision_id']=digest(p)
            tree['scope_revision']=digest(scope);tree.pop('revision_id',None);tree['revision_id']=digest(tree)
            save(output/'tree.json',tree);save(output/'assembly.json',{'passed':True,'points':len(tree['points']),'gaps':tree['gaps'],'diagnostic_only':recovery})
        except (TypeError,ValueError,KeyError) as e:save(output/'assembly.json',{'passed':False,'error':str(e)})
    finally:
        if provider.client:await provider.client.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run']);p.add_argument('root',type=Path);p.add_argument('--source',type=Path);p.add_argument('--recovery',action='store_true')
    a=p.parse_args();prepare(a.root,a.source) if a.action=='prepare' else asyncio.run(run(a.root,a.recovery))
