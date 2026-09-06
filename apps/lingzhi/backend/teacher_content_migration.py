"""Offline teacher-handout migration. No model or learner-data access."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import os

from course_document import document_from_legacy_course, course_view_from_document
from course_repository import CourseDocumentConflict
from teacher_course_content import SCHEMA, unified, commit_outline, commit_authoring, hydrate_authoring
from teacher_outline_source import has_complete_teacher_outline


class MemoryCourse:
    emit_course_events = False
    def __init__(self, raw): self.raw = deepcopy(raw)
    def update_course_data(self, course_id, update):
        self.raw = update(deepcopy(self.raw))
        return deepcopy(self.raw)


def prepare(raw, authoring, source):
    if raw.get('authoring_surface') != 'teacher':
        return {'status':'historical_student', 'course':raw, 'authoring':authoring}
    if unified(raw):
        hydrated = hydrate_authoring(raw, authoring)
        memory = MemoryCourse(raw)
        compact = commit_authoring(memory, hydrated)
        if memory.raw != raw:
            raise CourseDocumentConflict('已有统一课程的正文与教师引用不一致。')
        status = 'projection_repair' if compact != authoring else 'already_unified'
        return {'status':status, 'course':raw, 'authoring':compact, 'verified_lessons':len(hydrated.get('_canonical_baselines') or {})}
    if any(j.get('status') in {'pending','running','queued','paused'} for j in (authoring.get('jobs') or {}).values()):
        raise CourseDocumentConflict('课程仍有活动或可恢复教师任务，请自然结束后迁移。')
    if not has_complete_teacher_outline(source):
        raise CourseDocumentConflict('缺少当前完整大纲，不能确认讲次身份。')
    outline_revision = str((source.get('course_knowledge_scope_contract') or {}).get('revision_id')
        or (source.get('course_teaching_plan') or {}).get('source_outline_revision_id') or source.get('blueprint_revision_id') or '')
    if not outline_revision or authoring.get('outline_revision_id') != outline_revision:
        raise CourseDocumentConflict('教师资产与大纲来源修订不一致。')
    eligible = 0
    for lesson in (authoring.get('lessons') or {}).values():
        current = next((r for r in lesson.get('script_revisions') or [] if r.get('revision_id') == lesson.get('working_script_revision_id')),None)
        if not current: continue
        if not current.get('publication_eligible') or current.get('source_lesson_plan_revision_id') != lesson.get('working_revision_id') or lesson.get('source_state','current') != 'current':
            raise CourseDocumentConflict('当前讲义不完整或来源已过期。')
        plan = next((r for r in lesson.get('revisions') or [] if r.get('revision_id') == lesson.get('working_revision_id')),None)
        if not plan or plan.get('source_outline_revision_id') != outline_revision:
            raise CourseDocumentConflict('无法核实当前教案的来源。')
        eligible += 1
    if not eligible:
        raise CourseDocumentConflict('没有可迁移的完整当前讲义。')
    target=deepcopy(raw)
    if not target.get('course_document'):
        document=document_from_legacy_course(target)
        target['course_document']=document.model_dump(mode='json')
        target['course_document_revision']=document.document_revision
    target['teacher_production_schema']=SCHEMA
    memory=MemoryCourse(target)
    commit_outline(memory,source)
    compact=commit_authoring(memory,authoring)
    migrated=memory.raw
    compact=commit_authoring(memory, hydrate_authoring(migrated, compact))
    # Existing content may only be adopted with the same identity and text.
    original={b['block_id']:b for b in (raw.get('course_document') or {}).get('blocks') or [] if b.get('status')!='retired' and (b.get('payload') or {}).get('markdown')}
    current={b['block_id']:b for b in migrated['course_document']['blocks']}
    if any(bid not in current or old['payload'].get('markdown') != current[bid]['payload'].get('markdown') for bid,old in original.items()):
        raise CourseDocumentConflict('迁移不能覆盖现有正式正文或重新分配内容块身份。')
    return {'status':'ready','course':migrated,'authoring':compact,'verified_lessons':eligible}


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def atomic(path,data):
    fd,name=tempfile.mkstemp(prefix='.'+path.name,suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def migrate(data_dir, *, mode='preflight', backup_dir=None, course_ids=None):
    root=Path(data_dir).resolve();results=[]
    backup=None
    if mode=='apply':
        if backup_dir is None:raise ValueError('apply requires an external backup directory')
        parent=Path(backup_dir).resolve()
        if parent==root or root in parent.parents:raise ValueError('backup must be outside the data directory')
        # Also prohibit accidentally placing user data inside a Git checkout.
        if any((p/'.git').exists() for p in [parent,*parent.parents]):raise ValueError('backup must be outside Git repositories')
        backup=parent/datetime.now(timezone.utc).strftime('teacher-content-%Y%m%dT%H%M%S%fZ');backup.mkdir(parents=True)
    for path in sorted((root/'courses').glob('*.json')):
        cid=path.stem
        import re
        if re.search(r'\.v\d+$', cid):
            continue  # Storage history is immutable, never a migration target.
        if course_ids and cid not in course_ids:continue
        ap=root/'teacher_lesson_authoring'/f'{cid}.json'
        try:
            raw=json.loads(path.read_text());author=json.loads(ap.read_text()) if ap.exists() else {'course_id':cid,'lessons':{}}
            source=course_view_from_document(raw,raw['course_document']) if raw.get('course_document') else raw
            wp=None
            if not unified(raw) and raw.get('authoring_surface')=='teacher' and not has_complete_teacher_outline(source):
                jid=str(raw.get('generation_job_id') or '')
                if not jid or Path(jid).name != jid:raise CourseDocumentConflict('无法定位原大纲工作区。')
                wp=root/'generation_workspaces'/f'{jid}.json'
                workspace=json.loads(wp.read_text())
                if workspace.get('course_id')!=cid:raise CourseDocumentConflict('工作区课程身份不一致。')
                source=workspace.get('course_data') or {}
            inputs=[path]+([ap] if ap.exists() else [])+([wp] if wp else [])
            hashes={str(p.relative_to(root)):digest(p) for p in inputs}
            result=prepare(raw,author,source)
            status=result['status']
            if mode=='verify' and status in {'ready','projection_repair'}: status='not_migrated'
            if mode=='apply' and status in {'ready','projection_repair'}:
                assert backup is not None
                course_backup=backup/cid;course_backup.mkdir()
                for p in inputs:
                    dest=course_backup/p.relative_to(root);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
                    if digest(dest)!=hashes[str(p.relative_to(root))]:raise CourseDocumentConflict('备份校验失败。')
                atomic(course_backup/'manifest.json',{'course_id':cid,'sha256':hashes})
                lock_root=root/'teacher_lesson_authoring';lock_root.mkdir(exist_ok=True)
                with (lock_root/'.authoring.lock').open('a+') as alock, path.with_suffix('.lock').open('a+') as clock:
                    fcntl.flock(alock,fcntl.LOCK_EX);fcntl.flock(clock,fcntl.LOCK_EX)
                    if any(digest(p)!=hashes[str(p.relative_to(root))] for p in inputs):raise CourseDocumentConflict('预检后数据已变化。')
                    atomic(path,result['course'])
                    atomic(ap,result['authoring'])
                status='migrated'
            results.append({'course_id':cid,'status':status,'lessons':result.get('verified_lessons',0)})
        except (CourseDocumentConflict,ValueError,KeyError,OSError) as exc:
            results.append({'course_id':cid,'status':'conflict','reason':str(exc)})
    return {'mode':mode,'backup':str(backup) if backup else None,'courses':results}
