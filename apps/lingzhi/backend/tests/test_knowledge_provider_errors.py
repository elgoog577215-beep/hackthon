from types import SimpleNamespace

import httpx
import pytest

from ai_base import AIProviderRequestError
from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_atomic import setup_course, start


@pytest.mark.parametrize('status,reason', [(400,'invalid_request'),(401,'authentication'),(403,'permission_denied'),
    (404,'endpoint_unavailable'),(409,'request_rejected'),(422,'invalid_request'),(429,'rate_limited'),(500,'service_error')])
def test_http_failure_keeps_status_without_copying_provider_body(status, reason):
    from knowledge_provider_errors import provider_failure
    error=AIProviderRequestError('PRIVATE request prompt, Bearer SECRET')
    error.__cause__=httpx.HTTPStatusError('PRIVATE response',request=httpx.Request('POST','http://private/v1'),
        response=httpx.Response(status))
    result=provider_failure(error)
    assert result['provider_http_status']==status and result['provider_reason']==reason
    assert result['retryable'] is False and 'SECRET' not in str(result) and 'PRIVATE' not in str(result)


def test_isolated_guard_reason_is_explicit_and_exception_chain_is_cycle_safe():
    from knowledge_provider_errors import provider_failure
    error=AIProviderRequestError('<html>Error code: 409 Message: Outside isolated unfinished shards. Bearer SECRET</html>')
    error.__cause__=error
    result=provider_failure(error)
    assert result['provider_http_status']==409 and result['provider_reason']=='isolated_scope_rejected'
    assert '隔离测试限制' in result['message'] and '<html>' not in result['message'] and 'SECRET' not in str(result)


@pytest.mark.parametrize('message,reason',[('empty_response','empty_response'),('opaque PRIVATE SECRET','request_failed')])
def test_non_http_failure_gets_safe_category(message,reason):
    from knowledge_provider_errors import provider_failure
    result=provider_failure(AIProviderRequestError(message))
    assert result['provider_reason']==reason and 'provider_http_status' not in result
    assert 'PRIVATE' not in str(result) and 'SECRET' not in str(result)


def test_non_provider_failures_keep_their_domain_handler():
    from knowledge_provider_errors import provider_failure
    assert provider_failure(PermissionError('local disk'))=={}


@pytest.mark.asyncio
async def test_rejected_request_retains_actual_failure_stage_in_saved_job(svc,monkeypatch):
    setup_course(svc,monkeypatch)
    async def call(*args,**kwargs):
        raise AIProviderRequestError('<html>Error code: 409 Message: Outside isolated unfinished shards.</html>')
    svc.provider_factory=lambda:SimpleNamespace(_call_llm=call,model_smart='test-qwen',client=None)
    job=start(svc,'rejected-request',extraction_mode='single_pass_v1')
    await svc.run('c-pilot',job['id'])
    saved=svc.authoring.get_job('c-pilot',job['id'])
    assert saved['status']=='failed' and saved['progress']==0
    assert saved['error']['code']=='ModelProviderFailure'
    assert saved['error']['provider_http_status']==409
    assert saved['error']['provider_reason']=='isolated_scope_rejected'
    assert saved['error']['stage']==saved['pipeline_stage']=='extract'
    assert not saved.get('transport_retry_count')
