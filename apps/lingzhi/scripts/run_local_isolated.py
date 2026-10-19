"""Prepare immutable local releases; serve UI and API together on port 5173."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import hashlib
import io
import json
import os
import socket
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from dotenv import dotenv_values
import requests

APP=Path(__file__).resolve().parents[1]
BASELINE='c5575670'
FLAGS=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'DETACHED_PROCESS',0)|getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0)

def git(*args):
    return subprocess.check_output(['git','-C',str(APP),*args])

def assert_isolated(data,formal):
    data=data.resolve();formal=formal.resolve()
    if data==formal or data in formal.parents or formal in data.parents:
        raise RuntimeError('The isolated launcher cannot use the formal data directory')
    if not data.is_dir():raise RuntimeError('Isolated data directory is missing')
    for path in (data/'teacher_lesson_authoring').glob('*.json'):
        state=json.loads(path.read_text(encoding='utf8'))
        if any(j.get('status') in {'pending','running'} for j in state.get('jobs',{}).values()):
            raise RuntimeError('A generation task is active; do not replace its runtime')

def environment(config):
    values={k:v for k,v in dotenv_values(config['env_file']).items() if v is not None}
    env={**os.environ,**values}
    for key in list(env):
        if key.startswith('MODELSCOPE_'):env.pop(key)
    endpoint=values.get('ZJU_QWEN_BASE_URL') or values.get('AI_API_BASE')
    if not endpoint or '18739' in endpoint:raise RuntimeError('Normal school model route is required')
    for key in ('AI_API_BASE','ZJU_QWEN_BASE_URL','AI_PPT_API_BASE'):env[key]=endpoint
    env.update(AI_LOCAL_PROVIDER='http',LINGZHI_DATA_DIR=config['data'],LINGZHI_RELEASE_SHA=config['release_sha'],
        LINGZHI_RUNTIME_ID=config['runtime_id'],LINGZHI_RUNTIME_MODE='isolated',LINGZHI_FRONTEND_DIST=config['bundle'],
        LINGZHI_EXCHANGE_ROLE='',LINGZHI_EXCHANGE_PEER_URL='',LINGZHI_EXCHANGE_TOKEN='',
        PYTHONPATH=config['source_app'],PYTHONIOENCODING='utf-8',VITE_API_BASE_URL='',VITE_BASE_PATH='/',
        VITE_RUNTIME_ID=config['runtime_id'],VITE_RUNTIME_DATA_ID=config['data_id'],VITE_QIZHI_AUTH_REQUIRED='false')
    courses=list((Path(config['data'])/'courses').glob('*.json'))
    owners={json.loads(p.read_text(encoding='utf8')).get('owner_id') for p in courses}
    if len(owners)==1 and next(iter(owners)):env['VITE_TEACHER_USER_ID']=next(iter(owners))
    return env

def prepare(args):
    if subprocess.run(['git','-C',str(APP),'diff','--quiet','HEAD']).returncode:
        raise RuntimeError('Commit tracked source changes before preparing a release')
    repo=Path(git('rev-parse','--path-format=absolute','--git-common-dir').decode().strip()).parent
    data=Path(args.data_dir).resolve();formal=repo/'apps/lingzhi/backend/data';assert_isolated(data,formal)
    for name in ('knowledge_atomic.py','knowledge_extract.py','knowledge_hierarchy.py','knowledge_compact.py'):
        if (APP/'backend'/name).read_text(encoding='utf8')!=git('show',f'{BASELINE}:apps/lingzhi/backend/{name}').decode('utf8'):
            raise RuntimeError('The continuous generation baseline changed: '+name)
    if (APP/'backend/knowledge_content_review.py').exists():raise RuntimeError('Rewrite review must not be present')
    sha=git('rev-parse','HEAD').decode().strip();identity=uuid.uuid4().hex
    run=Path(args.state_dir).resolve()/'releases'/identity;run.mkdir(parents=True)
    source=run/'source';source.mkdir()
    with zipfile.ZipFile(io.BytesIO(git('archive','--format=zip',sha))) as archive:
        for item in archive.infolist():
            if not (source/item.filename).resolve().is_relative_to(source.resolve()):raise RuntimeError('Invalid archive member')
        archive.extractall(source)
    config={'run_dir':str(run),'runtime_id':identity,'release_sha':sha,'data':str(data),'formal_data':str(formal.resolve()),
        'data_id':hashlib.sha256(os.path.normcase(os.path.abspath(data)).encode()).hexdigest()[:16],
        'source_app':str(source/'apps/lingzhi'),'bundle':str(run/'frontend'),'env_file':str(Path(args.env_file).resolve())}
    env=environment(config)
    with (run/'build.log').open('wb') as log:
        subprocess.run([args.node,str(APP/'frontend/node_modules/vite/bin/vite.js'),'build','--outDir',config['bundle']],
            cwd=APP/'frontend',env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    manifest={k:config[k] for k in ('runtime_id','release_sha','data_id')}
    manifest.update(mode='isolated',knowledge_contract='knowledge_extract_v1')
    (Path(config['bundle'])/'runtime.json').write_text(json.dumps(manifest),encoding='utf8')
    (run/'run.json').write_text(json.dumps(config,indent=2),encoding='utf8')
    (Path(args.state_dir)/'prepared.json').write_text(json.dumps(config,indent=2),encoding='utf8')
    print(json.dumps({'prepared':str(run),'commit':sha,'runtime_id':identity}))

class RetiredEntry(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reject(self):
        body=json.dumps({'code':'RetiredLocalEntry','detail':'本地入口已统一，请打开 http://localhost:5173 并刷新页面。'},ensure_ascii=False).encode()
        self.send_response(409);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if self.path.startswith(('/api/','/ws')):self.reject();return
        self.send_response(302);self.send_header('Location','http://localhost:5173'+self.path)
        self.send_header('Cache-Control','no-store');self.end_headers()
    do_POST=do_PUT=do_PATCH=do_DELETE=reject

def aliases():
    servers=[ThreadingHTTPServer(('127.0.0.1',port),RetiredEntry) for port in (5175,8000,8001)]
    for server in servers[1:]:threading.Thread(target=server.serve_forever,daemon=True).start()
    servers[0].serve_forever()

def activate(args):
    run=Path(args.run_dir).resolve();config=json.loads((run/'run.json').read_text(encoding='utf8'))
    if Path(config['run_dir']).resolve()!=run:raise RuntimeError('Release path mismatch')
    assert_isolated(Path(config['data']),Path(config['formal_data']))
    for port in (5173,5175,8000,8001):
        with socket.socket() as probe:probe.bind(('127.0.0.1',port))
    env=environment(config)
    with (run/'backend.log').open('ab') as log:
        backend=subprocess.Popen([sys.executable,'-m','uvicorn','main:app','--host','127.0.0.1','--port','5173'],
            cwd=Path(config['source_app'])/'backend',env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=FLAGS)
    session=requests.Session();session.trust_env=False;ready=False
    for _ in range(120):
        if backend.poll() is not None:raise RuntimeError('Unified backend stopped; inspect backend.log')
        try:ready=session.get('http://127.0.0.1:5173/api/runtime',timeout=1).json().get('runtime_id')==config['runtime_id']
        except (requests.RequestException,ValueError):pass
        if ready:break
        time.sleep(.5)
    if not ready:raise RuntimeError('Unified backend did not become ready')
    with (run/'aliases.log').open('ab') as log:
        alias=subprocess.Popen([sys.executable,__file__,'aliases'],env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=FLAGS)
    receipt={**config,'frontend':'http://localhost:5173','backend':'http://127.0.0.1:5173',
        'processes':{'backend':backend.pid,'aliases':alias.pid},'mode':'isolated','knowledge_contract':'knowledge_extract_v1'}
    (run/'active.json').write_text(json.dumps(receipt,indent=2),encoding='utf8')
    (run.parents[1]/'active.json').write_text(json.dumps(receipt,indent=2),encoding='utf8')
    print(json.dumps({'ready':True,'url':receipt['frontend'],'runtime_id':config['runtime_id'],'processes':receipt['processes']}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();commands=parser.add_subparsers(dest='command',required=True)
    p=commands.add_parser('prepare');p.add_argument('--data-dir',required=True);p.add_argument('--state-dir',required=True)
    p.add_argument('--env-file',required=True);p.add_argument('--node',default='node')
    p=commands.add_parser('activate');p.add_argument('--run-dir',required=True)
    commands.add_parser('aliases');args=parser.parse_args()
    {'prepare':prepare,'activate':activate,'aliases':lambda _:aliases()}[args.command](args)
