"""Only read the affected course and print bounded exception metadata."""
import sys
import traceback
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
