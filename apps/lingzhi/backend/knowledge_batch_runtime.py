"""Bounded batch scheduling and shared errors without generation orchestration."""
import asyncio
from course_errors import CourseDocumentConflict
from knowledge_transport import REQUEST_SCOPE,model_scope

class KnowledgeModelIdleTimeout(TimeoutError):
    pass


class KnowledgeModelDegenerateOutput(RuntimeError):
    pass


class KnowledgeBatchValidationError(CourseDocumentConflict):
    """A local data failure; independent frozen batches can still finish once."""
    def __init__(self, batch_id, message, *, failures=None):
        self.failures = failures or [{'batch_id': batch_id, 'message': message}]
        super().__init__('；'.join(f"{e['batch_id']}：{e['message']}" for e in self.failures))


async def run_batches(rows, process, *, width, stage=None):
    """Bound requests, stop dispatch on failure, retain in-flight successes."""
    pending = iter((i, b) for i, b in enumerate(rows, 1) if b['status'] != 'completed')
    failures = []; data_failures = []
    async def worker():
        while not failures:
            entry = next(pending, None)
            if entry is None: return
            try:
                index, batch = entry
                with model_scope(batch_id=batch.get('id') or batch.get('key'), batch_index=index,
                                 last_stage=stage or REQUEST_SCOPE.get().get('last_stage')):
                    await process(index, batch)
            except KnowledgeBatchValidationError as exc:
                data_failures.extend(exc.failures)
            except Exception as exc:
                failures.append(exc)
    tasks = [asyncio.create_task(worker()) for _ in range(width)]
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done(): task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    if failures: raise failures[0]
    if data_failures:
        raise KnowledgeBatchValidationError('', '', failures=sorted(data_failures, key=lambda e: e['batch_id']))
