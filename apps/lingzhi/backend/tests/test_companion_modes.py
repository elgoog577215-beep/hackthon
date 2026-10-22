import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock
from types import SimpleNamespace
import pytest
from ai_teacher_state import AITeacherRepository, InteractionConflict
from companion_learning import CompanionService

def test_same_user_mode_blocks_proactive_trigger_before_runtime_analysis(tmp_path,monkeypatch):
    import ai_teacher_actions as actions
    repo=AITeacherRepository(tmp_path/'chats')
    CompanionService(repo).set_preferences('u','on_request',1,'request-pref')
    def forbidden(*a,**kw):raise AssertionError('quiet mode must not build proactive runtime')
    monkeypatch.setattr(actions,'build_learning_runtime',forbidden)
    assert actions.build_trigger_candidate({'course_id':'c'},user_id='u',node_id=None,repository=repo,moment='section_completed') is None

@pytest.mark.asyncio
async def test_only_on_request_skips_automatic_note_model_calls(tmp_path,monkeypatch):
    from routers import learning_records as routes
    from ai_service import ai_service
    import ai_teacher_state
    repo=AITeacherRepository(tmp_path/'chats');CompanionService(repo).set_preferences('u','on_request',1,'request-pref')
    monkeypatch.setattr(ai_teacher_state,'ai_teacher_repository',repo)
    monkeypatch.setattr(routes,'get_course_or_404',AsyncMock(return_value={'course_id':'c'}))
    call=AsyncMock(side_effect=AssertionError('No automatic model request'))
    monkeypatch.setattr(ai_service,'_call_llm',call)
    result=await routes.companion_review('c','note',routes.CompanionReviewRequest(expected_revision=1,course_version_id='cv'),SimpleNamespace(headers={'X-User-Id':'u'}))
    assert result=={'status':'on_request','finding':None}
    call.assert_not_called()

def test_two_repository_instances_cannot_accept_the_same_expected_revision(tmp_path,monkeypatch):
    first=AITeacherRepository(tmp_path/'chats');second=AITeacherRepository(tmp_path/'chats')
    original=AITeacherRepository._write_atomic
    def slow(self,*args):time.sleep(.06);return original(self,*args)
    monkeypatch.setattr(AITeacherRepository,'_write_atomic',slow)
    def change(repo,text):
        try:
            CompanionService(repo).command('u','c',action='save_goal',expected_revision=1,request_id=text,value={'text':text},catalog=[],source_revision='cv')
            return True
        except InteractionConflict:return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(change,first,'first-request');b=pool.submit(change,second,'other-request')
        assert sum([a.result(),b.result()])==1
