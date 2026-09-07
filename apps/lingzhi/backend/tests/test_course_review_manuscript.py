import asyncio
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace

import pytest

from course_evolution.manuscript_changes import apply_manuscript_candidate, generate_manuscript_candidate
from course_evolution.teacher_planning import _authoring_units
from ppt_teaching_manuscript import compile_teaching_manuscript
from backend.tests.test_ppt_fixed_templates import fixture, lowered


class Repository:
    def __init__(self):
        document, graph, template = fixture()
        manuscript = compile_teaching_manuscript(document, graph, template, {}, [{
            **lowered("bullets"), "page_id": "p", "teaching_unit_id": graph.units[0].teaching_unit_id,
            "source_block_ids": ["b"],
        }])
        self.state = {"source_state": "current", "source_script_revision_id": "script-1",
                      "revision": manuscript.manuscript_revision, "manuscript": manuscript.model_dump(mode="json")}
        self.script = "script-1"
        self.writes = 0

    def current_v6_ppt_manuscript(self, *_):
        return deepcopy(self.state)

    def lesson(self, *_):
        return {"working_script_revision_id": self.script, "ppt_manuscript": self.state}

    def _course_lock(self, *_):
        return nullcontext()

    def update_v6_ppt_manuscript_draft(self, *_, expected_manuscript_revision, manuscript):
        if self.state["revision"] != expected_manuscript_revision:
            raise ValueError("revision conflict")
        self.state.update(revision=manuscript["manuscript_revision"], manuscript=deepcopy(manuscript))
        self.writes += 1
        return self.state


def candidate(repository):
    item = SimpleNamespace(base_revisions={"ppt:lesson:p": repository.state["revision"]},
        metadata={"unit_id": "ppt:lesson:p", "literal_replacement": {"before": "课堂学习", "after": "课堂复习"}})
    return asyncio.run(generate_manuscript_candidate(course_id="course", lesson_id="lesson",
        plan=SimpleNamespace(request_text="修改标题", user_id="teacher"), items=[item],
        repository=repository, course_service=None))


def test_candidate_does_not_write_and_apply_undo_preserve_script():
    repository = Repository()
    before = deepcopy(repository.state)
    payload = candidate(repository)
    assert repository.state == before
    assert payload["candidate_manuscript"]["pages"][0]["title"] == "课堂复习"
    apply_manuscript_candidate(repository, "course", payload)
    apply_manuscript_candidate(repository, "course", payload)
    assert repository.writes == 1
    apply_manuscript_candidate(repository, "course", payload, undo=True)
    assert repository.state["manuscript"] == before["manuscript"]
    assert repository.script == "script-1"


def test_conflicting_edit_and_changed_source_are_preserved():
    repository = Repository()
    payload = candidate(repository)
    repository.state["revision"] = "teacher-edit"
    with pytest.raises(ValueError, match="revision conflict"):
        apply_manuscript_candidate(repository, "course", payload)
    repository.script = "script-2"
    with pytest.raises(ValueError, match="来源已变化"):
        apply_manuscript_candidate(repository, "course", payload)
    assert repository.writes == 0


def test_review_indexes_current_manuscript_before_exported_assets():
    repository = Repository()
    units = _authoring_units({"lessons": {"lesson": repository.lesson()}})
    pages = [unit for unit in units if unit.asset_type == "ppt"]
    assert len(pages) == 1
    assert pages[0].source_revision == repository.state["revision"]
    assert pages[0].full_text_fields["title"] == "课堂学习"
