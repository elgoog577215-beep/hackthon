"""Whole-lecture generation, publication and recovery without per-module calls."""

import asyncio
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from ai_base import AIProviderRequestError, AIResponseTruncated
from backend.tests.test_teacher_lesson_authoring import standard_lesson_plan, single_section_course_data
from course_generation.service import CourseService
from course_generation_budget import CourseGenerationBudgetExceeded
from teacher_lesson_authoring import TeacherLessonAuthoringRepository, TeacherLessonAuthoringService
from teacher_script import parse_handout_stream, handout_section_contract


BLOCK = '<!-- block:{"type":"定义","title":"定义与条件","key":"b1"} -->\n'

def response(ids):
    return "\n".join(f"<!-- section:{key} -->\n{BLOCK}定义、条件与完整解法。" for key in ids) + "\n<!-- handout:end -->"


@pytest.mark.parametrize(
    "text,expected,error",
    [
        (response(["a", "b"]), ["a", "b"], ""),
        (response(["a", "b"]).replace("section:", "section: "), ["a", "b"], ""),
        (response(["b", "a"]), [], "section_order_or_identity"),
        (response(["a", "a"]), [], "section_order_or_identity"),
        (response(["a", "x"]), [], "section_order_or_identity"),
        ("<!-- section:a -->\n正文\n<!-- handout:end -->", [], "unexpected_end"),
        ("<!-- section:a -->\n正文\n<!-- section:b -->\n完整正文", ["a", "b"], ""),
        (response(["a", "b"]) + "\n```\ntrailing\n```", ["a"], "trailing_content"),
        ("<!-- section:a -->\n正文\n<!-- section:b -->\n\\[x", ["a"], "section_incomplete"),
    ],
)
def test_marker_contract(text, expected, error):
    parsed = parse_handout_stream(text, ["a", "b"], provider_complete=True)
    assert list(parsed["completed"]) == expected
    assert parsed["error"] == error


def test_code_markers_are_literal_and_end_requires_provider_success():
    text = "<!-- section:a -->\n```html\n<!-- section:fake -->\n<!-- handout:end -->\n```\n解释\n<!-- section:b -->\n正文\n<!-- handout:end -->"
    partial = parse_handout_stream(text, ["a", "b"])
    assert list(partial["completed"]) == ["a"]
    complete = parse_handout_stream(text, ["a", "b"], provider_complete=True)
    assert "<!-- section:fake -->" in complete["completed"]["a"]
    assert list(complete["completed"]) == ["a", "b"]


@pytest.mark.parametrize("fragment", ["```python\nx=1", "\\[x=1", "\\(x=1"])
def test_unclosed_code_or_math_cannot_be_checkpointed(fragment):
    parsed = parse_handout_stream(
        "<!-- section:a -->\n" + fragment + "\n<!-- section:b -->\n正文\n<!-- handout:end -->",
        ["a", "b"],
        provider_complete=True,
    )
    assert not parsed["completed"]
    assert parsed["error"]


def fixture(tmp_path):
    repo = TeacherLessonAuthoringRepository(tmp_path)
    repo.set_outline("course-1", "outline-v1")
    plan = standard_lesson_plan()
    second = deepcopy(plan["sections"][0])
    second["node_id"] = "L2-1-2"
    plan["sections"].append(second)
    lesson = repo.save_plan_revision("course-1", "L1-1", plan, source_outline_revision_id="outline-v1")
    outlines = [{"node_id": s["node_id"], "node_name": s["node_id"]} for s in plan["sections"]]
    kwargs = dict(
        course_id="course-1",
        lesson_unit_id="L1-1",
        source_plan_revision_id=lesson["working_revision_id"],
        outline_sections=outlines,
        plan_sections={s["node_id"]: s for s in plan["sections"]},
        expected_script_revision="",
    )
    return repo, TeacherLessonAuthoringService(repo), kwargs


def new_job(repo):
    return repo.create_job(
        "course-1", "L1-1", job_type="teacher_lesson_script_generation", source_outline_revision_id="outline-v1"
    )["id"]


@pytest.mark.asyncio
async def test_one_request_covers_all_sections_and_preserves_saved_revision(tmp_path):
    repo, service, kwargs = fixture(tmp_path)
    calls = []

    async def generate(**request):
        calls.append(request)
        text = response([s["node_id"] for s in request["outline_sections"]])
        for token in text:
            await request["on_content_delta"](token)
        return {"text": text}

    result = await service.run_script_job(**kwargs, job_id=new_job(repo), generator=generate)
    assert result["status"] == "completed", result.get("error")
    assert len(calls) == 1
    assert len(result["result_sections"]) == 2
    assert all(len(s["blocks"]) == 1 for s in result["result_sections"])
    assert "<!-- section:" not in "\n".join(result.get("streamed_block_content", {}).values())
    assert len(repo.lesson("course-1", "L1-1")["script_revisions"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["disconnect", "length", "open_code", "bad_id"])
async def test_failure_keeps_sections_without_publishing_then_one_explicit_resume(tmp_path, failure):
    repo, service, kwargs = fixture(tmp_path)
    calls = []

    async def broken(**request):
        calls.append(request)
        text = "<!-- section:L2-1-1 -->\n" + BLOCK + "完整正文\n<!-- section:L2-1-2 -->\n" + BLOCK + "未完成片段"
        await request["on_content_delta"](text)
        if failure == "disconnect":
            raise AIProviderRequestError("offline")
        if failure == "length":
            raise AIResponseTruncated("length")
        return {"text": text + ("\n<!-- section:unknown -->" if failure == "bad_id" else "\n```python\nx =")}

    failed = await service.run_script_job(**kwargs, job_id=new_job(repo), generator=broken)
    assert failed["status"] == "failed"
    assert len(calls) == 1
    assert [s["section_node_id"] for s in failed["result_sections"]] == ["L2-1-1"]
    assert "未完成片段" in failed["raw_response"]
    assert not repo.lesson("course-1", "L1-1")["working_script_revision_id"]
    # Simulate a fresh process using the durable checkpoint.
    repo2 = TeacherLessonAuthoringRepository(tmp_path)

    async def resumed(**request):
        calls.append(request)
        assert [s["node_id"] for s in request["outline_sections"]] == ["L2-1-2"]
        assert request["completed_sections"][0]["blocks"][0]["content"] == "完整正文"
        return {"text": response(["L2-1-2"])}

    result = await TeacherLessonAuthoringService(repo2).run_script_job(
        **kwargs,
        job_id=repo2.resume_lesson_generation("course-1", failed["id"], input_fingerprint="")[0]["id"],
        generator=resumed,
        seed_sections=failed["result_sections"],
        partial_text=failed["raw_response"],
    )
    assert result["status"] == "completed", result.get("error")
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_save_failure_resume_uses_zero_model_calls(tmp_path, monkeypatch):
    repo, service, kwargs = fixture(tmp_path)
    calls = []

    async def generate(**request):
        calls.append(1)
        return {"text": response(["L2-1-1", "L2-1-2"])}

    save = repo.save_script_revision
    monkeypatch.setattr(
        repo, "save_script_revision", lambda *a, **k: (_ for _ in ()).throw(OSError("disk unavailable"))
    )
    failed = await service.run_script_job(**kwargs, job_id=new_job(repo), generator=generate)
    assert failed["status"] == "failed" and len(failed["result_sections"]) == 2
    monkeypatch.setattr(repo, "save_script_revision", save)
    result = await service.run_script_job(
        **kwargs,
        job_id=repo.resume_lesson_generation("course-1", failed["id"], input_fingerprint="")[0]["id"],
        generator=generate,
        seed_sections=failed["result_sections"],
    )
    assert result["status"] == "completed", result.get("error")
    assert calls == [1]


@pytest.mark.asyncio
async def test_late_response_cannot_overwrite_cancelled_job(tmp_path):
    repo, service, kwargs = fixture(tmp_path)
    jid = new_job(repo)

    async def generate(**request):
        repo.cancel_job("course-1", jid)
        return {"text": response(["L2-1-1", "L2-1-2"])}

    with pytest.raises(asyncio.CancelledError):
        await service.run_script_job(**kwargs, job_id=jid, generator=generate)
    assert not repo.lesson("course-1", "L1-1")["working_script_revision_id"]


@pytest.mark.asyncio
async def test_source_revision_conflict_prevents_publication(tmp_path):
    repo, service, kwargs = fixture(tmp_path)

    async def generate(**request):
        repo.set_outline("course-1", "changed")
        return {"text": response(["L2-1-1", "L2-1-2"])}

    result = await service.run_script_job(**kwargs, job_id=new_job(repo), generator=generate)
    assert result["status"] == "failed"
    assert not repo.lesson("course-1", "L1-1")["working_script_revision_id"]


@pytest.mark.asyncio
async def test_handout_request_has_complete_context_and_one_provider_attempt(monkeypatch):
    service = CourseService()
    calls = []

    async def model(prompt, system, **kw):
        calls.append((prompt, system, kw))
        return response(["a", "b"])

    monkeypatch.setattr(service, "_call_llm", model)
    result = await service.generate_teacher_handout(
        course_id="c",
        outline_sections=[{"node_id": "a"}, {"node_id": "b"}],
        plan_sections={"a": {"knowledge": "定义边界"}},
        lesson_context={"source": "指定资料"},
        requirements="保留推导",
    )
    assert result["text"] == response(["a", "b"]) and len(calls) == 1
    prompt, system, kw = calls[0]
    assert all(x in prompt for x in ["定义边界", "指定资料", "保留推导"])
    assert kw["max_attempts"] == kw["retry_count"] == 1 and kw["require_stop"]
    assert not kw["json_mode"]
    assert "口播稿" in system and "参考解法" in system


@pytest.mark.asyncio
async def test_handout_receives_saved_personalization_without_old_prose(monkeypatch):
    import json
    service = CourseService()
    data = {
        'course_name': '数据结构', 'target_audience': '转专业学生',
        'course_intent': {'goal': '独立完成项目'},
        'learner_starting_profile': {'known': ['数组'], 'needs_support': ['递归']},
        'course_generation_brief': {'subject_type_contract': {'methods': ['复杂度分析']},
                                    'old_prose': '不能传入的旧正文'},
    }
    service.register_course_generation_metadata('c', deepcopy(data))
    seen = []
    async def model(prompt, system, **kw):
        seen.append(json.JSONDecoder().raw_decode(prompt.split('\n', 1)[1])[0])
        return response(['a'])
    monkeypatch.setattr(service, '_call_llm', model)
    await service.generate_teacher_handout(course_id='c', outline_sections=[{'node_id': 'a'}],
        plan_sections={}, lesson_context={})
    context = seen[0]['course_context']
    assert context['course_intent'] == data['course_intent']
    assert context['learner_starting_profile'] == data['learner_starting_profile']
    assert context['subject_type_contract']['methods'] == ['复杂度分析']
    assert 'old_prose' not in str(seen)
    frozen = {'target_audience': '冻结的授课对象'}
    await service.generate_teacher_handout(course_id='c', outline_sections=[{'node_id': 'a'}],
        plan_sections={}, lesson_context={}, course_context=frozen)
    assert seen[1]['course_context'] == frozen


def test_current_personalization_overrides_or_clears_historical_brief():
    from course_generation.prompts import handout_course_context
    context = handout_course_context({
        'target_audience': '当前对象', 'learner_starting_profile': {},
        'course_generation_brief': {'target_audience': '旧对象',
                                    'learner_starting_profile': {'known': ['旧基础']}},
    })
    assert context['target_audience'] == '当前对象'
    assert 'learner_starting_profile' not in context


@pytest.mark.asyncio
async def test_pause_persists_visible_raw_text_between_disk_checkpoints(tmp_path, monkeypatch):
    import teacher_lesson_authoring as authoring
    repo, service, kwargs = fixture(tmp_path)
    jid = new_job(repo)
    tick = [100.0]
    monkeypatch.setattr(authoring.time, 'monotonic', lambda: tick[0])
    prefix = '<!-- section:L2-1-1 -->\n' + BLOCK + '已显示正文'
    async def generate(**request):
        await request['on_content_delta'](prefix)
        tick[0] += .5  # Next visible delta, before the two-second disk checkpoint.
        await request['on_content_delta']('最后收到的内容')
        repo.pause_job('course-1', jid)
        raise asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await service.run_script_job(**kwargs, job_id=jid, generator=generate)
    reloaded = TeacherLessonAuthoringRepository(repo.root).get_job('course-1', jid)
    assert reloaded['status'] == 'paused'
    assert reloaded['raw_response'] == prefix + '最后收到的内容'


@pytest.mark.asyncio
async def test_continuation_keeps_complete_prose_once_and_only_requests_missing_sections(monkeypatch):
    service = CourseService()
    prose = '已完成的教材正文与完整推导。' * 200
    source = '来源中的独有边界条件必须保留。' * 100
    completed = [{'section_node_id': 'a', 'title': '已完成', 'content': prose,
                  'blocks': [{'content': prose, 'source_plan_context': {'duplicate': prose}}]}]
    before = deepcopy(completed)
    calls = []

    async def model(prompt, system, **kwargs):
        calls.append(prompt)
        return response(['b'])

    monkeypatch.setattr(service, '_call_llm', model)
    await service.generate_teacher_handout(
        course_id='c', outline_sections=[{'node_id': 'b', 'learning_objective': '独有教学目标',
            'node_content': '旧版已生成正文', 'content_blocks': [{'content': '旧版已生成正文'}]}], plan_sections={},
        lesson_context={'source': source}, completed_sections=completed, partial_text='未完成的真实片段',
    )
    prompt = calls[0]
    assert completed == before
    assert prompt.count(prose) == 1
    assert source in prompt and '未完成的真实片段' in prompt
    assert '独有教学目标' in prompt and '旧版已生成正文' not in prompt
    assert '<!-- section:a -->' not in prompt
    assert '<!-- section:b -->\n[在这里依教学需要自由编排内容块，每块标记后紧接完整正文]' in prompt
    assert '完成全部请求小节' in prompt


@pytest.mark.asyncio
async def test_budget_split_only_on_capacity_and_same_capability(monkeypatch):
    service = CourseService()
    calls = []
    scopes = []
    service._generation_budget = replace(
        service._generation_budget, teacher_handout_max_input_chars=4000, teacher_handout_max_input_tokens=10000
    )

    async def model(*args, **kwargs):
        calls.append(1)
        return response(["a"])

    async def scope(ids):
        scopes.append(ids)

    monkeypatch.setattr(service, "_call_llm", model)
    await service.generate_teacher_handout(
        course_id="c",
        outline_sections=[{"node_id": "a", "text": "x" * 1300}, {"node_id": "b", "text": "x" * 1300}],
        plan_sections={},
        lesson_context={},
        on_scope=scope,
    )
    assert scopes == [["a"]] and calls == [1]
    with pytest.raises(CourseGenerationBudgetExceeded):
        await service.generate_teacher_handout(
            course_id="c", outline_sections=[{"node_id": "a", "text": "x" * 3000}], plan_sections={}, lesson_context={}
        )
    assert calls == [1]


@pytest.mark.asyncio
async def test_plan_provider_error_is_not_automatically_retried(tmp_path):
    repo = TeacherLessonAuthoringRepository(tmp_path)
    repo.set_outline("course-1", "outline-v1")
    job = repo.create_job("course-1", "L1-1", source_outline_revision_id="outline-v1")
    calls = []

    async def planner(*args):
        calls.append(1)
        raise AIProviderRequestError("offline")

    result = await TeacherLessonAuthoringService(repo).run_plan_job(
        course_id="course-1",
        lesson_unit_id="L1-1",
        job_id=job["id"],
        course_data=single_section_course_data(),
        planner=planner,
    )
    assert result["status"] == "failed" and calls == [1]
    assert not result.get("auto_improvement")


@pytest.mark.asyncio
async def test_same_task_resume_is_atomic_and_rejects_changed_input(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from teacher_lesson_authoring import TeacherLessonAuthoringError

    repo, service, kwargs = fixture(tmp_path)
    jid = new_job(repo)
    repo.update_job("course-1", jid, input_fingerprint="frozen", status="failed", error={"retryable": True})
    with pytest.raises(TeacherLessonAuthoringError):
        repo.resume_lesson_generation("course-1", jid, input_fingerprint="changed")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: repo.resume_lesson_generation("course-1", jid, input_fingerprint="frozen"), range(2))
        )
    assert sum(created for _, created in results) == 1
    assert {job["id"] for job, _ in results} == {jid}
    assert len(repo.view("course-1")["jobs"]) == 1


@pytest.mark.asyncio
async def test_authorization_or_material_conflict_keeps_candidate_without_publication(tmp_path):
    from teacher_lesson_authoring import TeacherLessonAuthoringError

    repo, service, kwargs = fixture(tmp_path)

    async def generate(**request):
        return {"text": response(["L2-1-1", "L2-1-2"])}

    async def revoked():
        raise TeacherLessonAuthoringError("lesson_authorization_conflict", "authorization revoked")

    job = await service.run_script_job(**kwargs, job_id=new_job(repo), generator=generate, before_save=revoked)
    assert job["status"] == "failed" and not job["error"]["retryable"]
    assert len(job["result_sections"]) == 2
    assert not repo.lesson("course-1", "L1-1")["working_script_revision_id"]


@pytest.mark.asyncio
async def test_old_revision_blocks_remain_addressable_after_whole_lecture_generation(tmp_path):
    from teacher_script import compile_teacher_script_module_contract, compile_teacher_script_section

    repo, service, kwargs = fixture(tmp_path)
    old_sections = [
        compile_teacher_script_section(
            "## 核心教学\n\n历史正文。",
            compile_teacher_script_module_contract(s, kwargs["plan_sections"][s["node_id"]]),
        )
        for s in kwargs["outline_sections"]
    ]
    old = repo.save_script_revision(
        "course-1", "L1-1", old_sections, source_lesson_plan_revision_id=kwargs["source_plan_revision_id"]
    )
    revision = deepcopy(old["script_revisions"][-1])
    kwargs["expected_script_revision"] = old["working_script_revision_id"]

    async def generate(**request):
        return {"text": response(["L2-1-1", "L2-1-2"])}

    job = await service.run_script_job(**kwargs, job_id=new_job(repo), generator=generate)
    assert job["status"] == "completed", job.get("error")
    versions = repo.lesson("course-1", "L1-1")["script_revisions"]
    assert next(r for r in versions if r["revision_id"] == revision["revision_id"]) == revision
    old_ids = {b["block_id"] for s in revision["sections"] for b in s["blocks"]}
    assert old_ids.isdisjoint({b["block_id"] for s in job["result_sections"] for b in s["blocks"]})


@pytest.mark.asyncio
@pytest.mark.parametrize("repair_succeeds", [True, False])
async def test_plan_json_repair_is_structural_and_bounded(monkeypatch, repair_succeeds):
    from backend.tests.test_material_backed_course_generation import (
        _multi_section_outline,
        _combined_teacher_lesson_v4_response,
    )
    from ai_base import AIProviderRequestError

    plan = _multi_section_outline(["核心定义", "条件应用"])
    plan["chapters"][0]["node_id"] = "L1-1"
    source = {"course_id": "joint-repair", "course_name": "结构修复测试", "course_plan": plan, "course_outline": plan}
    service = CourseService()
    calls = []

    async def invoke(prompt, system, **kwargs):
        calls.append((prompt, kwargs))
        if len(calls) == 1 or not repair_succeeds:
            return "invalid JSON"
        return _combined_teacher_lesson_v4_response(system)

    monkeypatch.setattr(service, "_call_llm", invoke)
    if repair_succeeds:
        result = await service.prepare_teacher_lesson_plan(course_data=source, lesson_unit_id="L1-1")
        assert len(result["plan"]["sections"]) == 2
    else:
        with pytest.raises(AIProviderRequestError):
            await service.prepare_teacher_lesson_plan(course_data=source, lesson_unit_id="L1-1")
    assert len(calls) == 2
    assert "只修复" in calls[1][0]
    assert all(k["max_attempts"] == k["retry_count"] == 1 for _, k in calls)


@pytest.mark.asyncio
async def test_plan_save_failure_continues_without_model_call(tmp_path, monkeypatch):
    repo = TeacherLessonAuthoringRepository(tmp_path)
    repo.set_outline("course-1", "outline-v1")
    job = repo.create_job("course-1", "L1-1", source_outline_revision_id="outline-v1")
    calls = []

    async def planner(*args):
        calls.append(1)
        return {"plan": standard_lesson_plan(), "generation_source": "model"}

    save = repo.save_plan_revision
    monkeypatch.setattr(repo, "save_plan_revision", lambda *a, **k: (_ for _ in ()).throw(OSError("disk unavailable")))
    kwargs = dict(
        course_id="course-1",
        lesson_unit_id="L1-1",
        job_id=job["id"],
        course_data=single_section_course_data(),
        planner=planner,
    )
    failed = await TeacherLessonAuthoringService(repo).run_plan_job(**kwargs)
    assert failed["status"] == "failed" and failed["checkpoint"]["generated_plan_result"]
    monkeypatch.setattr(repo, "save_plan_revision", save)
    repo.resume_lesson_generation("course-1", job["id"], input_fingerprint="")
    result = await TeacherLessonAuthoringService(repo).run_plan_job(**kwargs)
    assert result["status"] == "completed", result.get("error")
    assert calls == [1]


def test_unrecognized_first_marker_preserves_visible_unassigned_draft():
    parsed = parse_handout_stream(
        "<!-- section:wrong -->\n真实但未归属的片段\n<!-- handout:end -->", ["a"], provider_complete=True
    )
    assert not parsed["completed"]
    assert parsed["unassigned_fragment"] == "真实但未归属的片段"
    assert parsed["error"] == "section_order_or_identity"


@pytest.mark.asyncio
async def test_formal_script_and_completed_job_are_saved_atomically(tmp_path, monkeypatch):
    repo, service, kwargs = fixture(tmp_path)
    original = repo.update_job

    async def generate(**request):
        return {"text": response(["L2-1-1", "L2-1-2"])}

    def lost_final_status(*args, **changes):
        if changes.get("status") == "completed":
            raise OSError("process lost after publication")
        return original(*args, **changes)

    monkeypatch.setattr(repo, "update_job", lost_final_status)
    job = await service.run_script_job(**kwargs, job_id=new_job(repo), generator=generate)
    reloaded = TeacherLessonAuthoringRepository(tmp_path)
    assert reloaded.get_job("course-1", job["id"])["status"] == "completed"
    assert len(reloaded.lesson("course-1", "L1-1")["script_revisions"]) == 1
    assert job["result_revision_id"] == reloaded.lesson("course-1", "L1-1")["working_script_revision_id"]
