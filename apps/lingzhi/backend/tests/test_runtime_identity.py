import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.mark.parametrize('header',[None,'stale-runtime'])
def test_stale_or_unidentified_page_cannot_start_a_mutation(monkeypatch,header):
    from runtime_identity import RuntimeIdentityMiddleware
    monkeypatch.setenv('LINGZHI_RUNTIME_ID','current-runtime')
    app=FastAPI();calls=[]
    @app.post('/api/generate')
    def generate():calls.append(1);return {'ok':True}
    app.add_middleware(RuntimeIdentityMiddleware)
    with TestClient(app) as client:
        result=client.post('/api/generate',headers={'X-Lingzhi-Runtime':header} if header else {})
    assert result.status_code==409 and result.json()['code']=='RuntimeMismatch'
    assert calls==[]


def test_matching_runtime_keeps_the_original_route_and_unconfigured_hosts_unchanged(monkeypatch):
    from runtime_identity import RuntimeIdentityMiddleware
    for configured in ('current-runtime',''):
        monkeypatch.setenv('LINGZHI_RUNTIME_ID',configured)
        app=FastAPI()
        @app.post('/api/generate')
        def generate():return {'ok':True}
        app.add_middleware(RuntimeIdentityMiddleware)
        with TestClient(app) as client:
            assert client.post('/api/generate',headers={'X-Lingzhi-Runtime':'current-runtime'}).status_code==200


def test_bundle_must_match_backend_and_data_identity(monkeypatch,tmp_path):
    from runtime_identity import runtime_manifest, validate_frontend_bundle
    monkeypatch.setenv('LINGZHI_RUNTIME_ID','current-runtime')
    monkeypatch.setenv('LINGZHI_RUNTIME_MODE','isolated')
    monkeypatch.setenv('LINGZHI_RELEASE_SHA','commit-a')
    monkeypatch.setenv('LINGZHI_DATA_DIR',str(tmp_path/'private-data'))
    manifest=runtime_manifest();assert manifest['knowledge_contract']=='knowledge_extract_v1'
    assert str(tmp_path) not in json.dumps(manifest)
    file=tmp_path/'runtime.json';file.write_text(json.dumps(manifest),encoding='utf8')
    validate_frontend_bundle(tmp_path)
    for key in ('runtime_id','release_sha','data_id','knowledge_contract'):
        file.write_text(json.dumps({**manifest,key:'wrong'}),encoding='utf8')
        with pytest.raises(RuntimeError,match='runtime'):validate_frontend_bundle(tmp_path)
