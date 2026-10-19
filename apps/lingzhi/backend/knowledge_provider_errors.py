"""Safe, structured provider failure categories; never persist upstream bodies."""
import re


def _chain(error):
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error)); yield error
        error = error.__cause__ or error.__context__


def provider_http_status(error):
    chain = list(_chain(error))
    for item in chain:
        status = getattr(item, 'status_code', None) or getattr(getattr(item, 'response', None), 'status_code', None)
        if isinstance(status, int) and 400 <= status <= 599: return status
    for item in chain:
        match = re.search(r'\bError code:\s*([45]\d{2})\b', str(item), re.IGNORECASE)
        if match: return int(match[1])
    return None


def provider_failure(error):
    from ai_base import AIProviderRequestError, AIProviderUnavailable, AIResponseTruncated
    if not isinstance(error, (AIProviderRequestError, AIProviderUnavailable)): return {}
    status = provider_http_status(error)
    chain = list(_chain(error))
    message = ' '.join(str(item) for item in chain).casefold()
    reason = {400:'invalid_request',401:'authentication',403:'permission_denied',404:'endpoint_unavailable',
        409:'request_rejected',422:'invalid_request',429:'rate_limited'}.get(status,
        'service_error' if status and status >= 500 else 'request_rejected' if status else 'request_failed')
    if status is None and isinstance(error, AIProviderUnavailable):
        reason = {'authentication_failed':'authentication','not_configured':'not_configured',
            'ppt_provider_configuration_incomplete':'not_configured'}.get(error.reason,'service_unavailable')
    if status == 409 and 'outside isolated unfinished shards' in message: reason = 'isolated_scope_rejected'
    elif isinstance(error, AIResponseTruncated): reason = 'truncated_output'
    elif status is None and ('empty_response' in message or 'empty stream' in message): reason = 'empty_response'
    elif status is None and any(isinstance(item, TimeoutError) or 'timeout' in type(item).__name__.casefold() for item in chain): reason = 'timeout'
    descriptions = {'invalid_request':'请求格式或参数被拒绝','authentication':'模型连接鉴权失败',
        'permission_denied':'模型服务拒绝访问','endpoint_unavailable':'模型接口或模型不存在',
        'request_rejected':'模型服务拒绝当前请求','rate_limited':'模型服务限流或额度不足',
        'service_error':'模型服务内部异常','isolated_scope_rejected':'隔离测试限制拦截了当前生成请求',
        'truncated_output':'模型输出达到容量上限，片段已保留','empty_response':'模型未返回有效内容',
        'timeout':'模型请求超时','request_failed':'模型请求失败，请检查连接配置或服务日志',
        'not_configured':'模型连接尚未配置完整','service_unavailable':'模型服务暂不可用，请检查服务状态'}
    return {'code':'ModelProviderFailure','category':'provider_request','provider_reason':reason,
        **({'provider_http_status':status} if status else {}),
        'message':f'模型请求失败{f"（HTTP {status}）" if status else ""}：{descriptions[reason]}。已保留完成内容。',
        'retryable':False,'recovery_action':'check_model_service'}
