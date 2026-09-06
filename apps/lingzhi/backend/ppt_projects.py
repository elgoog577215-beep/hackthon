"""PPT source selections and three-step work, using the existing V6 engine.

Projects own source references, reviewable manuscripts and render receipts.
They never own a second editable course handout.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
import uuid
from functools import wraps


def authoring_transaction(method):
    @wraps(method)
    def locked(self, *args, **kwargs):
        with self.jobs._lock:
            return method(self, *args, **kwargs)
    return locked

from course_document import CourseDocument, CourseBlock, CourseSection, course_view_from_document, refresh_document_revision, stable_hash
from course_presentation_graph import compile_course_presentation_graph
from material_parser import parse_material_asset
from material_storage import material_repository
from ppt_manuscript_quality import manuscript_quality_passed
from ppt_teaching_manuscript import manuscript_layout_options, validate_reviewable_manuscript, template_for_manuscript
from slide_ai_planning_v6 import build_ai_base_story_planner_v6, build_ai_base_visual_planner_v2
from slide_deck_v6 import PptManuscriptV1, revise_ppt_manuscript_v1, compile_slide_deck_v6_from_manuscript
from slide_deck_v6_orchestrator import SlideDeckV6CandidateRepository, SlideDeckV6Orchestrator
from template_layout_contract import compile_builtin_template_layout_contract_v1
from teaching_representations import teaching_representation_repository
from teacher_lesson_authoring import TeacherLessonAuthoringError


def conflict(message="所选内容已变化，请重新选择来源。"):
    return TeacherLessonAuthoringError("ppt_project_source_conflict", message)


class PptProjectService:
    def __init__(self, storage, jobs, *, materials=material_repository):
        self.storage, self.jobs, self.materials = storage, jobs, materials
        self.candidates = SlideDeckV6CandidateRepository(jobs.root / "v6_candidates")
        self.orchestrator = SlideDeckV6Orchestrator(representation_repository=teaching_representation_repository,
            candidate_repository=self.candidates, progress_root=jobs.root / "v6_progress")

    def load(self, course_id, project_id):
        project = (self.storage.load_course(course_id).get("teacher_ppt_projects") or {}).get(project_id)
        if not project:
            raise TeacherLessonAuthoringError("ppt_project_not_found", "PPT 工作区不存在。")
        return deepcopy(project)

    def update(self, course_id, project_id, changes, *, expected=None, job_id=None, require_running=False, source_snapshot=None):
        result = {}
        def commit(raw):
            nonlocal result
            if not raw:
                raise conflict("课程已删除。")
            project = (raw.get("teacher_ppt_projects") or {}).get(project_id)
            if not project:
                raise conflict("PPT 工作区不存在。")
            if expected and project.get("revision") != expected:
                raise conflict("PPT 内容稿已变化，请刷新后重试。")
            if job_id and project.get("job_id") != job_id:
                raise conflict("PPT 任务已被替换。")
            if require_running and project.get("status") not in {"building", "rendering"}:
                raise conflict("PPT 任务已暂停。")
            if source_snapshot is not None and self.sources(course_id, project["lesson_ids"], project["asset_ids"], raw=raw) != source_snapshot:
                raise conflict()
            project.update(deepcopy(changes))
            project["revision"] = stable_hash({k:v for k,v in project.items() if k != "revision"}, prefix="pptp_")
            result = deepcopy(project)
            return raw
        self.storage.update_course_data(course_id, commit)
        return result

    def sources(self, course_id, lesson_ids, asset_ids, *, raw=None):
        raw = self.storage.load_course(course_id) if raw is None else raw
        doc = CourseDocument.model_validate(raw["course_document"])
        lectures = {s.section_id: s for s in doc.sections if s.level == 1}
        if len(set(lesson_ids)) != len(lesson_ids) or any(lid not in lectures for lid in lesson_ids):
            raise conflict("所选讲次不存在。")
        blocks = []
        for lid in lesson_ids:
            section_ids = {s.section_id for s in doc.sections if s.parent_section_id == lid or s.section_id == lid}
            current = [b for b in doc.blocks if b.section_id in section_ids and b.status == "final"]
            if not current:
                raise conflict("所选讲次尚无正式讲义。")
            blocks.extend(current)
        uploads = raw.get("teacher_ppt_uploads") or {}
        assets = []
        for aid in dict.fromkeys(asset_ids):
            if aid not in uploads:
                raise conflict("资料不属于当前课程。")
            asset = self.materials.get_asset(aid)
            if not asset or asset.sha256 != uploads[aid]["sha256"]:
                raise conflict("上传资料已变化或不可读取。")
            assets.append({"asset_id": aid, "sha256": asset.sha256, "filename": asset.filename})
        if not blocks and not assets:
            raise conflict("请选择讲义或上传资料。")
        return {"blocks": [{"block_id": b.block_id, "revision": b.internal_revision} for b in blocks],
            "lectures": [{"lesson_id": lid, "title": lectures[lid].title} for lid in lesson_ids], "materials": assets}

    def create(self, course_id, lesson_ids, asset_ids, *, title, expected_revision):
        raw = self.storage.load_course(course_id)
        if raw.get("course_document_revision") != expected_revision:
            raise conflict()
        sources = self.sources(course_id, lesson_ids, asset_ids)
        project = {"project_id": "ppt-" + uuid.uuid4().hex, "course_id": course_id,
            "title": title or " / ".join(x["title"] for x in sources["lectures"]) or sources["materials"][0]["filename"],
            "lesson_ids": lesson_ids, "asset_ids": asset_ids, "sources": sources,
            "status": "selected", "theme": "academic-editorial", "mode": "teaching",
            "manuscript": None, "last_good_render": None, "source_state": "current"}
        project["revision"] = stable_hash(project, prefix="pptp_")
        def save(latest):
            if latest.get("course_document_revision") != expected_revision:
                raise conflict()
            latest.setdefault("teacher_ppt_projects", {})[project["project_id"]] = project
            return latest
        self.storage.update_course_data(course_id, save)
        return project

    def source_current(self, project):
        try:
            return self.sources(project["course_id"], project["lesson_ids"], project["asset_ids"]) == project["sources"]
        except (TeacherLessonAuthoringError, ValueError):
            return False

    def document(self, project):
        if not self.source_current(project):
            raise conflict()
        raw = self.storage.load_course(project["course_id"])
        doc = CourseDocument.model_validate(raw["course_document"])
        ids = {b["block_id"] for b in project["sources"]["blocks"]}
        doc.blocks = [b for b in doc.blocks if b.block_id in ids]
        section_ids = {b.section_id for b in doc.blocks} | set(project["lesson_ids"])
        doc.sections = [s for s in doc.sections if s.section_id in section_ids]
        for source in project["sources"]["materials"]:
            parsed = self.materials.load_parsed_document(source["asset_id"])
            if not parsed or parsed.source_sha256 != source["sha256"] or parsed.parse_status not in {"parsed", "degraded"}:
                raise conflict("资料尚未完成解析，请重试。")
            sid = "ppt-material-" + source["asset_id"]
            doc.sections.append(CourseSection(section_id=sid, title=source["filename"], level=1, position=len(doc.sections)))
            for item in parsed.blocks:
                if item.text.strip():
                    doc.blocks.append(CourseBlock(block_id=f"{sid}-{item.block_id}", section_id=sid,
                        position=item.order, kind="source_excerpt", role="concept", payload={"title":"", "markdown":item.text},
                        evidence_refs=[item.block_id], asset_refs=[source["asset_id"]], status="final"))
        if not doc.blocks:
            raise conflict("所选资料没有可用于 PPT 的正文。")
        doc.title = project["title"]
        return refresh_document_revision(doc)

    def template(self, project):
        if project.get("manuscript"):
            return template_for_manuscript(PptManuscriptV1.model_validate(project["manuscript"]))
        from ppt_teaching_flags import three_stage_enabled
        if three_stage_enabled():
            from ppt_layout_execution import compile_teaching_template
            return compile_teaching_template(project["theme"])
        from ppt_fixed_templates import compile_fixed_template
        return compile_fixed_template(project["theme"])

    def view(self, course_id, project_id):
        project = self.load(course_id, project_id)
        project["source_state"] = "current" if self.source_current(project) else "stale"
        if project.get("job_id"):
            project["job"] = self.jobs.expire_stale_job(course_id, project["job_id"])
            if project["job"].get("status") in {"failed", "paused", "cancelled"} and project["status"] in {"building", "rendering"}:
                project["status"] = "paused"
        project["confirmable"] = project["source_state"] == "current" and manuscript_quality_passed(project.get("manuscript") or {})
        if project.get("manuscript"):
            manuscript = PptManuscriptV1.model_validate(project["manuscript"])
            template = self.template(project)
            project["layouts"] = manuscript_layout_options(manuscript, template) if manuscript.teaching_content_contract_version == "page_teaching_v2" else []
        return project

    @authoring_transaction
    def edit(self, course_id, project_id, expected, page_updates, pacing=None):
        project = self.load(course_id, project_id)
        if project["status"] in {"building", "rendering"}:
            raise conflict("当前任务仍在运行。")
        document = self.document(project)
        manuscript = revise_ppt_manuscript_v1(PptManuscriptV1.model_validate(project["manuscript"]), page_updates, pacing=pacing)
        graph = compile_course_presentation_graph(document, teaching_plan={})
        template = self.template(project)
        if manuscript.teaching_content_contract_version == "page_teaching_v2":
            validate_reviewable_manuscript(document, graph, manuscript, template)
        else:
            compile_slide_deck_v6_from_manuscript(document, graph, manuscript, template)
        return self.update(course_id, project_id, {"manuscript":manuscript.model_dump(mode="json"), "status":"draft"}, expected=expected, source_snapshot=project["sources"])

    @authoring_transaction
    def confirm(self, course_id, project_id, expected):
        project = self.load(course_id, project_id)
        if not self.source_current(project):
            raise conflict()
        if project["status"] not in {"draft", "confirmed", "ready"} or not manuscript_quality_passed(project.get("manuscript") or {}):
            raise conflict("请先保存可用的内容与排版稿。")
        return self.update(course_id, project_id, {"status":"confirmed", "confirmed_revision":project["manuscript"]["manuscript_revision"]}, expected=expected, source_snapshot=project["sources"])

    @authoring_transaction
    def start(self, course_id, project_id, expected, *, render=False):
        project = self.load(course_id, project_id)
        if project["revision"] != expected or not self.source_current(project):
            raise conflict()
        if project.get("job_id"):
            job = self.jobs.expire_stale_job(course_id, project["job_id"])
            if job.get("status") in {"pending", "running"}:
                return self.view(course_id, project_id)
        if render and (project.get("confirmed_revision") != (project.get("manuscript") or {}).get("manuscript_revision") or not project.get("confirmed_revision")):
            raise conflict("请先确认内容与排版稿。")
        job = self.jobs.create_job(course_id, project_id, job_type="teacher_lesson_ppt_generation" if render else "teacher_lesson_ppt_manuscript_generation", request_id=uuid.uuid4().hex)
        jid = job["id"]
        try:
            previous_job_id = project.get("job_id")
            if previous_job_id and project.get("status") == "paused":
                previous_job = self.jobs.get_job(course_id, previous_job_id)
                if bool((previous_job.get("request_snapshot") or {}).get("render")) == render:
                    try:
                        self.candidates.clone_checkpoint(previous_job_id, jid)
                    except FileNotFoundError:
                        pass
            self.jobs.update_job(course_id, jid, request_snapshot={"ppt_project_id":project_id, "render":render}, restart_whole=False)
            project = self.update(course_id, project_id, {"status":"rendering" if render else "building", "job_id":jid, "error":None}, expected=expected, source_snapshot=project["sources"])
        except BaseException:
            self.jobs.update_job(course_id, jid, status="cancelled", phase="cancelled")
            raise
        task = asyncio.create_task(self.run(project, render=render))
        self.jobs.track_runtime_job(course_id, task)
        return project

    async def run(self, project, *, render):
        cid, pid, jid = project["course_id"], project["project_id"], project["job_id"]
        try:
            self.jobs.update_job(cid, jid, status="running", phase="parsing", message="正在解析所选资料")
            for source in project["sources"]["materials"]:
                await parse_material_asset(self.materials, self.materials.get_asset(source["asset_id"]))
            document = self.document(project)
            view = course_view_from_document({"course_id":cid}, document)
            view["teacher_lesson_source"] = {"real_course_id":cid, "lesson_unit_ids":project["lesson_ids"],
                "script_revision_id":stable_hash(project["sources"], prefix="pptsrc_"), "project_id":pid,
                "material_bindings":[{"material_asset_id":m["asset_id"], "source_asset_id":m["asset_id"], "source_label":m["filename"], "role":"reference"} for m in project["sources"]["materials"]]}
            def current():
                job = self.jobs.get_job(cid, jid)
                return document.document_revision if job.get("status") == "running" and self.source_current(project) else ""
            async def progress(value):
                if not current():
                    raise conflict("来源已变化或任务已暂停。")
                self.jobs.update_job_live(cid, jid, phase=str(value.get("stage") or "building"), progress=int(value.get("percent") or 0))
            template = self.template(project)
            result = await self.orchestrator.build(task_id=jid, document=document, course_data=view, mode=project["mode"], theme=project["theme"],
                story_planner=build_ai_base_story_planner_v6(), visual_planner=build_ai_base_visual_planner_v2(),
                source_revision_provider=current, template_contract=template, template_digest_provider=lambda: template.template_digest,
                publish_result=False, manuscript_only=not render,
                confirmed_manuscript=PptManuscriptV1.model_validate(project["manuscript"]) if render else None,
                progress_callback=progress)
            if not current():
                raise conflict()
            if render:
                candidate = self.candidates.load(jid)
                changes = {"status":"ready", "last_good_render":{"task_id":jid, "manuscript_revision":project["confirmed_revision"],
                    "source_revision":document.document_revision, "deck":candidate["deck"], "ppt_manuscript":project["manuscript"]}}
            else:
                changes = {"status":"draft", "manuscript":result["ppt_manuscript"], "confirmed_revision":""}
            with self.jobs._lock:
                if self.jobs.get_job(cid, jid).get("status") != "running":
                    raise conflict("PPT 任务已暂停。")
                self.update(cid, pid, changes, job_id=jid, require_running=True, source_snapshot=project["sources"])
                self.jobs.update_job(cid, jid, status="completed", phase="completed", progress=100)
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            from teacher_lesson_authoring import generation_failure
            failure = generation_failure(exc, "ppt_project_build_failed")
            with self.jobs._lock:
                self.jobs.update_job(cid, jid, status="paused", phase="paused", error=failure)
                try:
                    self.update(cid, pid, {"status":"paused", "error":failure}, job_id=jid)
                except TeacherLessonAuthoringError:
                    pass  # A newer task owns the project; retain this task's failure only.
