#!/usr/bin/env python3
"""Run the real teacher HTTP chain in a local, isolated backend (no mocks)."""

import argparse
import io
import json
import time
import uuid
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8018')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if urlparse(args.base_url).hostname not in {'localhost', '127.0.0.1', '::1'}:
        parser.error('Only an isolated local backend is supported')
    args.output.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    report = {'run_id': run_id, 'status': 'running', 'stages': []}
    client = httpx.Client(base_url=args.base_url, timeout=180,
                         headers={'X-User-Id': 'teacher-local-workbench-v1'})

    def record(stage: str, **values) -> None:
        entry = {'stage': stage, **values}
        report['stages'].append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))

    def api(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        response = client.request(method, path, json=payload) if payload is not None else client.request(method, path)
        response.raise_for_status()
        return response.json()

    def poll(stage: str, path: str, done: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
        started = time.monotonic()
        previous = None
        while time.monotonic() - started < 1800:
            data = api('GET', path)
            state = (data.get('status'), data.get('phase'), (data.get('job') or {}).get('phase'))
            if state != previous:
                print(json.dumps({'stage': stage, 'state': state}, ensure_ascii=False), flush=True)
                previous = state
            if data.get('status') in {'failed', 'cancelled', 'paused'}:
                raise RuntimeError(f'{stage}: {json.dumps(data, ensure_ascii=False)}')
            if done(data):
                record(stage, elapsed_seconds=round(time.monotonic() - started, 3), status=data.get('status'))
                return data
            time.sleep(2)
        raise TimeoutError(stage)

    def lesson_job(kind: str, teacher_path: str, lesson_id: str) -> None:
        started = time.monotonic()
        job = api('POST', f'{teacher_path}/lessons/{lesson_id}/{kind}/generate',
                  {'request_id': f'{run_id}-{kind}'})['job']
        job_id = job['id']
        first_stream = None
        count = 0
        final = job
        with client.stream('GET', f'{teacher_path}/lesson-jobs/{job_id}/stream', timeout=1800) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith('data:'):
                    continue
                event = json.loads(line[5:].strip())
                final = event.get('job') or final
                count += 1
                if first_stream is None and int(final.get('stream_sequence') or 0) > 0:
                    first_stream = round(time.monotonic() - started, 3)
                    print(json.dumps({'stage': kind, 'first_stream_seconds': first_stream}), flush=True)
        (args.output / f'{kind}-job.json').write_text(json.dumps(final, ensure_ascii=False, indent=2))
        record(kind, elapsed_seconds=round(time.monotonic() - started, 3), job_id=job_id,
               first_stream_seconds=first_stream, stream_events=count, status=final.get('status'))
        if final.get('status') not in {'completed', 'completed_with_warnings'}:
            raise RuntimeError(f'{kind}: {final.get("error")}')

    try:
        brief = {'target_audience': '已学过函数与极限的大学一年级学生', 'total_class_hours': 2,
                 'lecture_count': 2, 'teaching_context': 'classroom'}
        generation = {'subject': '导数定义与切线入门', 'teacher_authoring_mode': 'lesson_assets_v1',
                      'teacher_course_brief': brief, 'course_teaching_type': 'theory',
                      'pedagogy_mode': 'math_formal', 'production_mode': 'manual',
                      'requirements': '共两讲，每讲45分钟。第一讲仅讲导数定义和平方函数的切线；第二讲讲基本求导规则。保留完整教学要求。'}
        course = api('POST', '/api/teacher/courses', {
            'course_name': f'本地真实链路验收-{run_id[:8]}', 'target_grade': '大学一年级',
            'course_category': '专业基础课', 'credits': 1, 'weekly_hours': 2, 'total_hours': 2,
            'planned_lecture_count': 2, 'generation_request': generation})
        cid = course['course_id']
        report['course_id'] = cid
        teacher = f'/api/teacher/courses/{cid}'
        record('create', course_id=cid)
        task = api('POST', '/api/course-generation/generate', {
            **generation, 'target_course_id': cid, 'request_id': run_id})
        tid = task['job_id']
        report['outline_task_id'] = tid
        poll('outline_framework', f'/api/tasks/{tid}',
             lambda d: (d.get('phase') or d.get('current_phase')) == 'outline_framework_ready')
        api('POST', f'/api/courses/{cid}/generation/outline-details/continue', {'task_id': tid})
        poll('outline_details', f'/api/tasks/{tid}',
             lambda d: d.get('status') in {'completed', 'completed_with_warnings'})
        view = api('GET', f'{teacher}/lesson-authoring')
        (args.output / 'outline.json').write_text(json.dumps(view, ensure_ascii=False, indent=2))
        assert len(view['lessons']) == 2, 'Expected the requested two lectures'
        lid = view['lessons'][0]['lesson_unit_id']
        report['lesson_id'] = lid
        lesson_job('plan', teacher, lid)
        lesson_job('script', teacher, lid)
        view = api('GET', f'{teacher}/lesson-authoring')
        (args.output / 'authoring.json').write_text(json.dumps(view, ensure_ascii=False, indent=2))
        first, second = view['lessons']
        assert first['plan']['ready'] and first['script']['ready']
        assert not second['plan']['ready'] and not second['script']['ready']
        preview = api('GET', f'{teacher}/preview')
        (args.output / 'preview.json').write_text(json.dumps(preview, ensure_ascii=False, indent=2))
        catalog = api('GET', f'{teacher}/ppt-projects')
        project = api('POST', f'{teacher}/ppt-projects', {
            'lesson_ids': [lid], 'expected_revision': catalog['document_revision']})
        pid = project['project_id']
        report['ppt_project_id'] = pid
        ppt_path = f'{teacher}/ppt-projects/{pid}'
        api('POST', f'{ppt_path}/prepare', {'expected_revision': project['revision']})
        project = poll('ppt_manuscript', ppt_path, lambda d: d.get('status') == 'draft')
        assert project['confirmable'], 'PPT manuscript failed its normal quality gate'
        project = api('POST', f'{ppt_path}/confirm', {'expected_revision': project['revision']})
        api('POST', f'{ppt_path}/render', {'expected_revision': project['revision']})
        project = poll('ppt_render', ppt_path, lambda d: d.get('status') == 'ready')
        assert project['source_state'] == 'current'
        (args.output / 'ppt-project.json').write_text(json.dumps(project, ensure_ascii=False, indent=2))
        started = time.monotonic()
        response = client.get(f'{ppt_path}/export')
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            slides = [name for name in archive.namelist()
                      if name.startswith('ppt/slides/slide') and name.endswith('.xml')]
        assert slides, 'Export has no slides'
        (args.output / 'first-lecture.pptx').write_bytes(response.content)
        report['status'] = 'passed'
        record('export', elapsed_seconds=round(time.monotonic() - started, 3),
               slides=len(slides), bytes=len(response.content))
    except Exception as error:
        report['status'] = 'failed'
        record('failure', error=str(error))
        raise
    finally:
        client.close()


if __name__ == '__main__':
    main()
