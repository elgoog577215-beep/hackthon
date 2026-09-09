"""Only read the affected course and print bounded exception metadata."""
import sys
import traceback
import os
import asyncio
import time
import json
import types
import logging
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / 'backend'))
from storage import storage
from jobs.manager import TaskManager
from dependencies import get_course_document_repository, get_teacher_lesson_authoring_repository
from question_bank import question_bank_repository
from teaching_representations import teaching_representation_repository
from course_evolution.application import CourseEvolutionApplicationService
from course_evolution.core import course_evolution_repository

manager = TaskManager(storage=storage, course_service=None, ws_service=None, runtime_mode='read_only')
service = CourseEvolutionApplicationService(
    evolution_repository=course_evolution_repository,
    document_repository=get_course_document_repository(),
    authoring_repository=get_teacher_lesson_authoring_repository(),
    representation_repository=teaching_representation_repository,
    question_bank_repository=question_bank_repository,
    course_service=None, task_manager=manager,
)
try:
    result = service.teacher_context('afb29754-6842-437b-af1b-5866bfb53b41')
    print('CONTEXT_OK', result.ready, len(result.units))
except Exception as error:
    print('CONTEXT_ERROR', type(error).__name__, str(error)[:500])
    for frame in traceback.extract_tb(error.__traceback__):
        print('FRAME', Path(frame.filename).name, frame.lineno, frame.name, frame.line)

from course_generation.service import get_course_service
from course_evolution.teacher_planning import rank_change_units
model = get_course_service()
model.analyze_teacher_course_change = types.MethodType(analyze_teacher_course_change, model)
logging.getLogger('ai_base').setLevel(logging.ERROR)
print('TIMEOUT_CONFIG', os.environ.get('AI_REQUEST_TIMEOUT_SECONDS', 'default'), model.client.timeout.read, flush=True)
print('MODEL_CONFIG', model.fast_models, flush=True)
ctx = service.teacher_context('afb29754-6842-437b-af1b-5866bfb53b41')
overview = {'course_id': ctx.course_id, 'course_title': ctx.course_title,
            'source_mode': ctx.source_mode, 'assets': [a.model_dump(mode='json') for a in ctx.assets],
            'outline': [{k: v for k, v in n.items() if k != 'section_snapshot'} for n in ctx.outline],
            'indexed_unit_count': 116}
ranked = {u['unit_id']: u for u in rank_change_units(ctx, '给每个章节加一个实践项目', limit=len(ctx.units), include_all=True)}
async def probe():
    from course_evolution.semantic_scan import validate_batch
    state = course_evolution_repository.load('learner_a44b54f7-1d80-442f-9b23-0e84371b2592', ctx.course_id)
    plan = next(p for p in state.change_sets if p.change_set_id == 'course-change-2395399f197543bc828e6a7ee1241c29')
    targets = ['course_content:tsb-82c81e8ea1c4', 'script:L1-6:tsb-82c81e8ea1c4', 'question_bank:qbi_5975a9f5125e0c53']
    semaphore = asyncio.Semaphore(2)
    async def check_unit(uid):
        u = next(u for u in ctx.units if u.unit_id == uid)
        body = '\n\n'.join(u.full_text_fields.values()) or u.text
        started = time.monotonic()
        size = 600 if len(body) > 6000 and '```' in body else 1200
        chunks = [body[i:i+size] for i in range(0, max(1, len(body)), size-100)]
        batches = [[{**ranked[uid], 'content': content, 'part': i+1, 'parts': len(chunks)}] for i, content in enumerate(chunks)]
        async def analyze(overview, items, instruction):
            async with semaphore:
                return await asyncio.wait_for(model.analyze_teacher_course_change(overview, items, instruction), 120)
        _, done, missing, failures, retries = await candidate_scan_batches(overview=overview, batches=batches,
            instruction=plan.request_text, revisions={}, analyzer=analyze)
        print('UNIT_RECOVERY', uid, len(chunks), round(time.monotonic()-started, 2),
              json.dumps({'done':sorted(done), 'missing':sorted(missing), 'errors':[e.get('message') for e in failures], 'retries':retries}), flush=True)
        return not missing
    results = await asyncio.gather(*(check_unit(uid) for uid in targets))
    print('FINAL_REPLAY', json.dumps({'units':len(targets), 'passed':sum(results), 'failed':len(results)-sum(results), 'course_writes':0}), flush=True)
asyncio.run(probe())
