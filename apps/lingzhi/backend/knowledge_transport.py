"""Bounded zero-output connection recovery, scoped to the current knowledge job."""
import asyncio
from contextlib import contextmanager
from contextvars import ContextVar

import httpx

REQUEST_SCOPE = ContextVar('knowledge_model_request_scope', default={})
MAX_ATTEMPTS = 3
JOB_RETRY_LIMIT = 6


@contextmanager
def model_scope(**values):
    token = REQUEST_SCOPE.set({**REQUEST_SCOPE.get(), **values})
    try: yield
    except Exception as error:
        scope = REQUEST_SCOPE.get()
        if scope.get('last_stage') and not getattr(error, 'knowledge_failure', None):
            error.knowledge_failure = {'stage': scope['last_stage'], 'batch_id': scope.get('batch_id'),
                                       'batch_index': scope.get('batch_index')}
        raise
    finally: REQUEST_SCOPE.reset(token)


def transient_connection(error):
    from ai_base import AIProviderRequestError, AIRequestBudgetExceeded, AIResponseTruncated
    network_types = (httpx.NetworkError, httpx.RemoteProtocolError, httpx.ConnectTimeout, ConnectionError)
    if isinstance(error, (AIRequestBudgetExceeded, AIResponseTruncated)): return False
    if not isinstance(error, (AIProviderRequestError, *network_types)): return False
    chain = []; seen = set(); current = error
    while current is not None and id(current) not in seen:
        seen.add(id(current)); chain.append(current)
        current = current.__cause__ or current.__context__
    # Authentication, quotas and invalid requests are not transport recovery.
    if any(getattr(e, 'status_code', None) in {400, 401, 403, 404, 422, 429} for e in chain): return False
    if any(isinstance(e, network_types) for e in chain): return True
    if not isinstance(error, AIProviderRequestError): return False
    message = str(error).strip().casefold()
    return (message in {'connection error.', 'connection error'}
            or any(term in message for term in ('connection reset', 'connection refused', 'connection aborted', 'server disconnected', 'bad gateway'))
            or any(f' {code}' in f' {message}' for code in (502, 503, 504)))


async def retry_pause(seconds):
    await asyncio.sleep(seconds)


async def recover_connection(svc, course_id, job_id, stage, operation):
    scope = REQUEST_SCOPE.get()
    budget = scope.get('retry_budget')
    if budget is None: budget = {'used': 0, 'active': {}}
    key = object(); registered = False

    def publish():
        active = budget['active']
        svc.authoring.update_job_live(course_id, job_id, transport_retry_count=budget['used'],
            transport_retry_limit=JOB_RETRY_LIMIT, transport_retry_active_count=len(active),
            transport_retry_stage=next(iter(active.values()), ''))

    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            svc._active(course_id, job_id)
            if scope.get('validate_source'): scope['validate_source']()
            try:
                with model_scope(transport_attempt=attempt):
                    return await operation()
            except Exception as error:
                details = {'stage': stage, 'batch_id': scope.get('batch_id'), 'batch_index': scope.get('batch_index'),
                    'transport_attempts': attempt, 'transport_max_attempts': MAX_ATTEMPTS}
                error.knowledge_failure = details
                retry = transient_connection(error) and not getattr(error, 'partial_response', '')
                if not retry or attempt == MAX_ATTEMPTS or budget['used'] >= JOB_RETRY_LIMIT:
                    details['retry_exhausted'] = bool(retry)
                    raise
                # No await between checking and reserving the shared retry budget.
                budget['used'] += 1; budget['active'][key] = stage; registered = True
                publish()
                svc.authoring.update_job_live(course_id, job_id, phase='model_retry_wait')
                await retry_pause((0.5, 1.5)[attempt - 1])
    finally:
        if registered:
            budget['active'].pop(key, None); publish()
