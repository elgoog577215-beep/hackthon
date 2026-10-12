"""Independent evaluation of the rendered trial, not a production save gate."""
from pathlib import Path
import argparse
import re
from .pipeline import read,save,digest,code_hash
from .compiler import probe_environment,run_checks
from .handout_trial import resolved_assets


def check(root,destination,gcc,reuse_execution=False):
    baseline=read(root/'knowledge.snapshot.json');primary={c['point_id']:c for c in baseline['checks']}
    environment=read(root/'verification-environment.json') if reuse_execution else probe_environment(gcc,root/'verification-environment.json')
    result={}
    filenames={'types':'01-数值类型转换','if':'02-if配对与语句范围','for':'03-for控制流'}
    revision=read(root/'revision-manifest.json') if (root/'revision-manifest.json').exists() else None
    for topic,filename in filenames.items():
        bundle=read(root/topic/'bundle.json')
        doc=read(root/revision['document_paths'][topic]) if revision else read(root/'calls'/(topic+'-handout')/'parsed.json')
        if revision:assert digest(doc)==revision['revised_document_hashes'][topic]
        rendered=(destination/(filename+'.md')).read_text(encoding='utf-8')
        assets=resolved_assets(bundle,doc);programs=[]
        for e in assets['examples']:
            programs.append({'id':e['key'],'key':e['key'],'knowledge_ids':e['knowledge_keys'],'kind':'runtime',
                'code':e['code'],'sample_return_type':'void','platform_assumptions':[],'predicted_stdout':e['answer_stdout'],
                'frozen_code_hash':e['answer_ref']['code_hash']})
        if assets['diagnostic']:
            for e in assets['diagnostic']['examples']:
                key=assets['diagnostic']['key']+'-'+e['role']
                programs.append({'id':key,'key':key,'knowledge_ids':assets['diagnostic']['knowledge_keys'],'kind':'runtime',
                    'code':e['code'],'sample_return_type':'void','platform_assumptions':[],'predicted_stdout':e['answer_stdout'],
                    'frozen_code_hash':e['answer_ref']['code_hash']})
        for p in programs:
            assert code_hash(p)==p['frozen_code_hash'],p['key']
            assert '```c\n'+p['code']+'\n```' in rendered,p['key']
        if reuse_execution:
            cached={r['check_id']:r for r in read(root/topic/'rendered-code-verification/results.json')}
            results=[]
            for p in programs:
                r=cached[p['id']]
                assert r['code_hash']==code_hash(p) and r['environment_hash']==digest(environment)
                assert r['stdout']==p['predicted_stdout'] and r['returncode']==0 and r['optimization_agrees']
                results.append(r)
        else:
            results=run_checks({'checks':programs},gcc,root/topic/'rendered-code-verification',[code_hash(p) for p in programs],environment)
        assert all(r['status']=='executed' and r['model_prediction_matches'] for r in results)
        labels={p['key']:p['knowledge_id'] for p in bundle['points']}
        for q in assets['exercises']:
            original=primary[labels[q['knowledge_keys'][0]]]
            assert all(q[k]==original[k] for k in ['question','answer','rationale','conditions'])
            assert q['question'] in rendered and q['answer'] in rendered and q['rationale'] in rendered
        prose=[doc.get('introduction','')]
        headings=[]
        for section in doc.get('sections',[]):
            prose += [p for p in section.get('paragraphs',[]) if isinstance(p,str)]
            prose += [b['text'] for b in section.get('blocks',[]) if isinstance(b,dict) and isinstance(b.get('text'),str)]
            headings += [section.get('title',section.get('heading',''))]+[b.get('heading','') for b in section.get('blocks',[]) if isinstance(b,dict)]
        assert all(p in rendered for p in prose)
        raw='\n'.join(prose+headings)
        terms=[]
        for term in bundle['terminology']:
            forms=[term['canonical']]+term['aliases']
            terms.append({'key':term['key'],'canonical':term['canonical'],'seen_forms':[x for x in forms if x in raw]})
        record={'topic':topic,'verified_rendered_programs':len(programs),'o0_o2_runs':2*len(programs),
            'frozen_examples':len(assets['examples']),'inserted_diagnostic':assets['diagnostic'] is not None,
            'frozen_exercises':len(assets['exercises']),'rendered_exposition_preserved':True,
            'exposition_origin':'codex_editorial_revision' if revision else 'qwen_first_output',
            'execution_reused':reuse_execution,
            'prose_chinese_characters':len(re.findall(r'[\u3400-\u9fff]', '\n'.join(prose))),
            'terminology_matches':terms,'code_results':results,
            'knowledge_revision':bundle['knowledge_revision'],'terminology_revision':bundle['terminology_revision'],
            'generated_exposition_hash':digest(prose)}
        result[topic]=record
        if not revision:
            record['model_prose_preserved']=True
            record['model_prose_chinese_characters']=record['prose_chinese_characters']
        print(topic,len(programs),'programs',len(assets['exercises']),'fixed exercises; prose',record['prose_chinese_characters'],flush=True)
    save(root/'asset-verification.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('destination',type=Path);parser.add_argument('--gcc',required=True)
    parser.add_argument('--reuse-execution',action='store_true',help='Reuse exact code/environment receipts for text-only edits; mismatches fail.')
    args=parser.parse_args();check(args.root,args.destination,args.gcc,args.reuse_execution)
