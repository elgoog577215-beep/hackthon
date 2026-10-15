"""Historical subject-library revisions remain immutable and explicitly pinned."""
from copy import deepcopy

import pytest

from subject_library_repository import SubjectLibraryConflict, SubjectLibraryRepository


def _library():
    return {
        "schema_version": "knowledge_library_v3",
        "library_id": "cs.data_structures",
        "subject_id": "computer_science.data_structures",
        "revision_id": "revision-1",
        "source_course_ids": ["course-ds"],
        "nodes": [{"knowledge_id": "heap", "name": "堆序性质"}],
    }


def test_repository_keeps_immutable_revisions_and_review_is_conflict_safe(tmp_path):
    repository = SubjectLibraryRepository(tmp_path)
    stored = repository.save_revision(_library())
    loaded = repository.load_revision(stored["library_id"], stored["revision_id"])
    accepted = repository.review_revision(
        stored["library_id"], stored["revision_id"], decision="accept", note="结构通过",
    )
    repeated = repository.review_revision(
        stored["library_id"], stored["revision_id"], decision="accept", note="重复请求",
    )
    assert loaded == stored
    assert accepted["lifecycle_status"] == "accepted"
    assert repeated["revision_id"] == accepted["revision_id"]
    assert repository.load_accepted("computer_science.data_structures")["revision_id"] == stored["revision_id"]
    with pytest.raises(SubjectLibraryConflict):
        repository.review_revision(
            stored["library_id"], stored["revision_id"], decision="reject", note="冲突决定",
        )


def test_bound_course_resolves_the_pinned_revision_not_a_dynamic_rebuild(tmp_path):
    repository = SubjectLibraryRepository(tmp_path)
    first = repository.save_revision(_library())
    changed = deepcopy(first)
    changed["revision_id"] = "revision-2"
    changed["supersedes_revision_id"] = first["revision_id"]
    changed["nodes"].append({"knowledge_id": "heapify", "name": "堆构建"})
    second = repository.save_revision(changed)
    course = {"course_id": "course-ds", "knowledge_library_binding": repository.binding_for(first)}
    resolved = repository.resolve_for_course(course)
    assert first["revision_id"] != second["revision_id"]
    assert resolved["revision_id"] == first["revision_id"]
    assert all(node["name"] != "堆构建" for node in resolved["nodes"])
