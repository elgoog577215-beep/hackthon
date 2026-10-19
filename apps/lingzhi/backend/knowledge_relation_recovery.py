"""Bounded transport recovery for an unfinished relation batch, never content repair."""
import asyncio

import httpx
from openai import APIConnectionError, APIStatusError

MAX_ATTEMPTS = 3
RETRY_DELAYS = (2, 4)


def transient_connection(error):
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, APIStatusError):
            return error.status_code in {408, 429, 500, 502, 503, 504}
        if isinstance(error, (TimeoutError, httpx.TransportError, APIConnectionError)):
            return True
        # AIBase retains the SDK/transport exception as its cause. Authentication,
        # quota, invalid output and local quality errors do not become retries.
        if type(error).__name__ in {'AIRequestBudgetExceeded', 'AIProviderUnavailable', 'AIResponseTruncated'}:
            return False
        error = error.__cause__
    return False


async def call_with_recovery(svc, course_id, job_id, provider, prompt, batch, save, validate):
    from knowledge_atomic import call_stage
    from knowledge_first import now
    class CapacityAwareProvider:
        async def _call_llm(self, *args, **kwargs):
            return await provider._call_llm(*args, **kwargs, wait_for_capacity=True)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        svc._active(course_id, job_id)
        validate()
        try:
            return await call_stage(svc, course_id, job_id, CapacityAwareProvider(), prompt, 'relations')
        except Exception as exc:
            svc._active(course_id, job_id)
            validate()
            if not transient_connection(exc):
                raise
            batch.setdefault('connection_failures', []).append({
                'at':now(), 'attempt':attempt, 'code':type(exc).__name__})
            if attempt == MAX_ATTEMPTS:
                save()
                raise
            delay = RETRY_DELAYS[attempt - 1]
            save(phase='relation_retry_wait', recovery_attempt=attempt,
                 message='关联连接暂时中断，正在重试当前批次；知识树已保存。')
            # Check cancellation and source changes during the bounded delay.
            for _ in range(delay):
                await asyncio.sleep(1)
                svc._active(course_id, job_id)
                validate()
