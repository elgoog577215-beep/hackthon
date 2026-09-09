"""Only read the affected course and print bounded exception metadata."""
import sys
import traceback
import os
import asyncio
import time
import json
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
print('TIMEOUT_CONFIG', os.environ.get('AI_REQUEST_TIMEOUT_SECONDS', 'default'), model.client.timeout.read, flush=True)
print('MODEL_CONFIG', model.fast_models, flush=True)
ctx = service.teacher_context('afb29754-6842-437b-af1b-5866bfb53b41')
overview = {'course_id': ctx.course_id, 'course_title': ctx.course_title,
            'source_mode': ctx.source_mode, 'assets': [a.model_dump(mode='json') for a in ctx.assets],
            'outline': [{k: v for k, v in n.items() if k != 'section_snapshot'} for n in ctx.outline],
            'indexed_unit_count': 116}
ranked = {u['unit_id']: u for u in rank_change_units(ctx, '给每个章节加一个实践项目', limit=len(ctx.units), include_all=True)}
async def probe():
    for uid in ['outline:L2-1-1', 'course_content:tsb-82c81e8ea1c4']:
        u = next(u for u in ctx.units if u.unit_id == uid)
        body = '\n\n'.join(u.full_text_fields.values()) or u.text
        chunk = {**ranked[uid], 'content': body[:4000], 'part': 1, 'parts': max(1, (len(body)+3799)//3800)}
        started = time.monotonic()
        try:
            output = await asyncio.wait_for(model.analyze_teacher_course_change(overview, [chunk], '给每个章节加一个实践项目'), 200)
            print('MODEL_REPLAY', uid, round(time.monotonic()-started, 2), type(output).__name__,
                  'affected_count', len((output or {}).get('affected_units') or []), flush=True)
        except Exception as error:
            print('MODEL_REPLAY_ERROR', uid, round(time.monotonic()-started, 2), type(error).__name__, str(error)[:160], flush=True)
asyncio.run(probe())
