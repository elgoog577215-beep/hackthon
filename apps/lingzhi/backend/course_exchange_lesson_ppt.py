"""Read existing per-lecture exports through the common publication contract."""

from copy import deepcopy


def lesson_ppt_projects(storage, course, public_document):
    # Authoring drafts stay in their existing repository. This adapter neither
    # creates another project nor writes the teacher body into a student store.
    if course.get("authoring_surface") != "teacher" or not course.get("course_id"):
        return {}
    from course_document import stable_hash
    from course_revisions import revision_vector_for_course
    from ppt_manuscript_quality import manuscript_quality_passed
    from teacher_content_projection import authoring_repository
    from teacher_authoring_errors import TeacherLessonAuthoringError
    from teacher_lesson_authoring import teacher_lesson_v6_source
    from teaching_representations import teaching_representation_repository

    state = authoring_repository(storage).load(course["course_id"])
    public_blocks = {b["block_id"]: b["internal_revision"] for b in public_document["blocks"]}
    titles = {s["section_id"]: s["title"] for s in public_document["sections"]}
    projects = {}
    for lesson_id, lesson in state.get("lessons", {}).items():
        manuscript_state = lesson.get("ppt_manuscript") or {}
        manuscript = manuscript_state.get("manuscript") or {}
        revision = manuscript_state.get("revision")
        representation_id = manuscript_state.get("generated_representation_id")
        # The current main workflow derives pages solely from the saved handout.
        # Other branches can contain private uploads and need their own consent.
        if (manuscript_state.get("generation_contract_version") != "script_ppt_bundle_v1"
                or manuscript_state.get("status") not in {"ready", "confirmed"}
                or manuscript_state.get("source_state") != "current"
                or manuscript_state.get("source_material_revision") != stable_hash([], prefix="pptrefs_")
                or not revision or not representation_id
                or manuscript.get("manuscript_revision") != revision
                or not manuscript_quality_passed(manuscript)):
            continue
        plan_id = lesson.get("working_revision_id")
        script_id = lesson.get("working_script_revision_id")
        if (lesson.get("source_state", "current") != "current"
                or manuscript_state.get("source_lesson_plan_revision_id") != plan_id
                or manuscript_state.get("source_script_revision_id") != script_id):
            continue
        plan = next((r for r in lesson.get("revisions", []) if r.get("revision_id") == plan_id), None)
        script = next((r for r in lesson.get("script_revisions", []) if r.get("revision_id") == script_id), None)
        asset = next((a for a in lesson.get("ppt_assets", [])
                      if a.get("working_representation_id") == representation_id
                      and a.get("source_state") == "current"
                      and a.get("source_lesson_plan_revision_id") == plan_id
                      and a.get("source_script_revision_id") == script_id
                      and a.get("ppt_manuscript_revision") == revision), None)
        if not plan or not script or not asset or lesson_id not in titles:
            continue
        try:
            source, view, scope_id = teacher_lesson_v6_source(
                course, lesson_unit_id=lesson_id, plan_revision=plan, script_revision=script)
        except TeacherLessonAuthoringError:
            continue
        # Every source block must be present in the disclosed course, including
        # its exact revision. A single hidden block makes the deck unshareable.
        if not source.blocks or any(public_blocks.get(b.block_id) != b.internal_revision for b in source.blocks):
            continue
        registry = teaching_representation_repository.for_storage_scope(course["course_id"], scope_id).load(course["course_id"])
        representation = next((r for r in registry.representations if r.representation_id == representation_id), None)
        spec = next((s for s in registry.specs if representation and s.spec_id == representation.spec_id), None)
        if not representation or not spec or representation.status != "ready" or representation.rebuild_required:
            continue
        vector = revision_vector_for_course(source, view).revisions
        if any(b.material_evidence_ids or any(vector.get(k) != v for k, v in b.source_revisions.items())
               for b in [*representation.source_bindings, *spec.source_bindings]):
            continue
        content = spec.payload.get("content") or {}
        if (content.get("schema_version") != "slide_deck_v6"
                or (content.get("ppt_manuscript") or {}).get("manuscript_revision") != revision):
            continue
        projects[f"lesson-ppt:{lesson_id}"] = {
            "title": titles[lesson_id], "status": "ready", "confirmed_revision": revision,
            "manuscript": deepcopy(manuscript), "lesson_ids": [lesson_id], "asset_ids": [],
            "sources": {"materials": [], "lectures": [{"lesson_id": lesson_id, "title": titles[lesson_id]}],
                        "blocks": [{"block_id": b.block_id, "revision": b.internal_revision} for b in source.blocks]},
            "last_good_render": {"deck": deepcopy(content), "ppt_manuscript": deepcopy(manuscript), "manuscript_revision": revision},
        }
    return projects
