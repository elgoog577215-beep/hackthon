from pathlib import Path
import importlib.util
import threading

import pytest
import requests
from http.server import ThreadingHTTPServer

spec=importlib.util.spec_from_file_location('isolated_launcher',Path(__file__).resolve().parents[2]/'scripts/run_local_isolated.py')
launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)


def test_launcher_refuses_formal_or_ancestor_data_and_active_tasks(tmp_path):
    formal=tmp_path/'formal';formal.mkdir()
    for path in (formal,formal/'child',tmp_path):
        with pytest.raises(RuntimeError,match='formal'):launcher.assert_isolated(path,formal)
    isolated=tmp_path/'isolated';(isolated/'teacher_lesson_authoring').mkdir(parents=True)
    launcher.assert_isolated(isolated,formal)
    (isolated/'teacher_lesson_authoring/c.json').write_text('{"jobs":{"j":{"status":"running"}}}')
    with pytest.raises(RuntimeError,match='active'):launcher.assert_isolated(isolated,formal)


def test_retired_entry_redirects_navigation_but_never_forwards_mutations():
    server=ThreadingHTTPServer(('127.0.0.1',0),launcher.RetiredEntry)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    session=requests.Session();session.trust_env=False
    try:
        base=f'http://127.0.0.1:{server.server_port}'
        result=session.get(base+'/course/c?lesson=L1-6',allow_redirects=False,timeout=2)
        assert result.status_code==302 and result.headers['Location']=='http://localhost:5173/course/c?lesson=L1-6'
        result=session.post(base+'/api/generate',json={'request_id':'stale'},timeout=2)
        assert result.status_code==409 and result.json()['code']=='RetiredLocalEntry'
    finally:session.close();server.shutdown();server.server_close();thread.join(2)
