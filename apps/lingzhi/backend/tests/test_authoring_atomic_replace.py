import json
import os

import pytest
from backend.tests.test_knowledge_first import svc


def busy():
    error=PermissionError('Windows sharing violation');error.winerror=32
    return error


def test_transient_windows_reader_does_not_lose_authoring_save(svc,monkeypatch):
    original=os.replace;calls=[]
    def replace(source,target):
        calls.append(1)
        if len(calls)<3:raise busy()
        return original(source,target)
    monkeypatch.setattr(os,'replace',replace)
    state=svc.authoring.load('c-pilot');state['probe']='saved'
    svc.authoring._save(state)
    assert len(calls)==3 and svc.authoring.load('c-pilot')['probe']=='saved'


def test_permanent_access_failure_keeps_original_file_and_stops(svc,monkeypatch):
    state=svc.authoring.load('c-pilot');svc.authoring._save(state);path=svc.authoring._path('c-pilot');before=path.read_bytes();calls=[]
    def replace(*_):calls.append(1);raise PermissionError('No write access')
    monkeypatch.setattr(os,'replace',replace)
    state['probe']='must not appear'
    with pytest.raises(PermissionError):svc.authoring._save(state)
    assert len(calls)==1 and path.read_bytes()==before and 'probe' not in json.loads(path.read_text(encoding='utf-8'))
